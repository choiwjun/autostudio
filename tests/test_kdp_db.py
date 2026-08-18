# v30: KDP 파이프라인 DB — kdp_books/kdp_chapters/kdp_publish/kdp_performance/kdp_qc_results 스키마·메서드
from db import Database


def make_db(tmp_path):
    d = Database(f"sqlite:///{tmp_path / 't.db'}")
    d.init()
    return d


def _seed_book(d, title="52주 절약 챌린지 워크북", status="draft", lang="en",
               priority=0.0, source_keyword="절약 챌린지"):
    return d.insert_kdp_book(title=title, status=status, lang=lang,
                             priority=priority, source_keyword=source_keyword,
                             created_at="2026-08-14T00:00:00")


def test_init_creates_kdp_tables(tmp_path):
    d = make_db(tmp_path)
    rows = d.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    names = {r[0] for r in rows}
    assert {"kdp_books", "kdp_chapters", "kdp_covers", "kdp_publish",
            "kdp_performance", "kdp_qc_results"} <= names
    d.close()


def test_insert_and_get_kdp_book(tmp_path):
    d = make_db(tmp_path)
    bid = _seed_book(d)
    book = d.get_kdp_book(bid)
    assert book["title"] == "52주 절약 챌린지 워크북"
    assert book["status"] == "draft"
    assert book["lang"] == "en"
    assert book["source_keyword"] == "절약 챌린지"
    d.close()


def test_title_unique_ignored(tmp_path):
    d = make_db(tmp_path)
    _seed_book(d)
    # 같은 title 재삽입 → 무시(UNIQUE) — 새 id 발급 없음
    d.insert_kdp_book(title="52주 절약 챌린지 워크북", status="draft",
                      created_at="2026-08-14")
    books = d.list_kdp_books()
    assert len(books) == 1
    d.close()


def test_update_kdp_book_status(tmp_path):
    d = make_db(tmp_path)
    bid = _seed_book(d)
    d.update_kdp_book_status(bid, "ready", updated_at="2026-08-15T00:00:00")
    assert d.get_kdp_book(bid)["status"] == "ready"
    d.close()


def test_list_kdp_books_status_filter(tmp_path):
    d = make_db(tmp_path)
    _seed_book(d, title="A", status="ready", priority=2.0)
    _seed_book(d, title="B", status="draft", priority=0.5)
    _seed_book(d, title="C", status="draft", priority=1.5)
    ready = d.list_kdp_books(status="ready")
    assert [b["title"] for b in ready] == ["A"]
    drafts = d.list_kdp_books(status="draft")
    assert [b["title"] for b in drafts] == ["C", "B"]  # priority DESC
    all_rows = d.list_kdp_books()
    assert len(all_rows) == 3
    d.close()


def test_insert_and_list_kdp_chapters(tmp_path):
    d = make_db(tmp_path)
    bid = _seed_book(d)
    d.insert_kdp_chapter(bid, seq=1, title="왜 52주인가", body_md="## 본문",
                         word_count=912, status="done")
    d.insert_kdp_chapter(bid, seq=2, title="예산 세우기")
    chapters = d.list_kdp_chapters(bid)
    assert len(chapters) == 2
    assert chapters[0]["seq"] == 1 and chapters[0]["word_count"] == 912
    assert chapters[1]["status"] == "pending"
    d.close()


def test_upsert_kdp_cover(tmp_path):
    d = make_db(tmp_path)
    bid = _seed_book(d)
    d.upsert_kdp_cover(bid, "https://cdn/cover.png", size="6x9")
    cover = d.get_kdp_cover(bid)
    assert cover["image_url"] == "https://cdn/cover.png"
    # 재upsert(같은 책) — 신규 행 추가 없음
    d.upsert_kdp_cover(bid, "https://cdn/cover2.png")
    rows = d.conn.execute(
        "SELECT COUNT(*) c FROM kdp_covers WHERE book_id = ?",
        (bid,)).fetchone()
    assert rows["c"] == 1
    d.close()


def test_insert_and_verify_kdp_publish(tmp_path):
    d = make_db(tmp_path)
    bid = _seed_book(d, status="ready")
    pid = d.insert_kdp_publish(bid, publish_date="2026-08-15", price=9.99)
    p = d.conn.execute(
        "SELECT * FROM kdp_publish WHERE id = ?", (pid,)).fetchone()
    assert p["status"] == "pending"
    assert p["expected_royalty"] == round(9.99 * 0.7 - 0.06, 2)
    d.verify_kdp_publish(pid, verified_at="2026-08-17T00:00:00",
                         mirror_status="정상", price_ok=1)
    v = d.conn.execute(
        "SELECT * FROM kdp_publish WHERE id = ?", (pid,)).fetchone()
    assert v["status"] == "verified"
    assert v["verified_at"] == "2026-08-17T00:00:00"
    assert v["mirror_status"] == "정상"
    d.close()


