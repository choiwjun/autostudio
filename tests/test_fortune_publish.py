# tests/test_fortune_publish.py — v22.3(2.x): 운세 발행 (3.3 — 매일 자동 + 재시도)
import json

import db
import publish_client
import pytest


def _open(tmp_path):
    d = db.Database(f"sqlite:///{tmp_path / 't.db'}")
    d.init()
    return d


def _cfg(tmp_path, enabled=True):
    return {"blog_api_url": "https://blog.example.com", "blog_token": "tok",
            "blog_publish_enabled": enabled,
            "fortune_fixed_per_day": 0,  # 고정 콘텐츠는 별도 테스트
            "db_url": f"sqlite:///{tmp_path / 't.db'}"}


def _blog_content(ref="2026-08-10"):
    return {"title": f"{ref} 오늘의 운세", "summary": "한줄 요약",
            "body": f"## 총평\n{ref} 기준 본문입니다."}


class _Resp:
    def __init__(self, status, text):
        self.status_code = status
        self.text = text if isinstance(text, str) else json.dumps(text)

    def json(self):
        return {"ok": True}


# ---------- publish_fortune ----------

def test_publish_fortune_success(monkeypatch, tmp_path):
    posted = {}

    def fake_post(url, json, headers, timeout):
        posted["url"] = url
        posted["payload"] = json
        posted["headers"] = headers
        return _Resp(200, {})

    monkeypatch.setattr(publish_client.requests, "post", fake_post)
    d = _open(tmp_path)
    d.upsert_fortune_generation("2026-08-10", "daily_blog", "", grounding="g")
    content = _blog_content()
    url = publish_client.publish_fortune(_cfg(tmp_path), d, "2026-08-10", content)
    assert url == "https://blog.example.com/fortune-2026-08-10"
    assert posted["payload"]["slug"] == "fortune-2026-08-10"
    assert posted["payload"]["category"] == "운세"
    assert posted["payload"]["engine_meta"] == {
        "fortune_type": "daily", "ref_date": "2026-08-10"}
    assert posted["payload"]["status"] == "published"
    assert posted["headers"]["Authorization"] == "Bearer tok"
    row = d.get_fortune_generation("2026-08-10", "daily_blog")
    assert row["status"] == "published"
    assert json.loads(row["content"])["title"] == content["title"]
    d.close()


def test_publish_fortune_requires_config(tmp_path):
    d = _open(tmp_path)
    d.upsert_fortune_generation("2026-08-10", "daily_blog", "", grounding="g")
    with pytest.raises(publish_client.BlogPublishError):
        publish_client.publish_fortune({}, d, "2026-08-10", _blog_content())
    assert d.get_fortune_generation("2026-08-10", "daily_blog")["status"] == "generated"
    d.close()


# ---------- collect.fortune_generate_step 발행 연결 ----------

def _patch_generators(monkeypatch):
    import engine.fortune_content as fc
    import llm_client

    monkeypatch.setattr(llm_client, "has_api_key", lambda: True)
    monkeypatch.setattr(fc, "generate_blog_detail",
                        lambda g, **kw: dict(_blog_content()))
    monkeypatch.setattr(fc, "generate_sns_summary",
                        lambda g, **kw: {"text": "오늘의 운세 요약",
                                         "hashtags": ["운세"]})


def test_fortune_step_publishes_on_success(monkeypatch, tmp_path):
    import collect

    _patch_generators(monkeypatch)
    posted = {}

    def fake_post(url, json, headers, timeout):
        posted["payload"] = json
        return _Resp(200, {})

    monkeypatch.setattr(publish_client.requests, "post", fake_post)
    d = _open(tmp_path)
    n = collect.fortune_generate_step(d, _cfg(tmp_path), "2026-08-10")
    assert n == 2  # SNS + 블로그 생성 (고정 콘텐츠는 별도 테스트)
    assert posted["payload"]["slug"] == "fortune-2026-08-10"
    row = d.get_fortune_generation("2026-08-10", "daily_blog")
    assert row["status"] == "published"
    d.close()


def test_fortune_step_skips_publish_when_disabled(monkeypatch, tmp_path):
    import collect

    _patch_generators(monkeypatch)
    d = _open(tmp_path)
    collect.fortune_generate_step(d, _cfg(tmp_path, enabled=False), "2026-08-10")
    row = d.get_fortune_generation("2026-08-10", "daily_blog")
    assert row["status"] == "generated"  # 발행 안 함 — 품질 리뷰 전
    d.close()


