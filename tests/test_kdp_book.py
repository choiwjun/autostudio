# v30: K-2 책 생성 (kdp_book) - T-K2-01~06
import db
import kdp_book as kb


def make_db(tmp_path):
    d = db.Database(f"sqlite:///{tmp_path / 't.db'}")
    d.init()
    return d


def _seed_book(d, status="draft"):
    return d.insert_kdp_book(title="52주 절약 챌린지 워크북", status=status,
                             lang="en", source_keyword="절약",
                             created_at="2026-08-14")


def _pass1_runner():
    # pass1_outline이 소비하는 형식: {"h2s":[{"title":..., "bullets":[...]}]}
    return lambda prompt, timeout=90: (
        '{"h2s": ['
        '{"title":"왜 52주인가","bullets":["개념","효과"]},'
        '{"title":"예산 세우기","bullets":["수입","목표"]},'
        '{"title":"주간 체크인","bullets":["트래커","보상"]}'
        ']}')


def _pass2_runner():
    return lambda prompt, timeout=120: (
        '{"title":"Test Chapter","first_paragraph":"즉답",'
        '"body":"이 문단은 충분한 분량의 예시 문장입니다. 문장 하나.",'
        '"tags":["키워드"]}')


def _chapter_body_words(n=1100):
    return ("word " * n)


def test_generate_outline_returns_list(tmp_path):
    d = make_db(tmp_path)
    bid = _seed_book(d)
    outline = kb.generate_outline(d, "절약", {}, runner=_pass1_runner())
    assert isinstance(outline, list) and len(outline) >= 1
    d.close()


def test_generate_chapter_persists_and_counts_words(tmp_path):
    d = make_db(tmp_path)
    bid = _seed_book(d, status="assembling")
    d.insert_kdp_chapter(bid, seq=1, title="왜 52주인가")
    body = _chapter_body_words()
    ch = kb.generate_chapter(d, {"book_id": bid, "seq": 1, "title": "왜 52주인가",
                                 "keyword": "절약"},
                             runner=lambda p, timeout=120: (
                                 f'{{"title":"C","first_paragraph":"즉답","body":"{body}"}}'))
    row = d.list_kdp_chapters(bid)[0]
    assert row["status"] == "done"
    assert row["word_count"] > 0
    d.close()


def test_chapter_budget_saves_partial(tmp_path):
    d = make_db(tmp_path)
    bid = _seed_book(d, status="assembling")
    d.insert_kdp_chapter(bid, seq=1, title="예산 세우기")

    def slow_runner(prompt, timeout=120):
        raise kb.DraftGenerationError("시간 초과")
    kb.generate_chapter(d, {"book_id": bid, "seq": 1, "title": "예산 세우기"},
                        runner=slow_runner, hard_budget_seconds=300)
    row = d.list_kdp_chapters(bid)[0]
    assert row["status"] == "partial"
    d.close()


def test_consistency_pass_runs(tmp_path):
    d = make_db(tmp_path)
    bid = _seed_book(d, status="assembling")
    for i in (1, 2):
        d.insert_kdp_chapter(bid, seq=i, title=f"챕터{i}", body_md="## 본문")
    chs = d.list_kdp_chapters(bid)
    res = kb.consistency_pass(chs, runner=lambda p, timeout=120: (
        '{"body":"통일 본문 문장입니다."}'))
    assert res["passed"] is True
    d.close()


def test_generate_book_marks_ready_on_qc_pass(tmp_path, monkeypatch):
    d = make_db(tmp_path)
    bid = _seed_book(d, status="assembling")
    # outline 고정 + run_qc 전부 통과 → ready
    monkeypatch.setattr(kb, "generate_outline",
                        lambda d, kw, s, runner=None: [
                            {"title": "챕터1", "bullets": ["a"]}])
    monkeypatch.setattr(kb, "run_qc", lambda d, bid, dump, run_at="x": [
        kb.QCResult(k, True, "") for k in kb.QC_ITEMS])
    kb.generate_book(d, {}, bid, runner=_pass2_runner(), marks_ready=True)
    assert d.get_kdp_book(bid)["status"] == "ready"
    d.close()


def test_run_qc_reports_failures(tmp_path):
    d = make_db(tmp_path)
    bid = _seed_book(d, status="assembling")
    chapters = [
        {"body_md": "투자 수익을 보장합니다. " * 200},
        {"body_md": "정상적인 본문 문장입니다. " * 200},
    ]
    results = kb.run_qc(d, bid, {"chapters": chapters, "book": {
        "keywords": "[]", "category": "Finance", "pen_name": "",
        "description": "", "title": "T"}, })
    by = {r.qc_item: r.passed for r in results}
    assert len(by) == 8
    assert by["banned_words"] is False
    d.close()


def test_generate_outline_enforces_min_chapters(tmp_path):
    # K2-1: pass1이 3개만 반환해도 MIN_CHAPTERS(6) 이상으로 패딩
    d = make_db(tmp_path)
    bid = _seed_book(d)
    outline = kb.generate_outline(d, "절약", {}, runner=_pass1_runner())
    assert isinstance(outline, list)
    assert len(outline) >= kb.MIN_CHAPTERS
    assert len(outline) <= kb.MAX_CHAPTERS
    d.close()
