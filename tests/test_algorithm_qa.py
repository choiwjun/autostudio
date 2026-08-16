# v31 (알고리즘 QA): 전수 알고리즘 분석에서 확정된 결함의 회귀 테스트.
# 커버: calendar DST 경계 2건, KDP ready 교착(cover/AI표기/metadata),
# 2패스 2회차 실패 시 1회차 초안 회수, 골격 물결표 범위, 최신성 연도 판정,
# 쇼핑클릭 단계 중단, 자동완성 시드 중복, AdPost 지수 표기, 상품 상한.
from datetime import date

import adpost
import autocomplete
import collect
import db
import kdp_book as kb
import kdp_research as kr
import product_recommend
from datalab import DatalabError
from draft_generator import DraftGenerationError
from draft_pipeline import _stale_month_claim, generate_two_pass
from engine.calendar import (AmbiguousCivilTimeError,
                             NonexistentCivilTimeError,
                             resolve_korean_legal_time)
from outline import _split_sentences


def _parts(y, m, d, h, mi):
    return {"year": y, "month": m, "day": d, "hour": h, "minute": mi}


# ---------- calendar DST 경계 (수정 전: TypeError 누출) ----------

def test_dst_start_boundary_raises_nonexistent():
    # 1987-05-10 02:30 — 서머타임 개시로 건너뛴 시각
    try:
        resolve_korean_legal_time(_parts(1987, 5, 10, 2, 30))
    except NonexistentCivilTimeError:
        return
    except Exception as e:  # TypeError 등 의도 외 예외
        raise AssertionError(f"의도 외 예외: {type(e).__name__}: {e}")
    raise AssertionError("NonexistentCivilTimeError가 발생해야 함")


def test_dst_end_boundary_raises_ambiguous():
    # 1987-10-11 02:30 — 서머타임 종료로 반복되는 시각
    try:
        resolve_korean_legal_time(_parts(1987, 10, 11, 2, 30))
    except AmbiguousCivilTimeError:
        return
    except Exception as e:
        raise AssertionError(f"의도 외 예외: {type(e).__name__}: {e}")
    raise AssertionError("AmbiguousCivilTimeError가 발생해야 함")


def test_dst_interior_date_unaffected():
    r = resolve_korean_legal_time(_parts(1987, 6, 15, 12, 0))
    assert r["total_offset_minutes"] == 600  # 540 + 60


# ---------- outline: 물결표 범위 절단 (수정 전: "5만원~10만원" 분리) ----------

def test_tilde_range_not_split():
    parts = _split_sentences("가격은 5만원~10만원이에요. 다음 문장입니다.")
    assert parts[0] == "가격은 5만원~10만원이에요."


def test_rank_range_not_split():
    assert len(_split_sentences("인기 1위~3위 목록이에요")) == 1


def test_tilde_korean_still_splits():
    parts = _split_sentences("좋아요~ 다음 문장입니다")
    assert len(parts) == 2


# ---------- draft_pipeline: 최신성 검수 연도 판정 ----------

_TODAY = date(2026, 8, 16)


def test_stale_month_future_year_passes():
    # 수정 전: 월 숫자 비교만으로 "2027년 3월 추천"이 stale 오탐
    assert _stale_month_claim("2027년 3월 여행지 추천 best", _TODAY) is False


def test_stale_month_explicit_past_year_fails():
    assert _stale_month_claim("2025년 3월 여행지 추천", _TODAY) is True


def test_stale_month_yearless_behavior_unchanged():
    assert _stale_month_claim("3월 여행지 추천", _TODAY) is True
    assert _stale_month_claim("12월 여행지 추천", _TODAY) is False


# ---------- draft_pipeline: 2회차 실패 시 1회차 초안 회수 ----------

