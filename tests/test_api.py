import collect
import db
from fastapi.testclient import TestClient
from server import create_app

AUTH = {"Authorization": "Bearer sekret"}


def make_app(tmp_path, env="development"):
    dbfile = f"sqlite:///{tmp_path / 't.db'}"
    d = db.Database(dbfile)
    d.init()
    a = d.upsert_keyword("에어프라이어", category="가전", day="2026-08-01")
    b = d.upsert_keyword("선풍기", day="2026-08-02")
    c = d.upsert_keyword("퇴역키워드", day="2026-08-01")
    d.set_active(c, 0)
    d.add_seed("에어프라이어", "요리")
    d.insert_daily_stats(a, "2026-08-01", {
        "total_sim": 100, "total_date": 110, "fresh_ratio": 0.3,
        "shop_total": 500, "shop_avg_price": 35000, "shop_category": "가전",
        "commercial": None})
    d.insert_daily_stats(a, "2026-08-02", {
        "total_sim": 130, "total_date": 140, "fresh_ratio": 0.5,
        "shop_total": 520, "shop_avg_price": 35000, "shop_category": "가전",
        "growth": 0.27, "opportunity": 64.1, "commercial": None,
        "demand_idx": 0.5, "shop_click_idx": 0.9, "ai_cite_idx": 0.8})  # v6: ai_pick 프리셋 통과
    d.insert_daily_stats(b, "2026-08-02", {
        "total_sim": 10, "total_date": 10, "fresh_ratio": 0.0,
        "shop_total": 10, "shop_avg_price": 1000, "shop_category": "가전",
        "commercial": None, "opportunity": 30.0, "shop_click_idx": 0.1,
        "ai_cite_idx": 0.3})  # v3/v4/v6: ai_pick 미달 (ai_cite<0.6)
    d.insert_daily_stats(c, "2026-08-02", {
        "total_sim": 5, "total_date": 5, "shop_category": "디지털",
        "commercial": None})
    # v9: 초안 생성은 골격 선행 필수 — 테스트용 기본 골격 (keyword_id=1)
    d.upsert_outline(1, "2026-08-02",
                     '{"questions": ["에어프라이어 추천 기준은?"], "comparisons": [], "facts": []}')
    d.close()
    return create_app({"db_url": dbfile, "dashboard_token": "sekret",
                       "manual_budget_seconds": 45, "env": env})


def test_list_reads_precomputed_scores(tmp_path):
    client = TestClient(make_app(tmp_path))
    body = client.get("/keywords?preset=").json()  # v6: 기본 프리셋(ai_pick) 회피 — 전체 목록
    assert body["count"] == 2                 # 비활성 제외
    item = body["items"][0]
    assert item["keyword"] == "에어프라이어"   # 기회점수 NULL은 뒤로
    assert item["opportunity"] == 64.1        # 저장값 그대로 (조회 시 재계산 없음)
    assert item["growth"] == 0.27
    assert item["demand_idx"] == 0.5
    assert item["shop_click_idx"] == 0.9      # v4: 쇼핑 클릭 지수
    assert item["ai_cite_idx"] == 0.8         # v6: AI 인용 가능성
    assert item["days"] == 2


def test_default_preset_is_ai_pick(tmp_path):
    # v6: 기본 뷰 = '지금 써야 할 키워드' — ai_cite≥0.6 & demand≥0.2만 노출 (에어프라이어만 통과)
    client = TestClient(make_app(tmp_path))
    body = client.get("/keywords").json()
    assert body["count"] == 1
    assert body["items"][0]["keyword"] == "에어프라이어"
    assert body["items"][0]["priority"] is not None
    body2 = client.get("/keywords?sort=priority").json()
    assert body2["items"][0]["keyword"] == "에어프라이어"


