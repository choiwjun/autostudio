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


def test_retire_protects_null_scores(tmp_path):
    # v3/v4: 쇼핑 클릭 미조회(분야 미매칭) 키워드는 0점 취급 금지 — 은퇴 보호
    d = make_db(tmp_path)
    d.upsert_keyword("쇼핑클릭미조회", day="2026-07-01")
    bad = d.upsert_keyword("확실히저조", day="2026-07-01")
    d.insert_daily_stats(d.upsert_keyword("쇼핑클릭미조회", day="2026-07-01"),
                         "2026-08-01", {"opportunity": 10.0, "shop_click_idx": None})
    d.insert_daily_stats(bad, "2026-08-01", {"opportunity": 10.0, "shop_click_idx": 0.1})
    victims = d.find_retire_candidates("2026-07-20", "2026-07-27", 35.0, 0.5)
    assert [v["keyword"] for v in victims] == ["확실히저조"]


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
