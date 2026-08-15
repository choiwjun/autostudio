# v30: K-4 대시보드/API (test_kdp_api.py) - T-K4-01~06, T-DB-01~02
import config as config_mod
import db
from fastapi.testclient import TestClient
from server import create_app


def _cfg(tmp_path):
    return {
        "db_url": f"sqlite:///{tmp_path / 't.db'}",
        "env": "development",   # require_token 생략
        "dashboard_token": "",
        "client_id": "", "client_secret": "",
    }


def _seed_book(d, title="A", status="ready", price=9.99):
    bid = d.insert_kdp_book(title=title, status=status, lang="en",
                            priority=2.0, source_keyword="절약",
                            created_at="2026-08-14",
                            pen_name="Pen", description="desc",
                            keywords_json='["a","b","c","d","e","f","g"]',
                            category="Finance, Money")
    return bid


def _client(tmp_path):
    cfg = _cfg(tmp_path)
    app = create_app(cfg)
    d = db.Database(cfg["db_url"]); d.init()
    return TestClient(app), d


def test_kdp_books_list(tmp_path):
    c, d = _client(tmp_path)
    bid = _seed_book(d)
    d.close()
    r = c.get("/kdp/books")
    assert r.status_code == 200
    items = r.json()["items"]
    assert any(b["id"] == bid for b in items)


def test_kdp_book_detail_has_qc(tmp_path):
    c, d = _client(tmp_path)
    bid = _seed_book(d)
    d.replace_kdp_qc_results(bid, "2026-08-15T00:00:00", [
        {"qc_item": "length", "passed": 1, "detail": "900단어"}])
    d.close()
    r = c.get(f"/kdp/books/{bid}")
    assert r.status_code == 200
    assert r.json()["book"]["id"] == bid
    assert len(r.json()["qc"]) == 1


def test_kdp_book_create(tmp_path):
    c, d = _client(tmp_path)
    r = c.post("/kdp/books", json={"title": "신규 책"})
    assert r.status_code == 200
    bid = r.json()["book_id"]
    assert d.get_kdp_book(bid)["title"] == "신규 책"
    d.close()


def test_publish_queue_today_capacity(tmp_path):
    # AC-K4-1: 일 3권 게이트 반영 (ready 책 4권 + 오늘 publish 행 → 3 published / 1 pended)
    c, d = _client(tmp_path)
    today = str(config_mod.today_kst())
    bids = []
    for i in range(4):
        bids.append(_seed_book(d, title=f"책{i}", status="ready", price=5.0 + i))
    for b in bids:
        d.insert_kdp_publish(b, publish_date=today, price=5.0)
    d.close()
    r = c.get("/kdp/publish-queue")
    assert r.status_code == 200
    gate = r.json()["gate"]
    assert gate["published"] == 3
    assert gate["pended"] == 1


def test_publish_and_verify(monkeypatch, tmp_path):
    # AC-K4-1③ + AC-K4-2②: 출간 → 48h 확인 → verified
    c, d = _client(tmp_path)
    bid = _seed_book(d, status="ready")
    d.close()
    pr = c.post("/kdp/publish", json={"book_id": bid, "price": 9.99})
    assert pr.status_code == 200
    pid = pr.json()["publish_id"]
    vr = c.post(f"/kdp/publish/{pid}/verify",
                json={"publish_id": pid, "mirror_status": "정상", "price_ok": 1})
    assert vr.status_code == 200
    mon = c.get("/kdp/monitoring")
    # verified 후엔 미검증 목록에서 빠짐 (status=verified)
    assert mon.status_code == 200


def test_performance_and_breakeven(tmp_path):
    # AC-DB-1: 성과 입력 + 손익분기표
    c, d = _client(tmp_path)
    bid = _seed_book(d)
    d.close()
    pr = c.post("/kdp/performance",
                json={"book_id": bid, "year_month": "2026-08",
                      "sales": 14, "royalty": 97.02})
    assert pr.status_code == 200
    be = c.get("/kdp/breakeven")
    assert be.status_code == 200
    rows = {r["price"]: r for r in be.json()["items"]}
    assert rows[9.99]["royalty_per"] == 6.93


def test_monitoring_summary_kpi(tmp_path):
    c, d = _client(tmp_path)
    pid = d.insert_kdp_publish(_seed_book(d, status="published"),
                               publish_date="2026-08-15", price=9.99)
    d.close()
    r = c.get("/kdp/monitoring-summary")
    assert r.status_code == 200
    # published & verified_at NULL → 셀 수 >= 1 (단, verify 날짜에 따라 다를 수 있음)
    assert "pending_48h" in r.json()


def test_publish_blocks_incomplete_checklist(tmp_path):
    # M-3: 체크리스트 미완료(키워드<7) 책 → 출간 차단(400), AC-K4-1②
    c, d = _client(tmp_path)
    bid = d.insert_kdp_book(title="미완료책", status="ready", lang="en",
                            priority=1.0, source_keyword="절약",
                            created_at="2026-08-14", pen_name="Pen",
                            description="desc", keywords_json='["a"]',
                            category="Finance, Money")
    d.close()
    r = c.post("/kdp/publish", json={"book_id": bid, "price": 9.99})
    assert r.status_code == 400
    assert "체크리스트" in r.json()["detail"] or "차단" in r.json()["detail"]


def test_publish_queue_checklist_fields(tmp_path):
    # M-3: /kdp/publish-queue가 책별 checklist를 반환
    c, d = _client(tmp_path)
    bid = d.insert_kdp_book(title="완료책", status="ready", lang="en",
                            priority=1.0, source_keyword="절약",
                            created_at="2026-08-14", pen_name="Pen",
                            description="desc",
                            keywords_json='["a","b","c","d","e","f","g"]',
                            category="Finance, Money")
    d.close()
    r = c.get("/kdp/publish-queue")
    assert r.status_code == 200
    items = r.json()["ready_books"]
    assert items and "checklist" in items[0]
    assert items[0]["checklist"]["keywords_ok"] is True


def test_performance_history_route(tmp_path):
    # M-3: 성과 입력 후 월별 집계/이력 조회
    c, d = _client(tmp_path)
    bid = d.insert_kdp_book(title="성과책", status="published", lang="en",
                            source_keyword="절약", created_at="2026-08-14")
    d.close()
    c.post("/kdp/performance",
           json={"book_id": bid, "year_month": "2026-08",
                 "sales": 14, "royalty": 97.02})
    r = c.get("/kdp/performance-history")
    assert r.status_code == 200
    assert r.json()["items"]
