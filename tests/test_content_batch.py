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
    assert result == {"drafts_created": 0, "draft_images_created": 0}
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


def test_backfills_missing_images_only(tmp_path, monkeypatch):
    monkeypatch.setenv("BAILIAN_TOKEN_PLAN_API_KEY", "test-key")
    d = make_db(tmp_path)
    kid = d.upsert_keyword("키워드", day="2026-08-01")
    did = d.insert_draft(kid, "기존 초안", "fp", "## 섹션1\n본문", created_at="n")
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