def test_paging(tmp_path):
    client = TestClient(make_app(tmp_path))
    body = client.get("/keywords?preset=&page_size=1").json()
    assert body["count"] == 2
    assert len(body["items"]) == 1
    body2 = client.get("/keywords?preset=&page_size=1&page=2").json()
    assert body2["items"][0]["keyword"] == "선풍기"
    assert client.get("/keywords?preset=&page_size=1&page=3").json()["items"] == []


def test_filters(tmp_path):
    client = TestClient(make_app(tmp_path))
    assert client.get("/keywords?preset=&click_min=0.5").json()["count"] == 1  # v4
    body = client.get("/keywords?preset=&q=선풍").json()
    assert [i["keyword"] for i in body["items"]] == ["선풍기"]
    assert client.get("/keywords?preset=&show_inactive=1").json()["count"] == 3


def test_detail_404_and_history_with_scores(tmp_path):
    client = TestClient(make_app(tmp_path))
    assert client.get("/keywords/999").status_code == 404
    body = client.get("/keywords/1").json()
    assert body["keyword"] == "에어프라이어"
    assert len(body["history"]) == 2
    assert body["history"][1]["opportunity"] == 64.1  # 점수 추이 그래프용


def test_patch_active_requires_token_and_toggles(tmp_path):
    # v6: development는 인증 생략(README "로컬 개발만 인증 생략") — 프로덕션에서만 401
    client = TestClient(make_app(tmp_path))
    assert client.patch("/keywords/1", json={"active": False}).status_code == 200
    assert client.get("/keywords?preset=").json()["count"] == 1
    # 프로덕션: 무토큰 401, 올바른 토큰 200
    prod = TestClient(make_app(tmp_path, env="production"))
    assert prod.patch("/keywords/1", json={"active": True}).status_code == 401
    assert prod.patch("/keywords/1", json={"active": True}, headers=AUTH).status_code == 200


def test_seed_writes_require_token(tmp_path):
    # v6: development는 인증 생략 — 쓰기 동작 자체 검증
    client = TestClient(make_app(tmp_path))
    assert client.post("/seeds", json={"keyword": "새시드", "category": "육아"}).status_code == 200
    seeds = client.get("/seeds").json()
    assert len(seeds) == 2
    assert client.delete(f"/seeds/{seeds[1]['id']}").status_code == 200
    # 프로덕션: 무토큰 401
    prod = TestClient(make_app(tmp_path, env="production"))
    assert prod.post("/seeds", json={"keyword": "새시드"}).status_code == 401


def test_collect_trigger_is_manual_and_budgeted(tmp_path, monkeypatch):
    # v6: development는 인증 생략 — 프로덕션 401은 별도 검증
    client = TestClient(make_app(tmp_path))
    captured = {}

    def fake_run(cfg, trigger="schedule", budget_seconds=None):
        captured.update(trigger=trigger, budget=budget_seconds)
        return {"locked": False, "new_keywords": 0, "snapshotted": 0,
                "errors": [], "partial": False}

    monkeypatch.setattr(collect, "run_collection", fake_run)
    resp = client.post("/collect")
    assert resp.status_code == 200
    assert captured["trigger"] == "manual"
    assert captured["budget"] == 45
    # 프로덕션: 무토큰 401
    prod = TestClient(make_app(tmp_path, env="production"))
    assert prod.post("/collect").status_code == 401


def test_collect_schedule_trigger_runs_full_pipeline(tmp_path, monkeypatch):
    # v3: cron-job.org 대체 경로 — trigger=schedule은 발굴·수요·은퇴·보존까지 실행
    # (v2의 manual-only는 발굴/수요/은퇴/보존이 누락되어 스케줄러를 대체하지 못했음)
    client = TestClient(make_app(tmp_path))
    captured = {}

    def fake_run(cfg, trigger="schedule", budget_seconds=None):
        captured.update(trigger=trigger, budget=budget_seconds)
        return {"locked": False, "new_keywords": 0, "snapshotted": 0,
                "errors": [], "partial": False}

    monkeypatch.setattr(collect, "run_collection", fake_run)
    resp = client.post("/collect", json={"trigger": "schedule"}, headers=AUTH)
    assert resp.status_code == 200
    assert captured["trigger"] == "schedule"
    assert captured["budget"] == 45  # Vercel 60초 한도 내 예산 (전 구간 적용)


