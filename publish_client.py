# publish_client.py — v22.3(2.x): 별도 블로그(autoblog) 발행 API 클라이언트
# 초안·운세 글을 발행 API로 HTTP 전송 (DB 직접 접근 없음 — 설계 원칙).
#   - slug 규칙: 일반 `k-{키워드 해시8}` (키워드 기반 멱등), 운세 `fortune-YYYY-MM-DD`
#   - 멱등: autoblog POST /api/posts가 slug 기준 upsert — 재발행해도 중복 없음
#   - 재시도: 지수 백오프 (429·5xx) — 게시 유실 방지 (리스크 완화)
#   - 게시 로그: 성공 시 set_draft_published_url → status/published_at 갱신 (v21.1)
import hashlib
import json
import logging
import re
import time

import requests

logger = logging.getLogger("publish_client")

RETRY_BACKOFF_SECONDS = 2.0   # 1회당 대기 초 (2, 4, 8 ...)
MAX_RETRIES = 3
REQUEST_TIMEOUT = 20


class BlogPublishError(Exception):
    """autoblog 발행 API 호출 실패 (재시도 후에도) — 게시 유실 방지용 구분."""


def blog_slug(keyword, *, fortune_ref_date=None):
    """slug 규칙 — 운세: fortune-YYYY-MM-DD, 일반: k-{sha1(keyword)[:8]}.
    autoblog slug 제약 [a-z0-9-]+ 준수 (한글 키워드는 해시로 변환)."""
    if fortune_ref_date:
        return f"fortune-{fortune_ref_date}"
    ascii_kw = re.sub(r"[^a-z0-9]+", "-", keyword.lower()).strip("-")
    if ascii_kw and ascii_kw.count("-") < 4:
        return f"k-{ascii_kw}"[:64]
    return f"k-{hashlib.sha1(keyword.encode('utf-8')).hexdigest()[:8]}"


def _post(cfg, payload, retries=MAX_RETRIES):
    url = f"{cfg['blog_api_url'].rstrip('/')}/api/posts"
    headers = {
        "Authorization": f"Bearer {cfg['blog_token']}",
        "Content-Type": "application/json",
    }
    last_err = None
    for attempt in range(retries + 1):
        try:
            resp = requests.post(url, json=payload, headers=headers,
                                 timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in (429, 500, 502, 503, 504):
                last_err = BlogPublishError(
                    f"HTTP {resp.status_code}: {resp.text[:120]}")
            else:
                # 400(검증)·401(토큰)은 재시도 무의미 — 즉시 실패
                raise BlogPublishError(
                    f"HTTP {resp.status_code}: {resp.text[:120]}")
        except requests.RequestException as e:
            last_err = BlogPublishError(f"network error: {e}")
        if attempt < retries:
            time.sleep(RETRY_BACKOFF_SECONDS * (2 ** attempt))
    raise last_err or BlogPublishError("publish failed")


def publish_draft(cfg, d, draft, keyword_row="", *, fortune_ref_date=None,
                  engine_meta=None):
    """초안을 autoblog에 발행 → 게시 로그 갱신. 성공 시 blog URL 반환.
    keyword_row: keyword/category 소스 (없으면 draft 컬럼 폴백)."""
    if not cfg.get("blog_api_url") or not cfg.get("blog_token"):
        raise BlogPublishError("BLOG_API_URL/BLOG_TOKEN 미설정 — 발행 불가")
    keyword = (keyword_row or {}).get("keyword") or draft.get("keyword") or ""
    category = (keyword_row or {}).get("category") or ""
    slug = blog_slug(keyword, fortune_ref_date=fortune_ref_date)
    try:
        tags = json.loads(draft.get("tags") or "[]")
    except (TypeError, json.JSONDecodeError):
        tags = []
    payload = {
        "slug": slug,
        "title": draft["title"],
        "body": draft["body"],
        "tags": [t for t in tags if isinstance(t, str) and t.strip()],
        "category": category,
        "image_url": draft.get("image_url") or "",
        "engine_meta": engine_meta or {},
        "status": "published",
    }
    logger.info("publishing draft=%s → blog slug=%s", draft["id"], slug)
    _post(cfg, payload)
    blog_url = f"{cfg['blog_api_url'].rstrip('/')}/{slug}"
    d.set_draft_published_url(draft["id"], blog_url)
    return blog_url


def fortune_slug(fortune_type, ref):
    """운세 글 slug — autoblog [a-z0-9-]+ 제약 준수.
    daily: fortune-YYYY-MM-DD / weekly: fortune-week-{월요일} /
    monthly: fortune-month-{YYYY-MM} / 고정 콘텐츠: fortune-{type}-{index}"""
    if fortune_type == "daily":
        return f"fortune-{ref}"
    if fortune_type == "weekly":
        return f"fortune-week-{ref}"
    if fortune_type == "monthly":
        return f"fortune-month-{ref}"
    # 고정 콘텐츠 — type은 [a-z0-9-]+ 제약에 맞춰 밑줄 제거 (day_pillar → day-pillar)
    return f"fortune-{fortune_type.replace('_', '-')}-{ref}"


FORTUNE_TAGS = {
    "daily": ["운세", "오늘의운세"],
    "weekly": ["운세", "주간운세"],
    "monthly": ["운세", "월간운세"],
    "day_pillar": ["운세", "일주"],
    "zodiac": ["운세", "별자리운세"],
    "animal": ["운세", "띠별운세"],
}


def publish_fortune(cfg, d, ref, content, fortune_type="daily"):
    """운세 블로그 상세본을 autoblog에 발행 (3.3 — 매일 자동).
    slug: fortune-{기준일} — autoblog 인덱스 정책(당일만 index)과 연동.
    engine_meta.fortune_type/ref_date — autoblog가 운세 여부·index 여부 판단."""
    if not cfg.get("blog_api_url") or not cfg.get("blog_token"):
        raise BlogPublishError("BLOG_API_URL/BLOG_TOKEN 미설정 — 발행 불가")
    slug = fortune_slug(fortune_type, ref)
    content_type = ("daily_blog", "weekly_blog", "monthly_blog",
                    "day_pillar_blog", "zodiac_blog", "animal_blog")[
        ("daily", "weekly", "monthly", "day_pillar", "zodiac", "animal")
        .index(fortune_type)]
    payload = {
        "slug": slug,
        "title": content["title"],
        "body": content["body"],
        "tags": FORTUNE_TAGS[fortune_type],
        "category": "운세",
        "image_url": content.get("image_url") or "",
        "engine_meta": {"fortune_type": fortune_type, "ref_date": ref},
        "status": "published",
    }
    logger.info("publishing fortune %s/%s → blog slug=%s",
                fortune_type, ref, slug)
    _post(cfg, payload)
    d.update_fortune_generation(
        ref, content_type, json.dumps(content, ensure_ascii=False),
        status="published")
    return f"{cfg['blog_api_url'].rstrip('/')}/{slug}"
