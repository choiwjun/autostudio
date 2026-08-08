import hmac
import json
import logging
import os
import re
import threading
from datetime import timedelta

import config as config_mod
import db
import requests
from fastapi import Body, Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

logger = logging.getLogger("server")

# v15.1: 이미지 다운로드 프록시 — 외부 CDN URL은 cross-origin이라 <a download>가
# 무시되고 브라우저가 새 탭으로 열어버림. DB 저장 URL만 서버가 받아 attachment로
# 되돌려준다. 임의 URL 파라미터는 받지 않아 오픈 프록시/SSRF 우회 불가.
IMAGE_DOWNLOAD_TIMEOUT = 30
IMAGE_DOWNLOAD_MAX_BYTES = 20 * 1024 * 1024
IMAGE_DOWNLOAD_MAX_REDIRECTS = 3


def _fetch_image_bytes(url):
    """반환: (바이트, content_type). HTTPS만, 리다이렉트도 HTTPS 한정, 크기 상한
    스트리밍 검사, 비이미지 응답 거부 — 위반은 명확한 HTTP 오류로 변환."""
    if not url or not url.startswith("https://"):
        raise HTTPException(status_code=400, detail="HTTPS 이미지 URL이 아닙니다")
    current = url
    for _ in range(IMAGE_DOWNLOAD_MAX_REDIRECTS + 1):
        try:
            resp = requests.get(current, timeout=IMAGE_DOWNLOAD_TIMEOUT,
                                stream=True, allow_redirects=False)
        except requests.RequestException as e:
            raise HTTPException(
                status_code=502, detail=f"이미지 수신 실패: {e}") from e
        if resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("Location", "")
            if not location.startswith("https://"):
                raise HTTPException(
                    status_code=502, detail="HTTPS가 아닌 리다이렉트 거부")
            current = location
            continue
        if resp.status_code != 200:
            raise HTTPException(
                status_code=502, detail=f"이미지 서버 응답 {resp.status_code}")
        content_type = resp.headers.get("Content-Type", "")
        if not content_type.startswith("image/"):
            raise HTTPException(
                status_code=502, detail="이미지가 아닌 응답입니다")
        chunks, size = [], 0
        with resp:
            for chunk in resp.iter_content(chunk_size=65536):
                size += len(chunk)
                if size > IMAGE_DOWNLOAD_MAX_BYTES:
                    raise HTTPException(
                        status_code=502, detail="이미지가 크기 상한을 초과했습니다")
                chunks.append(chunk)
        return b"".join(chunks), content_type
    raise HTTPException(status_code=502, detail="리다이렉트 횟수 초과")


class SeedIn(BaseModel):
    keyword: str
    category: str = ""


class KeywordPatch(BaseModel):
    active: bool


class CollectIn(BaseModel):
    trigger: str = "manual"  # "schedule" = cron-job.org 대체 스케줄러 (전 구간, v3)


class DraftIn(BaseModel):
    keyword_id: int


class FeedbackIn(BaseModel):
    # v10 [6]: 게시 후 성과 피드백 — 서치어드바이저에서 확인한 유입/체류를 수동 입력
    published_at: str = ""
    performance_score: float  # 0~100 (유입·체류 반영)
    note: str = ""


class PublishedUrlIn(BaseModel):
    # v17: 게시 URL 등록 — AdPost 리포트 매칭의 기준 키 (게시 파이프라인)
    url: str


def _unavailable_search_evidence(reference_date, searched_at):
    return {
        "status": "unavailable",
        "searched_at_kst": searched_at,
        "reference_date": reference_date.isoformat(),
        "items": [],
    }


def _latest_search_snapshot(cfg, keyword, reference_date):
    import analyzer
    from naver_client import NaverAPIError, NaverClient

    searched_at = config_mod.now_kst_iso()
    if not cfg.get("client_id") or not cfg.get("client_secret"):
        return None, _unavailable_search_evidence(reference_date, searched_at)
    client = NaverClient(cfg["client_id"], cfg["client_secret"])
    try:
        snapshot = analyzer.analyze_keyword(
            client, keyword, reference_date, searched_at_kst=searched_at)
    except NaverAPIError as e:
        logger.warning("latest search unavailable keyword=%s: %s", keyword, e)
        return None, _unavailable_search_evidence(reference_date, searched_at)
    return snapshot, snapshot["search_evidence"]


