# tests/test_db.py
from db import Database


def make_url(tmp_path):
    return f"sqlite:///{tmp_path / 't.db'}"


def make_db(tmp_path):
    d = Database(make_url(tmp_path))
    d.init()
    return d


def test_init_creates_tables(tmp_path):
    d = make_db(tmp_path)
    rows = d.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    names = {r[0] for r in rows}
    assert {
        "seed_keywords", "keywords", "daily_stats",
        "top_results", "collection_log", "collection_runs",
    } <= names


def test_init_creates_parent_dir(tmp_path):
    dbfile = tmp_path / "nested" / "t.db"
    d = Database(f"sqlite:///{dbfile}")
    d.init()
    assert dbfile.exists()
    d.close()


def test_dialect_detection():
    assert Database("sqlite:///x.db", connect=False).dialect == "sqlite"
    assert Database("postgresql://u:p@localhost/db", connect=False).dialect == "postgres"


def test_seed_keyword_crud(tmp_path):
    d = make_db(tmp_path)
    d.add_seed("에어프라이어", "요리")
    seeds = d.list_seeds()
    assert len(seeds) == 1
    assert seeds[0]["keyword"] == "에어프라이어"
    d.delete_seed(seeds[0]["id"])
    assert d.list_seeds() == []


def test_keyword_upsert_preserves_category(tmp_path):
    # v1 결함 수정 검증: category 없는 재upsert가 기존 분야를 지우면 안 됨
    d = make_db(tmp_path)
    kid = d.upsert_keyword("에어프라이어", category="가전", day="2026-08-01")
    assert d.upsert_keyword("에어프라이어", day="2026-08-02") == kid
    rows = d.list_active_keywords_stale_first()
    assert rows[0]["category"] == "가전"
    assert rows[0]["first_seen"] == "2026-08-01"


def test_snapshot_prev_and_demand(tmp_path):
    d = make_db(tmp_path)
    kid = d.upsert_keyword("에어프라이어", day="2026-08-01")
    d.insert_daily_stats(kid, "2026-08-01", {
        "total_sim": 1000, "total_date": 1200, "fresh_ratio": 0.4,
    })
    d.insert_daily_stats(kid, "2026-08-02", {
        "total_sim": 1100, "total_date": 1300, "fresh_ratio": 0.5,
        "growth": 0.083, "opportunity": 55.0, "commercial": 12.5,
    })
    assert len(d.get_history(kid)) == 2
    assert d.get_latest_stats(kid)["opportunity"] == 55.0
    prev = d.get_prev_stats(kid, "2026-08-02")
    assert prev["day"] == "2026-08-01"
    assert prev["growth"] is None
    assert d.get_prev_stats(kid, "2026-08-01") is None
    d.update_demand_idx(kid, "2026-08-02", 0.25)
    assert d.get_latest_stats(kid)["demand_idx"] == 0.25
    assert d.top_by_opportunity("2026-08-02", 10)[0]["keyword"] == "에어프라이어"


def test_top_results_and_log_timestamp(tmp_path):
    d = make_db(tmp_path)
    kid = d.upsert_keyword("테스트", day="2026-08-03")
    d.insert_top_results(kid, "2026-08-03", ["20260801", "20260730"])
    assert d.get_top_results(kid, "2026-08-03") == ["20260801", "20260730"]
    d.log_collection("테스트", "keep", "정상", "2026-08-03T07:17:03+09:00")
    log = d.get_logs()
    assert len(log) == 1
    assert log[0]["run_at"] == "2026-08-03T07:17:03+09:00"


def test_counts_and_known_set(tmp_path):
    d = make_db(tmp_path)
    k1 = d.upsert_keyword("키워드1", day="2026-08-03")
    d.upsert_keyword("키워드2", day="2026-08-03")
    assert d.count_new_keywords_today("2026-08-03") == 2
    assert d.count_active() == 2
    assert d.all_keyword_names() == {"키워드1", "키워드2"}
    d.set_active(k1, 0)
    assert d.count_active() == 1


