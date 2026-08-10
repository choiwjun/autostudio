# tests/test_platforms.py — v19: 멀티 플랫폼 (네이버/티스토리/애드센스/브랜드)
import json

import db
import draft_pipeline
import image_gen
import platforms
import pytest
from draft_generator import _append_faq_if_missing, parse_draft
from fastapi.testclient import TestClient
from server import create_app


def _open(tmp_path):
    d = db.Database(f"sqlite:///{tmp_path / 't.db'}")
    d.init()
    return d


def _make_app(tmp_path, env="development"):
    d = _open(tmp_path)
    a = d.upsert_keyword("에어프라이어", category="가전", day="2026-08-01")
    d.insert_daily_stats(a, "2026-08-02", {
        "total_sim": 100, "total_date": 110, "fresh_ratio": 0.5,
        "growth": 0.27, "opportunity": 64.1, "demand_idx": 0.005,
        "shop_click_idx": 0.9, "ai_cite_idx": 0.8, "commercial": None})
    d.upsert_outline(a, "2026-08-02",
                     '{"questions": ["기준은?"], "comparisons": [], "facts": []}')
    d.close()
    return create_app({"db_url": f"sqlite:///{tmp_path / 't.db'}",
                       "dashboard_token": "sekret", "env": env})


# ---------- 태그 형식 ----------

def test_format_tags_per_platform():
    tags = ["에어프라이어 추천", "주방가전"]
    assert platforms.format_tags(tags, "naver") == "#에어프라이어 추천 #주방가전"
    assert platforms.format_tags(tags, "adsense") == "#에어프라이어 추천 #주방가전"
    assert platforms.format_tags(tags, "brand") == "#에어프라이어 추천 #주방가전"
    assert platforms.format_tags(tags, "tistory") == "에어프라이어 추천, 주방가전"
    assert platforms.format_tags([], "naver") == ""
    assert platforms.format_tags(["", "  "], "tistory") == ""


# ---------- 네이버 마크다운 금지 검수 ----------

def test_naver_markdown_violations():
    assert platforms.naver_markdown_violations("소제목\n\n본문입니다.") == []
    hits = {s for s, _ in platforms.naver_markdown_violations(
        "## 소제목\n- 리스트\n| 표 |\n**굵게**\n```\n코드\n```")}
    assert "##" in hits and "- " in hits and "|" in hits and "**" in hits


def _naver_good_body(subtitle="소제목", extra_titles=()):
    """네이버 검수 통과 본문 — 3000자+, 키워드 12회, 플레인 텍스트."""
    lines = [subtitle, ""]
    lines.append("본문입니다. 선택 기준과 구매 전 확인 사항을 정리했습니다. " * 90)
    for t in extra_titles:
        lines += ["", t, "", "본문입니다. 선택 기준과 구매 전 확인 사항을 정리했습니다. " * 90]
    lines.append("키워드 추천 기준입니다. " * 12)
    lines += ["", "자주 묻는 질문", "", "Q. 질문", "A. 답변"]
    return "\n".join(lines)


def test_naver_plain_text_qc_rejects_markdown():
    from draft_pipeline import validate_draft
    fp = "즉답입니다. 추천 기준은 용량과 조리 방식, 관리 편의성 순서로 확인해야 합니다."
    body = _naver_good_body()
    ok, failed = validate_draft(
        {"title": "좋은 제목", "first_paragraph": fp, "body": body}, "키워드")
    assert ok, failed
    bad = body.replace("소제목", "## 소제목")
    ok2, failed2 = validate_draft(
        {"title": "좋은 제목", "first_paragraph": fp, "body": bad}, "키워드")
    assert not ok2 and "no_markdown" in failed2


def test_naver_structure_check_uses_skeleton():
    from draft_pipeline import validate_draft
    skeleton = [{"title": "기준", "bullets": []}, {"title": "용량", "bullets": []},
                {"title": "관리", "bullets": []}]
    fp = "즉답입니다. 추천 기준은 용량과 조리 방식, 관리 편의성 순서로 확인해야 합니다."
    body = _naver_good_body(subtitle="기준", extra_titles=("용량", "관리"))
    ok, failed = validate_draft(
        {"title": "좋은 제목", "first_paragraph": fp, "body": body},
        "키워드", skeleton=skeleton)
    assert ok, failed
    # 골격 소제목이 본문에 없으면 구조 검수 실패
    ok2, failed2 = validate_draft(
        {"title": "좋은 제목", "first_paragraph": fp,
         "body": _naver_good_body(subtitle="다른제목",
                                  extra_titles=("용량", "관리"))},
        "키워드", skeleton=skeleton)
    assert not ok2 and "structure" in failed2


# ---------- 플랫폼 프롬프트 주입 ----------

def test_pass1_injects_platform_rules():
    captured = {}

    def fake_run(prompt, timeout=90):
        captured["prompt"] = prompt
        return '{"h2s": [{"title": "H2", "bullets": ["b"]}]}'

    draft_pipeline.pass1_outline("키워드", {}, runner=fake_run, platform="tistory")
    assert "## 플랫폼 규칙" in captured["prompt"]
    assert "구글 검색(Featured Snippet)" in captured["prompt"]
    captured.clear()
    draft_pipeline.pass1_outline("키워드", {}, runner=fake_run, platform="naver")
    assert "플레인 텍스트 한 줄" in captured["prompt"]
    assert "구글 검색(Featured Snippet)" not in captured["prompt"]


