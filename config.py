# config.py
import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

# KST는 DST가 없으므로 고정 오프셋 사용 (tzdata 의존성 불필요, Windows 포함 동일 동작)
KST = timezone(timedelta(hours=9))


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
    }