def test_fortune_publish_failed_retries_next_run(monkeypatch, tmp_path):
    import collect

    d = _open(tmp_path)
    d.upsert_fortune_generation("2026-08-10", "daily_blog",
                                json.dumps(_blog_content(), ensure_ascii=False),
                                grounding="g")
    d.update_fortune_generation("2026-08-10", "daily_blog",
                                json.dumps(_blog_content(), ensure_ascii=False),
                                status="publish_failed")
    calls = []

    def flaky(url, json, headers, timeout):
        calls.append(1)
        if len(calls) <= 4:  # 1차 실행: 재시도 3회 포함 전부 실패
            return _Resp(503, "boom")
        return _Resp(200, {})

    monkeypatch.setattr(publish_client.requests, "post", flaky)
    monkeypatch.setattr(publish_client.time, "sleep", lambda s: None)
    import llm_client
    monkeypatch.setattr(llm_client, "has_api_key", lambda: False)
    # 1차: 실패 → publish_failed 유지
    collect.fortune_generate_step(d, _cfg(tmp_path), "2026-08-10")
    assert d.get_fortune_generation("2026-08-10", "daily_blog")["status"] == \
        "publish_failed"
    # 2차 (다음 실행): 재시도 성공 → published
    collect.fortune_generate_step(d, _cfg(tmp_path), "2026-08-10")
    assert d.get_fortune_generation("2026-08-10", "daily_blog")["status"] == \
        "published"
    d.close()


def test_upsert_retries_empty_placeholder(tmp_path):
    # LLM 실패로 빈 content가 남은 행 — 다음 실행에서 재시도 허용 (멱등 블록 방지)
    d = _open(tmp_path)
    assert d.upsert_fortune_generation("2026-08-10", "daily_blog", "", grounding="g")
    assert d.upsert_fortune_generation("2026-08-10", "daily_blog", "", grounding="g")
    row = d.get_fortune_generation("2026-08-10", "daily_blog")
    assert row["content"] == ""
    # content 채워지면 멱등 스킵
    d.update_fortune_generation("2026-08-10", "daily_blog",
                                json.dumps(_blog_content(), ensure_ascii=False))
    assert not d.upsert_fortune_generation("2026-08-10", "daily_blog", "", grounding="g")
    d.close()


def test_upsert_retries_qc_failed(tmp_path):
    # E-1: QC 실패(status=qc_failed) 행은 content 존재해도 재시도 허용 —
    # content만으로 멱등 스킵하면 영구 결손. 재생성 성공(generated) 후엔 멱등.
    d = _open(tmp_path)
    d.upsert_fortune_generation("2026-08-10", "daily_blog",
                                json.dumps(_blog_content(), ensure_ascii=False),
                                grounding="g")
    d.update_fortune_generation("2026-08-10", "daily_blog",
                                json.dumps(_blog_content(), ensure_ascii=False),
                                status="qc_failed")
    assert d.upsert_fortune_generation("2026-08-10", "daily_blog", "",
                                       grounding="g2")
    row = d.get_fortune_generation("2026-08-10", "daily_blog")
    assert row["grounding"] == "g2"
    d.update_fortune_generation("2026-08-10", "daily_blog",
                                json.dumps(_blog_content(), ensure_ascii=False),
                                status="generated")
    assert not d.upsert_fortune_generation("2026-08-10", "daily_blog", "",
                                           grounding="g3")
    d.close()


def test_fortune_qc_failed_not_published(monkeypatch, tmp_path):
    import collect

    d = _open(tmp_path)
    d.upsert_fortune_generation("2026-08-10", "daily_blog",
                                json.dumps(_blog_content(), ensure_ascii=False),
                                grounding="g")
    d.update_fortune_generation("2026-08-10", "daily_blog",
                                json.dumps(_blog_content(), ensure_ascii=False),
                                status="qc_failed")
    import llm_client
    monkeypatch.setattr(llm_client, "has_api_key", lambda: False)
    collect.fortune_generate_step(d, _cfg(tmp_path), "2026-08-10")
    assert d.get_fortune_generation("2026-08-10", "daily_blog")["status"] == \
        "qc_failed"  # 수동 검토 대상 — 자동 발행 안 함
    d.close()


# ---------- 3.1 확장: 고정 콘텐츠·주간·월간 ----------