def test_stale_first_order(tmp_path):
    d = make_db(tmp_path)
    d.upsert_keyword("한번도수집안됨", day="2026-08-01")
    b = d.upsert_keyword("어제수집됨", day="2026-08-01")
    d.insert_daily_stats(b, "2026-08-02", {"total_sim": 1})
    rows = d.list_active_keywords_stale_first()
    assert rows[0]["keyword"] == "한번도수집안됨"
    assert rows[0]["last_day"] == ""
    assert rows[1]["last_day"] == "2026-08-02"


def test_run_lock_stale_reclaim_and_finish(tmp_path):
    d = make_db(tmp_path)
    rid = d.start_run("schedule", "2026-08-03T07:17:00+09:00", "2026-08-03T06:47:00+09:00")
    assert rid is not None
    # 실행 중(30분 미경과)이면 잠금
    assert d.start_run("manual", "2026-08-03T07:20:00+09:00", "2026-08-03T06:50:00+09:00") is None
    # 정상 종료 후엔 새 실행 가능
    d.finish_run(rid, "done", "2026-08-03T07:30:00+09:00", {
        "new_keywords": 3, "snapshotted": 10, "errors": ["e1"], "partial": False,
    })
    rid2 = d.start_run("manual", "2026-08-03T08:00:00+09:00", "2026-08-03T07:30:00+09:00")
    assert rid2 is not None and rid2 != rid
    # stale 잠금(30분 초과)은 회수하고 새 실행 허용
    assert d.start_run("schedule", "2026-08-03T09:00:00+09:00", "2026-08-03T08:30:00+09:00") is not None
    runs = d.get_last_runs(10)
    assert runs[0]["status"] == "running"
    assert any(r["status"] == "failed" and r["note"] == "stale lock 회수" for r in runs)
    assert any(r["status"] == "done" and r["snapshotted"] == 10 and r["errors"] == 1 for r in runs)


def test_query_keywords_filter_sort_paging(tmp_path):
    d = make_db(tmp_path)
    a = d.upsert_keyword("에어프라이어", day="2026-08-01")
    b = d.upsert_keyword("선풍기", day="2026-08-02")
    c = d.upsert_keyword("중고폰", day="2026-08-02")
    d.insert_daily_stats(a, "2026-08-02", {
        "total_sim": 100, "total_date": 100, "fresh_ratio": 0.5,
        "shop_total": 500, "shop_avg_price": 30000, "shop_category": "가전",
        "growth": 0.1, "opportunity": 80.0, "commercial": 100.0,
    })
    d.insert_daily_stats(b, "2026-08-02", {
        "total_sim": 10, "total_date": 10, "shop_total": 10,
        "shop_avg_price": 1000, "shop_category": "가전", "commercial": 2.5,
    })
    d.insert_daily_stats(c, "2026-08-02", {
        "total_sim": 5, "total_date": 5, "shop_category": "디지털", "commercial": 0.0,
    })
    # 기본 정렬: 기회점수, NULL은 뒤로 (뒤끼리는 id순)
    assert [r["keyword"] for r in d.query_keywords()] == ["에어프라이어", "선풍기", "중고폰"]
    assert d.count_keywords() == 3
    assert [r["keyword"] for r in d.query_keywords(limit=1, offset=1)] == ["선풍기"]
    assert [r["keyword"] for r in d.query_keywords(commercial_min=50)] == ["에어프라이어"]
    assert [r["keyword"] for r in d.query_keywords(q="선풍")] == ["선풍기"]
    assert [r["keyword"] for r in d.query_keywords(category="가전")] == ["에어프라이어", "선풍기"]
    assert [r["keyword"] for r in d.query_keywords(discovered_since="2026-08-02")] == ["선풍기", "중고폰"]
    assert d.query_keywords()[0]["days"] == 1
    # 비활성 처리
    d.set_active(c, 0)
    assert d.count_keywords() == 2
    assert d.count_keywords(active=None) == 3


