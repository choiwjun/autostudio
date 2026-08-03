# config.py
import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

# KST는 DST가 없으므로 고정 오프셋 사용 (tzdata 의존성 불필요, Windows 포함 동일 동작)
KST = timezone(timedelta(hours=9))

# v6: 집중 발굴 기본 시드 — 애드포스트 1차 목표 기준. 고CPC(RPM 상위) × AI 인용 유망
# (정보형·질문형) 카테고리로 한정. 시드가 비어 있으면 collect가 이 목록으로 자동 초기화.
# (리서치: 금융/보험 RPM 800~1,000, IT 500~700 — 일상/취미 200~400 대비 우위)
DEFAULT_FOCUS_SEEDS = [
    ("보험 비교 방법", "보험"),
    ("실비보험 추천", "보험"),
    ("재테크 방법", "금융"),
    ("연말정산 환급 방법", "금융"),
    ("건강 관리 방법", "건강"),
    ("다이어트 식단 추천", "건강"),
    ("노트북 추천 비교", "IT"),
    ("AI 활용 방법", "IT"),
    ("자격증 준비 방법", "교육"),
    ("공부법 추천", "교육"),
]

# v6: 애드포스트 CPC 등급 (카테고리 → 0~1) — scoring.cpc_tier_score가 사용
DEFAULT_CPC_TIERS = {
    "보험": 1.0, "금융": 1.0, "재테크": 1.0, "부동산": 0.9, "법률": 0.9,
    "건강": 0.9, "의료": 0.9, "IT": 0.8, "디지털": 0.8, "교육": 0.8,
    "자격증": 0.8, "여행": 0.4, "맛집": 0.4, "반려동물": 0.3,
    "일상": 0.3, "취미": 0.3, "인테리어": 0.5, "패션": 0.5, "뷰티": 0.5,
}


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
    return {
        "client_id": os.getenv("NAVER_CLIENT_ID", ""),
        "client_secret": os.getenv("NAVER_CLIENT_SECRET", ""),
        "db_url": os.getenv("DATABASE_URL", "sqlite:///data/keywords.db"),
        # 0 = 일일 신규 제한 없음. ACTIVE_KEYWORD_CAP은 별도 안전 상한.
        "daily_new_keyword_cap": int(os.getenv("DAILY_NEW_KEYWORD_CAP", "0")),
        "active_keyword_cap": int(os.getenv("ACTIVE_KEYWORD_CAP", "200")),
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
        "env": os.getenv("ENV", "development"),
        "run_lock_stale_minutes": int(os.getenv("RUN_LOCK_STALE_MINUTES", "60")),
        # v6: 시드 비어 있을 때 자동 초기화용 집중 시드 + 애드포스트 CPC 등급
        "default_focus_seeds": DEFAULT_FOCUS_SEEDS,
        "cpc_tiers": DEFAULT_CPC_TIERS,
    }