def test_fixed_content_generated_and_published(monkeypatch, tmp_path):
    import collect
    import llm_client
    from engine import fortune_content as fc

    monkeypatch.setattr(llm_client, "has_api_key", lambda: False)
    published = []

    def fake_post(url, json, headers, timeout):
        published.append(json["slug"])
        return _Resp(200, {})

    monkeypatch.setattr(publish_client.requests, "post", fake_post)
    cfg = _cfg(tmp_path)
    cfg["fortune_fixed_per_day"] = 3
    d = _open(tmp_path)
    n = collect.fortune_generate_step(d, cfg, "2026-08-10")
    assert n == 3  # 일주 1 + 별자리 1 + 띠 1 (순차 상한)
    # 결정적 생성 — LLM 키 없이도 동작
    assert d.get_fortune_generation("01", "day_pillar_blog")["status"] == "published"
    assert "fortune-day-pillar-01" in published
    assert "fortune-zodiac-01" in published
    assert "fortune-animal-01" in published
    # 멱등 — 같은 ref(01)는 재생성 없음 (quota가 남으면 02부터 순차 생성)
    n2 = collect.fortune_generate_step(d, cfg, "2026-08-10")
    rows = d.list_fortune_generations()
    ones = [r for r in rows if r["ref_date"] == "01"]
    assert len(ones) == 3  # 01 3타입 그대로 — 재생성 없음
    assert all(r["status"] == "published" for r in ones)
    assert all(r["ref_date"] == "02" for r in rows if r not in ones)
    d.close()


def test_weekly_fixed_grounding_not_daily(monkeypatch, tmp_path):
    # E-2: weekly/monthly/고정 콘텐츠의 grounding은 자체 builder 결과여야 함 —
    # daily 그라운딩이 오염 저장되는 문제 차단
    import collect
    import llm_client
    from engine import fortune_content as fc
    import json as json_mod

    def fake_blog(g, **kw):
        ref = g.get("reference", "2026-08-10")
        return {"title": f"{ref} 주간 운세", "summary": "요약",
                "body": f"## 총평\n{ref} 기준 본문"}

    monkeypatch.setattr(llm_client, "has_api_key", lambda: True)
    monkeypatch.setattr(fc, "generate_sns_summary",
                        lambda g, **kw: {"text": "요약", "hashtags": []})
    monkeypatch.setattr(fc, "generate_blog_detail", fake_blog)
    monkeypatch.setattr(fc, "generate_extended_blog", fake_blog)
    monkeypatch.setattr(publish_client.requests, "post",
                        lambda *a, **kw: _Resp(200, {}))
    d = _open(tmp_path)
    cfg = _cfg(tmp_path)
    cfg["fortune_fixed_per_day"] = 1
    collect.fortune_generate_step(d, cfg, "2026-08-10")  # 월요일 → weekly
    weekly = d.get_fortune_generation("2026-08-10", "weekly_blog")
    wg = json_mod.loads(weekly["grounding"])
    assert wg.get("content_type") == "weekly", "weekly grounding이 daily로 오염"
    fixed = d.get_fortune_generation("01", "day_pillar_blog")
    fg = json_mod.loads(fixed["grounding"])
    assert fg.get("content_type") == "day_pillar", "고정 콘텐츠 grounding이 daily로 오염"
    d.close()


def test_weekly_and_monthly_created_on_schedule(monkeypatch, tmp_path):
    import collect
    import llm_client
    from engine import fortune_content as fc

    def fake_blog(g, **kw):
        ref = g.get("reference", "2026-08-10")
        return {"title": f"{ref} 주간 운세", "summary": "요약",
                "body": f"## 총평\n{ref} 기준 본문"}

    monkeypatch.setattr(llm_client, "has_api_key", lambda: True)
    monkeypatch.setattr(fc, "generate_sns_summary",
                        lambda g, **kw: {"text": "요약", "hashtags": []})
    monkeypatch.setattr(fc, "generate_blog_detail", fake_blog)
    monkeypatch.setattr(fc, "generate_extended_blog", fake_blog)
    monkeypatch.setattr(publish_client.requests, "post",
                        lambda *a, **kw: _Resp(200, {}))
    d = _open(tmp_path)
    cfg = _cfg(tmp_path)
    # 월요일 (2026-08-10) → weekly 생성
    import datetime
    assert datetime.date(2026, 8, 10).weekday() == 0
    n = collect.fortune_generate_step(d, cfg, "2026-08-10")
    weekly = d.get_fortune_generation("2026-08-10", "weekly_blog")
    assert weekly and weekly["status"] == "published"
    # 화요일 → weekly 미생성 (멱등 스케줄)
    n2 = collect.fortune_generate_step(d, cfg, "2026-08-11")
    assert d.get_fortune_generation("2026-08-10", "weekly_blog")["status"] == "published"
    # 1일 → monthly 생성 (ref: YYYY-MM)
    n3 = collect.fortune_generate_step(d, cfg, "2026-09-01")
    monthly = d.get_fortune_generation("2026-09", "monthly_blog")
    assert monthly and monthly["status"] == "published"
    d.close()


