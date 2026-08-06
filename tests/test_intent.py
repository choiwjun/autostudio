# tests/test_intent.py
from intent import Intent, classify


def test_purchase_intent():
    assert classify("에어프라이어 가격") == Intent.PURCHASE
    assert classify("실비보험 비용 비교") == Intent.PURCHASE  # 구매 신호 우선
    assert classify("노트북 후기") == Intent.PURCHASE
    assert classify("다이소 추천 살만한것") == Intent.PURCHASE


def test_compare_intent():
    assert classify("노트북 추천 비교") == Intent.COMPARE
    assert classify("실비보험 차이") == Intent.COMPARE
    assert classify("장단점 정리") == Intent.COMPARE


def test_compare_intent_vs_pattern():
    # v14: \b 경계 버그 회귀 방지 — 한글 인접·공백·대문자 모두 비교형으로
    assert classify("노트북vs맥북") == Intent.COMPARE
    assert classify("노트북 vs 맥북") == Intent.COMPARE
    assert classify("갤럭시 VS 아이폰") == Intent.COMPARE


def test_vs_inside_english_word_is_not_compare():
    # 영문 단어 내부의 'vs'(예: devs)는 비교 신호 아님 (정보형 기본)
    assert classify("devs 설정 방법") == Intent.INFO


def test_info_intent_default():
    assert classify("연말정산 환급 방법") == Intent.INFO
    assert classify("에어프라이어") == Intent.INFO
    assert classify("") == Intent.INFO
    assert classify(None) == Intent.INFO


def test_info_patterns_with_spaces():
    # 공백 유지 매칭 — '하는 법' 등 \s* 허용 패턴
    assert classify("청소 하는 법") == Intent.INFO
    assert classify("보험 추천 방법") == Intent.INFO


def test_daehaeseo_is_not_compare():
    # v15: '대해서'는 비교 신호가 아님 — "실비보험에 대해서"는 정보형
    assert classify("실비보험에 대해서") == Intent.INFO
    assert classify("연말정산에 대해서 알려주세요") == Intent.INFO
