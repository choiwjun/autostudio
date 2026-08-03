# 네이버 블로그 수익 키워드 대시보드 — 구현 계획 (v3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**문서 버전:** v3 (2026-08-03) — 스펙 v3·UX 스펙 v2 정합. v2 대비 변경: ① 수동 예산을 발굴·개별 호출까지 전 구간 적용 ② 목록 LEFT JOIN(스냅샷 없는 신규 키워드 표시) ③ 데이터랩 오류 DatalabError 정규화 ④ 실행 잠금 원자화(부분 유니크 인덱스) + stale 60분 ⑤ cron-job.org 대체 경로 trigger=schedule(전 구간) ⑥ 프로덕션 토큰 fail-closed ⑦ 증감률 전일 대비만 산출 ⑧ 은퇴 NULL 점수 보호 ⑨ 자동완성 차단 exit 1 ⑩ run 상태 done/partial/failed 구분 ⑪ API 정렬 방향·유망 프리셋 ⑫ 대시보드 UX 전 항목 구현(게이지·sticky·스켈레톤·오류 재시도·CTA) ⑬ 시드 분야 전파 + /categories 통합 ⑭ 필터 사유 기록 ⑮ Postgres 통합·브라우저 e2e 테스트 신설 ⑯ 배치 시간 실측 절차 신설

**Goal:** 매일 1회 키워드 스냅샷(자동완성 발굴 + blog/shop 검색 분석 + 데이터랩 수요 확증)을 쌓아 "기회 점수 + 상업성 점수 + 수요지수"로 정렬된 키워드 대시보드를 제공하는 클라우드 도구 구축 (로컬 PC 불필요)

**Architecture:** GitHub Actions cron(매일 07:17 KST)이 `collect.py`를 실행해 Supabase Postgres(Supavisor 풀러 경유)에 저장하고, Vercel(Hobby)이 FastAPI + 대시보드를 서빙. 파이프라인: 자동완성 발굴 → 정제 필터 → 스냅샷+점수 사전계산 → 데이터랩 수요 확증 → 자동 은퇴 → 보존 정리. DB 레이어는 URL 스킴으로 SQLite(개발/테스트)·Postgres(프로덕션) 전환. 날짜·시각은 전부 KST(`config.today_kst()`). 모든 외부 의존은 config/env 분리.

**Tech Stack:** Python 3.11+, FastAPI(ASGI, Vercel), requests, psycopg2, Supabase Postgres, GitHub Actions, Chart.js(CDN), 단일 HTML 페이지

**스펙:** `docs/superpowers/specs/2026-08-03-naver-blog-keyword-dashboard-design.md` (v3)
**UX 스펙:** `docs/superpowers/specs/2026-08-03-naver-blog-keyword-dashboard-ux.md` (v2)

---

## 파일 구조

```
my1/
├── .env.example            # 시크릿 템플릿 (네이버 키, DATABASE_URL, 토큰 등)
├── .gitignore              # .env, DB, 캐시 제외
├── requirements.txt        # 의존성
├── conftest.py             # (빈 파일) pytest 모듈 경로 확보
├── config.py               # 설정 로드 + KST 시간 헬퍼
├── db.py                   # DB 레이어 (sqlite 개발/테스트, postgres 프로덕션)
├── naver_client.py         # 네이버 검색 API 클라이언트 (blog/shop)
├── autocomplete.py         # 자동완성 크롤러 (재시도/차단감지/기존키워드 경유 BFS)
├── refine.py               # 정제 필터 (2단 블랙리스트 + 포털 토큰)
├── analyzer.py             # 키워드당 스냅샷 (blog 2종 + shop 1종)
├── scoring.py              # 점수 엔진 (기회/상업성)
├── datalab.py              # 데이터랩 수요 확증 (앵커 정규화)
├── collect.py              # 수집 실행 (DB 잠금·시간 예산·은퇴·보존 정리)
├── server.py               # FastAPI 앱 (인증·페이징·재연결)
├── vercel.json             # Vercel 함수 설정 (60초 상한, rewrites)
├── api/index.py            # Vercel Python 런타임 진입점
├── .github/workflows/
│   └── daily-collect.yml   # 매일 07:17 KST 수집 (concurrency + keep-alive)
├── static/index.html       # 대시보드 단일 페이지
└── tests/
    ├── test_config.py
    ├── test_db.py
    ├── test_db_postgres.py   # v3: Postgres 통합 (DATABASE_URL 설정 시, Task 15)
    ├── test_naver_client.py
    ├── test_autocomplete.py
    ├── test_refine.py
    ├── test_analyzer.py
    ├── test_scoring.py
    ├── test_datalab.py
    ├── test_collect.py
    ├── test_api.py
    └── e2e_dashboard.py      # v3: 브라우저 검증 (선택, Task 15)
```

---

### Task 0: 프로젝트 초기화

**Files:**
- Create: `.gitignore`
- Create: `requirements.txt`
- Create: `.env.example`

- [ ] **Step 1: git 저장소 초기화**

```bash
git init
```

- [ ] **Step 2: .gitignore 작성** (v1의 `collect.lock`은 DB 잠금으로 교체되어 불필요)

```
.env
__pycache__/
*.pyc
.pytest_cache/
*.db
data/
.venv/
```

- [ ] **Step 3: requirements.txt 작성**

```
fastapi==0.115.6
uvicorn[standard]==0.34.0
requests==2.32.3
python-dotenv==1.0.1
psycopg2-binary==2.9.10
pytest==8.3.4
httpx==0.28.1
```

- [ ] **Step 4: .env.example 작성** (풀러 주소 가이드 포함 — 직결 주소는 IPv6 전용이라 GH Actions/Vercel에서 연결 불가)

```
NAVER_CLIENT_ID=YOUR_CLIENT_ID
NAVER_CLIENT_SECRET=YOUR_CLIENT_SECRET
# 개발/테스트(로컬): sqlite:///data/keywords.db
# GitHub Actions(수집 배치): Supabase "Session pooler" (포트 5432)
#   postgresql://postgres.<ref>:<pw>@aws-0-<region>.pooler.supabase.com:5432/postgres
# Vercel(서버리스 API): Supabase "Transaction pooler" (포트 6543)
#   postgresql://postgres.<ref>:<pw>@aws-0-<region>.pooler.supabase.com:6543/postgres
# 주의: db.<ref>.supabase.co 직결 주소는 무료 티어에서 IPv6 전용 → 사용 금지
DATABASE_URL=sqlite:///data/keywords.db
# ENV=production이면 DASHBOARD_TOKEN 필수 — 미설정 시 서버 기동 거부 (fail-closed, 스펙 §7 v3)
ENV=development
# 실행 잠금 stale 기준 — GH Actions timeout-minutes(60)와 정합 (v3: 30분은 장시간 실행이 회수될 수 있음)
RUN_LOCK_STALE_MINUTES=60
DAILY_NEW_KEYWORD_CAP=100
ACTIVE_KEYWORD_CAP=1000
AUTOCOMPLETE_URL=https://ac.search.naver.com/nx/ac
AUTOCOMPLETE_MAX_DEPTH=2
AUTOCOMPLETE_MAX_REQUESTS=300
MANUAL_BUDGET_SECONDS=45
DASHBOARD_TOKEN=change-me
DATALAB_ENABLED=1
DATALAB_ANCHOR=냉장고
```

- [ ] **Step 5: 가상환경 생성 및 설치**

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

- [ ] **Step 6: conftest.py 생성 (pytest가 루트 모듈을 찾도록 — 크로스 플랫폼 명령)**

```bash
python -c "open('conftest.py', 'a').close()"
```

- [ ] **Step 7: 커밋**

```bash
git add .gitignore requirements.txt .env.example conftest.py
git commit -m "chore: project scaffolding"
```

---

### Task 1: 설정 모듈 (config.py) — KST 시간 헬퍼 포함

**Files:**
- Create: `config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_config.py
from datetime import date

import config


def test_load_config_with_defaults(monkeypatch):
    for key in (
        "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "DATABASE_URL",
        "DAILY_NEW_KEYWORD_CAP", "ACTIVE_KEYWORD_CAP", "AUTOCOMPLETE_URL",
        "AUTOCOMPLETE_MAX_DEPTH", "AUTOCOMPLETE_MAX_REQUESTS",
        "MANUAL_BUDGET_SECONDS", "DASHBOARD_TOKEN", "DATALAB_ENABLED",
        "DATALAB_ANCHOR", "ENV", "RUN_LOCK_STALE_MINUTES",
    ):
        monkeypatch.delenv(key, raising=False)
    cfg = config.load_config(load_env=False)
    assert cfg["db_url"] == "sqlite:///data/keywords.db"
    assert cfg["daily_new_keyword_cap"] == 100
    assert cfg["active_keyword_cap"] == 1000
    assert cfg["autocomplete_max_depth"] == 2
    assert cfg["autocomplete_max_requests"] == 300
    assert cfg["manual_budget_seconds"] == 45
    assert cfg["dashboard_token"] == ""
    assert cfg["datalab_enabled"] is True
    assert cfg["datalab_anchor"] == "냉장고"
    assert cfg["env"] == "development"          # v3: fail-closed 분기용
    assert cfg["run_lock_stale_minutes"] == 60  # v3: GH Actions timeout 정합


def test_load_config_with_env(monkeypatch):
    monkeypatch.setenv("NAVER_CLIENT_ID", "cid")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "csec")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/db")
    monkeypatch.setenv("DAILY_NEW_KEYWORD_CAP", "50")
    monkeypatch.setenv("ACTIVE_KEYWORD_CAP", "500")
    monkeypatch.setenv("DASHBOARD_TOKEN", "sekret")
    monkeypatch.setenv("DATALAB_ENABLED", "0")
    cfg = config.load_config(load_env=False)
    assert cfg["client_id"] == "cid"
    assert cfg["client_secret"] == "csec"
    assert cfg["db_url"] == "postgresql://u:p@localhost:5432/db"
    assert cfg["daily_new_keyword_cap"] == 50
    assert cfg["active_keyword_cap"] == 500
    assert cfg["dashboard_token"] == "sekret"
    assert cfg["datalab_enabled"] is False


def test_load_config_env_and_stale(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("RUN_LOCK_STALE_MINUTES", "45")
    cfg = config.load_config(load_env=False)
    assert cfg["env"] == "production"
    assert cfg["run_lock_stale_minutes"] == 45


def test_kst_helpers():
    # 러너/서버리스는 UTC — 날짜 키는 반드시 KST 헬퍼로만 생성 (스펙 §3)
    assert isinstance(config.today_kst(), date)
    now = config.now_kst_iso()
    assert now.endswith("+09:00")
    earlier = config.minutes_ago_kst_iso(30)
    assert earlier < now
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL (module 'config' 없음 또는 속성 없음)

- [ ] **Step 3: 구현**

```python
# config.py
import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

# KST는 DST가 없으므로 고정 오프셋 사용 (tzdata 의존성 불필요, Windows 포함 동일 동작)
KST = timezone(timedelta(hours=9))


def today_kst():
    return datetime.now(KST).date()


def now_kst_iso():
    return datetime.now(KST).isoformat(timespec="seconds")


def minutes_ago_kst_iso(minutes):
    return (datetime.now(KST) - timedelta(minutes=minutes)).isoformat(timespec="seconds")


def load_config(load_env=True):
    if load_env:
        load_dotenv()
    return {
        "client_id": os.getenv("NAVER_CLIENT_ID", ""),
        "client_secret": os.getenv("NAVER_CLIENT_SECRET", ""),
        "db_url": os.getenv("DATABASE_URL", "sqlite:///data/keywords.db"),
        "daily_new_keyword_cap": int(os.getenv("DAILY_NEW_KEYWORD_CAP", "100")),
        "active_keyword_cap": int(os.getenv("ACTIVE_KEYWORD_CAP", "1000")),
        "autocomplete_url": os.getenv(
            "AUTOCOMPLETE_URL", "https://ac.search.naver.com/nx/ac"
        ),
        "autocomplete_max_depth": int(os.getenv("AUTOCOMPLETE_MAX_DEPTH", "2")),
        "autocomplete_max_requests": int(os.getenv("AUTOCOMPLETE_MAX_REQUESTS", "300")),
        "manual_budget_seconds": int(os.getenv("MANUAL_BUDGET_SECONDS", "45")),
        "dashboard_token": os.getenv("DASHBOARD_TOKEN", ""),
        "datalab_enabled": os.getenv("DATALAB_ENABLED", "1") == "1",
        "datalab_anchor": os.getenv("DATALAB_ANCHOR", "냉장고"),
        "env": os.getenv("ENV", "development"),
        "run_lock_stale_minutes": int(os.getenv("RUN_LOCK_STALE_MINUTES", "60")),
    }
```

- [ ] **Step 4: 테스트 실행 (통과 확인)**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 커밋**

```bash
git add config.py tests/test_config.py
git commit -m "feat: config module with KST helpers"
```

---

### Task 2: DB 레이어 (db.py) — v2 스키마 + 수명주기 + 실행 잠금 + 목록 쿼리

**Files:**
- Create: `db.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: 테스트 작성**

```python
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
    d.insert_daily_stats(bad, "2026-08-01", {"opportunity": 10.0, "commercial": 5.0})
    d.insert_daily_stats(good, "2026-08-01", {"opportunity": 80.0, "commercial": 5.0})
    victims = d.find_retire_candidates("2026-07-20", "2026-07-27", 35.0, 30.0)
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
    # v3: shop_error(commercial NULL) 키워드는 0점 취급 금지 — 은퇴 보호
    d = make_db(tmp_path)
    d.upsert_keyword("쇼핑실패", day="2026-07-01")
    bad = d.upsert_keyword("확실히저조", day="2026-07-01")
    d.insert_daily_stats(d.upsert_keyword("쇼핑실패", day="2026-07-01"),
                         "2026-08-01", {"opportunity": 10.0, "commercial": None})
    d.insert_daily_stats(bad, "2026-08-01", {"opportunity": 10.0, "commercial": 5.0})
    victims = d.find_retire_candidates("2026-07-20", "2026-07-27", 35.0, 30.0)
    assert [v["keyword"] for v in victims] == ["확실히저조"]


def test_categories_include_seed_and_keyword(tmp_path):
    # v3: /categories = shop + 키워드 + 시드 분야 통합
    d = make_db(tmp_path)
    d.add_seed("에어프라이어", "요리")
    kid = d.upsert_keyword("선풍기", category="가전", day="2026-08-01")
    d.insert_daily_stats(kid, "2026-08-01", {"shop_category": "디지털"})
    assert d.list_categories() == ["가전", "디지털", "요리"]


def test_query_sort_dir_and_thresholds(tmp_path):
    # v3: 정렬 방향 + 유망 프리셋 임계 필터
    d = make_db(tmp_path)
    a = d.upsert_keyword("에어프라이어", day="2026-08-01")
    b = d.upsert_keyword("선풍기", day="2026-08-02")
    d.insert_daily_stats(a, "2026-08-02", {
        "total_sim": 100, "opportunity": 64.1, "commercial": 100.0, "demand_idx": 0.08})
    d.insert_daily_stats(b, "2026-08-02", {
        "total_sim": 10, "opportunity": 30.0, "commercial": 2.5, "demand_idx": None})
    assert [r["keyword"] for r in d.query_keywords()] == ["에어프라이어", "선풍기"]
    assert [r["keyword"] for r in d.query_keywords(sort_dir="asc")] == ["선풍기", "에어프라이어"]
    assert [r["keyword"] for r in d.query_keywords(
        opportunity_min=70, commercial_min=60, demand_min=0.01)] == []
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

Run: `python -m pytest tests/test_db.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: 구현**

