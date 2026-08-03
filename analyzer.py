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
        if d >= cutoff:
            fresh += 1
    return fresh / len(post_dates)


def analyze_keyword(client, keyword, today):
    blog_sim = client.search_blog(keyword, sort="sim", display=20)
    blog_date = client.search_blog(keyword, sort="date", display=100)

    shop = None
    shop_error = None
    try:
        shop = client.search_shop(keyword, display=10)
    except Exception as e:
        shop_error = str(e)

    post_dates = [item.get("postdate", "") for item in blog_sim.get("items", [])]
    shop_items = shop.get("items", []) if shop else []
    prices = [int(i.get("lprice", 0)) for i in shop_items if i.get("lprice")]
    category = ""
    if shop_items:
        category = shop_items[0].get("category1", "")
        if shop_items[0].get("category2"):
            category = f"{category}/{shop_items[0].get('category2')}"

    return {
        "total_sim": int(blog_sim.get("total", 0)),
        "total_date": int(blog_date.get("total", 0)),
        "fresh_ratio": compute_fresh_ratio(post_dates, today),
        "top_post_dates": post_dates,
        "shop_total": int(shop.get("total", 0)) if shop else 0,
        "shop_avg_price": int(sum(prices) / len(prices)) if prices else 0,
        "shop_category": category,
        "shop_error": shop_error,
    }