def _refresh_outline_structure(structure, search_evidence):
    try:
        parsed = json.loads(structure) if isinstance(structure, str) else structure
    except json.JSONDecodeError:
        parsed = {}
    parsed = parsed if isinstance(parsed, dict) else {}
    parsed["search_evidence"] = search_evidence
    return json.dumps(parsed, ensure_ascii=False)


def boost_for_score(score):
    """v11: 성과 점수 → priority 보너스. 피드백 재입력 시 차액만 가산해 멱등."""
    if score is None:
        return 0
    if score >= 70:
        return 10
    if score < 30:
        return -10
    return 0


# v14 §3: 백분위 자가보정 임계 — 프리셋·배지가 절대값 하드코딩 대신 데이터 분포를
# 따라가 재보정 커밋(v12/v13형)을 원천 차단. 표본 부족·P50=0이면 폴백 절대값.
MIN_PERCENTILE_SAMPLES = 20
THRESHOLD_SPECS = (
    # (응답 키, 지표, 분위, 폴백 절대값)
    ("ai_cite", "ai_cite_idx", 0.5, 0.6),
    ("demand", "demand_idx", 0.5, 0.001),
    ("opportunity", "opportunity", 0.75, 20.0),
)
RISING_GROWTH_MIN = 0.1  # 상승 프리셋: 최근 7일 평균이 이전 23일 대비 +10% 이상


def resolve_thresholds(d):
    """반환: (임계 dict, 소스 'percentile'|'fallback'|'mixed') — 조회 시마다 계산
    (키워드 ≤ 500, 쿼리 비용 무시 가능 — 스펙 §3.3). 지표별로 폴백 판단."""
    thresholds, sources = {}, set()
    for key, metric, q, fallback in THRESHOLD_SPECS:
        n, pct = d.percentiles(metric)
        if n >= MIN_PERCENTILE_SAMPLES and pct.get(0.5, 0) > 0:
            thresholds[key] = pct[q]
            sources.add("percentile")
        else:
            thresholds[key] = fallback
            sources.add("fallback")
    source = sources.pop() if len(sources) == 1 else "mixed"
    return thresholds, source


