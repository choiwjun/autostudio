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
        "demand_idx": 0.005, "shop_click_idx": 0.9, "ai_cite_idx": 0.8})  # v12: demand는 v9 실측 스케일(0~0.01)
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
    assert item["demand_idx"] == 0.005
    assert item["shop_click_idx"] == 0.9      # v4: 쇼핑 클릭 지수
    assert item["ai_cite_idx"] == 0.8         # v6: AI 인용 가능성
    assert item["days"] == 2


def test_default_preset_is_ai_pick(tmp_path):
    # v6: 기본 뷰 = '지금 써야 할 키워드' — ai_cite≥0.6 & demand≥0.001만 노출 (에어프라이어만 통과)
    # v14: 임계는 백분위 — 표본 2개(< 20)라 폴백 절대값(0.6/0.001) 적용 → 결과 동일
    client = TestClient(make_app(tmp_path))
    body = client.get("/keywords").json()
    assert body["count"] == 1
    assert body["items"][0]["keyword"] == "에어프라이어"
    # v14: priority = 30×0.8 + 25×(0.005/0.01) + 15×0(growth NULL) + 30×0.5(가전 기본)
    assert body["items"][0]["priority"] == 51.5
    body2 = client.get("/keywords?sort=priority").json()
    assert body2["items"][0]["keyword"] == "에어프라이어"
    # v14: thresholds 응답 — 폴백이어도 필드는 항상 포함 (대시보드 배지 공용 소스)
    assert body["thresholds"] == {"ai_cite": 0.6, "demand": 0.001, "opportunity": 20.0}
    assert body["threshold_source"] == "fallback"


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
    # v9: 유망 = 기회≥20 & 수요≥0.001 (쇼핑클릭 필터는 교집합 0건으로 제거) → 픽스처 1건 통과
    assert client.get("/keywords?preset=promising").json()["count"] == 1
    # v6/v12: ai_pick 프리셋 = ai_cite≥0.6 & demand≥0.001 → 에어프라이어(0.8/0.005)만 통과
    assert client.get("/keywords?preset=ai_pick").json()["count"] == 1


def test_production_without_token_fails_closed(tmp_path):
    # v3: ENV=production + 토큰 미설정 → 기동 거부 (무인증 쓰기 API 방지, 스펙 §7)
    import pytest
    with pytest.raises(RuntimeError):
        create_app({"db_url": f"sqlite:///{tmp_path / 't.db'}",
                    "dashboard_token": "", "env": "production",
                    "manual_budget_seconds": 45})


def test_env_case_variant_also_fails_closed(tmp_path):
    # v15: 'Production' 대소문자 변형으로 fail-closed를 우회하던 경로 차단
    import pytest
    with pytest.raises(RuntimeError):
        create_app({"db_url": f"sqlite:///{tmp_path / 't.db'}",
                    "dashboard_token": "", "env": "Production",
                    "manual_budget_seconds": 45})


def test_production_reads_require_token(tmp_path):
    # v15: 읽기 API도 인증 — 수익 전략 데이터(키워드·성과) 공개 금지
    client = TestClient(make_app(tmp_path, env="production"))
    for path in ("/keywords", "/keywords/1", "/seeds", "/status", "/categories"):
        assert client.get(path).status_code == 401, path
        assert client.get(path, headers=AUTH).status_code == 200, path


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


def test_create_draft_saves_and_returns_tags(tmp_path, monkeypatch):
    # v17.2: 생성된 태그는 DB 저장·응답에서 파싱된 리스트로 반환
    import draft_pipeline

    def fake_generate(keyword, structure, **kwargs):
        return {"title": "제목", "first_paragraph": "첫문단", "body": "## 소제목\n본문",
                "tags": ["여름 휴가 추천", "국내 여행"]}, []

    monkeypatch.setattr(draft_pipeline, "generate_two_pass", fake_generate)
    client = TestClient(make_app(tmp_path))
    r = client.post("/drafts", json={"keyword_id": 1})
    assert r.status_code == 200
    assert r.json()["tags"] == ["여름 휴가 추천", "국내 여행"]
    did = r.json()["id"]
    assert client.get(f"/drafts/{did}").json()["tags"] == ["여름 휴가 추천", "국내 여행"]


