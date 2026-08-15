# v30: K-1 주제 선정 (kdp_research) — T-K1-01~04
import db
import kdp_research as kr


def make_db(tmp_path):
    d = db.Database(f"sqlite:///{tmp_path / 't.db'}")
    d.init()
    return d


# ---- 아마존 스냅샷 fetcher mock ----
def _snap(rows):
    # rows: [(title, price, rating, reviews)]
    return {"status": "available",
            "items": [{"title": t, "price": p, "rating": r, "reviews": n}
                      for t, p, r, n in rows]}


def _empty_snap():
    return {"status": "available", "items": []}


# ---- 영어 현지화 rule 기반 (결정성) ----
def test_english_candidate_rule_based(tmp_path):
    # rule 미적중은 None(→ 한국어 병행 후보), 미적중만 영어로 번역 폴백
    got = kr.english_candidate("52주 절약 챌린지", "금융", translator=None)
    assert got is not None
    assert "52 week" in got["title"].lower() or "saving" in got["title"].lower()
    assert got["lang"] == "en"


def test_english_fallback_uses_translator(tmp_path):
    # rule 미적중 → translator 호출 (runner 주입)
    calls = []

    def translator(prompt):
        calls.append(prompt)
        return '{"title": "Saving Challenge Workbook", "keywords": ["saving"], "category": "Personal Finance"}'
    got = kr.english_candidate("특이한 주제 토큰", "기타", translator=translator)
    assert got is not None
    assert calls and got["lang"] == "en"


# ---- 아마존 검색 0건 → 후보 제외 (T-K1-02) ----
def test_zero_search_excluded_from_candidates(tmp_path):
    d = make_db(tmp_path)
    kws = [("52주 절약 챌린지", "금융"), ("요가 초보 가이드", "건강")]
    snaps = {"52주 절약 챌린지": _empty_snap(),   # 수요 미검증 → 제외
             "요가 초보 가이드": _snap([("Yoga for Beginners", 9.99, 4.5, 1200)])}
    res = kr.run_research(d, {}, kws, snapshot_fetcher=lambda q: snaps[q],
                          translator=None, limit=10)
    assert res["candidates"]
    assert all("52주" not in c["title"] for c in res["candidates"])


# ---- 영어/한국어 양쪽 후보 + 전환율 게이트 (T-K1-01/03/04) ----
def test_lang_candidates_and_conversion_gate(tmp_path):
    d = make_db(tmp_path)
    kws = [("절약 챌린지", "금융"), ("56일 걷기", "건강"),
           ("AI 활용 일기", "IT"), ("특이 주제 A", "기타"),
           ("특이 주제 B", "기타"), ("특이 주제 C", "기타"), ("특이 주제 D", "기타")]
    snaps = {}
    for kw, _ in kws:
        snaps[kw] = _snap([(f"{kw} book", 9.99, 4.6, 500)])
    # 영어 현지화 실패 다수 → 한국어 병행 후보(K-2)로
    res = kr.run_research(d, {}, kws, snapshot_fetcher=lambda q: snaps[q],
                          translator=None, limit=10)
    langs = set()
    for c in res["candidates"]:
        langs.add(c["lang"])
    assert langs <= {"en", "ko"}
    assert "conversion_rate" in res
    # 전환율이 낮으면 suggestion에 한국어 비중 확대 권고
    if res["conversion_rate"] < 0.3:
        assert "한국어" in res["suggestion"]


# ---- 틈새 판정 함수 ----
def test_niche_score():
    # 경쟁 적음(권수 0, 리뷰 적음) → 높은 틈새 가중
    light = kr.niche_score([{"price": 9.99, "rating": 4.0, "reviews": 5}])
    compete = kr.niche_score([{"price": 9.99, "rating": 4.8, "reviews": 5000}] * 20)
    assert float(light["score"]) > float(compete["score"])


# ---- graceful 폴백: 스냅샷 실패 (네트워크) ----
def test_snapshot_failure_graceful_fallback(tmp_path):
    def boom(query):
        raise kr.AmazonSnapshotError("timeout parsing")
    got = kr.fetch_snapshot("x", fetcher=boom)
    assert got["status"] == "unavailable"


# ---- 저장된 후보를 kdp_books로 확인 ----
def test_research_persists_candidates(tmp_path):
    d = make_db(tmp_path)
    kws = [("절약 챌린지", "금융")]
    res = kr.run_research(d, {}, kws,
                          snapshot_fetcher=lambda q: _snap([("Saving Workbook", 9.99, 4.6, 800)]),
                          translator=None, limit=10)
    books = d.list_kdp_books()
    assert len(books) == len(res["candidates"]) >= 1
    assert all(b["status"] in ("draft",) for b in books)
    d.close()


def test_snapshot_url_encoded(monkeypatch):
    # M-4: query가 URL 인코딩(quote)되어 요청 — 특수문자·공백 안전
    captured = {}
    def fake_get(url, **kw):
        captured["url"] = url
        captured["allow_redirects"] = kw.get("allow_redirects")
        captured["stream"] = kw.get("stream")
        class Resp:
            status_code = 200
            headers = {}
            def iter_content(self, chunk_size=None):
                return [b'<div data-asin="ZZZZZZZZZZ"></div>']
            def __enter__(self): return self
            def __exit__(self, *a): return False
        return Resp()
    import requests as requests_mod
    import kdp_research
    monkeypatch.setattr(requests_mod, "get", fake_get)
    out = kdp_research.fetch_snapshot("절약 & 다이어트", fetcher=kdp_research._fetch_snapshot_http)
    assert captured["allow_redirects"] is False
    assert captured["stream"] is True
    # 공백은 + 로, & 는 %26 로 인코딩
    assert "%26" in captured["url"] or "+" in captured["url"]
    assert out["status"] == "available"


def test_snapshot_rejects_non_https_redirect(monkeypatch):
    # M-4: 비HTTPS 리다이렉트 거부 (graceful 폴백)
    calls = []
    def fake_get(url, **kw):
        calls.append(url)
        class Resp:
            status_code = 302
            headers = {"Location": "http://evil.example.com/x"}
            def __enter__(self): return self
            def __exit__(self, *a): return False
        return Resp()
    import requests as requests_mod
    import kdp_research
    monkeypatch.setattr(requests_mod, "get", fake_get)
    out = kdp_research.fetch_snapshot("x", fetcher=kdp_research._fetch_snapshot_http)
    assert out["status"] == "unavailable"
    assert calls  # 요청 시도 1회까지(비HTTPS 거부로 중단)
