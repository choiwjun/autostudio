import collect
import db
from fastapi.testclient import TestClient
from server import create_app

AUTH = {"Authorization": "Bearer sekret"}


def make_app(tmp_path):
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
        "commercial": 100.0})
    d.insert_daily_stats(a, "2026-08-02", {
        "total_sim": 130, "total_date": 140, "fresh_ratio": 0.5,
        "shop_total": 520, "shop_avg_price": 35000, "shop_category": "가전",
        "growth": 0.27, "opportunity": 64.1, "commercial": 100.0,
        "demand_idx": 0.08})
    d.insert_daily_stats(b, "2026-08-02", {
        "total_sim": 10, "total_date": 10, "fresh_ratio": 0.0,
        "shop_total": 10, "shop_avg_price": 1000, "shop_category": "가전",
        "commercial": 2.5, "opportunity": 30.0})  # v3: 정렬 방향 검증용 점수 추가
    d.insert_daily_stats(c, "2026-08-02", {
        "total_sim": 5, "total_date": 5, "shop_category": "디지털",
        "commercial": 0.0})
    d.close()
    return create_app({"db_url": dbfile, "dashboard_token": "sekret",
                       "manual_budget_seconds": 45, "env": "development"})


def test_list_reads_precomputed_scores(tmp_path):
    client = TestClient(make_app(tmp_path))
    body = client.get("/keywords").json()
    assert body["count"] == 2                 # 비활성 제외
    item = body["items"][0]
    assert item["keyword"] == "에어프라이어"   # 기회점수 NULL은 뒤로
    assert item["opportunity"] == 64.1        # 저장값 그대로 (조회 시 재계산 없음)
    assert item["growth"] == 0.27
    assert item["demand_idx"] == 0.08
    assert item["days"] == 2


def test_paging(tmp_path):
    client = TestClient(make_app(tmp_path))
    body = client.get("/keywords?page_size=1").json()
    assert body["count"] == 2
    assert len(body["items"]) == 1
    body2 = client.get("/keywords?page_size=1&page=2").json()
    assert body2["items"][0]["keyword"] == "선풍기"
    assert client.get("/keywords?page_size=1&page=3").json()["items"] == []


def test_filters(tmp_path):
    client = TestClient(make_app(tmp_path))
    assert client.get("/keywords?commercial_min=50").json()["count"] == 1
    body = client.get("/keywords?q=선풍").json()
    assert [i["keyword"] for i in body["items"]] == ["선풍기"]
    assert client.get("/keywords?show_inactive=1").json()["count"] == 3


def test_detail_404_and_history_with_scores(tmp_path):
    client = TestClient(make_app(tmp_path))
    assert client.get("/keywords/999").status_code == 404
    body = client.get("/keywords/1").json()
    assert body["keyword"] == "에어프라이어"
    assert len(body["history"]) == 2
    assert body["history"][1]["opportunity"] == 64.1  # 점수 추이 그래프용


def test_patch_active_requires_token_and_toggles(tmp_path):
    client = TestClient(make_app(tmp_path))
    assert client.patch("/keywords/1", json={"active": False}).status_code == 401
    resp = client.patch("/keywords/1", json={"active": False}, headers=AUTH)
    assert resp.status_code == 200
    assert client.get("/keywords").json()["count"] == 1


def test_seed_writes_require_token(tmp_path):
    client = TestClient(make_app(tmp_path))
    assert client.post("/seeds", json={"keyword": "새시드"}).status_code == 401
    assert client.post("/seeds", json={"keyword": "새시드", "category": "육아"},
                       headers=AUTH).status_code == 200
    seeds = client.get("/seeds").json()
    assert len(seeds) == 2
    assert client.delete(f"/seeds/{seeds[1]['id']}", headers=AUTH).status_code == 200


def test_collect_trigger_is_manual_and_budgeted(tmp_path, monkeypatch):
    client = TestClient(make_app(tmp_path))
    assert client.post("/collect").status_code == 401
    captured = {}

    def fake_run(cfg, trigger="schedule", budget_seconds=None):
        captured.update(trigger=trigger, budget=budget_seconds)
        return {"locked": False, "new_keywords": 0, "snapshotted": 0,
                "errors": [], "partial": False}

    monkeypatch.setattr(collect, "run_collection", fake_run)
    resp = client.post("/collect", headers=AUTH)
    assert resp.status_code == 200
    assert captured["trigger"] == "manual"
    assert captured["budget"] == 45


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
    # v3: 정렬 토글(sort_dir) + 유망 프리셋(preset=promising) — UX §6·§8 계약
    client = TestClient(make_app(tmp_path))
    desc = client.get("/keywords?sort=opportunity").json()
    assert [i["keyword"] for i in desc["items"]] == ["에어프라이어", "선풍기"]
    asc = client.get("/keywords?sort=opportunity&sort_dir=asc").json()
    assert [i["keyword"] for i in asc["items"]] == ["선풍기", "에어프라이어"]
    # 유망 = 기회≥70 & 상업성≥60 & 수요≥0.01 → 픽스처 최고 64.1 → 0건 (서버 필터 확인)
    assert client.get("/keywords?preset=promising").json()["count"] == 0


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