def test_create_draft_without_tags_returns_empty_list(tmp_path, monkeypatch):
    # v17.2: tags 없는 초안은 빈 리스트로 정규화
    import draft_pipeline

    def fake_generate(keyword, structure, **kwargs):
        return {"title": "제목", "first_paragraph": "첫문단", "body": "## 소제목\n본문"}, []

    monkeypatch.setattr(draft_pipeline, "generate_two_pass", fake_generate)
    client = TestClient(make_app(tmp_path))
    r = client.post("/drafts", json={"keyword_id": 1})
    assert r.status_code == 200
    assert r.json()["tags"] == []


def test_create_draft_passes_fresh_search_evidence(tmp_path, monkeypatch):
    import draft_pipeline
    import server

    evidence = {
        "status": "available",
        "searched_at_kst": "2026-08-06T10:00:00+09:00",
        "reference_date": "2026-08-06",
        "items": [{"source": "news", "rank": 1,
                    "title": "최신 뉴스", "description": "최신 내용"}],
    }
    captured = {}

    monkeypatch.setattr(server, "_latest_search_snapshot", lambda cfg, keyword, day: (
        {"top_descriptions": ["최신 내용"]}, evidence))

    def fake_generate(keyword, structure, **kwargs):
        captured.update(structure=structure, kwargs=kwargs)
        return {"title": "최신 제목", "first_paragraph": "최신 첫문단",
                "body": "## 소제목\n본문"}, []

    monkeypatch.setattr(draft_pipeline, "generate_two_pass", fake_generate)
    client = TestClient(make_app(tmp_path))
    r = client.post("/drafts", json={"keyword_id": 1})
    assert r.status_code == 200
    assert captured["kwargs"]["search_evidence"] == evidence
    assert captured["kwargs"]["current_date"].isoformat()
    assert "최신 내용" in captured["structure"]
    assert "search_evidence_unavailable" not in r.json().get("quality_warnings", [])


def test_create_draft_warns_when_fresh_search_is_unavailable(tmp_path, monkeypatch):
    import draft_pipeline

    def fake_generate(keyword, structure, **kwargs):
        assert kwargs["search_evidence"]["status"] == "unavailable"
        assert "search_evidence" in structure
        return {"title": "제목", "first_paragraph": "첫문단", "body": "## 소제목\n본문"}, []

    monkeypatch.setattr(draft_pipeline, "generate_two_pass", fake_generate)
    client = TestClient(make_app(tmp_path))
    r = client.post("/drafts", json={"keyword_id": 1})
    assert r.status_code == 200
    assert "search_evidence_unavailable" in r.json()["quality_warnings"]


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
    # v15: image_gen이 timeout을 실제로 전달 — 목도 시그니처 정합 필요
    monkeypatch.setattr(image_gen, "_run_http",
                        lambda prompt, timeout=55: "https://img.example.com/1.png")
    client = TestClient(make_app(tmp_path))
    did = client.post("/drafts", json={"keyword_id": 1}).json()["id"]
    body = client.post(f"/drafts/{did}/image").json()
    assert body["image_url"] == "https://img.example.com/1.png"


def test_draft_image_404(tmp_path):
    client = TestClient(make_app(tmp_path))
    assert client.post("/drafts/999/image").status_code == 404


def make_big_app(tmp_path, n=24):
    # v14: 백분위 유효 표본(≥20) 픽스처 — 지표가 i에 따라 선형 증가
    dbfile = f"sqlite:///{tmp_path / 'big.db'}"
    d = db.Database(dbfile)
    d.init()
    for i in range(n):
        kid = d.upsert_keyword(f"키워드{i:02d}", day="2026-08-01")
        d.insert_daily_stats(kid, "2026-08-02", {
            "total_sim": 100,
            "ai_cite_idx": i / 100.0,
            "demand_idx": round(i * 0.0004, 4),
            "opportunity": float(i),
            "demand_growth": round(-0.05 + i * 0.01, 4),
        })
    d.close()
    return create_app({"db_url": dbfile, "dashboard_token": "sekret",
                       "manual_budget_seconds": 45, "env": "development"})


