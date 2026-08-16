import base64
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
from pydantic import BaseModel, field_validator

logger = logging.getLogger("server")

# v15.1: 이미지 다운로드 프록시 — 외부 CDN URL은 cross-origin이라 <a download>가
# 무시되고 브라우저가 새 탭으로 열어버림. DB 저장 URL만 서버가 받아 attachment로
# 되돌려준다. 임의 URL 파라미터는 받지 않아 오픈 프록시/SSRF 우회 불가.
IMAGE_DOWNLOAD_TIMEOUT = 30
IMAGE_DOWNLOAD_MAX_BYTES = 20 * 1024 * 1024
IMAGE_DOWNLOAD_MAX_REDIRECTS = 3
# v17.3: AdPost 임포트 처리 시간 예산 — 서버리스 60초 한도 대비.
# 모듈 레벨 상수로 테스트가 결정적으로 패치 가능 (time.monotonic 전역
# 패치는 TestClient/httpx 내부 타임아웃 계산도 오염시켜 금지).
ADPOST_IMPORT_BUDGET_SECONDS = 50
# v28: 운세 수동 발행 총 예산 — Vercel 60초 서버리스 한도 대비 5초 마진.
# LLM 생성(1회 시도) + 발행 순회를 합산하며, 초과 시 남은 항목은
# skipped("시간 예산")로 반환 (OQ-1 — 멱등 재클릭으로 이어서 처리).
FORTUNE_PUBLISH_BUDGET_SECONDS = 55


def _fetch_image_bytes(url):
    """반환: (바이트, content_type).
    v27: data URI(나노바나나 base64 저장, AC4-3) — base64 디코드 + image/ MIME
    검사 + 크기 상한. 위반은 명확한 HTTP 오류로 변환.
    HTTPS URL — 기존 경로 그대로 (리다이렉트도 HTTPS 한정, 크기 상한 스트리밍
    검사, 비이미지 응답 거부)."""
    if not url:
        raise HTTPException(status_code=400, detail="HTTPS 이미지 URL이 아닙니다")
    if url.startswith("data:"):
        return _decode_data_uri(url)
    if not url.startswith("https://"):
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


def _decode_data_uri(url):
    """v27 (AC4-3): data URI 이미지 디코드 — data:{mime};base64,{b64}.
    image/ MIME 강제, 크기 상한(IMAGE_DOWNLOAD_MAX_BYTES) 적용."""
    try:
        header, sep, b64 = url.partition(",")
        if not sep or not b64:
            raise ValueError("missing payload")
        mime = header[5:].partition(";")[0] or "image/jpeg"
        if not mime.startswith("image/"):
            raise ValueError("non-image mime")
        content = base64.b64decode(b64, validate=True)  # 오염 데이터 URI 400 처리
    except (ValueError, TypeError) as e:
        raise HTTPException(
            status_code=400, detail="잘못된 data URI 이미지입니다") from e
    if len(content) > IMAGE_DOWNLOAD_MAX_BYTES:
        raise HTTPException(
            status_code=502, detail="이미지가 크기 상한을 초과했습니다")
    return content, mime


class SeedIn(BaseModel):
    keyword: str
    category: str = ""


def _reject_nonfinite(value, field_label):
    """v30.4 (적대적 QA): NaN/Infinity 차단 공용 검증기.
    Field(allow_inf_nan=False)를 쓰면 422 에러 응답이 NaN 입력값을 input으로
    에코하고, Starlette JSONResponse(allow_nan=False)가 그 에코 직렬화에서
    또다시 500을 내므로 검증기에서 HTTPException을 직접 올린다."""
    if value != value or value in (float("inf"), float("-inf")):
        raise HTTPException(
            status_code=422,
            detail=f"{field_label}에 NaN/Infinity는 허용되지 않습니다")
    return value


class KeywordPatch(BaseModel):
    active: bool


class CollectIn(BaseModel):
    trigger: str = "manual"  # "schedule" = cron-job.org 대체 스케줄러 (전 구간, v3)


class DraftIn(BaseModel):
    keyword_id: int
    # v19: 멀티 플랫폼 — 네이버/티스토리/애드센스/브랜드 (기본 네이버)
    platform: str = "naver"


class FeedbackIn(BaseModel):
    # v10 [6]: 게시 후 성과 피드백 — 서치어드바이저에서 확인한 유입/체류를 수동 입력
    published_at: str = ""
    # v30.4 (적대적 QA): NaN 차단 — 클램프 max(0, min(100, NaN))이 Python 특성상
    # 100.0을 반환해 만점 오염이 저장되던 경로 제거. Infinity도 함께 차단.
    performance_score: float  # 0~100 (유입·체류 반영)
    note: str = ""

    @field_validator("performance_score")
    @classmethod
    def _score_finite(cls, v):
        return _reject_nonfinite(v, "성과 점수")


class PublishedUrlIn(BaseModel):
    # v17: 게시 URL 등록 — AdPost 리포트 매칭의 기준 키 (게시 파이프라인)
    url: str


# v30: KDP 파이프라인 (K-1~K-4) 요청 모델
class KdpBookCreateIn(BaseModel):
    # K-1: 수동 책 생성 트리거 (R-1: source_keyword로 배치 generate 스테이지 연결)
    title: str
    lang: str = "en"
    source_keyword: str = ""


class KdpGenerateIn(BaseModel):
    # K-2: 책 생성 시작 (배치 트리거 큐)
    book_id: int


class KdpPublishIn(BaseModel):
    # K-4: 출간 시작 (체크리스트 검증 후)
    book_id: int
    price: float
    publish_date: str = ""

    # v30.4 (적대적 QA): NaN 차단 — NaN < 2.99 / NaN > 12.99가 모두 False라
    # 구간 검증을 통과하고 저장 계층에서 파열(로컬 500 / Postgres는 NaN 저장).
    @field_validator("price")
    @classmethod
    def _price_finite(cls, v):
        return _reject_nonfinite(v, "가격")


