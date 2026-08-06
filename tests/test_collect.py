# tests/test_collect.py
import pytest

import collect
import config as config_mod
import db
from collect import run_collection


class FakeClient:
    def search_blog(self, query, sort="sim", display=100, start=1):
        return {"total": 100, "items": [{"postdate": "20260101"}]}


def make_cfg(tmp_path):
    return {
        "db_url": f"sqlite:///{tmp_path / 't.db'}",
        "client_id": "cid", "client_secret": "csec",
        "daily_new_keyword_cap": 100, "active_keyword_cap": 1000,
        "autocomplete_url": "http://ac.test", "autocomplete_max_depth": 1,
        "autocomplete_max_requests": 10, "manual_budget_seconds": 45,
        "dashboard_token": "", "datalab_enabled": False, "datalab_anchor": "냉장고",
        "env": "development", "run_lock_stale_minutes": 60,  # v3
        "shopping_insight_category": "50000000",  # v4
        "default_focus_seeds": [], "cpc_tiers": {},  # v6: 시드 자동 초기화 비활성(기존 테스트 보존)
        "keyword_category_rules": [("에어프라이어", "요리"), ("보험", "보험")],  # v8
        "content_batch_enabled": False,  # v17: 단위 테스트는 콘텐츠 배치 생략
    }


def test_empty_seeds_auto_init_focus_seeds(tmp_path):
    # v6: 시드 없으면 집중 기본 시드 자동 초기화 → 발굴 진행 (애드포스트 1차 목표)
    cfg = make_cfg(tmp_path)
    cfg["default_focus_seeds"] = [("보험 비교 방법", "보험"), ("재테크 방법", "금융")]
    d = db.Database(cfg["db_url"])
    d.init()
    run_collection(cfg, client=FakeClient(), today="2026-08-01")
    seeds = d.list_seeds()
    assert {s["keyword"] for s in seeds} == {"보험 비교 방법", "재테크 방법"}
    assert {s["category"] for s in seeds} == {"보험", "금융"}
    d.close()


def test_two_day_snapshot_precomputes_scores(tmp_path):
    cfg = make_cfg(tmp_path)
    d = db.Database(cfg["db_url"])
    d.init()
    kid = d.upsert_keyword("키워드1", day="2026-07-31")
    r1 = run_collection(cfg, client=FakeClient(), today="2026-08-01")
    r2 = run_collection(cfg, client=FakeClient(), today="2026-08-02")
    assert r1["snapshotted"] == 1 and r2["snapshotted"] == 1
    hist = d.get_history(kid)
    assert len(hist) == 2
    assert hist[0]["opportunity"] is None  # 1일차: 전일 없음 → NULL ("데이터 쌓는 중")
    assert hist[1]["growth"] == 0.0        # (100−100)/100
    assert hist[1]["opportunity"] == 15.0  # 40×0 + 30×0 + 30×(1−0.5)
    assert hist[1]["commercial"] is None   # v4: 쇼핑 검색 API 종료 — 상업성 NULL (쇼핑클릭은 배치 갱신)
    d.close()


def test_same_day_rerun_is_idempotent(tmp_path):
    cfg = make_cfg(tmp_path)
    d = db.Database(cfg["db_url"])
    d.init()
    d.upsert_keyword("키워드1", day="2026-07-31")
    run_collection(cfg, client=FakeClient(), today="2026-08-01")
    again = run_collection(cfg, client=FakeClient(), today="2026-08-01")
    assert again["snapshotted"] == 0  # 같은 날짜 스킵 → 수동+자동 중복에도 안전
    d.close()


def test_manual_budget_partial(tmp_path):
    cfg = make_cfg(tmp_path)
    d = db.Database(cfg["db_url"])
    d.init()
    d.upsert_keyword("키워드1", day="2026-07-31")
    d.upsert_keyword("키워드2", day="2026-07-31")
    result = run_collection(cfg, client=FakeClient(), today="2026-08-01",
                            trigger="manual", budget_seconds=0)
    assert result["partial"] is True
    assert result["snapshotted"] == 0
    d.close()


