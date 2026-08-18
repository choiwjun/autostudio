# v32: 유입 키워드 피드백 루프 — 크리에이터 어드바이저 실측 유입 키워드 임포트 →
# 키워드 스코어링 반영(계열 가점) + 게시 반복 무유입 키워드 감점.
# 목적: 대시보드 추천(시장 가설)과 실제 블로그 유입(실측)의 괴리를 루프로 닫는다.
import db
from fastapi.testclient import TestClient
from server import create_app

AUTH = {"Authorization": "Bearer sekret"}


def make_db(tmp_path):
    d = db.Database(f"sqlite:///{tmp_path / 't.db'}")
    d.init()
    return d


def _publish(d, keyword_id, n):
    for i in range(n):
        did = d.insert_draft(keyword_id, f"게시글 {i}", "첫 문단", "본문입니다")
        d._qd("UPDATE drafts SET status = 'published' WHERE id = ?", (did,))


def make_app(tmp_path):
    """키워드 3종 시드:
    - 실비보험추천: 유입 계열(실비보험) 매칭 대상
    - 에어프라이어: 게시 0건·무유입 (감점 대상 아님)
    - 홍삼종류: 게시 3건·무유입 → 감점 대상"""
    dbfile = f"sqlite:///{tmp_path / 't.db'}"
    d = db.Database(dbfile)
    d.init()
    d.upsert_keyword("실비보험추천", day="2026-08-01")
    d.upsert_keyword("에어프라이어", day="2026-08-01")
    c = d.upsert_keyword("홍삼종류", day="2026-08-01")
    _publish(d, c, 3)
    d.close()
    return create_app({"db_url": dbfile, "dashboard_token": "sekret",
                       "manual_budget_seconds": 45, "env": "production"})


# ---------- 스키마 ----------

