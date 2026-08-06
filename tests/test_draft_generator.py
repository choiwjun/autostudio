# tests/test_draft_generator.py
import pytest

from draft_generator import DraftGenerationError, parse_draft

# v15: v8 단일패스 generate_draft는 프로덕션 미사용 사어 코드라 제거됨 —
# 초안 생성 진입점은 draft_pipeline.generate_two_pass 유일.


def test_parse_draft_json():
    d = parse_draft('{"title": "t", "first_paragraph": "p", "body": "b"}')
    assert d == {"title": "t", "first_paragraph": "p", "body": "b"}


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