def test_active_cap_blocks_discovery(tmp_path, monkeypatch):
    cfg = dict(make_cfg(tmp_path), active_keyword_cap=1)
    d = db.Database(cfg["db_url"])
    d.init()
    d.add_seed("시드", "요리")
    d.upsert_keyword("이미있음", day="2026-07-31")

    def boom(*a, **k):
        raise AssertionError("총량 캡 도달 시 크롤을 시작하면 안 됨")

    monkeypatch.setattr(collect, "expand_keywords", boom)
    result = run_collection(cfg, client=FakeClient(), today="2026-08-01")
    assert result["new_keywords"] == 0
    assert result["snapshotted"] == 1
    d.close()


def test_zero_daily_cap_uses_active_room(tmp_path, monkeypatch):
    # v5: DAILY_NEW_KEYWORD_CAP=0 해제 시 활성 총량 여유분까지 발굴
    cfg = dict(make_cfg(tmp_path), daily_new_keyword_cap=0, active_keyword_cap=1)
    d = db.Database(cfg["db_url"])
    d.init()
    d.add_seed("트렌드", "정보")
    monkeypatch.setattr(
        collect, "expand_keywords",
        lambda *a, **k: (["트렌드 새키워드"], {"트렌드 새키워드": "트렌드"}, None),
    )
    result = run_collection(cfg, client=FakeClient(), today="2026-08-03")
    assert result["new_keywords"] == 1
    assert d.count_active() == 1
    d.close()


def test_locked_when_run_in_progress(tmp_path):
    cfg = make_cfg(tmp_path)
    d = db.Database(cfg["db_url"])
    d.init()
    assert d.start_run("schedule", config_mod.now_kst_iso(),
                       config_mod.minutes_ago_kst_iso(30)) is not None
    result = run_collection(cfg, client=FakeClient(), today="2026-08-01")
    assert result["locked"] is True
    d.close()


def test_schedule_run_retires_and_cleans(tmp_path, monkeypatch):
    cfg = make_cfg(tmp_path)
    d = db.Database(cfg["db_url"])
    d.init()
    bad = d.upsert_keyword("낡고나쁨", day="2026-07-01")
    d.insert_daily_stats(bad, "2026-08-01", {
        "total_date": 100, "opportunity": 10.0, "shop_click_idx": 0.1})
    d.insert_daily_stats(bad, "2026-01-15", {"total_sim": 1})  # 90일 보존 초과분
    d.insert_top_results(bad, "2026-01-15", ["20260101"])      # 30일 보존 초과분

    # v4: 쇼핑 클릭 지수는 배치 단계 갱신 — 8/2 스냅샷에 저조한 클릭 0.1 주입
    def fake_shop_clicks(d2, cfg2, today, now, budget_seconds=None, started=None):
        d2.update_shop_click_idx(bad, today, 0.1)
        return 1

    # v14: total_sim 포화(경쟁 만점)라 8/2 기회점수 0 — 은퇴 폴백 임계(12) 하회
    monkeypatch.setattr(collect, "analyze_keyword", lambda client, kw, today: {
        "total_sim": 100000, "total_date": 100, "fresh_ratio": 0.0,
        "top_post_dates": [], "top_bloggers": [], "top_descriptions": []})
    monkeypatch.setattr(collect, "update_shop_clicks", fake_shop_clicks)
    result = run_collection(cfg, client=FakeClient(), today="2026-08-02")
    assert result["snapshotted"] == 1
    assert result["shop_clicks_updated"] == 1
    assert result["retired"] == 1  # 8/2: 기회 0 < 12(폴백), 쇼핑클릭 0.1 < 0.5 → 은퇴
    assert d.count_active() == 0
    assert all(h["day"] >= "2026-05-04" for h in d.get_history(bad))
    assert d.get_top_results(bad, "2026-01-15") == []
    d.close()


def test_date_gap_keeps_growth_null(tmp_path):
    # v3: 전일(day-1) 스냅샷만 증감률·기회점수 산출 — 8/2 공백이면 8/3은 NULL
    cfg = make_cfg(tmp_path)
    d = db.Database(cfg["db_url"])
    d.init()
    kid = d.upsert_keyword("키워드1", day="2026-07-30")
    run_collection(cfg, client=FakeClient(), today="2026-08-01")
    run_collection(cfg, client=FakeClient(), today="2026-08-03")
    hist = d.get_history(kid)
    assert hist[-1]["growth"] is None        # 며칠치 증가율을 하루치로 계산 금지
    assert hist[-1]["opportunity"] is None
    d.close()


