# tests/test_fortune_content.py — v22.2(3.1~3.2): 운세 콘텐츠 생성 검증
# 데이터 조립 결정성·프롬프트 구조·검수·DB 멱등
import json

import pytest

from engine.fortune_content import (
    EXPERT_TERMS, SNS_MAX_LEN, build_daily_grounding, build_blog_prompt,
    build_sns_prompt, check_banned_words, check_expert_terms,
    check_reference_date, check_sns_length, generate_blog_detail,
    generate_sns_summary, validate_content,
)


def test_build_daily_grounding_deterministic_and_complete():
    import config as config_mod
    from datetime import date
    today = config_mod.today_kst()
    g1 = build_daily_grounding(today)
    g2 = build_daily_grounding(today)
    assert g1 == g2  # 결정성
    assert g1["reference_date"] == today.isoformat()
    assert g1["energy"] and g1["fortune_text"]
    assert set(g1["fields"].keys()) == {"재물", "애정", "건강", "일"}
    assert all(v for v in g1["fields"].values())
    assert g1["lucky"]["색"] and g1["lucky"]["숫자"]
    assert g1["day_pillar_keyword"] and g1["day_pillar_summary"]  # 60일주 연결
    assert g1["month_rhythm_summary"]


def test_grounding_has_no_banned_words():
    g = build_daily_grounding()
    blob = json.dumps(g, ensure_ascii=False)
    assert check_banned_words(blob) == []
    assert check_expert_terms(blob) == []  # 그라운딩 자체도 전문용어 금지


def test_prompts_contain_grounding_and_rules():
    g = build_daily_grounding()
    sns = build_sns_prompt(g)
    assert "## 엔진 데이터" in sns and g["fortune_text"] in sns
    assert "500자" in sns and "블로그에서 확인하세요" in sns
    blog = build_blog_prompt(g)
    assert "분야별 상세" in blog and "전문용어" in blog
    assert g["reference_date"] in blog


def test_generate_with_fake_runner_and_validate():
    g = build_daily_grounding()

    def fake_sns(prompt, timeout=90):
        return json.dumps({"text": f"{g['reference_date']} 오늘의 운세 — "
                                   "미뤄둔 계획을 꺼내기 좋은 날입니다. "
                                   "창의력이 빛나는 하루예요. 재물운: 절약이 유리합니다. "
                                   "애정운: 대화가 잘 통합니다. 건강운: 산책이 도움이 됩니다. "
                                   "일운: 시작하기 좋습니다. 행운 색: 초록. "
                                   "더 자세한 오늘의 운세는 블로그에서 확인하세요",
                           "hashtags": ["운세", "오늘의운세"]}, ensure_ascii=False)

    sns = generate_sns_summary(g, runner=fake_sns)
    assert check_sns_length(sns["text"]) and check_reference_date(sns["text"], g["reference_date"])
    ok, fails = validate_content(sns, g["reference_date"], "sns")
    assert ok, fails

    def fake_blog(prompt, timeout=90):
        body = ("오늘의 운세를 알려드립니다. " * 60)  # 30자 × 60 = 1800자 이상
        return json.dumps({"title": f"{g['reference_date']} 오늘의 운세",
                           "summary": "미뤄둔 계획을 시작하기 좋은 날",
                           "body": body}, ensure_ascii=False)

    blog = generate_blog_detail(g, runner=fake_blog)
    ok2, fails2 = validate_content(blog, g["reference_date"], "blog")
    assert ok2, fails2


def test_validate_rejects_violations():
    g = build_daily_grounding()
    bad_sns = {"text": "반드시 운이 좋습니다. 오늘의 일간은 갑목입니다. " * 20}
    ok, fails = validate_content(bad_sns, g["reference_date"], "sns")
    assert not ok
    assert any("금지어" in f for f in fails)
    assert any("전문용어" in f for f in fails)
    assert any("길이 초과" in f for f in fails)
    assert any("기준일" in f for f in fails)


def test_expert_terms_cover_common():
    for term in ("일간", "십신", "간지", "오행", "용신"):
        assert term in EXPERT_TERMS


def test_fortune_generation_idempotent(tmp_path):
    import db
    d = db.Database(f"sqlite:///{tmp_path / 't.db'}")
    d.init()
    assert d.upsert_fortune_generation("2026-08-11", "daily_sns", "내용") is True
    assert d.upsert_fortune_generation("2026-08-11", "daily_sns", "내용2") is False
    assert d.get_fortune_generation("2026-08-11", "daily_sns")["content"] == "내용"
    rows = d.list_fortune_generations("2026-08-11")
    assert len(rows) == 1
    d.close()