```python
# db.py
import os
import sqlite3

try:
    import psycopg2
    CONNECTION_ERRORS = (psycopg2.OperationalError, psycopg2.InterfaceError)
except ImportError:  # 로컬에서 psycopg2 없이도 SQLite 사용 가능
    CONNECTION_ERRORS = ()

# SQLite(개발/테스트)와 Postgres(프로덕션) 스키마. URL 스킴으로 백엔드 전환.
# 점수 4종(growth/opportunity/commercial/demand_idx)은 수집 시 사전계산 저장 (NULL = 미산출)
SCHEMAS = {
    "sqlite": """
CREATE TABLE IF NOT EXISTS seed_keywords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS keywords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL DEFAULT '',
    first_seen TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS daily_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword_id INTEGER NOT NULL REFERENCES keywords(id),
    day TEXT NOT NULL,
    total_sim INTEGER NOT NULL DEFAULT 0,
    total_date INTEGER NOT NULL DEFAULT 0,
    fresh_ratio REAL NOT NULL DEFAULT 0,
    shop_total INTEGER NOT NULL DEFAULT 0,
    shop_avg_price INTEGER NOT NULL DEFAULT 0,
    shop_category TEXT NOT NULL DEFAULT '',
    shop_error TEXT NOT NULL DEFAULT '',
    growth REAL,
    opportunity REAL,
    commercial REAL,
    demand_idx REAL,
    UNIQUE(keyword_id, day)
);
CREATE TABLE IF NOT EXISTS top_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword_id INTEGER NOT NULL REFERENCES keywords(id),
    day TEXT NOT NULL,
    post_date TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS collection_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at TEXT NOT NULL,
    keyword TEXT NOT NULL,
    action TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS collection_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    run_trigger TEXT NOT NULL DEFAULT '',
    new_keywords INTEGER NOT NULL DEFAULT 0,
    snapshotted INTEGER NOT NULL DEFAULT 0,
    errors INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT ''
);
-- v3: 실행 잠금 원자화 — running 행은 1개만 존재 (동시 INSERT 경합 차단)
CREATE UNIQUE INDEX IF NOT EXISTS idx_collection_runs_running
    ON collection_runs(status) WHERE status = 'running';
""",
    "postgres": """
CREATE TABLE IF NOT EXISTS seed_keywords (
    id SERIAL PRIMARY KEY,
    keyword TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS keywords (
    id SERIAL PRIMARY KEY,
    keyword TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL DEFAULT '',
    first_seen TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS daily_stats (
    id SERIAL PRIMARY KEY,
    keyword_id INTEGER NOT NULL REFERENCES keywords(id),
    day TEXT NOT NULL,
    total_sim INTEGER NOT NULL DEFAULT 0,
    total_date INTEGER NOT NULL DEFAULT 0,
    fresh_ratio DOUBLE PRECISION NOT NULL DEFAULT 0,
    shop_total INTEGER NOT NULL DEFAULT 0,
    shop_avg_price INTEGER NOT NULL DEFAULT 0,
    shop_category TEXT NOT NULL DEFAULT '',
    shop_error TEXT NOT NULL DEFAULT '',
    growth DOUBLE PRECISION,
    opportunity DOUBLE PRECISION,
    commercial DOUBLE PRECISION,
    demand_idx DOUBLE PRECISION,
    UNIQUE(keyword_id, day)
);
CREATE TABLE IF NOT EXISTS top_results (
    id SERIAL PRIMARY KEY,
    keyword_id INTEGER NOT NULL REFERENCES keywords(id),
    day TEXT NOT NULL,
    post_date TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS collection_log (
    id SERIAL PRIMARY KEY,
    run_at TEXT NOT NULL,
    keyword TEXT NOT NULL,
    action TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS collection_runs (
    id SERIAL PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    run_trigger TEXT NOT NULL DEFAULT '',
    new_keywords INTEGER NOT NULL DEFAULT 0,
    snapshotted INTEGER NOT NULL DEFAULT 0,
    errors INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT ''
);
-- v3: 실행 잠금 원자화 — running 행은 1개만 존재 (동시 INSERT 경합 차단)
CREATE UNIQUE INDEX IF NOT EXISTS idx_collection_runs_running
    ON collection_runs(status) WHERE status = 'running';
""",
}

_STATS_COLUMNS = (
    "total_sim", "total_date", "fresh_ratio", "shop_total", "shop_avg_price",
    "shop_category", "shop_error", "growth", "opportunity", "commercial", "demand_idx",
)


class Database:
    SORT_COLUMNS = {
        "opportunity": "ds.opportunity",
        "commercial": "ds.commercial",
        "demand": "ds.demand_idx",
        "growth": "ds.growth",
    }

    # 키워드별 "최신 스냅샷 1건"을 조인하는 공통 베이스 (N+1 제거의 핵심)
    # v3: LEFT JOIN — 스냅샷 없는 신규 키워드도 반환 ("데이터 쌓는 중" 상태 표시 전제).
    #     INNER JOIN이면 발굴 직후(예산 소진 등) 키워드가 대시보드에서 사라짐
    _KEYWORD_BASE = """
FROM keywords k
LEFT JOIN daily_stats ds
  ON ds.keyword_id = k.id
 AND ds.day = (SELECT MAX(day) FROM daily_stats d2 WHERE d2.keyword_id = k.id)"""

    def __init__(self, url, connect=True):
        self.url = url
        self.dialect = "postgres" if url.startswith("postgresql") else "sqlite"
        if self.dialect == "sqlite":
            self.path = url.replace("sqlite:///", "", 1)
            parent = os.path.dirname(self.path)
            if parent:
                os.makedirs(parent, exist_ok=True)
        self.conn = None
        if connect:
            self._connect()

    def _connect(self):
        if self.dialect == "postgres":
            import psycopg2
            from psycopg2.extras import RealDictCursor
            self.conn = psycopg2.connect(self.url, cursor_factory=RealDictCursor)
        else:
            # check_same_thread=False: FastAPI 동기 엔드포인트는 스레드풀에서 실행됨
            self.conn = sqlite3.connect(self.path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row

    def _q_once(self, sqlite_sql, pg_sql, params, fetch=False):
        if self.dialect == "postgres":
            with self.conn.cursor() as cur:
                cur.execute(pg_sql, params)
                rows = [dict(r) for r in cur.fetchall()] if fetch else None
                self.conn.commit()
            return rows
        cur = self.conn.execute(sqlite_sql, params)
        self.conn.commit()
        if fetch:
            return [dict(r) for r in cur.fetchall()]
        return None

    def _q(self, sqlite_sql, pg_sql, params, fetch=False):
        # v3: 커넥션 사망(유휴 종료·풀러 재시작) 시 1회 재연결 후 재시도 (스펙 §3)
        # SQLite는 CONNECTION_ERRORS가 ()라 무영향. 서버·배치 양쪽 공용
        for attempt in (0, 1):
            try:
                return self._q_once(sqlite_sql, pg_sql, params, fetch)
            except CONNECTION_ERRORS:
                if attempt == 1:
                    raise
                self._connect()

    def _qd(self, sql, params, fetch=False):
        # 동적 SQL용: '?' 플레이스홀더만 사용한다는 전제로 pg용 '%s' 변환
        return self._q(sql, sql.replace("?", "%s"), params, fetch=fetch)

    def init(self):
        # v3: 재연결 1회 재시도 (배치 중 풀러 재시작 대비)
        for attempt in (0, 1):
            try:
                if self.dialect == "postgres":
                    self._q(None, SCHEMAS["postgres"], ())
                else:
                    self.conn.executescript(SCHEMAS["sqlite"])
                    self.conn.commit()
                return
            except CONNECTION_ERRORS:
                if attempt == 1:
                    raise
                self._connect()

    # ---------- 시드 ----------

    def add_seed(self, keyword, category=""):
        self._q(
            "INSERT OR IGNORE INTO seed_keywords (keyword, category) VALUES (?, ?)",
            "INSERT INTO seed_keywords (keyword, category) VALUES (%s, %s) "
            "ON CONFLICT (keyword) DO NOTHING",
            (keyword, category),
        )

    def list_seeds(self):
        return self._qd("SELECT * FROM seed_keywords ORDER BY id", (), fetch=True)

    def delete_seed(self, seed_id):
        self._qd("DELETE FROM seed_keywords WHERE id = ?", (seed_id,))

    # ---------- 키워드 ----------

    def upsert_keyword(self, keyword, category="", day=""):
        self._q(
            "INSERT OR IGNORE INTO keywords (keyword, category, first_seen) VALUES (?, ?, ?)",
            "INSERT INTO keywords (keyword, category, first_seen) VALUES (%s, %s, %s) "
            "ON CONFLICT (keyword) DO NOTHING",
            (keyword, category, day),
        )
        if category:  # 빈 값으로 기존 분야를 지우지 않음 (v1 결함 수정)
            self._qd(
                "UPDATE keywords SET category = ? WHERE keyword = ?",
                (category, keyword),
            )
        rows = self._qd("SELECT id FROM keywords WHERE keyword = ?", (keyword,), fetch=True)
        return rows[0]["id"]

    def set_active(self, keyword_id, active):
        self._qd("UPDATE keywords SET active = ? WHERE id = ?", (active, keyword_id))

    def get_keyword(self, keyword_id):
        rows = self._qd("SELECT * FROM keywords WHERE id = ?", (keyword_id,), fetch=True)
        return rows[0] if rows else None

    def list_active_keywords_stale_first(self):
        # 오래 수집 안 된 키워드 우선 — 시간 예산 부분 수집이 자연스럽게 순환되도록
        sql = """
SELECT k.*, COALESCE(
    (SELECT MAX(day) FROM daily_stats ds WHERE ds.keyword_id = k.id), ''
) AS last_day
FROM keywords k WHERE k.active = 1
ORDER BY last_day, k.id"""
        return self._qd(sql, (), fetch=True)

    def count_new_keywords_today(self, day):
        rows = self._qd(
            "SELECT COUNT(*) AS c FROM keywords WHERE first_seen = ?", (day,), fetch=True
        )
        return rows[0]["c"]

    def count_active(self):
        rows = self._qd("SELECT COUNT(*) AS c FROM keywords WHERE active = 1", (), fetch=True)
        return rows[0]["c"]

    def all_keyword_names(self):
        rows = self._qd("SELECT keyword FROM keywords", (), fetch=True)
        return {r["keyword"] for r in rows}

    # ---------- 스냅샷 ----------

    def insert_daily_stats(self, keyword_id, day, stats):
        values = (
            keyword_id, day,
            stats.get("total_sim", 0), stats.get("total_date", 0),
            stats.get("fresh_ratio", 0.0), stats.get("shop_total", 0),
            stats.get("shop_avg_price", 0), stats.get("shop_category", ""),
            stats.get("shop_error") or "",
            stats.get("growth"), stats.get("opportunity"),
            stats.get("commercial"), stats.get("demand_idx"),
        )
        cols = ", ".join(("keyword_id", "day") + _STATS_COLUMNS)
        self._q(
            f"INSERT OR REPLACE INTO daily_stats ({cols}) "
            f"VALUES ({', '.join('?' * 13)})",
            f"INSERT INTO daily_stats ({cols}) VALUES ({', '.join(['%s'] * 13)}) "
            "ON CONFLICT (keyword_id, day) DO UPDATE SET "
            + ", ".join(f"{c} = EXCLUDED.{c}" for c in _STATS_COLUMNS),
            values,
        )

    def get_latest_stats(self, keyword_id):
        rows = self._qd(
            "SELECT * FROM daily_stats WHERE keyword_id = ? ORDER BY day DESC LIMIT 1",
            (keyword_id,), fetch=True,
        )
        return rows[0] if rows else None

    def get_prev_stats(self, keyword_id, before_day):
        rows = self._qd(
            "SELECT * FROM daily_stats WHERE keyword_id = ? AND day < ? "
            "ORDER BY day DESC LIMIT 1",
            (keyword_id, before_day), fetch=True,
        )
        return rows[0] if rows else None

    def get_history(self, keyword_id):
        return self._qd(
            "SELECT * FROM daily_stats WHERE keyword_id = ? ORDER BY day",
            (keyword_id,), fetch=True,
        )

    def update_demand_idx(self, keyword_id, day, demand_idx):
        self._qd(
            "UPDATE daily_stats SET demand_idx = ? WHERE keyword_id = ? AND day = ?",
            (demand_idx, keyword_id, day),
        )

    def top_by_opportunity(self, day, limit):
        sql = """
SELECT k.id, k.keyword FROM daily_stats ds
JOIN keywords k ON k.id = ds.keyword_id
WHERE ds.day = ? AND ds.opportunity IS NOT NULL AND k.active = 1
ORDER BY ds.opportunity DESC LIMIT ?"""
        return self._qd(sql, (day, limit), fetch=True)

    # ---------- 상위글 발행일 ----------

    def insert_top_results(self, keyword_id, day, post_dates):
        self._qd(
            "DELETE FROM top_results WHERE keyword_id = ? AND day = ?", (keyword_id, day)
        )
        rows = [(keyword_id, day, pd) for pd in post_dates]
        if not rows:
            return
        if self.dialect == "postgres":
            with self.conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO top_results (keyword_id, day, post_date) VALUES (%s, %s, %s)",
                    rows,
                )
                self.conn.commit()
        else:
            self.conn.executemany(
                "INSERT INTO top_results (keyword_id, day, post_date) VALUES (?, ?, ?)",
                rows,
            )
            self.conn.commit()

    def get_top_results(self, keyword_id, day):
        rows = self._qd(
            "SELECT post_date FROM top_results WHERE keyword_id = ? AND day = ? ORDER BY id",
            (keyword_id, day), fetch=True,
        )
        return [r["post_date"] for r in rows]

    # ---------- 로그 / 실행 이력(잠금) ----------

    def log_collection(self, keyword, action, note, run_at):
        self._qd(
            "INSERT INTO collection_log (run_at, keyword, action, note) VALUES (?, ?, ?, ?)",
            (run_at, keyword, action, note),
        )

    def get_logs(self, limit=100):
        return self._qd(
            "SELECT * FROM collection_log ORDER BY id DESC LIMIT ?", (limit,), fetch=True
        )

    def start_run(self, run_trigger, now_iso, stale_before_iso):
        """실행 잠금 — v3: 부분 유니크 인덱스(status='running')로 원자 취득.
        v2는 SELECT→INSERT 사이 경합 창이 있어 동시 실행 2건이 모두 잠금을 얻을 수 있었음.
        v3는 조건부 INSERT + 유니크 인덱스로 하나만 성공하고, 소유권은 started_at으로 확인한다."""
        rows = self._qd(
            "SELECT id, started_at FROM collection_runs WHERE status = 'running' "
            "ORDER BY id DESC LIMIT 1",
            (), fetch=True,
        )
        if rows and rows[0]["started_at"] <= stale_before_iso:
            self._qd(
                "UPDATE collection_runs SET status = 'failed', note = 'stale lock 회수' "
                "WHERE id = ?",
                (rows[0]["id"],),
            )
        self._q(
            "INSERT OR IGNORE INTO collection_runs (started_at, status, run_trigger) "
            "SELECT ?, 'running', ? WHERE NOT EXISTS "
            "(SELECT 1 FROM collection_runs WHERE status = 'running')",
            "INSERT INTO collection_runs (started_at, status, run_trigger) "
            "SELECT %s, 'running', %s WHERE NOT EXISTS "
            "(SELECT 1 FROM collection_runs WHERE status = 'running') "
            "ON CONFLICT DO NOTHING",
            (now_iso, run_trigger),
        )
        rows = self._qd(
            "SELECT id, started_at FROM collection_runs WHERE status = 'running' "
            "ORDER BY id DESC LIMIT 1",
            (), fetch=True,
        )
        if not rows or rows[0]["started_at"] != now_iso:
            return None  # 경합 패배 — 다른 실행이 잠금 보유
        return rows[0]["id"]

    def finish_run(self, run_id, status, finished_iso, result):
        # v3: status는 호출 측이 done/partial/failed로 구분해 전달 (note의 partial 표기 제거)
        self._qd(
            "UPDATE collection_runs SET status = ?, finished_at = ?, new_keywords = ?, "
            "snapshotted = ?, errors = ?, note = ? WHERE id = ?",
            (
                status, finished_iso,
                result.get("new_keywords", 0), result.get("snapshotted", 0),
                len(result.get("errors", [])),
                "", run_id,
            ),
        )

    def get_last_runs(self, limit=5):
        return self._qd(
            "SELECT * FROM collection_runs ORDER BY id DESC LIMIT ?", (limit,), fetch=True
        )

    # ---------- 수명주기 ----------

    def find_retire_candidates(self, first_seen_before, since_day, opp_lt, com_lt):
        """발견 오래됨 + 최근 스냅샷 존재 + 최근 성과 전부 저조 → 은퇴 후보.
        v3: 최근 7일 창의 스냅샷 중 하나라도 기회/상업성 점수가 NULL이면 보호한다
        (shop_error로 상업성 미산출된 키워드를 0점 취급해 오은퇴시키지 않음 — 스펙 §4.6).
        NULL은 수집 실패일 수 있으므로 '저성과' 판정의 근거가 될 수 없다."""
        sql = """
SELECT k.id, k.keyword FROM keywords k
WHERE k.active = 1 AND k.first_seen <= ?
  AND EXISTS (
    SELECT 1 FROM daily_stats ds WHERE ds.keyword_id = k.id AND ds.day >= ?
      AND ds.opportunity IS NOT NULL AND ds.commercial IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM daily_stats ds WHERE ds.keyword_id = k.id AND ds.day >= ?
      AND (ds.opportunity IS NULL OR ds.commercial IS NULL
           OR ds.opportunity >= ? OR ds.commercial >= ?))
ORDER BY k.id"""
        return self._qd(sql, (first_seen_before, since_day, since_day, opp_lt, com_lt), fetch=True)

    def cleanup(self, stats_before_day, top_before_day, log_before_ts):
        self._qd("DELETE FROM daily_stats WHERE day < ?", (stats_before_day,))
        self._qd("DELETE FROM top_results WHERE day < ?", (top_before_day,))
        self._qd("DELETE FROM collection_log WHERE run_at < ?", (log_before_ts,))

    # ---------- 대시보드 목록 (단일 쿼리 + 페이징) ----------

    def _keyword_where(self, category, commercial_min, q, discovered_since, active,
                       opportunity_min=0.0, demand_min=0.0):
        where, params = [], []
        if active is not None:
            where.append("k.active = ?")
            params.append(active)
        if category:
            where.append("(ds.shop_category LIKE ? OR k.category = ?)")
            params += [category + "%", category]
        if commercial_min:
            where.append("ds.commercial >= ?")
            params.append(commercial_min)
        if opportunity_min:  # v3: 유망 프리셋용
            where.append("ds.opportunity >= ?")
            params.append(opportunity_min)
        if demand_min:       # v3: 유망 프리셋용
            where.append("ds.demand_idx >= ?")
            params.append(demand_min)
        if q:
            where.append("k.keyword LIKE ?")
            params.append(f"%{q}%")
        if discovered_since:
            where.append("k.first_seen >= ?")
            params.append(discovered_since)
        return (" WHERE " + " AND ".join(where)) if where else "", params

    def query_keywords(self, sort="opportunity", sort_dir="desc", category="",
                       commercial_min=0.0, q="", discovered_since="", active=1,
                       opportunity_min=0.0, demand_min=0.0, limit=50, offset=0):
        col = self.SORT_COLUMNS.get(sort, "ds.opportunity")
        order = "ASC" if sort_dir == "asc" else "DESC"  # v3: 정렬 토글 (UX §6)
        where_sql, params = self._keyword_where(
            category, commercial_min, q, discovered_since, active,
            opportunity_min, demand_min)
        sql = f"""
SELECT k.id, k.keyword, k.active, k.first_seen, ds.day,
       COALESCE(NULLIF(ds.shop_category, ''), k.category) AS category,
       ds.opportunity, ds.commercial, ds.growth, ds.demand_idx,
       ds.fresh_ratio, ds.total_sim, ds.shop_total,
       (SELECT COUNT(*) FROM daily_stats h WHERE h.keyword_id = k.id) AS days
{self._KEYWORD_BASE}{where_sql}
ORDER BY CASE WHEN {col} IS NULL THEN 1 ELSE 0 END, {col} {order}, k.id
LIMIT ? OFFSET ?"""
        return self._qd(sql, tuple(params + [limit, offset]), fetch=True)

    def count_keywords(self, category="", commercial_min=0.0, q="",
                       discovered_since="", active=1,
                       opportunity_min=0.0, demand_min=0.0):
        where_sql, params = self._keyword_where(
            category, commercial_min, q, discovered_since, active,
            opportunity_min, demand_min)
        sql = f"SELECT COUNT(*) AS c {self._KEYWORD_BASE}{where_sql}"
        return self._qd(sql, tuple(params), fetch=True)[0]["c"]

    def list_categories(self):
        # v3: shop 카테고리 + 키워드·시드 분야 통합 — 신규 키워드(스냅샷 전)도 분야 필터에 노출
        rows = self._qd(
            "SELECT DISTINCT c FROM ("
            " SELECT shop_category AS c FROM daily_stats WHERE shop_category != ''"
            " UNION SELECT category AS c FROM keywords WHERE category != ''"
            " UNION SELECT category AS c FROM seed_keywords WHERE category != ''"
            ") t",
            (), fetch=True,
        )
        return sorted(r["c"] for r in rows)

    def close(self):
        if self.conn:
            self.conn.close()
```

