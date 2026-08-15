# v30: K-4 KDP 배치 진입점 (test_kdp_pipeline.py) — H-1 end-to-end 오케스트레이션 검증
import pytest
from datetime import date, timedelta

import config as config_mod
import db
import kdp_pipeline as kp


def _cfg(tmp_path):
    return {"db_url": f"sqlite:///{tmp_path / 't.db'}"}


def _seed_book(d, title, status="draft", source_keyword="절약"):
    return d.insert_kdp_book(title=title, status=status, lang="en",
                             priority=2.0, source_keyword=source_keyword,
                             created_at="2026-08-14")


def test_run_pipeline_day_gate(tmp_path):
    d = db.Database(_cfg(tmp_path)["db_url"]); d.init()
    today = "2026-08-15"
    for i in range(4):
        bid = _seed_book(d, f"책{i}", status="ready")
        d.insert_kdp_publish(bid, publish_date=today, price=5.0 + i)
    d.close()
    res = kp.run_pipeline({"db_url": _cfg(tmp_path)["db_url"]}, today=date(2026, 8, 15))
    assert res["published"] == 3
    assert res["pended"] == 1


def test_run_pipeline_counts_unverified_48h(tmp_path):
    d = db.Database(_cfg(tmp_path)["db_url"]); d.init()
    past = (date(2026, 8, 1)).isoformat()
    bid = _seed_book(d, "오래된 책", status="published")
    pid = d.insert_kdp_publish(bid, publish_date=past, price=9.99)
    d.conn.execute("UPDATE kdp_publish SET status = 'published' WHERE id = ?", (pid,))
    d.conn.commit()
    d.close()
    res = kp.run_pipeline({"db_url": _cfg(tmp_path)["db_url"]},
                          today=date(2026, 8, 15))
    assert res["pending_48h"] >= 1


def test_main_exit_zero_without_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(kp.config_mod, "load_config",
                        lambda: {"db_url": f"sqlite:///{tmp_path / 'm.db'}"})
    with pytest.raises(SystemExit) as e:
        kp.main()
    assert e.value.code == 0


# ----- H-1: end-to-end 파이프라인 (research → generate → assemble) -----

def _mock_research(d, cfg, keywords, snapshot_fetcher=None, translator=None, limit=10):
    # draft·source_keyword 책을 ready(후보 수락 후)로 두고 research 산출 기록
    d.update_kdp_book_status(1, "draft", updated_at="2026-08-15T00:00:00")
    return {"candidates": [{"id": 1, "lang": "en"}], "conversion_rate": 1.0,
            "suggestion": "", "skipped": []}


def _mock_generate(d, cfg, book_id, runner=None, translator=None,
                   qc_enabled=True, marks_ready=False):
    # 챕터 2개 완성 + QC 전부 통과 → ready
    for i in (1, 2):
        d.insert_kdp_chapter(book_id, seq=i, title=f"챕터 {i}",
                             body_md="word " * 500, word_count=500, status="done")
    d.update_kdp_book_status(book_id, "ready", updated_at="2026-08-15T00:00:00")
    return {"status": "ready", "chapters": [], "qc": None}


def _mock_assemble(book, chapters, cover_bytes=None, out_path=None):
    # EPUB 저장 — epub 경로를 DB에 기록 (또는 out 파일 생성)
    if out_path:
        with open(out_path, "wb") as f:
            f.write(b"PK-MOCK-EPUB")
    return b"PK-MOCK-EPUB"


def test_run_pipeline_full_flow(tmp_path, monkeypatch):
    # H-1: draft 책 1권 → research → generate(ready 전이) → assemble(EPUB) 완주
    d = db.Database(_cfg(tmp_path)["db_url"]); d.init()
    bid = _seed_book(d, "52주 절약 챌린지 워크북", status="draft")
    d.close()
    monkeypatch.setattr(kp, "run_research", _mock_research)
    monkeypatch.setattr(kp, "generate_book", _mock_generate)
    monkeypatch.setattr(kp, "build_epub", _mock_assemble)
    cfg = _cfg(tmp_path)
    cfg["kdp_epub_dir"] = str(tmp_path / "out")
    res = kp.run_pipeline(cfg, today=date(2026, 8, 15))
    assert res.get("generated", 0) >= 1
    assert res.get("assembled", 0) >= 1
    d2 = db.Database(cfg["db_url"]); d2.init()
    assert d2.get_kdp_book(bid)["status"] == "ready"
    d2.close()