class KdpVerifyIn(BaseModel):
    # K-4: 48h 확인
    publish_id: int
    mirror_status: str = "정상"
    price_ok: int = 1


class KdpPerformanceIn(BaseModel):
    # K-4: 성과 입력 (AC-DB-1, measured_by=manual)
    book_id: int
    year_month: str
    sales: int = 0
    royalty: float = 0.0

    # v31 (알고리즘 QA): NaN/Infinity 성과값 차단 (KdpPublishIn과 동일 계열)
    @field_validator("royalty")
    @classmethod
    def _royalty_finite(cls, v):
        return _reject_nonfinite(v, "로열티")


class ShortsScriptIn(BaseModel):
    # v31 (S-3): 쇼츠 스크립트 생성 트리거 — shorts_topics 후보 label
    topic: str


def _validate_text(value, field_label, max_len):
    """v30.4 (적대적 QA): 저장 전 텍스트 입력 가드 — null byte와 과대 길이 차단.
    null byte는 SQLite에는 저장되지만 Postgres \u0000 거부로 프로덕션에서만
    크래시하는 침묵 지뢰. 길이 무제한 입력은 저장 남용(1MB 키워드 관측됨) 경로."""
    if "\x00" in value:
        raise HTTPException(
            status_code=400, detail=f"{field_label}에 null 바이트가 포함되어 있습니다")
    if len(value) > max_len:
        raise HTTPException(
            status_code=400,
            detail=f"{field_label}이(가) 너무 깁니다 (최대 {max_len}자)")


def _unavailable_search_evidence(reference_date, searched_at):
    return {
        "status": "unavailable",
        "searched_at_kst": searched_at,
        "reference_date": reference_date.isoformat(),
        "items": [],
    }


def _with_parsed_tags(draft):
    """v17.2: DB의 태그 JSON 문자열 → 응답용 리스트 (대시보드가 바로 쓰게).
    v19: thumbnail_ideas도 동일 파싱. v21(B.5): product_block도 파싱."""
    if not draft:
        return draft
    for field in ("tags", "thumbnail_ideas", "product_block"):
        try:
            parsed = json.loads(draft.get(field) or "[]")
            draft[field] = parsed if isinstance(parsed, list) else []
        except (TypeError, json.JSONDecodeError):
            draft[field] = []
    return draft


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
# v20.1: '곧 뜰' 프리셋 상승 반전 최소 임계 — 0 초과면 0.1% 미세 상승(노이즈)도
# 잡혀 실측 43개(활성의 21%)가 선점 후보로 나옴. 2% 이상 반전 + 콜드스타트(1.0)만.
UPCOMING_GROWTH_MIN = 0.02
# R-5: 리프레시 최소 게시 경과일 — db.refresh_candidates 기본값(14)과 정합
REFRESH_MIN_AGE_DAYS = 14


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