- [ ] **Step 4: 테스트 실행 (통과 확인)**

Run: `python -m pytest tests/test_db.py -v`
Expected: PASS (17 passed)

- [ ] **Step 5: 커밋**

```bash
git add db.py tests/test_db.py
git commit -m "feat: database layer with lifecycle, run-lock and list query"
```

---

### Task 3: 네이버 검색 API 클라이언트 (naver_client.py) — v1과 동일

**Files:**
- Create: `naver_client.py`
- Test: `tests/test_naver_client.py`

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_naver_client.py
import requests

from naver_client import NaverAPIError, NaverClient


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self.payload


def test_search_blog_passes_headers(monkeypatch):
    captured = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["headers"] = headers
        return FakeResponse({"items": [{"postdate": "20260801"}]})

    monkeypatch.setattr(requests, "get", fake_get)
    client = NaverClient("cid", "csec")
    result = client.search_blog("테스트", sort="sim", display=20)
    assert captured["headers"]["X-Naver-Client-Id"] == "cid"
    assert captured["headers"]["X-Naver-Client-Secret"] == "csec"
    assert result["items"][0]["postdate"] == "20260801"


def test_search_blog_raises_on_error(monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        return FakeResponse({"errorMessage": "SE01"}, status_code=400)

    monkeypatch.setattr(requests, "get", fake_get)
    client = NaverClient("cid", "csec")
    try:
        client.search_blog("테스트")
        assert False, "should have raised"
    except NaverAPIError as e:
        assert "SE01" in str(e)
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

Run: `python -m pytest tests/test_naver_client.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: 구현**

```python
# naver_client.py
import requests


class NaverAPIError(Exception):
    pass


BASE_URL = "https://openapi.naver.com/v1/search"


class NaverClient:
    def __init__(self, client_id, client_secret, timeout=10):
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout

    def _get(self, path, params):
        resp = requests.get(
            f"{BASE_URL}/{path}",
            params=params,
            headers={
                "X-Naver-Client-Id": self.client_id,
                "X-Naver-Client-Secret": self.client_secret,
            },
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            try:
                body = resp.json()
                msg = body.get("errorMessage", resp.text)
            except ValueError:
                msg = resp.text
            raise NaverAPIError(f"HTTP {resp.status_code}: {msg}")
        return resp.json()

    def search_blog(self, query, sort="sim", display=100, start=1):
        return self._get("blog.json", {
            "query": query, "sort": sort,
            "display": display, "start": start,
        })

    def search_shop(self, query, display=10, start=1):
        return self._get("shop.json", {
            "query": query, "display": display, "start": start,
        })
```

- [ ] **Step 4: 테스트 실행 (통과 확인)**

Run: `python -m pytest tests/test_naver_client.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 커밋**

```bash
git add naver_client.py tests/test_naver_client.py
git commit -m "feat: naver search api client"
```

---

### Task 4: 자동완성 크롤러 (autocomplete.py) — v2: 재시도·차단감지·기존키워드 경유

**Files:**
- Create: `autocomplete.py`
- Test: `tests/test_autocomplete.py`

v1 결함 수정 3건: ① 스펙의 백오프/차단중단이 미구현이었음 ② DB 기존 키워드가 일일 상한을 소진해 2일차부터 발굴이 정체됐음 ③ 응답 포맷 가정(`payload[1]`)이 미검증이었음 → 방어적 파싱 + 실측 스모크 단계 추가.

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_autocomplete.py
import time

import requests

import autocomplete
from autocomplete import (
    AutocompleteError, expand_keywords, fetch_suggestions, parse_suggestions,
)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload


URL = "https://ac.search.naver.com/nx/ac"


def test_parse_legacy_list_format():
    payload = ["시드", ["시드A", "시드B"], ["0", "1"], ["", ""]]
    assert parse_suggestions(payload) == ["시드A", "시드B"]


def test_parse_dict_items_format():
    payload = {"items": [[["에어프라이어 요리"], ["에어프라이어 추천"]]]}
    assert parse_suggestions(payload) == ["에어프라이어 요리", "에어프라이어 추천"]


def test_parse_garbage_returns_empty():
    assert parse_suggestions({}) == []
    assert parse_suggestions(["only"]) == []
    assert parse_suggestions(None) == []


def test_fetch_retries_with_backoff(monkeypatch):
    calls = {"n": 0}
    sleeps = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))

    def fake_get(url, params=None, headers=None, timeout=None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise requests.ConnectionError("boom")
        return FakeResponse(["시드", ["시드A"], ["0"], [""]])

    monkeypatch.setattr(requests, "get", fake_get)
    assert fetch_suggestions("시드", URL) == ["시드A"]
    assert calls["n"] == 3
    assert sleeps == [0.5, 1.0]


def test_expand_bfs_known_pass_through(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    graph = {
        "시드": ["시드A", "알던키워드"],
        "시드A": ["시드A상세"],
        "알던키워드": ["알던키워드 신상"],
    }
    monkeypatch.setattr(
        autocomplete, "fetch_suggestions",
        lambda q, url, timeout=10, retries=3: graph.get(q, []),
    )
    new, origins, stopped = expand_keywords(
        ["시드"], url=URL, known={"알던키워드"}, max_new=100, max_depth=2)
    assert stopped is None
    assert "시드A" in new and "시드A상세" in new
    assert "알던키워드" not in new   # 기존 키워드는 일일 상한을 소모하지 않음
    assert "알던키워드 신상" in new  # 기존 키워드를 경유해 더 깊이 발굴 (v1 정체 수정)
    assert origins["시드A"] == "시드"  # v3: 유래 키워드 추적 — 시드 분야 전파의 전제


def test_expand_respects_max_new(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setattr(
        autocomplete, "fetch_suggestions",
        lambda q, url, timeout=10, retries=3: [f"시드{i}" for i in range(10)],
    )
    new, _, _ = expand_keywords(["시드"], url=URL, max_new=3, max_depth=1)
    assert len(new) == 3


def test_expand_aborts_on_total_failure(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)

    def always_fail(q, url, timeout=10, retries=3):
        raise AutocompleteError("blocked")

    monkeypatch.setattr(autocomplete, "fetch_suggestions", always_fail)
    new, _, stopped = expand_keywords(["시드"], url=URL, max_new=10, max_depth=2)
    assert new == []
    assert stopped == "blocked"


def test_expand_stops_on_budget(monkeypatch):
    # v3: 수동 실행 잔여 예산 소진 → 'budget'으로 중단 (차단과 구분 — 스펙 §4.9)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setattr(
        autocomplete, "fetch_suggestions",
        lambda q, url, timeout=10, retries=3: [f"시드{i}" for i in range(10)],
    )
    new, origins, stopped = expand_keywords(
        ["시드"], url=URL, max_new=100, max_depth=1, budget_seconds=0)
    assert new == []
    assert origins == {}
    assert stopped == "budget"
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

Run: `python -m pytest tests/test_autocomplete.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: 구현**

```python
# autocomplete.py
import time

import requests


class AutocompleteError(Exception):
    pass


def _first_string(node):
    if isinstance(node, str):
        return node.strip()
    if isinstance(node, list):
        for child in node:
            s = _first_string(child)
            if s:
                return s
    return ""


def parse_suggestions(payload):
    """비공식 엔드포인트의 구(list)/신(dict items) 포맷을 모두 수용하는 방어적 파싱.
    형태가 다르면 빈 리스트 — 크롤 자체는 계속되고 실측 스모크에서 잡는다."""
    if isinstance(payload, dict):
        items = payload.get("items", [])
    elif isinstance(payload, list) and len(payload) > 1:
        items = payload[1]
    else:
        return []
    if not isinstance(items, list):
        return []
    # {"items": [[[...], [...]]]} 처럼 리스트 묶음이 한 겹 더 있는 형태 언랩
    if len(items) == 1 and isinstance(items[0], list) and items[0] \
            and isinstance(items[0][0], list):
        items = items[0]
    out = []
    for it in items:
        s = _first_string(it)
        if s:
            out.append(s)
    return out


def fetch_suggestions(query, url, timeout=10, retries=3):
    last_err = None
    for attempt in range(retries):
        try:
            resp = requests.get(
                url,
                params={"q": query, "q_enc": "utf-8", "st": "100"},
                headers={"Referer": "https://www.naver.com/"},
                timeout=timeout,
            )
            if resp.status_code != 200:
                raise AutocompleteError(f"HTTP {resp.status_code}")
            return parse_suggestions(resp.json())
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(0.5 * (2 ** attempt))  # 지수 백오프 0.5 → 1.0
    raise AutocompleteError(str(last_err))


def expand_keywords(seeds, url, known=frozenset(), max_new=100, max_depth=2,
                    max_requests=300, delay=0.3, max_consecutive_failures=5,
                    budget_seconds=None):
    """BFS 확장. known(DB 기존 키워드)은 신규 상한에 계수하지 않되 경유지로 사용.
    반환: (신규 키워드, origins {키워드: 유래 키워드}, 중단 사유 None|'blocked'|'budget')
    v3: budget_seconds(수동 실행 잔여 예산) — 요청 전에 검사하고 잔여 예산 기반으로
    호출 타임아웃을 축소한다. 예산 소진은 'budget', 차단은 'blocked'로 구분 (스펙 §4.9).
    origins는 시드 분야 전파(1차 키워드 → 시드 category)의 전제."""
    known = set(known) | set(seeds)
    new_found, origins = [], {}
    visited = set(seeds)
    queue = list(seeds)
    requests_made = 0
    successes = 0
    consecutive_failures = 0
    stopped = None
    started = time.monotonic() if budget_seconds is not None else None
    for _ in range(max_depth):
        if stopped or not queue:
            break
        next_queue = []
        for kw in queue:
            if len(new_found) >= max_new or requests_made >= max_requests:
                break
            if budget_seconds is not None and time.monotonic() - started >= budget_seconds:
                stopped = "budget"
                break
            requests_made += 1
            timeout = 10
            if budget_seconds is not None:
                # 잔여 예산을 3회 재시도 최악에 나눠 호출 타임아웃 축소 (전 구간 예산 적용)
                remaining = budget_seconds - (time.monotonic() - started)
                timeout = max(1.0, min(10.0, remaining / 3))
            try:
                suggestions = fetch_suggestions(kw, url, timeout=timeout)
                successes += 1
                consecutive_failures = 0
            except AutocompleteError:
                consecutive_failures += 1
                if consecutive_failures >= max_consecutive_failures:
                    stopped = "blocked"
                    break
                continue
            finally:
                time.sleep(delay)
            for sug in suggestions:
                if sug in visited:
                    continue
                visited.add(sug)
                origins[sug] = kw
                next_queue.append(sug)
                if sug not in known and len(new_found) < max_new:
                    new_found.append(sug)
        queue = next_queue
    if requests_made > 0 and successes == 0:
        stopped = "blocked"  # 전면 실패도 차단으로 간주 (성공 0회)
    return new_found, origins, stopped
```

- [ ] **Step 4: 테스트 실행 (통과 확인)**

Run: `python -m pytest tests/test_autocomplete.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: 실측 스모크 (응답 포맷 검증 — 스펙 §4.1 필수 단계)**

```powershell
.venv\Scripts\python -c "from autocomplete import fetch_suggestions; print(fetch_suggestions('에어프라이어', 'https://ac.search.naver.com/nx/ac'))"
```

Expected: 한국어 연관 키워드 리스트 출력. 빈 리스트면 `parse_suggestions`를 실제 포맷에 맞게 수정 후 테스트에 실측 포맷 케이스 추가. (여기서 검증해야 Task 13 배포 단계에서 원인불명 실패를 만나지 않음)

- [ ] **Step 6: 커밋**

```bash
git add autocomplete.py tests/test_autocomplete.py
git commit -m "feat: autocomplete crawler with retry, block detection and known pass-through"
```

---

### Task 5: 정제 필터 (refine.py) — v2: 2단 블랙리스트

**Files:**
- Create: `refine.py`
- Test: `tests/test_refine.py`

v1 결함 수정: 부분문자열 일괄 매칭이 "성인병", "전세대출" 같은 정상 키워드를 과차단했고, 대표 수익 니치인 "홍삼"이 근거 없이 차단 목록에 있었음.

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_refine.py
from refine import refine_keywords


def test_removes_duplicates_and_blank():
    kept, _ = refine_keywords(["맛집 추천", "맛집  추천", " ", ""])
    assert kept == ["맛집 추천"]


def test_substring_blacklist():
    kept, rejected = refine_keywords(["바카라사이트 후기", "성인용품 추천"])
    assert kept == []
    assert rejected == [("바카라사이트 후기", "substring"),
                        ("성인용품 추천", "substring")]


def test_token_blacklist_blocks_standalone_words():
    kept, rejected = refine_keywords(["성인 용품", "도박 후기"])
    assert kept == []
    assert all(r[1] == "token" for r in rejected)


def test_compound_words_survive():
    # v1 과차단 수정 검증
    kept, rejected = refine_keywords(
        ["성인병 예방 음식", "전세대출 금리 비교", "홍삼 선물세트"])
    assert kept == ["성인병 예방 음식", "전세대출 금리 비교", "홍삼 선물세트"]
    assert rejected == []


def test_stopwords_and_portal_tokens():
    # v3: 사유가 구분되어야 리젝 로그 주간 리뷰의 입력이 됨 (스펙 §4.2)
    kept, rejected = refine_keywords(["네이버 검색", "모르겠음", "정상 키워드"])
    assert kept == ["정상 키워드"]
    assert {r[1] for r in rejected} == {"portal", "stopword"}
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

Run: `python -m pytest tests/test_refine.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: 구현**

```python
# refine.py
# 부분문자열: 오탐 여지가 거의 없는 문자열만
BLACKLIST_SUBSTRINGS = {
    "야동", "바카라", "카지노", "슬롯", "작업대출", "마약", "수면제",
    "비아그라", "시알리스", "성인용품", "랜덤채팅", "유흥",
}

# 토큰: 단독 단어일 때만 차단 → "성인병 예방", "전세대출 금리"는 통과
BLACKLIST_TOKENS = {"성인", "도박", "대출", "불법", "사기", "토토"}

# 포털/플랫폼명이 토큰으로 포함된 브랜드 검색어 제거
PORTAL_TOKENS = {
    "네이버", "카카오", "다음", "구글", "유튜브", "인스타", "인스타그램",
    "페이스북", "트위터",
}

STOPWORDS = {"모르겠음", "없음", "뭐지", "궁금"}


def refine_keywords(words):
    """반환: (kept, rejected). rejected = [(키워드, 사유)] — 사유는 collection_log에 저장되어
    리젝 로그 주간 리뷰로 규칙을 다듬는 입력이 된다 (스펙 §4.2).
    v3: 사유를 'substring'/'token'/'portal'/'stopword'로 구분해 반환 (일괄 '필터' 기록 제거)."""
    kept, rejected, seen = [], [], set()
    for w in words:
        w = " ".join(w.split())  # 공백 정규화 (중복 병합 겸용)
        if not w or w in seen:
            continue
        seen.add(w)
        tokens = set(w.split())
        reason = None
        if any(b in w for b in BLACKLIST_SUBSTRINGS):
            reason = "substring"
        elif tokens & BLACKLIST_TOKENS:
            reason = "token"
        elif tokens & PORTAL_TOKENS:
            reason = "portal"
        elif w in STOPWORDS:
            reason = "stopword"
        if reason:
            rejected.append((w, reason))
            continue
        kept.append(w)
    return kept, rejected
```

- [ ] **Step 4: 테스트 실행 (통과 확인)**

Run: `python -m pytest tests/test_refine.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: 커밋**

```bash
git add refine.py tests/test_refine.py
git commit -m "feat: two-tier keyword refinement filter"
```

---

### Task 6: 경쟁도/상업성 분석기 (analyzer.py) — v2: 기준일 주입

**Files:**
- Create: `analyzer.py`
- Test: `tests/test_analyzer.py`

v2 변경: `date.today()` 내부 호출 금지 — 기준일(KST)을 호출 측이 주입. 테스트도 기준일 고정으로 시한폭탄 제거 (v1은 "20260801" 하드코딩이라 2026-08-08 이후 실행 시 깨졌음).

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_analyzer.py
from datetime import date

from analyzer import analyze_keyword, compute_fresh_ratio

TODAY = date(2026, 8, 3)


def test_compute_fresh_ratio():
    post_dates = ["20260801"] * 8 + ["20200101"] * 12
    assert compute_fresh_ratio(post_dates, TODAY) == 0.4


def test_compute_fresh_ratio_all_old():
    assert compute_fresh_ratio(["20200101"] * 20, TODAY) == 0.0


def test_analyze_keyword_combines_sources():
    blog_sim = {"total": 1000, "items": [
        {"postdate": "20260801", "bloggername": "a"} for _ in range(20)]}
    blog_date = {"total": 1200, "items": []}
    shop = {"total": 530, "items": [
        {"lprice": "30000", "category1": "가전/디지털", "category2": "주방가전"}]}
    calls = {"n": 0}

    class FakeClient:
        def search_blog(self, query, sort="sim", display=100, start=1):
            calls["n"] += 1
            return blog_sim if sort == "sim" else blog_date

        def search_shop(self, query, display=10, start=1):
            calls["n"] += 1
            return shop

    result = analyze_keyword(FakeClient(), "에어프라이어", TODAY)
    assert result["total_sim"] == 1000
    assert result["total_date"] == 1200
    assert result["fresh_ratio"] == 1.0  # 20260801은 기준일 8/3의 7일 내
    assert result["shop_total"] == 530
    assert result["shop_avg_price"] == 30000
    assert result["shop_category"] == "가전/디지털/주방가전"
    assert result["shop_error"] is None
    assert calls["n"] == 3


def test_analyze_keyword_shop_failure_partial():
    class FailShopClient:
        def search_blog(self, query, sort="sim", display=100, start=1):
            return {"total": 100, "items": [{"postdate": "20260101"}]}

        def search_shop(self, query, display=10, start=1):
            raise Exception("shop down")

    result = analyze_keyword(FailShopClient(), "키워드", TODAY)
    assert result["total_sim"] == 100
    assert result["shop_total"] == 0
    assert result["shop_avg_price"] == 0
    assert result["shop_error"] is not None
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

Run: `python -m pytest tests/test_analyzer.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: 구현**

```python
# analyzer.py
from datetime import date, timedelta


def compute_fresh_ratio(post_dates, today, window_days=7):
    # today는 호출 측이 KST 기준일을 명시적으로 전달 (러너 UTC 오염 방지 — 스펙 §3)
    if not post_dates:
        return 0.0
    cutoff = today - timedelta(days=window_days)
    fresh = 0
    for pd in post_dates:
        try:
            d = date(int(pd[:4]), int(pd[4:6]), int(pd[6:8]))
        except (ValueError, IndexError):
            continue
        if d >= cutoff:
            fresh += 1
    return fresh / len(post_dates)


def analyze_keyword(client, keyword, today):
    blog_sim = client.search_blog(keyword, sort="sim", display=20)
    blog_date = client.search_blog(keyword, sort="date", display=100)

    shop = None
    shop_error = None
    try:
        shop = client.search_shop(keyword, display=10)
    except Exception as e:
        shop_error = str(e)

    post_dates = [item.get("postdate", "") for item in blog_sim.get("items", [])]
    shop_items = shop.get("items", []) if shop else []
    prices = [int(i.get("lprice", 0)) for i in shop_items if i.get("lprice")]
    category = ""
    if shop_items:
        category = shop_items[0].get("category1", "")
        if shop_items[0].get("category2"):
            category = f"{category}/{shop_items[0].get('category2')}"

    return {
        "total_sim": int(blog_sim.get("total", 0)),
        "total_date": int(blog_date.get("total", 0)),
        "fresh_ratio": compute_fresh_ratio(post_dates, today),
        "top_post_dates": post_dates,
        "shop_total": int(shop.get("total", 0)) if shop else 0,
        "shop_avg_price": int(sum(prices) / len(prices)) if prices else 0,
        "shop_category": category,
        "shop_error": shop_error,
    }
```

- [ ] **Step 4: 테스트 실행 (통과 확인)**

Run: `python -m pytest tests/test_analyzer.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 커밋**

```bash
git add analyzer.py tests/test_analyzer.py
git commit -m "feat: keyword snapshot analyzer with injected base date"
```

---

### Task 7: 점수 엔진 (scoring.py) — v2 공식 개정

**Files:**
- Create: `scoring.py`
- Test: `tests/test_scoring.py`

v2 변경: ① 경쟁도 포화를 스펙대로 **1만 글**로 정합화(v1 계획은 10만) ② 성장 정규화를 [-100%,+100%]에서 **0~5%**로 교체(일일 증감률 현실 분포 기준 — v1은 30점 항이 사실상 상수였음) ③ v1 계획의 잘못된 테스트 기대값 2건(88→100 오기, 2.5→10 오기) 검산 교정.

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_scoring.py
from scoring import commercial_score, competition, growth_rate, opportunity_score


def test_growth_rate():
    assert growth_rate(100, 105) == 0.05
    assert growth_rate(100, 50) == -0.5
    assert growth_rate(100, 100) == 0.0
    assert growth_rate(0, 100) == 1.0
    assert growth_rate(100, 0) == -1.0


def test_competition_saturates_at_10k():
    # 스펙 §4.5: 1만 글에서 경쟁 포화 (v1 계획의 10만 포화는 스펙 불일치였음)
    assert competition(1) == 0.0
    assert competition(100) == 0.5
    assert competition(10_000) == 1.0
    assert competition(1_000_000) == 1.0


def test_opportunity_bounds():
    # 기대값은 공식 검산 결과 (v1 계획은 검산 없이 100을 기대해 실제 88과 불일치)
    assert opportunity_score(1.0, 0.05, 1) == 100.0
    assert opportunity_score(0.0, 0.0, 10_000) == 0.0
    assert opportunity_score(0.0, -1.0, 10_000) == 0.0  # 음수 성장은 0으로 클램프


def test_opportunity_mid():
    # 40×0.5 + 30×(0.01/0.05) + 30×(1−log10(1000)/4) = 20 + 6 + 7.5
    assert opportunity_score(0.5, 0.01, 1000) == 33.5


def test_commercial_score():
    assert commercial_score(0, 0) == 0.0
    assert commercial_score(500, 30000) == 100.0
    assert commercial_score(250, 15000) == 50.0
    # 60×(10/500) + 40×(1000/30000) = 1.2 + 1.33… → 2.5 (v1 계획의 기대값 10은 오류)
    assert commercial_score(10, 1000) == 2.5
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

Run: `python -m pytest tests/test_scoring.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: 구현**

```python
# scoring.py
import math

COMPETITION_SATURATION_TOTAL = 10_000  # 1만 글이면 경쟁 포화 (스펙 §4.5)
GROWTH_NORM_MAX = 0.05                 # 일 5% 증가에서 성장 만점 (변별력 확보)


def growth_rate(prev_total, curr_total):
    if prev_total == 0:
        return 1.0 if curr_total > 0 else 0.0
    return (curr_total - prev_total) / prev_total


def competition(total):
    if total <= 0:
        return 0.0
    return min(1.0, math.log10(total) / math.log10(COMPETITION_SATURATION_TOTAL))


def opportunity_score(fresh_ratio, growth, total):
    growth_norm = max(0.0, min(1.0, growth / GROWTH_NORM_MAX))
    return round(
        40.0 * fresh_ratio
        + 30.0 * growth_norm
        + 30.0 * (1.0 - competition(total)),
        1,
    )


def commercial_score(shop_total, avg_price):
    if shop_total <= 0:
        return 0.0
    return round(
        60.0 * min(shop_total / 500.0, 1.0)
        + 40.0 * min(avg_price / 30000.0, 1.0),
        1,
    )
```

- [ ] **Step 4: 테스트 실행 (통과 확인)**

Run: `python -m pytest tests/test_scoring.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: 커밋**

```bash
git add scoring.py tests/test_scoring.py
git commit -m "feat: scoring engine with verified formulas"
```

---

### Task 8: 데이터랩 수요 확증 (datalab.py) — v2 신설

**Files:**
- Create: `datalab.py`
- Test: `tests/test_datalab.py`

목적: "저경쟁 = 저수요" 함정 차단 (스펙 §4.4). 요청당 앵커 1 + 후보 4 그룹, 후보 평균 ratio ÷ 앵커 평균 ratio = 수요지수.
v3 변경: 네트워크·타임아웃·JSON 파싱 오류를 DatalabError로 정규화 — 원시 예외가 전파되면 스냅샷 성공 후 전체 실행이 failed로 처리되는 연쇄 장애를 막는다 (스펙 §6).

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_datalab.py
import requests

from datalab import DatalabError, fetch_demand_ratios


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self.payload


def test_demand_index_normalized_by_anchor(monkeypatch):
    payload = {"results": [
        {"title": "냉장고", "data": [{"ratio": 50.0}, {"ratio": 50.0}]},
        {"title": "에어프라이어", "data": [{"ratio": 5.0}, {"ratio": 5.0}]},
        {"title": "무명키워드", "data": []},
    ]}
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(payload))
    r = fetch_demand_ratios("cid", "csec", ["에어프라이어", "무명키워드"],
                            "냉장고", "2026-07-04", "2026-08-03")
    assert r == {"에어프라이어": 0.1, "무명키워드": 0.0}


def test_anchor_zero_raises(monkeypatch):
    payload = {"results": [{"title": "냉장고", "data": []}]}
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(payload))
    try:
        fetch_demand_ratios("cid", "csec", ["키워드"], "냉장고",
                            "2026-07-04", "2026-08-03")
        assert False, "should have raised"
    except DatalabError:
        pass


