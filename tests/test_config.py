# tests/test_config.py
from datetime import date

import config


def test_load_config_with_defaults(monkeypatch):
    for key in (
        "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "DATABASE_URL",
        "DAILY_NEW_KEYWORD_CAP", "ACTIVE_KEYWORD_CAP", "AUTOCOMPLETE_URL",
        "AUTOCOMPLETE_MAX_DEPTH", "AUTOCOMPLETE_MAX_REQUESTS",
        "MANUAL_BUDGET_SECONDS", "DASHBOARD_TOKEN", "DATALAB_ENABLED",
        "DATALAB_ANCHOR", "ENV", "RUN_LOCK_STALE_MINUTES",
    ):
        monkeypatch.delenv(key, raising=False)
    cfg = config.load_config(load_env=False)
    assert cfg["db_url"] == "sqlite:///data/keywords.db"
    assert cfg["daily_new_keyword_cap"] == 100
    assert cfg["active_keyword_cap"] == 1000
    assert cfg["autocomplete_max_depth"] == 2
    assert cfg["autocomplete_max_requests"] == 300
    assert cfg["manual_budget_seconds"] == 45
    assert cfg["dashboard_token"] == ""
    assert cfg["datalab_enabled"] is True
    assert cfg["datalab_anchor"] == "냉장고"
    assert cfg["env"] == "development"          # v3: fail-closed 분기용
    assert cfg["run_lock_stale_minutes"] == 60  # v3: GH Actions timeout 정합


def test_load_config_with_env(monkeypatch):
    monkeypatch.setenv("NAVER_CLIENT_ID", "cid")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "csec")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/db")
    monkeypatch.setenv("DAILY_NEW_KEYWORD_CAP", "50")
    monkeypatch.setenv("ACTIVE_KEYWORD_CAP", "500")
    monkeypatch.setenv("DASHBOARD_TOKEN", "sekret")
    monkeypatch.setenv("DATALAB_ENABLED", "0")
    cfg = config.load_config(load_env=False)
    assert cfg["client_id"] == "cid"
    assert cfg["client_secret"] == "csec"
    assert cfg["db_url"] == "postgresql://u:p@localhost:5432/db"
    assert cfg["daily_new_keyword_cap"] == 50
    assert cfg["active_keyword_cap"] == 500
    assert cfg["dashboard_token"] == "sekret"
    assert cfg["datalab_enabled"] is False


def test_load_config_env_and_stale(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("RUN_LOCK_STALE_MINUTES", "45")
    cfg = config.load_config(load_env=False)
    assert cfg["env"] == "production"
    assert cfg["run_lock_stale_minutes"] == 45


def test_kst_helpers():
    # 러너/서버리스는 UTC — 날짜 키는 반드시 KST 헬퍼로만 생성 (스펙 §3)
    assert isinstance(config.today_kst(), date)
    now = config.now_kst_iso()
    assert now.endswith("+09:00")
    earlier = config.minutes_ago_kst_iso(30)
    assert earlier < now
