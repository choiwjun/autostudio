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
    # v6: bloggername 수집 — 상위글 작성자 권위(AI 인용 C-Rank 프록시) 신호의 원자료.
    # 키워드당 호출: blog 2종 (sim + date)
    blog_sim = client.search_blog(keyword, sort="sim", display=20)
    blog_date = client.search_blog(keyword, sort="date", display=100)

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
    }