def test_percentile_presets_with_enough_sample(tmp_path):
    # v14 §3: 표본 ≥ 20이면 백분위 임계 — ai픽 = ai_cite≥P50 & demand≥P50,
    # 유망 = opportunity≥P75 & demand≥P50, 상승 = growth≥0.1 & demand≥P50
    client = TestClient(make_big_app(tmp_path))
    body = client.get("/keywords").json()
    assert body["threshold_source"] == "percentile"
    # n=24 → P50 idx 12, P75 idx 17
    assert body["thresholds"]["ai_cite"] == 0.12
    assert body["thresholds"]["demand"] == 0.0048
    assert body["thresholds"]["opportunity"] == 17.0
    assert body["count"] == 12                    # i ≥ 12 (ai·demand 모두 충족)
    prom = client.get("/keywords?preset=promising").json()
    assert prom["count"] == 7                     # i ≥ 17 (opp≥17 & demand≥0.0048)
    rising = client.get("/keywords?preset=rising").json()
    assert rising["count"] == 9                   # growth≥0.1 → i ≥ 15


def test_q_escapes_like_wildcards(tmp_path):
    # v14: 검색어의 %/_는 리터럴 — 와일드카드 전체 매치 방지
    client = TestClient(make_app(tmp_path))
    assert client.get("/keywords?preset=&q=%25").json()["count"] == 0
    assert client.get("/keywords?preset=&q=%EC%84%A0%ED%92%8D").json()["count"] == 1  # '선풍'


def _priority_of(client, keyword):
    items = client.get("/keywords?preset=").json()["items"]
    return next(i["priority"] for i in items if i["keyword"] == keyword)


# ---------- v15.1: 이미지 다운로드 프록시 ----------

def _create_draft(client, monkeypatch, body_md="## 소제목\n본문"):
    import draft_pipeline
    monkeypatch.setattr(draft_pipeline, "generate_two_pass", lambda k, s, **kw: (
        {"title": "제목", "first_paragraph": "첫문단", "body": body_md}, []))
    return client.post("/drafts", json={"keyword_id": 1}).json()["id"]


class _FakeImageResp:
    def __init__(self, content=b"PNGDATA", status_code=200,
                 content_type="image/png"):
        self._content = content
        self.status_code = status_code
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def iter_content(self, chunk_size=65536):
        return [self._content]


def test_download_endpoints_require_token_in_production(tmp_path):
    # v15.1: 다운로드 프록시도 읽기 API — 프로덕션에서 토큰 필수
    client = TestClient(make_app(tmp_path, env="production"))
    assert client.get("/drafts/1/image-download").status_code == 401
    assert client.get("/drafts/1/section-images/0/download").status_code == 401
    assert client.get("/drafts/1/image-download", headers=AUTH).status_code == 404
    # (초안 없음 404 — 인증은 통과했다는 뜻)


def test_image_download_proxy_serves_attachment(tmp_path, monkeypatch):
    # v15.1: DB 저장 URL을 attachment로 되돌림 — 파일명 고정, content-type 유지
    import server as server_mod
    client = TestClient(make_app(tmp_path))
    did = _create_draft(client, monkeypatch)
    import image_gen
    monkeypatch.setenv("BAILIAN_TOKEN_PLAN_API_KEY", "test-key")
    monkeypatch.setattr(image_gen, "_run_http",
                        lambda prompt, timeout=55: "https://cdn.example.com/img.png")
    assert client.post(f"/drafts/{did}/image").status_code == 200

    monkeypatch.setattr(server_mod.requests, "get",
                        lambda url, **kw: _FakeImageResp(b"PNGDATA"))
    r = client.get(f"/drafts/{did}/image-download")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/png")
    assert 'attachment; filename="blog-representative.png"' \
        in r.headers["content-disposition"]
    assert r.content == b"PNGDATA"