def test_sort_dir_and_promising_preset(tmp_path):
    # v3/v4: 정렬 토글(sort_dir) + 유망 프리셋(preset=promising, 쇼핑클릭 기준) — UX §6·§8 계약
    # v6: 기본 프리셋이 ai_pick이므로 전체 목록은 preset= 명시
    client = TestClient(make_app(tmp_path))
    desc = client.get("/keywords?preset=&sort=opportunity").json()
    assert [i["keyword"] for i in desc["items"]] == ["에어프라이어", "선풍기"]
    asc = client.get("/keywords?preset=&sort=opportunity&sort_dir=asc").json()
    assert [i["keyword"] for i in asc["items"]] == ["선풍기", "에어프라이어"]
    click = client.get("/keywords?preset=&sort=click").json()
    assert [i["keyword"] for i in click["items"]] == ["에어프라이어", "선풍기"]
    # v9: 유망 = 기회≥20 & 쇼핑클릭≥0.05 & 수요≥0.001 → 픽스처 1건 통과 (실측 분포 기반 임계 현실화)
    assert client.get("/keywords?preset=promising").json()["count"] == 1
    # v6: ai_pick 프리셋 = ai_cite≥0.6 & demand≥0.2 → 에어프라이어(0.8/0.5)만 통과
    assert client.get("/keywords?preset=ai_pick").json()["count"] == 1


def test_production_without_token_fails_closed(tmp_path):
    # v3: ENV=production + 토큰 미설정 → 기동 거부 (무인증 쓰기 API 방지, 스펙 §7)
    import pytest
    with pytest.raises(RuntimeError):
        create_app({"db_url": f"sqlite:///{tmp_path / 't.db'}",
                    "dashboard_token": "", "env": "production",
                    "manual_budget_seconds": 45})


def test_status(tmp_path):
    client = TestClient(make_app(tmp_path))
    body = client.get("/status").json()
    assert body["keyword_count"] == 2
    assert body["seed_count"] == 1
    assert "last_run" in body
    assert "last_success" in body


def test_categories(tmp_path):
    client = TestClient(make_app(tmp_path))
    assert "가전" in client.get("/categories").json()
    assert "요리" in client.get("/categories").json()  # v3: 시드 분야 포함


def test_outline_not_found(tmp_path):
    client = TestClient(make_app(tmp_path))
    assert client.get("/outlines/999").status_code == 404


def test_analyze_outline_requires_token(tmp_path):
    # v7: development는 인증 생략 — 프로덕션에서만 401
    prod = TestClient(make_app(tmp_path, env="production"))
    assert prod.post("/outlines/1").status_code == 401


def test_create_draft_requires_token_and_404(tmp_path):
    # v7: development는 인증 생략 — 404는 골격 없는 키워드 검증
    client = TestClient(make_app(tmp_path))
    r = client.post("/drafts", json={"keyword_id": 999})
    assert r.status_code == 404
    prod = TestClient(make_app(tmp_path, env="production"))
    assert prod.post("/drafts", json={"keyword_id": 1}).status_code == 401


