# v17: 콘텐츠 배치 — 컬렉트 잡에서 초안·이미지 생성 (버그 3·고도화 4)
import json

import content_batch
import db


def make_db(tmp_path):
    d = db.Database(f"sqlite:///{tmp_path / 't.db'}")
    d.init()
    return d


def make_cfg(tmp_path):
    return {
        "db_url": f"sqlite:///{tmp_path / 't.db'}",
        "client_id": "cid", "client_secret": "csec",
        "content_batch_max_new": 2, "content_batch_budget_seconds": 600,
        # v19: 마크다운 본문·섹션 이미지 경로 검증 — 티스토리 플랫폼 사용
        "content_batch_platform": "tistory",
    }


class FakeClient:
    def search_blog(self, query, sort="sim", display=100, start=1):
        return {"total": 100, "items": [{"postdate": "20260101"}]}


def test_skips_without_llm_key(tmp_path, monkeypatch):
    monkeypatch.delenv("BAILIAN_TOKEN_PLAN_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    d = make_db(tmp_path)
    kid = d.upsert_keyword("키워드", day="2026-08-01")
    d.insert_daily_stats(kid, "2026-08-02", {"opportunity": 10.0})
    result = content_batch.run_content_batch(
        d, make_cfg(tmp_path), "2026-08-02", "now", FakeClient())
    # v26(FR-4): 결과 dict에 이미지 집계 키 추가 — 계약 변경으로 기대값 갱신
    assert result == {"drafts_created": 0, "draft_images_created": 0,
                      "image_attempts": 0, "image_failures": 0,
                      "image_alert": False}
    assert any(l["action"] == "skip" for l in d.get_logs())
    d.close()


def test_creates_draft_and_images_for_top_keyword(tmp_path, monkeypatch):
    monkeypatch.setenv("BAILIAN_TOKEN_PLAN_API_KEY", "test-key")
    d = make_db(tmp_path)
    kid = d.upsert_keyword("키워드", day="2026-08-01")
    d.insert_daily_stats(kid, "2026-08-02", {"opportunity": 10.0})
    cfg = make_cfg(tmp_path)

    import analyzer
    import draft_pipeline
    import image_gen

    monkeypatch.setattr(analyzer, "analyze_keyword", lambda client, kw, rd,
                        searched_at_kst=None: {
        "total_sim": 100, "total_date": 100, "fresh_ratio": 0.5,
        "top_post_dates": [], "top_bloggers": [], "top_descriptions": [],
        "search_evidence": {"status": "available", "searched_at_kst": "",
                            "reference_date": "", "items": []},
    })
    # collect._create_draft는 content_batch 경유 — analyze_keyword는
    # content_batch가 import한 이름에 바인딩됨
    monkeypatch.setattr(content_batch, "analyze_keyword",
                        analyzer.analyze_keyword)
    monkeypatch.setattr(
        draft_pipeline, "generate_two_pass",
        lambda k, s, **kw: ({"title": "배치 제목", "first_paragraph": "즉답",
                             "body": "## 섹션1\n내용\n\n## 자주 묻는 질문\n### q\na"}, []))
    monkeypatch.setattr(content_batch, "generate_two_pass",
                        draft_pipeline.generate_two_pass)
    monkeypatch.setattr(image_gen, "generate_image",
                        lambda kw, title, **kw2: "https://cdn.example.com/main.png")
    monkeypatch.setattr(content_batch, "generate_image",
                        image_gen.generate_image)
    monkeypatch.setattr(
        image_gen, "generate_section_images",
        lambda kw, title, sections, **kw2: ["https://cdn.example.com/s1.png"])
    monkeypatch.setattr(content_batch, "generate_section_images",
                        image_gen.generate_section_images)

    result = content_batch.run_content_batch(
        d, cfg, "2026-08-02", "now", FakeClient())
    assert result["drafts_created"] == 1
    assert result["draft_images_created"] == 2  # 대표 1 + 섹션 1
    drafts = d.list_drafts_by_keyword(kid)
    assert len(drafts) == 1
    assert drafts[0]["title"] == "배치 제목"
    assert drafts[0]["image_url"] == "https://cdn.example.com/main.png"
    assert json.loads(drafts[0]["section_images"]) == [
        "https://cdn.example.com/s1.png"]
    d.close()


def test_batch_attaches_product_block_for_shop_category(tmp_path, monkeypatch):
    # v21(B.3): 쇼핑 전환 적합 카테고리(요리) 초안에 상품 블록 자동 첨부
    monkeypatch.setenv("BAILIAN_TOKEN_PLAN_API_KEY", "test-key")
    d = make_db(tmp_path)
    kid = d.upsert_keyword("에어프라이어 추천", category="요리", day="2026-08-01")
    d.insert_daily_stats(kid, "2026-08-02", {"opportunity": 10.0})
    cfg = make_cfg(tmp_path)

    import draft_pipeline
    import image_gen
    import product_recommend

    monkeypatch.setattr(content_batch, "analyze_keyword",
                        lambda client, kw, rd, **kw2: {
        "total_sim": 100, "total_date": 100, "fresh_ratio": 0.5,
        "top_post_dates": [], "top_bloggers": [], "top_descriptions": [],
        "search_evidence": {"status": "available", "searched_at_kst": "",
                            "reference_date": "", "items": []}})
    monkeypatch.setattr(draft_pipeline, "generate_two_pass",
                        lambda k, s, **kw: (
                            {"title": "제목", "first_paragraph": "즉답",
                             "body": "## 섹션1\n내용"}, []))
    monkeypatch.setattr(content_batch, "generate_two_pass",
                        draft_pipeline.generate_two_pass)
    monkeypatch.setattr(image_gen, "generate_image",
                        lambda kw, title, **kw2: "https://cdn.example.com/m.png")
    monkeypatch.setattr(content_batch, "generate_image",
                        image_gen.generate_image)
    monkeypatch.setattr(image_gen, "generate_section_images",
                        lambda kw, title, sections, **kw2: [])
    monkeypatch.setattr(content_batch, "generate_section_images",
                        image_gen.generate_section_images)
    monkeypatch.setattr(product_recommend, "search_products",
                        lambda client, kw: [{
                            "title": "에어프라이어 5L",
                            "link": "https://shopping.naver.com/gold/gold.naver?productId=1",
                            "image": "", "price": 15000, "mall": "스토어"}])
    monkeypatch.setattr(content_batch, "search_products",
                        product_recommend.search_products)

    result = content_batch.run_content_batch(
        d, cfg, "2026-08-02", "now", FakeClient())
    assert result["drafts_created"] == 1
    draft = d.list_drafts_by_keyword(kid)[0]
    block = json.loads(draft["product_block"])
    assert block[0]["title"] == "에어프라이어 5L"
    assert block[0]["price"] == 15000
    d.close()


def test_batch_skips_product_block_for_non_shop_category(tmp_path, monkeypatch):
    # v21(B.3): 비쇼핑 카테고리(보험) 초안은 상품 블록 없음
    monkeypatch.setenv("BAILIAN_TOKEN_PLAN_API_KEY", "test-key")
    d = make_db(tmp_path)
    kid = d.upsert_keyword("보험 비교", category="보험", day="2026-08-01")
    d.insert_daily_stats(kid, "2026-08-02", {"opportunity": 10.0})
    cfg = make_cfg(tmp_path)

    import draft_pipeline
    import image_gen

    monkeypatch.setattr(content_batch, "analyze_keyword",
                        lambda client, kw, rd, **kw2: {
        "total_sim": 100, "total_date": 100, "fresh_ratio": 0.5,
        "top_post_dates": [], "top_bloggers": [], "top_descriptions": [],
        "search_evidence": {"status": "available", "searched_at_kst": "",
                            "reference_date": "", "items": []}})
    monkeypatch.setattr(draft_pipeline, "generate_two_pass",
                        lambda k, s, **kw: (
                            {"title": "제목", "first_paragraph": "즉답",
                             "body": "## 섹션1\n내용"}, []))
    monkeypatch.setattr(content_batch, "generate_two_pass",
                        draft_pipeline.generate_two_pass)
    monkeypatch.setattr(image_gen, "generate_image",
                        lambda kw, title, **kw2: "https://cdn.example.com/m.png")
    monkeypatch.setattr(content_batch, "generate_image",
                        image_gen.generate_image)
    monkeypatch.setattr(image_gen, "generate_section_images",
                        lambda kw, title, sections, **kw2: [])
    monkeypatch.setattr(content_batch, "generate_section_images",
                        image_gen.generate_section_images)

    result = content_batch.run_content_batch(
        d, cfg, "2026-08-02", "now", FakeClient())
    assert result["drafts_created"] == 1
    draft = d.list_drafts_by_keyword(kid)[0]
    assert draft["product_block"] == ""
    d.close()


def test_backfills_missing_images_only(tmp_path, monkeypatch):
    monkeypatch.setenv("BAILIAN_TOKEN_PLAN_API_KEY", "test-key")
    d = make_db(tmp_path)
    kid = d.upsert_keyword("키워드", day="2026-08-01")
    did = d.insert_draft(kid, "기존 초안", "fp", "## 섹션1\n본문",
                         created_at="n", platform="tistory")
    cfg = make_cfg(tmp_path)

    import image_gen
    monkeypatch.setattr(image_gen, "generate_image",
                        lambda kw, title, **kw2: "https://cdn.example.com/main.png")
    monkeypatch.setattr(content_batch, "generate_image",
                        image_gen.generate_image)
    monkeypatch.setattr(
        image_gen, "generate_section_images",
        lambda kw, title, sections, **kw2: ["https://cdn.example.com/s1.png"])
    monkeypatch.setattr(content_batch, "generate_section_images",
                        image_gen.generate_section_images)
    # 신규 초안 생성 경로는 비활성화 (백필만 검증)
    monkeypatch.setattr(d, "keywords_without_drafts", lambda limit: [])

    result = content_batch.run_content_batch(
        d, cfg, "2026-08-02", "now", FakeClient())
    assert result["drafts_created"] == 0
    assert result["draft_images_created"] == 2
    draft = d.get_draft(did)
    assert draft["image_url"] == "https://cdn.example.com/main.png"
    assert json.loads(draft["section_images"]) == [
        "https://cdn.example.com/s1.png"]
    d.close()


def test_draft_failure_is_isolated(tmp_path, monkeypatch):
    # 한 키워드 실패가 배치 전체를 멈추지 않음
    monkeypatch.setenv("BAILIAN_TOKEN_PLAN_API_KEY", "test-key")
    d = make_db(tmp_path)
    k1 = d.upsert_keyword("실패키워드", day="2026-08-01")
    k2 = d.upsert_keyword("성공키워드", day="2026-08-01")
    d.insert_daily_stats(k1, "2026-08-02", {"opportunity": 20.0})
    d.insert_daily_stats(k2, "2026-08-02", {"opportunity": 10.0})
    cfg = make_cfg(tmp_path)

    import draft_pipeline
    from draft_generator import DraftGenerationError
    calls = []

    def fake_two_pass(k, s, **kw):
        calls.append(k)
        if k == "실패키워드":
            raise DraftGenerationError("api down")
        return ({"title": "t", "first_paragraph": "fp", "body": "본문"}, [])

    import analyzer
    monkeypatch.setattr(content_batch, "analyze_keyword",
                        lambda client, kw, rd, searched_at_kst=None: {
        "total_sim": 10, "total_date": 10, "fresh_ratio": 0.1,
        "top_post_dates": [], "top_bloggers": [], "top_descriptions": [],
        "search_evidence": {"status": "available", "searched_at_kst": "",
                            "reference_date": "", "items": []},
    })
    monkeypatch.setattr(content_batch, "generate_two_pass", fake_two_pass)
    import image_gen
    monkeypatch.setattr(image_gen, "ImageGenerationError",
                        image_gen.ImageGenerationError)
    monkeypatch.setattr(
        content_batch, "generate_image",
        lambda kw, title, **kw2: (_ for _ in ()).throw(
            image_gen.ImageGenerationError("no key")))
    monkeypatch.setattr(content_batch, "generate_section_images",
                        lambda *a, **kw: [])

    result = content_batch.run_content_batch(
        d, cfg, "2026-08-02", "now", FakeClient())
    assert result["drafts_created"] == 1  # 실패 격리 후 2번째는 성공
    assert len(calls) == 2
    assert any(l["action"] == "error" and l["keyword"] == "실패키워드"
               for l in d.get_logs())
    d.close()


# ============ v26: 이미지 실패 집계·임계 알림 (TDD — 요구사항 FR-4·FR-5, 테스트 T4~T6) ============

def test_consecutive_image_failures_alert(tmp_path, monkeypatch, caplog):
    """T4 (AC5-1·AC5-5): 배치 내 이미지 최종 실패 연속 5건 → ERROR 로그 1건 +
    결과 dict image_alert=True (백필 경로 — 대표 이미지 5건 전부 실패)."""
    import logging
    import llm_client
    monkeypatch.setenv("BAILIAN_TOKEN_PLAN_API_KEY", "bailian-key")
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    d = make_db(tmp_path)
    cfg = make_cfg(tmp_path)
    for i in range(5):
        kid = d.upsert_keyword(f"키워드{i}", day="2026-08-01")
        d.insert_draft(kid, f"초안{i}", "fp", "## 섹션1\n본문",
                       created_at="n", platform="naver")

    def fake_post_json(url, payload, api_key, timeout, error_cls, err_prefix, **kw):
        raise error_cls("image API http 429: quota exhausted")

    monkeypatch.setattr(llm_client, "post_json", fake_post_json)
    with caplog.at_level(logging.ERROR, logger="content_batch"):
        result = content_batch.run_content_batch(
            d, cfg, "2026-08-02", "now", FakeClient())
    assert result["image_attempts"] == 5
    assert result["image_failures"] == 5
    assert result["image_alert"] is True            # AC5-5
    assert len([r for r in caplog.records]) >= 1
    assert any("임계" in r.message for r in caplog.records)  # AC5-1 ERROR 로그
    assert any("5" in r.message for r in caplog.records if "임계" in r.message)
    d.close()


def test_failure_rate_over_half_alerts(tmp_path, monkeypatch, caplog):
    """T5a (AC5-2): 시도 5건 중 3건 최종 실패(실패율 60% > 50%) → ERROR 로그 +
    image_alert=True."""
    import logging
    import llm_client
    monkeypatch.setenv("BAILIAN_TOKEN_PLAN_API_KEY", "bailian-key")
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    d = make_db(tmp_path)
    cfg = make_cfg(tmp_path)
    for i in range(5):
        kid = d.upsert_keyword(f"키워드{i}", day="2026-08-01")
        d.insert_draft(kid, f"초안{i}", "fp", "## 섹션1\n본문",
                       created_at="n", platform="naver")
    calls = {"n": 0}

    def fake_post_json(url, payload, api_key, timeout, error_cls, err_prefix, **kw):
        calls["n"] += 1
        if calls["n"] <= 3:
            raise error_cls("image API http 429: quota exhausted")
        return {"output": {"choices": [{"message": {"content": [
            {"type": "image", "image": "https://cdn.example.com/main.png"}]}}]}}

    monkeypatch.setattr(llm_client, "post_json", fake_post_json)
    with caplog.at_level(logging.ERROR, logger="content_batch"):
        result = content_batch.run_content_batch(
            d, cfg, "2026-08-02", "now", FakeClient())
    assert result["image_attempts"] == 5
    assert result["image_failures"] == 3
    assert result["image_alert"] is True
    assert any("임계" in r.message for r in caplog.records)
    d.close()


def test_below_threshold_no_error_log(tmp_path, monkeypatch, caplog):
    """T5b (AC5-3): 시도 5건 중 1건 실패(실패율 20%) → ERROR 로그 없음,
    image_alert=False (기존 warning 로그만)."""
    import logging
    import llm_client
    monkeypatch.setenv("BAILIAN_TOKEN_PLAN_API_KEY", "bailian-key")
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    d = make_db(tmp_path)
    cfg = make_cfg(tmp_path)
    for i in range(5):
        kid = d.upsert_keyword(f"키워드{i}", day="2026-08-01")
        d.insert_draft(kid, f"초안{i}", "fp", "## 섹션1\n본문",
                       created_at="n", platform="naver")
    calls = {"n": 0}

    def fake_post_json(url, payload, api_key, timeout, error_cls, err_prefix, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise error_cls("image API http 429: quota exhausted")
        return {"output": {"choices": [{"message": {"content": [
            {"type": "image", "image": "https://cdn.example.com/main.png"}]}}]}}

    monkeypatch.setattr(llm_client, "post_json", fake_post_json)
    with caplog.at_level(logging.ERROR, logger="content_batch"):
        result = content_batch.run_content_batch(
            d, cfg, "2026-08-02", "now", FakeClient())
    assert result["image_attempts"] == 5
    assert result["image_failures"] == 1
    assert result["image_alert"] is False
    assert not [r for r in caplog.records]          # ERROR 레코드 0건
    d.close()


def test_image_alert_threshold_function():
    """T6 (AC5-2 소표본 가드): 임계 판정 함수 단위 —
    연속 5건(시도 무관) / 시도 5건+ 실패율 50% 초과 / 시도 5건 미만 실패율 미적용."""
    triggered = content_batch.image_alert_triggered
    assert triggered(5, 5, 5) is True     # 연속 5건
    assert triggered(4, 4, 5) is True     # 연속 5건은 시도 수 무관
    assert triggered(5, 3, 3) is True     # 실패율 60% > 50% (시도 5건+)
    assert triggered(6, 4, 4) is True     # 실패율 66.7%
    assert triggered(5, 2, 2) is False    # 실패율 40% 이하
    assert triggered(4, 4, 4) is False    # 시도 4건: 연속 4<5·실패율 미적용 (소표본 가드)
    assert triggered(0, 0, 0) is False


def test_new_draft_path_image_stats_aggregated(tmp_path, monkeypatch):
    """QA P4: 신규 초안 경로(대표+섹션) stats 집계 — 대표 성공·섹션1 실패·섹션2 성공
    → attempts 3, failures 1, alert 없음 (신규 생성 경로의 AC4-2 자동 테스트)."""
    import llm_client
    monkeypatch.setenv("BAILIAN_TOKEN_PLAN_API_KEY", "bailian-key")
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    d = make_db(tmp_path)
    kid = d.upsert_keyword("보험 비교", category="보험", day="2026-08-01")
    d.insert_daily_stats(kid, "2026-08-02", {"opportunity": 10.0})
    cfg = make_cfg(tmp_path)

    import draft_pipeline
    monkeypatch.setattr(content_batch, "analyze_keyword",
                        lambda client, kw, rd, **kw2: {
        "total_sim": 100, "total_date": 100, "fresh_ratio": 0.5,
        "top_post_dates": [], "top_bloggers": [], "top_descriptions": [],
        "search_evidence": {"status": "available", "searched_at_kst": "",
                            "reference_date": "", "items": []}})
    monkeypatch.setattr(draft_pipeline, "generate_two_pass",
                        lambda k, s, **kw: (
                            {"title": "제목", "first_paragraph": "즉답",
                             "body": "## 섹션1\n내용\n\n## 섹션2\n내용"}, []))
    monkeypatch.setattr(content_batch, "generate_two_pass",
                        draft_pipeline.generate_two_pass)
    calls = {"n": 0}

    def fake_post_json(url, payload, api_key, timeout, error_cls, err_prefix, **kw):
        calls["n"] += 1
        if calls["n"] == 2:  # 1=대표 성공, 2=섹션1 실패, 3=섹션2 성공
            raise error_cls("image API http 429: quota exhausted")
        return {"output": {"choices": [{"message": {"content": [
            {"type": "image", "image": "https://cdn.example.com/img.png"}]}}]}}

    monkeypatch.setattr(llm_client, "post_json", fake_post_json)
    result = content_batch.run_content_batch(
        d, cfg, "2026-08-02", "now", FakeClient())
    assert result["drafts_created"] == 1
    assert result["image_attempts"] == 3    # 대표 1 + 섹션 2
    assert result["image_failures"] == 1    # 섹션1만 최종 실패
    assert result["image_alert"] is False   # 1/3=33%·연속 1 < 5
    draft = d.list_drafts_by_keyword(kid)[0]
    assert len(json.loads(draft["section_images"])) == 1  # 섹션2만 저장 (격리 유지)
    d.close()