def test_retire_candidates_and_cleanup(tmp_path):
    d = make_db(tmp_path)
    bad = d.upsert_keyword("낡고나쁨", day="2026-07-01")
    good = d.upsert_keyword("낡지만좋음", day="2026-07-01")
    d.upsert_keyword("수집끊김", day="2026-07-01")  # 최근 스냅샷 없음 → 은퇴 보호
    # v4: 은퇴는 기회점수 + 쇼핑 클릭 지수로 판정 (쇼핑 검색 API 종료)
    d.insert_daily_stats(bad, "2026-08-01", {"opportunity": 10.0, "shop_click_idx": 0.1})
    d.insert_daily_stats(good, "2026-08-01", {"opportunity": 80.0, "shop_click_idx": 0.1})
    victims = d.find_retire_candidates("2026-07-20", "2026-07-27", 35.0, 0.5)
    assert [v["keyword"] for v in victims] == ["낡고나쁨"]
    d.set_active(victims[0]["id"], 0)
    assert d.count_active() == 2
    # 보존 정리: daily_stats / top_results / collection_log 각각 기준일 이전 삭제
    d.insert_daily_stats(bad, "2026-04-01", {"total_sim": 1})
    d.insert_top_results(bad, "2026-04-01", ["20260101"])
    d.log_collection("낡고나쁨", "new", "옛 로그", "2026-01-01T00:00:00+09:00")
    d.log_collection("낡고나쁨", "new", "최근 로그", "2026-08-01T00:00:00+09:00")
    d.cleanup("2026-05-05", "2026-07-04", "2026-02-04T00:00:00+09:00")
    assert all(h["day"] >= "2026-05-05" for h in d.get_history(bad))
    assert d.get_top_results(bad, "2026-04-01") == []
    assert [row["note"] for row in d.get_logs()] == ["최근 로그"]


def test_query_includes_keywords_without_snapshot(tmp_path):
    # v3: LEFT JOIN — 발굴 직후(예산 소진·실패) 스냅샷 없는 키워드도 목록에 표시
    d = make_db(tmp_path)
    d.upsert_keyword("방금발굴", day="2026-08-03")  # 스냅샷 없음
    d.upsert_keyword("스냅샷있음", day="2026-08-01")
    rows = d.query_keywords()
    assert [r["keyword"] for r in rows] == ["스냅샷있음", "방금발굴"]  # NULL은 뒤로
    assert rows[1]["opportunity"] is None
    assert rows[1]["days"] == 0
    assert d.count_keywords() == 2
    # 분야 필터: 스냅샷이 없어도 k.category로 매칭 가능해야 함
    assert [r["keyword"] for r in d.query_keywords(category="가전")] == []


def test_start_run_atomic_blocks_duplicate(tmp_path):
    # v3: 부분 유니크 인덱스 — 동시 INSERT 경합 시 하나만 running 유지
    d = make_db(tmp_path)
    rid = d.start_run("schedule", "2026-08-03T07:00:00+09:00",
                      "2026-08-03T06:00:00+09:00")
    assert rid is not None
    assert d.start_run("manual", "2026-08-03T07:10:00+09:00",
                       "2026-08-03T06:10:00+09:00") is None
    rows = d._qd("SELECT status FROM collection_runs", (), fetch=True)
    assert [r["status"] for r in rows] == ["running"]


def test_retire_clickless_by_opportunity_alone(tmp_path):
    # v17 (버그 1): 클릭 데이터가 한 번도 수집되지 않은 키워드(상위 200 슬롯 밖·
    # 분야 미매칭)는 기회점수 단독 판정으로 은퇴 — 기존 EXISTS(클릭 비NULL)는
    # 이들을 영구 보호해 500 상한 도달 시 발견이 영구 정지했음
    d = make_db(tmp_path)
    clickless = d.upsert_keyword("클릭미수집", day="2026-07-01")
    d.insert_daily_stats(clickless, "2026-08-01",
                         {"opportunity": 10.0, "shop_click_idx": None})
    victims = d.find_retire_candidates("2026-07-20", "2026-07-27", 35.0, 0.5)
    assert [v["keyword"] for v in victims] == ["클릭미수집"]
    assert victims[0]["clickless"] == 1  # 은퇴 로그 구분용 플래그


