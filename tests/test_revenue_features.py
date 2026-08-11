# tests/test_revenue_features.py — v18: 실측 CPC/RPM · 게시 플래너 · 리프레시 · 수익 인사이트 · 패턴 학습
import datetime

import db
import draft_pipeline
import pytest
from fastapi.testclient import TestClient
from server import create_app


def _open(tmp_path):
    d = db.Database(f"sqlite:///{tmp_path / 't.db'}")
    d.init()
    return d


def _old_day(days):
    return (datetime.date.today() - datetime.timedelta(days=days)).isoformat()


def _make_big_app(tmp_path):
    d = _open(tmp_path)
    a = d.upsert_keyword("에어프라이어", category="가전", day="2026-08-01")
    b = d.upsert_keyword("선풍기", day="2026-08-02")
    d.insert_daily_stats(a, "2026-08-02", {
        "total_sim": 100, "total_date": 110, "fresh_ratio": 0.5,
        "shop_total": 500, "shop_avg_price": 35000, "shop_category": "가전",
        "growth": 0.27, "opportunity": 64.1, "commercial": None,
        "demand_idx": 0.005, "shop_click_idx": 0.9, "ai_cite_idx": 0.8})
    d.insert_daily_stats(b, "2026-08-02", {
        "total_sim": 10, "total_date": 10, "fresh_ratio": 0.0,
        "shop_total": 10, "shop_avg_price": 1000, "shop_category": "가전",
        "commercial": None, "opportunity": 30.0, "shop_click_idx": 0.1,
        "ai_cite_idx": 0.3})
    d.upsert_outline(a, "2026-08-02",
                     '{"questions": ["기준은?"], "comparisons": [], "facts": []}')
    d.close()
    return create_app({"db_url": f"sqlite:///{tmp_path / 't.db'}",
                       "dashboard_token": "sekret", "env": "development"})


# ---------- 실측 CPC/RPM → priority ----------

def test_measured_cpc_tier_updates_priority(tmp_path):
    # v18: 카테고리 실측 CPC(AdPost)가 표본 3건 이상이면 priority CPC 항을
    # 보정 — 정적 등급이 낮은(일상 0.3) 카테고리도 실측이 좋으면 상승
    d = _open(tmp_path)
    k = d.upsert_keyword("취미 글", category="일상", day="2026-08-01")
    for _ in range(3):
        did = d.insert_draft(k, "제목", "첫문단", "본문", created_at="2026-08-01")
        d.record_adpost_metrics(did, k, 3000.0, 1000, 1, 100.0,
                                "2026-08-05", "2026-08-05", 0)
    base = d.query_keywords(sort="priority", active=1)[0]["priority"]
    assert base == round(30.0 * 0.3, 1)  # 정적 등급 0.3 (스냅샷·boost 없음)
    d.refresh_category_cpc_stats("2026-08-06")
    row = d.category_cpc_stats_list()[0]
    assert row["category"] == "일상"
    assert row["posts"] == 3 and row["cpc"] == 3000.0
    assert row["rpm"] == 3000.0  # 3000/1000*1000
    assert row["measured_tier"] == 0.65  # 0.5*0.3 + 0.5*min(1, 3000/3000)
    # v20: 베이지안 스무딩 (prior=3) — (3*0.3 + 3*0.65)/(3+3)=0.475 → 14.25
    # SQL ROUND는 half-away(14.3), Python round는 banker's(14.2) — SQL 값 기준
    after = d.query_keywords(sort="priority", active=1)[0]["priority"]
    assert after == 14.3
    d.close()


def test_measured_tier_needs_min_posts(tmp_path):
    # v18: 표본 3건 미만이어도 v20 베이지안 스무딩으로 일부 반영
    # v20: (prior=3) posts=2 → (3*0.4 + 2*0.7)/(3+2)=0.52 → priority 15.6
    # 여행 measured_tier = 0.5*0.4+0.5*1.0=0.7
    d = _open(tmp_path)
    k = d.upsert_keyword("여행 후기", category="여행", day="2026-08-01")
    for _ in range(2):
        did = d.insert_draft(k, "제목", "첫문단", "본문", created_at="2026-08-01")
        d.record_adpost_metrics(did, k, 3000.0, 1000, 1, 100.0,
                                "2026-08-05", "2026-08-05", 0)
    d.refresh_category_cpc_stats("2026-08-06")
    row = d.category_cpc_stats_list()[0]
    assert row["posts"] == 2 and row["measured_tier"] is not None
    priority = d.query_keywords(sort="priority", active=1)[0]["priority"]
    assert priority == round(30.0 * 0.52, 1)  # 베이지안 스무딩 (3*0.4+2*0.7)/5
    d.close()