def test_blocked_crawl_marks_partial_and_exit(tmp_path, monkeypatch):
    # v3: 차단은 스냅샷 성공 여부와 무관하게 exit 1 — 조용히 성공 처리 금지 (스펙 §5)
    cfg = make_cfg(tmp_path)
    d = db.Database(cfg["db_url"])
    d.init()
    d.add_seed("시드", "요리")
    monkeypatch.setattr(collect, "expand_keywords",
                        lambda *a, **k: ([], {}, "blocked"))
    result = run_collection(cfg, client=FakeClient(), today="2026-08-01")
    assert result["crawl_stopped"] == "blocked"
    runs = d.get_last_runs(1)
    assert runs[0]["status"] == "partial"   # 발굴 중단은 partial로 기록
    monkeypatch.setattr(collect, "run_collection",
                        lambda *a, **k: {"locked": False, "new_keywords": 0,
                                         "snapshotted": 1, "errors": [],
                                         "partial": False, "crawl_stopped": "blocked",
                                         "retired": 0, "demand_updated": 0,
                                         "shop_clicks_updated": 0})
    with pytest.raises(SystemExit) as exc:
        collect.main()
    assert exc.value.code == 1
    d.close()


def test_reject_log_carries_reason(tmp_path, monkeypatch):
    # v3: 필터 사유를 collection_log에 저장 — 리젝 로그 리뷰의 입력 (스펙 §4.2)
    cfg = make_cfg(tmp_path)
    d = db.Database(cfg["db_url"])
    d.init()
    d.add_seed("시드", "요리")
    monkeypatch.setattr(collect, "expand_keywords",
                        lambda *a, **k: (["야동사이트 후기", "정상키워드"],
                                         {"야동사이트 후기": "시드", "정상키워드": "시드"}, None))
    run_collection(cfg, client=FakeClient(), today="2026-08-01")
    logs = d.get_logs()
    assert any(l["action"] == "reject" and l["note"] == "substring" for l in logs)
    assert any(l["action"] == "new" and l["keyword"] == "정상키워드" for l in logs)
    # 1차 파생 키워드(유래=시드)는 시드 분야 상속 (v3)
    assert d.query_keywords(q="정상키워드")[0]["category"] == "요리"
    d.close()


def test_manual_discovery_respects_budget(tmp_path):
    # v3: 첫 실행(활성 0개) 수동 발굴도 예산 내 중단 — 예산 초과는 blocked가 아닌 budget
    cfg = make_cfg(tmp_path)
    d = db.Database(cfg["db_url"])
    d.init()
    d.add_seed("시드", "요리")
    result = run_collection(cfg, client=FakeClient(), today="2026-08-01",
                            trigger="manual", budget_seconds=0)
    assert result["crawl_stopped"] == "budget"
    assert result["new_keywords"] == 0


def test_rule_fallback_categorizes_seedless_keywords(tmp_path, monkeypatch):
    # v8: 무카테고리 시드 유래(유래 불일치) 키워드는 패턴 규칙으로 분류
    # v14: 규칙까지 매치 실패하면 "기타" 폴백 (빈 문자열은 필터 누락·CPC 기본값 문제)
    cfg = make_cfg(tmp_path)
    d = db.Database(cfg["db_url"])
    d.init()
    d.add_seed("유래불일치시드", "")
    monkeypatch.setattr(collect, "expand_keywords",
                        lambda *a, **k: (["에어프라이어 추천 내돈내산", "무관한 키워드"],
                                         {"에어프라이어 추천 내돈내산": "유래불일치시드",
                                          "무관한 키워드": "유래불일치시드"}, None))
    run_collection(cfg, client=FakeClient(), today="2026-08-01")
    assert d.query_keywords(q="에어프라이어 추천 내돈내산")[0]["category"] == "요리"
    assert d.query_keywords(q="무관한 키워드")[0]["category"] == "기타"
    d.close()


