# tests/test_analyzer.py
from datetime import date

from analyzer import analyze_keyword, compute_fresh_ratio

TODAY = date(2026, 8, 3)


def test_compute_fresh_ratio():
    post_dates = ["20260801"] * 8 + ["20200101"] * 12
    assert compute_fresh_ratio(post_dates, TODAY) == 0.4


def test_compute_fresh_ratio_all_old():
    assert compute_fresh_ratio(["20200101"] * 20, TODAY) == 0.0


def test_analyze_keyword_combines_sources():
    blog_sim = {"total": 1000, "items": [
        {"postdate": "20260801", "bloggername": "a"} for _ in range(20)]}
    blog_date = {"total": 1200, "items": []}
    calls = {"n": 0}

    class FakeClient:
        def search_blog(self, query, sort="sim", display=100, start=1):
            calls["n"] += 1
            return blog_sim if sort == "sim" else blog_date

    # v4: 쇼핑 검색 API 종료 — 호출은 blog 2종만
    result = analyze_keyword(FakeClient(), "에어프라이어", TODAY)
    assert result["total_sim"] == 1000
    assert result["total_date"] == 1200
    assert result["fresh_ratio"] == 1.0  # 20260801은 기준일 8/3의 7일 내
    assert result["top_post_dates"][0] == "20260801"
    assert calls["n"] == 2


def test_analyze_keyword_captures_top_bloggers():
    # v6: 상위글 작성자 집중도 — 동일 블로거 다수 점유가 권위 블로거 존재 신호
    items = ([{"postdate": "20260801", "bloggername": "권위블로거"}] * 12
             + [{"postdate": "20260801", "bloggername": "일반1"}] * 5
             + [{"postdate": "20260801", "bloggername": "일반2"}] * 3)

    class FakeClient:
        def search_blog(self, query, sort="sim", display=100, start=1):
            return {"total": 50, "items": items}

    result = analyze_keyword(FakeClient(), "보험 비교", TODAY)
    assert result["top_bloggers"][0] == ("권위블로거", 12)
    assert result["top_bloggers"][1] == ("일반1", 5)
    assert result["top_bloggers"][2] == ("일반2", 3)
    assert len(result["top_bloggers"]) == 3