def test_measured_cpc_stats_refreshed_on_import(tmp_path, monkeypatch):
    # v18: AdPost 임포트 후 category_cpc_stats 재집계 → /revenue-insights에 반영
    client = TestClient(_make_big_app(tmp_path))
    monkeypatch.setattr(draft_pipeline, "generate_two_pass",
                        lambda k, s, **kw: (
                            {"title": "제목", "first_paragraph": "첫문단",
                             "body": "## 소제목\n본문"}, []))
    did = client.post("/drafts", json={"keyword_id": 1}).json()["id"]
    client.post(f"/drafts/{did}/published-url",
                json={"url": "https://blog.naver.com/a/1"})
    csv = ("게시물 제목,URL,수익(원),노출수,클릭수\n"
           "제목,https://blog.naver.com/a/1,3000,1000,1\n").encode("utf-8-sig")
    client.post("/adpost/import", files={"file": ("r.csv", csv, "text/csv")})
    insights = client.get("/revenue-insights").json()
    cats = {c["category"]: c for c in insights["categories"]}
    assert "가전" in cats
    assert cats["가전"]["measured_tier"] == 0.75  # 0.5*0.5(가전 ELSE) + 0.5*1.0
    d = _open(tmp_path)
    assert d.category_cpc_stats_list()[0]["posts"] == 1
    d.close()


# ---------- 게시 플래너 ----------

def test_publish_plan_orders_images_first(tmp_path):
    d = _open(tmp_path)
    a = d.upsert_keyword("에어프라이어", category="가전", day="2026-08-01")
    d.insert_daily_stats(a, "2026-08-02", {
        "total_sim": 100, "total_date": 110, "fresh_ratio": 0.5,
        "growth": 0.27, "opportunity": 64.1, "demand_idx": 0.005,
        "shop_click_idx": 0.9, "ai_cite_idx": 0.8, "commercial": None})
    no_img = d.insert_draft(a, "이미지 없는 글", "첫문단",
                            "## 섹션1\n본문\n\n## 섹션2\n본문\n\n## 자주 묻는 질문\n질문",
                            created_at="2026-08-01")
    d.insert_draft(a, "이미지 있는 글", "첫문단", "## 섹션A\n본문", image_url="https://cdn.example.com/a.png",
                   created_at="2026-08-01")
    plan = d.publish_plan(10)
    assert [p["draft_id"] for p in plan] == [no_img + 1, no_img]  # 이미지 있는 글 우선
    assert plan[1]["has_main_image"] is False
    assert plan[1]["section_images_needed"] == 2  # FAQ 제외
    assert plan[1]["section_images_ready"] == 0
    d.close()


def test_planner_endpoint_shape(tmp_path, monkeypatch):
    client = TestClient(_make_big_app(tmp_path))
    monkeypatch.setattr(draft_pipeline, "generate_two_pass",
                        lambda k, s, **kw: (
                            {"title": "제목", "first_paragraph": "첫문단",
                             "body": "## 소제목\n본문"}, []))
    client.post("/drafts", json={"keyword_id": 1})
    body = client.get("/planner").json()
    assert len(body["publish_queue"]) == 1
    assert body["publish_queue"][0]["title"] == "제목"
    assert "refresh_candidates" in body and "pattern" in body


# ---------- 저성과 리프레시 ----------

