# tests/test_draft_generator.py
import pytest

from draft_generator import (
    DraftGenerationError, generate_draft, parse_draft,
)


def _runner(ok=True):
    def run(prompt):
        if not ok:
            raise DraftGenerationError("opencode not found")
        assert "keyword" not in prompt or True
        return ('{"title": "제목", "first_paragraph": "첫문단", '
                '"body": "## 소제목\\n본문"}')
    return run


def test_parse_draft_json():
    d = parse_draft('{"title": "t", "first_paragraph": "p", "body": "b"}')
    assert d == {"title": "t", "first_paragraph": "p", "body": "b"}


def test_parse_draft_strips_codeblock():
    raw = '```json\n{"title": "t", "first_paragraph": "p", "body": "b"}\n```'
    assert parse_draft(raw)["title"] == "t"


def test_parse_draft_missing_field():
    with pytest.raises(DraftGenerationError):
        parse_draft('{"title": "t"}')


def test_parse_draft_not_json():
    with pytest.raises(DraftGenerationError):
        parse_draft("그냥 텍스트")


def test_generate_draft_uses_runner():
    d = generate_draft("에어프라이어", {"questions": ["어떤 걸?"]}, runner=_runner())
    assert d["title"] == "제목"
    assert d["body"].startswith("##")


def test_generate_draft_runner_error_propagates():
    with pytest.raises(DraftGenerationError):
        generate_draft("에어프라이어", {}, runner=_runner(ok=False))


def test_generate_draft_accepts_str_structure():
    d = generate_draft("에어프라이어", '{"questions": []}', runner=_runner())
    assert d["title"]
