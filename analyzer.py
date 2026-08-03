# analyzer.py
from datetime import date, timedelta


def compute_fresh_ratio(post_dates, today, window_days=7):
    # today는 호출 측이 KST 기준일을 명시적으로 전달 (러너 UTC 오염 방지 — 스펙 §3)
    if not post_dates:
        return 0.0
    cutoff = today - timedelta(days=window_days)
    fresh = 0
    for pd in post_dates:
        try:
            d = date(int(pd[:4]), int(pd[4:6]), int(pd[6:8]))
        except (ValueError, IndexError):
            continue
        if d > cutoff:
            fresh += 1
    return fresh / len(post_dates)


def analyze_keyword(client, keyword, today):
    # v4: 쇼핑 검색 API 종료로 shop 호출 제거 — 상업 신호는 쇼핑인사이트 배치(collect.py)로 대체.
    # 키워드당 호출: blog 2종 (sim + date)
    blog_sim = client.search_blog(keyword, sort="sim", display=20)
    blog_date = client.search_blog(keyword, sort="date", display=100)

    post_dates = [item.get("postdate", "") for item in blog_sim.get("items", [])]

    return {
        "total_sim": int(blog_sim.get("total", 0)),
        "total_date": int(blog_date.get("total", 0)),
        "fresh_ratio": compute_fresh_ratio(post_dates, today),
        "top_post_dates": post_dates,
    }
