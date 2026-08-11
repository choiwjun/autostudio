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
    # E-5: 실측 기준점 2026-08-11 10:30 (engine.db 계산으로 고정) —
    # 10간 중 하나인지만 보던 항진성 단언을 실제 기대값으로 교체
    result = get_ganji(2026, 8, 11, 10, 30)
    assert result["day"]["ganji"] == "丁巳"
    assert result["hour"]["ganji"] == "乙巳"
    assert result["year"]["ganji"] == "丙午"
    assert result["month"]["ganji"] == "丙申"
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


# ---------- v22.2(1.5-선행): 한국 법정시간 (korean-legal-time 포팅 검증) ----------

from engine.calendar import (  # noqa: E402
    AmbiguousCivilTimeError, ManseryeokPolicyError, NonexistentCivilTimeError,
    resolve_korean_legal_time,
)

POLICY_FIXTURE = os.path.join(
    MYUNGLAB_ROOT, "tests", "fixtures", "manseryeok-policy-cases.json")


@pytest.fixture(scope="module")
def legal_time_cases():
    if not os.path.exists(POLICY_FIXTURE):
        pytest.skip("myunglab policy fixture 없음")
    with open(POLICY_FIXTURE, encoding="utf-8") as f:
        return json.load(f)["legalTimeCases"]


def _to_parts(s, add_minutes=0):
    y, m, d = map(int, s.split("-"))
    parts = {"year": y, "month": m, "day": d,
             "hour": 0, "minute": 0, "second": 0}
    if add_minutes:
        from engine.calendar import _shift_utc
        shifted = _shift_utc(parts, add_minutes)
        return shifted
    return parts


def test_legal_time_matches_policy_cases(legal_time_cases):
    # myunglab manseryeok-policy-cases.json — 법정시간 케이스 재사용
    # DST 케이스는 sampleDate, 구간 케이스는 from (전환일 00:00은 경계 라벨 —
    # 1954/1961 전환은 +30분 직후 시각으로 검증)
    checked = 0
    for case in legal_time_cases:
        if "sampleDate" in case:
            date = _to_parts(case["sampleDate"])
        elif "dateRange" in case:
            add = 30 if case["dateRange"]["from"] in (
                "1954-03-21", "1961-08-10") else 0
            date = _to_parts(case["dateRange"]["from"], add)
        else:
            continue
        result = resolve_korean_legal_time(date)
        assert result["standard_offset_minutes"] == case["legalOffsetMinutes"], case["id"]
        assert result["daylight_offset_minutes"] == case.get("dstOffsetMinutes", 0), case["id"]
        assert result["total_offset_minutes"] == case["effectiveOffsetMinutes"], case["id"]
        assert result["standard_meridian_degrees"] == case["legalOffsetMinutes"] / 4
        checked += 1
    assert checked >= 5  # 최소 5케이스 이상 실행


def test_legal_time_pre_1908_raises():
    with pytest.raises(ManseryeokPolicyError):
        resolve_korean_legal_time(
            {"year": 1900, "month": 1, "day": 1, "hour": 0, "minute": 0, "second": 0})


def test_legal_time_transition_labels():
    # 1954-03-21 00:00~00:30 — 반복(모호) 라벨
    with pytest.raises(AmbiguousCivilTimeError):
        resolve_korean_legal_time(
            {"year": 1954, "month": 3, "day": 21, "hour": 0, "minute": 10, "second": 0})
    # 1961-08-10 00:00~00:30 — 스킵(부재) 라벨
    with pytest.raises(NonexistentCivilTimeError):
        resolve_korean_legal_time(
            {"year": 1961, "month": 8, "day": 10, "hour": 0, "minute": 10, "second": 0})
    # 전환 직후 00:30 — 정상 해석 (표준 +9)
    result = resolve_korean_legal_time(
        {"year": 1961, "month": 8, "day": 10, "hour": 0, "minute": 30, "second": 0})
    assert result["total_offset_minutes"] == 540


def test_legal_time_dst():
    # DST 기간(1957년 여름) — +1h 반영 / 비DST(1957년 겨울) — 표준만
    summer = resolve_korean_legal_time(
        {"year": 1957, "month": 6, "day": 1, "hour": 12, "minute": 0, "second": 0})
    assert summer["daylight_offset_minutes"] == 60
    assert summer["total_offset_minutes"] == 510 + 60
    winter = resolve_korean_legal_time(
        {"year": 1957, "month": 12, "day": 1, "hour": 12, "minute": 0, "second": 0})
    assert winter["daylight_offset_minutes"] == 0
    assert winter["total_offset_minutes"] == 510


def test_legal_time_modern_is_kst():
    # 1961-08-10 00:30 이후 +9 고정 (일운·월운 시나리오)
    result = resolve_korean_legal_time(
        {"year": 2026, "month": 8, "day": 11, "hour": 12, "minute": 0, "second": 0})
    assert result["total_offset_minutes"] == 540
    assert result["transition_status"] == "standard"


def test_ganji_legal_time_historical_smoke():
    # 과거 날짜(1957 DST 여름)에서 get_ganji가 legal time 반영 경로로 동작
    # (DST +1h → 벽시계 shift 후 기둥 계산 — 크래시 없이 4기둥 산출)
    summer = get_ganji(1957, 6, 1, 12, 0)
    winter = get_ganji(1957, 12, 1, 12, 0)
    assert summer["year"]["ganji"] == winter["year"]["ganji"]  # 같은 해 → 같은 년주
    assert all(p["ganji"] for p in (summer["day"], summer["hour"],
                                    winter["day"], winter["hour"]))
    # legal_time 비활성과 결과 일치 여부는 보장하지 않음 — 활성 경로 무결성만 확인
