# shorts_research.py — v30.3: 쇼츠 파이프라인 S-1 유튜브 수집
# YouTube Data API v3 기반 매일 1회 수집 (AC-S1-1~4).
# - 인기 동영상(KR) 50개 + 채널 20 + 검색 10 + 댓글 20 ≈ 100 units/일 (쿼터 예산)
# - 멱등 UPSERT(video_id UNIQUE), 지수 백오프 재시도, 4xx 스킵
# - 쿼터 사용량 로그 (youtube_quota_log), 예산 초과 시 중단
#
# 인증: Google 서비스 계정 키 (YOUTUBE_SERVICE_ACCOUNT_KEY — .env.local)
#   - 읽기 API(channels/search/videos/commentThreads) 전용으로 충분
#   - 공개 데이터(인기 급상승·검색)는 서비스 계정으로 조회 가능 (검증 완료)
import json
import logging
import os
import random
import time
from datetime import datetime, timedelta

import config as config_mod

logger = logging.getLogger("shorts_research")

# ---- 쿼터 예산 (AC-S1-4: ≤100 units/일 = 10,000 대비 1%) ----
QUOTA_BUDGET_DAILY = 100
SEARCH_BUCKET_DAILY = 100      # search.list 별도 버킷 (1회 = 1 unit)
MAX_RETRIES = 3                # 지수 백오프 재시도 횟수
RETRY_BACKOFF_BASE = 2.0       # 2^n 초 지수 백오프
RETRY_BACKOFF_JITTER = 0.5     # 지터 (±50%)
MAX_RESULTS_POPULAR = 50       # 인기 동영상 상위 50 (S-1)
MAX_RESULTS_SEARCH = 10        # 검색 10회
MAX_RESULTS_COMMENTS = 20      # 댓글 20 (채널 비소유 시에도 가능)

# 엔드포인트별 쿼터 단위 (공식: videos.list=1, channels.list=1, search.list=1, commentThreads.list=1)
QUOTA_UNITS = {
    "videos.list": 1,
    "channels.list": 1,
    "search.list": 1,
    "commentThreads.list": 1,
}


class QuotaExceededError(Exception):
    """일일 쿼터 예산 초과 — 수집 중단 (AC-S1-4②)."""


class YouTubeAPIError(Exception):
    """YouTube API 호출 실패 — 재시도 후에도 지속 시 전파."""


