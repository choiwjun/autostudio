# v30.4 (적대적 QA): 실측 취약점 3건 + 견고성 결함 3건의 회귀 테스트.
# 서버를 실기동해 발견한 입력 벡터(NaN/거대 정수/비-ASCII 헤더/1MB 텍스트)를
# 그대로 재현해 수정 후 동작을 고정한다.
import sqlite3

import db
from fastapi.testclient import TestClient
from server import create_app

AUTH = {"Authorization": "Bearer sekret"}
HUGE = 10 ** 24  # SQLite int64(≈9.2×10^18) 초과 — OverflowError 유발값


def make_app(tmp_path, env="development"):
    dbfile = f"sqlite:///{tmp_path / 'qa.db'}"
    d = db.Database(dbfile)
    d.init()
    a = d.upsert_keyword("qa키워드", category="QA", day="2026-08-01")
    d.upsert_outline(a, "2026-08-01", '{"questions": [], "comparisons": []}')
    d.close()
    return create_app({"db_url": dbfile, "dashboard_token": "sekret",
                       "manual_budget_seconds": 45, "env": env}), dbfile


def _insert_draft(dbfile):
    """피드백 테스트용 초안 1행 직접 삽입 (LLM 생성 없이)."""
    d = db.Database(dbfile)
    kw = d.query_keywords(limit=1)[0]["id"]
    cur = d.conn.execute(
        "INSERT INTO drafts (keyword_id, title, first_paragraph, body, "
        "created_at, tags, platform, status) "
        "VALUES (?, 'qa-draft', 'p', 'b', '2026-08-16T00:00:00', '[]', "
        "'naver', 'created')", (kw,))
    d.conn.commit()
    draft_id = cur.lastrowid
    d.close()
    return draft_id


def _make_checklist_book(dbfile):
    """출간 체크리스트(키워드 7·카테고리 2)를 통과하는 KDP 책 직접 준비."""
    d = db.Database(dbfile)
    bid = d.insert_kdp_book(title="qa-book", status="draft", lang="en",
                            source_keyword="qa", created_at="2026-08-16")
    d.conn.execute(
        "UPDATE kdp_books SET keywords = ?, category = 'cat1,cat2' WHERE id = ?",
        ('["a","b","c","d","e","f","g"]', bid))
    d.conn.commit()
    d.close()
    return bid


# ---------- 취약점 1: NaN 성과 점수 → 만점 오염 ----------

def test_feedback_nan_score_rejected(tmp_path):
    app, dbfile = make_app(tmp_path)
    draft_id = _insert_draft(dbfile)
    client = TestClient(app)
    # JSON 표준에 없는 NaN 토큰 — Python json은 기본 파싱 허용
    resp = client.post(
        f"/drafts/{draft_id}/feedback", content='{"performance_score": NaN}',
        headers={"Content-Type": "application/json"})
    assert resp.status_code == 422  # 수정 전: 200 + performance_score=100.0 저장
    d = db.Database(dbfile)
    row = d.conn.execute(
        "SELECT performance_score FROM drafts WHERE id = ?",
        (draft_id,)).fetchone()
    d.close()
    assert row["performance_score"] is None  # 오염 미발생


def test_feedback_normal_score_still_works(tmp_path):
    app, dbfile = make_app(tmp_path)
    draft_id = _insert_draft(dbfile)
    client = TestClient(app)
    resp = client.post(f"/drafts/{draft_id}/feedback",
                       json={"performance_score": 85.0})
    assert resp.status_code == 200
    assert resp.json()["performance_score"] == 85.0


# ---------- 취약점 2: NaN 가격/성과 → 검증 통과 후 파열 ----------

def test_kdp_publish_nan_price_rejected(tmp_path):
    app, dbfile = make_app(tmp_path)
    bid = _make_checklist_book(dbfile)
    client = TestClient(app)
    resp = client.post(
        "/kdp/publish",
        content=f'{{"book_id": {bid}, "price": NaN}}',
        headers={"Content-Type": "application/json"})
    assert resp.status_code == 422  # 수정 전: 500 (NOT NULL 위반)


def test_kdp_performance_nan_royalty_rejected(tmp_path):
    app, dbfile = make_app(tmp_path)
    _make_checklist_book(dbfile)
    client = TestClient(app)
    resp = client.post(
        "/kdp/performance",
        content='{"book_id": 1, "year_month": "2026-08", "royalty": NaN}',
        headers={"Content-Type": "application/json"})
    assert resp.status_code == 422  # 수정 전: 500