def test_retire_protects_recent_null_with_click_history(tmp_path):
    # v17: 과거 클릭 이력이 있는데 최근 NULL = 수집 공백 의심 → 보호 (§4.6 유지).
    # '수집 실패'와 '구조적 미수집'은 이력 유무로 구분된다.
    d = make_db(tmp_path)
    gap = d.upsert_keyword("수집공백의심", day="2026-07-01")
    d.insert_daily_stats(gap, "2026-07-28",
                         {"opportunity": 10.0, "shop_click_idx": 0.1})
    d.insert_daily_stats(gap, "2026-08-01",
                         {"opportunity": 10.0, "shop_click_idx": None})
    victims = d.find_retire_candidates("2026-07-20", "2026-07-27", 35.0, 0.5)
    assert victims == []


def test_retire_protects_performance_boost(tmp_path):
    # v11: 게시 성과 피드백 보너스(≥10) 키워드는 지표 저조에도 은퇴 보호
    d = make_db(tmp_path)
    boosted = d.upsert_keyword("성과확인됨", day="2026-07-01")
    plain = d.upsert_keyword("그냥저조", day="2026-07-01")
    d.insert_daily_stats(boosted, "2026-08-01",
                         {"opportunity": 10.0, "shop_click_idx": 0.1})
    d.insert_daily_stats(plain, "2026-08-01",
                         {"opportunity": 10.0, "shop_click_idx": 0.1})
    d.set_performance_boost(boosted, 10)
    victims = d.find_retire_candidates("2026-07-20", "2026-07-27", 35.0, 0.5)
    assert [v["keyword"] for v in victims] == ["그냥저조"]
    # boost 상쇄(성과 하향 피드백)되면 다시 은퇴 후보
    d.set_performance_boost(boosted, -20)
    victims = d.find_retire_candidates("2026-07-20", "2026-07-27", 35.0, 0.5)
    assert {v["keyword"] for v in victims} == {"성과확인됨", "그냥저조"}


def test_categories_include_seed_and_keyword(tmp_path):
    # v3: /categories = shop + 키워드 + 시드 분야 통합
    d = make_db(tmp_path)
    d.add_seed("에어프라이어", "요리")
    kid = d.upsert_keyword("선풍기", category="가전", day="2026-08-01")
    d.insert_daily_stats(kid, "2026-08-01", {"shop_category": "디지털"})
    assert d.list_categories() == ["가전", "디지털", "요리"]


def test_query_sort_dir_and_thresholds(tmp_path):
    # v3/v4: 정렬 방향 + 유망 프리셋 임계 필터 (쇼핑 클릭 지수 기준)
    d = make_db(tmp_path)
    a = d.upsert_keyword("에어프라이어", day="2026-08-01")
    b = d.upsert_keyword("선풍기", day="2026-08-02")
    d.insert_daily_stats(a, "2026-08-02", {
        "total_sim": 100, "opportunity": 64.1, "shop_click_idx": 0.9, "demand_idx": 0.08})
    d.insert_daily_stats(b, "2026-08-02", {
        "total_sim": 10, "opportunity": 30.0, "shop_click_idx": 0.1, "demand_idx": None})
    assert [r["keyword"] for r in d.query_keywords()] == ["에어프라이어", "선풍기"]
    assert [r["keyword"] for r in d.query_keywords(sort_dir="asc")] == ["선풍기", "에어프라이어"]
    assert [r["keyword"] for r in d.query_keywords(sort="click")] == ["에어프라이어", "선풍기"]
    assert [r["keyword"] for r in d.query_keywords(
        opportunity_min=70, click_min=0.5, demand_min=0.01)] == []
    assert [r["keyword"] for r in d.query_keywords(click_min=0.5)] == ["에어프라이어"]


def test_init_creates_v7_tables(tmp_path):
    # v7: 콘텐츠 자동화 테이블 생성 확인
    d = make_db(tmp_path)
    rows = d.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    names = {r[0] for r in rows}
    assert {"drafts", "outlines"} <= names
    d.close()


