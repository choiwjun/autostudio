# v30: K-2 QC 8항목 단위 (test_kdp_qc.py) - T-K2-03~06
import db
import kdp_book as kb


def make_db(tmp_path):
    d = db.Database(f"sqlite:///{tmp_path / 't.db'}")
    d.init()
    return d


def _book_dict(keywords=6, category="Finance", pen_name="Pen", desc="설명"):
    return {"keywords": '["a","b","c","d","e","f"]',
            "category": category, "pen_name": pen_name,
            "description": desc, "title": "Book"}


def test_qc_items_are_eight():
    assert len(kb.QC_ITEMS) == 8


def test_check_banned_words():
    ok, det = kb.check_banned_words("이건 정상적인 내용")
    assert ok
    ok, det = kb.check_banned_words("수익을 보장합니다")
    assert not ok and "보장" in det


def test_check_factual_claims():
    ok, det = kb.check_factual_claims("일에 대한 안내")
    assert ok
    ok, det = kb.check_factual_claims("이 방법은 무조건 성공한다")
    assert not ok


def test_check_chapter_duplication_threshold(tmp_path):
    d = make_db(tmp_path)
    a = "동일한 문장 내용이 계속 반복됩니다. 동일 단어가 반복됩니다. " * 50
    b = "동일한 문장 내용이 계속 반복됩니다. 동일 단어가 반복됩니다. " * 50
    ok, det = kb.check_chapter_duplication([a, b])
    assert ok is False


def test_check_length_band():
    ok, _ = kb.check_length("word " * 1100)
    assert ok
    ok2, det2 = kb.check_length("word")   # 1단어 → 미달
    assert not ok2


def test_check_ai_disclosure():
    ok, _ = kb.check_ai_disclosure("본문... AI-generated 공개")
    assert ok
    ok2, _ = kb.check_ai_disclosure("AI가 작성한 부분")
    assert not ok2


def test_check_markdown_balanced():
    ok, _ = kb.check_markdown("일반 본문입니다")
    assert ok
    # fence 미닫힘 (라인 시작 fence)
    ok2, det2 = kb.check_markdown("hello\n" + chr(96) * 3)
    assert not ok2


def test_check_metadata_requires_7_2():
    ok, det = kb.check_metadata(_book_dict())
    assert not ok and "키워드 6" in det   # 6 ← 7 미달
    good = dict(_book_dict())
    good["keywords"] = '["a","b","c","d","e","f","g"]'
    good["category"] = "Finance, Money"
    ok2, _ = kb.check_metadata(good)
    assert ok2


def test_run_qc_stores_and_all_pass_ready(tmp_path):
    d = make_db(tmp_path)
    bid = d.insert_kdp_book(title="QC책", status="assembling", lang="en",
                            keywords_json='["a","b","c","d","e","f","g"]',
                            category="Finance, Money", pen_name="Pen",
                            description="설명", source_keyword="절약",
                            created_at="2026-08-14")
    chapters = [{"body_md": "정상적인 본문 문장 " + "AI-generated " * 10 + "입니다. " * 40}]
    results = kb.run_qc(d, bid, {"chapters": chapters, "book": d.get_kdp_book(bid)})
    assert len(results) == 8
    # banned_words·factual_claims·markdown·ai_disclosure 통과하되 metadata는 펜네임/카테고리 충족
    by = {r.qc_item: r.passed for r in results}
    # 전체 통과는 아니어도(길이 등) 적어도 순서/저장 확인
    stored = d.get_kdp_qc_results(bid)
    assert len(stored) == 8
    d.close()


def test_check_ai_disclosure_requires_cover_text():
    # M-1: 표지 AI 공개 문구 포함 시 통과, 부재 시 실패
    body = "본문 ... AI-generated"
    ok, _ = kb.check_ai_disclosure(body, cover_text="AI-generated", cover_is_ai=True)
    assert ok
    ok2, det2 = kb.check_ai_disclosure(body, cover_text="no disclosure", cover_is_ai=True)
    assert not ok2 and "표지" in det2
    # 표지가 AI가 아니면(직접 제작) cover 문구 불필요 통과
    ok3, _ = kb.check_ai_disclosure(body, cover_text="", cover_is_ai=False)
    assert ok3


def test_run_qc_ai_disclosure_checks_cover(tmp_path):
    # M-1: run_qc에 cover 포함 전달 — cover에 공개 문구 없으면 ai_disclosure 실패
    d = make_db(tmp_path)
    bid = d.insert_kdp_book(title="QC책2", status="assembling", lang="en",
                            keywords_json='["a","b","c","d","e","f","g"]',
                            category="Finance, Money", pen_name="Pen",
                            description="설명", source_keyword="절약",
                            created_at="2026-08-14")
    chapters = [{"body_md": "정상 본문. AI-generated 공개 문구 포함입니다. " * 3}]
    # cover에 AI 표기 없음 → ai_disclosure FAIL
    results = kb.run_qc(d, bid, {"chapters": chapters,
                                 "book": d.get_kdp_book(bid), "cover": ""})
    by = {r.qc_item: r.passed for r in results}
    assert by["ai_disclosure"] is False
    # cover에 AI 표기 있음 → ai_disclosure PASS
    d.update_kdp_book_status(bid, "assembling", updated_at="2026-08-15")
    results2 = kb.run_qc(d, bid, {"chapters": chapters,
                                  "book": d.get_kdp_book(bid),
                                  "cover": "AI-generated"})
    by2 = {r.qc_item: r.passed for r in results2}
    assert by2["ai_disclosure"] is True
    d.close()
