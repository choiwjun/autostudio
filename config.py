# config.py
import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

# KST는 DST가 없으므로 고정 오프셋 사용 (tzdata 의존성 불필요, Windows 포함 동일 동작)
KST = timezone(timedelta(hours=9))

# v6: 집중 발굴 기본 시드 — 애드포스트 1차 목표 기준. 고CPC(RPM 상위) × AI 인용 유망
# (정보형·질문형) 카테고리로 한정. 시드가 비어 있으면 collect가 이 목록으로 자동 초기화.
# (리서치: 금융/보험 RPM 800~1,000, IT 500~700 — 일상/취미 200~400 대비 우위)
# v8: 카테고리 확장 — 기존 5개에 재테크·부동산·법률·의료·자격증·디지털 추가 (CPC 0.8~1.0)
DEFAULT_FOCUS_SEEDS = [
    ("보험 비교 방법", "보험"),
    ("실비보험 추천", "보험"),
    ("암보험 가입 전 확인", "보험"),
    ("재테크 방법", "금융"),
    ("연말정산 환급 방법", "금융"),
    ("주식 초보 시작 방법", "재테크"),
    ("ISA 계좌 개설 조건", "재테크"),
    ("청약 당첨 후 절차", "부동산"),
    ("전세 계약 시 확인 사항", "부동산"),
    ("상속세 신고 방법", "법률"),
    ("양도소득세 계산 방법", "법률"),
    ("건강 관리 방법", "건강"),
    ("다이어트 식단 추천", "건강"),
    ("건강검진 항목 추천", "의료"),
    ("실손의료보험 청구 방법", "의료"),
    ("노트북 추천 비교", "IT"),
    ("AI 활용 방법", "IT"),
    ("생성형 AI 도구 추천", "디지털"),
    ("홈페이지 제작 방법", "디지털"),
    ("자격증 준비 방법", "교육"),
    ("공부법 추천", "교육"),
    ("정보처리기사 준비 기간", "자격증"),
    ("요양보호사 자격증 조건", "자격증"),
]

# v6: 애드포스트 CPC 등급 (카테고리 → 0~1) — scoring.cpc_tier_score가 사용
DEFAULT_CPC_TIERS = {
    "보험": 1.0, "금융": 1.0, "재테크": 1.0, "부동산": 0.9, "법률": 0.9,
    "건강": 0.9, "의료": 0.9, "IT": 0.8, "디지털": 0.8, "교육": 0.8,
    "자격증": 0.8, "여행": 0.4, "맛집": 0.4, "반려동물": 0.3,
    "일상": 0.3, "취미": 0.3, "인테리어": 0.5, "패션": 0.5, "뷰티": 0.5,
    "요리": 0.5,
}

# v8: 무카테고리 키워드 자동 분류 — 시드 카테고리 상속 실패 시 패턴으로 분류.
# 키워드에 포함된 단어 → 카테고리. 앞 항목 우선 (첫 매치 사용).
# v14: 실측 무카테고리 유입(맛집·여행·반려동물 계열) 규칙 증분 — 새 규칙은
# 오탐이 없는 고신뢰 토큰만 추가하고, 매치 실패는 FALLBACK_CATEGORY('기타')로 수렴.
DEFAULT_KEYWORD_CATEGORY_RULES = [
    ("에어프라이어", "요리"),
    ("에어프라이", "요리"),
    ("레시피", "요리"),
    ("요리", "요리"),
    ("반찬", "요리"),
    ("김치", "요리"),
    ("다이어트", "건강"),
    ("운동", "건강"),
    ("보험", "보험"),
    ("보험료", "보험"),
    ("대출", "금융"),
    ("적금", "금융"),
    ("예금", "금융"),
    ("주식", "재테크"),
    ("펀드", "재테크"),
    ("ISA", "재테크"),
    ("청약", "부동산"),
    ("전세", "부동산"),
    ("월세", "부동산"),
    ("아파트", "부동산"),
    ("상속", "법률"),
    ("세금", "법률"),
    ("양도소득세", "법률"),
    ("병원", "의료"),
    ("검진", "의료"),
    ("암", "의료"),
    ("노트북", "IT"),
    ("컴퓨터", "IT"),
    ("AI", "IT"),
    ("자격증", "자격증"),
    ("기사", "자격증"),
    # v14 증분
    ("맛집", "맛집"),
    ("카페", "맛집"),
    ("여행", "여행"),
    ("캠핑", "취미"),
    ("강아지", "반려동물"),
    ("고양이", "반려동물"),
    ("반려", "반려동물"),
]