# ---------- v28: 항목별 결과 수집 헬퍼 (수동 발행 엔드포인트용) ----------


def _seed(d, ref, ctype, status="generated"):
    d.upsert_fortune_generation(ref, ctype, "", grounding="g")
    d.update_fortune_generation(
        ref, ctype, json.dumps(_blog_content(ref), ensure_ascii=False),
        status=status)


def test_publish_all_fortune_items_collects_per_item(monkeypatch, tmp_path):
    # T5 (AC-3~AC-5, AC-10): 200/401/429/5xx/qc_failed/published 혼합 —
    # 항목별 상태·사유 정확성, daily_sns 비포함, DB 상태 갱신 기존 동작 유지
    import collect
    d = _open(tmp_path)
    cfg = _cfg(tmp_path)
    _seed(d, "2026-08-10", "daily_blog")                     # → 성공
    _seed(d, "01", "day_pillar_blog")                        # → 401 즉시 실패
    _seed(d, "01", "zodiac_blog")                            # → 429 재시도 후 실패
    _seed(d, "01", "animal_blog")                            # → 503 재시도 후 실패
    _seed(d, "02", "zodiac_blog", status="qc_failed")        # → 스킵 (검수 대기)
    _seed(d, "02", "animal_blog", status="published")        # → 스킵 (이미 발행됨)
    _seed(d, "2026-08-10", "daily_sns")                      # → 발행 후보 아님

    def fake_post(url, json, headers, timeout):
        slug = json["slug"]
        if slug == "fortune-day-pillar-01":
            return _Resp(401, "unauthorized")
        if slug == "fortune-zodiac-01":
            return _Resp(429, "quota exhausted")
        if slug == "fortune-animal-01":
            return _Resp(503, "boom")
        return _Resp(200, {})

    monkeypatch.setattr(publish_client.requests, "post", fake_post)
    monkeypatch.setattr(publish_client.time, "sleep", lambda s: None)
    items = collect.publish_all_fortune_items(d, cfg, "2026-08-10")
    by = {(it["content_type"], it["ref"]): it for it in items}
    assert ("daily_sns", "2026-08-10") not in by  # AC-10 — 후보에 없음
    assert by[("daily_blog", "2026-08-10")]["ok"] is True
    assert by[("daily_blog", "2026-08-10")]["status"] == "published"
    assert by[("day_pillar_blog", "01")]["status"] == "failed"
    assert by[("day_pillar_blog", "01")]["reason"].startswith("HTTP 401")
    assert "토큰 불일치" in by[("day_pillar_blog", "01")]["reason"]
    assert by[("zodiac_blog", "01")]["status"] == "failed"
    assert by[("zodiac_blog", "01")]["reason"].startswith("HTTP 429")
    assert "쿼터 소진" in by[("zodiac_blog", "01")]["reason"]
    assert by[("animal_blog", "01")]["status"] == "failed"
    assert "HTTP 503" in by[("animal_blog", "01")]["reason"]
    assert by[("zodiac_blog", "02")]["status"] == "skipped"
    assert "검수 대기" in by[("zodiac_blog", "02")]["reason"]
    assert by[("animal_blog", "02")]["status"] == "skipped"
    assert "이미 발행됨" in by[("animal_blog", "02")]["reason"]
    # DB 상태 갱신 — 기존 _publish_all_fortune과 동일 동작
    assert d.get_fortune_generation("2026-08-10", "daily_blog")["status"] == "published"
    assert d.get_fortune_generation("01", "day_pillar_blog")["status"] == "publish_failed"
    assert d.get_fortune_generation("02", "zodiac_blog")["status"] == "qc_failed"
    d.close()


def test_publish_all_fortune_items_budget_skips_rest(monkeypatch, tmp_path):
    # OQ-1: 예산 0 → 발행 시도 없이 전 항목 skipped("시간 예산") — 멱등 재클릭 전제
    import collect
    d = _open(tmp_path)
    _seed(d, "2026-08-10", "daily_blog")
    calls = []
    monkeypatch.setattr(publish_client.requests, "post",
                        lambda *a, **kw: (calls.append(1), _Resp(200, {}))[1])
    items = collect.publish_all_fortune_items(d, _cfg(tmp_path), "2026-08-10",
                                              budget_seconds=0)
    assert calls == []
    assert len(items) == 86  # daily 1 + weekly 1(월요일) + 고정 60/12/12
    assert all(it["status"] == "skipped" and it["reason"] == "시간 예산"
               for it in items)
    d.close()