def test_refresh_candidates_filters(tmp_path):
    d = _open(tmp_path)
    k = d.upsert_keyword("보험 비교", category="보험", day="2026-06-01")
    ids = []
    for i, (published, score) in enumerate([
            (_old_day(20), 30.0),   # 후보
            (_old_day(20), 80.0),   # 성과 좋음 — 제외
            (_old_day(3), 30.0),    # 최근 게시 — 제외
            (_old_day(20), None),   # 성과 미기록 — 제외
    ]):
        did = d.insert_draft(k, f"제목{i}", "첫문단", "본문",
                             created_at="2026-06-05")
        d.record_draft_feedback(did, k, published, score, "", "2026-08-01", 0)
        ids.append(did)
    d.mark_draft_refreshed(ids[0], "2026-08-01")  # 이미 리프레시 — 제외
    cands = d.refresh_candidates(10)
    assert [c["id"] for c in cands] == []
    d2 = _open(tmp_path)  # 새 인스턴스로 원복 확인
    k2 = d2.upsert_keyword("보험 비교", category="보험", day="2026-06-01")
    did2 = d2.insert_draft(k2, "후보", "첫문단", "본문", created_at="2026-06-05")
    d2.record_draft_feedback(did2, k2, _old_day(20), 30.0, "", "2026-08-01", 0)
    cands2 = d2.refresh_candidates(10)
    assert [c["id"] for c in cands2] == [did2]
    d.close()
    d2.close()


def test_refresh_draft_endpoint(tmp_path, monkeypatch):
    # v18: 리프레시 — 같은 키워드 새 초안 + 원본 refreshed_at 기록 + 재시도 차단
    client = TestClient(_make_big_app(tmp_path))
    monkeypatch.setattr(draft_pipeline, "generate_two_pass",
                        lambda k, s, **kw: (
                            {"title": "리프레시된 제목", "first_paragraph": "첫문단",
                             "body": "## 소제목\n본문"}, []))
    did = client.post("/drafts", json={"keyword_id": 1}).json()["id"]
    d = _open(tmp_path)
    d.record_draft_feedback(did, 1, _old_day(20), 30.0, "", "2026-08-01", 0)
    d.close()
    r = client.post(f"/drafts/{did}/refresh")
    assert r.status_code == 200
    new = r.json()
    assert new["id"] != did and new["refresh_of"] == did
    d = _open(tmp_path)
    assert d.get_draft(did)["refreshed_at"] != ""
    d.close()
    # 이미 리프레시된 초안은 거부
    assert client.post(f"/drafts/{did}/refresh").status_code == 400
    # 없는 초안 404
    assert client.post("/drafts/9999/refresh").status_code == 404


# ---------- 성과 상위 패턴 ----------

def test_top_performer_pattern_needs_sample(tmp_path):
    d = _open(tmp_path)
    k = d.upsert_keyword("보험 비교", category="보험", day="2026-06-01")
    body = ("## 섹션1\n본문에 표 포함 | 10 |\n\n"
            "## 섹션2\n본문\n\n## 자주 묻는 질문\n### 질문\n답변")
    for i in range(9):
        did = d.insert_draft(k, f"제목{i}", "첫문단", body, created_at="2026-06-05")
        d.record_draft_feedback(did, k, _old_day(i + 5), 75.0, "", "2026-08-01", 10)
    assert d.top_performer_pattern() is None  # 9 < 10
    did = d.insert_draft(k, "제목10", "첫문단", body, created_at="2026-06-05")
    d.record_draft_feedback(did, k, _old_day(1), 75.0, "", "2026-08-01", 10)
    p = d.top_performer_pattern()
    assert p is not None and p["sample"] == 10
    assert p["title_len_avg"] == 3.1  # 제목0~8(3자)×9 + 제목10(4자) → 31/10
    assert p["h2_count_avg"] == 2.0   # FAQ 제외 H2 2개
    assert p["table_pct"] == 100 and p["faq_pct"] == 100
    d.close()


def test_pattern_guidance_injected_into_prompts(monkeypatch):
    # v18: 표본 충분 시 패턴 가이드가 1/2패스 프롬프트에 주입 (없으면 미주입)
    import json as json_mod
    captured = []

    def fake_run(prompt, timeout=90):
        captured.append(prompt)
        return '{"h2s":[{"title":"기준","bullets":["b"]}]}'

    pattern = {"sample": 10, "title_len_avg": 27.0, "first_paragraph_len_avg": 120.0,
               "body_len_avg": 4000, "h2_count_avg": 5.0, "table_pct": 90, "faq_pct": 80}
    draft_pipeline.pass1_outline("보험 비교", {}, runner=fake_run,
                                 pattern_guidance=pattern)
    assert "성과 상위 글 패턴" in captured[0]
    assert "제목 27.0자" in captured[0]

    captured.clear()
    draft_pipeline.pass1_outline("보험 비교", {}, runner=fake_run)
    assert "성과 상위 글 패턴" not in captured[0]

    def fake_run2(prompt, timeout=90):
        captured.append(prompt)
        return json_mod.dumps({"title": "제목", "first_paragraph": "첫문단 30자 이상 작성",
                               "body": "본문"}, ensure_ascii=False)

    captured.clear()
    draft_pipeline.pass2_expand("보험 비교", [{"title": "기준", "bullets": ["b"]}],
                                "info", runner=fake_run2, pattern_guidance=pattern)
    assert "성과 상위 글 패턴" in captured[0]


