from scoring import (
    ai_citation_score, competition, cpc_tier_score,
    growth_norm, growth_rate, opportunity_score, question_pattern_score,
    v6_priority,
)


def test_growth_rate():
    assert growth_rate(100, 105) == 0.05
    assert growth_rate(100, 50) == -0.5
    assert growth_rate(100, 100) == 0.0
    assert growth_rate(100, 0) == -1.0


def test_growth_rate_low_base_is_neutral():
    # v14: prev < 10이면 비율이 노이즈(0→100이 100% 성장) — 중립 0.0 반환
    assert growth_rate(0, 100) == 0.0
    assert growth_rate(5, 100) == 0.0
    assert growth_rate(9, 1000) == 0.0
    assert growth_rate(10, 15) == 0.5  # 기준 볼륨 이상은 정상 계산


def test_competition_saturates_at_10k():
    # 스펙 §4.5: 1만 글에서 경쟁 포화 (v1 계획의 10만 포화는 스펙 불일치였음)
    assert competition(1) == 0.0
    assert competition(100) == 0.5
    assert competition(10_000) == 1.0
    assert competition(1_000_000) == 1.0


def test_opportunity_bounds():
    # 기대값은 공식 검산 결과 (v1 계획은 검산 없이 100을 기대해 실제 88과 불일치)
    assert opportunity_score(1.0, 0.05, 1) == 100.0
    assert opportunity_score(0.0, 0.0, 10_000) == 0.0
    assert opportunity_score(0.0, -1.0, 10_000) == 0.0  # 음수 성장은 0으로 클램프


def test_opportunity_mid():
    # 40×0.5 + 30×(0.01/0.05) + 30×(1−log10(1000)/4) = 20 + 6 + 7.5
    assert opportunity_score(0.5, 0.01, 1000) == 33.5


# ---------- v6: AI 인용 가능성 + 애드포스트 CPC ----------

def test_question_pattern_score():
    assert question_pattern_score("보험 비교 방법") == 1.0
    assert question_pattern_score("노트북 추천") == 1.0
    assert question_pattern_score("자격증 준비") == 1.0
    assert question_pattern_score("에어프라이어") == 0.0  # 질문형 패턴 없음
    assert question_pattern_score("") == 0.0
    # v14: "하는 법"은 공백 제거 후 "하는법"으로 매칭 (패턴 목록은 무공백만 유지)
    assert question_pattern_score("청소 하는 법") == 1.0


def test_ai_citation_score_formula():
    # 0.5×질문형 + 0.3×fresh + 0.2×카테고리가중 (보험 가중 0.9)
    assert ai_citation_score("보험 비교 방법", 1.0, "보험") == 0.98   # 0.5+0.3+0.18
    assert ai_citation_score("보험 비교 방법", 0.0, "보험") == 0.68   # 0.5+0.0+0.18
    assert ai_citation_score("에어프라이어", 0.5, "가전") == 0.29    # 0+0.15+0.14
    # 과정형(여행 1.0) vs 결과물형(인테리어 0.4) 카테고리 가중 차이
    assert ai_citation_score("여행 코스 추천", 0.5, "여행") > ai_citation_score(
        "여행 코스 추천", 0.5, "인테리어")
    # v14: 의료(0.9)·맛집(0.4) 가중 추가 — CPC 티어와 정합
    assert ai_citation_score("검진 방법", 0.0, "의료") == 0.68   # 0.5+0+0.18
    assert ai_citation_score("맛집 추천", 0.0, "맛집") == 0.58   # 0.5+0+0.08


def test_cpc_tier_defaults():
    assert cpc_tier_score("보험") == 1.0
    assert cpc_tier_score("금융") == 1.0
    assert cpc_tier_score("IT") == 0.8
    assert cpc_tier_score("일상") == 0.3
    assert cpc_tier_score("미분류") == 0.5  # 기본값
    assert cpc_tier_score("보험", {"보험": 0.9}) == 0.9  # tiers 오버라이드


# ---------- v14: 성장 정규화 + priority 공식 ----------

def test_growth_norm():
    # v14 §4.1: clamp(growth / 0.05, -0.5, 1.0), None은 0 (미수집 중립)
    assert growth_norm(None) == 0.0
    assert growth_norm(0.0) == 0.0
    assert growth_norm(0.05) == 1.0    # 일 5% 성장 = 만점
    assert growth_norm(0.2) == 1.0     # 상한 클램프
    assert growth_norm(0.025) == 0.5
    assert growth_norm(-0.1) == -0.5   # 하한 클램프
    assert growth_norm(-0.025) == -0.5


def test_v6_priority_bounds():
    # v14: 30×ai + 25×demand(0.01 기준 정규화) + 15×growth + 30×cpc
    assert v6_priority(1.0, 1.0, 1.0, 0.05) == 100.0
    assert v6_priority(1.0, 1.0, 1.0) == 85.0          # growth None은 중립
    assert v6_priority(0.0, 0.0, 0.0) == 0.0
    assert v6_priority(None, None, None) == 0.0        # NULL 보호
    assert v6_priority(1.0, 5.0, 1.0, 0.05) == 100.0   # demand 상한(0.01) 초과는 1로 클램프


def test_v6_priority_demand_normalized_v12():
    # v12 정규화 유지 + v14 가중치(30/25/15/30)
    assert v6_priority(1.0, 0.01, 1.0) == 85.0         # 30×1 + 25×1 + 30×1
    assert v6_priority(1.0, 0.005, 1.0) == 72.5        # 30 + 12.5 + 30
    assert v6_priority(1.0, 0.001, 1.0) == 62.5        # 30 + 2.5 + 30
    assert v6_priority(1.0, 0.0, 1.0) == 60.0


def test_v6_priority_growth_term():
    # 상승 키워드 상향, 하락 키워드 하향 (성공 기준 ②)
    assert v6_priority(1.0, 0.0, 1.0, 0.2) == 75.0     # 60 + 15×1.0
    assert v6_priority(1.0, 0.0, 1.0, -0.2) == 52.5    # 60 + 15×(-0.5)
