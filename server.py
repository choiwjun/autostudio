import hmac
import os
import re
import threading
from datetime import timedelta

import config as config_mod
import db
from fastapi import Body, Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel


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
    env = cfg.get("env", "development")
    # v3: fail-closed — 프로덕션에서 토큰 미설정 시 기동 거부 (스펙 §7).
    # v2는 토큰이 비면 인증을 생략해 설정 실수가 무인증 쓰기 API로 이어졌음.
    # 로컬 개발(ENV 미설정/development)만 인증 생략 허용
    if env == "production" and not cfg.get("dashboard_token", ""):
        raise RuntimeError("DASHBOARD_TOKEN required in production (fail-closed)")
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
        token = cfg.get("dashboard_token", "")
        if token and not hmac.compare_digest(authorization, f"Bearer {token}"):
            raise HTTPException(status_code=401, detail="invalid token")

    @app.get("/keywords")
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

    @app.get("/keywords/{keyword_id}")
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

    @app.get("/seeds")
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

    @app.get("/status")
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

    @app.get("/categories")
    def categories():
        return run_db(lambda d: d.list_categories())

    @app.get("/outlines/{keyword_id}")
    def get_outline(keyword_id: int):
        outline = run_db(lambda d: d.get_outline(keyword_id))
        if not outline:
            raise HTTPException(status_code=404, detail="outline not found")
        return outline

    @app.post("/outlines/{keyword_id}", dependencies=[Depends(require_token)])
    def analyze_outline(keyword_id: int):
        # v7: 상위글 골격 분석 — 블로그 검색 API description 캡처 → structure JSON 저장
        kw = run_db(lambda d: d.get_keyword(keyword_id))
        if not kw:
            raise HTTPException(status_code=404, detail="not found")
        import analyzer
        import outline as outline_mod
        from naver_client import NaverClient
        client = NaverClient(cfg.get("client_id", ""), cfg.get("client_secret", ""))
        snap = analyzer.analyze_keyword(client, kw["keyword"], config_mod.today_kst())
        structure = outline_mod.build_outline_structure(snap["top_descriptions"])
        day = config_mod.today_kst().isoformat()
        run_db(lambda d: d.upsert_outline(keyword_id, day, structure))
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
        structure = outline["structure"]
        try:
            # v10: 2패스 생성(골격→섹션 확장) + 검수 8항목. 검수 미달 항목은 응답에 포함.
            # v11: 재생성 시간 예산 25초 — 1사이클이 예산을 넘기면 재생성 없이 경고만
            # 반환 (서버리스에서 2사이클 풀 실행 시 타임아웃 리스크).
            draft, failed_checks = draft_pipeline.generate_two_pass(
                kw["keyword"], structure, retry_budget_seconds=25)
        except draft_pipeline.DraftGenerationError as e:
            raise HTTPException(status_code=503, detail=str(e))
        created_at = config_mod.now_kst_iso()
        draft_id = run_db(lambda d: d.insert_draft(
            body.keyword_id, draft["title"], draft["first_paragraph"],
            draft["body"], created_at=created_at))
        result = run_db(lambda d: d.get_draft(draft_id))
        if failed_checks:
            result["quality_warnings"] = failed_checks
        return result

    @app.get("/drafts/{draft_id}")
    def get_draft(draft_id: int):
        draft = run_db(lambda d: d.get_draft(draft_id))
        if not draft:
            raise HTTPException(status_code=404, detail="not found")
        return draft

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
            raise HTTPException(status_code=503, detail=str(e))
        run_db(lambda d: d.update_draft_image(
            draft_id, url, config_mod.now_kst_iso()))
        return run_db(lambda d: d.get_draft(draft_id))

    @app.post("/drafts/{draft_id}/section-images", dependencies=[Depends(require_token)])
    def generate_section_images(draft_id: int):
        # v10 [5]: 섹션 이미지 5~8장 — 본문 H2 소제목에서 주제 추출, 체류·스크롤 증가
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
        try:
            urls = image_gen.generate_section_images(
                run_db(lambda d: d.get_keyword(draft["keyword_id"]))["keyword"],
                draft["title"], sections)
        except image_gen.ImageGenerationError as e:
            raise HTTPException(status_code=503, detail=str(e))
        run_db(lambda d: d.update_draft_section_images(
            draft_id, json.dumps(urls, ensure_ascii=False), config_mod.now_kst_iso()))
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

    @app.get("/")
    def index():
        return FileResponse(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "static", "index.html"))

    return app


app = create_app(config_mod.load_config())