def test_outline_upsert_and_get(tmp_path):
    # v7: 같은 날 재분석은 갱신, 최신 1건 조회
    d = make_db(tmp_path)
    kid = d.upsert_keyword("에어프라이어", day="2026-08-01")
    d.upsert_outline(kid, "2026-08-03", '{"headings":["질문A"]}')
    d.upsert_outline(kid, "2026-08-04", '{"headings":["질문B"]}')
    latest = d.get_outline(kid)
    assert latest["day"] == "2026-08-04"
    assert "질문B" in latest["structure"]
    # 같은 keyword_id+day는 갱신 (행 수 불변)
    d.upsert_outline(kid, "2026-08-04", '{"headings":["질문C"]}')
    assert len(d.list_outlines(kid)) == 2
    assert "질문C" in d.get_outline(kid)["structure"]
    d.close()


def test_draft_insert_and_get(tmp_path):
    # v7: 초안 생성 → 단건 조회, image_url 갱신
    d = make_db(tmp_path)
    kid = d.upsert_keyword("에어프라이어", day="2026-08-01")
    did = d.insert_draft(
        kid, "제목", "첫문단", "본문",
        created_at="2026-08-04T08:00:00+09:00")
    draft = d.get_draft(did)
    assert draft["title"] == "제목"
    assert draft["first_paragraph"] == "첫문단"
    assert draft["status"] == "draft"
    assert draft["created_at"] == "2026-08-04T08:00:00+09:00"
    assert draft["updated_at"] == "2026-08-04T08:00:00+09:00"
    d.update_draft_image(did, "https://img.example.com/a.png",
                         "2026-08-04T08:05:00+09:00")
    assert d.get_draft(did)["image_url"] == "https://img.example.com/a.png"
    d.close()


def test_draft_list_by_keyword(tmp_path):
    # v7: 키워드별 초안 목록 (최신순)
    d = make_db(tmp_path)
    kid = d.upsert_keyword("에어프라이어", day="2026-08-01")
    d.insert_draft(kid, "첫번째", "p1", "b1", created_at="2026-08-04T08:00:00+09:00")
    d.insert_draft(kid, "두번째", "p2", "b2", created_at="2026-08-04T09:00:00+09:00")
    drafts = d.list_drafts_by_keyword(kid)
    assert len(drafts) == 2
    assert drafts[0]["title"] == "두번째"
    d.close()


# ---------- v14: 백분위 (자가보정 임계 단일 소스) ----------

def _seed_opps(d, values, day="2026-08-02", prefix="kw"):
    ids = []
    for i, v in enumerate(values):
        kid = d.upsert_keyword(f"{prefix}{i:02d}", day="2026-08-01")
        if v is not None:
            d.insert_daily_stats(kid, day, {"opportunity": v})
        ids.append(kid)
    return ids


def test_percentiles_empty_table(tmp_path):
    # v14: 빈 테이블 — 표본 0, 폴백 판단(n<20)은 호출 측
    d = make_db(tmp_path)
    assert d.percentiles("opportunity") == (0, {})


def test_percentiles_single_and_ties(tmp_path):
    d = make_db(tmp_path)
    _seed_opps(d, [10.0])
    n, pct = d.percentiles("opportunity")
    assert n == 1
    assert pct[0.25] == pct[0.5] == pct[0.75] == pct[0.9] == 10.0
    # 동점 — 모든 분위가 동일값
    _seed_opps(d, [10.0] * 3, prefix="tie")
    n, pct = d.percentiles("opportunity")
    assert n == 4
    assert pct[0.5] == 10.0


def test_percentiles_boundaries_and_latest_snapshot(tmp_path):
    # v14: 오프셋 ROUND(분위×(n-1), half-up) 경계 + 키워드별 최신 스냅샷만 집계
    d = make_db(tmp_path)
    ids = _seed_opps(d, [float(i) for i in range(1, 21)])  # 값 1..20, n=20
    # 최신 스냅샷보다 오래된 값은 집계에서 제외돼야 함 (최신 스냅샷 기준 — 스펙 §3.1)
    d.insert_daily_stats(ids[0], "2026-08-01", {"opportunity": 999.0})
    n, pct = d.percentiles("opportunity")
    assert n == 20
    # 0-base 인덱스: 값 = 인덱스+1
    assert pct[0.25] == 6.0    # idx int(0.25×19+0.5)=5
    assert pct[0.5] == 11.0    # idx int(0.5×19+0.5)=10
    assert pct[0.75] == 15.0   # idx int(0.75×19+0.5)=14
    assert pct[0.9] == 18.0    # idx int(0.9×19+0.5)=17


