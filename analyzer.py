# analyzer.py
import re
from datetime import date, datetime, timedelta, timezone


KST = timezone(timedelta(hours=9))
EVIDENCE_MAX_ITEMS = 12
EVIDENCE_TEXT_MAX_LEN = 300
_TAG_RE = re.compile(r"<[^>]*>")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def _clean_evidence_text(value):
    text = _TAG_RE.sub("", str(value or ""))
    text = _CONTROL_RE.sub(" ", text)
    return " ".join(text.split())[:EVIDENCE_TEXT_MAX_LEN]


def _clean_evidence_url(value):
    url = str(value or "").strip()
    return url if url.startswith(("http://", "https://")) else ""


def _evidence_item(item, source, rank):
    return {
        "source": source,
        "rank": rank,
        "title": _clean_evidence_text(item.get("title")),
        "description": _clean_evidence_text(item.get("description")),
        "postdate": _clean_evidence_text(item.get("postdate")),
        "pubDate": _clean_evidence_text(item.get("pubDate")),
        "link": _clean_evidence_url(item.get("link")),
    }


def _build_search_evidence(blog_sim, blog_date, news, today, searched_at_kst):
    items = []
    for source, payload, date_key in (
        ("blog", blog_date, "postdate"),
        ("news", news, "pubDate"),
    ):
        for rank, item in enumerate(payload.get("items", [])[:EVIDENCE_MAX_ITEMS], 1):
            evidence = _evidence_item(item, source, rank)
            if evidence["title"] or evidence["description"]:
                items.append(evidence)
    return {
        "status": "available" if items else "empty",
        "searched_at_kst": searched_at_kst,
        "reference_date": today.isoformat(),
        "items": items[:EVIDENCE_MAX_ITEMS],
    }


def compute_fresh_ratio(post_dates, today, window_days=7):
    # today는 호출 측이 KST 기준일을 명시적으로 전달 (러너 UTC 오염 방지 — 스펙 §3)
    if not post_dates:
        return 0.0
    cutoff = today - timedelta(days=window_days)
    fresh = parsed = 0
    for pd in post_dates:
        try:
            d = date(int(pd[:4]), int(pd[4:6]), int(pd[6:8]))
        except (ValueError, IndexError):
            continue  # v15: 파싱 불가 날짜는 분모에서 제외 — fresh_ratio 과소 왜곡 방지
        parsed += 1
        if d >= cutoff:  # v15: 정확히 window_days일 전 글도 fresh (기존 > 는 오프바이원)
            fresh += 1
    return fresh / parsed if parsed else 0.0


def analyze_keyword(client, keyword, today, searched_at_kst=None, news=None):
    # v4: 쇼핑 검색 API 종료로 shop 호출 제거 — 상업 신호는 쇼핑인사이트 배치(collect.py)로 대체.
    # v6: bloggername 수집 — 상위글 작성자 권위(AI 인용 C-Rank 프록시) 신호의 원자료.
    # 키워드당 호출: blog 2종(sim + date)과 news 최신순 1종.
    blog_sim = client.search_blog(keyword, sort="sim", display=20)
    blog_date = client.search_blog(keyword, sort="date", display=100)
    if news is None:
        search_news = getattr(client, "search_news", None)
        news = search_news(keyword, sort="date", display=20) if search_news else {"items": []}
    searched_at_kst = searched_at_kst or datetime.now(KST).isoformat(timespec="seconds")

    items = blog_sim.get("items", [])
    post_dates = [item.get("postdate", "") for item in items]
    # v6: 상위 20개 중 작성자 중복 빈도 — 동일 블로거가 다수 점유 = 권위 블로거 존재(경쟁/성숙 신호)
    bloggers = [item.get("bloggername", "") for item in items if item.get("bloggername")]
    top_bloggers = sorted(
        {b: bloggers.count(b) for b in set(bloggers)}.items(),
        key=lambda kv: (-kv[1], kv[0]),
    )[:5]
    # v7: 상위글 골격 분석 원자료 — 검색 API description 캡처 (기존에 버리던 필드).
    #     질문형/비교/수치 구조 추출은 outline.py에서 담당
    top_descriptions = [
        item.get("description", "") for item in items[:20] if item.get("description")
    ]

    return {
        "total_sim": int(blog_sim.get("total", 0)),
        "total_date": int(blog_date.get("total", 0)),
        "fresh_ratio": compute_fresh_ratio(post_dates, today),
        "top_post_dates": post_dates,
        "top_bloggers": top_bloggers,
        "top_descriptions": top_descriptions,
        "search_evidence": _build_search_evidence(
            blog_sim, blog_date, news, today, searched_at_kst),
    }
