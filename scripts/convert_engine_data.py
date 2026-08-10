# scripts/convert_engine_data.py — v22.2(1.1): myunglab 만세력 데이터 → SQLite
# myunglab 생성 JSON(lunar-solar·solar-terms)을 engine 조회용 SQLite로 변환.
# - engine_solar_lunar: 양력 날짜 → 음력(년/월/일/윤달)
# - engine_lunar_solar: 음력 키(년-월-일-윤달) → 양력 날짜
# - engine_solar_terms: 연도별 24절기 (월/일/시/분/초 + 율리우스일)
# 멱등: 실행 시 테이블 재생성 후 재적재. 소스 경로는 인자/환경변수로 지정.
import json
import os
import sqlite3
import sys


def source_path(base):
    """myunglab core/data 디렉토리 — --data-dir 인자 > MYUNGLAB_ENGINE_DATA > 기본 경로."""
    if base:
        return base
    env = os.getenv("MYUNGLAB_ENGINE_DATA", "")
    if env:
        return env
    return os.path.join(
        os.path.expanduser("~"), "Documents", "myunglab",
        "src", "engine", "core", "data")


SCHEMA = """
CREATE TABLE engine_solar_lunar (
    solar_date TEXT PRIMARY KEY,   -- 양력 YYYY-MM-DD
    lunar_year INTEGER NOT NULL,
    lunar_month INTEGER NOT NULL,
    lunar_day INTEGER NOT NULL,
    is_leap INTEGER NOT NULL DEFAULT 0  -- 1 = 음력 윤달
);
CREATE TABLE engine_lunar_solar (
    lunar_key TEXT PRIMARY KEY,    -- '년-월-일-윤달' (1898-11-20-0)
    solar_date TEXT NOT NULL
);
CREATE TABLE engine_solar_terms (
    year INTEGER NOT NULL,
    ordinal INTEGER NOT NULL,      -- 1~24 (소한=1, 대설=24)
    source_name TEXT NOT NULL,     -- 한자명 (小寒...)
    korean_name TEXT NOT NULL,     -- 한글명
    month INTEGER NOT NULL,
    day INTEGER NOT NULL,
    hour INTEGER NOT NULL DEFAULT 0,
    minute INTEGER NOT NULL DEFAULT 0,
    second INTEGER NOT NULL DEFAULT 0,
    julian_day REAL NOT NULL,
    PRIMARY KEY (year, ordinal)
);
"""


def convert(json_dir, db_path):
    with open(os.path.join(json_dir, "lunar-solar.generated.json"),
              encoding="utf-8") as f:
        lunar_solar = json.load(f)
    with open(os.path.join(json_dir, "solar-terms.generated.json"),
              encoding="utf-8") as f:
        terms = json.load(f)

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript("DROP TABLE IF EXISTS engine_solar_lunar;"
                           "DROP TABLE IF EXISTS engine_lunar_solar;"
                           "DROP TABLE IF EXISTS engine_solar_terms;" + SCHEMA)
        s2l = lunar_solar["solarToLunar"]
        l2s = lunar_solar["lunarToSolar"]
        conn.executemany(
            "INSERT INTO engine_solar_lunar "
            "(solar_date, lunar_year, lunar_month, lunar_day, is_leap) "
            "VALUES (?, ?, ?, ?, ?)",
            [(d, v[0], v[1], v[2], v[3]) for d, v in s2l.items()])
        conn.executemany(
            "INSERT INTO engine_lunar_solar (lunar_key, solar_date) "
            "VALUES (?, ?)",
            [(k, f"{v[0]:04d}-{v[1]:02d}-{v[2]:02d}") for k, v in l2s.items()])
        rows = []
        for year, items in terms.items():
            for i, t in enumerate(items, 1):
                rows.append((int(t["year"]), i, t["sourceName"],
                             t["koreanName"], t["month"], t["day"],
                             t.get("hour", 0), t.get("minute", 0),
                             t.get("second", 0), t["julianDay"]))
        conn.executemany(
            "INSERT INTO engine_solar_terms (year, ordinal, source_name, "
            "korean_name, month, day, hour, minute, second, julian_day) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
        conn.commit()
        return {
            "solar_lunar": len(s2l), "lunar_solar": len(l2s),
            "solar_terms": len(rows),
        }
    finally:
        conn.close()


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    data_dir = source_path(next(
        (a for a in argv if not a.startswith("--")), None))
    db_path = "data/engine.db"
    os.makedirs("data", exist_ok=True)
    counts = convert(data_dir, db_path)
    print(f"변환 완료: {db_path} "
          f"(양력→음력 {counts['solar_lunar']:,} · "
          f"음력→양력 {counts['lunar_solar']:,} · "
          f"절기 {counts['solar_terms']:,})")


if __name__ == "__main__":
    main()