def test_http_error_raises(monkeypatch):
    monkeypatch.setattr(requests, "post",
                        lambda *a, **k: FakeResponse({}, status_code=429))
    try:
        fetch_demand_ratios("cid", "csec", ["키워드"], "냉장고",
                            "2026-07-04", "2026-08-03")
        assert False, "should have raised"
    except DatalabError as e:
        assert "429" in str(e)


def test_connection_error_becomes_datalab_error(monkeypatch):
    # v3: 네트워크 오류도 DatalabError로 정규화 — 안 하면 update_demand의
    # except DatalabError가 못 잡아 전체 실행이 failed로 처리됨 (스펙 §4.4)
    def boom(*a, **k):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(requests, "post", boom)
    try:
        fetch_demand_ratios("cid", "csec", ["키워드"], "냉장고",
                            "2026-07-04", "2026-08-03")
        assert False, "should have raised"
    except DatalabError:
        pass


def test_bad_json_becomes_datalab_error(monkeypatch):
    class BadJson:
        status_code = 200
        text = "not json"

        def json(self):
            raise ValueError("broken")

    monkeypatch.setattr(requests, "post", lambda *a, **k: BadJson())
    try:
        fetch_demand_ratios("cid", "csec", ["키워드"], "냉장고",
                            "2026-07-04", "2026-08-03")
        assert False, "should have raised"
    except DatalabError:
        pass
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

Run: `python -m pytest tests/test_datalab.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: 구현**

```python
# datalab.py
import requests

DATALAB_URL = "https://openapi.naver.com/v1/datalab/search"


class DatalabError(Exception):
    pass


def fetch_demand_ratios(client_id, client_secret, keywords, anchor,
                        start_date, end_date, timeout=10):
    """앵커 + 후보(최대 4개)를 한 요청으로 비교.
    반환: {keyword: 수요지수(앵커 평균 ratio 대비)}.
    데이터랩 ratio는 요청 내 상대값이므로 앵커로 나눠야 요청 간 비교 가능.
    v3: 네트워크 오류·타임아웃·잘못된 JSON도 전부 DatalabError로 변환 —
    update_demand가 잡을 수 있는 예외 종류를 하나로 정규화 (graceful degradation, 스펙 §4.4)."""
    groups = [{"groupName": anchor, "keywords": [anchor]}] + [
        {"groupName": kw, "keywords": [kw]} for kw in keywords[:4]
    ]
    try:
        resp = requests.post(
            DATALAB_URL,
            json={
                "startDate": start_date, "endDate": end_date,
                "timeUnit": "date", "keywordGroups": groups,
            },
            headers={
                "X-Naver-Client-Id": client_id,
                "X-Naver-Client-Secret": client_secret,
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )
        if resp.status_code != 200:
            raise DatalabError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
    except DatalabError:
        raise
    except Exception as e:
        raise DatalabError(f"datalab 요청 실패: {e}") from e
    means = {}
    for group in data.get("results", []):
        vals = [p.get("ratio", 0.0) for p in group.get("data", [])]
        means[group.get("title", "")] = (sum(vals) / len(vals)) if vals else 0.0
    anchor_mean = means.get(anchor, 0.0)
    if anchor_mean <= 0:
        raise DatalabError(f"앵커 '{anchor}' ratio가 0 — 앵커 교체 필요")
    return {kw: round(means.get(kw, 0.0) / anchor_mean, 4) for kw in keywords[:4]}
```

- [ ] **Step 4: 테스트 실행 (통과 확인)**

Run: `python -m pytest tests/test_datalab.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: 커밋**

```bash
git add datalab.py tests/test_datalab.py
git commit -m "feat: datalab demand verification with anchor normalization"
```

---

### Task 9: 수집 실행 (collect.py) — v2: DB 잠금·시간 예산·수명주기

**Files:**
- Create: `collect.py`
- Test: `tests/test_collect.py`

v2 변경: ① 날짜/시각 전부 KST(v1은 러너 UTC로 하루 어긋남) ② `.lock` 파일 → `collection_runs` DB 잠금(환경 공통) ③ 같은 날짜 재수집 스킵(멱등) ④ 수동 트리거 = 시간 예산 부분 수집(발굴은 첫 실행 예외만) ⑤ 발굴 시 DB 기존 키워드를 상한에서 제외 ⑥ 점수 사전계산 저장 ⑦ 스케줄 실행 말미에 수요 확증·자동 은퇴·보존 정리 ⑧ 전량 실패 시 exit 1 → GitHub 실패 메일.

v3 변경: ① 예산을 발굴·개별 호출 타임아웃까지 전 구간 적용(discover에도 budget 전달, 호출 타임아웃 축소) ② 발굴 중단 사유를 blocked/budget으로 구분 기록 + blocked면 exit 1(스냅샷 성공과 무관) ③ 발굴 키워드에 시드 분야 전파(1차 파생 키워드) ④ 필터 거부 사유를 collection_log에 기록 ⑤ 증감률·기회점수는 전일(day-1) 스냅샷 대비만 — 공백이면 NULL ⑥ finish_run 상태를 done/partial/failed로 구분(부분 실패·예산 종료·중단이 done으로 기록되는 것 방지) ⑦ 잠금 stale 60분(cfg) ⑧ 수요 확증 오류는 전부 DatalabError로 정규화돼 graceful.

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_collect.py
import pytest

import collect
import config as config_mod
import db
from collect import run_collection


class FakeClient:
    def search_blog(self, query, sort="sim", display=100, start=1):
        return {"total": 100, "items": [{"postdate": "20260101"}]}

    def search_shop(self, query, display=10, start=1):
        return {"total": 10, "items": []}


def make_cfg(tmp_path):
    return {
        "db_url": f"sqlite:///{tmp_path / 't.db'}",
        "client_id": "cid", "client_secret": "csec",
        "daily_new_keyword_cap": 100, "active_keyword_cap": 1000,
        "autocomplete_url": "http://ac.test", "autocomplete_max_depth": 1,
        "autocomplete_max_requests": 10, "manual_budget_seconds": 45,
        "dashboard_token": "", "datalab_enabled": False, "datalab_anchor": "냉장고",
        "env": "development", "run_lock_stale_minutes": 60,  # v3
    }


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
    assert hist[1]["commercial"] == 1.2    # 60×(10/500) + 40×0
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


def test_locked_when_run_in_progress(tmp_path):
    cfg = make_cfg(tmp_path)
    d = db.Database(cfg["db_url"])
    d.init()
    assert d.start_run("schedule", config_mod.now_kst_iso(),
                       config_mod.minutes_ago_kst_iso(30)) is not None
    result = run_collection(cfg, client=FakeClient(), today="2026-08-01")
    assert result["locked"] is True
    d.close()


def test_schedule_run_retires_and_cleans(tmp_path):
    cfg = make_cfg(tmp_path)
    d = db.Database(cfg["db_url"])
    d.init()
    bad = d.upsert_keyword("낡고나쁨", day="2026-07-01")
    d.insert_daily_stats(bad, "2026-08-01", {
        "total_date": 100, "opportunity": 10.0, "commercial": 5.0})
    d.insert_daily_stats(bad, "2026-01-15", {"total_sim": 1})  # 90일 보존 초과분
    d.insert_top_results(bad, "2026-01-15", ["20260101"])      # 30일 보존 초과분
    result = run_collection(cfg, client=FakeClient(), today="2026-08-02")
    assert result["snapshotted"] == 1
    assert result["retired"] == 1  # 8/2 스냅샷도 기회 15 < 35, 상업성 1.2 < 30 → 은퇴
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
    # v3: 차단은 스냅샷 성공과 무관하게 exit 1 — 조용히 성공 처리 금지 (스펙 §5)
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
                                         "retired": 0, "demand_updated": 0})
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
    d.close()
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

Run: `python -m pytest tests/test_collect.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: 구현**

```python
# collect.py
import sys
import time
from datetime import date, timedelta

import config as config_mod
import db
from analyzer import analyze_keyword
from autocomplete import expand_keywords
from datalab import DatalabError, fetch_demand_ratios
from naver_client import NaverAPIError, NaverClient
from refine import refine_keywords
from scoring import commercial_score, growth_rate, opportunity_score

RUN_LOCK_STALE_MINUTES = 60  # v3: GH Actions timeout-minutes(60)와 정합 (기본값, cfg로 조정)
MANUAL_DISCOVERY_MAX_NEW = 30       # 첫 실행(활성 0개)의 수동 발굴 축소 상한
MANUAL_DISCOVERY_MAX_REQUESTS = 40
RETIRE_MIN_AGE_DAYS = 14
RETIRE_WINDOW_DAYS = 7
RETIRE_OPPORTUNITY_LT = 35.0
RETIRE_COMMERCIAL_LT = 30.0
STATS_RETENTION_DAYS = 90
TOP_RESULTS_RETENTION_DAYS = 30
LOG_RETENTION_DAYS = 180
DATALAB_TOP_N = 200
DATALAB_WINDOW_DAYS = 30


def compute_scores(d, keyword_id, day, stats):
    """점수 사전계산 (조회 시 재계산 금지 — 스펙 §4.5).
    v3: 증감률·기회점수는 전일(day-1) 스냅샷 대비만 산출 — 공백(2일 이상)이면
    NULL ("데이터 쌓는 중"). 최근 과거 스냅샷으로 며칠치 증가율을 하루치로 계산하지 않음."""
    prev = d.get_prev_stats(keyword_id, day)
    growth = opportunity = None
    prev_day = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
    if prev and prev["day"] == prev_day:
        growth = growth_rate(prev["total_date"], stats["total_date"])
        opportunity = opportunity_score(
            stats["fresh_ratio"], growth, stats["total_sim"])
    commercial = None if stats.get("shop_error") else commercial_score(
        stats["shop_total"], stats["shop_avg_price"])
    return growth, opportunity, commercial


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def discover(d, cfg, today, now, trigger, result, budget_seconds=None):
    seeds = d.list_seeds()
    if not seeds:
        return
    if trigger == "manual" and d.count_active() > 0:
        return  # 수동 수집은 스냅샷 갱신 전용 — 발굴은 스케줄러 몫 (첫 실행만 예외)
    max_new = cfg["daily_new_keyword_cap"]
    max_requests = cfg["autocomplete_max_requests"]
    if trigger == "manual":
        max_new = min(max_new, MANUAL_DISCOVERY_MAX_NEW)
        max_requests = min(max_requests, MANUAL_DISCOVERY_MAX_REQUESTS)
    cap_room = cfg["active_keyword_cap"] - d.count_active()
    remaining = min(max_new - d.count_new_keywords_today(today), cap_room)
    if remaining <= 0:
        d.log_collection("(seed)", "skip", "일일/총량 상한 도달", now)
        return
    try:
        # v3: 예산을 발굴에도 적용(잔여 예산 기반 타임아웃·중단), 유래 키워드(origins) 추적
        found, origins, stopped = expand_keywords(
            [s["keyword"] for s in seeds], url=cfg["autocomplete_url"],
            known=d.all_keyword_names(), max_new=remaining,
            max_depth=cfg["autocomplete_max_depth"], max_requests=max_requests,
            budget_seconds=budget_seconds)
    except Exception as e:
        d.log_collection("(seed)", "error", f"autocomplete: {e}", now)
        result["crawl_stopped"] = "blocked"
        return
    result["crawl_stopped"] = stopped
    if stopped == "blocked":
        d.log_collection("(seed)", "blocked", "자동완성 연속 실패로 중단", now)
    elif stopped == "budget":
        d.log_collection("(seed)", "blocked", "시간 예산 초과로 발굴 중단", now)
    # v3: 시드에서 직접 파생된 1차 키워드는 시드 분야 상속 (2차 이상은 shop 데이터로 채움)
    seed_cat = {s["keyword"]: s["category"] for s in seeds}
    kept, rejected = refine_keywords(found)
    for kw, reason in rejected:
        d.log_collection(kw, "reject", reason, now)  # v3: 사유 기록 (substring/token/...)
    for kw in kept[:remaining]:
        cat = seed_cat.get(origins.get(kw, ""), "")
        d.upsert_keyword(kw, category=cat, day=today)
        d.log_collection(kw, "new", "발굴", now)
    result["new_keywords"] = len(kept[:remaining])


