# tests/test_shopping_insight.py
# v4: 쇼핑인사이트(검색 클릭 추이) — 쇼핑 검색 API 종료 대체 상업 신호
import requests

from datalab import DatalabError
from shopping_insight import fetch_click_ratios


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self.payload


def test_click_index_normalized_by_anchor(monkeypatch):
    payload = {"results": [
        {"title": "냉장고", "data": [{"ratio": 50.0}, {"ratio": 50.0}]},
        {"title": "에어프라이어", "data": [{"ratio": 5.0}, {"ratio": 5.0}]},
        {"title": "무명키워드", "data": []},
    ]}
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(payload))
    r = fetch_click_ratios("cid", "csec", ["에어프라이어", "무명키워드"],
                           "냉장고", "50000000", "2026-07-04", "2026-08-03")
    assert r == {"에어프라이어": 0.1, "무명키워드": 0.0}


def test_anchor_zero_raises(monkeypatch):
    payload = {"results": [{"title": "냉장고", "data": []}]}
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(payload))
    try:
        fetch_click_ratios("cid", "csec", ["키워드"], "냉장고",
                           "50000000", "2026-07-04", "2026-08-03")
        assert False, "should have raised"
    except DatalabError:
        pass


def test_http_error_raises(monkeypatch):
    monkeypatch.setattr(requests, "post",
                        lambda *a, **k: FakeResponse({}, status_code=429))
    try:
        fetch_click_ratios("cid", "csec", ["키워드"], "냉장고",
                           "50000000", "2026-07-04", "2026-08-03")
        assert False, "should have raised"
    except DatalabError as e:
        assert "429" in str(e)


def test_connection_error_becomes_datalab_error(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(requests, "post", boom)
    try:
        fetch_click_ratios("cid", "csec", ["키워드"], "냉장고",
                           "50000000", "2026-07-04", "2026-08-03")
        assert False, "should have raised"
    except DatalabError:
        pass


def test_bad_json_becomes_datalab_error(monkeypatch):
    class BadJson:
        status_code = 200
        text = "not json"

        def json(self):
            raise ValueError("broken")

    monkeypatch.setattr(requests, "post", lambda *a, **k: BadJson())
    try:
        fetch_click_ratios("cid", "csec", ["키워드"], "냉장고",
                           "50000000", "2026-07-04", "2026-08-03")
        assert False, "should have raised"
    except DatalabError:
        pass