def test_image_download_error_paths(tmp_path, monkeypatch):
    import db as db_mod
    import server as server_mod
    client = TestClient(make_app(tmp_path))
    assert client.get("/drafts/999/image-download").status_code == 404
    did = _create_draft(client, monkeypatch)
    assert client.get(f"/drafts/{did}/image-download").status_code == 404  # 미생성
    assert client.get(f"/drafts/{did}/section-images/0/download").status_code == 404
    # HTTPS가 아닌 URL은 프록시 거부 (이미지 URL 오염 방어)
    d = db_mod.Database(f"sqlite:///{tmp_path / 't.db'}")
    d.update_draft_image(did, "http://insecure.example.com/x.png", "")
    d.close()
    assert client.get(f"/drafts/{did}/image-download").status_code == 400


def test_image_download_rejects_non_image_upstream(tmp_path, monkeypatch):
    # upstream이 HTML 에러 페이지를 주면 .png로 저장되지 않고 502
    import server as server_mod
    client = TestClient(make_app(tmp_path))
    did = _create_draft(client, monkeypatch)
    import image_gen
    monkeypatch.setenv("BAILIAN_TOKEN_PLAN_API_KEY", "test-key")
    monkeypatch.setattr(image_gen, "_run_http",
                        lambda prompt, timeout=55: "https://cdn.example.com/img.png")
    assert client.post(f"/drafts/{did}/image").status_code == 200
    monkeypatch.setattr(server_mod.requests, "get",
                        lambda url, **kw: _FakeImageResp(b"<html>", content_type="text/html"))
    assert client.get(f"/drafts/{did}/image-download").status_code == 502


def test_section_image_download_and_bounds(tmp_path, monkeypatch):
    import server as server_mod
    client = TestClient(make_app(tmp_path))
    did = _create_draft(client, monkeypatch)
    import image_gen
    monkeypatch.setenv("BAILIAN_TOKEN_PLAN_API_KEY", "test-key")
    monkeypatch.setattr(image_gen, "_run_http",
                        lambda prompt, timeout=55: "https://cdn.example.com/sec.png")
    assert client.post(f"/drafts/{did}/section-images").status_code == 200

    monkeypatch.setattr(server_mod.requests, "get",
                        lambda url, **kw: _FakeImageResp(b"SECDATA"))
    r = client.get(f"/drafts/{did}/section-images/0/download")
    assert r.status_code == 200
    assert 'blog-section-1.png' in r.headers["content-disposition"]
    assert r.content == b"SECDATA"
    assert client.get(f"/drafts/{did}/section-images/5/download").status_code == 404


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


# ---------- v17: 게시 파이프라인·AdPost 피드백 자동화 ----------

def test_published_url_set_and_validate(tmp_path, monkeypatch):
    client = TestClient(make_app(tmp_path))
    did = _create_draft(client, monkeypatch)
    assert client.post(f"/drafts/{did}/published-url",
                       json={"url": "not a url"}).status_code == 400
    r = client.post(f"/drafts/{did}/published-url",
                    json={"url": "https://blog.naver.com/a/1"})
    assert r.status_code == 200
    assert r.json()["published_url"] == "https://blog.naver.com/a/1"
    assert client.post("/drafts/999/published-url",
                       json={"url": "https://x.com"}).status_code == 404
    prod = TestClient(make_app(tmp_path, env="production"))
    assert prod.post("/drafts/1/published-url",
                     json={"url": "https://x.com"}).status_code == 401


def test_export_markdown_contains_images(tmp_path, monkeypatch):
    import json as json_mod
    client = TestClient(make_app(tmp_path))
    did = _create_draft(client, monkeypatch)
    import db as db_mod
    d = db_mod.Database(f"sqlite:///{tmp_path / 't.db'}")
    d.update_draft_image(did, "https://cdn.example.com/m.png", "")
    d.update_draft_section_images(
        did, json_mod.dumps(["https://cdn.example.com/s.png"]), "")
    d.close()
    r = client.get(f"/drafts/{did}/export")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    assert f"blog-draft-{did}.md" in r.headers["content-disposition"]
    text = r.content.decode("utf-8")
    assert text.startswith("# 제목")
    assert "![대표 이미지](https://cdn.example.com/m.png)" in text
    assert "![섹션 이미지 1](https://cdn.example.com/s.png)" in text
    assert client.get("/drafts/999/export").status_code == 404