def test_pass2_injects_platform_format_and_thumbnail_rules():
    captured = {}

    def fake_run(prompt, timeout=90):
        captured["prompt"] = prompt
        return json.dumps({"title": "제목", "first_paragraph": "즉답입니다.",
                           "body": "## 1. 섹션\n본문"}, ensure_ascii=False)

    draft_pipeline.pass2_expand("키워드", [{"title": "H2", "bullets": ["b"]}],
                                "info", runner=fake_run, platform="tistory")
    p = captured["prompt"]
    assert "## 플랫폼 포맷" in p and "마크다운 + 구글 SEO" in p
    assert "썸네일 아이디어 2개" in p and '"thumbnail_ideas"' in p
    assert "표(markdown table) 1~2개 이상" in p
    captured.clear()
    draft_pipeline.pass2_expand("키워드", [{"title": "H2", "bullets": ["b"]}],
                                "info", runner=fake_run, platform="naver")
    p = captured["prompt"]
    assert "플레인 텍스트 전용" in p
    assert "표(markdown table) 1~2개 이상" not in p
    assert "마크다운 기호" in p


# ---------- FAQ 플랫폼 포맷 ----------

def test_append_faq_platform_formats():
    base = {"title": "t", "first_paragraph": "p", "body": "본문입니다"}
    q = {"questions": ["어떤 게 좋을까?"]}
    naver = _append_faq_if_missing(dict(base), q, platform="naver")["body"]
    assert "\n자주 묻는 질문\n" in naver and "Q. 어떤 게 좋을까?" in naver
    assert "##" not in naver
    tistory = _append_faq_if_missing(dict(base), q, platform="tistory")["body"]
    assert "## 자주 묻는 질문 (FAQ)" in tistory and "> **Q. 어떤 게 좋을까?**" in tistory


# ---------- 썸네일 아이디어 ↔ 이미지 ----------

def test_image_prompt_uses_thumbnail_ideas():
    prompt = image_gen._build_prompt("에어프라이어", "제목",
                                     ["실사 주방 배경 콘셉트", "두 번째"])
    assert "썸네일 콘셉트(첫 번째 아이디어 우선): 실사 주방 배경 콘셉트" in prompt
    plain = image_gen._build_prompt("에어프라이어", "제목")
    assert "썸네일 콘셉트" not in plain


# ---------- API: 플랫폼 저장·검증·섹션 이미지 가드 ----------

def test_create_draft_stores_platform_and_thumbnail_ideas(tmp_path, monkeypatch):
    monkeypatch.setattr(
        draft_pipeline, "generate_two_pass",
        lambda k, s, **kw: ({"title": "제목", "first_paragraph": "즉답입니다.",
                             "body": "## 1. 섹션\n본문\n\n## 자주 묻는 질문 (FAQ)\n### q\na",
                             "tags": ["태그1"], "thumbnail_ideas": ["컨셉A", "컨셉B"]}, []))
    client = TestClient(_make_app(tmp_path))
    r = client.post("/drafts", json={"keyword_id": 1, "platform": "tistory"})
    assert r.status_code == 200
    body = r.json()
    assert body["platform"] == "tistory"
    assert body["thumbnail_ideas"] == ["컨셉A", "컨셉B"]
    d = _open(tmp_path)
    row = d.get_draft(body["id"])
    assert row["platform"] == "tistory"
    assert json.loads(row["thumbnail_ideas"]) == ["컨셉A", "컨셉B"]
    d.close()


def test_create_draft_rejects_unknown_platform(tmp_path, monkeypatch):
    monkeypatch.setattr(draft_pipeline, "generate_two_pass",
                        lambda k, s, **kw: (
                            {"title": "t", "first_paragraph": "즉답입니다.",
                             "body": "본문"}, []))
    client = TestClient(_make_app(tmp_path))
    assert client.post("/drafts", json={"keyword_id": 1,
                                        "platform": "not-a-platform"}).status_code == 400


def test_naver_draft_section_images_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(draft_pipeline, "generate_two_pass",
                        lambda k, s, **kw: (
                            {"title": "t", "first_paragraph": "즉답입니다.",
                             "body": "소제목\n\n본문"}, []))
    client = TestClient(_make_app(tmp_path))
    did = client.post("/drafts", json={"keyword_id": 1,
                                       "platform": "naver"}).json()["id"]
    r = client.post(f"/drafts/{did}/section-images")
    assert r.status_code == 400
    assert "플레인 텍스트" in r.json()["detail"]


def test_refresh_inherits_platform(tmp_path, monkeypatch):
    monkeypatch.setattr(draft_pipeline, "generate_two_pass",
                        lambda k, s, **kw: (
                            {"title": "새 제목", "first_paragraph": "즉답입니다.",
                             "body": "## 1. 섹션\n본문"}, []))
    client = TestClient(_make_app(tmp_path))
    did = client.post("/drafts", json={"keyword_id": 1,
                                       "platform": "adsense"}).json()["id"]
    r = client.post(f"/drafts/{did}/refresh")
    assert r.status_code == 200
    assert r.json()["platform"] == "adsense"
    assert r.json()["refresh_of"] == did


def test_planner_queue_includes_platform(tmp_path, monkeypatch):
    monkeypatch.setattr(draft_pipeline, "generate_two_pass",
                        lambda k, s, **kw: (
                            {"title": "t", "first_paragraph": "즉답입니다.",
                             "body": "## 1. 섹션\n본문"}, []))
    client = TestClient(_make_app(tmp_path))
    client.post("/drafts", json={"keyword_id": 1, "platform": "tistory"})
    queue = client.get("/planner").json()["publish_queue"]
    assert queue[0]["platform"] == "tistory"
