# tests/test_scoring.py
from scoring import (
    ai_citation_score, commercial_score, competition, cpc_tier_score,
    growth_rate, opportunity_score, question_pattern_score, v6_priority,
)


def test_growth_rate():
    assert growth_rate(100, 105) == 0.05
    assert growth_rate(100, 50) == -0.5
    assert growth_rate(100, 100) == 0.0
    assert growth_rate(0, 100) == 1.0
    assert growth_rate(100, 0) == -1.0


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


def test_commercial_score():
    assert commercial_score(0, 0) == 0.0
    assert commercial_score(500, 30000) == 100.0
    assert commercial_score(250, 15000) == 50.0
    # 60×(10/500) + 40×(1000/30000) = 1.2 + 1.33… → 2.5 (v1 계획의 기대값 10은 오류)
    assert commercial_score(10, 1000) == 2.5


# ---------- v6: AI 인용 가능성 + 애드포스트 CPC ----------

def test_question_pattern_score():
    assert question_pattern_score("보험 비교 방법") == 1.0
    assert question_pattern_score("노트북 추천") == 1.0
    assert question_pattern_score("자격증 준비") == 1.0
    assert question_pattern_score("에어프라이어") == 0.0  # 질문형 패턴 없음
    assert question_pattern_score("") == 0.0


def test_ai_citation_score_formula():
    # 0.5×질문형 + 0.3×fresh + 0.2×카테고리가중 (보험 가중 0.9)
    assert ai_citation_score("보험 비교 방법", 1.0, "보험") == 0.98   # 0.5+0.3+0.18
    assert ai_citation_score("보험 비교 방법", 0.0, "보험") == 0.68   # 0.5+0.0+0.18
    assert ai_citation_score("에어프라이어", 0.5, "가전") == 0.29    # 0+0.15+0.14
    # 과정형(여행 1.0) vs 결과물형(인테리어 0.4) 카테고리 가중 차이
    assert ai_citation_score("여행 코스 추천", 0.5, "여행") > ai_citation_score(
        "여행 코스 추천", 0.5, "인테리어")


def test_cpc_tier_defaults():
    assert cpc_tier_score("보험") == 1.0
    assert cpc_tier_score("금융") == 1.0
    assert cpc_tier_score("IT") == 0.8
    assert cpc_tier_score("일상") == 0.3
    assert cpc_tier_score("미분류") == 0.5  # 기본값
    assert cpc_tier_score("보험", {"보험": 0.9}) == 0.9  # tiers 오버라이드


def test_v6_priority_bounds():
    # 0.35×ai + 0.35×demand(0.01 기준 정규화) + 0.30×cpc
    assert v6_priority(1.0, 1.0, 1.0) == 100.0
    assert v6_priority(0.0, 0.0, 0.0) == 0.0
    assert v6_priority(None, None, None) == 0.0  # NULL 보호
    assert v6_priority(1.0, 5.0, 1.0) == 100.0   # demand 상한(0.01) 초과는 1로 클램프


def test_v6_priority_demand_normalized_v12():
    # v12: v9 실측 demand(앵커 대비 0~0.01) 기준 정규화 — 기존 ≤1 클램프는 demand 항 무력화
    assert v6_priority(1.0, 0.01, 1.0) == 100.0       # 실측 상한 = 만점
    assert v6_priority(1.0, 0.005, 1.0) == 82.5       # 35×1 + 35×0.5 + 30×1
    assert v6_priority(1.0, 0.001, 1.0) == 68.5       # 35×1 + 35×0.1 + 30×1
    assert v6_priority(1.0, 0.0, 1.0) == 65.0