def test_percentiles_excludes_inactive_and_null(tmp_path):
    d = make_db(tmp_path)
    ids = _seed_opps(d, [1.0, 2.0, None])
    d.set_active(ids[1], 0)  # 비활성 제외
    n, pct = d.percentiles("opportunity")
    assert n == 1            # NULL·비활성 제외 → 1건만
    assert pct[0.5] == 1.0


def test_percentiles_rejects_unknown_metric(tmp_path):
    import pytest
    d = make_db(tmp_path)
    with pytest.raises(ValueError):
        d.percentiles("total_sim")


# ---------- v14: boost 클램프 + 피드백 원자성 ----------

def test_performance_boost_clamped(tmp_path):
    # v14: 다수 초안 피드백에도 누적 boost는 [-20, 20]
    d = make_db(tmp_path)
    kid = d.upsert_keyword("키워드", day="2026-08-01")
    for _ in range(5):
        d.set_performance_boost(kid, 10)
    assert d.get_keyword(kid)["performance_boost"] == 20.0
    d.set_performance_boost(kid, -10)
    assert d.get_keyword(kid)["performance_boost"] == 10.0
    for _ in range(5):
        d.set_performance_boost(kid, -10)
    assert d.get_keyword(kid)["performance_boost"] == -20.0
    d.close()


def test_record_draft_feedback_atomic(tmp_path):
    # v14: 초안 점수 + 키워드 boost가 한 트랜잭션에 반영 (부분 유실 틈 제거)
    d = make_db(tmp_path)
    kid = d.upsert_keyword("키워드", day="2026-08-01")
    did = d.insert_draft(kid, "제목", "첫문단", "본문",
                         created_at="2026-08-04T08:00:00+09:00")
    d.record_draft_feedback(did, kid, "2026-08-05T09:00:00+09:00", 85.0,
                            "메모", "2026-08-05T09:00:00+09:00", 10)
    draft = d.get_draft(did)
    assert draft["status"] == "published"
    assert draft["performance_score"] == 85.0
    assert d.get_keyword(kid)["performance_boost"] == 10.0
    d.close()


def test_priority_sql_matches_v6_priority(tmp_path):
    # v14 §6: db.PRIORITY_SQL과 scoring.v6_priority 동일 수식 — 하나의 테스트로
    # 정합 보장 (v12 원칙: 두 곳 동일 값 유지)
    import scoring
    d = make_db(tmp_path)
    a = d.upsert_keyword("보험 비교 방법", category="보험", day="2026-08-01")
    b = d.upsert_keyword("하락 키워드", category="여행", day="2026-08-01")
    c = d.upsert_keyword("성장 미수집", category="요리", day="2026-08-01")
    d.insert_daily_stats(a, "2026-08-02", {
        "ai_cite_idx": 0.8, "demand_idx": 0.004, "demand_growth": 0.02})
    d.insert_daily_stats(b, "2026-08-02", {
        "ai_cite_idx": 0.5, "demand_idx": 0.002, "demand_growth": -0.2})
    d.insert_daily_stats(c, "2026-08-02", {
        "ai_cite_idx": 0.4, "demand_idx": 0.001})  # demand_growth NULL
    rows = {r["keyword"]: r["priority"] for r in d.query_keywords()}
    assert rows["보험 비교 방법"] == scoring.v6_priority(0.8, 0.004, 1.0, 0.02)
    assert rows["하락 키워드"] == scoring.v6_priority(0.5, 0.002, 0.4, -0.2)
    assert rows["성장 미수집"] == scoring.v6_priority(0.4, 0.001, 0.5, None)
    d.close()


