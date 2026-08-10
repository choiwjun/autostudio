# tests/test_fortune_extra.py — v22.2(1.3 확장): 운세 문구 확장 세트 검증
# 결정성·금지어(반드시/무조건/100%)·세트 완전성(20·12·12·60)
import pytest

from engine.day_pillar import DAY_PILLAR_PROFILES, day_pillar_profile
from engine.fortune_extra import (
    FIELD_PHRASES, LUCKY_ELEMENTS, ZODIAC_ANIMAL_PROFILES, ZODIAC_PROFILES,
    field_fortunes, lucky_elements, zodiac_animal_fortune, zodiac_fortune,
)

BANNED = ("반드시", "무조건", "100%")


def test_field_fortunes_complete_and_deterministic():
    # 오행×4분야 = 20세트 — 전부 문구 보유
    assert len(FIELD_PHRASES) == 20
    for gan in ("갑", "병", "무", "경", "임"):  # 목화토금수 대표
        f1 = field_fortunes(gan, 2026, 8, 11)
        f2 = field_fortunes(gan, 2026, 8, 11)
        assert f1 == f2  # 결정성
        assert set(f1.keys()) == {"재물", "애정", "건강", "일"}
        for text in f1.values():
            assert text
            assert all(b not in text for b in BANNED)
    # 다른 날짜 → 문구 분산 (같은 문구 반복 방지)
    texts = {field_fortunes("갑", 2026, 8, d)["재물"] for d in range(1, 10)}
    assert len(texts) > 1


def test_lucky_elements_mapping():
    assert len(LUCKY_ELEMENTS) == 5  # 오행 5종
    for gan, element in (("갑", "목"), ("병", "화"), ("무", "토"),
                         ("경", "금"), ("임", "수")):
        lucky = lucky_elements(gan)
        assert lucky["색"] and lucky["숫자"] and lucky["방위"]
    # 미등록 일간 → 목(木) 폴백
    assert lucky_elements("??") == lucky_elements("갑")


def test_zodiac_profiles_complete():
    assert len(ZODIAC_PROFILES) == 12
    assert len(ZODIAC_ANIMAL_PROFILES) == 12
    for name in ZODIAC_PROFILES:
        result = zodiac_fortune(name, 2026)
        assert result["profile"] and all(b not in result["profile"] for b in BANNED)
    for name in ZODIAC_ANIMAL_PROFILES:
        result = zodiac_animal_fortune(name, 2026)
        assert result["profile"] and all(b not in result["profile"] for b in BANNED)


def test_day_pillar_profiles_complete():
    assert len(DAY_PILLAR_PROFILES) == 60  # 갑자~계해 전부
    # 결정성 + 금지어 + 형식
    for pillar, (keyword, summary) in DAY_PILLAR_PROFILES.items():
        assert len(pillar) == 2
        assert keyword and summary
        assert all(b not in summary for b in BANNED)
        assert day_pillar_profile(pillar) == (keyword, summary)
    # 미등록 일주 → 빈 값 (무해)
    assert day_pillar_profile("??") == ("", "")


def test_ganji_day_pillar_link():
    # get_ganji 일주(한자) → day_pillar_profile 연결 (3.x 운세 글의 그라운딩 흐름)
    from engine.calendar import get_ganji
    from engine.day_pillar import to_hangul_pillar
    result = get_ganji(2026, 8, 11, 10, 30)
    pillar = result["day"]["ganji"]
    keyword, summary = day_pillar_profile(pillar)
    assert keyword and summary  # 60일주 전부 등록돼 있어야 함
    # 한자→한글 변환 확인
    assert to_hangul_pillar("丁巳") == "정사"
    assert to_hangul_pillar("갑자") == "갑자"
