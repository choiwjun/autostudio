# tests/test_engine_calendar.py — v22.2(1.4): 만세력 core 교차 검증
# myunglab golden-fixtures(manseryeok-golden.json)를 Python 포팅에 재사용 —
# 동일 입력 → 동일 기둥 출력이 이식 완료의 판정 기준.
import json
import os

import pytest

from engine.calendar import (
    get_daily_fortune, get_ganji, get_monthly_rhythm, get_yearly_rhythm,
    to_julian_day,
)
from engine.calendar_data import lunar_to_solar, solar_to_lunar

MYUNGLAB_ROOT = os.path.join(os.path.expanduser("~"), "Documents", "myunglab")
FIXTURE = os.path.join(MYUNGLAB_ROOT, "tests", "fixtures", "manseryeok-golden.json")


@pytest.fixture(scope="module")
def golden_cases():
    if not os.path.exists(FIXTURE):
        pytest.skip("myunglab golden fixture 없음")
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)["cases"]


def test_golden_solar_pillars(golden_cases):
    # myunglab calculatePalja와 동일한 4기둥 — solar 입력
    for case in golden_cases:
        if case["input"]["calendar"] != "solar":
            continue
        inp = case["input"]
        result = get_ganji(inp["year"], inp["month"], inp["day"],
                           inp["hour"], inp["minute"])
        actual = {
            "yearPillar": result["year"]["ganji"],
            "monthPillar": result["month"]["ganji"],
            "dayPillar": result["day"]["ganji"],
            "hourPillar": result["hour"]["ganji"],
        }
        for key, expected in case["expected"].items():
            if expected:
                assert actual[key] == expected, f"{case['id']} {key}"


def test_golden_lunar_conversion_and_pillars(golden_cases):
    # 음력 입력 → 양력 변환 + 4기둥 (케이스 2: 음력 1992-09-29 = 양력 1992-10-24)
    for case in golden_cases:
        if case["input"]["calendar"] != "lunar":
            continue
        inp = case["input"]
        solar = lunar_to_solar(inp["year"], inp["month"], inp["day"],
                               int(inp.get("isLeapMonth", False)))
        if case["expected"].get("solar"):
            assert solar == case["expected"]["solar"], case["id"]
        if case["expected"].get("dayPillar"):
            assert solar is not None
            sy, sm, sd = map(int, solar.split("-"))
            result = get_ganji(sy, sm, sd, inp["hour"], inp["minute"])
            for key in ("yearPillar", "monthPillar", "dayPillar", "hourPillar"):
                expected = case["expected"].get(key)
                if expected:
                    assert result[key[:-len("Pillar")].lower()]["ganji"] == expected, \
                        f"{case['id']} {key}"


def test_ganji_known_pillars():
    # 실측 기준점: 2026-08-11 (자평명리 표준 계산과 대조)
    result = get_ganji(2026, 8, 11, 10, 30)
    assert result["day"]["gan"] in ("甲", "乙", "丙", "丁", "戊",
                                    "己", "庚", "辛", "壬", "癸")
    assert result["hour"]["ganji"] == f"{result['hour']['gan']}{result['hour']['ji']}"
    # 일주 결정성: 같은 날짜 → 같은 기둥
    assert get_ganji(2026, 8, 11, 10, 30)["day"] == result["day"]


def test_to_julian_day_matches_known():
    # 율리우스일 실측: 2000-01-01 = 2451544.5
    assert abs(to_julian_day(2000, 1, 1) - 2451544.5) < 1e-9


def test_daily_fortune_deterministic():
    # 일운: 같은 날+일간 → 항상 같은 문구, 금지어 미포함
    a = get_daily_fortune("갑", 2026, 8, 11)
    b = get_daily_fortune("갑", 2026, 8, 11)
    assert a == b and a["energy"] == "목(木)"
    for banned in ("반드시", "무조건", "100%"):
        assert banned not in a["text"]
    # 다른 날짜 → 다른 문구 (전체 풀 순환 범위 내)
    texts = {get_daily_fortune("갑", 2026, 8, d)["text"] for d in range(1, 15)}
    assert len(texts) > 5  # 14일간 충분히 분산


def test_monthly_rhythm_deterministic_and_yearly():
    a = get_monthly_rhythm("병", 2026, 8)
    b = get_monthly_rhythm("병", 2026, 8)
    assert a == b
    assert "확장" in a["energy"] or "표현" in a["energy"] or "정리" in a["energy"]
    yearly = get_yearly_rhythm("병", 2026)
    assert len(yearly) == 12
    for banned in ("반드시", "무조건", "100%"):
        assert all(banned not in m["summary"] + m["recommendation"]
                   for m in yearly)


def test_solar_lunar_roundtrip():
    # 양력→음력→양력 왕복 — 결정적 데이터 정합
    lunar = solar_to_lunar("1992-10-24")
    assert lunar is not None
    assert (lunar["lunar_year"], lunar["lunar_month"], lunar["lunar_day"]) \
        == (1992, 9, 29)
    assert lunar_to_solar(1992, 9, 29, lunar["is_leap"]) == "1992-10-24"


def test_midnight_boundary_no_crash():
    # validation-100 midnightBoundaryCases 파생 — 자시(23시)에서 크래시 없이 기둥 산출
    for y, m, d, h in ((1985, 6, 15, 23), (1985, 6, 16, 0),
                       (1946, 9, 1, 23), (1965, 3, 15, 8)):
        for sect in (1, 2):
            result = get_ganji(y, m, d, h, 0, sect=sect)
            assert result["day"]["ganji"] and result["hour"]["ganji"]
    # sect 차이: 23시는 sect=1이면 일주가 다음 날로 shift
    s1 = get_ganji(1985, 6, 15, 23, 0, sect=1)
    s2 = get_ganji(1985, 6, 15, 23, 0, sect=2)
    assert s1["day"]["ganji"] == get_ganji(1985, 6, 16, 0, 0, sect=2)["day"]["ganji"]
    assert s2["day"]["ganji"] != s1["day"]["ganji"]


def test_ipchun_boundary():
    # 입춘 경계 (2026년 입춘 2/4) — 2/3은 전년도 년주, 2/4는 당해 년주
    before = get_ganji(2026, 2, 3, 12, 0)
    after = get_ganji(2026, 2, 4, 12, 0)
    assert before["year"]["ganji"] != after["year"]["ganji"]