def test_migrate_repairs_legacy_schema(tmp_path):
    # v15: 구버전(컬럼 누락) DB에서도 init()이 누락 컬럼만 보완 —
    # shop_click_idx는 마이그레이션 대상에서 빠져 insert가 깨지던 것의 회귀 방지.
    # 중간 충돌로 일부만 추가된 DB(묶음 ALTER 실패 시나리오)도 개별 가드로 복구.
    import sqlite3
    dbfile = tmp_path / "legacy.db"
    conn = sqlite3.connect(dbfile)
    conn.execute(
        "CREATE TABLE daily_stats (id INTEGER PRIMARY KEY, keyword_id INTEGER, "
        "day TEXT, total_sim INTEGER)")
    conn.execute(
        "CREATE TABLE keywords (id INTEGER PRIMARY KEY, keyword TEXT UNIQUE, "
        "category TEXT DEFAULT '', first_seen TEXT, active INTEGER DEFAULT 1)")
    conn.commit()
    conn.close()
    d = Database(f"sqlite:///{dbfile}")
    d.init()
    stat_cols = {r[1] for r in d.conn.execute("PRAGMA table_info(daily_stats)")}
    assert {"shop_click_idx", "ai_cite_idx", "demand_growth"} <= stat_cols
    kw_cols = {r[1] for r in d.conn.execute("PRAGMA table_info(keywords)")}
    assert "performance_boost" in kw_cols
    # 재실행 멱등 — 이미 있는 컬럼에 duplicate column으로 깨지면 안 됨
    d.init()
    d.close()


def test_priority_sql_clamps_out_of_range_inputs(tmp_path):
    # v15: 오염 데이터(범위 초과)에도 Python↔SQL 정합 — 양쪽 다 클램프
    import scoring
    d = make_db(tmp_path)
    kid = d.upsert_keyword("오염 데이터", category="보험", day="2026-08-01")
    d.insert_daily_stats(kid, "2026-08-02", {
        "ai_cite_idx": 1.5, "demand_idx": -0.5, "demand_growth": 9.0})
    rows = {r["keyword"]: r["priority"] for r in d.query_keywords()}
    expected = scoring.v6_priority(1.5, -0.5, 1.0, 9.0)
    assert expected == 75.0          # 30×1 + 25×0 + 15×1 + 30×1 (전부 클램프)
    assert rows["오염 데이터"] == expected
    d.close()


def test_query_growth_min_filter(tmp_path):
    # v14: 상승 프리셋용 demand_growth 하한 필터 (NULL은 자동 제외)
    d = make_db(tmp_path)
    a = d.upsert_keyword("상승", day="2026-08-01")
    b = d.upsert_keyword("하락", day="2026-08-01")
    c = d.upsert_keyword("미수집", day="2026-08-01")
    d.insert_daily_stats(a, "2026-08-02", {"opportunity": 10.0, "demand_growth": 0.3})
    d.insert_daily_stats(b, "2026-08-02", {"opportunity": 10.0, "demand_growth": -0.2})
    d.insert_daily_stats(c, "2026-08-02", {"opportunity": 10.0})
    assert [r["keyword"] for r in d.query_keywords(growth_min=0.1)] == ["상승"]
    assert d.count_keywords(growth_min=0.1) == 1
    assert d.count_keywords() == 3


# ---------- v17: 데이터랩 슬롯 순환 (고도화 5) ----------

def test_datalab_targets_priority_plus_rotation(tmp_path):
    # 상위 고정 슬롯 + 순환 슬롯(수요 갱신 오래된 순) — 전체 커버리지 확보
    d = make_db(tmp_path)
    a = d.upsert_keyword("기회최상", day="2026-08-01")
    b = d.upsert_keyword("기회중간", day="2026-08-01")
    c = d.upsert_keyword("수요오래됨", day="2026-08-01")
    e = d.upsert_keyword("수요미갱신", day="2026-08-01")
    d.insert_daily_stats(a, "2026-08-02", {"opportunity": 90.0})
    d.insert_daily_stats(b, "2026-08-02", {"opportunity": 80.0})
    d.insert_daily_stats(c, "2026-08-02", {"opportunity": 10.0, "demand_idx": 0.001})
    d.insert_daily_stats(e, "2026-08-02", {"opportunity": 5.0})
    # c는 08-01에 수요 갱신 이력 추가 → e(미갱신·NULL)가 순환 우선
    d.update_demand_idx(c, "2026-08-01", 0.001)
    targets = d.datalab_targets("2026-08-02", priority_n=2, rotate_n=2)
    assert [t["keyword"] for t in targets] == ["기회최상", "기회중간", "수요미갱신", "수요오래됨"]


