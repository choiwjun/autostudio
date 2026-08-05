# scoring.py
import math

import config as config_mod

COMPETITION_SATURATION_TOTAL = 10_000  # 1만 글이면 경쟁 포화 (스펙 §4.5)
GROWTH_NORM_MAX = 0.05                 # 일 5% 증가에서 성장 만점 (변별력 확보)

# v9: config.DEFAULT_CPC_TIERS를 단일 소스로 사용 — 중복 딕셔너리는 드리프트 발생
#     (scoring.py에 '요리' 누락 사례). cpc_tier_score는 테스트·참조용이며
#     실제 priority는 db.CPC_TIER_SQL(SQL)이 사용 — 두 곳을 동일 값으로 유지할 것.
DEFAULT_CPC_TIERS = config_mod.DEFAULT_CPC_TIERS

# --- v6: AI 인용 가능성 신호 ---
# AI 브리핑은 정보형·질문형 검색에서 활성화되고 과정형 카테고리에서 본문 인용 비율이
# 높음 (리서치: 인용글 786개 분석). 질문형 패턴은 인용 후보 문장 구조의 간접 신호.

QUESTION_PATTERNS = (
    "방법", "비교", "추천", "차이", "원인", "이유", "정의", "vs", "순위",
    "장단점", "하는 법", "하는법", "준비", "팁", "가이드", "사용법",
    "효과", "후기", "비용", "기준", "조건", "절차", "과정", "해결", "대처",
)

# 과정형(본문 인용 유리) vs 결과물형(이미지 인용만) 카테고리 가중
CATEGORY_AI_WEIGHT = {
    "여행": 1.0, "레시피": 1.0, "요리": 1.0, "반려동물": 1.0, "육아": 0.9,
    "IT": 0.9, "디지털": 0.9, "건강": 0.9, "금융": 0.9, "보험": 0.9,
    "재테크": 0.9, "교육": 0.9, "자격증": 0.9, "부동산": 0.9, "법률": 0.9,
    "인테리어": 0.4, "전시": 0.4, "패션": 0.4, "뷰티": 0.5,
}
DEFAULT_AI_WEIGHT = 0.7


def question_pattern_score(keyword):
    k = (keyword or "").lower().replace(" ", "")
    return 1.0 if any(p in k for p in QUESTION_PATTERNS) else 0.0


def ai_citation_score(keyword, fresh_ratio, category=""):
    """0.5×질문형 + 0.3×최신성 + 0.2×과정형가중 (0~1)."""
    q = question_pattern_score(keyword)
    cat_w = CATEGORY_AI_WEIGHT.get(category, DEFAULT_AI_WEIGHT)
    return round(0.5 * q + 0.3 * max(0.0, min(1.0, fresh_ratio)) + 0.2 * cat_w, 3)


def cpc_tier_score(category, tiers=None):
    """애드포스트 단가 등급 (0~1). tiers 미지정 시 DEFAULT_CPC_TIERS 사용."""
    tiers = tiers or DEFAULT_CPC_TIERS
    return tiers.get(category, tiers.get("", 0.5))


# v12: demand_idx는 앵커('냉장고') 대비 상대비율 — 실측 0~0.01 분포 (v9 현실화).
#      이 상한을 기준으로 0~1 정규화해 v6 가중치(0.35)가 실제로 priority에 반영되도록 함.
DEMAND_NORM_MAX = 0.01


def v6_priority(ai_cite, demand, cpc):
    """0.35×AI인용 + 0.35×조회수잠재력(demand/0.01, ≤1) + 0.30×CPC (0~100)."""
    ai = max(0.0, min(1.0, ai_cite or 0.0))
    dm = max(0.0, min(1.0, (demand or 0.0) / DEMAND_NORM_MAX))
    cp = max(0.0, min(1.0, cpc or 0.0))
    return round(35.0 * ai + 35.0 * dm + 30.0 * cp, 1)


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
