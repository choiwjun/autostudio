# tests/test_naver_client.py
import requests

from naver_client import NaverAPIError, NaverClient


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self.payload


def test_search_blog_passes_headers(monkeypatch):
    captured = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["headers"] = headers
        return FakeResponse({"items": [{"postdate": "20260801"}]})

    monkeypatch.setattr(requests, "get", fake_get)
    client = NaverClient("cid", "csec")
    result = client.search_blog("테스트", sort="sim", display=20)
    assert captured["headers"]["X-Naver-Client-Id"] == "cid"
    assert captured["headers"]["X-Naver-Client-Secret"] == "csec"
    assert result["items"][0]["postdate"] == "20260801"


def test_search_news_passes_date_sort(monkeypatch):
    captured = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured.update(url=url, params=params)
        return FakeResponse({"items": [{"title": "뉴스", "pubDate": "2026-08-06"}]})

    monkeypatch.setattr(requests, "get", fake_get)
    client = NaverClient("cid", "csec")
    result = client.search_news("테스트")
    assert captured["url"].endswith("/news.json")
    assert captured["params"]["sort"] == "date"
    assert result["items"][0]["pubDate"] == "2026-08-06"


def test_search_blog_raises_on_error(monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        return FakeResponse({"errorMessage": "SE01"}, status_code=400)

    monkeypatch.setattr(requests, "get", fake_get)
    client = NaverClient("cid", "csec")
    try:
        client.search_blog("테스트")
        assert False, "should have raised"
    except NaverAPIError as e:
        assert "SE01" in str(e)


def test_search_blog_retries_429_then_succeeds(monkeypatch):
    # v15: 429 두 번 뒤 성공 — 재시도로 스냅샷 단계 중단 방지
    import naver_client
    monkeypatch.setattr(naver_client.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def flaky_get(url, params=None, headers=None, timeout=None):
        calls["n"] += 1
        if calls["n"] < 3:
            return FakeResponse({}, status_code=429)
        return FakeResponse({"items": []})

    monkeypatch.setattr(requests, "get", flaky_get)
    client = NaverClient("cid", "csec")
    assert client.search_blog("테스트") == {"items": []}
    assert calls["n"] == 3


def test_search_blog_network_error_normalized(monkeypatch):
    # v15: requests 예외도 NaverAPIError로 정규화 (스냅샷 루프의 기존 핸들러가 잡도록)
    import naver_client
    monkeypatch.setattr(naver_client.time, "sleep", lambda s: None)

    def boom(url, params=None, headers=None, timeout=None):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(requests, "get", boom)
    client = NaverClient("cid", "csec")
    try:
        client.search_blog("테스트")
        assert False, "should have raised"
    except NaverAPIError as e:
        assert "network" in str(e)


def test_search_blog_bad_json_normalized(monkeypatch):
    # v15: 200 응답에 비정상 본문 — raw JSONDecodeError 대신 NaverAPIError
    class BadJson(FakeResponse):
        def json(self):
            raise ValueError("broken")

    monkeypatch.setattr(requests, "get",
                        lambda *a, **k: BadJson("not json"))
    client = NaverClient("cid", "csec")
    try:
        client.search_blog("테스트")
        assert False, "should have raised"
    except NaverAPIError as e:
        assert "bad json" in str(e)