def test_adpost_import_matches_by_url_and_title(tmp_path, monkeypatch):
    client = TestClient(make_app(tmp_path))
    did = _create_draft(client, monkeypatch)
    client.post(f"/drafts/{did}/published-url",
                json={"url": "https://blog.naver.com/a/1"})
    base = _priority_of(client, "에어프라이어")
    csv = ("게시물 제목,URL,수익(원),노출수,클릭수\n"
           "제목,https://blog.naver.com/a/1,3000,5000,100\n"
           "매칭 실패 글,https://blog.naver.com/a/999,100,10,1\n").encode("utf-8-sig")
    r = client.post("/adpost/import",
                    files={"file": ("report.csv", csv, "text/csv")})
    assert r.status_code == 200
    body = r.json()
    assert body["matched"] == 1 and body["unmatched"] == 1
    assert body["results"][0]["draft_id"] == did
    assert body["results"][0]["performance_score"] == 100.0
    # 만점 성과 → boost +10이 priority에 반영
    assert _priority_of(client, "에어프라이어") == base + 10
    # 초안에도 지표 저장
    draft = client.get(f"/drafts/{did}").json()
    assert draft["adpost_revenue"] == 3000.0
    assert draft["performance_score"] == 100.0
    # 제목 매칭 경로 (URL 미등록 초안)
    did2 = _create_draft(client, monkeypatch)
    csv2 = "게시물 제목,수익\n제목,100\n".encode("utf-8-sig")
    body2 = client.post("/adpost/import",
                        files={"file": ("r.csv", csv2, "text/csv")}).json()
    assert body2["matched"] >= 1  # 동명 초안 중 최신에 매칭


def test_adpost_import_rejects_bad_csv(tmp_path):
    client = TestClient(make_app(tmp_path))
    r = client.post("/adpost/import",
                    files={"file": ("bad.csv", b"day,views\n", "text/csv")})
    assert r.status_code == 400
    prod = TestClient(make_app(tmp_path, env="production"))
    assert prod.post("/adpost/import",
                     files={"file": ("r.csv", b"x", "text/csv")}).status_code == 401


def test_section_images_incremental(tmp_path, monkeypatch):
    # v17 (버그 3): 기존 이미지 이후부터 증분 생성 + 즉시 저장
    import json as json_mod
    client = TestClient(make_app(tmp_path))
    did = _create_draft(client, monkeypatch,
                        body_md="## 섹션1\n본문\n\n## 섹션2\n본문")
    import db as db_mod
    import image_gen
    d = db_mod.Database(f"sqlite:///{tmp_path / 't.db'}")
    d.update_draft_section_images(
        did, json_mod.dumps(["https://cdn.example.com/1.png"]), "")
    d.close()
    monkeypatch.setenv("BAILIAN_TOKEN_PLAN_API_KEY", "test-key")
    calls = []

    def fake_run(prompt):
        calls.append(prompt)
        return f"https://cdn.example.com/{len(calls) + 1}.png"

    monkeypatch.setattr(image_gen, "_run_http",
                        lambda prompt, timeout=55: fake_run(prompt))
    r = client.post(f"/drafts/{did}/section-images")
    assert r.status_code == 200
    urls = json_mod.loads(r.json()["section_images"])
    assert len(urls) == 2                      # 기존 1 + 신규 1 (증분)
    assert urls[0] == "https://cdn.example.com/1.png"
    assert len(calls) == 1                     # 누락분만 생성
    # 전부 있으면 무호출
    calls.clear()
    client.post(f"/drafts/{did}/section-images")
    assert calls == []