# v14 §2: 시드 상속·규칙 매치 모두 실패한 키워드의 카테고리 — 빈 문자열이면
# 카테고리 필터에서 누락되고 CPC 등급도 ELSE 기본값에 머무르던 문제를 "기타"로 수렴.
# (CPC_TIER_SQL의 ELSE 0.5는 그대로 적용 — 의도된 동작)
FALLBACK_CATEGORY = "기타"


def today_kst():
    return datetime.now(KST).date()


def now_kst_iso():
    return datetime.now(KST).isoformat(timespec="seconds")


def minutes_ago_kst_iso(minutes):
    return (datetime.now(KST) - timedelta(minutes=minutes)).isoformat(timespec="seconds")


def load_config(load_env=True):
    if load_env:
        load_dotenv()          # .env (있으면)
        load_dotenv(".env.local")  # 로컬 시크릿 (gitignore 대상, 우선 순위는 .env가 높음)
    # v15: env 소문자 정규화 — 'Production' 변형이 fail-closed를 우회하던 문제 차단
    env = os.getenv("ENV", "development").strip().lower()
    # v15: DATABASE_URL fail-closed — 비개발 환경에서 미설정 시 sqlite로 조용히
    # 폴백되면 서버리스/GH Actions에서 데이터가 무소음 유실됨. 개발만 로컬 sqlite 허용.
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        if env != "development":
            raise RuntimeError(
                "DATABASE_URL required when ENV is not 'development' (fail-closed)")
        db_url = "sqlite:///data/keywords.db"
    return {
        "client_id": os.getenv("NAVER_CLIENT_ID", ""),
        "client_secret": os.getenv("NAVER_CLIENT_SECRET", ""),
        "db_url": db_url,
        # 0 = 일일 신규 제한 없음. ACTIVE_KEYWORD_CAP은 별도 안전 상한.
        "daily_new_keyword_cap": int(os.getenv("DAILY_NEW_KEYWORD_CAP", "0")),
        "active_keyword_cap": int(os.getenv("ACTIVE_KEYWORD_CAP", "500")),
        "autocomplete_url": os.getenv(
            "AUTOCOMPLETE_URL", "https://ac.search.naver.com/nx/ac"
        ),
        "autocomplete_max_depth": int(os.getenv("AUTOCOMPLETE_MAX_DEPTH", "2")),
        "autocomplete_max_requests": int(os.getenv("AUTOCOMPLETE_MAX_REQUESTS", "300")),
        "manual_budget_seconds": int(os.getenv("MANUAL_BUDGET_SECONDS", "45")),
        "dashboard_token": os.getenv("DASHBOARD_TOKEN", ""),
        "datalab_enabled": os.getenv("DATALAB_ENABLED", "1") == "1",
        "datalab_anchor": os.getenv("DATALAB_ANCHOR", "냉장고"),
        "shopping_insight_category": os.getenv("SHOPPING_INSIGHT_CATEGORY", "50000000"),
        "env": env,  # v15: 소문자 정규화값
        "run_lock_stale_minutes": int(os.getenv("RUN_LOCK_STALE_MINUTES", "60")),
        # v6: 시드 비어 있을 때 자동 초기화용 집중 시드 + 애드포스트 CPC 등급
        # v8: 무카테고리 키워드 자동 분류 규칙 (시드 상속 실패 시 폴백)
        "default_focus_seeds": DEFAULT_FOCUS_SEEDS,
        "cpc_tiers": DEFAULT_CPC_TIERS,
        "keyword_category_rules": DEFAULT_KEYWORD_CATEGORY_RULES,
    }
