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


# ----- R-1: 배치 research 실제 호출 (자율 신규 주제 산출) -----

def test_research_stage_calls_run_research_with_upcoming_keywords(tmp_path, monkeypatch):
    # R-1: _run_research_stage가 '곧 뜰' 상위 키워드로 run_research를 실제 호출
    d = db.Database(_cfg(tmp_path)["db_url"]); d.init()
    d.upsert_keyword("절약 챌린지", category="금융", day="2026-08-01")
    d.upsert_keyword("걷기 습관", category="건강", day="2026-08-01")
    d.close()
    captured = {}

    def fake_research(db_conn, cfg, keywords, snapshot_fetcher=None,
                      translator=None, limit=10):
        captured["keywords"] = list(keywords)
        captured["limit"] = limit
        return {"candidates": [{"id": 1, "lang": "en"}],
                "conversion_rate": 0.5, "suggestion": "", "skipped": []}

    monkeypatch.setattr(kp, "run_research", fake_research)
    d2 = db.Database(_cfg(tmp_path)["db_url"]); d2.init()
    result = {"research": 0}
    n = kp._run_research_stage(d2, _cfg(tmp_path), result)
    d2.close()
    assert n == 1 and result["research"] == 1
    assert captured["limit"] == kp.RESEARCH_KEYWORD_LIMIT
    kws = {k for k, _ in captured["keywords"]}
    assert kws == {"절약 챌린지", "걷기 습관"}


def test_research_stage_isolates_failure(tmp_path, monkeypatch):
    # R-1: run_research 예외는 격리 — errors 기록 후 스테이지 0 반환 (파이프라인 중단 X)
    d = db.Database(_cfg(tmp_path)["db_url"]); d.init()
    d.upsert_keyword("절약 챌린지", category="금융", day="2026-08-01")
    d.close()

    def boom(*a, **k):
        raise RuntimeError("amazon down")

    monkeypatch.setattr(kp, "run_research", boom)
    d2 = db.Database(_cfg(tmp_path)["db_url"]); d2.init()
    result = {"research": 0, "errors": []}
    n = kp._run_research_stage(d2, _cfg(tmp_path), result)
    d2.close()
    assert n == 0 and result["research"] == 0
    assert any("research" in e for e in result["errors"])


# ----- R-2: 배치 assemble 표지 첨부 -----

def test_assemble_stage_attaches_cover_png(tmp_path, monkeypatch):
    # R-2: cover_bytes 미지정 시 make_cover_image 생성 → build_epub에 첨부
    d = db.Database(_cfg(tmp_path)["db_url"]); d.init()
    bid = _seed_book(d, "52주 절약 챌린지 워크북", status="ready")
    d.insert_kdp_chapter(bid, seq=1, title="챕터 1",
                         body_md="word " * 500, word_count=500, status="done")
    d.close()
    captured = {}

    def fake_assemble(book, chapters, cover_bytes=None, out_path=None):
        captured["cover"] = cover_bytes
        if out_path:
            with open(out_path, "wb") as f:
                f.write(b"PK-MOCK-EPUB")
        return b"PK-MOCK-EPUB"

    monkeypatch.setattr(kp, "build_epub", fake_assemble)
    cfg = _cfg(tmp_path)
    cfg["kdp_epub_dir"] = str(tmp_path / "out")
    d2 = db.Database(cfg["db_url"]); d2.init()
    result = {"assembled": 0}
    n = kp._run_assemble_stage(d2, cfg, result)
    d2.close()
    assert n == 1 and result["assembled"] == 1
    cover = captured.get("cover")
    assert cover is not None and cover[:8] == b"\x89PNG\r\n\x1a\n"
    # AI 공개 문구 포함 (M-1 정합 — PNG는 바이너리라 시그니처 검증, 문구는 make_cover_image 단위 테스트 담당)