def test_inflow_table_and_score_column_created(tmp_path):
    d = make_db(tmp_path)
    names = {r[0] for r in d.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "inflow_keywords" in names
    cols = {r[1] for r in d.conn.execute("PRAGMA table_info(keywords)")}
    assert "inflow_score" in cols
    d.close()


# ---------- 계열 매칭 규칙 ----------

def test_family_matching_rules():
    fam = db.Database.inflow_family
    assert fam("실비보험", "실비보험")            # 완전 일치
    assert fam("실비보험", "실비보험추천")        # 포함 (짧은 쪽 4자 이상)
    assert fam("실비보험추천", "실비보험")        # 방향 무관
    assert fam("에어프라이어", "에어프라이어 추천 리스트")  # 긴 변형도 같은 계열
    assert not fam("보험", "실비보험추천")        # 너무 짧은 토큰 과매칭 차단
    assert not fam("캠핑", "캠핑의자")            # 2자 토큰 차단
    assert not fam("", "실비보험")                # 빈 문자열
    assert not fam("에어프라이어", "홍삼종류")    # 무관


# ---------- 임포트 엔드포인트 ----------

def test_import_requires_auth(tmp_path):
    client = TestClient(make_app(tmp_path))
    r = client.post("/inflow/import", json={"items": [{"keyword": "실비보험"}]})
    assert r.status_code == 401
    assert client.get("/inflow/keywords").status_code == 401


def test_import_items_and_text(tmp_path):
    client = TestClient(make_app(tmp_path))
    # items + 붙여넣기 텍스트(탭/공백 구분·방문수 생략 가능) 병행 임포트
    r = client.post("/inflow/import", json={
        "items": [{"keyword": "실비보험", "visits": 120}],
        "text": "에어프라이어\t80\n청소기 추천 45\n\n노트북",
    }, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["imported"] == 4
    kws = {i["keyword"] for i in client.get(
        "/inflow/keywords", headers=AUTH).json()["items"]}
    assert {"실비보험", "에어프라이어", "청소기 추천", "노트북"} <= kws


def test_import_idempotent_same_day(tmp_path):
    client = TestClient(make_app(tmp_path))
    payload = {"items": [{"keyword": "실비보험", "visits": 100}]}
    client.post("/inflow/import", json=payload, headers=AUTH)
    client.post("/inflow/import", json=payload, headers=AUTH)
    rows = client.get("/inflow/keywords", headers=AUTH).json()["items"]
    assert [r for r in rows if r["keyword"] == "실비보험"] == [
        {"keyword": "실비보험", "visits": 100,
         "recorded_at": rows[0]["recorded_at"]}]


def test_import_validation(tmp_path):
    client = TestClient(make_app(tmp_path))
    # 빈 키워드 무시(행 자체 스킵), 200자 초과 거부, 음수 visits는 0 클램프
    r = client.post("/inflow/import", json={
        "items": [{"keyword": "가" * 201}], "text": ""}, headers=AUTH)
    assert r.status_code == 400
    r = client.post("/inflow/import", json={
        "items": [{"keyword": "실비보험", "visits": -5}], "text": "\n  \n"},
        headers=AUTH)
    assert r.status_code == 200
    assert r.json()["imported"] == 1


# ---------- 스코어링 반영 ----------

def _scores(client):
    items = client.get("/keywords?page_size=200", headers=AUTH).json()["items"]
    return {i["keyword"]: i for i in items}


def test_family_boost_and_no_inflow_demotion(tmp_path):
    client = TestClient(make_app(tmp_path))
    client.post("/inflow/import", json={
        "items": [{"keyword": "실비보험", "visits": 120}]}, headers=AUTH)
    s = _scores(client)
    assert s["실비보험추천"]["inflow_score"] == db.INFLOW_FAMILY_BOOST
    # 게시 3건·무유입 → 감점 / 게시 0건은 대상 아님
    assert s["홍삼종류"]["inflow_score"] == db.INFLOW_NO_RESULT_PENALTY
    assert s["에어프라이어"]["inflow_score"] == 0.0


def test_boost_raises_priority(tmp_path):
    client = TestClient(make_app(tmp_path))
    before = _scores(client)["실비보험추천"]["priority"]
    client.post("/inflow/import", json={
        "items": [{"keyword": "실비보험", "visits": 120}]}, headers=AUTH)
    after = _scores(client)["실비보험추천"]["priority"]
    # 스냅샷 없는 키워드(priority 0)도 유입 가점으로 우선순위 상승
    assert after == before + db.INFLOW_FAMILY_BOOST


def test_reimport_recomputes_scores(tmp_path):
    client = TestClient(make_app(tmp_path))
    client.post("/inflow/import", json={
        "items": [{"keyword": "실비보험"}]}, headers=AUTH)
    assert _scores(client)["실비보험추천"]["inflow_score"] == db.INFLOW_FAMILY_BOOST
    # 매칭 없는 새 유입만 재임포트 → 기존 계열 가점은 유지(30일 창)
    client.post("/inflow/import", json={
        "items": [{"keyword": "캠핑의자"}]}, headers=AUTH)
    assert _scores(client)["실비보험추천"]["inflow_score"] == db.INFLOW_FAMILY_BOOST


# ---------- 적대적 케이스 (검증 강화) ----------

def test_empty_import_no_side_effects(tmp_path):
    client = TestClient(make_app(tmp_path))
    r = client.post("/inflow/import", json={"items": [], "text": "  \n"},
                    headers=AUTH)
    assert r.json()["imported"] == 0
    # 빈 임포트가 대량 감점을 유발하면 안 됨 (재계산 자체를 건너뜀)
    assert _scores(client)["홍삼종류"]["inflow_score"] == 0.0


def test_text_parsing_edge_cases(tmp_path):
    client = TestClient(make_app(tmp_path))
    # 천 단위 콤마 방문수 + 숫자만 있는 행(키워드 없음 → 무시)
    r = client.post("/inflow/import", json={
        "text": "실비보험\t1,234\n80"}, headers=AUTH)
    assert r.json()["imported"] == 1
    items = client.get("/inflow/keywords", headers=AUTH).json()["items"]
    assert items[0]["keyword"] == "실비보험"
    assert items[0]["visits"] == 1234


def test_unpublished_drafts_not_demoted(tmp_path):
    # 미게시 초안 3건은 감점 대상 아님 — 'published' 게시만 계산
    client = TestClient(make_app(tmp_path))
    d = db.Database(f"sqlite:///{tmp_path / 't.db'}")
    kid = d.upsert_keyword("미게시대상", day="2026-08-01")
    for i in range(3):
        d.insert_draft(kid, f"미게시 {i}", "첫 문단", "본문")  # status=draft
    d.close()
    client.post("/inflow/import", json={
        "items": [{"keyword": "실비보험"}]}, headers=AUTH)
    assert _scores(client)["미게시대상"]["inflow_score"] == 0.0


def test_long_inflow_boosts_short_keyword(tmp_path):
    # 유입이 긴 변형이어도 짧은 키워드가 계열 가점을 받음
    client = TestClient(make_app(tmp_path))
    client.post("/inflow/import", json={
        "items": [{"keyword": "에어프라이어 추천 리스트"}]}, headers=AUTH)
    assert _scores(client)["에어프라이어"]["inflow_score"] == db.INFLOW_FAMILY_BOOST
