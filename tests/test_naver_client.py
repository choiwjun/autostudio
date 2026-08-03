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