def test_two_pass_recovers_first_draft_on_second_failure():
    calls = {"n": 0}

    def stateful_runner(prompt, timeout=90):
        calls["n"] += 1
        if calls["n"] == 1:  # 1회차 pass1 — 정상 골격
            return ('{"h2s": [{"title": "첫 번째 섹션", "bullets": ["a", "b"]},'
                    ' {"title": "두 번째 섹션", "bullets": ["c"]}]}')
        if calls["n"] == 2:  # 1회차 pass2 — 생성 성공하나 검수 미달(분량 부족)
            return ('{"title": "1회차 초안", "first_paragraph": "즉답 문단입니다.",'
                    ' "body": "짧은 본문"}')
        return "not json"    # 2회차 pass1 — 하드 실패

    draft, failed = generate_two_pass(
        "키워드", {"questions": ["질문?"], "facts": [], "comparisons": []},
        runner=stateful_runner, hard_budget_seconds=None)
    # 수정 전: 2회차 DraftGenerationError가 그대로 raise → 1회차 초안 폐기
    assert draft is not None and draft["title"] == "1회차 초안"
    assert "body_length" in failed


def test_two_pass_still_raises_when_no_draft():
    def boom_runner(prompt, timeout=90):
        return "not json"    # 양 회차 모두 생성 실패 → 초안 없음

    try:
        generate_two_pass(
            "키워드", {"questions": [], "facts": [], "comparisons": []},
            runner=boom_runner, hard_budget_seconds=None)
    except DraftGenerationError:
        return
    raise AssertionError("초안 없이 전체 실패 시 DraftGenerationError여야 함")


# ---------- KDP: ready 교착 회귀 (cover 판단 + AI 표기 + metadata) ----------

def _make_db(tmp_path):
    d = db.Database(f"sqlite:///{tmp_path / 'qa.db'}")
    d.init()
    return d


def _seed_complete_book(d, status="draft"):
    """QC #8을 충족하는 메타데이터를 갖춘 책 (7키워드·2카테고리·펜네임·설명)."""
    return d.insert_kdp_book(
        title="52주 절약 챌린지 워크북", status=status, lang="ko",
        source_keyword="절약", created_at="2026-08-14",
        keywords_json='["절약","워크북","가이드","초보","실습","독학","문제집"]',
        category="재테크,교육", pen_name="오토스튜디오",
        description="초보자를 위한 단계별 실습 워크북.")


def _varied_runner():
    """챕터마다 다른 본문을 반환 — chapter_duplication 회피하며 총 분량을
    length 밴드(640~1440단어) 안으로 맞춘다 (챕터 6개 × ~170단어)."""
    import json as _json
    state = {"n": 0}

    def run(prompt, timeout=120):
        state["n"] += 1
        i = state["n"]
        body = (f"chapter{i} intro sentence here. " + f"topic{i} token " * 55
                + f"detail{i} note " * 55)
        return _json.dumps({"title": "Chapter", "first_paragraph": "요약 문단",
                            "body": body, "tags": ["절약"]})
    return run


def test_generate_book_reaches_ready_end_to_end(tmp_path, monkeypatch):
    """배치 경로 교착 회귀 — 수정 전에는 ai_disclosure(cover/AI표기)와
    metadata(5키워드 저장)가 영구 실패해 ready에 도달할 수 없었다."""
    d = _make_db(tmp_path)
    bid = _seed_complete_book(d, status="assembling")
    monkeypatch.setattr(
        kb, "generate_outline",
        lambda d_, kw, s, runner=None: [
            {"title": f"챕터 {i}", "bullets": ["a"]} for i in range(1, 7)])
    kb.generate_book(d, {}, bid, runner=_varied_runner(),
                     qc_enabled=True, marks_ready=True)
    assert d.get_kdp_book(bid)["status"] == "ready"  # 수정 전: 도달 불가
    # AI 표기가 마지막 챕터에 반영(EPUB에도 표기 유지)
    chapters = d.list_kdp_chapters(bid)
    assert "AI-generated" in chapters[-1]["body_md"]
    d.close()


def test_ai_disclosure_cover_none_skips_cover_check():
    ok, _ = kb.check_ai_disclosure(
        "This book includes AI-generated content.",
        cover_text=None, cover_is_ai=True)
    assert ok  # 수정 전: cover_text=""가 None이 아니라 빈 표지 검사로 항상 실패


def test_ai_disclosure_cover_with_text_still_checked():
    ok, _ = kb.check_ai_disclosure(
        "This book includes AI-generated content.",
        cover_text="My Cover", cover_is_ai=True)
    assert not ok  # 실제 표지가 있는데 표기 없으면 여전히 실패 (M-1 유지)