def test_create_draft_mocks_generator(tmp_path, monkeypatch):
    # v7: 생성은 Mock — generate_two_pass가 (초안 dict, 검수 실패 목록) 반환
    def fake_generate(keyword, structure, **kwargs):
        return {"title": "제목", "first_paragraph": "첫문단", "body": "## 소제목\n본문"}, []

    import draft_pipeline
    monkeypatch.setattr(draft_pipeline, "generate_two_pass", fake_generate)
    client = TestClient(make_app(tmp_path))
    r = client.post("/drafts", json={"keyword_id": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "제목"
    assert body["keyword_id"] == 1
    assert body["status"] == "draft"
    assert body["created_at"].endswith("+09:00")


def test_get_draft(tmp_path, monkeypatch):
    import draft_pipeline
    monkeypatch.setattr(draft_pipeline, "generate_two_pass", lambda k, s, **kw: (
        {"title": "제목", "first_paragraph": "첫문단", "body": "본문"}, []))
    client = TestClient(make_app(tmp_path))
    did = client.post("/drafts", json={"keyword_id": 1}).json()["id"]
    body = client.get(f"/drafts/{did}").json()
    assert body["id"] == did
    assert body["title"] == "제목"
    assert client.get("/drafts/999").status_code == 404


def test_draft_image_no_key_returns_503(tmp_path, monkeypatch):
    # v7: 키 미발급 → 503 + 명확한 안내, 초안 데이터는 유지
    import draft_pipeline
    import image_gen
    monkeypatch.setattr(draft_pipeline, "generate_two_pass", lambda k, s, **kw: (
        {"title": "제목", "first_paragraph": "첫문단", "body": "본문"}, []))
    monkeypatch.delenv("BAILIAN_TOKEN_PLAN_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    client = TestClient(make_app(tmp_path))
    did = client.post("/drafts", json={"keyword_id": 1}).json()["id"]
    r = client.post(f"/drafts/{did}/image")
    assert r.status_code == 503
    assert "이미지 키" in r.json()["detail"]
    assert client.get(f"/drafts/{did}").json()["image_url"] == ""


def test_draft_image_success_updates_url(tmp_path, monkeypatch):
    # v7: 키 존재 + Mock runner → image_url 저장
    import draft_pipeline
    import image_gen
    monkeypatch.setattr(draft_pipeline, "generate_two_pass", lambda k, s, **kw: (
        {"title": "제목", "first_paragraph": "첫문단", "body": "본문"}, []))
    monkeypatch.setenv("BAILIAN_TOKEN_PLAN_API_KEY", "test-key")
    monkeypatch.setattr(image_gen, "_run_http", lambda prompt: "https://img.example.com/1.png")
    client = TestClient(make_app(tmp_path))
    did = client.post("/drafts", json={"keyword_id": 1}).json()["id"]
    body = client.post(f"/drafts/{did}/image").json()
    assert body["image_url"] == "https://img.example.com/1.png"


def test_draft_image_404(tmp_path):
    client = TestClient(make_app(tmp_path))
    assert client.post("/drafts/999/image").status_code == 404


def _priority_of(client, keyword):
    items = client.get("/keywords?preset=").json()["items"]
    return next(i["priority"] for i in items if i["keyword"] == keyword)


def test_feedback_idempotent_boost(tmp_path, monkeypatch):
    # v11: 같은 초안에 피드백 반복 전송 시 boost가 누적되지 않아야 함 (차액 가산)
    import draft_pipeline
    monkeypatch.setattr(draft_pipeline, "generate_two_pass", lambda k, s, **kw: (
        {"title": "제목", "first_paragraph": "첫문단", "body": "본문"}, []))
    client = TestClient(make_app(tmp_path))
    did = client.post("/drafts", json={"keyword_id": 1}).json()["id"]
    base = _priority_of(client, "에어프라이어")

    for _ in range(2):  # 동일 점수 2회 — boost는 +10 한 번분만
        r = client.post(f"/drafts/{did}/feedback", json={"performance_score": 80})
        assert r.status_code == 200
        assert r.json()["status"] == "published"
    assert _priority_of(client, "에어프라이어") == base + 10

    # 점수 하향 재입력 — +10 → -10 차액 반영
    client.post(f"/drafts/{did}/feedback", json={"performance_score": 20})
    assert _priority_of(client, "에어프라이어") == base - 10

    # 중간 점수(30~69)는 보너스 없음 — 기존 boost 회수
    client.post(f"/drafts/{did}/feedback", json={"performance_score": 50})
    assert _priority_of(client, "에어프라이어") == base