def _build_client(key_path=None):
    """Google 서비스 계정 인증 클라이언트.
    key_path 미지정 시 .env.local의 YOUTUBE_SERVICE_ACCOUNT_KEY 사용."""
    if key_path is None:
        key_path = os.getenv("YOUTUBE_SERVICE_ACCOUNT_KEY", "")
    if not key_path:
        raise YouTubeAPIError(
            "YOUTUBE_SERVICE_ACCOUNT_KEY 미설정 — .env.local에 서비스 계정 키 경로 필요")
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    creds = service_account.Credentials.from_service_account_file(
        key_path, scopes=["https://www.googleapis.com/auth/youtube.readonly"])
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def _parse_video_item(item, region="KR", fetched_at=""):
    """YouTube videos.list/search.list 응답 항목 → youtube_raw 레코드 dict.
    statistics 값은 문자열 — int 변환, 없으면 0. tags는 JSON 문자열 저장."""
    sn = item.get("snippet", {})
    st = item.get("statistics", {})
    tags = sn.get("tags") or []

    def _int(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0

    return {
        "video_id": item.get("id") if isinstance(item.get("id"), str)
                    else item.get("id", {}).get("videoId", ""),
        "title": sn.get("title", ""),
        "tags": json.dumps(tags, ensure_ascii=False),
        "description": sn.get("description", ""),
        "channel_id": sn.get("channelId", ""),
        "channel_title": sn.get("channelTitle", ""),
        "published_at": sn.get("publishedAt", ""),
        "view_count": _int(st.get("viewCount")),
        "like_count": _int(st.get("likeCount")),
        "comment_count": _int(st.get("commentCount")),
        "share_count": _int(st.get("shareCount")) if st.get("shareCount") else None,
        "region": region,
        "fetched_at": fetched_at,
    }


def _call_with_retry(fn, endpoint, log_quota=None, run_at=""):
    """API 호출 + 지수 백오프 재시도 (AC-S1-1 edge: 403/429).
    - 4xx(403/404): 재시도 금지 (비용 낭비 방지, AC-S1-4 edge)
    - 429/5xx: 지수 백오프 재시도
    - 성공/실패 모두 쿼터 1 unit 기록 (실패 요청도 최소 1 unit — 공식)"""
    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = fn()
            if log_quota is not None:
                log_quota(run_at, endpoint, QUOTA_UNITS.get(endpoint, 1), "ok")
            return resp
        except Exception as e:  # noqa: BLE001 — 구글 클라이언트 예외는 광범위
            last_exc = e
            status = getattr(e, "resp", None)
            code = status.status if status is not None else None
            # 4xx — 재시도 금지 (403 = 접근 거부/키 문제, 404 = 없음)
            if code is not None and 400 <= code < 500 and code != 429:
                if log_quota is not None:
                    log_quota(run_at, endpoint, QUOTA_UNITS.get(endpoint, 1),
                              f"error_{code}", str(e)[:200])
                raise YouTubeAPIError(f"{endpoint} 4xx({code}): {e}") from e
            # 429/5xx/네트워크 — 지수 백오프
            if attempt < MAX_RETRIES - 1:
                sleep_s = RETRY_BACKOFF_BASE ** attempt * (
                    1 + random.uniform(-RETRY_BACKOFF_JITTER, RETRY_BACKOFF_JITTER))
                logger.warning("%s retry %d/%d in %.1fs: %s",
                               endpoint, attempt + 1, MAX_RETRIES, sleep_s, e)
                time.sleep(sleep_s)
    if log_quota is not None:
        log_quota(run_at, endpoint, QUOTA_UNITS.get(endpoint, 1),
                  "error", str(last_exc)[:200])
    raise YouTubeAPIError(f"{endpoint} failed after retries: {last_exc}") from last_exc


def quota_remaining(used, budget=QUOTA_BUDGET_DAILY):
    return max(0, budget - used)


def quota_exceeded(used, budget=QUOTA_BUDGET_DAILY):
    return used >= budget


def fetch_popular_videos(d, client=None, region="KR", max_results=MAX_RESULTS_POPULAR,
                         fetched_at="", log_quota=None):
    """① 인기 동영상(KR) 50개 수집 (AC-S1-1①) → youtube_raw 멱등 저장.
    client 미지정 시 _build_client()로 생성. 반환: {fetched, quota_units, errors}"""
    if fetched_at == "":
        fetched_at = config_mod.now_kst_iso()
    client = client or _build_client()

    def log(run_at, endpoint, units, status, note=""):
        if log_quota is not None:
            log_quota(run_at, endpoint, units, status, note)
        elif hasattr(d, "log_youtube_quota"):
            d.log_youtube_quota(run_at, endpoint, units, status, note)

    errors = []
    try:
        resp = _call_with_retry(
            lambda: client.videos().list(
                part="snippet,statistics", chart="mostPopular",
                regionCode=region, maxResults=max_results).execute(),
            "videos.list", log_quota=log, run_at=fetched_at)
    except YouTubeAPIError as e:
        logger.warning("popular videos fetch failed: %s", e)
        return {"fetched": 0, "quota_units": 1, "errors": [str(e)]}

    items = resp.get("items", [])
    for item in items:
        rec = _parse_video_item(item, region=region, fetched_at=fetched_at)
        try:
            d.upsert_youtube_video(rec)
        except Exception as e:  # noqa: BLE001 — 단건 실패는 격리
            errors.append(f"{rec['video_id']}: {e}")
    return {"fetched": len(items), "quota_units": 1, "errors": errors}


def run_collection(d, cfg, client=None, region="KR", fetched_at="", log_quota=None):
    """S-1 배치 진입점 — 인기 동영상 수집 + 쿼터 로그.
    반환: {fetched, quota_used, errors, quota_logged}
    AC-S1-4: 예산(100 units) 내에서만 실행, 초과 시 중단."""
    if fetched_at == "":
        fetched_at = config_mod.now_kst_iso()
    # 당일 쿼터 사용량 조회 (이미 로그된 것 포함)
    day = fetched_at[:10]
    usage, total = d.youtube_quota_usage(day) if hasattr(d, "youtube_quota_usage") else ({}, 0)

    def _log_quota(run_at, endpoint, units, status="ok", note=""):
        if log_quota is not None:
            log_quota(run_at, endpoint, units, status, note)
        elif hasattr(d, "log_youtube_quota"):
            d.log_youtube_quota(run_at, endpoint, units, status, note)

    result = {"fetched": 0, "quota_used": total, "errors": [], "quota_logged": 0,
              "stopped": False}
    # 인기 동영상 (1 unit)
    if total + 1 > QUOTA_BUDGET_DAILY:
        result["stopped"] = True
        return result
    pop = fetch_popular_videos(d, client=client, region=region,
                               fetched_at=fetched_at, log_quota=_log_quota)
    result["fetched"] += pop["fetched"]
    result["errors"].extend(pop["errors"])
    result["quota_used"] += pop["quota_units"]
    return result


if __name__ == "__main__":
    import db
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    cfg = config_mod.load_config()
    d = db.Database(cfg["db_url"])
    d.init()
    res = run_collection(d, cfg)
    logger.info("S-1 수집 완료: %s", res)
    d.close()
    import sys
    sys.exit(0 if not res.get("errors") else 1)