# ---------- 수익 인사이트 ----------

def test_revenue_insights_aggregates(tmp_path):
    d = _open(tmp_path)
    a = d.upsert_keyword("보험 비교", category="보험", day="2026-06-01")
    b = d.upsert_keyword("일상 글", category="일상", day="2026-06-01")
    did1 = d.insert_draft(a, "글1", "첫문단", "본문", created_at="2026-06-05")
    d.record_adpost_metrics(did1, a, 1000.0, 500, 2, 90.0,
                            "2026-07-10", "2026-07-10", 10)
    did2 = d.insert_draft(a, "글2", "첫문단", "본문", created_at="2026-07-01")
    d.record_adpost_metrics(did2, a, 2000.0, 1000, 4, 95.0,
                            "2026-08-02", "2026-08-02", 10)
    did3 = d.insert_draft(b, "글3", "첫문단", "본문", created_at="2026-07-10")
    d.record_adpost_metrics(did3, b, 500.0, 100, 1, 80.0,
                            "2026-08-05", "2026-08-05", 0)
    d.refresh_category_cpc_stats("2026-08-06")
    ins = d.revenue_insights()
    assert ins["totals"]["posts"] == 3
    assert ins["totals"]["revenue"] == 3500.0
    assert ins["totals"]["clicks"] == 7
    months = {m["month"]: m["revenue"] for m in ins["monthly"]}
    assert months == {"2026-07": 1000.0, "2026-08": 2500.0}
    assert ins["top_keywords"][0]["keyword"] == "보험 비교"
    assert ins["top_keywords"][0]["revenue"] == 3000.0
    cats = {c["category"]: c for c in ins["categories"]}
    assert cats["보험"]["cpc"] == 500.0   # 3000/6
    assert cats["보험"]["measured_tier"] == round(0.5 * 1.0 + 0.5 * (500.0 / 3000.0), 3)
    assert cats["일상"]["cpc"] == 500.0
    d.close()


def test_revenue_insights_consistent_filters(tmp_path):
    # R-4: totals/monthly/top_keywords 집계 기준 통일 — 수익만 있고 노출·클릭이
    # NULL인 글이 monthly에만 잡히면 합계가 어긋난다 (totals와 불일치)
    d = _open(tmp_path)
    k = d.upsert_keyword("부분지표", category="일상", day="2026-06-01")
    did = d.insert_draft(k, "부분글", "첫문단", "본문", created_at="2026-07-01")
    # 부분 지표: 수익만 기록 (노출/클릭 NULL) — record_adpost_metrics는 3지표 필수라 직접 UPDATE
    d._qd("UPDATE drafts SET adpost_revenue = 5000.0, "
          "published_at = '2026-07-15' WHERE id = ?", (did,))
    ins = d.revenue_insights()
    assert ins["totals"]["posts"] == 0        # 3지표 모두 있는 글만 합산
    assert ins["totals"]["revenue"] == 0.0
    monthly_total = sum((m["revenue"] or 0) for m in ins["monthly"])
    assert monthly_total == ins["totals"]["revenue"]  # 월별 합계 = 전체 합계
    assert ins["top_keywords"] == []          # 부분 지표 글은 기여 집계 제외
    d.close()


def test_revenue_insights_endpoint_auth(tmp_path):
    client = TestClient(_make_big_app(tmp_path))
    assert client.get("/revenue-insights").json()["totals"]["posts"] == 0
    prod = TestClient(create_app({"db_url": f"sqlite:///{tmp_path / 't.db'}",
                                  "dashboard_token": "sekret", "env": "production"}))
    assert prod.get("/revenue-insights").status_code == 401