def test_kdp_publish_price_range_unchanged(tmp_path):
    app, dbfile = make_app(tmp_path)
    bid = _make_checklist_book(dbfile)
    client = TestClient(app)
    assert client.post("/kdp/publish", json={"book_id": bid, "price": 2.98}
                       ).status_code == 400
    assert client.post("/kdp/publish", json={"book_id": bid, "price": 9.99}
                       ).status_code == 200


# ---------- 취약점 3: 비-ASCII 인증 헤더 → 무인증 500 ----------

def test_non_ascii_auth_header_is_401_not_500(tmp_path):
    app, _ = make_app(tmp_path, env="production")
    client = TestClient(app)
    # httpx는 str 헤더에 ASCII만 허용하므로 bytes로 전송 (실전 curl과 동일 경로:
    # 서버는 헤더를 latin-1로 디코드해 비-ASCII str을 받게 됨)
    resp = client.get("/keywords", headers={
        "Authorization": "Bearer 토큰한글".encode("utf-8")})
    assert resp.status_code == 401  # 수정 전: TypeError → 500

    # 정상 토큰 경로 불변
    assert client.get("/keywords", headers=AUTH).status_code == 200
    assert client.get("/keywords").status_code == 401


# ---------- 결함 4: 거대 정수 → OverflowError 500 ----------

def test_huge_page_param_clamped(tmp_path):
    app, _ = make_app(tmp_path)
    client = TestClient(app)
    resp = client.get(f"/keywords?page={HUGE}&page_size=5")
    assert resp.status_code == 200  # 수정 전: 500
    assert resp.json()["page"] == 1_000_000


def test_huge_discovered_within_clamped(tmp_path):
    app, _ = make_app(tmp_path)
    client = TestClient(app)
    resp = client.get(f"/keywords?discovered_within={HUGE}")
    assert resp.status_code == 200  # 수정 전: timedelta OverflowError → 500


def test_huge_keyword_id_is_422(tmp_path):
    app, _ = make_app(tmp_path)
    client = TestClient(app)
    resp = client.get(f"/keywords/{HUGE}")
    assert resp.status_code == 422  # 수정 전: SQLite 바인딩 OverflowError → 500


# ---------- 결함 5: 실패 INSERT 후 쓰기 잠금 잔존 ----------

def test_failed_insert_releases_lock(tmp_path):
    dbfile = f"sqlite:///{tmp_path / 'qa.db'}"
    d = db.Database(dbfile)
    d.init()
    # NOT NULL 위반 유발 — 수정 전에는 암시 트랜잭션이 열린 채 잔존
    try:
        d._qd("INSERT INTO drafts (keyword_id) VALUES (?)", (1,))
    except sqlite3.IntegrityError:
        pass
    # 외부 쓰기가 즉시 가능해야 함 (수정 전: database is locked)
    conn = sqlite3.connect(str(tmp_path / "qa.db"), timeout=2)
    conn.execute("PRAGMA busy_timeout = 2000")
    conn.execute("INSERT OR IGNORE INTO keywords (keyword, first_seen, active) "
                 "VALUES ('lock-probe', '2026-08-16', 1)")
    conn.commit()
    conn.close()
    d.close()


# ---------- 결함 6: 과대 길이/null byte 텍스트 ----------

def test_seed_oversized_keyword_rejected(tmp_path):
    app, _ = make_app(tmp_path)
    client = TestClient(app)
    resp = client.post("/seeds", json={"keyword": "A" * 100000})
    assert resp.status_code == 400  # 수정 전: 200 + 100KB 저장


def test_seed_null_byte_rejected(tmp_path):
    app, _ = make_app(tmp_path)
    client = TestClient(app)
    resp = client.post("/seeds", json={"keyword": "a\x00b"})
    assert resp.status_code == 400  # 수정 전: 200 (Postgres에선 크래시하는 지뢰)


def test_seed_normal_input_still_works(tmp_path):
    app, _ = make_app(tmp_path)
    client = TestClient(app)
    assert client.post("/seeds", json={"keyword": "보험 비교", "category": "보험"}
                       ).status_code == 200
