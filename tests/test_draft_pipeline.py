# tests/test_draft_pipeline.py
import pytest

from draft_pipeline import (
    KEYWORD_DENSITY_MAX, KEYWORD_DENSITY_MIN, TITLE_MAX_LEN,
    check_faq, check_first_paragraph, check_keyword_density,
    check_no_fake_experience, check_tables, check_title,
    generate_two_pass, pass1_outline, pass2_expand, validate_draft,
)
from draft_generator import DraftGenerationError


def _good_draft(keyword="에어프라이어"):
    return {
        "title": "에어프라이어 추천, 어떤 게 좋을까요?",
        "first_paragraph": "에어프라이어는 바삭한 식감을 원한다면 오븐형, 간편함을 원한다면 바스켓형이 좋습니다. 조리 시간과 관리 편의성을 먼저 확인하세요.",
        "body": (
            "## 에어프라이어 추천 기준\n"
            "에어프라이어 추천은 용량과 조리 방식으로 나뉩니다.\n\n"
            "| 구분 | 바스켓형 | 오븐형 |\n"
            "| --- | --- | --- |\n"
            "| 용량 | 3~5L | 10L+ |\n"
            "| 가격 | 5~10만원 | 15만원+ |\n\n"
            "## 자주 묻는 질문\n"
            "### 에어프라이어 세척은 어떻게 하나요?\n"
            "바스켓과 트레이를 분리해 세척하면 됩니다."
        ),
    }


def test_check_title():
    assert check_title({"title": "짧은 제목"})
    assert not check_title({"title": "가" * (TITLE_MAX_LEN + 1)})


def test_check_first_paragraph():
    assert check_first_paragraph(_good_draft())
    assert not check_first_paragraph({"first_paragraph": "짧음"})


def test_check_tables():
    assert check_tables(_good_draft())
    assert not check_tables({"body": "표 없음"})


def test_check_faq():
    assert check_faq(_good_draft())
    assert not check_faq({"body": "FAQ 없음"})


def test_check_keyword_density():
    good = _good_draft()
    assert check_keyword_density(good, "에어프라이어")
    # 과도한 키워드 반복은 도배로 판정
    spam = {"body": "에어프라이어 " * 500}
    assert not check_keyword_density(spam, "에어프라이어")


def test_check_no_fake_experience():
    assert check_no_fake_experience(_good_draft())
    assert not check_no_fake_experience({"body": "제가 직접 사용해봤습니다"})


def test_validate_draft_all_pass():
    ok, failed = validate_draft(_good_draft(), "에어프라이어")
    assert ok
    assert failed == []


def test_pass1_outline_uses_runner():
    captured = {}

    def fake_run(prompt, timeout=90):
        captured["prompt"] = prompt
        return '{"h2s": [{"title": "어떤 걸 골라야 하나요?", "bullets": ["용량", "가격"]}]}'

    h2s = pass1_outline("에어프라이어", {"questions": ["어떤 걸?"]}, runner=fake_run)
    assert h2s[0]["title"] == "어떤 걸 골라야 하나요?"


def test_pass1_bad_json_raises():
    with pytest.raises(DraftGenerationError):
        pass1_outline("키워드", {}, runner=lambda p, timeout=90: "not json")


def test_pass2_expand_uses_runner():
    captured = {}

    def fake_run(prompt, timeout=90):
        captured["prompt"] = prompt
        return '{"title": "제목", "first_paragraph": "즉답", "body": "## H2\\n내용\\n\\n## 자주 묻는 질문\\n### 질문\\n답변"}'

    h2s = [{"title": "H2", "bullets": ["내용"]}]
    draft = pass2_expand("키워드", h2s, "info", False, runner=fake_run)
    assert draft["title"] == "제목"
    assert "자주 묻는 질문" in draft["body"]


def test_generate_two_pass_retries_on_fail():
    calls = []

    def fake_runner(prompt, timeout=90):
        calls.append(prompt[:5])  # pass1('키워드') vs pass2('키워드') 구분용
        is_pass2 = "골격을 확장" in prompt
        if not is_pass2:
            return '{"h2s": [{"title": "H2", "bullets": ["b"]}]}'
        if len([c for c in calls if "골격을 확장" in c]) == 1:
            return '{"title": "' + "가" * 40 + '", "first_paragraph": "즉답", "body": "본문"}'
        return ('{"title": "좋은 제목", '
                '"first_paragraph": "즉답입니다 키워드 추천 기준은 용량과 조리 방식입니다 30자 이상", '
                '"body": "## H2\\n키워드 본문 내용입니다 키워드를 활용합니다.\\n\\n'
                '| a | b |\\n| --- | --- |\\n| 1 | 2 |\\n\\n'
                '## 자주 묻는 질문\\n### 질문\\n답변"}')

    draft, failed = generate_two_pass("키워드", {}, runner=fake_runner)
    assert failed == []  # 재시도로 검수 통과
    assert draft["title"] == "좋은 제목"


def test_density_bounds_are_sane():
    assert 0 < KEYWORD_DENSITY_MIN < KEYWORD_DENSITY_MAX
