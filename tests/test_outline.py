# tests/test_outline.py
from outline import build_outline_structure, extract_outline


def test_extract_questions_from_descriptions():
    descs = [
        "에어프라이어 추천 <b>어떤 제품</b>이 좋을까요?",
        "가성비 좋은 에어프라이어 비교",
        "에어프라이어 1년 사용 후기",
    ]
    out = extract_outline(descs)
    assert any("어떤 제품" in q for q in out["questions"])
    assert any("비교" in c for c in out["comparisons"])
    assert any("1년" in f for f in out["facts"])


def test_extract_ignores_short_and_html():
    descs = ["짧음", "<b></b>", ""]
    out = extract_outline(descs)
    assert out["questions"] == []
    assert out["comparisons"] == []
    assert out["facts"] == []


def test_headings_capped_at_six():
    descs = [f"질문 {i} 어떻게 하죠? 상세 설명" for i in range(10)]
    out = extract_outline(descs)
    assert len(out["headings"]) <= 6


def test_build_outline_structure_is_json():
    descs = ["어떻게 고르나요? 추천 방법"]
    s = build_outline_structure(descs)
    import json
    parsed = json.loads(s)
    assert "questions" in parsed
    assert "headings" in parsed
