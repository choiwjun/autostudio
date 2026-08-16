# shorts_research.py — v30.3: 쇼츠 파이프라인 S-1 유튜브 수집
# YouTube Data API v3 기반 매일 1회 수집 (AC-S1-1~4).
# - v31: 구현 범위 = 인기 동영상(KR) 50개(videos.list 1 unit)
#   + 채널 구독자수 통계(channels.list 1 unit) = 2 units/일.
#   기획 단계의 검색·댓글 수집은 미구현 — search.list는 공식 100 units/호출이라
#   구현 시 쿼터 예산 전체 재설계가 필요 (v31 주석 정정).
# - 멱등 UPSERT(video_id UNIQUE), 지수 백오프 재시도, 4xx 스킵
# - 쿼터 사용량 로그 (youtube_quota_log), 예산 초과 시 중단
# - 수집 성공 후 S-2 주제 스코어 산출(shorts_topic.refresh_topics) 연계
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
MAX_RETRIES = 3                # 지수 백오프 재시도 횟수
RETRY_BACKOFF_BASE = 2.0       # 2^n 초 지수 백오프
RETRY_BACKOFF_JITTER = 0.5     # 지터 (±50%)
MAX_RESULTS_POPULAR = 50       # 인기 동영상 상위 50 (S-1)

# 엔드포인트별 쿼터 단위 (공식 문서 기준 — videos/channels/commentThreads=1,
# search.list=100. v31 정정: 기존 주석이 search.list=1로 오기재돼 향후 구현 시
# 예산이 100배 과소계상될 위험이 있었다. search는 현재 미사용)
QUOTA_UNITS = {
    "videos.list": 1,
    "channels.list": 1,
    "search.list": 100,
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


def fetch_channel_subscribers(client, channel_ids, log_quota=None, run_at=""):
    """② 채널 구독자수 일괄 조회 (channels.list 1 unit) → {channel_id: 구독자수}.
    v31: S-2 정규화 지표 ②(조회/구독 비율)의 입력. 실패 시 {} 폴백 —
    구독자 미수집은 스코어가 0 기여로 강등될 뿐 수집 자체는 계속된다."""
    ids = [c for c in dict.fromkeys(channel_ids) if c]
    if not ids:
        return {}

    def log(run_at_, endpoint, units, status, note=""):
        if log_quota is not None:
            log_quota(run_at_, endpoint, units, status, note)

    try:
        resp = _call_with_retry(
            lambda: client.channels().list(
                part="statistics", id=",".join(ids[:50])).execute(),
            "channels.list", log_quota=log, run_at=run_at)
    except YouTubeAPIError as e:
        logger.warning("channel subscribers fetch failed: %s", e)
        return {}
    out = {}
    for item in resp.get("items", []):
        try:
            out[item["id"]] = int(
                item.get("statistics", {}).get("subscriberCount", 0))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def fetch_popular_videos(d, client=None, region="KR", max_results=MAX_RESULTS_POPULAR,
                         fetched_at="", log_quota=None):
    """① 인기 동영상(KR) 50개 수집 (AC-S1-1①) → youtube_raw 멱등 저장.
    v31: 채널 구독자수(channels.list 1 unit)를 병합해 저장 — S-2 지표 ② 입력.
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
    quota_units = 0
    try:
        resp = _call_with_retry(
            lambda: client.videos().list(
                part="snippet,statistics", chart="mostPopular",
                regionCode=region, maxResults=max_results).execute(),
            "videos.list", log_quota=log, run_at=fetched_at)
        quota_units += QUOTA_UNITS["videos.list"]
    except YouTubeAPIError as e:
        logger.warning("popular videos fetch failed: %s", e)
        return {"fetched": 0,
                "quota_units": QUOTA_UNITS["videos.list"], "errors": [str(e)]}

    items = resp.get("items", [])
    subs = fetch_channel_subscribers(
        client, [i.get("snippet", {}).get("channelId", "") for i in items],
        log_quota=log, run_at=fetched_at)
    quota_units += QUOTA_UNITS["channels.list"]
    for item in items:
        rec = _parse_video_item(item, region=region, fetched_at=fetched_at)
        rec["subscriber_count"] = subs.get(rec["channel_id"]) or None
        try:
            d.upsert_youtube_video(rec)
        except Exception as e:  # noqa: BLE001 — 단건 실패는 격리
            errors.append(f"{rec['video_id']}: {e}")
    return {"fetched": len(items), "quota_units": quota_units, "errors": errors}


def run_collection(d, cfg, client=None, region="KR", fetched_at="", log_quota=None):
    """S-1 배치 진입점 — 인기 동영상 + 채널 구독자 수집 + 쿼터 로그 + S-2 스코어 갱신.
    반환: {fetched, quota_used, errors, quota_logged, topics, stopped}
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
              "topics": 0, "stopped": False}
    # 인기 동영상 + 채널 통계 (2 units — v31 channels.list 추가)
    if total + QUOTA_UNITS["videos.list"] + QUOTA_UNITS["channels.list"] \
            > QUOTA_BUDGET_DAILY:
        result["stopped"] = True
        return result
    pop = fetch_popular_videos(d, client=client, region=region,
                               fetched_at=fetched_at, log_quota=_log_quota)
    result["fetched"] += pop["fetched"]
    result["errors"].extend(pop["errors"])
    result["quota_used"] += pop["quota_units"]
    # S-2 연계 — 수집 원본에서 주제 스코어 산출·저장 (API 비용 없음)
    if pop["fetched"]:
        try:
            import shorts_topic
            result["topics"] = len(shorts_topic.refresh_topics(d))
        except Exception as e:  # noqa: BLE001 — S-2 실패가 수집 성공을 덮지 않음
            logger.warning("S-2 topic refresh failed: %s", e)
            result["errors"].append(f"topics: {e}")
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