def create_app(cfg):
    # v15: env 소문자 정규화 — 'Production' 같은 대소문자 변형이 fail-closed와
    # require_token 분기를 모두 우회하던 문제 차단
    env = (cfg.get("env") or "development").strip().lower()
    # v3: fail-closed — 프로덕션에서 토큰 미설정 시 기동 거부 (스펙 §7).
    # v2는 토큰이 비면 인증을 생략해 설정 실수가 무인증 쓰기 API로 이어졌음.
    # v15: 'development'가 아닌 모든 값(prod/Production/오타 포함)은 프로덕션 취급 —
    # 토큰 없으면 기동 자체가 거부되므로 require_token의 빈 토큰 통과 경로도 소멸.
    # 로컬 개발(ENV 미설정/development)만 인증 생략 허용
    if env != "development" and not cfg.get("dashboard_token", ""):
        raise RuntimeError(
            "DASHBOARD_TOKEN required when ENV is not 'development' (fail-closed)")
    app = FastAPI()

    @app.middleware("http")
    async def strip_api_prefix(request, call_next):
        # Vercel: api/index.py는 /api/* 에만 매핑되고 최신 런타임은 rewrite된
        # destination path(/api)로 라우팅한다. /api 프리픽스를 제거해 라우트와
        # 매칭시킨다. 프리픽스 없는 요청(로컬)은 그대로 통과시킨다.
        path = request.url.path
        if path == "/api":
            request.scope["path"] = "/"
            request.scope["raw_path"] = b"/"
        elif path.startswith("/api/"):
            new_path = path[4:]
            request.scope["path"] = new_path
            request.scope["raw_path"] = new_path.encode()
        return await call_next(request)

    state = {"db": None}
    lock = threading.Lock()

    def get_db():
        if state["db"] is None:
            state["db"] = db.Database(cfg["db_url"])
            state["db"].init()
        return state["db"]

    def run_db(fn):
        # 서버리스에서 유휴 종료된 커넥션 대비: 연결 오류 1회 재연결 후 재시도 (스펙 §3)
        with lock:
            try:
                return fn(get_db())
            except db.CONNECTION_ERRORS:
                state["db"] = None
                return fn(get_db())

    def require_token(authorization: str = Header(default="")):
        # v6: 로컬 개발(development)은 토큰이 설정돼 있어도 인증 생략 — README
        # "로컬 개발만 인증 생략"과 일치. .env.local에 DASHBOARD_TOKEN이 있어도
        # 개발 편의를 위해 쓰기 API가 401을 내지 않도록 한다 (프로덕션만 강제).
        if env == "development":
            return
        # v15: 빈 토큰 통과 경로 제거 — 기동 시 fail-closed로 비개발 환경의 빈 토큰은
        # 이미 거부됐으므로 여기선 토큰이 반드시 존재. 없으면(설정 오류) 전부 401.
        token = cfg.get("dashboard_token", "")
        if not token or not hmac.compare_digest(authorization, f"Bearer {token}"):
            raise HTTPException(status_code=401, detail="invalid token")

    # v15: 읽기 API도 인증 — 키워드·성과 데이터는 수익 전략 자산이라 공개 금지.
    # (개발 환경은 require_token이 생략하므로 로컬 동작 불변)
    @app.get("/keywords", dependencies=[Depends(require_token)])
    def list_keywords(sort: str = "priority", sort_dir: str = "desc",
                      category: str = "", commercial_min: float = 0,
                      click_min: float = 0, q: str = "",
                      discovered_within: int = 0,
                      preset: str = "ai_pick", show_inactive: int = 0,
                      page: int = 1, page_size: int = 50):
        page = max(page, 1)
        page_size = min(max(page_size, 1), 200)
        discovered_since = ""
        if discovered_within > 0:
            discovered_since = (
                config_mod.today_kst() - timedelta(days=discovered_within)
            ).isoformat()
        # v4: 유망 프리셋 — 기회≥70 & 쇼핑클릭≥0.5 & 수요지수≥0.01 (쇼핑 검색 API 종료 대체)
        # v9: 실측 기반 재정의 — opp 최대 24.2, 쇼핑클릭>0은 9개(모두 여름휴가 계열,
        #     금융·보험과 카테고리 미매칭). 쇼핑클릭 필터는 교집합 0건 유발 → 제거.
        #     유망 = 기회≥20(성장 신호) & 수요≥0.001. 쇼핑클릭은 별도 열로만 노출.
        # v6: 기본 프리셋 'ai_pick' — AI 인용 가능성 + 수요(조회수 프록시) 기반,
        #     애드포스트 1차 목표에 맞는 '지금 써야 할 키워드' 상위 20개 중심
        # v14: 임계는 백분위 자가보정 (ai_pick = ai_cite≥P50 & demand≥P50,
        #     promising = opportunity≥P75 & demand≥P50) — 폴백은 v13 절대값.
        #     thresholds 필드로 대시보드에 노출해 배지·툴팁이 같은 임계를 쓴다.
        #     rising = demand_growth≥0.1 & demand≥P50 (성공 기준 ② 검증용).
        thresholds, threshold_source = run_db(resolve_thresholds)
        opportunity_min, demand_min, ai_cite_min, growth_min = 0.0, 0.0, 0.0, None
        if preset == "promising":
            opportunity_min, demand_min = thresholds["opportunity"], thresholds["demand"]
        elif preset == "ai_pick":
            ai_cite_min, demand_min = thresholds["ai_cite"], thresholds["demand"]
        elif preset == "rising":
            demand_min, growth_min = thresholds["demand"], RISING_GROWTH_MIN
        filters = dict(category=category, commercial_min=commercial_min, q=q,
                       discovered_since=discovered_since,
                       active=None if show_inactive else 1,
                       opportunity_min=opportunity_min, demand_min=demand_min,
                       click_min=click_min, ai_cite_min=ai_cite_min,
                       growth_min=growth_min)
        items = run_db(lambda d: d.query_keywords(
            sort=sort, sort_dir=sort_dir, limit=page_size,
            offset=(page - 1) * page_size, **filters))
        total = run_db(lambda d: d.count_keywords(**filters))
        return {"items": items, "count": total, "page": page, "page_size": page_size,
                "thresholds": thresholds, "threshold_source": threshold_source}

    @app.get("/keywords/{keyword_id}", dependencies=[Depends(require_token)])
    def keyword_detail(keyword_id: int):
        kw = run_db(lambda d: d.get_keyword(keyword_id))
        if not kw:
            raise HTTPException(status_code=404, detail="not found")
        history = run_db(lambda d: d.get_history(keyword_id))
        return {"keyword": kw["keyword"], "active": kw["active"], "history": history}

    @app.patch("/keywords/{keyword_id}", dependencies=[Depends(require_token)])
    def patch_keyword(keyword_id: int, body: KeywordPatch):
        kw = run_db(lambda d: d.get_keyword(keyword_id))
        if not kw:
            raise HTTPException(status_code=404, detail="not found")
        run_db(lambda d: d.set_active(keyword_id, 1 if body.active else 0))
        return {"ok": True}

    @app.get("/seeds", dependencies=[Depends(require_token)])
    def list_seeds():
        return run_db(lambda d: d.list_seeds())

    @app.post("/seeds", dependencies=[Depends(require_token)])
    def add_seed(seed: SeedIn):
        run_db(lambda d: d.add_seed(seed.keyword, seed.category))
        return {"ok": True}

    @app.delete("/seeds/{seed_id}", dependencies=[Depends(require_token)])
    def delete_seed(seed_id: int):
        run_db(lambda d: d.delete_seed(seed_id))
        return {"ok": True}

    @app.post("/collect", dependencies=[Depends(require_token)])
    def trigger_collect(body: CollectIn = Body(default_factory=CollectIn)):
        import collect
        if body.trigger == "schedule":
            # v3: cron-job.org 대체 경로 — 전체 파이프라인(발굴·수요·은퇴·보존).
            # Vercel 60초 한도 내라 예산(45초)을 걸어 전 구간 예산 적용 + 잔여는 다음 실행이 순환
            return collect.run_collection(
                cfg, trigger="schedule",
                budget_seconds=cfg.get("manual_budget_seconds", 45))
        return collect.run_collection(
            cfg, trigger="manual",
            budget_seconds=cfg.get("manual_budget_seconds", 45))

    @app.get("/status", dependencies=[Depends(require_token)])
    def status():
        runs = run_db(lambda d: d.get_last_runs(5))
        # v3: partial/failed는 성공 수집으로 집계하지 않음 (UX §5.2 경고 기준)
        last_success = next((r for r in runs if r["status"] == "done"), None)
        return {
            "keyword_count": run_db(lambda d: d.count_active()),
            "seed_count": len(run_db(lambda d: d.list_seeds())),
            "today": config_mod.today_kst().isoformat(),
            "last_run": runs[0] if runs else None,
            "last_success": last_success,
        }

    @app.get("/categories", dependencies=[Depends(require_token)])
    def categories():
        return run_db(lambda d: d.list_categories())

    @app.get("/outlines/{keyword_id}", dependencies=[Depends(require_token)])
    def get_outline(keyword_id: int):
        outline = run_db(lambda d: d.get_outline(keyword_id))
        if not outline:
            raise HTTPException(status_code=404, detail="outline not found")
        return outline

    @app.post("/outlines/{keyword_id}", dependencies=[Depends(require_token)])
    def analyze_outline(keyword_id: int):
        # v16: 블로그+뉴스 최신 검색 근거와 KST 기준일을 outline에 함께 저장
        kw = run_db(lambda d: d.get_keyword(keyword_id))
        if not kw:
            raise HTTPException(status_code=404, detail="not found")
        import outline as outline_mod
        reference_date = config_mod.today_kst()
        snap, evidence = _latest_search_snapshot(cfg, kw["keyword"], reference_date)
        descriptions = snap["top_descriptions"] if snap else []
        structure = outline_mod.build_outline_structure(descriptions, evidence)
        run_db(lambda d: d.upsert_outline(
            keyword_id, reference_date.isoformat(), structure))
        return run_db(lambda d: d.get_outline(keyword_id))

    @app.post("/drafts", dependencies=[Depends(require_token)])
    def create_draft(body: DraftIn):
        # v7: 글 초안 생성 — 골격 기반 (v9: Token Plan HTTP API, v10: 2패스+검수)
        import draft_pipeline
        kw = run_db(lambda d: d.get_keyword(body.keyword_id))
        if not kw:
            raise HTTPException(status_code=404, detail="not found")
        outline = run_db(lambda d: d.get_outline(body.keyword_id))
        # v9: 골격 없이 초안 생성 금지 — 빈 구조로 진행하면 모델 상상의 글이 됨 (독창성·어뷰징 위험)
        if not outline:
            raise HTTPException(
                status_code=400,
                detail="먼저 상위글 골격 분석이 필요합니다 — '글 생성' 플로우에서 골격 분석 후 다시 시도하세요",
            )
        reference_date = config_mod.today_kst()
        snap, search_evidence = _latest_search_snapshot(
            cfg, kw["keyword"], reference_date)
        quality_warnings = []
        if snap:
            import outline as outline_mod
            structure = outline_mod.build_outline_structure(
                snap["top_descriptions"], search_evidence)
            run_db(lambda d: d.upsert_outline(
                body.keyword_id, reference_date.isoformat(), structure))
        else:
            try:
                parsed = json.loads(outline["structure"])
            except (TypeError, json.JSONDecodeError):
                parsed = {}
            structure = json.dumps({
                "questions": parsed.get("questions", []),
                "comparisons": parsed.get("comparisons", []),
                "facts": [],
                "headings": parsed.get("headings", []),
                "search_evidence": search_evidence,
            }, ensure_ascii=False)
            quality_warnings.append("search_evidence_unavailable")
        if search_evidence.get("status") == "empty":
            quality_warnings.append("search_evidence_empty")
        try:
            # v16: 생성 직전 최신 검색 근거·KST 기준일을 2패스 전체에 전달
            # v17.1: 25초 재생성 예산+55초 하드 예산은 Vercel 60초 한도 전용.
            # 로컬(ENV=development)은 서버리스 한도가 없어 예산 해제 — 2패스
            # 1사이클이 25초를 항상 초과해 검수 미달 재생성이 실제로는 한 번도
            # 실행되지 않고 경고만 반환되던 문제를 개발 환경에서 제거.
            serverless = cfg.get("env") != "development"
            draft, failed_checks = draft_pipeline.generate_two_pass(
                kw["keyword"], structure,
                retry_budget_seconds=25 if serverless else None,
                current_date=reference_date, search_evidence=search_evidence,
                hard_budget_seconds=(draft_pipeline.HARD_BUDGET_SECONDS
                                     if serverless else None))

        except draft_pipeline.DraftGenerationError as e:
            # v15: 구조화 로그 — 배포 환경에서 초안 실패 원인을 추적할 수 있게
            logger.warning("draft generation failed kw_id=%s kw=%s: %s",
                           body.keyword_id, kw["keyword"], e)
            raise HTTPException(status_code=503, detail=str(e))
        created_at = config_mod.now_kst_iso()
        draft_id = run_db(lambda d: d.insert_draft(
            body.keyword_id, draft["title"], draft["first_paragraph"],
            draft["body"], created_at=created_at))
        result = run_db(lambda d: d.get_draft(draft_id))
        all_warnings = quality_warnings + failed_checks
        if all_warnings:
            result["quality_warnings"] = all_warnings
        return result

    @app.get("/drafts/{draft_id}", dependencies=[Depends(require_token)])
    def get_draft(draft_id: int):
        draft = run_db(lambda d: d.get_draft(draft_id))
        if not draft:
            raise HTTPException(status_code=404, detail="not found")
        return draft

    # v15.1: 생성 이미지 다운로드 프록시 — DB 저장 URL만 사용(임의 URL 파라미터
    # 없음), attachment 헤더로 브라우저 다운로드 보장. 파일명은 고정 안전 이름.
    @app.get("/drafts/{draft_id}/image-download",
             dependencies=[Depends(require_token)])
    def download_draft_image(draft_id: int):
        draft = run_db(lambda d: d.get_draft(draft_id))
        if not draft:
            raise HTTPException(status_code=404, detail="not found")
        if not draft.get("image_url"):
            raise HTTPException(
                status_code=404, detail="대표 이미지가 아직 생성되지 않았습니다")
        content, content_type = _fetch_image_bytes(draft["image_url"])
        return Response(
            content=content, media_type=content_type,
            headers={"Content-Disposition":
                     'attachment; filename="blog-representative.png"'})

    @app.get("/drafts/{draft_id}/section-images/{image_index}/download",
             dependencies=[Depends(require_token)])
    def download_section_image(draft_id: int, image_index: int):
        draft = run_db(lambda d: d.get_draft(draft_id))
        if not draft:
            raise HTTPException(status_code=404, detail="not found")
        urls = []
        if draft.get("section_images"):
            try:
                parsed = json.loads(draft["section_images"])
                if isinstance(parsed, list):
                    urls = parsed
            except json.JSONDecodeError:
                pass
        if not (0 <= image_index < len(urls)):
            raise HTTPException(
                status_code=404, detail="해당 순서의 섹션 이미지가 없습니다")
        content, content_type = _fetch_image_bytes(urls[image_index])
        return Response(
            content=content, media_type=content_type,
            headers={"Content-Disposition":
                     f'attachment; filename="blog-section-{image_index + 1}.png"'})

    @app.post("/drafts/{draft_id}/image", dependencies=[Depends(require_token)])
    def generate_draft_image(draft_id: int):
        # v7: 블로그 이미지 생성 — 키 미발급 시 503(명확한 안내), 텍스트 초안은 유지
        import image_gen
        draft = run_db(lambda d: d.get_draft(draft_id))
        if not draft:
            raise HTTPException(status_code=404, detail="not found")
        try:
            url = image_gen.generate_image(
                run_db(lambda d: d.get_keyword(draft["keyword_id"]))["keyword"],
                draft["title"])
        except image_gen.ImageGenerationError as e:
            logger.warning("image generation failed draft_id=%s: %s", draft_id, e)
            raise HTTPException(status_code=503, detail=str(e))
        run_db(lambda d: d.update_draft_image(
            draft_id, url, config_mod.now_kst_iso()))
        return run_db(lambda d: d.get_draft(draft_id))

    # v17: 요청당 섹션 이미지 시간 창 — 이미지 1장 타임아웃(55초)보다 짧아야
    # Vercel 60초 한도 내 완료. 나머지 분량은 재호출(증분) 또는 컬렉트 배치로.
    SECTION_IMAGE_WINDOW_SECONDS = 38

    @app.post("/drafts/{draft_id}/section-images", dependencies=[Depends(require_token)])
    def generate_section_images(draft_id: int):
        # v10 [5]: 섹션 이미지 최대 8장 — 본문 H2 소제목에서 주제 추출, 체류·스크롤 증가
        # v17: 증분 생성 — 기존은 8장×55초 순차라 60초 한도에 죽어 비용만 손실.
        # 이제 시간 창 내에서 생성되는 즉시 저장하고, 나머지는 재호출이 이어서 생성.
        import json
        import image_gen
        draft = run_db(lambda d: d.get_draft(draft_id))
        if not draft:
            raise HTTPException(status_code=404, detail="not found")
        h2s = re.findall(r"^##\s+(.+)$", draft["body"], flags=re.M)
        # FAQ 섹션 제외 + 길이 제한
        sections = [h for h in h2s if "자주 묻는 질문" not in h][:8]
        if not sections:
            raise HTTPException(status_code=400, detail="본문에 H2 소제목이 없어 섹션 이미지를 생성할 수 없습니다")
        existing = []
        if draft.get("section_images"):
            try:
                parsed = json.loads(draft["section_images"])
                if isinstance(parsed, list):
                    existing = parsed
            except json.JSONDecodeError:
                existing = []
        if len(existing) >= len(sections):
            return run_db(lambda d: d.get_draft(draft_id))  # 전부 생성됨
        try:
            new_urls = image_gen.generate_section_images(
                run_db(lambda d: d.get_keyword(draft["keyword_id"]))["keyword"],
                draft["title"], sections, start_index=len(existing),
                budget_seconds=SECTION_IMAGE_WINDOW_SECONDS)
        except image_gen.ImageGenerationError as e:
            logger.warning("section image generation failed draft_id=%s: %s", draft_id, e)
            raise HTTPException(status_code=503, detail=str(e))
        if new_urls:  # 부분 성공도 즉시 저장 — 중도 종료 손실 차단 (버그 3)
            run_db(lambda d: d.update_draft_section_images(
                draft_id, json.dumps(existing + new_urls, ensure_ascii=False),
                config_mod.now_kst_iso()))
        return run_db(lambda d: d.get_draft(draft_id))

    @app.post("/drafts/{draft_id}/feedback", dependencies=[Depends(require_token)])
    def record_draft_feedback(draft_id: int, body: FeedbackIn):
        # v10 [6]: 게시 후 성과 기록 + 키워드 점수 보정.
        # 성과(0~100)를 해당 키워드 priority에 반영해 '잘 된 키워드 우선' 학습 루프.
        # v11: boost는 (새 점수 보너스 - 기존 점수 보너스) 차액만 가산 — 같은 초안에
        # 피드백을 반복 전송해도 누적되지 않는 멱등 처리. 성과 우수(>=70) 키워드는
        # 은퇴 판정에서도 보호 (db.find_retire_candidates의 performance_boost 조건).
        # v14: 점수 저장과 boost 가산을 단일 트랜잭션으로 — 중간 실패 시 재시도의
        # 차액이 0이 되어 boost가 유실되던 틈 차단. 누적 boost는 [-20, 20] 클램프.
        draft = run_db(lambda d: d.get_draft(draft_id))
        if not draft:
            raise HTTPException(status_code=404, detail="not found")
        score = max(0.0, min(100.0, body.performance_score))
        published = body.published_at or config_mod.now_kst_iso()
        delta = boost_for_score(score) - boost_for_score(draft.get("performance_score"))
        run_db(lambda d: d.record_draft_feedback(
            draft_id, draft["keyword_id"], published, score, body.note,
            config_mod.now_kst_iso(), delta))
        return run_db(lambda d: d.get_draft(draft_id))

    # ---------- v17: 게시 파이프라인 + AdPost 피드백 자동화 ----------

    @app.post("/drafts/{draft_id}/published-url",
              dependencies=[Depends(require_token)])
    def set_published_url(draft_id: int, body: PublishedUrlIn):
        draft = run_db(lambda d: d.get_draft(draft_id))
        if not draft:
            raise HTTPException(status_code=404, detail="not found")
        url = (body.url or "").strip()
        if not url.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="올바른 URL이 아닙니다")
        run_db(lambda d: d.set_draft_published_url(
            draft_id, url, config_mod.now_kst_iso()))
        return run_db(lambda d: d.get_draft(draft_id))

    @app.get("/drafts/{draft_id}/export", dependencies=[Depends(require_token)])
    def export_draft(draft_id: int):
        # v17: 게시용 마크다운 내보내기 — 네이버 블로그는 쓰기 API가 없어
        # 복붙이 최종 단계. 이미지 포함 완성 문서로 마찰을 최소화한다 (고도화 3)
        import publish
        draft = run_db(lambda d: d.get_draft(draft_id))
        if not draft:
            raise HTTPException(status_code=404, detail="not found")
        markdown = publish.build_export_markdown(draft)
        return Response(
            content=markdown.encode("utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition":
                     f'attachment; filename="blog-draft-{draft_id}.md"'})

    ADPOST_IMPORT_MAX_BYTES = 5 * 1024 * 1024

    @app.post("/adpost/import", dependencies=[Depends(require_token)])
    async def import_adpost_report(file: UploadFile = File(...)):
        # v17: AdPost 리포트 CSV → 초안 매칭 → 성과 점수·priority 자동 보정.
        # 수동 점수 입력(FeedbackIn)의 자동화 대체 경로 (고도화 1).
        import adpost
        raw = await file.read()
        if len(raw) > ADPOST_IMPORT_MAX_BYTES:
            raise HTTPException(status_code=400, detail="CSV가 너무 큽니다 (5MB 상한)")
        try:
            rows = adpost.parse_adpost_csv(raw)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        now = config_mod.now_kst_iso()
        matched, unmatched = [], 0
        for row in rows:
            draft = (run_db(lambda d, u=row["url"]: d.find_draft_by_published_url(u))
                     if row["url"] else None)
            if not draft and row["title"]:
                draft = run_db(
                    lambda d, t=row["title"]: d.find_draft_by_title(t))
            if not draft:
                unmatched += 1
                continue
            score = adpost.adpost_performance_score(
                row["revenue"], row["impressions"], row["clicks"])
            delta = (boost_for_score(score)
                     - boost_for_score(draft.get("performance_score")))
            run_db(lambda d, dr=draft, r=row, s=score, dl=delta: d.record_adpost_metrics(
                dr["id"], dr["keyword_id"], r["revenue"], r["impressions"],
                r["clicks"], s, now, now, dl))
            matched.append({"draft_id": draft["id"], "title": draft["title"],
                            "revenue": row["revenue"], "performance_score": score})
        return {"matched": len(matched), "unmatched": unmatched,
                "results": matched}

    @app.get("/")
    def index():
        return FileResponse(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "static", "index.html"))

    return app


app = create_app(config_mod.load_config())
