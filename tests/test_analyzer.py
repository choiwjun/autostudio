# tests/test_analyzer.py
from datetime import date, timedelta

from analyzer import analyze_keyword, compute_fresh_ratio

TODAY = date(2026, 8, 3)


def test_compute_fresh_ratio():
    post_dates = ["20260801"] * 8 + ["20200101"] * 12
    assert compute_fresh_ratio(post_dates, TODAY) == 0.4


def test_compute_fresh_ratio_all_old():
    assert compute_fresh_ratio(["20200101"] * 20, TODAY) == 0.0


def test_compute_fresh_ratio_unparseable_excluded_from_denominator():
    # v15: 파싱 실패 건은 분모에서 제외 — fresh_ratio 과소 왜곡 방지
    # 8/1 신선 8건 + 오래됨 4건 + 파싱 불가 8건 → 8/12 (기존식은 8/20)
    post_dates = ["20260801"] * 8 + ["20200101"] * 4 + ["", "bad", "2026"] * 4
    assert len(post_dates) == 24
    assert compute_fresh_ratio(post_dates, TODAY) == 8 / 12


def test_compute_fresh_ratio_boundary_inclusive():
    # v15: 정확히 window_days(7일) 전 글도 fresh — 기존 '>' 비교 오프바이원 수정
    exact = (TODAY - timedelta(days=7)).strftime("%Y%m%d")
    assert compute_fresh_ratio([exact], TODAY) == 1.0
    older = (TODAY - timedelta(days=8)).strftime("%Y%m%d")
    assert compute_fresh_ratio([older], TODAY) == 0.0


def test_compute_fresh_ratio_all_unparseable():
    assert compute_fresh_ratio(["", "xx"], TODAY) == 0.0


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


def test_analyze_keyword_builds_blog_news_search_evidence():
    class FakeClient:
        def search_blog(self, query, sort="sim", display=100, start=1):
            if sort == "date":
                return {"total": 2, "items": [{
                    "postdate": "20260805", "title": "<b>블로그 제목</b>",
                    "description": "최신 정보\n설명", "link": "https://blog.example/post",
                }]}
            return {"total": 1, "items": [{"postdate": "20260804",
                "description": "검색 설명", "bloggername": "a"}]}

        def search_news(self, query, sort="date", display=20, start=1):
            return {"total": 1, "items": [{
                "title": "<b>뉴스 제목</b>", "description": "뉴스 설명",
                "pubDate": "Thu, 06 Aug 2026 09:00:00 +0900",
                "link": "javascript:alert(1)",
            }]}

    result = analyze_keyword(FakeClient(), "최신 정보", TODAY,
                             searched_at_kst="2026-08-06T10:00:00+09:00")
    evidence = result["search_evidence"]
    assert evidence["status"] == "available"
    assert evidence["reference_date"] == "2026-08-03"
    assert evidence["searched_at_kst"] == "2026-08-06T10:00:00+09:00"
    assert {item["source"] for item in evidence["items"]} == {"blog", "news"}
    assert all("<b>" not in item["title"] for item in evidence["items"])
    assert all(item["link"] != "javascript:alert(1)" for item in evidence["items"])


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


def test_analyze_keyword_captures_descriptions():
    # v7: 상위글 골격 분석 원자료 — description 캡처 (기존에 버리던 필드)
    items = [
        {"postdate": "20260801", "bloggername": "a",
         "description": "어떤 제품을 골라야 할까요? 추천 비교"},
        {"postdate": "20260801", "bloggername": "b", "description": "가격 3만원대 비교"},
        {"postdate": "20260801", "bloggername": "c"},  # description 없음 → 제외
    ]

    class FakeClient:
        def search_blog(self, query, sort="sim", display=100, start=1):
            return {"total": 3, "items": items}

    result = analyze_keyword(FakeClient(), "에어프라이어", TODAY)
    assert len(result["top_descriptions"]) == 2
    assert "어떤 제품을 골라야 할까요" in result["top_descriptions"][0]
