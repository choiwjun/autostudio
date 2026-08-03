# tests/test_scoring.py
from scoring import commercial_score, competition, growth_rate, opportunity_score


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
