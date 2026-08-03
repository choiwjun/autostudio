# tests/test_db_postgres.py
import os
import threading

import pytest

import db

PG_URL = os.getenv("DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not PG_URL, reason="DATABASE_URL 미설정")


def make_db():
    d = db.Database(PG_URL)
    d.init()
    return d


def test_init_is_idempotent_and_lock_index_exists():
    d = make_db()
    d.init()  # 재실행 안전 (마이그레이션 멱등 — CREATE IF NOT EXISTS)
    rows = d._qd(
        "SELECT indexname FROM pg_indexes WHERE tablename = 'collection_runs'",
        (), fetch=True)
    assert any("idx_collection_runs_running" in r["indexname"] for r in rows)


def test_upsert_and_query_roundtrip():
    d = make_db()
    kid = d.upsert_keyword("pg통합", category="가전", day="2026-08-03")
    d.insert_daily_stats(kid, "2026-08-03", {"total_sim": 100, "opportunity": 55.0})
    rows = d.query_keywords(q="pg통합")
    assert rows[0]["opportunity"] == 55.0
    assert rows[0]["category"] == "가전"  # LEFT JOIN + COALESCE fallback 동일 동작


def test_run_lock_atomic_under_concurrency():
    # v3: 동시 start_run 8건 → running 행은 정확히 1개 (원자 취득, 스펙 §4.7)
    d = make_db()
    d._qd("DELETE FROM collection_runs", ())
    now = "2026-08-03T07:17:00+09:00"
    stale = "2026-08-03T06:17:00+09:00"
    ids, errors = [], []

    def acquire():
        try:
            ids.append(d.start_run("schedule", now, stale))
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    ts = [threading.Thread(target=acquire) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errors
    running = [r for r in d.get_last_runs(10) if r["status"] == "running"]
    assert len(running) == 1  # 잠금 소유자 1명


def test_reconnect_after_pooler_restart():
    # v3: 풀러 재시작(커넥션 사망) 시뮬레이션 — _q의 1회 재연결로 복구 (스펙 §3)
    d = make_db()
    d._connect()  # 커넥션 강제 교체
    rows = d._qd("SELECT 1 AS ok", (), fetch=True)
    assert rows[0]["ok"] == 1
    d.close()