def test_korean_candidate_metadata_meets_qc(tmp_path):
    c = kr.korean_candidate("절약", "재테크")
    assert len(c["keywords"]) >= 7
    assert len([x for x in c["category"].split(",") if x.strip()]) >= 2


def test_pad_keywords_reaches_seven():
    assert len(kr._pad_keywords(["a", "b"])) == 7
    assert len(kr._pad_keywords([])) == 7


def test_run_research_persists_complete_metadata(tmp_path):
    """research 산출물이 QC #8(7키워드/2카테고리/펜네임/설명)을 충족해 저장되는지."""
    d = _make_db(tmp_path)
    res = kr.run_research(
        d, {}, [("절약", "재테크")],
        snapshot_fetcher=lambda q: {"status": "ok", "items": [
            {"title": "x", "price": 9.99, "rating": 4.5, "reviews": 10}]})
    assert len(res["candidates"]) == 1
    book = d.get_kdp_book(res["candidates"][0]["id"])
    import json as _json
    assert len(_json.loads(book["keywords"])) >= 7
    assert len([x for x in book["category"].split(",") if x.strip()]) >= 2
    assert book["pen_name"]
    assert book["description"]
    d.close()


def test_run_research_marks_unavailable_snapshot(tmp_path):
    """스냅샷 unavailable(차단)은 후보 제외가 아니라 미검증 마킹으로 저장."""
    d = _make_db(tmp_path)
    res = kr.run_research(
        d, {}, [("절약", "재테크")],
        snapshot_fetcher=lambda q: {"status": "unavailable", "items": []})
    assert len(res["candidates"]) == 1  # unavailable → 제외 아님
    import json as _json
    book = d.get_kdp_book(res["candidates"][0]["id"])
    assert _json.loads(book["evidence"])["snapshot_status"] == "unavailable"
    d.close()


# ---------- collect: 쇼핑클릭 단계 중단 스코프 ----------

def test_shop_clicks_aborts_whole_stage_on_error(tmp_path, monkeypatch):
    """API 장애 시 단계 전체 중단 — 수정 전: 배치마다 반복 에러."""
    d = _make_db(tmp_path)
    fake_targets = [{"id": i, "keyword": f"kw{i}", "category": "재테크"}
                    for i in range(1, 9)]  # 2배치 (4+4)
    monkeypatch.setattr(d, "datalab_targets", lambda today, n, m: fake_targets)

    def boom(*a, **k):
        raise DatalabError("장애")

    monkeypatch.setattr(collect, "fetch_click_ratios", boom)
    cfg = {"datalab_enabled": True, "client_id": "x", "client_secret": "y",
           "shopping_insight_category": "50000000", "datalab_anchor": "냉장고"}
    collect.update_shop_clicks(d, cfg, "2026-08-16", "now",
                               budget_seconds=60, started=None)
    rows = d._qd("SELECT COUNT(*) AS c FROM collection_log "
                 "WHERE action = 'error'", (), fetch=True)
    assert rows[0]["c"] == 1  # 수정 전: 배치 수만큼(2회) 에러 로그
    d.close()


# ---------- 경량 수정 회귀 ----------

def test_parse_number_exponent_notation():
    assert adpost._parse_number("1e5") == 100000.0   # 수정 전: 15.0
    assert adpost._parse_number("1,234원") == 1234.0
    assert adpost._parse_number("") == 0.0
    assert adpost._parse_number("1.2.3") == 0.0


def test_product_search_max_items_zero(monkeypatch):
    class FakeClient:
        def search_shop(self, keyword, display=5):
            return {"items": [
                {"title": "t", "link": "https://x.com/p?productId=1",
                 "lprice": "1000", "mallName": "m"}] * 3}
    assert product_recommend.search_products(FakeClient(), "kw", max_items=0) == []


def test_expand_keywords_dedupes_seeds(monkeypatch):
    calls = []

    def fake_fetch(query, url, timeout=10, retries=3):
        calls.append(query)
        return []

    monkeypatch.setattr(autocomplete, "fetch_suggestions", fake_fetch)
    autocomplete.expand_keywords(["절약", "절약"], "http://x",
                                 max_depth=1, max_requests=10, delay=0)
    assert calls.count("절약") == 1  # 수정 전: 초기 큐 중복으로 2회 요청
