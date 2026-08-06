# tests/test_autocomplete.py
import time

import requests

import autocomplete
from autocomplete import (
    AutocompleteError, expand_keywords, fetch_suggestions, parse_suggestions,
)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload


URL = "https://ac.search.naver.com/nx/ac"


def test_parse_legacy_list_format():
    payload = ["시드", ["시드A", "시드B"], ["0", "1"], ["", ""]]
    assert parse_suggestions(payload) == ["시드A", "시드B"]


def test_parse_dict_items_format():
    payload = {"items": [[["에어프라이어 요리"], ["에어프라이어 추천"]]]}
    assert parse_suggestions(payload) == ["에어프라이어 요리", "에어프라이어 추천"]


def test_parse_garbage_returns_empty():
    assert parse_suggestions({}) == []
    assert parse_suggestions(["only"]) == []
    assert parse_suggestions(None) == []


def test_fetch_retries_with_backoff(monkeypatch):
    calls = {"n": 0}
    sleeps = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))

    def fake_get(url, params=None, headers=None, timeout=None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise requests.ConnectionError("boom")
        return FakeResponse(["시드", ["시드A"], ["0"], [""]])

    monkeypatch.setattr(requests, "get", fake_get)
    assert fetch_suggestions("시드", URL) == ["시드A"]
    assert calls["n"] == 3
    assert sleeps == [0.5, 1.0]


def test_expand_bfs_known_pass_through(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    graph = {
        "시드": ["시드A", "알던키워드"],
        "시드A": ["시드A상세"],
        "알던키워드": ["알던키워드 신상"],
    }
    monkeypatch.setattr(
        autocomplete, "fetch_suggestions",
        lambda q, url, timeout=10, retries=3: graph.get(q, []),
    )
    new, origins, stopped = expand_keywords(
        ["시드"], url=URL, known={"알던키워드"}, max_new=100, max_depth=2)
    assert stopped is None
    assert "시드A" in new and "시드A상세" in new
    assert "알던키워드" not in new   # 기존 키워드는 일일 상한을 소모하지 않음
    assert "알던키워드 신상" in new  # 기존 키워드를 경유해 더 깊이 발굴 (v1 정체 수정)
    assert origins["시드A"] == "시드"  # v3: 유래 키워드 추적 — 시드 분야 전파의 전제


def test_expand_respects_max_new(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setattr(
        autocomplete, "fetch_suggestions",
        lambda q, url, timeout=10, retries=3: [f"시드{i}" for i in range(10)],
    )
    new, _, _ = expand_keywords(["시드"], url=URL, max_new=3, max_depth=1)
    assert len(new) == 3


def test_expand_aborts_on_total_failure(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)

    def always_fail(q, url, timeout=10, retries=3):
        raise AutocompleteError("blocked")

    monkeypatch.setattr(autocomplete, "fetch_suggestions", always_fail)
    new, _, stopped = expand_keywords(["시드"], url=URL, max_new=10, max_depth=2)
    assert new == []
    assert stopped == "blocked"


def test_expand_stops_on_budget(monkeypatch):
    # v3: 수동 실행 잔여 예산 소진 → 'budget'으로 중단 (차단과 구분 — 스펙 §4.9)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setattr(
        autocomplete, "fetch_suggestions",
        lambda q, url, timeout=10, retries=3: [f"시드{i}" for i in range(10)],
    )
    new, origins, stopped = expand_keywords(
        ["시드"], url=URL, max_new=100, max_depth=1, budget_seconds=0)
    assert new == []
    assert origins == {}
    assert stopped == "budget"


def test_expand_exclude_blocks_noise_waypoints(monkeypatch):
    # v14: exclude 판별이 True인 제안어는 수집은 물론 다음 depth 경유지에서도 제외 —
    # 노이즈 키워드가 하위 제안어를 증폭시키던 팬아웃 차단
    monkeypatch.setattr(time, "sleep", lambda s: None)
    queried = []

    def fake_fetch(q, url, timeout=10, retries=3):
        queried.append(q)
        return {
            "시드": ["노이즈경유", "정상키워드"],
            "노이즈경유": ["노이즈하위1", "노이즈하위2"],
            "정상키워드": ["정상 하위"],
        }.get(q, [])

    monkeypatch.setattr(autocomplete, "fetch_suggestions", fake_fetch)
    new, origins, stopped = expand_keywords(
        ["시드"], url=URL, max_new=100, max_depth=2,
        exclude=lambda w: w.startswith("노이즈"))
    assert stopped is None
    assert new == ["정상키워드", "정상 하위"]
    assert "노이즈경유" not in origins          # 유래 지도에도 없음
    assert "노이즈경유" not in queried           # 경유지 쿼리 자체를 안 함
    assert queried == ["시드", "정상키워드"]
