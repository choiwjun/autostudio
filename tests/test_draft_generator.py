# tests/test_draft_generator.py
import pytest

from draft_generator import DraftGenerationError, parse_draft

# v15: v8 단일패스 generate_draft는 프로덕션 미사용 사어 코드라 제거됨 —
# 초안 생성 진입점은 draft_pipeline.generate_two_pass 유일.


def test_parse_draft_json():
    d = parse_draft('{"title": "t", "first_paragraph": "p", "body": "b"}')
    assert d == {"title": "t", "first_paragraph": "p", "body": "b", "tags": []}


def test_parse_draft_strips_codeblock():
    raw = '```json\n{"title": "t", "first_paragraph": "p", "body": "b"}\n```'
    assert parse_draft(raw)["title"] == "t"


def test_parse_draft_strips_uppercase_codeblock():
    # v15: 공용 펜스 제거 — 대문자 ```JSON도 처리 (기존 소문자 전용 매칭 누락)
    raw = '```JSON\n{"title": "t", "first_paragraph": "p", "body": "b"}\n```'
    assert parse_draft(raw)["title"] == "t"
    raw2 = '```\n{"title": "t2", "first_paragraph": "p", "body": "b"}\n```'
    assert parse_draft(raw2)["title"] == "t2"


def test_parse_draft_missing_field():
    with pytest.raises(DraftGenerationError):
        parse_draft('{"title": "t"}')


def test_parse_draft_not_json():
    with pytest.raises(DraftGenerationError):
        parse_draft("그냥 텍스트")


def test_faq_appended_when_missing():
    # v8: AEO — 모델이 FAQ를 놓치면 골격 질문으로 보정
    from draft_generator import _append_faq_if_missing
    draft = {"title": "t", "first_paragraph": "p", "body": "## 본문\n내용"}
    out = _append_faq_if_missing(draft, {"questions": ["어떤 게 좋을까?", "가격은?"]})
    assert "자주 묻는 질문" in out["body"]
    assert "어떤 게 좋을까" in out["body"]


def test_faq_not_duplicated_when_present():
    from draft_generator import _append_faq_if_missing
    draft = {"title": "t", "first_paragraph": "p", "body": "## 자주 묻는 질문\n이미 있음"}
    out = _append_faq_if_missing(draft, {"questions": ["어떤 걸?"]})
    assert out["body"].count("자주 묻는 질문") == 1


def test_faq_skipped_without_questions():
    from draft_generator import _append_faq_if_missing
    draft = {"title": "t", "first_paragraph": "p", "body": "본문"}
    out = _append_faq_if_missing(draft, {"questions": []})
    assert out["body"] == "본문"


# ---------- v17.2: 태그 정규화 ----------

def test_parse_draft_normalizes_tags():
    # # 제거·공백 정리·중복 제거·순서 유지
    raw = ('{"title": "t", "first_paragraph": "p", "body": "b", '
           '"tags": ["#여름휴가", " 여름 휴가 추천 ", "여름휴가", "", "부산 여행"]}')
    assert parse_draft(raw)["tags"] == ["여름휴가", "여름 휴가 추천", "부산 여행"]


def test_parse_draft_tags_missing_or_malformed():
    assert parse_draft('{"title": "t", "first_paragraph": "p", "body": "b"}')["tags"] == []
    # 리스트가 아니면 빈 리스트로 정규화 (모델이 문자열로 돌려주는 경우 대비)
    raw = ('{"title": "t", "first_paragraph": "p", "body": "b", '
           '"tags": "여름휴가"}')
    assert parse_draft(raw)["tags"] == []


def test_parse_draft_tags_capped():
    from draft_generator import TAGS_MAX_COUNT
    tags = [f"태그{i}" for i in range(15)]
    import json as json_mod
    raw = json_mod.dumps({"title": "t", "first_paragraph": "p",
                          "body": "b", "tags": tags}, ensure_ascii=False)
    assert len(parse_draft(raw)["tags"]) == TAGS_MAX_COUNT