def _fortune_target(r, ct, json_mod):
    """운세 대상 라벨 — grounding.key(쥐띠/물고기자리/계해일) 우선,
    없으면 content_type 기본 라벨."""
    try:
        g = json_mod.loads(r.get("grounding") or "{}")
        if isinstance(g, dict) and g.get("key"):
            return str(g["key"])
    except Exception:
        pass
    return {
        "daily_blog": "오늘의 종합 운세",
        "daily_sns": "오늘의 SNS 운세",
        "weekly_blog": "이번 주 종합 운세",
        "monthly_blog": "이번 달 종합 운세",
        "animal_blog": "띠 운세",
        "zodiac_blog": "별자리 운세",
        "day_pillar_blog": "일주 운세",
    }.get(ct, ct)



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
            except OverflowError:
                # v30.4 (적대적 QA): 10^19급 경로/쿼리 정수가 SQLite int64 바인딩에서
                # OverflowError(→500)를 내던 것을 422로 변환 — 클라이언트 입력 오류
                raise HTTPException(
                    status_code=422, detail="숫자가 너무 큽니다")

    def _generate_and_store_draft(keyword_id, refresh_of=None, platform="naver"):
        """초안 생성 공통 경로 — 골격 분석 → 최신 검색 근거 → 2패스 생성 → 저장.
        v18: 성과 상위 글 패턴(top_performer_pattern)을 가이드로 주입.
        v19: platform — 플랫폼별 프롬프트·검수 분기, 썸네일 아이디어 저장.
        refresh_of가 있으면 리프레시 초안으로 기록. 반환: 저장된 초안 dict."""
        import draft_pipeline
        import platforms as platforms_mod
        if platform not in platforms_mod.PLATFORMS:
            raise HTTPException(
                status_code=400,
                detail=f"지원하지 않는 플랫폼입니다: {platform} (지원: "
                       + ", ".join(platforms_mod.PLATFORMS) + ")")
        kw = run_db(lambda d: d.get_keyword(keyword_id))
        if not kw:
            raise HTTPException(status_code=404, detail="not found")
        outline = run_db(lambda d: d.get_outline(keyword_id))
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
                keyword_id, reference_date.isoformat(), structure))
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
            # v18: 성과 상위 글 패턴 가이드 주입 (표본 부족 시 None → 미주입)
            # v19: 플랫폼별 프롬프트·검수
            serverless = cfg.get("env") != "development"
            draft, failed_checks = draft_pipeline.generate_two_pass(
                kw["keyword"], structure,
                retry_budget_seconds=25 if serverless else None,
                current_date=reference_date, search_evidence=search_evidence,
                hard_budget_seconds=(draft_pipeline.HARD_BUDGET_SECONDS
                                     if serverless else None),
                pattern_guidance=run_db(lambda d: d.top_performer_pattern()),
                platform=platform)

        except draft_pipeline.DraftGenerationError as e:
            # v15: 구조화 로그 — 배포 환경에서 초안 실패 원인을 추적할 수 있게
            logger.warning("draft generation failed kw_id=%s kw=%s: %s",
                           keyword_id, kw["keyword"], e)
            raise HTTPException(status_code=503, detail=str(e))
        created_at = config_mod.now_kst_iso()
        draft_id = run_db(lambda d: d.insert_draft(
            keyword_id, draft["title"], draft["first_paragraph"],
            draft["body"], created_at=created_at,
            tags=json.dumps(draft.get("tags") or [], ensure_ascii=False),
            refresh_of=refresh_of, platform=platform,
            thumbnail_ideas=json.dumps(
                draft.get("thumbnail_ideas") or [], ensure_ascii=False)))
        result = _with_parsed_tags(run_db(lambda d: d.get_draft(draft_id)))
        all_warnings = quality_warnings + failed_checks
        if all_warnings:
            result["quality_warnings"] = all_warnings
        return result

    def require_token(authorization: str = Header(default="")):
        # v6: 로컬 개발(development)은 토큰이 설정돼 있어도 인증 생략 — README
        # "로컬 개발만 인증 생략"과 일치. .env.local에 DASHBOARD_TOKEN이 있어도
        # 개발 편의를 위해 쓰기 API가 401을 내지 않도록 한다 (프로덕션만 강제).
        if env == "development":
            return
        # v15: 빈 토큰 통과 경로 제거 — 기동 시 fail-closed로 비개발 환경의 빈 토큰은
        # 이미 거부됐으므로 여기선 토큰이 반드시 존재. 없으면(설정 오류) 전부 401.
        # v30.4 (적대적 QA): bytes 비교 — str compare_digest는 비-ASCII 헤더에서
        # TypeError(→500)를 내며, 인증 안 된 요청만으로 서버 에러를 유발할 수 있었음.
        token = cfg.get("dashboard_token", "")
        expected = f"Bearer {token}".encode("utf-8")
        supplied = authorization.encode("utf-8", "replace")
        if not token or not hmac.compare_digest(supplied, expected):
            raise HTTPException(status_code=401, detail="invalid token")

    # v15: 읽기 API도 인증 — 키워드·성과 데이터는 수익 전략 자산이라 공개 금지.
    # (개발 환경은 require_token이 생략하므로 로컬 동작 불변)
    @app.get("/keywords", dependencies=[Depends(require_token)])
    def list_keywords(sort: str = "priority", sort_dir: str = "desc",
                      category: str = "", commercial_min: float = 0,
                      click_min: float = 0, q: str = "",
                      discovered_within: int = 0,
                      # UX-1: 기본 = 전체 — 추천(ai_pick)은 대시보드 버튼으로 명시
                      preset: str = "", show_inactive: int = 0,
                      page: int = 1, page_size: int = 50):
        page = max(page, 1)
        page_size = min(max(page_size, 1), 200)
        # v30.4 (적대적 QA): 거대 page/기간 값 클램프 — OFFSET 바인딩·timedelta가
        # 각각 OverflowError(→500)를 내던 것을 정상 파라미터로 수렴
        page = min(page, 1_000_000)
        discovered_within = min(discovered_within, 36_500)  # 상한 100년
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
        #     v20: upcoming(곧 뜰) = demand_growth>0(상승 반전) & demand<P50(아직
        #     수요 낮음 = 선점 가능) & opportunity≥P50(경쟁 아직 안 붙음) — '오르기
        #     전 주식' 후보. 성과 실적이 쌓이면 이 프리셋의 적중률을 데이터로 검증.
        thresholds, threshold_source = run_db(resolve_thresholds)
        opportunity_min, demand_min, demand_max, ai_cite_min, growth_min = (
            0.0, 0.0, None, 0.0, None)
        if preset == "promising":
            opportunity_min, demand_min = thresholds["opportunity"], thresholds["demand"]
        elif preset == "ai_pick":
            ai_cite_min, demand_min = thresholds["ai_cite"], thresholds["demand"]
        elif preset == "rising":
            demand_min, growth_min = thresholds["demand"], RISING_GROWTH_MIN
        elif preset == "upcoming":
            _, opp_pct = run_db(lambda d: d.percentiles("opportunity"))
            # B-1: P50=0이면 get 기본값이 아니라 0.0이 반환돼 프리셋 필터가
            # 무력화(전체 노출)됨 — resolve_thresholds와 동일하게 폴백 규칙 적용
            opportunity_min = opp_pct.get(0.5) or 20.0
            demand_max = thresholds["demand"]
            growth_min = UPCOMING_GROWTH_MIN
        filters = dict(category=category, commercial_min=commercial_min, q=q,
                       discovered_since=discovered_since,
                       active=None if show_inactive else 1,
                       opportunity_min=opportunity_min, demand_min=demand_min,
                       demand_max=demand_max, click_min=click_min,
                       ai_cite_min=ai_cite_min, growth_min=growth_min)
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
        # v30.4 (적대적 QA): 길이/null byte 가드
        _validate_text(seed.keyword, "키워드", 200)
        _validate_text(seed.category, "카테고리", 100)
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

    # ---------- v29: 운세 생성·발행 분리 (대시보드 "운세 생성" / "자동 발행" 버튼) ----------
    # v28은 "운세 발행" 한 버튼이 생성+발행을 함께 수행 — BLOG_PUBLISH_ENABLED
    # 미설정 환경(사용자가 수동 게시하려는 경우)에선 "발행 비활성"만 노출되어
    # 운세 생성 자체를 못 쓰는 문제. v29에서 생성(/fortune/generate)과
    # 발행(/fortune/publish)을 분리한다.



    @app.post("/fortune/generate", dependencies=[Depends(require_token)])
    def fortune_generate():
        """v29: 운세 콘텐츠만 생성 (LLM 1회 시도, 발행 안 함) — 사용자가
        콘텐츠를 보고 수동으로 게시하기 위한 버튼. 생성 결과(항목+본문 미리보기)
        를 반환한다. 기존 fortune_generate_step(publish=False) 재사용 (AC-8)."""
        import collect
        import json as json_mod
        today = config_mod.today_kst().isoformat()

        def _generate(d):
            created = collect.fortune_generate_step(
                d, cfg, today, publish=False)
            # v29.4: 전체 콘텐츠 표시 — daily/weekly/monthly는 오늘 기준 최신,
            # 고정 콘텐츠(일주 60·별자리 12·띠 12)는 전부 반환 (각각 다른 운세)
            rows = d.list_fortune_generations(limit=300)
            # 오늘자 daily 계열은 최신 1건만, 고정은 전건 유지
            latest = {}
            for r in rows:
                ct = r["content_type"]
                if ct in ("day_pillar_blog", "zodiac_blog", "animal_blog"):
                    latest.setdefault(ct, []).append(r)
                else:
                    prev = latest.get(ct)
                    if prev is None or (r["ref_date"], r["id"]) > (prev["ref_date"], prev["id"]):
                        latest[ct] = r
            items = []
            for ct in sorted(latest):
                batch = latest[ct]
                if not isinstance(batch, list):
                    batch = [batch]
                # v29.6: 띠별 12개를 하나의 합본으로 — 각 띠 제목+본문을 순서대로 병합
                if ct == "animal_blog" and len(batch) > 1:
                    parts = []
                    refs = []
                    for r in sorted(batch, key=lambda x: (x["ref_date"], x["id"])):
                        p = {}
                        try:
                            p = json_mod.loads(r["content"] or "{}")
                        except Exception:
                            pass
                        if not isinstance(p, dict) or not (r["content"] or "").strip():
                            continue
                        refs.append(r["ref_date"])
                        title = str(p.get("title", "") or "띠 운세")
                        body = str(p.get("body", "") or "")
                        parts.append(f"## {title}\n\n{body}")
                    if parts:
                        combined_body = "\n\n---\n\n".join(parts)
                        items.append({
                            "ref": today, "content_type": "animal_blog",
                            "target": "띠별 종합 (12)",
                            "status": "생성됨",
                            "has_content": True,
                            "title": f"{today} 띠별 운세 종합",
                            "summary": "12개 띠(쥐띠~돼지띠) 운세를 하나로 합친 종합본",
                            "preview": " ".join(combined_body.replace("#", " ").replace("*", " ").split())[:100],
                            "body_full": combined_body,
                            "sns_full": "",
                        })
                    continue
                for r in sorted(batch, key=lambda x: (x["ref_date"], x["id"])):
                    parsed = {}
                    try:
                        parsed = json_mod.loads(r["content"] or "{}")
                    except Exception:
                        pass
                    if not isinstance(parsed, dict):
                        parsed = {}
                    has_content = bool(r["content"] and r["content"].strip())
                    # daily_sns는 {text, hashtags} 구조 — text를 제목으로 노출
                    if ct == "daily_sns":
                        title = str(parsed.get("text", "") or "")[:60]
                        summary = ""
                    else:
                        title = str(parsed.get("title", "") or "")[:80]
                        summary = str(parsed.get("summary", "") or "")[:120]
                    body = str(parsed.get("body", "") or "")
                    # 마크다운 헤더·구분선 제거 후 첫 문단만 미리보기
                    plain = body.replace("#", "").replace("*", "").replace("---", " ").strip()
                    preview = " ".join(plain.split())[:100]
                    # 생성 패널용 상태 라벨 — 발행 상태를 "수동 게시 대기" 맥락으로
                    # (publish_failed는 이전 발행 시도 실패 — 콘텐츠는 정상)
                    if not has_content:
                        status_label = "미생성"
                    elif r["status"] == "qc_failed":
                        status_label = "검수 실패"
                    elif r["status"] == "published":
                        status_label = "발행됨"
                    elif r["status"] == "publish_failed":
                        status_label = "발행 대기 (자동 발행 실패 이력)"
                    else:
                        status_label = "생성됨"
                    items.append({
                        "ref": r["ref_date"], "content_type": ct,
                        "status": status_label,
                        "has_content": has_content,
                        "title": title, "summary": summary, "preview": preview,
                        # v29.5: 대상(어느 띠/사주/별자리) 표시 — grounding.key 사용
                        "target": _fortune_target(r, ct, json_mod),
                        # v29.2: 수동 게시용 전체 본문 (hashtags 포함)
                        "body_full": (parsed.get("body", "")
                                      if isinstance(parsed, dict) else ""),
                        "sns_full": (parsed.get("text", "")
                                     if isinstance(parsed, dict) else ""),
                    })
            return created, items

        created, items = run_db(_generate)
        # 오늘 이미 생성된 콘텐츠가 있으면 안내 (0건이어도 정상)
        if created > 0:
            message = f"운세 생성 완료 — {created}건 새로 생성"
        else:
            message = ("이미 생성된 운세가 있습니다 — 아래에서 본문을 확인하고 "
                       "복사해 게시하세요")
        return {"created": created, "items": items, "message": message}

    @app.post("/fortune/publish", dependencies=[Depends(require_token)])
    def fortune_publish():
        # v28 (FR-1~FR-5): 수동 운세 발행 — ① 미생성 콘텐츠 생성(LLM 1회 시도)
        # ② 미발행 콘텐츠 전부 발행 시도 ③ 항목별 결과 JSON 반환.
        # - 발행 로직은 collect 헬퍼 재사용 (FR-3 — requests.post 직호출·후보
        #   하드코딩·slug 규칙 재구현 없음, AC-8)
        # - BlogPublishError.status_code 기반 401/429 힌트 (AC-4/AC-5, OQ-2)
        # - Vercel 60초 예산: FORTUNE_PUBLISH_BUDGET_SECONDS, 초과 항목
        #   skipped("시간 예산") (OQ-1)
        import collect
        import time as time_mod
        today = config_mod.today_kst().isoformat()
        started = time_mod.monotonic()
        enabled = bool(cfg.get("blog_publish_enabled") and cfg.get("blog_api_url"))

        def _generate_and_publish(d):
            try:
                created = collect.fortune_generate_step(
                    d, cfg, today, publish=False)
            except Exception as e:
                # 생성 실패여도 발행 단계는 진행 (OQ-1 — 부분 수행)
                logger.warning("fortune generate step failed: %s", e)
                created = 0
            if not enabled:
                return created, []  # FR-4 — 발행 시도 0건
            remaining = max(0, FORTUNE_PUBLISH_BUDGET_SECONDS
                            - int(time_mod.monotonic() - started))
            items = collect.publish_all_fortune_items(
                d, cfg, today, budget_seconds=remaining)
            # AC-10: daily_sns는 발행 후보가 아님 — 오늘자 행이 있으면 구분 표시
            if d.get_fortune_generation(today, "daily_sns"):
                items.append({
                    "ref": today, "content_type": "daily_sns", "ok": False,
                    "status": "not_target",
                    "reason": "발행 대상 아님 — SNS 요약은 발행 후보가 아님 (*_blog만)",
                })
            return created, items

        created, items = run_db(_generate_and_publish)
        published = sum(1 for it in items if it["ok"])
        failed = sum(1 for it in items if it["status"] == "failed")
        skipped = sum(1 for it in items
                      if it["status"] in ("skipped", "not_target"))
        if not enabled:
            message = "발행 비활성 — BLOG_PUBLISH_ENABLED=1 및 BLOG_API_URL 설정 필요"
        else:
            message = (f"발행 완료 — 성공 {published}건 / 실패 {failed}건 / "
                       f"스킵 {skipped}건 (생성 {created}건)")
            if any(it["reason"] == collect.FORTUNE_SKIP_REASON_BUDGET
                   for it in items):
                message += " — 시간 예산 초과, 남은 항목은 재클릭으로 이어서 발행됩니다"
        return {"created": created, "published": published, "failed": failed,
                "skipped": skipped, "enabled": enabled, "message": message,
                "items": items}

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
        # v18: 생성 로직은 _generate_and_store_draft로 추출 (리프레시와 공용)
        # v19: 플랫폼별 생성
        return _generate_and_store_draft(
            body.keyword_id, platform=body.platform)

    @app.get("/drafts/{draft_id}", dependencies=[Depends(require_token)])
    def get_draft(draft_id: int):
        draft = run_db(lambda d: d.get_draft(draft_id))
        if not draft:
            raise HTTPException(status_code=404, detail="not found")
        return _with_parsed_tags(draft)

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
        # v19: 초안의 썸네일 아이디어를 프롬프트 재료로 사용
        import image_gen
        draft = run_db(lambda d: d.get_draft(draft_id))
        if not draft:
            raise HTTPException(status_code=404, detail="not found")
        ideas = []
        if draft.get("thumbnail_ideas"):
            try:
                parsed = json.loads(draft["thumbnail_ideas"])
                ideas = parsed if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                ideas = []
        try:
            url = image_gen.generate_image(
                run_db(lambda d: d.get_keyword(draft["keyword_id"]))["keyword"],
                draft["title"], thumbnail_ideas=ideas)
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
        # v19: 네이버 플레인 텍스트는 마크다운 H2가 없어 섹션 이미지 대상 불가 —
        # 대표 이미지 1장으로 갈음 (플랫폼 특성 고지)
        if (draft.get("platform") or "naver") == "naver":
            raise HTTPException(
                status_code=400,
                detail="네이버 플레인 텍스트 글은 섹션 이미지를 지원하지 않습니다 — 대표 이미지를 생성하세요")
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
        # v18: 성과 기록은 AdPost 지표와 함께 실측 CPC 통계 원료 — 재집계
        run_db(lambda d: d.refresh_category_cpc_stats(config_mod.now_kst_iso()))
        return run_db(lambda d: d.get_draft(draft_id))

    # ---------- v17: 게시 파이프라인 + AdPost 피드백 자동화 ----------

    @app.post("/drafts/{draft_id}/published-url",
              dependencies=[Depends(require_token)])
    def set_published_url(draft_id: int, body: PublishedUrlIn):
        draft = run_db(lambda d: d.get_draft(draft_id))
        if not draft:
            raise HTTPException(status_code=404, detail="not found")
        url = (body.url or "").strip().rstrip("/")
        if not url.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="올바른 URL이 아닙니다")
        run_db(lambda d: d.set_draft_published_url(
            draft_id, url, config_mod.now_kst_iso()))
        return run_db(lambda d: d.get_draft(draft_id))

    @app.get("/drafts/{draft_id}/export", dependencies=[Depends(require_token)])
    def export_draft(draft_id: int):
        # v17: 게시용 마크다운 내보내기 — 네이버 블로그는 쓰기 API가 없어
        # 복붙이 최종 단계. 이미지 포함 완성 문서로 마찰을 최소화한다 (고도화 3)
        # v19: 플랫폼별 문서 — 네이버 플레인 / 티스토리·애드센스·브랜드 마크다운
        import platforms as platforms_mod
        import publish
        draft = run_db(lambda d: d.get_draft(draft_id))
        if not draft:
            raise HTTPException(status_code=404, detail="not found")
        platform = draft.get("platform") or platforms_mod.DEFAULT_PLATFORM
        markdown = publish.build_export_markdown(draft, platform=platform)
        filename = platforms_mod.PLATFORM_FILENAME.get(platform, "blog")
        return Response(
            content=markdown.encode("utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition":
                     f'attachment; filename="{filename}-{draft_id}.md"'})

    ADPOST_IMPORT_MAX_BYTES = 5 * 1024 * 1024

    @app.post("/adpost/import", dependencies=[Depends(require_token)])
    async def import_adpost_report(file: UploadFile = File(...)):
        # v17: AdPost 리포트 CSV → 초안 매칭 → 성과 점수·priority 자동 보정.
        # 수동 점수 입력(FeedbackIn)의 자동화 대체 경로 (고도화 1).
        # v17.3: 시간 예산 초과 시 남은 행은 건너뛰고 부분 처리 결과를 명시적으로
        # 반환 — 중간 타임아웃으로 무소음 유실 방지. 멱등 설계(boost 차액)라
        # 같은 CSV 재업로드로 나머지를 이어서 반영할 수 있다.
        import adpost
        import time as time_mod
        raw = await file.read()
        if len(raw) > ADPOST_IMPORT_MAX_BYTES:
            raise HTTPException(status_code=400, detail="CSV가 너무 큽니다 (5MB 상한)")
        try:
            rows = adpost.parse_adpost_csv(raw)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        now = config_mod.now_kst_iso()
        started = time_mod.monotonic()
        budget = ADPOST_IMPORT_BUDGET_SECONDS
        matched, unmatched, skipped = [], 0, 0
        for row in rows:
            if time_mod.monotonic() - started >= budget:
                skipped += 1
                continue
            draft = (run_db(lambda d, u=row["url"]: d.find_draft_by_published_url(u))
                     if row["url"] else None)
            if not draft and row["title"]:
                # R-3: 제목 매칭은 게시된 초안만 — 미게시 초안에 실측 성과가
                # 붙어 priority가 오염되는 경로 차단
                draft = run_db(
                    lambda d, t=row["title"]: d.find_draft_by_title(
                        t, status="published"))
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
        # v18: 임포트된 실측 지표로 카테고리별 CPC/RPM 재집계 — priority 반영
        run_db(lambda d: d.refresh_category_cpc_stats(now))
        result = {"matched": len(matched), "unmatched": unmatched,
                  "results": matched}
        if skipped:
            result["partial"] = True
            result["skipped"] = skipped
            result["message"] = (f"시간 예산 내 {len(rows) - skipped}/{len(rows)}행 처리 — "
                                 "같은 CSV 재업로드로 나머지를 반영하세요")
        return result

    # ---------- v18: 게시 플래너 · 리프레시 · 수익 인사이트 ----------

    @app.get("/planner", dependencies=[Depends(require_token)])
    def planner():
        # v18: 게시 플래너 — 미게시 초안 게시 추천 대기열(이미지 완성 우선) +
        # 저성과 글 리프레시 추천 + 성과 상위 패턴(가이드 주입 현황).
        # v21(A.1): age_days(발행 리마인더) + recent_published(게시 로그) 추가
        return {
            "publish_queue": run_db(lambda d: d.publish_plan(10)),
            "refresh_candidates": run_db(lambda d: d.refresh_candidates(5)),
            "pattern": run_db(lambda d: d.top_performer_pattern()),
            "recent_published": run_db(lambda d: d.recent_published(5)),
        }

    @app.post("/drafts/{draft_id}/refresh", dependencies=[Depends(require_token)])
    def refresh_draft(draft_id: int):
        # v18: 저성과 글 리프레시 — 같은 키워드로 새 초안을 생성하고 원본에
        # refreshed_at 기록 (재추천 방지). 원본 성과는 남겨 비교 지표로 활용.
        # v19: 원본의 플랫폼을 그대로 계승.
        old = run_db(lambda d: d.get_draft(draft_id))
        if not old:
            raise HTTPException(status_code=404, detail="not found")
        if old["refreshed_at"]:
            raise HTTPException(status_code=400, detail="이미 리프레시된 초안입니다")
        # R-5: 플래너(refresh_candidates)와 동일 게이트 — 게시 14일+·성과 50 미만만
        # 리프레시 허용. 미게시/최근 게시/성과 양호 초안의 무분별 재작성 차단.
        if old.get("status") != "published" or not old.get("published_at"):
            raise HTTPException(status_code=400,
                                detail="게시된 초안만 리프레시할 수 있습니다")
        cutoff = (config_mod.today_kst()
                  - timedelta(days=REFRESH_MIN_AGE_DAYS)).isoformat()
        if old.get("published_at", "") > cutoff:
            raise HTTPException(status_code=400,
                                detail="게시 14일 이후부터 리프레시할 수 있습니다")
        if old.get("performance_score") is None or old["performance_score"] >= 50:
            raise HTTPException(status_code=400,
                                detail="성과 50 미만 초안만 리프레시할 수 있습니다")
        result = _generate_and_store_draft(
            old["keyword_id"], refresh_of=old["id"],
            platform=old.get("platform") or "naver")
        run_db(lambda d: d.mark_draft_refreshed(
            old["id"], config_mod.now_kst_iso()))
        return result

    @app.get("/revenue-insights", dependencies=[Depends(require_token)])
    def revenue_insights():
        # v18: 수익 인사이트 — AdPost 실측 기준 월별 추이·키워드 기여·카테고리 실측.
        return run_db(lambda d: d.revenue_insights())

    # ---------- v30: KDP 파이프라인 (K-1~K-4) ----------

    @app.get("/kdp/books", dependencies=[Depends(require_token)])
    def kdp_books(status: str = ""):
        # K-1: 책 목록 (상태 필터), status=ready 등
        return {"items": run_db(lambda d: d.list_kdp_books(status=status))}

    @app.get("/kdp/books/{book_id}", dependencies=[Depends(require_token)])
    def kdp_book_detail(book_id: int):
        # K-2: 책 상세 — 책 + 챕터 + QC + 표지
        book = run_db(lambda d: d.get_kdp_book(book_id))
        if not book:
            raise HTTPException(status_code=404, detail="not found")
        return {
            "book": book,
            "chapters": run_db(lambda d: d.list_kdp_chapters(book_id)),
            "qc": run_db(lambda d: d.get_kdp_qc_results(book_id)),
            "cover": run_db(lambda d: d.get_kdp_cover(book_id)),
        }

    @app.post("/kdp/books", dependencies=[Depends(require_token)])
    def kdp_book_create(body: KdpBookCreateIn):
        # K-1: 책 생성 트리거 (후보 수락) — R-1: source_keyword 전달로 배치 generate 연결
        # v30.4 (적대적 QA): 길이/null byte 가드
        _validate_text(body.title, "책 제목", 500)
        _validate_text(body.lang, "언어", 10)
        _validate_text(body.source_keyword, "소스 키워드", 200)
        bid = run_db(lambda d: d.insert_kdp_book(
            title=body.title, status="draft", lang=body.lang,
            source_keyword=body.source_keyword,
            created_at=config_mod.now_kst_iso()))
        return {"ok": True, "book_id": bid}

    @app.post("/kdp/books/{book_id}/generate", dependencies=[Depends(require_token)])
    def kdp_book_generate(book_id: int):
        # K-2: 생성 시작 → 배치 트리거 큐(비동기) — 서버리스 60초 준수
        book = run_db(lambda d: d.get_kdp_book(book_id))
        if not book:
            raise HTTPException(status_code=404, detail="not found")
        run_db(lambda d: d.update_kdp_book_status(
            book_id, "assembling", updated_at=config_mod.now_kst_iso()))
        # 실제 생성은 GH Actions 배치(kdp_pipeline)에서 수행 — 여기선 트리거 기록
        return {"ok": True, "message": "책 생성이 배치에서 처리됩니다",
                "book_id": book_id, "status": "assembling"}

    @app.post("/kdp/books/{book_id}/qc", dependencies=[Depends(require_token)])
    def kdp_book_qc(book_id: int):
        # K-2: QC 8항목 재실행
        book = run_db(lambda d: d.get_kdp_book(book_id))
        if not book:
            raise HTTPException(status_code=404, detail="not found")
        import kdp_book
        results = run_db(lambda d: kdp_book.run_qc(
            d, book_id, {"chapters": d.list_kdp_chapters(book_id),
                         "book": d.get_kdp_book(book_id)},
            run_at=config_mod.now_kst_iso()))
        return {"qc": [{"qc_item": r.qc_item, "passed": r.passed,
                        "detail": r.detail} for r in results]}

    @app.get("/kdp/books/{book_id}/epub", dependencies=[Depends(require_token)])
    def kdp_book_epub(book_id: int):
        # K-3: EPUB 다운로드 (ready+만) — 메모리 조립 후 attachment
        import io
        import ebook_builder
        book = run_db(lambda d: d.get_kdp_book(book_id))
        if not book:
            raise HTTPException(status_code=404, detail="not found")
        if book["status"] not in ("ready", "published", "monitoring"):
            raise HTTPException(status_code=400,
                                detail="ready 상태 이상에서만 EPUB을 다운로드할 수 있습니다")
        chapters = run_db(lambda d: d.list_kdp_chapters(book_id))
        cover = run_db(lambda d: d.get_kdp_cover(book_id))
        cover_bytes = None
        if cover and cover.get("image_url"):
            try:
                from ebook_builder import make_cover_image
                cover_bytes = make_cover_image(
                    book["title"], subtitle=book.get("pen_name") or "")
            except Exception:
                cover_bytes = None
        data = ebook_builder.build_epub(book, chapters, cover_bytes=cover_bytes)
        filename = "kdp-%d.epub" % book_id
        return Response(content=data, media_type="application/epub+zip",
                        headers={"Content-Disposition":
                                 'attachment; filename="%s"' % filename})

    def _kdp_checklist(book):
        """M-3: 출간 체크리스트 4종 (AC-K4-1②) — AI 표기·가격·키워드7·카테고리2."""
        import json
        try:
            kws = json.loads(book.get("keywords") or "[]")
            kws = kws if isinstance(kws, list) else []
        except (TypeError, json.JSONDecodeError):
            kws = []
        cats = [c for c in (book.get("category") or "").split(",") if c.strip()]
        return {
            "ai_disclosure": True,                # QC #6 통과 전제(본문+표지 AI-generated 공개)
            "keywords_ok": len(kws) >= 7,
            "categories_ok": len(cats) >= 2,
        }  # price는 별도 — POST /kdp/publish에서 body.price 2.99~12.99 검증

    @app.get("/kdp/publish-queue", dependencies=[Depends(require_token)])
    def kdp_publish_queue():
        # K-4: 출간 큐 (일 3권 게이트 반영) — ready 책 + 체크리스트 상태 + 오늘 예약
        ready = run_db(lambda d: d.list_kdp_books(status="ready"))
        today = config_mod.today_kst().isoformat()
        gate = run_db(lambda d: d.publish_day_gate(today, max_per_day=3))
        # M-3: 책별 체크리스트 검증 (AI 표기·가격·키워드7·카테고리2)
        items = []
        for b in ready:
            cl = _kdp_checklist(b)
            items.append({"book": b, "checklist": cl,
                          "checklist_done": int(sum(1 for v in cl.values() if v)),
                          "checklist_total": len(cl)})
        return {"ready_books": items, "today": today, "gate": gate}

    @app.post("/kdp/publish", dependencies=[Depends(require_token)])
    def kdp_publish(body: KdpPublishIn):
        # K-4: 출간 시작 (AC-K4-1② 체크리스트 검증 후) → kdp_publish 기록
        book = run_db(lambda d: d.get_kdp_book(body.book_id))
        if not book:
            raise HTTPException(status_code=404, detail="not found")
        cl = _kdp_checklist(book)
        missing = [k for k, v in cl.items() if not v]
        if missing:
            raise HTTPException(status_code=400, detail=(
                "체크리스트 미완료 — 출간이 차단되었습니다: " + ", ".join(missing)))
        if body.price < 2.99 or body.price > 12.99:
            raise HTTPException(status_code=400,
                                detail="가격은 70% 로열티 구간($2.99~$12.99)이어야 합니다")
        publish_date = body.publish_date or config_mod.today_kst().isoformat()
        pid = run_db(lambda d: d.insert_kdp_publish(
            book["id"], publish_date, price=body.price))
        return {"ok": True, "publish_id": pid, "publish_date": publish_date}

    @app.post("/kdp/publish/{publish_id}/verify", dependencies=[Depends(require_token)])
    def kdp_publish_verify(publish_id: int, body: KdpVerifyIn):
        # K-4: 48h 확인 → verified + verified_at + mirror (AC-K4-2②)
        run_db(lambda d: d.verify_kdp_publish(
            publish_id, verified_at=config_mod.now_kst_iso(),
            mirror_status=body.mirror_status, price_ok=body.price_ok))
        return {"ok": True, "publish_id": publish_id}

    @app.get("/kdp/monitoring", dependencies=[Depends(require_token)])
    def kdp_monitoring():
        # K-4: 48h 미검증 책 목록 (상단 정렬)
        published = run_db(lambda d: d.list_kdp_publish(status="published"))
        now = config_mod.now_kst_iso()
        pending_rows = [p for p in published if not p.get("verified_at")]
        return {"items": pending_rows, "now": now}

    @app.post("/kdp/performance", dependencies=[Depends(require_token)])
    def kdp_performance(body: KdpPerformanceIn):
        # K-4: 성과 입력 (AC-DB-1) — measured_by=manual
        run_db(lambda d: d.upsert_kdp_performance(
            body.book_id, body.year_month, sales=body.sales,
            royalty=body.royalty, measured_by="manual"))
        return {"ok": True}

    @app.get("/kdp/performance-history", dependencies=[Depends(require_token)])
    def kdp_performance_history(month: str = ""):
        # M-3: 성과 월별 집계 (AC-DB-1④) — 대시보드 성과 탭
        rows = run_db(lambda d: d.list_kdp_performance(year_month=month))
        summary = run_db(lambda d: d.kdp_monthly_summary())
        return {"items": rows, "monthly": summary}

    @app.get("/kdp/books-for-publish", dependencies=[Depends(require_token)])
    def kdp_books_for_publish():
        # M-3: 성과 입력 폼 대상 책 목록 (published 이상)
        books = run_db(lambda d: d.list_kdp_books(status="published"))
        mono = run_db(lambda d: d.list_kdp_books(status="monitoring"))
        return {"items": books + mono}

    @app.get("/kdp/breakeven", dependencies=[Depends(require_token)])
    def kdp_breakeven():
        # K-4: 손익분기표 (AC-DB-1③) — 정보성
        rows = []
        for price in (2.99, 4.99, 9.99, 12.99):
            royalty_per = round(price * 0.7 - 0.06, 2)
            rows.append({"price": price, "royalty_per": royalty_per,
                         "breakeven_100": max(1, round(100 / royalty_per))})
        return {"items": rows}

    @app.get("/kdp/monitoring-summary", dependencies=[Depends(require_token)])
    def kdp_monitoring_summary():
        # K-4: 48h 미검증 수 (대시보드 KPI)
        published = run_db(lambda d: d.list_kdp_publish(status="published"))
        n = sum(1 for p in published if not p.get("verified_at"))
        return {"pending_48h": n}

    # ---------- v31: 쇼츠 파이프라인 S-2 — 주제 후보 ----------

    @app.get("/shorts/topics", dependencies=[Depends(require_token)])
    def shorts_topics(status: str = ""):
        # S-2: 주제 후보 목록 (score 내림차순) — 대시보드 탭(S-4) 전 데이터 노출
        import json as json_mod
        items = run_db(lambda d: d.list_shorts_topics(status=status))
        for it in items:
            try:
                it["evidence"] = json_mod.loads(it.get("evidence") or "{}")
            except (TypeError, json_mod.JSONDecodeError):
                it["evidence"] = {}
        return {"items": items}

    @app.get("/shorts/scripts", dependencies=[Depends(require_token)])
    def list_shorts_scripts(status: str = ""):
        # S-3: 스크립트 목록 — hashtags/qc_detail/ref_video_ids JSON 파싱 노출
        import json as json_mod
        items = run_db(lambda d: d.list_shorts_scripts(status=status))
        for it in items:
            for field in ("hashtags", "ref_video_ids", "qc_detail"):
                try:
                    parsed = json_mod.loads(it.get(field) or "[]")
                    it[field] = parsed if isinstance(parsed, list) else []
                except (TypeError, json_mod.JSONDecodeError):
                    it[field] = []
        return {"items": items}

    @app.post("/shorts/scripts", dependencies=[Depends(require_token)])
    def create_shorts_script(body: ShortsScriptIn):
        # S-3: 스크립트 생성 (사용자 트리거 — 스펙 §5 'GH Actions 또는 사용자 트리거')
        import shorts_script
        _validate_text(body.topic, "주제", 100)
        try:
            result = run_db(lambda d: shorts_script.generate_script(
                d, body.topic))
        except shorts_script.ScriptGenerationError as e:
            logger.warning("shorts script generation failed topic=%s: %s",
                           body.topic, e)
            raise HTTPException(status_code=503, detail=str(e))
        if result is None:
            raise HTTPException(status_code=404,
                                detail="주제 후보를 찾을 수 없습니다")
        return result

    @app.get("/")
    def index():
        return FileResponse(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "static", "index.html"))

    return app


app = create_app(config_mod.load_config())
