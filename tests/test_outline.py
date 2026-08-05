# tests/test_outline.py
from outline import QUESTION_MAX_LEN, build_outline_structure, extract_outline


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


# ---------- v11: 문장 분리 기반 추출 ----------

def test_long_promo_snippet_split_into_sentences():
    # 100자+ 홍보 스니펫에 질문 마커가 있어도 — 문장 단위로만 추출.
    # 스니펫 전체(홍보 문단)가 questions로 들어가면 안 된다.
    descs = ["그래서 보험을 처음 알아볼 때도 실비보험 추천 검색이 꾸준히 이어지는 것으로 보였습니다. "
             "실비보험 구조는 어떻게 이해해야 할까? 처음에는 보험이 어렵게 느껴집니다."]
    out = extract_outline(descs)
    assert all(len(q) <= QUESTION_MAX_LEN for q in out["questions"])
    assert any("어떻게 이해해야" in q for q in out["questions"])
    # 홍보 서두 문장은 질문으로 안 들어감
    assert not any("보였습니다" in q for q in out["questions"])


def test_question_longer_than_cap_excluded():
    # 문장 분리 기호가 없는 단일 긴 문장 — 질문 마커가 있어도 길이 상한으로 제외
    long_q = "이 문장은 매우 길어서 소제목으로 쓸 수 없는 수준인지 궁금한 내용 " * 3
    out = extract_outline([long_q])
    assert out["questions"] == []


def test_sentence_classified_independently():
    # 한 문장이 질문+비교+수치면 세 목록에 모두 포함 (elif 체인 아님)
    sent = "1만원짜리 A와 B 중 어떤 게 나을까요?"
    out = extract_outline([sent])
    assert sent in out["questions"]
    assert sent in out["comparisons"]
    assert sent in out["facts"]


def test_hashtag_stripped_before_split():
    descs = ["실비보험 비교는 어떻게 하나요? #실비보험 #보험추천"]
    out = extract_outline(descs)
    assert any("어떻게 하나요?" in q for q in out["questions"])
    assert not any("#" in q for q in out["questions"])
