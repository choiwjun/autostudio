# engine/calendar_data.py — v22.2(1.1): 만세력 데이터 조회 (SQLite)
# scripts/convert_engine_data.py가 생성한 data/engine.db를 읽는다.
# 1.2(간지·절기·음양력 계산)의 데이터 계층 — 결정적 조회만 담당.
import os
import sqlite3

DEFAULT_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "data", "engine.db")


class EngineDataError(Exception):
    pass


def _connect(db_path=None):
    path = db_path or os.getenv("ENGINE_DB_PATH", "") or DEFAULT_DB
    if not os.path.exists(path):
        raise EngineDataError(
            f"만세력 데이터가 없습니다: {path} — "
            "scripts/convert_engine_data.py 실행 필요")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def solar_to_lunar(solar_date, db_path=None):
    """양력 날짜('YYYY-MM-DD') → 음력 dict 또는 None.
    반환: {'lunar_year', 'lunar_month', 'lunar_day', 'is_leap'}"""
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT lunar_year, lunar_month, lunar_day, is_leap "
            "FROM engine_solar_lunar WHERE solar_date = ?",
            (solar_date,)).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def lunar_to_solar(lunar_year, lunar_month, lunar_day, is_leap=0, db_path=None):
    """음력(년/월/일/윤달) → 양력 날짜('YYYY-MM-DD') 또는 None."""
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT solar_date FROM engine_lunar_solar WHERE lunar_key = ?",
            (f"{lunar_year}-{lunar_month}-{lunar_day}-{is_leap}",)).fetchone()
    finally:
        conn.close()
    return row["solar_date"] if row else None


def get_solar_terms(year, db_path=None):
    """연도별 24절기 목록 — ordinal 순 (1=소한 ... 24=대설).
    반환: [{'ordinal','source_name','korean_name','month','day',
            'hour','minute','second','julian_day'}]"""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT ordinal, source_name, korean_name, month, day, hour, "
            "minute, second, julian_day FROM engine_solar_terms "
            "WHERE year = ? ORDER BY ordinal", (year,)).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]