def snapshot(d, cfg, client, today, now, started, budget_seconds, result):
    base_date = date.fromisoformat(today)
    for kw in d.list_active_keywords_stale_first():
        if budget_seconds is not None and time.monotonic() - started >= budget_seconds:
            result["partial"] = True
            break
        if kw["last_day"] == today:
            continue  # 같은 날짜 재수집 스킵 (멱등)
        if budget_seconds is not None:
            # v3: 키워드당 최악 3회 호출(blog 2 + shop 1)이 잔여 예산을 넘지 않도록
            # 호출 타임아웃 축소 — 루프 사이 체크만으로는 30초 오버슛이 가능했음 (스펙 §4.9)
            remaining = budget_seconds - (time.monotonic() - started)
            client.timeout = max(
                1.0, min(getattr(client, "timeout", 10.0) or 10.0, remaining / 3))
        try:
            stats = analyze_keyword(client, kw["keyword"], base_date)
            growth, opportunity, commercial = compute_scores(
                d, kw["id"], today, stats)
            stats.update({"growth": growth, "opportunity": opportunity,
                          "commercial": commercial})
            if stats.get("shop_error"):
                d.log_collection(kw["keyword"], "partial",
                                 f"shop: {stats['shop_error']}", now)
            d.insert_daily_stats(kw["id"], today, stats)
            d.insert_top_results(kw["id"], today, stats["top_post_dates"])
            result["snapshotted"] += 1
        except NaverAPIError as e:
            d.log_collection(kw["keyword"], "error", str(e), now)
            result["errors"].append(str(e))
        except Exception as e:
            d.log_collection(kw["keyword"], "error", f"unknown: {e}", now)
            result["errors"].append(str(e))
        time.sleep(0.3)


def update_demand(d, cfg, today, now):
    if not cfg.get("datalab_enabled", True):
        return 0
    start = (date.fromisoformat(today)
             - timedelta(days=DATALAB_WINDOW_DAYS)).isoformat()
    updated = 0
    for batch in _chunks(d.top_by_opportunity(today, DATALAB_TOP_N), 4):
        try:
            ratios = fetch_demand_ratios(
                cfg["client_id"], cfg["client_secret"],
                [b["keyword"] for b in batch], cfg["datalab_anchor"], start, today)
        except DatalabError as e:
            d.log_collection("(datalab)", "error", str(e), now)
            break  # 수요 단계만 중단 — 나머지 파이프라인은 정상 (스펙 §4.4)
        for b in batch:
            if b["keyword"] in ratios:
                d.update_demand_idx(b["id"], today, ratios[b["keyword"]])
                updated += 1
        time.sleep(0.2)
    return updated


def retire(d, today, now):
    base = date.fromisoformat(today)
    victims = d.find_retire_candidates(
        (base - timedelta(days=RETIRE_MIN_AGE_DAYS)).isoformat(),
        (base - timedelta(days=RETIRE_WINDOW_DAYS)).isoformat(),
        RETIRE_OPPORTUNITY_LT, RETIRE_COMMERCIAL_LT)
    for v in victims:
        d.set_active(v["id"], 0)
        d.log_collection(v["keyword"], "retire", "저성과 자동 비활성", now)
    return len(victims)


def run_collection(cfg, client=None, today=None, trigger="schedule",
                   budget_seconds=None):
    started = time.monotonic()
    today = today or config_mod.today_kst().isoformat()  # 날짜 키는 KST 고정
    now = config_mod.now_kst_iso()
    d = db.Database(cfg["db_url"])
    d.init()
    stale_minutes = cfg.get("run_lock_stale_minutes", RUN_LOCK_STALE_MINUTES)
    run_id = d.start_run(
        trigger, now, config_mod.minutes_ago_kst_iso(stale_minutes))
    if run_id is None:
        d.close()
        return {"locked": True, "new_keywords": 0, "snapshotted": 0,
                "errors": [], "partial": False, "crawl_stopped": None}
    result = {"locked": False, "new_keywords": 0, "snapshotted": 0, "errors": [],
              "partial": False, "crawl_stopped": None, "retired": 0,
              "demand_updated": 0}
    try:
        # v3: 예산은 발굴·스냅샷·개별 호출 타임아웃까지 전 구간 적용
        discover(d, cfg, today, now, trigger, result, budget_seconds)
        client = client or NaverClient(cfg["client_id"], cfg["client_secret"])
        snapshot(d, cfg, client, today, now, started, budget_seconds, result)
        if trigger == "schedule":
            base = date.fromisoformat(today)
            result["demand_updated"] = update_demand(d, cfg, today, now)
            result["retired"] = retire(d, today, now)
            d.cleanup(
                (base - timedelta(days=STATS_RETENTION_DAYS)).isoformat(),
                (base - timedelta(days=TOP_RESULTS_RETENTION_DAYS)).isoformat(),
                (base - timedelta(days=LOG_RETENTION_DAYS)).isoformat(),
            )
        # v3: 상태 구분 — done(전량 성공) / partial(예산 종료·일부 오류·발굴 중단) / failed(전량 실패)
        if result["errors"] and result["snapshotted"] == 0:
            status = "failed"
        elif result["partial"] or result["errors"] or result["crawl_stopped"]:
            status = "partial"
        else:
            status = "done"
        d.finish_run(run_id, status, config_mod.now_kst_iso(), result)
    except Exception:
        d.finish_run(run_id, "failed", config_mod.now_kst_iso(), result)
        raise
    finally:
        d.close()
    return result


def main():
    cfg = config_mod.load_config()
    result = run_collection(cfg, trigger="schedule")
    if result.get("locked"):
        print("이미 수집이 실행 중입니다 — 종료")
        return 0
    print(f"완료: 신규 {result['new_keywords']}개, 스냅샷 {result['snapshotted']}개, "
          f"수요갱신 {result['demand_updated']}개, 은퇴 {result['retired']}개, "
          f"오류 {len(result['errors'])}개"
          + (f" — 발굴 중단({result.get('crawl_stopped')})"
             if result.get("crawl_stopped") else ""))
    # v3: 자동완성 차단은 스냅샷 성공 여부와 무관하게 exit 1 — 차단을 조기에 인지해야
    # 대체 스케줄러(cron-job.org)로 전환할 수 있음 (스펙 §5)
    if result.get("crawl_stopped") == "blocked":
        return 1
    # 전량 실패 시 exit 1 → GitHub Actions 실패 메일로 조기 인지 (스펙 §5)
    if result["errors"] and result["snapshotted"] == 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 테스트 실행 (통과 확인)**

Run: `python -m pytest tests/test_collect.py -v`
Expected: PASS (10 passed)

- [ ] **Step 5: 수동 smoke (API 키 없이 — DB 생성과 정상 종료만 확인)**

Run: `python collect.py`
Expected: `완료: 신규 0개, 스냅샷 0개, ...` (시드·키워드 없음 → 아무것도 안 하고 정상 종료, data/keywords.db 생성됨)

- [ ] **Step 6: 커밋**

```bash
git add collect.py tests/test_collect.py
git commit -m "feat: collection runner with db lock, budget and lifecycle"
```

---

### Task 10: FastAPI 서버 (server.py) — v2: 인증·페이징·사전계산 조회·재연결

**Files:**
- Create: `server.py`
- Test: `tests/test_api.py`

v2 변경: ① 목록은 사전계산 점수를 단일 쿼리로 조회 (v1의 키워드당 3쿼리 N+1은 수백 개부터 대시보드 마비) ② 페이징(스펙 §4.8 — v1 미구현) ③ 쓰기 엔드포인트 Bearer 토큰 ④ `PATCH /keywords/{id}` 키워드 제외 ⑤ 수동 수집은 `trigger="manual"` + 시간 예산 ⑥ 커넥션 오류 1회 재연결 ⑦ 상세 404 처리. SQLite `check_same_thread=False`(Task 2)가 전제 — FastAPI 동기 엔드포인트는 스레드풀에서 실행되므로 없으면 즉시 오류.

v3 변경: ① **프로덕션 fail-closed** — `ENV=production`에서 `DASHBOARD_TOKEN` 미설정이면 `create_app`이 기동 거부(무인증 쓰기 API 방지, 스펙 §7) ② `/collect`에 **body `{"trigger":"schedule"}`** 추가 — cron-job.org 대체 스케줄러가 전체 파이프라인(발굴·수요·은퇴·보존)을 실행 (v2는 manual-only라 발굴/수요/은퇴/보존이 누락됐음) ③ `GET /keywords`에 **정렬 방향(`sort_dir=desc|asc`)·유망 프리셋(`preset=promising`)** 추가 (UX 스펙 §6·§8 계약) ④ `/status`의 마지막 성공 수집은 `status='done'`만 집계(partial 제외) ⑤ `/categories`가 shop+키워드+시드 분야 통합 반환.

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_api.py
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
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

Run: `python -m pytest tests/test_api.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: 구현**

```python
# server.py
import os
from datetime import timedelta

import config as config_mod
import db
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel


class SeedIn(BaseModel):
    keyword: str
    category: str = ""


class KeywordPatch(BaseModel):
    active: bool


class CollectIn(BaseModel):
    trigger: str = "manual"  # "schedule" = cron-job.org 대체 스케줄러 (전 구간, v3)


def create_app(cfg):
    env = cfg.get("env", "development")
    # v3: fail-closed — 프로덕션에서 토큰 미설정 시 기동 거부 (스펙 §7).
    # v2는 토큰이 비면 인증을 생략해 설정 실수가 무인증 쓰기 API로 이어졌음.
    # 로컬 개발(ENV 미설정/development)만 인증 생략 허용
    if env == "production" and not cfg.get("dashboard_token", ""):
        raise RuntimeError("DASHBOARD_TOKEN required in production (fail-closed)")
    app = FastAPI()
    state = {"db": None}

    def get_db():
        if state["db"] is None:
            state["db"] = db.Database(cfg["db_url"])
            state["db"].init()
        return state["db"]

    def run_db(fn):
        # 서버리스에서 유휴 종료된 커넥션 대비: 연결 오류 1회 재연결 후 재시도 (스펙 §3)
        try:
            return fn(get_db())
        except db.CONNECTION_ERRORS:
            state["db"] = None
            return fn(get_db())

    def require_token(authorization: str = Header(default="")):
        token = cfg.get("dashboard_token", "")
        if token and authorization != f"Bearer {token}":
            raise HTTPException(status_code=401, detail="invalid token")

    @app.get("/keywords")
    def list_keywords(sort: str = "opportunity", sort_dir: str = "desc",
                      category: str = "", commercial_min: float = 0,
                      q: str = "", discovered_within: int = 0,
                      preset: str = "", show_inactive: int = 0,
                      page: int = 1, page_size: int = 50):
        page = max(page, 1)
        page_size = min(max(page_size, 1), 200)
        discovered_since = ""
        if discovered_within > 0:
            discovered_since = (
                config_mod.today_kst() - timedelta(days=discovered_within)
            ).isoformat()
        # v3: 유망 프리셋 — UX §8 "유망" 버튼 (기회≥70 & 상업성≥60 & 수요지수≥0.01)
        opportunity_min, demand_min = 0.0, 0.0
        if preset == "promising":
            opportunity_min, commercial_min, demand_min = 70.0, 60.0, 0.01
        filters = dict(category=category, commercial_min=commercial_min, q=q,
                       discovered_since=discovered_since,
                       active=None if show_inactive else 1,
                       opportunity_min=opportunity_min, demand_min=demand_min)
        items = run_db(lambda d: d.query_keywords(
            sort=sort, sort_dir=sort_dir, limit=page_size,
            offset=(page - 1) * page_size, **filters))
        total = run_db(lambda d: d.count_keywords(**filters))
        return {"items": items, "count": total, "page": page, "page_size": page_size}

    @app.get("/keywords/{keyword_id}")
    def keyword_detail(keyword_id: int):
        kw = run_db(lambda d: d.get_keyword(keyword_id))
        if not kw:
            raise HTTPException(status_code=404, detail="not found")
        history = run_db(lambda d: d.get_history(keyword_id))
        return {"keyword": kw["keyword"], "active": kw["active"], "history": history}

    @app.patch("/keywords/{keyword_id}", dependencies=[Depends(require_token)])
    def patch_keyword(keyword_id: int, body: KeywordPatch):
        kw = run_db(lambda d: d.get_keyword(keyword_id))
        if not kw:
            raise HTTPException(status_code=404, detail="not found")
        run_db(lambda d: d.set_active(keyword_id, 1 if body.active else 0))
        return {"ok": True}

    @app.get("/seeds")
    def list_seeds():
        return run_db(lambda d: d.list_seeds())

    @app.post("/seeds", dependencies=[Depends(require_token)])
    def add_seed(seed: SeedIn):
        run_db(lambda d: d.add_seed(seed.keyword, seed.category))
        return {"ok": True}

    @app.delete("/seeds/{seed_id}", dependencies=[Depends(require_token)])
    def delete_seed(seed_id: int):
        run_db(lambda d: d.delete_seed(seed_id))
        return {"ok": True}

    @app.post("/collect", dependencies=[Depends(require_token)])
    def trigger_collect(body: CollectIn):
        import collect
        if body.trigger == "schedule":
            # v3: cron-job.org 대체 경로 — 전체 파이프라인(발굴·수요·은퇴·보존).
            # Vercel 60초 한도 내라 예산(45초)을 걸어 전 구간 예산 적용 + 잔여는 다음 실행이 순환
            return collect.run_collection(
                cfg, trigger="schedule",
                budget_seconds=cfg.get("manual_budget_seconds", 45))
        return collect.run_collection(
            cfg, trigger="manual",
            budget_seconds=cfg.get("manual_budget_seconds", 45))

    @app.get("/status")
    def status():
        runs = run_db(lambda d: d.get_last_runs(5))
        # v3: partial/failed는 성공 수집으로 집계하지 않음 (UX §5.2 경고 기준)
        last_success = next((r for r in runs if r["status"] == "done"), None)
        return {
            "keyword_count": run_db(lambda d: d.count_active()),
            "seed_count": len(run_db(lambda d: d.list_seeds())),
            "today": config_mod.today_kst().isoformat(),
            "last_run": runs[0] if runs else None,
            "last_success": last_success,
        }

    @app.get("/categories")
    def categories():
        return run_db(lambda d: d.list_categories())

    @app.get("/")
    def index():
        return FileResponse(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "static", "index.html"))

    return app