def test_datalab_targets_excludes_unsnapshotted_and_inactive(tmp_path):
    d = make_db(tmp_path)
    a = d.upsert_keyword("활성스냅샷", day="2026-08-01")
    b = d.upsert_keyword("비활성", day="2026-08-01")
    c = d.upsert_keyword("오늘미스냅샷", day="2026-08-01")
    d.insert_daily_stats(a, "2026-08-02", {"opportunity": 90.0})
    d.insert_daily_stats(b, "2026-08-02", {"opportunity": 80.0})
    d.insert_daily_stats(c, "2026-08-01", {"opportunity": 70.0})  # 어제만
    d.set_active(b, 0)
    targets = d.datalab_targets("2026-08-02", priority_n=5, rotate_n=5)
    assert [t["keyword"] for t in targets] == ["활성스냅샷"]


# ---------- v17: 콘텐츠 배치·AdPost용 초안 조회 ----------

def test_list_drafts_missing_images(tmp_path):
    import json as json_mod
    d = make_db(tmp_path)
    kid = d.upsert_keyword("키워드", day="2026-08-01")
    d1 = d.insert_draft(kid, "t1", "fp", "## 섹션\n본문", created_at="n")
    d2 = d.insert_draft(kid, "t2", "fp", "## 섹션\n본문",
                        image_url="https://x", created_at="n")
    d.update_draft_section_images(  # 전부 있음 — 대상 아님
        d2, json_mod.dumps(["https://x/s.png"]), "n")
    d3 = d.insert_draft(kid, "t3", "fp", "## 섹션\n본문",
                        image_url="https://x", created_at="n")  # 섹션만 누락
    d4 = d.insert_draft(kid, "t4", "fp", "H2 없는 본문", created_at="n")  # 대표만 필요
    rows = d.list_drafts_missing_images(10)
    assert [r["id"] for r in rows] == [d1, d3, d4]


def test_keywords_without_drafts_priority_order(tmp_path):
    d = make_db(tmp_path)
    low = d.upsert_keyword("저순위", category="일상", day="2026-08-01")
    high = d.upsert_keyword("고순위", category="보험", day="2026-08-01")
    has_draft = d.upsert_keyword("초안있음", category="보험", day="2026-08-01")
    for kid, opp in ((low, 5.0), (high, 5.0), (has_draft, 5.0)):
        d.insert_daily_stats(kid, "2026-08-02",
                             {"opportunity": opp, "ai_cite_idx": 0.5,
                              "demand_idx": 0.005})
    d.insert_draft(has_draft, "t", "fp", "본문", created_at="n")
    rows = d.keywords_without_drafts(10)
    assert [r["keyword"] for r in rows] == ["고순위", "저순위"]  # CPC 등급 순


def test_record_adpost_metrics_updates_score_and_boost(tmp_path):
    d = make_db(tmp_path)
    kid = d.upsert_keyword("키워드", day="2026-08-01")
    did = d.insert_draft(kid, "t", "fp", "본문", created_at="n")
    d.record_adpost_metrics(did, kid, 1500.0, 2500, 50, 62.5,
                            "2026-08-05T00:00:00+09:00", "2026-08-06T00:00:00+09:00", 0)
    draft = d.get_draft(did)
    assert draft["adpost_revenue"] == 1500.0
    assert draft["adpost_impressions"] == 2500
    assert draft["performance_score"] == 62.5
    assert draft["published_at"] == "2026-08-05T00:00:00+09:00"  # 미게시면 기록
    # 재기록 시 기존 published_at 유지
    d.record_adpost_metrics(did, kid, 3000.0, 5000, 100, 100.0,
                            "2026-08-06T00:00:00+09:00", "2026-08-06T00:00:00+09:00", 10)
    draft = d.get_draft(did)
    assert draft["published_at"] == "2026-08-05T00:00:00+09:00"
    assert d.get_keyword(kid)["performance_boost"] == 10.0