def test_daily_publish_gate_limits_to_three(tmp_path):
    # AC-K4-1: 일 3권 게이트 — 같은 publish_date에 3권만 'published', 4번째는 pending
    d = make_db(tmp_path)
    for i in range(4):
        bid = _seed_book(d, title=f"책{i}", status="ready", priority=4 - i)
        d.insert_kdp_publish(bid, publish_date="2026-08-15",
                             price=2.99 + i)
    result = d.publish_day_gate("2026-08-15", max_per_day=3)
    assert result["published"] == 3
    assert result["pended"] == 1
    # 초과분 pending 확인
    pend = d.conn.execute(
        "SELECT COUNT(*) c FROM kdp_publish WHERE publish_date = '2026-08-15' "
        "AND status = 'pending'").fetchone()
    assert pend["c"] == 1
    d.close()



def test_upsert_and_monthly_kdp_performance(tmp_path):
    d = make_db(tmp_path)
    bid = _seed_book(d)
    d.upsert_kdp_performance(bid, "2026-08", sales=14, royalty=97.02)
    d.upsert_kdp_performance(bid, "2026-08", sales=16, royalty=110.0)
    d.upsert_kdp_performance(bid, "2026-07", sales=11, royalty=76.23)
    m = d.list_kdp_performance("2026-08")
    assert len(m) == 1 and m[0]["sales"] == 16  # UPSERT
    summary = d.kdp_monthly_summary()
    assert summary["2026-08"] == 110.0 and summary["2026-07"] == 76.23
    d.close()


def test_replace_and_get_kdp_qc_results(tmp_path):
    d = make_db(tmp_path)
    bid = _seed_book(d, status="assembling")
    results = [
        {"qc_item": "plagiarism", "passed": 1, "detail": ""},
        {"qc_item": "length", "passed": 0, "detail": "912 < 800"},
    ]
    d.replace_kdp_qc_results(bid, "2026-08-15T00:00:00", results)
    got = d.get_kdp_qc_results(bid)
    assert len(got) == 2
    by_item = {r["qc_item"]: r for r in got}
    assert by_item["length"]["passed"] == 0
    assert by_item["length"]["detail"] == "912 < 800"
    d.close()


def test_replace_kdp_qc_results_sql_is_postgres_compatible(tmp_path):
    # v31.4 회귀 가드: INSERT OR REPLACE(SQLite 전용)가 프로덕션 Postgres 배치에서
    # "syntax error at or near OR"를 내 책 생성 런이 실패했음 — 재도입 차단.
    # 선행 DELETE가 (book_id, run_at) 중복을 배제하므로 일반 INSERT면 충분하다.
    d = make_db(tmp_path)
    bid = _seed_book(d, status="assembling")
    captured = []
    orig_qd = d._qd

    def spy(sql, params, fetch=False):
        captured.append(sql)
        return orig_qd(sql, params, fetch=fetch)

    d._qd = spy
    d.replace_kdp_qc_results(bid, "2026-08-16T00:00:00",
                             [{"qc_item": "length", "passed": 1, "detail": ""}])
    assert any(s.lstrip().startswith("INSERT") for s in captured)
    assert not any("OR REPLACE" in s.upper() for s in captured)
    d.close()


def test_publish_day_gate_atomic_concurrency(tmp_path):
    # M-2: 동시 2 스레드가 게이트 호출 → 총 3권 초과 불가 (원자적 슬롯 선점)
    import threading
    d = make_db(tmp_path)
    today = "2026-08-16"
    for i in range(6):
        bid = d.insert_kdp_book(title=f"동시책{i}", status="ready", lang="en",
                                priority=6 - i, source_keyword="절약",
                                created_at="2026-08-14")
        d.insert_kdp_publish(bid, publish_date=today, price=5.0 + i)
    results = []
    def _call():
        dd = Database(f"sqlite:///{tmp_path / 't.db'}")
        dd.init()
        results.append(dd.publish_day_gate(today, max_per_day=3))
        dd.close()
    t1 = threading.Thread(target=_call); t2 = threading.Thread(target=_call)
    t1.start(); t2.start(); t1.join(); t2.join()
    # 두 콜이 합쳐도 총 3권까지만 published (서로 같은 3건 선점 불가 — 원자화)
    published = d.conn.execute(
        "SELECT COUNT(*) c FROM kdp_publish WHERE publish_date = ? AND status = 'published'",
        (today,)).fetchone()["c"]
    assert published == 3
    # 각 스레드의 단일 콜은 3권 이하만 published
    for r in results:
        assert r["published"] <= 3
    d.close()