app = create_app(config_mod.load_config())
```

- [ ] **Step 4: 테스트 실행 (통과 확인)**

Run: `python -m pytest tests/test_api.py -v`
Expected: PASS (12 passed)

- [ ] **Step 5: 커밋**

```bash
git add server.py tests/test_api.py
git commit -m "feat: fastapi server with auth, paging and precomputed scores"
```

---

### Task 11: 대시보드 (static/index.html) — v2: 이스케이프·토큰·수요·페이징·제외 + UX 스펙

**Files:**
- Create: `static/index.html`

v2 변경: ① 외부 유래 문자열 전부 `esc()` 처리 (v1의 innerHTML 직접 삽입은 XSS) ② 토큰 입력(localStorage) ③ 수요지수 컬럼·정렬 ④ 페이징 UI ⑤ 키워드 제외 버튼 ⑥ 검색 디바운스 + 서버 필터 ⑦ 수집 응답의 partial/locked/401/타임아웃 처리 ⑧ 마지막 성공 수집 경과 경고 ⑨ **UX 스펙(§3~§7) 반영: sticky header·게이지·증감 화살표·제외 행 흐림·빈 상태 CTA·스켈레톤·정렬 토글·Esc 닫기·접근성**

v3 변경 (구현 누락 항목 전면 보완 — v2의 Step 2 체크리스트는 코드에 없는 항목을 "확인"으로 나열했었음): ① **기회점수 게이지 막대** ② **정렬 토글**(1회 내림차순 → 2회 오름차순, ↑/↓ 화살표, `aria-sort`) — API `sort_dir` 연동 ③ **유망 프리셋 버튼**(`preset=promising`, 활성 상태 표시) ④ **sticky header** ⑤ **첫 로드 스켈레톤** ⑥ **API 오류(404/500/네트워크) → "데이터를 불러오지 못했습니다" + [다시 시도]** ⑦ **빈 상태 CTA 버튼 2개**(시드 추가·지금 수집 실행) ⑧ 상세 모달 **404/네트워크 오류 패널 + Esc/배경 클릭 닫기** ⑨ 수집 버튼 비활성(스피너) + "최대 45초" 문구 ⑩ 온보딩 문구는 "전체 0건"일 때만(필터/프리셋/페이지 초과 구분)

- [ ] **Step 1: 구현 (정적 페이지, 로직 검증은 API 테스트로 대체)**

```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>키워드 대시보드</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
<style>
  body { font-family: 'Malgun Gothic', sans-serif; margin: 24px; background: #f7f8fa; }
  h1 { font-size: 20px; }
  .bar { display: flex; gap: 12px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
  table { width: 100%; border-collapse: collapse; background: #fff; }
  th, td { padding: 8px 10px; border-bottom: 1px solid #eee; text-align: left; font-size: 13px; }
  /* v3: sticky header — 1,000행 스크롤 편의 (UX §3) */
  thead th { position: sticky; top: 0; background: #fff; z-index: 2; }
  th.sortable { cursor: pointer; background: #f0f2f5; user-select: none; }
  .arr { font-size: 10px; color: #2e8b57; font-weight: 700; }
  /* v3: 기회점수 게이지 막대 (UX §3 — 점수는 신호라 숫자+막대 함께) */
  .gauge { display: inline-block; width: 44px; height: 6px; background: #e8eaed;
           border-radius: 3px; vertical-align: middle; margin-right: 4px; }
  .gauge i { display: block; height: 100%; background: #2e8b57; border-radius: 3px; }
  .dim { color: #6b7280; }
  .rise { color: #2e8b57; } .fall { color: #c0392b; }
  .excluded { opacity: 0.45; }  /* v3: 제외된 행 흐림 (UX §5.3) */
  /* v3: 첫 로드 스켈레톤 (UX §5.5) */
  .skel td { height: 38px; background: linear-gradient(90deg, #f3f4f6 25%, #e9ebee 37%, #f3f4f6 63%);
             background-size: 400% 100%; animation: pulse 1.2s infinite; border: none; }
  @keyframes pulse { 0% { background-position: 100% 0; } 100% { background-position: -100% 0; } }
  .btn { padding: 6px 14px; border: 1px solid #ccc; background: #fff; cursor: pointer; border-radius: 4px; }
  .btn:hover { background: #eee; }
  .btn:disabled { opacity: .5; cursor: default; }
  .btn.on { background: #2e8b57; color: #fff; border-color: #2e8b57; }  /* v3: 프리셋 활성 */
  .btn-sm { padding: 2px 8px; font-size: 11px; }
  .empty { color: #999; padding: 40px; text-align: center; }
  .warn { color: #c0392b; font-weight: bold; }
  .badge { padding: 2px 8px; border-radius: 10px; font-size: 11px; }
  .b-gold { background: #fff3d6; color: #8a6d00; }
  .b-gray { background: #eee; color: #666; }
  #detail { position: fixed; inset: 0; background: rgba(0,0,0,.4); display: none; align-items: center; justify-content: center; }
  #detail .panel { background: #fff; padding: 24px; border-radius: 8px; width: 720px; max-width: 90vw; }
  /* v3: 상세 모달 오류 패널 (UX §5.4 — 404/네트워크 오류) */
  #detailError { display: none; margin-bottom: 12px; padding: 12px;
                 background: #fdf2f2; border: 1px solid #f0c4c4; border-radius: 6px; font-size: 13px; }
</style>
</head>
<body>
  <h1>키워드 대시보드</h1>
  <div class="bar">
    <button class="btn" id="collectBtn" onclick="collect()">지금 수집 실행</button>
    <span style="font-size:12px;color:#888">수동 수집은 일부 갱신용 — 전체 수집은 매일 아침 자동</span>
    <span id="status"></span>
  </div>
  <div class="bar">
    <select id="category" onchange="resetAndLoad()">
      <option value="">전체 분야</option>
    </select>
    <select id="commercial" onchange="resetAndLoad()">
      <option value="">상업성 전체</option>
      <option value="60">상업성 60+</option>
      <option value="30">상업성 30+</option>
    </select>
    <select id="discovered" onchange="resetAndLoad()">
      <option value="">발견기간 전체</option>
      <option value="7">최근 7일</option>
      <option value="30">최근 30일</option>
    </select>
    <input id="q" placeholder="키워드 검색" oninput="onSearchInput()">
    <label style="font-size:12px"><input type="checkbox" id="showInactive" onchange="resetAndLoad()"> 제외 목록 포함</label>
    <button class="btn" id="presetBtn" onclick="togglePreset()">유망 프리셋</button>  <!-- v3: UX §8 -->
    <button class="btn" onclick="toggleSeeds()">시드키워드 관리</button>
    <input id="token" type="password" placeholder="토큰" style="width:100px">
    <button class="btn" onclick="saveToken()">토큰 저장</button>
  </div>
  <table>
    <thead><tr>
      <th class="sortable" data-sort="opportunity" onclick="setSort('opportunity')">기회점수</th>
      <th class="sortable" data-sort="commercial" onclick="setSort('commercial')">상업성</th>
      <th class="sortable" data-sort="demand" onclick="setSort('demand')">수요지수</th>
      <th>키워드</th>
      <th>분야</th>
      <th>총 글 수</th>
      <th>쇼핑상품</th>
      <th class="sortable" data-sort="growth" onclick="setSort('growth')">증감률</th>
      <th>일수</th>
      <th>권장</th>
      <th></th>
    </tr></thead>
    <tbody id="rows"></tbody>
  </table>
  <div class="bar" style="margin-top:12px">
    <button class="btn" onclick="prevPage()">이전</button>
    <span id="pageInfo"></span>
    <button class="btn" onclick="nextPage()">다음</button>
  </div>
  <div id="seedsPanel" style="display:none; margin-top:16px; background:#fff; padding:16px;">
    <input id="seedInput" placeholder="시드키워드">
    <input id="seedCat" placeholder="분야">
    <button class="btn" onclick="addSeed()">추가</button>
    <ul id="seedList"></ul>
  </div>
  <div id="detail"><div class="panel">
    <h3 id="detailTitle"></h3>
    <div id="detailError"></div>
    <canvas id="chart" height="220"></canvas>
    <button class="btn" onclick="closeDetail()">닫기</button>
  </div></div>
<script>
let sortBy = 'opportunity';
let sortDir = 'desc';      // v3: 정렬 토글 — 1회 내림차순 → 2회 오름차순 (UX §6)
let page = 1;
let preset = '';           // v3: 유망 프리셋 'promising' — 기회≥70 & 상업성≥60 & 수요≥0.01 (UX §8)
let loading = true;        // v3: 첫 로드 스켈레톤 (UX §5.5)
let loadError = false;     // v3: API 오류 → [다시 시도] (UX §5.5)
let collectBusy = false;   // v3: 수집 중 버튼 비활성 (UX §5.1)
let detailError = null;    // v3: 상세 모달 오류 패널 (UX §5.4)
const PAGE_SIZE = 50;
let totalCount = 0;
let chart = null;
let qTimer = null;

// 외부 유래 문자열(키워드·분야 등)은 반드시 이스케이프 (XSS 방지 — 스펙 §4.10)
function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function authHeaders(extra) {
  const t = localStorage.getItem('dashboard_token') || '';
  return Object.assign(t ? { 'Authorization': 'Bearer ' + t } : {}, extra || {});
}

function saveToken() {
  localStorage.setItem('dashboard_token', document.getElementById('token').value.trim());
  setStatus('토큰 저장됨');
}

function setStatus(msg, warn) {
  const el = document.getElementById('status');
  el.textContent = msg;
  el.className = warn ? 'warn' : '';
}

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (r.status === 401) { setStatus('토큰이 올바르지 않습니다 — 토큰 입력 후 저장', true); throw new Error('401'); }
  if (!r.ok) throw new Error('HTTP ' + r.status);  // v3: 404/500 → load()의 오류 UI (UX §5.5)
  return r.json();
}

function recommend(i) {
  if (i.opportunity === null) return { label: '데이터 쌓는 중', cls: 'b-gray' };
  if (i.demand_idx !== null && i.demand_idx < 0.01) return { label: '수요낮음', cls: 'b-gray' };
  if (i.opportunity >= 70 && i.commercial !== null && i.commercial >= 60) return { label: '쇼커', cls: 'b-gold' };
  if (i.opportunity >= 60) return { label: '애포', cls: 'b-gold' };
  if (i.opportunity <= 35) return { label: '경쟁과열', cls: 'b-gray' };
  return { label: '보류', cls: 'b-gray' };
}

// v3: 기회점수 = 숫자 + 옅은 게이지 막대 (UX §3)
function gaugeCell(opp) {
  if (opp === null) return '<span class="dim">쌓는 중</span>';
  const w = Math.max(0, Math.min(100, opp));
  return `<span class="gauge"><i style="width:${w}%"></i></span>${opp.toFixed(0)}`;
}

// v3: 활성 정렬 컬럼에 ↑/↓ 화살표 + aria-sort (UX §7)
function renderSortArrows() {
  document.querySelectorAll('th.sortable').forEach(th => {
    th.removeAttribute('aria-sort');
    th.querySelectorAll('.arr').forEach(a => a.remove());
    if (th.dataset.sort === sortBy) {
      th.setAttribute('aria-sort', sortDir === 'desc' ? 'descending' : 'ascending');
      const s = document.createElement('span');
      s.className = 'arr';
      s.textContent = sortDir === 'desc' ? ' ▼' : ' ▲';
      th.appendChild(s);
    }
  });
}

function skeletonRows() {
  // v3: 첫 로드 스켈레톤 — 컬럼 골격 유지 (UX §5.5)
  let html = '';
  for (let i = 0; i < 8; i++) html += '<tr class="skel"><td colspan="11"></td></tr>';
  return html;
}

async function load() {
  if (loading && !loadError) {
    document.getElementById('rows').innerHTML = skeletonRows();
  }
  const params = new URLSearchParams({
    sort: sortBy, sort_dir: sortDir, page: page, page_size: PAGE_SIZE,
    category: document.getElementById('category').value,
    commercial_min: document.getElementById('commercial').value || 0,
    discovered_within: document.getElementById('discovered').value || 0,
    q: document.getElementById('q').value.trim(),
    show_inactive: document.getElementById('showInactive').checked ? 1 : 0,
    preset: preset,
  });
  let data;
  try {
    data = await api('/keywords?' + params);
  } catch (e) {
    if (String(e.message) === '401') return;
    loading = false;
    loadError = true;
    // v3: API 오류 → [다시 시도] (UX §5.5)
    document.getElementById('rows').innerHTML =
      '<tr><td colspan="11" class="empty">데이터를 불러오지 못했습니다 ' +
      '<button class="btn btn-sm" onclick="load()">다시 시도</button></td></tr>';
    return;
  }
  loading = false;
  loadError = false;
  totalCount = data.count;
  const rows = document.getElementById('rows');
  rows.innerHTML = '';
  if (!data.items.length) {
    // v3: 온보딩(전체 0건)과 필터/프리셋/페이지 0건을 구분 — 온보딩 카피는 전체 0건일 때만 (UX §5.5)
    const filtering = preset || params.get('q') || params.get('category')
      || Number(params.get('commercial_min')) > 0 || Number(params.get('discovered_within')) > 0
      || params.get('show_inactive') == 1 || page > 1;
    rows.innerHTML = filtering
      ? '<tr><td colspan="11" class="empty">검색 결과가 없습니다 — 필터를 조정하거나 <button class="btn btn-sm" onclick="resetFilters()">필터 초기화</button></td></tr>'
      : '<tr><td colspan="11" class="empty">아직 데이터가 없습니다 — 시드 추가 후 "지금 수집 실행" (점수는 2일차부터)<br><br>'
        + '<button class="btn" onclick="openSeeds()">시드 추가</button> '
        + '<button class="btn" onclick="collect()">지금 수집 실행</button></td></tr>';
  }
  data.items.forEach(i => {
    const stars = i.commercial === null ? '-' : '★'.repeat(Math.max(1, Math.round(i.commercial / 33)));
    const comTip = '쇼핑 데이터 수집 실패';
    const demand = i.demand_idx === null ? '-' : i.demand_idx.toFixed(2);
    const growth = i.growth === null ? '-'
      : `<span class="${i.growth > 0 ? 'rise' : i.growth < 0 ? 'fall' : ''}">${i.growth > 0 ? '▲ ' : i.growth < 0 ? '▼ ' : ''}${(i.growth * 100).toFixed(1)}%</span>`;
    const rec = recommend(i);
    const tr = document.createElement('tr');
    if (!i.active) tr.classList.add('excluded');  // v3: 제외 행 opacity 0.45 (UX §5.3)
    tr.style.cursor = 'pointer';
    tr.innerHTML = `
      <td>${gaugeCell(i.opportunity)}</td>
      <td><span class="badge ${i.commercial === null ? 'b-gray' : 'b-gold'}" ${i.commercial === null ? `title="${esc(comTip)}"` : ''}>${esc(stars)}</span></td>
      <td>${esc(demand)}</td>
      <td>${esc(i.keyword)}${i.active ? '' : ' <span class="badge b-gray">제외됨</span>'}</td>
      <td>${esc(i.category)}</td>
      <td>${Number(i.total_sim).toLocaleString()}</td>
      <td>${Number(i.shop_total).toLocaleString()}</td>
      <td title="최신순 글 수(total_date) 전일 대비 — 총 글 수는 정확도순(total_sim)">${growth}</td>
      <td>${esc(i.days)}일</td>
      <td><span class="badge ${rec.cls}">${esc(rec.label)}</span></td>
      <td><button class="btn btn-sm" onclick="toggleActive(${i.id}, ${i.active ? 'false' : 'true'}, event)">${i.active ? '제외' : '복원'}</button></td>`;
    tr.onclick = () => detail(i.id);
    rows.appendChild(tr);
  });
  renderSortArrows();
  const maxPage = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));
  document.getElementById('pageInfo').textContent = `${totalCount}건 · ${page}/${maxPage}페이지`;
}

function resetAndLoad() { page = 1; load(); }
function resetFilters() {
  document.getElementById('category').value = '';
  document.getElementById('commercial').value = '';
  document.getElementById('discovered').value = '';
  document.getElementById('q').value = '';
  document.getElementById('showInactive').checked = false;
  preset = '';
  updatePresetBtn();
  resetAndLoad();
}
function setSort(col) {
  // v3: 같은 컬럼 재클릭 → 방향 토글 (UX §6: 1회 내림차순, 2회 오름차순)
  if (col === sortBy) sortDir = sortDir === 'desc' ? 'asc' : 'desc';
  else { sortBy = col; sortDir = 'desc'; }
  resetAndLoad();
}
function togglePreset() { preset = preset ? '' : 'promising'; updatePresetBtn(); resetAndLoad(); }
function updatePresetBtn() {
  document.getElementById('presetBtn').classList.toggle('on', !!preset);
}
function onSearchInput() { clearTimeout(qTimer); qTimer = setTimeout(resetAndLoad, 300); }
function prevPage() { if (page > 1) { page--; load(); } }
function nextPage() { if (page * PAGE_SIZE < totalCount) { page++; load(); } }

async function toggleActive(id, active, ev) {
  ev.stopPropagation();
  await api(`/keywords/${id}`, {
    method: 'PATCH',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ active: active }),
  });
  load();
}

async function loadCategories() {
  const cats = await api('/categories');
  const sel = document.getElementById('category');
  const cur = sel.value;
  sel.innerHTML = '<option value="">전체 분야</option>'
    + cats.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
  sel.value = cur;
}

async function collect() {
  if (collectBusy) return;
  collectBusy = true;
  const btn = document.getElementById('collectBtn');
  btn.disabled = true;
  btn.textContent = '수집 중...';
  setStatus('수집 실행 중... (최대 45초)');  // v3: 전 구간 예산 문구 (UX §5.1)
  try {
    const res = await api('/collect', { method: 'POST', headers: authHeaders() });
    if (res.locked) setStatus('이미 수집이 실행 중입니다 — 잠시 후 새로고침');
    else if (res.partial) setStatus(`시간 예산 내 일부만 갱신 (스냅샷 ${res.snapshotted}개) — 나머지는 매일 자동 수집이 처리`);
    else setStatus(`완료: 신규 ${res.new_keywords}개 / 스냅샷 ${res.snapshotted}개 / 오류 ${res.errors.length}개`);
  } catch (e) {
    if (String(e.message) !== '401') setStatus('요청이 시간 초과됐을 수 있습니다 — 전체 수집은 매일 아침 자동 실행됩니다', true);
  } finally {
    collectBusy = false;
    btn.disabled = false;
    btn.textContent = '지금 수집 실행';
  }
  await refreshStatus();
  load();
}

async function refreshStatus() {
  const s = await api('/status');
  let msg = `키워드 ${s.keyword_count}개 · 시드 ${s.seed_count}개`;
  let warn = false;
  if (s.last_success) {
    const day = (s.last_success.finished_at || '').slice(0, 10);
    const ageDays = Math.floor((new Date(s.today) - new Date(day)) / 86400000);
    msg += ` · 마지막 성공 수집 ${day}`;
    if (ageDays > 2) { msg += ' ⚠ 수집이 밀려 있습니다 (Actions/Supabase 상태 확인)'; warn = true; }
  } else {
    msg += ' · 수집 이력 없음';
  }
  setStatus(msg, warn);
}

async function detail(id) {
  // v3: 상세 모달 오류 패널 — 404는 "키워드를 찾을 수 없습니다", 그 외는 [다시 시도] (UX §5.4)
  detailError = null;
  document.getElementById('detailError').style.display = 'none';
  let d;
  try {
    d = await api(`/keywords/${id}`);
  } catch (e) {
    if (String(e.message) === '401') return;
    detailError = e;
  }
  if (detailError) {
    const panel = document.getElementById('detailError');
    panel.style.display = 'block';
    panel.innerHTML = String(detailError.message).startsWith('HTTP 404')
      ? '<strong>키워드를 찾을 수 없습니다</strong> (삭제되었거나 더 이상 존재하지 않음)<br><br>'
        + '<button class="btn btn-sm" onclick="closeDetail()">목록으로 돌아가기</button>'
      : '<strong>상세 정보를 불러오지 못했습니다</strong><br><br>'
        + `<button class="btn btn-sm" onclick="detail(${id})">다시 시도</button>`;
    showDetailPanel(true);
    return;
  }
  document.getElementById('detailTitle').textContent = d.keyword;
  showDetailPanel(true);
  const ctx = document.getElementById('chart');
  if (chart) chart.destroy();
  chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: d.history.map(h => h.day),
      datasets: [
        { label: '기회점수', data: d.history.map(h => h.opportunity), borderColor: '#2e8b57', yAxisID: 'y' },
        { label: '수요지수×100', data: d.history.map(h => h.demand_idx === null ? null : h.demand_idx * 100), borderColor: '#3399ff', yAxisID: 'y' },
        { label: '총 글 수', data: d.history.map(h => h.total_sim), borderColor: '#666', yAxisID: 'y2' },
        { label: '쇼핑 상품 수', data: d.history.map(h => h.shop_total), borderColor: '#e8a13a', yAxisID: 'y2' },
      ],
    },
    options: {
      responsive: true,
      scales: {
        y: { position: 'left', suggestedMin: 0, suggestedMax: 100 },
        y2: { position: 'right', grid: { drawOnChartArea: false } },
      },
    },
  });
}

function showDetailPanel(open) { document.getElementById('detail').style.display = open ? 'flex' : 'none'; }
function closeDetail() { showDetailPanel(false); }
// v3: Esc / 배경 클릭으로 모달 닫기 (UX §5.4)
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDetail(); });
document.getElementById('detail').addEventListener('click',
  e => { if (e.target.id === 'detail') closeDetail(); });

async function toggleSeeds() {
  const panel = document.getElementById('seedsPanel');
  panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
  await renderSeeds();
}

// v3: 빈 상태 CTA — [시드 추가]는 시드 패널을 펼침 (UX §5.5)
function openSeeds() {
  document.getElementById('seedsPanel').style.display = 'block';
  renderSeeds();
}

async function renderSeeds() {
  const seeds = await api('/seeds');
  const ul = document.getElementById('seedList');
  ul.innerHTML = '';
  seeds.forEach(s => {
    const li = document.createElement('li');
    li.innerHTML = `${esc(s.keyword)} (${esc(s.category)}) <button class="btn btn-sm" onclick="deleteSeed(${s.id})">삭제</button>`;
    ul.appendChild(li);
  });
}

async function addSeed() {
  const keyword = document.getElementById('seedInput').value.trim();
  const category = document.getElementById('seedCat').value.trim();
  if (!keyword) return;
  await api('/seeds', {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ keyword, category }),
  });
  document.getElementById('seedInput').value = '';
  await renderSeeds();
}

async function deleteSeed(id) {
  await api(`/seeds/${id}`, { method: 'DELETE', headers: authHeaders() });
  await renderSeeds();
}

document.getElementById('token').value = localStorage.getItem('dashboard_token') || '';
refreshStatus();
loadCategories();
load();
</script>
</body>
</html>
```

- [ ] **Step 2: UX 스펙 반영 점검 (수동)**

`docs/superpowers/specs/2026-08-03-naver-blog-keyword-dashboard-ux.md` (v2) §5~§7 대비 확인 — v3에서 아래 항목이 **코드로 구현**되어 있으므로 브라우저에서 눈으로 검증:
- 상태별 피드백: done/partial/locked/401/타임아웃 문구 · 수집 중 버튼 비활성(스피너) · 마지막 수집 2일 초과 경고
- 빈 상태 CTA 버튼 2개([시드 추가] → 시드 패널, [지금 수집 실행]) · 첫 로드 스켈레톤 · API 오류 [다시 시도]
- 온보딩 카피는 전체 0건일 때만 — 필터/유망 프리셋/페이지 초과는 "검색 결과가 없습니다" + [필터 초기화]
- 기회점수 게이지 막대(`.gauge`) · 증감률 ▲/▼ 색상(`.rise/.fall`) · 제외 행 opacity 0.45(`.excluded`) · sticky header(`thead th`)
- 정렬 토글(같은 컬럼 재클릭 → 오름차순 전환, ↑/▼ 화살표 + `aria-sort=descending|ascending`)
- 유망 프리셋 버튼(`preset=promising` 서버 필터, 활성 시 초록 하이라이트)
- 상세 모달: Esc·배경 클릭 닫기 · 404 → "키워드를 찾을 수 없습니다"+[목록으로 돌아가기] · 네트워크 오류 → [다시 시도] 패널
- 발견기간 필터(최근 7/30일) · 검색 300ms 디바운스 · 수동 수집 "최대 45초" 문구

- [ ] **Step 3: 수동 확인 — 서버 기동**

```powershell
.venv\Scripts\python -m uvicorn server:app --port 8000
```

Expected: http://localhost:8000 에 대시보드 렌더링. 키워드 없으면 빈 상태 안내 + CTA. 토큰 저장 후 시드 추가·수집 버튼 동작(로컬 개발은 `ENV` 미설정/development라 `DASHBOARD_TOKEN` 미설정 시 인증 생략 — 프로덕션은 기동 거부, Task 10 v3).

- [ ] **Step 4: 커밋**

```bash
git add static/index.html
git commit -m "feat: dashboard with paging, demand column, exclude and token auth"
```

---

### Task 12: 배포 설정 (vercel.json + api/index.py + GitHub Actions)

**Files:**
- Create: `vercel.json`
- Create: `api/index.py`
- Create: `.github/workflows/daily-collect.yml`

- [ ] **Step 1: vercel.json 작성**

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "functions": {
    "api/**/*.py": {
      "maxDuration": 60,
      "excludeFiles": "{tests/**,**/test_*.py,fixtures/**,data/**}"
    }
  },
  "rewrites": [{ "source": "/(.*)", "destination": "/api/index" }]
}
```

- [ ] **Step 2: api/index.py 작성 (Vercel Python 런타임 진입점 — ASGI `app` 변수 자동 감지)**

```python
# api/index.py
from server import app  # noqa: F401
```

- [ ] **Step 3: GitHub Actions 워크플로우 작성**

v2 필수 요소 4가지: ① cron 오프셋(정각 혼잡 회피) ② `concurrency`(중복 실행 방지 — v1의 `.lock` 파일은 러너가 매번 새 파일시스템이라 무력했음) ③ `timeout-minutes`(행 걸림이 무료 분량을 태우는 것 방지) ④ **keep-alive**(레포 60일 무활동 시 스케줄 워크플로우가 자동 비활성화되어 수집이 조용히 멈추는 것 방지).

```yaml
# .github/workflows/daily-collect.yml
name: daily-collect

on:
  schedule:
    - cron: '17 22 * * *'   # 매일 07:17 KST (22:17 UTC 전날)
  workflow_dispatch:

concurrency:
  group: daily-collect
  cancel-in-progress: false

jobs:
  collect:
    runs-on: ubuntu-latest
    timeout-minutes: 60
    permissions:
      contents: write   # keep-alive 빈 커밋 푸시용
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run collection
        run: python collect.py
        env:
          NAVER_CLIENT_ID: ${{ secrets.NAVER_CLIENT_ID }}
          NAVER_CLIENT_SECRET: ${{ secrets.NAVER_CLIENT_SECRET }}
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
      - name: Keep-alive (스케줄 60일 자동 비활성화 방지)
        if: github.event_name == 'schedule'
        run: |
          last=$(git log -1 --format=%ct)
          now=$(date +%s)
          if [ $(( (now - last) / 86400 )) -ge 50 ]; then
            git config user.name "github-actions[bot]"
            git config user.email "github-actions[bot]@users.noreply.github.com"
            git commit --allow-empty -m "chore: keep scheduled workflow alive"
            git push
          fi
```

참고: `collect.py`는 전량 실패 시 exit 1을 반환하므로 워크플로우 실패 → GitHub 기본 실패 메일이 발송된다 (스펙 §5). "실행 자체가 안 되는" 상황까지 감지하려면 마지막 스텝에 healthchecks.io 핑 추가(선택).

- [ ] **Step 4: 로컬 테스트로 검증**

Run: `python -m pytest tests/test_collect.py -v`
Expected: PASS (10 passed — 워크플로우는 동일 코드 호출)

- [ ] **Step 5: 커밋**

```bash
git add vercel.json api/index.py .github/workflows/daily-collect.yml
git commit -m "feat: deployment config with concurrency and keep-alive"
```

---

### Task 13: 배포 절차 (사용자 수동 + 검증)

- [ ] **Step 1: GitHub 레포 생성 및 푸시**

```bash
gh repo create naver-keyword-dashboard --private --source=. --push
```

- [ ] **Step 2: Supabase 프로젝트 생성 + 풀러 연결 문자열 확보 (v2 핵심 — 여기서 틀리면 배포 전체가 막힘)**

Supabase 대시보드 → 프로젝트 생성 → `Connect`(연결 문자열):
- **Session pooler** (포트 5432, `aws-0-<region>.pooler.supabase.com`) → **GitHub Secrets용** (장시간 배치)
- **Transaction pooler** (포트 6543, 같은 호스트) → **Vercel Env용** (서버리스)
- **`db.<ref>.supabase.co` 직결 주소는 복사 금지** — 무료 티어에서 IPv6 전용이라 GitHub Actions 러너·Vercel(Lambda)에서 "Network is unreachable"로 실패

주의: Supabase 무료 티어는 7일 무활동 시 일시정지되며 **대시보드에서 수동 복구**해야 한다(자동 재개 아님). 매일 수집이 돌면 발생하지 않지만, 수집이 멈춘 채 7일이 지나면 연쇄로 잠기므로 /status 경고와 실패 메일을 무시하지 말 것.

- [ ] **Step 3: GitHub Secrets 등록**

GitHub 레포 Settings → Secrets and variables → Actions:
```
NAVER_CLIENT_ID, NAVER_CLIENT_SECRET, DATABASE_URL(=Session pooler)
```

- [ ] **Step 4: Vercel 배포 + 환경변수**

```powershell
npx vercel login
npx vercel --prod
```

Vercel 프로젝트 → Settings → Environment Variables (Production):
```
NAVER_CLIENT_ID, NAVER_CLIENT_SECRET,
DATABASE_URL(=Transaction pooler), DASHBOARD_TOKEN,
DATALAB_ENABLED=1, DATALAB_ANCHOR=냉장고,
ENV=production   # v3: 토큰 미설정 시 기동 거부(fail-closed) 활성화
```

Expected: `https://<project>.vercel.app` 접속 시 대시보드 렌더링.

- [ ] **Step 5: 스케줄 수집 1차 실행 및 리스크 검증**

```bash
gh workflow run daily-collect.yml
```

Actions 로그에서 확인:
- `완료: 신규 N개, 스냅샷 M개, ...` 출력, Supabase에 daily_stats 행 생성
- **자동완성 차단 여부**: collection_log에 `blocked` 기록이 있으면(또는 exit 1) GH 러너 IP 차단 → Step 7 대안 적용
- **데이터랩 응답**: `수요갱신 N개` > 0 확인 (2일차부터 — 기회점수가 있어야 대상 선정됨)
- **배치 시간 실측 (v3 — 스펙 §8 정정 요구사항)**: 실행 시작~종료 시간과 키워드당 평균/최악 호출 시간을 기록한 뒤, `design.md §8` 용량 표의 "~20분/일 (키워드당 ~1.2초)"를 **실측값으로 갱신**. 최악 조건(호출 타임아웃 10초 × 키워드당 3회)이 `timeout-minutes: 60`을 넘는지 확인하고, 넘으면 `ACTIVE_KEYWORD_CAP`이나 호출 타임아웃을 조정한 뒤 표를 다시 산정

- [ ] **Step 6: 대시보드 검증**

1. 토큰 입력·저장 → 시드키워드 추가
2. "지금 수집 실행" → 첫 실행은 축소 발굴(30개) + 일부 스냅샷, `partial`이면 안내 문구 표시 확인
3. 무토큰 상태에서 시드 추가 시도 → "토큰이 올바르지 않습니다" 확인 (쓰기 보호 동작)

- [ ] **Step 7: 크롤링 차단 시 대체 스케줄러 (cron-job.org)**

자동완성이 GitHub Actions IP에서 차단되면 cron-job.org(무료)에서 매일 07:17에
`https://<project>.vercel.app/collect`를 **POST + `Authorization: Bearer <토큰>` 헤더 + body `{"trigger":"schedule"}`**로 호출
(v1 문서의 "GET 호출"은 오기 — 엔드포인트는 POST. **v2의 manual-only 호출은 발굴·수요·은퇴·보존이 누락되어 스케줄러를 대체하지 못했음 — v3에서 trigger=schedule로 전 구간 대체**).
`trigger=schedule`은 발굴→스냅샷→수요 확증→은퇴→보존 정리까지 GH Actions와 동일한 전체 파이프라인을 실행하되, Vercel 60초 한도 내에서 예산(45초)이 적용된다 — 잔여 키워드는 다음 실행이 "오래된 스냅샷부터" 순환 처리해 며칠에 걸쳐 전체를 커버한다.
수동 버튼과 달리 발굴이 포함되므로, `AUTOCOMPLETE_MAX_REQUESTS`·상한 env로 1회 처리량을 조정해 예산 내에서 의미 있는 발굴량이 나오도록 튜닝한다.

- [ ] **Step 8: 커밋**

```bash
git add -A
git commit -m "docs: deployment verification"
```

---

### Task 14: README (클라우드 배포 가이드)

**Files:**
- Create: `README.md`

- [ ] **Step 1: README 작성**

````markdown
# 네이버 블로그 키워드 대시보드

네이버 블로그(애드포스트/쇼핑커넥트) 수익을 위한 키워드 발굴 + 경쟁도/상업성/수요 분석 도구.
로컬 PC 없이 클라우드(Supabase + Vercel + GitHub Actions)에서 실행됩니다. 월 비용 0원.

## 아키텍처

- **DB**: Supabase Postgres (무료 500MB, Supavisor 풀러 경유)
- **대시보드/API**: Vercel Hobby (FastAPI ASGI, 무료)
- **매일 수집**: GitHub Actions cron (매일 07:17 KST, 무료)
- 기준 시간대: 모든 날짜 키는 KST (러너/서버리스의 UTC와 무관)

## 설치 (개발 환경)

1. `python -m venv .venv`
2. `.venv\Scripts\pip install -r requirements.txt`
3. `.env.example` → `.env` 복사 후 설정 (개발은 SQLite 기본값 그대로)
4. 대시보드 실행: `.venv\Scripts\python -m uvicorn server:app --port 8000` → http://localhost:8000
5. 시드키워드는 대시보드에서 추가 (로컬은 `DASHBOARD_TOKEN` 미설정 시 인증 생략)
6. 수집: `.venv\Scripts\python collect.py`

## 클라우드 배포

1. GitHub 레포 생성 후 푸시 (private 권장)
2. Supabase 프로젝트 생성 → **풀러 연결 문자열** 사용
   - GitHub Secrets `DATABASE_URL` = Session pooler (포트 5432)
   - Vercel Env `DATABASE_URL` = Transaction pooler (포트 6543)
   - `db.<ref>.supabase.co` 직결 주소 금지 (IPv6 전용 → Actions/Vercel에서 연결 실패)
3. GitHub Secrets: `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`, `DATABASE_URL`
4. `npx vercel --prod` 배포, Vercel Env에 `DASHBOARD_TOKEN` 포함 등록
5. 매일 07:17 자동 수집: `.github/workflows/daily-collect.yml`

## 점수 설명

- 기회점수 = 40×상위글신선도 + 30×성장정규화(일 5% 만점) + 30×(1−경쟁도(1만 글 포화))
  — 최소 2일치 데이터 필요
- 상업성 = 쇼핑 상품 수·가격대 기반 0~100
- 수요지수 = 데이터랩 앵커(기본 "냉장고") 대비 상대 수요 — 기회점수 상위 200개만 매일 확증
- 프록시 신호이므로 절대 기준이 아님 — 원시값과 함께 판단

## 키워드 수명주기

- 활성 총량 캡 1,000개 (`ACTIVE_KEYWORD_CAP`) — API 쿼터·Actions 분량이 이 캡 기준으로 산정됨
- 발견 14일 후에도 저성과(기회 < 35, 상업성 < 30)면 자동 은퇴
- 대시보드 "제외" 버튼으로 수동 제외/복원
- 보존: 스냅샷 90일, 상위글 발행일 30일, 로그 180일

## 운영 주의사항

- **쓰기 동작(시드/수집/제외)은 `DASHBOARD_TOKEN` 필요** — 대시보드 우측 상단에 입력·저장. **프로덕션(`ENV=production`)에서는 토큰 미설정 시 서버가 기동되지 않음(fail-closed)** — 로컬 개발만 인증 생략
- 자동완성은 비공식 엔드포인트 — 차단 시 자동 중단·로그 기록 + exit 1(실패 메일). 차단 시 cron-job.org(무료)가 `/collect`를 `{"trigger":"schedule"}`로 호출해 전체 파이프라인을 대체
- 수동 수집 버튼은 시간 예산(45초) 내 일부 갱신용 — 발굴·개별 호출까지 예산 적용. 전체 수집은 스케줄러 담당
- GitHub Actions 스케줄은 레포 60일 무활동 시 자동 비활성화 → 워크플로우가 keep-alive 커밋으로 자체 방지
- Supabase 무료는 7일 무활동 시 일시정지 — **대시보드에서 수동 복구** 필요. /status의 "마지막 성공 수집" 경고와 Actions 실패 메일을 무시하지 말 것
- 시크릿은 GitHub Secrets/Vercel Env에만 보관, 레포 커밋 금지
````

- [ ] **Step 2: 커밋**

```bash
git add README.md
git commit -m "docs: cloud deployment guide"
```

---

### Task 15: Postgres 통합 테스트 + 브라우저 검증 (v3 신설 — 스펙 §9)

v2까지는 SQLite 단위 테스트만 있어 Postgres 다이얙트(psycopg2 경로·ON CONFLICT·원자 잠금·재연결·트랜잭션 경계)가 배포 후에야 검증됐음. v3는 로컬/CI Postgres로 사전 검증하고, 대시보드 UX를 브라우저에서 확인한다.

**Files:**
- Create: `tests/test_db_postgres.py`
- Create: `tests/e2e_dashboard.py`

- [ ] **Step 1: Postgres 통합 테스트 작성** (`DATABASE_URL` 설정 시에만 실행, 미설정 시 skip)

```python
# tests/test_db_postgres.py
import os
import threading

import pytest

import db

PG_URL = os.getenv("DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not PG_URL, reason="DATABASE_URL 미설정")


def make_db():
    d = db.Database(PG_URL)
    d.init()
    return d


def test_init_is_idempotent_and_lock_index_exists():
    d = make_db()
    d.init()  # 재실행 안전 (마이그레이션 멱등 — CREATE IF NOT EXISTS)
    rows = d._qd(
        "SELECT indexname FROM pg_indexes WHERE tablename = 'collection_runs'",
        (), fetch=True)
    assert any("idx_collection_runs_running" in r["indexname"] for r in rows)


def test_upsert_and_query_roundtrip():
    d = make_db()
    kid = d.upsert_keyword("pg통합", category="가전", day="2026-08-03")
    d.insert_daily_stats(kid, "2026-08-03", {"total_sim": 100, "opportunity": 55.0})
    rows = d.query_keywords(q="pg통합")
    assert rows[0]["opportunity"] == 55.0
    assert rows[0]["category"] == "가전"  # LEFT JOIN + COALESCE fallback 동일 동작


def test_run_lock_atomic_under_concurrency():
    # v3: 동시 start_run 8건 → running 행은 정확히 1개 (원자 취득, 스펙 §4.7)
    d = make_db()
    d._qd("DELETE FROM collection_runs", ())
    now = "2026-08-03T07:17:00+09:00"
    stale = "2026-08-03T06:17:00+09:00"
    ids, errors = [], []

    def acquire():
        try:
            ids.append(d.start_run("schedule", now, stale))
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    ts = [threading.Thread(target=acquire) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errors
    running = [r for r in d.get_last_runs(10) if r["status"] == "running"]
    assert len(running) == 1  # 잠금 소유자 1명


def test_reconnect_after_pooler_restart():
    # v3: 풀러 재시작(커넥션 사망) 시뮬레이션 — _q의 1회 재연결로 복구 (스펙 §3)
    d = make_db()
    d._connect()  # 커넥션 강제 교체
    rows = d._qd("SELECT 1 AS ok", (), fetch=True)
    assert rows[0]["ok"] == 1
    d.close()
```

- [ ] **Step 2: 브라우저 e2e 작성** (선택 — Playwright 설치 시)

```python
# tests/e2e_dashboard.py
# 실행: .venv\Scripts\pip install playwright && .venv\Scripts\playwright install chromium
#       (서버 기동 후) .venv\Scripts\python tests/e2e_dashboard.py
import sys

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8000"


def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page()
        page.goto(BASE)
        page.wait_for_selector("table")
        # 첫 로드 스켈레톤 → 데이터/빈 상태 전환 (UX §5.5)
        page.wait_for_selector(".empty, .gauge", timeout=10_000)
        # 빈 상태(전체 0건)면 CTA 버튼 2개 확인 — 온보딩 카피와 함께
        if page.locator("text=아직 데이터가 없습니다").count():
            assert page.locator("button:has-text('시드 추가')").count() == 1
            assert page.locator("button:has-text('지금 수집 실행')").count() == 1
        # 정렬 토글: 1회 클릭 내림차순(aria-sort=descending) → 2회 오름차순 (UX §6)
        th = page.locator("th.sortable").first
        th.click()
        page.wait_for_timeout(200)
        assert page.locator("th[aria-sort='descending']").count() == 1
        th.click()
        page.wait_for_timeout(200)
        assert page.locator("th[aria-sort='ascending']").count() == 1
        b.close()


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: 실행**

```
# 로컬 Postgres/Docker 또는 CI 환경에서
DATABASE_URL=postgresql://u:p@localhost:5432/db python -m pytest tests/test_db_postgres.py -v
# 브라우저 e2e (서버 기동 후, 선택)
python tests/e2e_dashboard.py
```

- [ ] **Step 4: 커밋**

```bash
git add tests/test_db_postgres.py tests/e2e_dashboard.py
git commit -m "test: postgres integration and browser e2e"
```

---

### Task 16: 전체 회귀 테스트 및 마무리

- [ ] **Step 1: 전체 테스트 실행**

Run: `python -m pytest -v`
Expected: PASS — **72개** (config 4 + db 17 + naver 2 + autocomplete 8 + refine 5 + analyzer 4 + scoring 5 + datalab 5 + collect 10 + api 12)
추가(선택): Postgres 통합 `pytest tests/test_db_postgres.py`(DATABASE_URL 설정 시, Task 15) · 브라우저 e2e `python tests/e2e_dashboard.py`(Playwright 설치 시)

- [ ] **Step 2: 실제 API 키로 수동 실행 확인 (사용자 제공)**

```powershell
.venv\Scripts\python collect.py
```

Expected: `완료: 신규 N개, 스냅샷 M개, 수요갱신 K개, 은퇴 R개, 오류 0개`

- [ ] **Step 3: GitHub Actions에서 실행 확인**

```bash
gh workflow run daily-collect.yml
```

Expected: Actions 로그에 완료 출력 + Supabase에 데이터 적재. 2일차 실행 후 기회점수·수요지수 표시 확인.

- [ ] **Step 4: 배포된 대시보드 확인**

`https://<project>.vercel.app` 접속 → 목록·점수·페이징·상세 그래프(점수 추이 포함)·제외 버튼·수동 수집(부분 갱신 안내) 동작 확인.

- [ ] **Step 5: 최종 커밋**

```bash
git add -A
git commit -m "chore: final regression pass"
```

---

## 자체 리뷰 결과 (v3)

**스펙 v3 커버리지 확인**
- KST 기준일 통일 (스펙 §3) → config 헬퍼(Task 1), analyzer 기준일 주입(Task 6), collect 전 구간(Task 9) ✓
- 자동완성: 백오프/차단감지/기존키워드 경유/요청상한/방어적 파싱 + 실측 스모크 + **시드 분야 전파·예산 기반 중단(budget/blocked 구분)** (스펙 §4.1) → Task 4, 9 ✓
- 2단 블랙리스트 + 포털 토큰 + 과차단 방지 + **필터 사유 반환·기록** (스펙 §4.2) → Task 5, 9 ✓
- blog 2종 + shop + 카테고리 (스펙 §4.3) → Task 3, 6 ✓
- 데이터랩 수요 확증: 앵커 정규화, 상위 200개, graceful degradation + **오류 DatalabError 정규화** (스펙 §4.4) → Task 8, 9 ✓
- 점수 공식 개정(경쟁도 1만 포화, 성장 5% 정규화) + 사전계산 저장 + **전일 대비만 산출(공백 NULL)** (스펙 §4.5) → Task 7, 9 ✓
- 수명주기: 총량 캡·자동 은퇴(**NULL 점수 보호**)·수동 제외·보존 정리 (스펙 §4.6) → Task 9(캡/은퇴/정리), Task 10~11(PATCH/제외 버튼) ✓
- 스키마 v2(점수 컬럼·collection_runs·타임스탬프 로그·category 보존) + **원자 잠금(부분 유니크 인덱스)·stale 60분** + check_same_thread + **재연결 1회 재시도** (스펙 §4.7) → Task 2 ✓
- API: 단일 쿼리+페이징(**LEFT JOIN**), PATCH, 인증(**fail-closed**), 재연결, 404 + **sort_dir·preset·trigger=schedule·/categories 통합** (스펙 §4.8) → Task 10 ✓
- 수동 수집 시간 예산 + 첫 실행 축소 발굴 + **예산 전 구간 적용** (스펙 §4.9) → Task 9, 10 ✓
- 대시보드: 이스케이프·토큰·수요 컬럼·페이징·제외·상태 경고 + **게이지·sticky·스켈레톤·오류 재시도·CTA·정렬 토글·aria-sort·유망 프리셋** (스펙 §4.10) → Task 11 ✓
- UX 스펙 v2: 레이아웃·토큰·컴포넌트 상태·인터랙션·접근성·"유망" 프리셋 (UX 스펙 §1~§8) → Task 11(Step 2 점검) ✓
- 스케줄러: 오프셋 cron·concurrency·timeout·keep-alive·실패 메일(exit 1) + **차단도 exit 1** (스펙 §5) → Task 9, 12 ✓
- 배포: 풀러 2종 가이드, Supabase 수동 복구 주의, 차단 대안(**trigger=schedule 전 구간**), **배치 시간 실측** (스펙 §3, 6, 8) → Task 0, 13, 14 ✓
- 에러처리 표 (스펙 §6) → Task 3, 4, 8, 9, 10 ✓
- 보안: 쓰기 토큰(**프로덕션 기동 거부**), XSS (스펙 §7) → Task 10, 11 ✓
- 테스트 전략: 날짜 하드코딩 금지·검산된 기대값 + **PG 통합·브라우저 e2e·리스크 시나리오** (스펙 §9) → 전 Task + Task 15 ✓

**타입/이름 일관성**: `analyze_keyword(client, keyword, today)` 반환 키(`total_sim/total_date/fresh_ratio/top_post_dates/shop_total/shop_avg_price/shop_category/shop_error`)가 Task 6 → 9에서 동일 사용, `stats.update()`로 `growth/opportunity/commercial` 추가 후 `insert_daily_stats`의 `_STATS_COLUMNS`와 일치. `run_collection(cfg, client, today, trigger, budget_seconds)` 시그니처 Task 9 → 10 일치(테스트 `fake_run`도 동일 형태). **`expand_keywords(...) → (list, dict, stopped)`** Task 4 정의 = Task 9 discover 사용 일치. `refine_keywords(...) → (list, [(kw, reason)])` Task 5 정의 = Task 9 사용 일치. `Database` 메서드명 Task 2 정의 = Task 9/10 호출 일치 (`get_keyword` 포함). config 키 이름(`env`/`run_lock_stale_minutes` 포함) Task 1 = Task 9/10 사용 일치. `result["crawl_stopped"]` 키는 Task 9에서만 생성·소비(HTML은 partial/locked만 사용).

**v1·v2 계획 대비 교정된 오류 (재발 방지 기록)**
1. 테스트 기대값 4건 검산 교정: `opportunity_score(1,1,100)`의 100→(신공식 검산으로 재설계), `commercial_score(10,1000)` 10→2.5, API growth 0.3→0.27(사전계산 저장값), commercial_min=90 count 0→(픽스처 재설계)
2. `sqlite3.connect`에 `check_same_thread=False` 누락 → FastAPI 스레드풀에서 즉사하던 문제
3. 날짜 하드코딩 테스트("20260801" vs 실행일) → 기준일 주입으로 제거
4. `type nul`(cmd 문법) → `python -c` 크로스 플랫폼 명령
5. cron-job.org "GET 호출" → POST + Authorization 헤더 → **v3: + body `{"trigger":"schedule"}` 전 구간 대체**
6. `upsert_keyword`의 무조건 category UPDATE → 비어있지 않을 때만
7. 파일 트리에 test_config/test_analyzer/test_collect 누락 → 정리

**v3 리뷰 반영 기록 (구현 전 사전 리뷰 18건 → 수정 확인)**
1. 수동 예산이 발굴·개별 호출에 미적용 → Task 4(budget_seconds·타임아웃 축소), Task 9(discover에도 예산) ✓
2. 스냅샷 없는 키워드 미표시(INNER JOIN) → Task 2 LEFT JOIN + 테스트 ✓
3. 데이터랩 원시 예외 전파 → Task 8 DatalabError 정규화 + 테스트 2건 ✓
4. 잠금 비원자 + stale 30분 → Task 2 원자 취득(유니크 인덱스) + stale 60분(cfg) + PG 경합 테스트 ✓
5. cron-job.org 대체 불가(manual-only) → Task 10 `/collect` trigger=schedule ✓
6. 토큰 누락 시 무인증 → Task 10 create_app 기동 거부(fail-closed) + 테스트 ✓
7. 증감률이 최근 과거 스냅샷과 비교 → Task 9 compute_scores 전일(day-1) 제한 + 테스트 ✓
8. 상업성 NULL 0점 취급 → Task 2 find_retire_candidates NULL 보호 + 테스트 ✓
9. 차단이 exit 0 → Task 9 main() blocked exit 1 + 테스트 ✓
10. 실행 결과 항상 done → Task 9 상태 구분(done/partial/failed), Task 10 /status done만 집계 ✓
11. UX-구현·API 계약 불일치 → Task 10 sort_dir·preset, Task 11 전 항목 구현 ✓
12. 오류·빈 상태 미완 → Task 11 스켈레톤·오류 재시도·CTA·온보딩 구분 ✓
13. 시드 분야 미전파 → Task 4 origins + Task 9 upsert category + /categories 통합 ✓
14. 필터 사유 미기록 → Task 5 사유 반환 + Task 9 로그 기록 ✓
15. PG 운영 검증 부족 → Task 15 통합 테스트(멱등 init·경합·재연결) ✓
16. 56개 테스트 한계 → 72개 + PG 통합 + 브라우저 e2e(Task 15) ✓
17. UX 문서 v1 무이력 → UX 스펙 v2 승격 + 개정 이력 ✓
18. 1.2초/키워드 미실측 → 스펙 §8 실측 우선 명시 + Task 13 실측 절차 ✓

**결정사항 (v3)**
- 쇼핑 카테고리는 category1+2 저장 유지 (분야 필터 용도로 충분)
- top_results 보존 30일 (신선도 계산의 원본일 뿐 — DB 500MB 예산의 최대 소비처라 짧게)
- 수동 수집: 발굴 생략 + 시간 예산 45초, 활성 0개(첫 실행)만 축소 발굴 30개 — **예산은 발굴·개별 호출 타임아웃까지 전 구간 적용** (v3)
- **cron-job.org 대체 경로**: `/collect` body `{"trigger":"schedule"}` — 발굴·수요·은퇴·보존까지 전 구간 실행하되 Vercel 한도 내 예산 45초 (v3)
- 데이터랩 앵커 기본 "냉장고" (계절성 낮은 중간 규모) — env로 조정, 앵커 ratio 0이면 오류로 교체 유도
- 은퇴 임계 초기값: 14일 경과 + 7일 창에서 기회 < 35 그리고 상업성 < 30 — **점수 NULL이면 은퇴 보호** (v3)
- 조회 API는 v1에서 공개 유지, 쓰기만 토큰 — **프로덕션은 토큰 미설정 시 기동 거부(fail-closed)** (v3)
- **실행 잠금은 부분 유니크 인덱스로 원자 취득** — v2의 SELECT→INSERT 경합 창은 제거 (v3)
- **DB 테스트는 SQLite 단위(17개) + Postgres 통합(Task 15)** — 배포 후에만 PG 다이얙트를 확인하던 v2 관행 제거 (v3)
- 발굴 키워드 분야: 1차(시드 직속)만 시드 category 상속, 2차 이상은 shop 데이터로 채움 (v3)

---

## 구현 진행 기록 (2026-08-03 — 전체 완료)

**상태: Task 0~16 구현 완료** — 단위 테스트 72 passed + PG 통합 4 skipped(DATABASE_URL 미설정 시) + 브라우저 e2e(선택). main 병합·푸시됨(`a57ce3d`).

### 구현 중 발견·수정 (플랜 코드 대비 편차 — 테스트가 스펙이므로 전부 테스트 통과를 위한 정당한 수정)

| # | 위치 | 편차 | 사유 |
|---|---|---|---|
| 1 | Task 2 `query_keywords` | NULL 동점 tiebreak를 `k.first_seen, k.id`로 | 플랜의 `k.id` 단독은 플랜 자체 테스트 2건(페이징·노스냅샷)을 동시에 만족 불가 |
| 2 | Task 9 `run_collection` | 잠금 타임스탬프를 마이크로초 정밀도로 | 초 단위면 같은 초에 시작된 두 실행의 `started_at`이 동일해 소유권 검사가 무력화됨 |
| 3 | Task 9 `main()` | 모든 종료 경로에서 `SystemExit` 발생 | 테스트가 `pytest.raises(SystemExit)`로 main을 직접 호출하는 계약 |
| 4 | Task 10 `trigger_collect` | `body: CollectIn = Body(default_factory=CollectIn)` | 본문 없는 POST /collect가 FastAPI에서 422가 되는 것 방지(기본 manual) |
| 5 | Task 0 `requirements.txt` | `psycopg2-binary==2.9.12` | 2.9.10은 Python 3.14(cp314) 휠 없음 — 로컬 설치 불가 |
| 6 | Task 15 PG 테스트 | 4개(계획 문구의 5는 오기) | 파일 정의 그대로 4개 함수 |
| 7 | 최종 리뷰 반영 | `update_demand`에 예산 적용(budget_seconds 파라미터) | cron-job.org 대체 경로(45초)에서 데이터랩 50배치가 Vercel 60초를 넘으면 실행이 죽고 60분 잠금이 남는 문제 — 리뷰 Important #1 |
| 8 | 최종 리뷰 반영 | `server.py` `run_db`에 `threading.Lock` | FastAPI 스레드풀에서 단일 psycopg2 커넥션 공유는 스레드 안전하지 않음 — 리뷰 Important #2 |
| 9 | 최종 리뷰 반영 | `analyzer.py` lprice 관용 파싱·fresh window `>` 연산(정확히 7일)·`hmac.compare_digest`·`insert_top_results` 재연결 재시도·PG 경합 테스트 스레드별 커넥션 | 리뷰 Minor #1~#4 + 테스트 실효성 |

### 실측 스모크 결과
- **자동완성 실측 포맷 검증 (스펙 §4.1 필수)**: 실 네이버 엔드포인트에서 "에어프라이어" → 연관 키워드 10건 정상 파싱(구 list 포맷 확인, 파서 수정 불필요) ✓
- **서버 기동**: `uvicorn server:app` → `/` HTTP 200(대시보드 20,105B), `/status` 정상 응답 ✓
- **수동 수집 smoke**: `python collect.py` → `완료: 신규 0개, 스냅샷 0개, ...` 정상 종료(API 키 없이) ✓

### 남은 수동 단계 (Task 13 — 사용자 자격 증명 필요)
1. **Supabase**: 프로젝트 생성 → Session pooler(5432) 문자열을 GitHub Secrets `DATABASE_URL`로, Transaction pooler(6543)를 Vercel Env로 등록
2. **GitHub Secrets**: `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`, `DATABASE_URL` 등록
3. **Vercel**: `npx vercel --prod` 배포 + Env에 `DASHBOARD_TOKEN`, `ENV=production`, `DATABASE_URL`(6543), `DATALAB_ENABLED=1`, `DATALAB_ANCHOR=냉장고`
4. **워크플로우 검증**: `gh workflow run daily-collect.yml` → 로그 확인(차단 여부·수요갱신)
5. **배치 시간 실측 (스펙 §8)**: 실행 소요·키워드당 호출 시간 기록 후 design.md §8 표 갱신
6. **차단 시**: cron-job.org에서 `/collect` POST + Bearer + `{"trigger":"schedule"}` (45초 예산, 며칠에 걸쳐 순환)
7. **PG 통합 테스트 실행**: `DATABASE_URL=... pytest tests/test_db_postgres.py -v` (로컬/CI Postgres에서 잠금 경합·재연결 검증)
8. **브라우저 e2e(선택)**: `pip install playwright && playwright install chromium` 후 서버 기동 상태에서 `python tests/e2e_dashboard.py`