def test_categorize_by_rules_first_match_wins():
    # v8: 규칙은 앞 항목 우선 (첫 매치)
    assert collect._categorize_by_rules("보험 에어프라이어", [("보험", "보험"), ("에어프라이어", "요리")]) == "보험"
    assert collect._categorize_by_rules("매치 없음", []) == ""


def test_categorize_rules_v17_precision(monkeypatch):
    # v17 (버그 2): 부분문자열·대소문자 오탐 수정 — 정밀도 우선
    import config as config_mod
    rules = config_mod.DEFAULT_KEYWORD_CATEGORY_RULES
    # 대소문자 무시 — 소문자 키워드가 대문자 규칙에 매치
    assert collect._categorize_by_rules("isa 계좌 조건", rules) == "재테크"
    assert collect._categorize_by_rules("ai 활용 방법", rules) == "IT"
    # 부분문자열 오탐 차단
    assert collect._categorize_by_rules("암사동 맛집", rules) == "맛집"  # '암' 아님
    assert collect._categorize_by_rules("운동화 추천", rules) == "패션"  # '운동' 아님
    # 복합어는 contains 명시 규칙만 허용 (실비보험 → 보험)
    assert collect._categorize_by_rules("실비보험 추천", rules) == "보험"
    assert collect._categorize_by_rules("보험료 계산", rules) == "보험"  # 보험료 우선 매치
    # 단어 단위 매치 유지
    assert collect._categorize_by_rules("다이어트 식단", rules) == "건강"
    assert collect._categorize_by_rules("무관한 키워드", rules) == ""


def test_discover_exception_labels_error_not_blocked(tmp_path, monkeypatch):
    # v17 (버그 6): 예상치 못한 예외는 'error' — 'blocked'(연속 차단)과 구분
    cfg = make_cfg(tmp_path)
    d = db.Database(cfg["db_url"])
    d.init()
    d.add_seed("시드", "요리")

    def boom(*a, **k):
        raise RuntimeError("예상 못 한 예외")

    monkeypatch.setattr(collect, "expand_keywords", boom)
    result = run_collection(cfg, client=FakeClient(), today="2026-08-01")
    assert result["crawl_stopped"] == "error"
    assert d.get_last_runs(1)[0]["status"] == "partial"
    d.close()


def test_datalab_stages_survive_missing_started(tmp_path, monkeypatch):
    # v17 (버그 6): started=None이어도 TypeError 없이 예산 검사 생략
    cfg = make_cfg(tmp_path)
    cfg["datalab_enabled"] = True
    d = db.Database(cfg["db_url"])
    d.init()
    kid = d.upsert_keyword("키워드1", day="2026-07-31")
    d.insert_daily_stats(kid, "2026-08-01", {"opportunity": 10.0})
    monkeypatch.setattr(collect, "fetch_demand_ratios",
                        lambda *a, **k: {"키워드1": {"ratio": 0.01, "growth": 0.0}})
    assert collect.update_demand(d, cfg, "2026-08-01", "now",
                                 budget_seconds=10, started=None) == 1
    monkeypatch.setattr(collect, "fetch_click_ratios",
                        lambda *a, **k: {"키워드1": None})  # 분야 미매칭
    assert collect.update_shop_clicks(d, cfg, "2026-08-01", "now",
                                      budget_seconds=10, started=None) == 0
    assert d.get_latest_stats(kid)["shop_click_idx"] is None  # NULL 유지
    d.close()


def test_datalab_rotation_covers_beyond_top_slot(tmp_path, monkeypatch):
    # v17 (고도화 5): 상위 고정 + 순환 슬롯 — 상위 100 밖 키워드도 갱신됨
    cfg = make_cfg(tmp_path)
    cfg["datalab_enabled"] = True
    d = db.Database(cfg["db_url"])
    d.init()
    monkeypatch.setattr(collect, "DATALAB_PRIORITY_N", 1)
    monkeypatch.setattr(collect, "DATALAB_ROTATE_N", 2)
    for i, opp in enumerate((50.0, 30.0, 10.0)):
        kid = d.upsert_keyword(f"키워드{i}", day="2026-07-31")
        d.insert_daily_stats(kid, "2026-08-01", {"opportunity": opp})
    seen = []
    monkeypatch.setattr(
        collect, "fetch_demand_ratios",
        lambda cid, csec, kws, anchor, start, end, timeout=10:
        seen.extend(kws) or {k: {"ratio": 0.01, "growth": 0.0} for k in kws})
    updated = collect.update_demand(d, cfg, "2026-08-01", "now")
    assert updated == 3                       # 상위 1 + 순환 2 = 전부 갱신
    assert set(seen) == {"키워드0", "키워드1", "키워드2"}
    d.close()


