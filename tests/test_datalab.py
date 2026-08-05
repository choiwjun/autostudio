import requests

from datalab import DatalabError, fetch_demand_ratios


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self.payload


def test_demand_index_normalized_by_anchor(monkeypatch):
    payload = {"results": [
        {"title": "냉장고", "data": [{"ratio": 50.0}, {"ratio": 50.0}]},
        {"title": "에어프라이어", "data": [{"ratio": 5.0}, {"ratio": 5.0}]},
        {"title": "무명키워드", "data": []},
    ]}
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(payload))
    r = fetch_demand_ratios("cid", "csec", ["에어프라이어", "무명키워드"],
                            "냉장고", "2026-07-04", "2026-08-03")
    # v9: 반환 구조 확장 — {"ratio": 앵커 정규화, "growth": 시계열 기울기}
    assert r["에어프라이어"]["ratio"] == 0.1
    assert r["에어프라이어"]["growth"] == 0.0  # 데이터 2개뿐 → 이전 기간 없음
    assert r["무명키워드"] == {"ratio": 0.0, "growth": 0.0}


def test_demand_growth_slope(monkeypatch):
    # v9: 최근 7일 ratio 상승 시 growth > 0 (뜨는 키워드 신호)
    payload = {"results": [
        {"title": "냉장고", "data": [{"ratio": 50.0}] * 30},
        {"title": "뜨는키워드", "data": [{"ratio": 10.0}] * 23 + [{"ratio": 20.0}] * 7},
    ]}
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(payload))
    r = fetch_demand_ratios("cid", "csec", ["뜨는키워드"],
                            "냉장고", "2026-07-04", "2026-08-03")
    assert r["뜨는키워드"]["growth"] > 0.0
    assert r["뜨는키워드"]["ratio"] > 0.2  # 평균 (10*23+20*7)/30 = 12.33 → /50 = 0.2467


def test_anchor_zero_raises(monkeypatch):
    payload = {"results": [{"title": "냉장고", "data": []}]}
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(payload))
    try:
        fetch_demand_ratios("cid", "csec", ["키워드"], "냉장고",
                            "2026-07-04", "2026-08-03")
        assert False, "should have raised"
    except DatalabError:
        pass


def test_http_error_raises(monkeypatch):
    monkeypatch.setattr(requests, "post",
                        lambda *a, **k: FakeResponse({}, status_code=429))
    try:
        fetch_demand_ratios("cid", "csec", ["키워드"], "냉장고",
                            "2026-07-04", "2026-08-03")
        assert False, "should have raised"
    except DatalabError as e:
        assert "429" in str(e)


def test_connection_error_becomes_datalab_error(monkeypatch):
    # v3: 네트워크 오류도 DatalabError로 정규화 — 안 하면 update_demand의
    # except DatalabError가 못 잡아 전체 실행이 failed로 처리됨 (스펙 §4.4)
    def boom(*a, **k):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(requests, "post", boom)
    try:
        fetch_demand_ratios("cid", "csec", ["키워드"], "냉장고",
                            "2026-07-04", "2026-08-03")
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
        fetch_demand_ratios("cid", "csec", ["키워드"], "냉장고",
                            "2026-07-04", "2026-08-03")
        assert False, "should have raised"
    except DatalabError:
        pass
