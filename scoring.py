# scoring.py
import math

COMPETITION_SATURATION_TOTAL = 10_000  # 1만 글이면 경쟁 포화 (스펙 §4.5)
GROWTH_NORM_MAX = 0.05                 # 일 5% 증가에서 성장 만점 (변별력 확보)


def growth_rate(prev_total, curr_total):
    if prev_total == 0:
        return 1.0 if curr_total > 0 else 0.0
    return (curr_total - prev_total) / prev_total


def competition(total):
    if total <= 0:
        return 0.0
    return min(1.0, math.log10(total) / math.log10(COMPETITION_SATURATION_TOTAL))


def opportunity_score(fresh_ratio, growth, total):
    growth_norm = max(0.0, min(1.0, growth / GROWTH_NORM_MAX))
    return round(
        40.0 * fresh_ratio
        + 30.0 * growth_norm
        + 30.0 * (1.0 - competition(total)),
        1,
    )


def commercial_score(shop_total, avg_price):
    if shop_total <= 0:
        return 0.0
    return round(
        60.0 * min(shop_total / 500.0, 1.0)
        + 40.0 * min(avg_price / 30000.0, 1.0),
        1,
    )