def test_reject_rate_recorded_in_run_note(tmp_path, monkeypatch):
    # v14 §1.2: 거부율(거부/발굴후보)을 collection_runs.note(JSON)에 기록 —
    # 대시보드 노이즈 유입률 노출의 원료. 발굴 없으면 note 빈 문자열.
    import json as json_mod
    cfg = make_cfg(tmp_path)
    d = db.Database(cfg["db_url"])
    d.init()
    d.add_seed("시드", "요리")
    monkeypatch.setattr(collect, "expand_keywords",
                        lambda *a, **k: (["바카라 후기", "정상키워드1", "정상키워드2"],
                                         {"바카라 후기": "시드", "정상키워드1": "시드",
                                          "정상키워드2": "시드"}, None))
    result = run_collection(cfg, client=FakeClient(), today="2026-08-01")
    assert result["found_raw"] == 3
    assert result["rejected"] == 1
    note = json_mod.loads(d.get_last_runs(1)[0]["note"])
    assert note["found_raw"] == 3
    assert note["rejected"] == 1
    assert note["reject_rate"] == round(1 / 3, 4)  # 소수 4자리 기록
    d.close()


def test_run_without_discovery_keeps_empty_note(tmp_path):
    cfg = make_cfg(tmp_path)
    d = db.Database(cfg["db_url"])
    d.init()
    d.upsert_keyword("키워드1", day="2026-07-31")
    run_collection(cfg, client=FakeClient(), today="2026-08-01")
    assert d.get_last_runs(1)[0]["note"] == ""
    d.close()


def test_retire_uses_percentile_threshold(tmp_path):
    # v14: 은퇴 기회점수 임계 = 활성 최신 스냅샷 P25 (자가보정).
    # 고정 35.0은 실측 기회점수 최대(~24)보다 높아 은퇴가 쇼핑클릭 조건으로
    # 퇴화하던 버그 — 표본 20개+에서 P25가 실제로 적용되는지 회귀 방지.
    cfg = make_cfg(tmp_path)
    d = db.Database(cfg["db_url"])
    d.init()
    now = "2026-08-02T07:00:00+09:00"
    for i in range(20):
        kid = d.upsert_keyword(f"집단{i:02d}", day="2026-07-01")
        d.insert_daily_stats(kid, "2026-08-01",
                             {"opportunity": 20.0 + i, "shop_click_idx": 0.9})
    victim = d.upsert_keyword("저성과", day="2026-07-01")
    d.insert_daily_stats(victim, "2026-08-01",
                         {"opportunity": 5.0, "shop_click_idx": 0.1})
    # n=21 → P25 = 24.0 — 집단(클릭 0.9)은 보호되고 저성과(5.0 < 24, 클릭 0.1)만 은퇴
    assert collect.retire(d, "2026-08-02", now) == 1
    assert d.count_active() == 20
    d.close()


def test_retire_fallback_when_sample_small(tmp_path):
    # v14: 표본 < 20이면 폴백 절대값(12.0) — 빈곤 표본에서 백분위 노이즈 방지
    cfg = make_cfg(tmp_path)
    d = db.Database(cfg["db_url"])
    d.init()
    now = "2026-08-02T07:00:00+09:00"
    bad = d.upsert_keyword("저성과", day="2026-07-01")
    d.insert_daily_stats(bad, "2026-08-01",
                         {"opportunity": 10.0, "shop_click_idx": 0.1})
    assert collect.retire(d, "2026-08-02", now) == 1  # 10.0 < 폴백 12.0
    assert d.count_active() == 0
    d.close()
