# db.py
import os
import sqlite3

import config as config_mod

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
    active INTEGER NOT NULL DEFAULT 1,
    performance_boost REAL NOT NULL DEFAULT 0
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
    shop_click_idx REAL,
    ai_cite_idx REAL,
    demand_growth REAL,
    UNIQUE(keyword_id, day)
);
CREATE TABLE IF NOT EXISTS top_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword_id INTEGER NOT NULL REFERENCES keywords(id),
    day TEXT NOT NULL,
    post_date TEXT NOT NULL
);
-- v17.3: 스냅샷 INSERT/DELETE·보존 DELETE (30일 보유분 풀스캔 방지)
CREATE INDEX IF NOT EXISTS idx_top_results_keyword_day
    ON top_results(keyword_id, day);
CREATE TABLE IF NOT EXISTS collection_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at TEXT NOT NULL,
    keyword TEXT NOT NULL,
    action TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT ''
);
-- v17.3: 보존 DELETE·조회 인덱스 (180일 보유분 풀스캔 방지)
CREATE INDEX IF NOT EXISTS idx_collection_log_run_at
    ON collection_log(run_at);
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
-- v7: 콘텐츠 자동화 — 상위글 골격 분석 결과 (질문형 소제목·비교·수치 구조 JSON)
CREATE TABLE IF NOT EXISTS outlines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword_id INTEGER NOT NULL REFERENCES keywords(id),
    day TEXT NOT NULL,
    structure TEXT NOT NULL DEFAULT '{}',
    source TEXT NOT NULL DEFAULT 'naver_blog_search',
    UNIQUE(keyword_id, day)
);
-- v7: 콘텐츠 자동화 — 생성된 글 초안 (제목·첫문단·본문·이미지 URL)
CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword_id INTEGER NOT NULL REFERENCES keywords(id),
    title TEXT NOT NULL,
    first_paragraph TEXT NOT NULL,
    body TEXT NOT NULL,
    image_url TEXT NOT NULL DEFAULT '',
    section_images TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT '',
    published_at TEXT NOT NULL DEFAULT '',
    performance_score REAL,
    performance_note TEXT NOT NULL DEFAULT '',
    published_url TEXT NOT NULL DEFAULT '',
    adpost_revenue REAL,
    adpost_impressions INTEGER,
    adpost_clicks INTEGER,
    refresh_of INTEGER,
    refreshed_at TEXT NOT NULL DEFAULT '',
    platform TEXT NOT NULL DEFAULT 'naver',
    thumbnail_ideas TEXT NOT NULL DEFAULT '',
    product_block TEXT NOT NULL DEFAULT ''
);
-- v17.3: 게시 URL·제목 매칭(AdPost 임포트)과 키워드별 초안 조회 인덱스
CREATE INDEX IF NOT EXISTS idx_drafts_keyword ON drafts(keyword_id);
CREATE INDEX IF NOT EXISTS idx_drafts_published_url ON drafts(published_url);
CREATE INDEX IF NOT EXISTS idx_drafts_title ON drafts(title);
-- v20: percentiles/datalab_targets MAX(day) 커버링 — UNIQUE만으론 풀스캔
CREATE INDEX IF NOT EXISTS idx_daily_stats_keyword_day ON daily_stats(keyword_id, day);
-- v18: 실측 CPC/RPM — AdPost 리포트 집계로 priority CPC 항을 보정 (고정 등급의
-- 실측 교정). 표본 부족(클릭 0)은 measured_tier NULL → SQL이 정적 등급 폴백.
CREATE TABLE IF NOT EXISTS category_cpc_stats (
    category TEXT PRIMARY KEY,
    posts INTEGER NOT NULL DEFAULT 0,
    revenue REAL NOT NULL DEFAULT 0,
    impressions INTEGER NOT NULL DEFAULT 0,
    clicks INTEGER NOT NULL DEFAULT 0,
    cpc REAL,
    rpm REAL,
    measured_tier REAL,
    updated_at TEXT NOT NULL DEFAULT ''
);
-- v22.2(3.3): 운세 콘텐츠 생성 멱등 — (기준일, 타입) 당 1건. 발행 대기 큐 겸용.
CREATE TABLE IF NOT EXISTS fortune_generations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ref_date TEXT NOT NULL,
    content_type TEXT NOT NULL,
    content TEXT NOT NULL,
    grounding TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'generated',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT '',
    UNIQUE(ref_date, content_type)
);
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
    active INTEGER NOT NULL DEFAULT 1,
    performance_boost DOUBLE PRECISION NOT NULL DEFAULT 0
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
    shop_click_idx DOUBLE PRECISION,
    ai_cite_idx DOUBLE PRECISION,
    demand_growth DOUBLE PRECISION,
    UNIQUE(keyword_id, day)
);
CREATE TABLE IF NOT EXISTS top_results (
    id SERIAL PRIMARY KEY,
    keyword_id INTEGER NOT NULL REFERENCES keywords(id),
    day TEXT NOT NULL,
    post_date TEXT NOT NULL
);
-- v17.3: 스냅샷 INSERT/DELETE·보존 DELETE (30일 보유분 풀스캔 방지)
CREATE INDEX IF NOT EXISTS idx_top_results_keyword_day
    ON top_results(keyword_id, day);
CREATE TABLE IF NOT EXISTS collection_log (
    id SERIAL PRIMARY KEY,
    run_at TEXT NOT NULL,
    keyword TEXT NOT NULL,
    action TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT ''
);
-- v17.3: 보존 DELETE·조회 인덱스 (180일 보유분 풀스캔 방지)
CREATE INDEX IF NOT EXISTS idx_collection_log_run_at
    ON collection_log(run_at);
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
-- v7: 콘텐츠 자동화 — 상위글 골격 분석 결과 (질문형 소제목·비교·수치 구조 JSON)
CREATE TABLE IF NOT EXISTS outlines (
    id SERIAL PRIMARY KEY,
    keyword_id INTEGER NOT NULL REFERENCES keywords(id),
    day TEXT NOT NULL,
    structure TEXT NOT NULL DEFAULT '{}',
    source TEXT NOT NULL DEFAULT 'naver_blog_search',
    UNIQUE(keyword_id, day)
);
-- v7: 콘텐츠 자동화 — 생성된 글 초안 (제목·첫문단·본문·이미지 URL)
CREATE TABLE IF NOT EXISTS drafts (
    id SERIAL PRIMARY KEY,
    keyword_id INTEGER NOT NULL REFERENCES keywords(id),
    title TEXT NOT NULL,
    first_paragraph TEXT NOT NULL,
    body TEXT NOT NULL,
    image_url TEXT NOT NULL DEFAULT '',
    section_images TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT '',
    published_at TEXT NOT NULL DEFAULT '',
    performance_score DOUBLE PRECISION,
    performance_note TEXT NOT NULL DEFAULT '',
    published_url TEXT NOT NULL DEFAULT '',
    adpost_revenue DOUBLE PRECISION,
    adpost_impressions INTEGER,
    adpost_clicks INTEGER,
    refresh_of INTEGER,
    refreshed_at TEXT NOT NULL DEFAULT '',
    platform TEXT NOT NULL DEFAULT 'naver',
    thumbnail_ideas TEXT NOT NULL DEFAULT '',
    product_block TEXT NOT NULL DEFAULT ''
);
-- v17.3: 게시 URL·제목 매칭(AdPost 임포트)과 키워드별 초안 조회 인덱스
CREATE INDEX IF NOT EXISTS idx_drafts_keyword ON drafts(keyword_id);
CREATE INDEX IF NOT EXISTS idx_drafts_published_url ON drafts(published_url);
CREATE INDEX IF NOT EXISTS idx_drafts_title ON drafts(title);
-- v20: percentiles/datalab_targets MAX(day) 커버링 — UNIQUE만으론 풀스캔
CREATE INDEX IF NOT EXISTS idx_daily_stats_keyword_day ON daily_stats(keyword_id, day);
-- v18: 실측 CPC/RPM — AdPost 리포트 집계로 priority CPC 항을 보정 (고정 등급의
-- 실측 교정). 표본 부족(클릭 0)은 measured_tier NULL → SQL이 정적 등급 폴백.
CREATE TABLE IF NOT EXISTS category_cpc_stats (
    category TEXT PRIMARY KEY,
    posts INTEGER NOT NULL DEFAULT 0,
    revenue DOUBLE PRECISION NOT NULL DEFAULT 0,
    impressions INTEGER NOT NULL DEFAULT 0,
    clicks INTEGER NOT NULL DEFAULT 0,
    cpc DOUBLE PRECISION,
    rpm DOUBLE PRECISION,
    measured_tier DOUBLE PRECISION,
    updated_at TEXT NOT NULL DEFAULT ''
);
-- v22.2(3.3): 운세 콘텐츠 생성 멱등 — (기준일, 타입) 당 1건. 발행 대기 큐 겸용.
CREATE TABLE IF NOT EXISTS fortune_generations (
    id SERIAL PRIMARY KEY,
    ref_date TEXT NOT NULL,
    content_type TEXT NOT NULL,
    content TEXT NOT NULL,
    grounding TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'generated',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT '',
    UNIQUE(ref_date, content_type)
);
""",
}

_STATS_COLUMNS = (
    "total_sim", "total_date", "fresh_ratio", "shop_total", "shop_avg_price",
    "shop_category", "shop_error", "growth", "opportunity", "commercial",
    "demand_idx", "shop_click_idx", "ai_cite_idx", "demand_growth",
)


class Database:
    # v6: priority = 0.35×ai_cite_idx + 0.35×demand_idx(≤1) + 0.30×CPC등급(카테고리)
    # v9: config.DEFAULT_CPC_TIERS와 정합 — 기존 4단계(ELSE 0.5)는 여행/맛집(0.4),
    #     반려동물/일상/취미(0.3)를 0.5로 과평가해 priority 왜곡 (실증: 반려동물 17개)
    # v12: v9에서 demand_idx가 앵커 대비 상대비율(실측 0~0.01)로 바뀌면서 기존 ≤1 클램프는
    #     demand 항을 사실상 무력화(최대 기여 ~0.35점) — 0.01(실측 상한) 기준 정규화로
    #     0~1 복원. 상한 초과는 1.0으로 클램프 (scoring.v6_priority와 동일 값 유지).
    # v14: growth 몫(15)을 수요에서 분리 — 30×AI인용 + 25×수요 + 15×성장 + 30×CPC.
    #     growth_norm = clamp(demand_growth / 0.05, -0.5, 1.0), NULL은 0 (scoring.growth_norm
    #     동일 수식 — GROWTH_NORM_MAX 0.05 재사용). 성공 기준 ② 상승 키워드 상단 노출.
    # SORT_COLUMNS에 쓰이는 priority 표현식 — SELECT에도 동일 alias로 노출 (server 조회용)
    CPC_TIER_SQL = (
        "CASE WHEN k.category IN ('보험','금융','재테크') THEN 1.0 "
        "WHEN k.category IN ('부동산','법률','건강','의료') THEN 0.9 "
        "WHEN k.category IN ('IT','디지털','교육','자격증') THEN 0.8 "
        "WHEN k.category IN ('인테리어','패션','뷰티','요리') THEN 0.5 "
        "WHEN k.category IN ('여행','맛집') THEN 0.4 "
        "WHEN k.category IN ('반려동물','일상','취미') THEN 0.3 "
        "ELSE 0.5 END"
    )
    # v18: 실측 CPC 보정 — category_cpc_stats(AdPost 리포트 집계)가 실측 tier를
    # 갖고 있으면 정적 등급 대신 사용. v20: 베이지안 스무딩(prior=3)으로 표본
    # 1~2건도 반영 — posts≥3이면 실측 비중↑, 미만이면 정적 쪽으로 수렴. NULL 폴백.
    EFFECTIVE_CPC_SQL = (
        "CASE WHEN EXISTS (SELECT 1 FROM category_cpc_stats cs "
        "WHERE cs.category = k.category AND cs.measured_tier IS NOT NULL) "
        f"THEN (SELECT (3.0 * ({CPC_TIER_SQL}) + cs.posts * cs.measured_tier) "
        "/ (3.0 + cs.posts) FROM category_cpc_stats cs "
        "WHERE cs.category = k.category AND cs.measured_tier IS NOT NULL) "
        f"ELSE {CPC_TIER_SQL} END"
    )
    # v20: 0.05 포화로 변별력 상실 — scoring.GROWTH_NORM_MAX(0.15)와 정합.
    GROWTH_NORM_SQL = (
        "CASE WHEN ds.demand_growth IS NULL THEN 0.0 "
        "WHEN ds.demand_growth / 0.15 >= 1.0 THEN 1.0 "
        "WHEN ds.demand_growth / 0.15 <= -0.5 THEN -0.5 "
        "ELSE ds.demand_growth / 0.15 END"
    )
    # v20: 0.01은 앵커 비수기 포화로 변별력 상실 — 0.02로 완화 (scoring.DEMAND_NORM_MAX와 정합).
    PRIORITY_SQL = (
        # v15: ai_cite도 [0,1] 클램프 — scoring.v6_priority의 max/min과 동일 수식.
        # (ai_cite_idx는 구조상 ≤1이지만 오염 데이터에도 정합 유지)
        "ROUND(CAST(30.0 * CASE WHEN COALESCE(ds.ai_cite_idx, 0) >= 1.0 THEN 1.0 "
        "WHEN COALESCE(ds.ai_cite_idx, 0) <= 0.0 THEN 0.0 "
        "ELSE COALESCE(ds.ai_cite_idx, 0) END "
        "+ 25.0 * CASE WHEN COALESCE(ds.demand_idx, 0) >= 0.02 THEN 1.0 "
        "WHEN COALESCE(ds.demand_idx, 0) <= 0.0 THEN 0.0 "
        "ELSE COALESCE(ds.demand_idx, 0) / 0.02 END "
        f"+ 15.0 * {GROWTH_NORM_SQL} "
        f"+ 30.0 * {EFFECTIVE_CPC_SQL} "
        "+ COALESCE(k.performance_boost, 0) AS NUMERIC), 1)"
    )
    # v14: performance_boost 누적 클램프 — 다수 초안 피드백의 무한 누적/상쇄 왜곡 방지
    BOOST_CLAMP_SQL = {
        "sqlite": "MAX(-20.0, MIN(20.0, COALESCE(performance_boost, 0) + ?))",
        "postgres": "GREATEST(-20.0, LEAST(20.0, COALESCE(performance_boost, 0) + %s))",
    }
    # v14: 백분위 자가보정 임계가 지원하는 지표 (percentiles)
    PERCENTILE_METRICS = {
        "ai_cite_idx": "ds.ai_cite_idx",
        "demand_idx": "ds.demand_idx",
        "opportunity": "ds.opportunity",
        "demand_growth": "ds.demand_growth",
    }
    PERCENTILE_QUANTILES = (0.25, 0.5, 0.75, 0.9)
    SORT_COLUMNS = {
        "opportunity": "ds.opportunity",
        "commercial": "ds.commercial",
        "click": "ds.shop_click_idx",  # v4: 쇼핑 클릭 지수 (쇼핑 검색 API 종료 대체)
        "demand": "ds.demand_idx",
        "demand_growth": "ds.demand_growth",  # v9: 데이터랩 시계열 기울기
        "growth": "ds.growth",
        "ai_cite": "ds.ai_cite_idx",   # v6: AI 인용 가능성
        "priority": PRIORITY_SQL,      # v6: 종합 우선순위
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
                self._migrate()
                return
            except CONNECTION_ERRORS:
                if attempt == 1:
                    raise
                self._connect()

    # v15: 마이그레이션 컬럼 목록 — (테이블, 컬럼, sqlite 선언, pg 선언).
    # 전부 개별 가드: 마이그레이션 중간 충돌로 일부만 추가된 DB에서도 다음 init이
    # 누락분만 마저 추가 (기존 묶음 ALTER는 duplicate column 한 건에 init 전체 실패).
    # shop_click_idx는 기존 마이그레이션에서 누락돼 구버전 DB가 insert 시 깨지던 것 보완.
    _MIGRATE_COLUMNS = (
        ("daily_stats", "ai_cite_idx", "REAL", "DOUBLE PRECISION"),
        ("daily_stats", "demand_growth", "REAL", "DOUBLE PRECISION"),
        ("daily_stats", "shop_click_idx", "REAL", "DOUBLE PRECISION"),
        ("drafts", "section_images", "TEXT NOT NULL DEFAULT ''",
         "TEXT NOT NULL DEFAULT ''"),
        ("drafts", "published_at", "TEXT NOT NULL DEFAULT ''",
         "TEXT NOT NULL DEFAULT ''"),
        ("drafts", "performance_score", "REAL", "DOUBLE PRECISION"),
        ("drafts", "performance_note", "TEXT NOT NULL DEFAULT ''",
         "TEXT NOT NULL DEFAULT ''"),
        ("keywords", "performance_boost", "REAL NOT NULL DEFAULT 0",
         "DOUBLE PRECISION NOT NULL DEFAULT 0"),
        # v17: 게시 파이프라인·AdPost 피드백 — 게시 URL 매칭 + 수익 지표 원본 저장
        ("drafts", "published_url", "TEXT NOT NULL DEFAULT ''",
         "TEXT NOT NULL DEFAULT ''"),
        ("drafts", "adpost_revenue", "REAL", "DOUBLE PRECISION"),
        ("drafts", "adpost_impressions", "INTEGER", "INTEGER"),
        ("drafts", "adpost_clicks", "INTEGER", "INTEGER"),
        # v17.2: 네이버 블로그 태그 — JSON 배열 문자열 (section_images와 동일 관례)
        ("drafts", "tags", "TEXT NOT NULL DEFAULT ''",
         "TEXT NOT NULL DEFAULT ''"),
        # v18: 저성과 글 리프레시 — 원본 초안 참조 + 리프레시 완료 시각
        ("drafts", "refresh_of", "INTEGER", "INTEGER"),
        ("drafts", "refreshed_at", "TEXT NOT NULL DEFAULT ''",
         "TEXT NOT NULL DEFAULT ''"),
        # v19: 멀티 플랫폼 — 네이버/티스토리/애드센스/브랜드 + 썸네일 아이디어
        ("drafts", "platform", "TEXT NOT NULL DEFAULT 'naver'",
         "TEXT NOT NULL DEFAULT 'naver'"),
        ("drafts", "thumbnail_ideas", "TEXT NOT NULL DEFAULT ''",
         "TEXT NOT NULL DEFAULT ''"),
        # v21(B.3): 네이버쇼핑커넥트 상품 블록 — JSON 배열 문자열 (B.4가 렌더링)
        ("drafts", "product_block", "TEXT NOT NULL DEFAULT ''",
         "TEXT NOT NULL DEFAULT ''"),
    )

    def _migrate(self):
        # v6: 기존 DB(스키마 변경 전 생성)에 신규 컬럼 추가 — CREATE TABLE IF NOT EXISTS는
        # 이미 존재하는 테이블에는 컬럼을 추가하지 않으므로 명시적 ALTER 필요.
        # (SQLite: PRAGMA 검사, Postgres: ADD COLUMN IF NOT EXISTS 네이티브)
        for table, col, sqlite_decl, pg_decl in self._MIGRATE_COLUMNS:
            if self.dialect == "postgres":
                self._q(
                    None,
                    f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {pg_decl}",
                    (),
                )
            else:
                rows = self._qd(
                    f"SELECT name FROM pragma_table_info('{table}') "
                    f"WHERE name = '{col}'",
                    (), fetch=True,
                )
                if not rows:
                    self._qd(
                        f"ALTER TABLE {table} ADD COLUMN {col} {sqlite_decl}", ())

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

    def set_performance_boost(self, keyword_id, delta):
        # v10 [6]: 게시 성과 피드백 보너스 — priority 상향/하향 (은퇴·우선순위 보정)
        # v14: 누적값은 [-20, 20] 클램프 — 한 키워드에 초안이 여러 개일 때 보너스가
        # 무한 누적(또는 상쇄)되어 priority를 왜곡하던 문제 차단
        self._q(
            "UPDATE keywords SET performance_boost = "
            + self.BOOST_CLAMP_SQL["sqlite"] + " WHERE id = ?",
            "UPDATE keywords SET performance_boost = "
            + self.BOOST_CLAMP_SQL["postgres"] + " WHERE id = %s",
            (delta, keyword_id),
        )

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

    def count_active_by_category(self):
        """v21(A.3): 활성 키워드 카테고리 분포 — 발굴 비중 가드의 입력."""
        rows = self._qd(
            "SELECT category, COUNT(*) AS c FROM keywords "
            "WHERE active = 1 AND category != '' GROUP BY category",
            (), fetch=True)
        return {r["category"]: r["c"] for r in rows}

    def all_keyword_names(self):
        rows = self._qd("SELECT keyword FROM keywords", (), fetch=True)
        return {r["keyword"] for r in rows}

    def percentiles(self, metric):
        """v14 §3: 활성 키워드 최신 스냅샷 기준 백분위 — 자가보정 임계의 단일 소스.
        반환: (표본 수, {분위: 값}) — 표본 부족·P50=0일 때의 폴백은 호출 측 판단.
        지표별 최신 스냅샷(_KEYWORD_BASE)의 NULL 제외 정렬값을 읽어 오프셋
        (ROUND(분위 × (n-1)))으로 도출 — SQL 함수 없이 양 백엔드 동일 결과.
        (키워드 ≤ 500이라 요청마다 계산해도 비용 무시 가능 — 스펙 §3.3)"""
        col = self.PERCENTILE_METRICS.get(metric)
        if col is None:
            raise ValueError(f"unknown percentile metric: {metric}")
        sql = f"""
SELECT {col} AS v {self._KEYWORD_BASE}
WHERE k.active = 1 AND {col} IS NOT NULL
ORDER BY 1"""
        vals = [r["v"] for r in self._qd(sql, (), fetch=True)]
        n = len(vals)
        if not n:
            return 0, {}
        # half-up 오프셋 — Python round()의 banker's rounding는 SQL ROUND와
        # .5 경계에서 어긋남 (SQLite ROUND는 0에서 먼 방향)
        return n, {q: vals[int(q * (n - 1) + 0.5)] for q in self.PERCENTILE_QUANTILES}

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
            stats.get("shop_click_idx"), stats.get("ai_cite_idx"),
            stats.get("demand_growth"),
        )
        cols = ", ".join(("keyword_id", "day") + _STATS_COLUMNS)
        placeholders = ", ".join("?" * len(values))
        pg_placeholders = ", ".join(["%s"] * len(values))
        self._q(
            f"INSERT OR REPLACE INTO daily_stats ({cols}) VALUES ({placeholders})",
            f"INSERT INTO daily_stats ({cols}) VALUES ({pg_placeholders}) "
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

    def update_demand_growth(self, keyword_id, day, demand_growth):
        # v9: 데이터랩 30일 시계열 기울기 — 최근 7일 vs 이전 23일 평균 ratio 변화율
        self._qd(
            "UPDATE daily_stats SET demand_growth = ? WHERE keyword_id = ? AND day = ?",
            (demand_growth, keyword_id, day),
        )

    def update_shop_click_idx(self, keyword_id, day, shop_click_idx):
        # v4: 쇼핑 클릭 지수 (쇼핑인사이트 앵커 정규화)
        self._qd(
            "UPDATE daily_stats SET shop_click_idx = ? WHERE keyword_id = ? AND day = ?",
            (shop_click_idx, keyword_id, day),
        )

    def top_by_opportunity(self, day, limit):
        sql = """
SELECT k.id, k.keyword, k.category FROM daily_stats ds
JOIN keywords k ON k.id = ds.keyword_id
WHERE ds.day = ? AND ds.opportunity IS NOT NULL AND k.active = 1
ORDER BY ds.opportunity DESC LIMIT ?"""
        return self._qd(sql, (day, limit), fetch=True)

    def datalab_targets(self, day, priority_n, rotate_n):
        """v17: 데이터랩(수요·쇼핑클릭) 갱신 대상 — 고정 슬롯 + 순환 슬롯.
        기존은 기회점수 상위 200개만 갱신해 슬롯 밖 키워드는 수요·클릭 신호가
        영구 NULL(우선순위 왜곡 + 은퇴 판정 사각지대). 이제 상위 priority_n은
        매일 고정 갱신하고, 나머지 rotate_n은 수요 갱신이 가장 오래된 키워드부터
        채워 활성 전체가 며칠 주기로 골고루 갱신된다 (주간 캐시 효과 자동 발생).
        반환: [{'id','keyword'}] — 고정 슬롯 우선, 순환 슬롯은 중복 제외."""
        priority_rows = self.top_by_opportunity(day, priority_n)
        if rotate_n <= 0:
            return priority_rows
        seen = {r["id"] for r in priority_rows}
        # v20: 기존 EXISTS(day=today)는 partial로 오늘 스냅샷을 못 받은 키워드를
        # 수요/쇼핑 갱신 대상에서 영구 배제해 사각지대가 누적됐다.
        # 최근 7일 스냅샷 존재 여부로 완화해 partial 반복 시에도 커버리지를 유지한다.
        # (cutoff는 Python에서 계산 — date(?, '-7 days')는 Postgres 비호환)
        from datetime import date as date_mod, timedelta
        cutoff_day = (date_mod.fromisoformat(day) - timedelta(days=7)).isoformat()
        # NULLS FIRST를 CASE로 표현 (SQLite/Postgres 공통)
        sql = """
SELECT k.id, k.keyword, k.category FROM keywords k
WHERE k.active = 1
  AND EXISTS (SELECT 1 FROM daily_stats ds
              WHERE ds.keyword_id = k.id AND ds.day >= ?)
ORDER BY CASE WHEN (SELECT MAX(day) FROM daily_stats d2
                     WHERE d2.keyword_id = k.id
                       AND d2.demand_idx IS NOT NULL) IS NULL
               THEN 0 ELSE 1 END,
          (SELECT MAX(day) FROM daily_stats d2
           WHERE d2.keyword_id = k.id AND d2.demand_idx IS NOT NULL) ASC,
          k.id
LIMIT ?"""
        rows = self._qd(
            sql, (cutoff_day, rotate_n + len(seen)), fetch=True)
        rotate_rows = [r for r in rows if r["id"] not in seen][:rotate_n]
        return priority_rows + rotate_rows

    # ---------- 상위글 발행일 ----------

    def insert_top_results(self, keyword_id, day, post_dates):
        self._qd(
            "DELETE FROM top_results WHERE keyword_id = ? AND day = ?", (keyword_id, day)
        )
        rows = [(keyword_id, day, pd) for pd in post_dates]
        if not rows:
            return
        if self.dialect == "postgres":
            for attempt in (0, 1):
                try:
                    with self.conn.cursor() as cur:
                        cur.executemany(
                            "INSERT INTO top_results (keyword_id, day, post_date) "
                            "VALUES (%s, %s, %s)",
                            rows,
                        )
                        self.conn.commit()
                    break
                except CONNECTION_ERRORS:
                    if attempt == 1:
                        raise
                    self._connect()
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

    def finish_run(self, run_id, status, finished_iso, result, note=""):
        # v3: status는 호출 측이 done/partial/failed로 구분해 전달 (note의 partial 표기 제거)
        # v14: note는 호출 측이 자유롭게 채움 (거부율 지표 JSON — 스펙 §1.2/§5)
        self._qd(
            "UPDATE collection_runs SET status = ?, finished_at = ?, new_keywords = ?, "
            "snapshotted = ?, errors = ?, note = ? WHERE id = ?",
            (
                status, finished_iso,
                result.get("new_keywords", 0), result.get("snapshotted", 0),
                len(result.get("errors", [])),
                note, run_id,
            ),
        )

    def get_last_runs(self, limit=5):
        return self._qd(
            "SELECT * FROM collection_runs ORDER BY id DESC LIMIT ?", (limit,), fetch=True
        )

    # ---------- 수명주기 ----------

    def find_retire_candidates(self, first_seen_before, since_day, opp_lt, click_lt):
        """발견 오래됨 + 최근 스냅샷 존재 + 최근 성과 전부 저조 → 은퇴 후보.
        v4: 쇼핑 검색 API 종료로 상업성은 항상 NULL이므로 은퇴는 기회점수 + 쇼핑 클릭 지수로 판정.
        최근 7일 창의 스냅샷 중 하나라도 기회점수가 NULL이면 보호한다
        (미조회 키워드를 0점 취급해 오은퇴시키지 않음 — 스펙 §4.6).
        NULL은 수집 실패일 수 있으므로 '저성과' 판정의 근거가 될 수 없다.
        v11: 게시 성과 피드백 보너스(performance_boost ≥ 10) 키워드는 은퇴 보호 —
        실제로 유입·체류 성과가 확인된 키워드는 지표가 일시적으로 낮아도 유지.
        v17: 쇼핑클릭 사각지대 수정 — 클릭 데이터는 상위 200 슬롯만 수집되므로
        슬롯 밖·분야 미매칭 키워드는 클릭 이력이 영영 생기지 않는다. 기존 EXISTS는
        클릭 비NULL을 요구해 이런 키워드가 기회점수와 무관하게 영구 은퇴 불가 →
        500 상한 도달 시 BFS 발굴이 영구 정지했음. 이제 클릭 이력 유무로 구분:
        - 클릭 이력 있음: 기회+클릭 둘 다 저조해야 은퇴. 최근 클릭 NULL은 수집
          공백 의심이라 보호 (§4.6 유지)
        - 클릭 이력 없음(구조적 부재): 기회점수 단독 판정 (부재는 수집 실패가 아님)
        clickless 열은 은퇴 사유 로그 구분용 (collect.retire가 참조)."""
        has_clicks = ("EXISTS (SELECT 1 FROM daily_stats h "
                      "WHERE h.keyword_id = k.id AND h.shop_click_idx IS NOT NULL)")
        # v20: 최근 7일 스냅샷이 3개 미만이면 변동성으로 과은퇴 — COUNT(*) >= 3 가드로 보호.
        sql = f"""
SELECT k.id, k.keyword,
       CASE WHEN NOT {has_clicks} THEN 1 ELSE 0 END AS clickless
FROM keywords k
WHERE k.active = 1 AND k.first_seen <= ?
  AND COALESCE(k.performance_boost, 0) < 10
  AND (SELECT COUNT(*) FROM daily_stats ds
       WHERE ds.keyword_id = k.id AND ds.day >= ?) >= 3
  AND EXISTS (
    SELECT 1 FROM daily_stats ds WHERE ds.keyword_id = k.id AND ds.day >= ?
      AND ds.opportunity IS NOT NULL
      AND (ds.shop_click_idx IS NOT NULL OR NOT {has_clicks}))
  AND NOT EXISTS (
    SELECT 1 FROM daily_stats ds WHERE ds.keyword_id = k.id AND ds.day >= ?
      AND (ds.opportunity IS NULL OR ds.opportunity >= ?
           OR ds.shop_click_idx >= ?
           OR (ds.shop_click_idx IS NULL AND {has_clicks})))
ORDER BY k.id"""
        return self._qd(
            sql,
            (first_seen_before, since_day, since_day, since_day, opp_lt, click_lt),
            fetch=True)

    def cleanup(self, stats_before_day, top_before_day, log_before_ts):
        self._qd("DELETE FROM daily_stats WHERE day < ?", (stats_before_day,))
        self._qd("DELETE FROM top_results WHERE day < ?", (top_before_day,))
        self._qd("DELETE FROM collection_log WHERE run_at < ?", (log_before_ts,))

    # ---------- 대시보드 목록 (단일 쿼리 + 페이징) ----------

    @staticmethod
    def _escape_like(s):
        # v14: 검색어의 LIKE 와일드카드(% _)를 리터럴로 — 미이스케이프 시
        # '50%' 검색이 '50'으로 시작하는 모든 키워드에 매치되던 문제
        return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    def _keyword_where(self, category, commercial_min, q, discovered_since, active,
                       opportunity_min=0.0, demand_min=0.0, demand_max=None,
                       click_min=0.0, ai_cite_min=0.0, growth_min=None):
        where, params = [], []
        if active is not None:
            where.append("k.active = ?")
            params.append(active)
        if category:
            where.append("(ds.shop_category LIKE ? OR k.category = ?)")
            params += [category + "%", category]
        if q:
            where.append("k.keyword LIKE ? ESCAPE '\\'")
            params.append(f"%{self._escape_like(q)}%")
        if discovered_since:
            where.append("k.first_seen >= ?")
            params.append(discovered_since)
        # v17.2: 점수(프리셋) 필터 — 제외 목록 포함(active=None) 경로는 복원·관리
        # 용도라 제외 키워드는 프리셋 점수와 무관하게 보여야 함. 기존은 기본
        # 프리셋(AI픽) 임계에 못 미치는 제외 키워드가 '제외 목록 포함'을 켜도
        # 계속 숨겨져 사용자가 복원조차 못 하던 문제.
        score, score_params = [], []
        if commercial_min:
            score.append("ds.commercial >= ?")
            score_params.append(commercial_min)
        if opportunity_min:  # v3: 유망 프리셋용
            score.append("ds.opportunity >= ?")
            score_params.append(opportunity_min)
        if demand_min:       # v3: 유망 프리셋용
            score.append("ds.demand_idx >= ?")
            score_params.append(demand_min)
        if demand_max is not None:  # v20: '곧 뜰' 프리셋 — 수요 아직 P50 미만(선점)
            score.append("ds.demand_idx <= ?")
            score_params.append(demand_max)
        if click_min:        # v4: 쇼핑 클릭 지수 최소 (유망 프리셋·필터)
            score.append("ds.shop_click_idx >= ?")
            score_params.append(click_min)
        if ai_cite_min:      # v6: AI 인용 가능성 최소 (AI 유망 프리셋)
            score.append("ds.ai_cite_idx >= ?")
            score_params.append(ai_cite_min)
        if growth_min is not None:  # v14: 상승 프리셋 — 성장 기울기 최소 (NULL 자동 제외)
            score.append("ds.demand_growth >= ?")
            score_params.append(growth_min)
        if score:
            if active is None:
                where.append(f"(k.active = 0 OR ({' AND '.join(score)}))")
                params += score_params
            else:
                where += score
                params += score_params
        return (" WHERE " + " AND ".join(where)) if where else "", params

    def query_keywords(self, sort="opportunity", sort_dir="desc", category="",
                       commercial_min=0.0, q="", discovered_since="", active=1,
                       opportunity_min=0.0, demand_min=0.0, demand_max=None,
                       click_min=0.0, ai_cite_min=0.0, growth_min=None,
                       limit=50, offset=0):
        col = self.SORT_COLUMNS.get(sort, "ds.opportunity")
        order = "ASC" if sort_dir == "asc" else "DESC"  # v3: 정렬 토글 (UX §6)
        where_sql, params = self._keyword_where(
            category, commercial_min, q, discovered_since, active,
            opportunity_min, demand_min, demand_max, click_min, ai_cite_min,
            growth_min)
        sql = f"""
SELECT k.id, k.keyword, k.active, k.first_seen, ds.day,
       COALESCE(NULLIF(ds.shop_category, ''), k.category) AS category,
       ds.opportunity, ds.commercial, ds.growth, ds.demand_idx, ds.shop_click_idx,
       ds.fresh_ratio, ds.total_sim, ds.shop_total, ds.ai_cite_idx,
       ds.demand_growth,
       {self.PRIORITY_SQL} AS priority,
       (SELECT COUNT(*) FROM daily_stats h WHERE h.keyword_id = k.id) AS days
{self._KEYWORD_BASE}{where_sql}
ORDER BY CASE WHEN {col} IS NULL THEN 1 ELSE 0 END, {col} {order}, k.first_seen, k.id
LIMIT ? OFFSET ?"""
        return self._qd(sql, tuple(params + [limit, offset]), fetch=True)

    def count_keywords(self, category="", commercial_min=0.0, q="",
                       discovered_since="", active=1,
                       opportunity_min=0.0, demand_min=0.0, demand_max=None,
                       click_min=0.0, ai_cite_min=0.0, growth_min=None):
        where_sql, params = self._keyword_where(
            category, commercial_min, q, discovered_since, active,
            opportunity_min, demand_min, demand_max, click_min, ai_cite_min,
            growth_min)
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

    # ---------- v7: 상위글 골격 (outlines) ----------

    def upsert_outline(self, keyword_id, day, structure, source="naver_blog_search"):
        self._q(
            "INSERT INTO outlines (keyword_id, day, structure, source) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(keyword_id, day) DO UPDATE SET structure = excluded.structure, "
            "source = excluded.source",
            "INSERT INTO outlines (keyword_id, day, structure, source) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (keyword_id, day) DO UPDATE SET structure = EXCLUDED.structure, "
            "source = EXCLUDED.source",
            (keyword_id, day, structure, source),
        )

    def get_outline(self, keyword_id):
        rows = self._qd(
            "SELECT * FROM outlines WHERE keyword_id = ? ORDER BY day DESC, id DESC LIMIT 1",
            (keyword_id,), fetch=True,
        )
        return rows[0] if rows else None

    def list_outlines(self, keyword_id):
        return self._qd(
            "SELECT * FROM outlines WHERE keyword_id = ? ORDER BY day DESC, id DESC",
            (keyword_id,), fetch=True,
        )

    # ---------- v7: 글 초안 (drafts) ----------

    def insert_draft(self, keyword_id, title, first_paragraph, body,
                     image_url="", status="draft", created_at="", tags="",
                     refresh_of=None, platform="naver", thumbnail_ideas="",
                     product_block=""):
        # v15: id는 RETURNING/lastrowid로 취득 — 기존 'INSERT 후 ORDER BY id DESC
        # LIMIT 1 재읽기'는 다중 인스턴스에서 그 사이 끼어든 타 실행의 초안 ID를
        # 반환할 수 있는 레이스였음
        # v18: refresh_of — 리프레시 초안의 원본 초안 id
        # v19: platform — 생성 플랫폼 (네이버/티스토리/애드센스/브랜드), thumbnail_ideas JSON
        # v21(B.3): product_block — 쇼핑커넥트 상품 JSON (B.4가 렌더링)
        values = (keyword_id, title, first_paragraph, body, image_url, status,
                  created_at, created_at, tags, refresh_of, platform,
                  thumbnail_ideas, product_block)
        if self.dialect == "postgres":
            for attempt in (0, 1):
                try:
                    with self.conn.cursor() as cur:
                        cur.execute(
                            "INSERT INTO drafts (keyword_id, title, first_paragraph, "
                            "body, image_url, status, created_at, updated_at, tags, "
                            "refresh_of, platform, thumbnail_ideas, product_block) "
                            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                            "RETURNING id",
                            values)
                        draft_id = cur.fetchone()["id"]
                        self.conn.commit()
                    return draft_id
                except CONNECTION_ERRORS:
                    if attempt == 1:
                        raise
                    self._connect()
        cur = self.conn.execute(
            "INSERT INTO drafts (keyword_id, title, first_paragraph, body, image_url, "
            "status, created_at, updated_at, tags, refresh_of, platform, "
            "thumbnail_ideas, product_block) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            values)
        self.conn.commit()
        return cur.lastrowid

    def get_draft(self, draft_id):
        rows = self._qd(
            "SELECT * FROM drafts WHERE id = ?", (draft_id,), fetch=True
        )
        return rows[0] if rows else None

    def update_draft_image(self, draft_id, image_url, updated_at=""):
        self._qd(
            "UPDATE drafts SET image_url = ?, updated_at = ? WHERE id = ?",
            (image_url, updated_at, draft_id),
        )

    def update_draft_section_images(self, draft_id, section_images_json, updated_at=""):
        # v10 [5]: 섹션 이미지 5~8장 (JSON 배열 문자열) — 체류·스크롤 증가
        self._qd(
            "UPDATE drafts SET section_images = ?, updated_at = ? WHERE id = ?",
            (section_images_json, updated_at, draft_id),
        )

    def record_draft_feedback(self, draft_id, keyword_id, published_at, score,
                              note, updated_at, boost_delta):
        # v10 [6]: 게시 후 성과 기록 — 서치어드바이저 수동 입력 기반.
        # score 0~100 (유입/체류 반영), note는 성과 메모.
        # v14: 초안 점수 갱신과 키워드 boost 가산을 단일 커밋으로 묶음 — 기존은
        # 점수 저장 후 boost 갱신 실패 시 재시도의 차액이 0이 되어 boost가 영구
        # 유실되는 틈이 있었음 (서버리스 중간 종료 리스크).
        for attempt in (0, 1):
            try:
                if self.dialect == "postgres":
                    with self.conn.cursor() as cur:
                        cur.execute(
                            "UPDATE drafts SET published_at = %s, performance_score = %s, "
                            "performance_note = %s, status = 'published', updated_at = %s "
                            "WHERE id = %s",
                            (published_at, score, note, updated_at, draft_id),
                        )
                        cur.execute(
                            "UPDATE keywords SET performance_boost = "
                            + self.BOOST_CLAMP_SQL["postgres"] + " WHERE id = %s",
                            (boost_delta, keyword_id),
                        )
                        self.conn.commit()
                else:
                    self.conn.execute(
                        "UPDATE drafts SET published_at = ?, performance_score = ?, "
                        "performance_note = ?, status = 'published', updated_at = ? "
                        "WHERE id = ?",
                        (published_at, score, note, updated_at, draft_id),
                    )
                    self.conn.execute(
                        "UPDATE keywords SET performance_boost = "
                        + self.BOOST_CLAMP_SQL["sqlite"] + " WHERE id = ?",
                        (boost_delta, keyword_id),
                    )
                    self.conn.commit()
                return
            except CONNECTION_ERRORS:
                if attempt == 1:
                    raise
                self._connect()

    def list_drafts_by_keyword(self, keyword_id):
        return self._qd(
            "SELECT * FROM drafts WHERE keyword_id = ? ORDER BY id DESC",
            (keyword_id,), fetch=True,
        )

    # ---------- v17: 콘텐츠 배치 (컬렉트 잡 초안·이미지 생성) ----------

    def list_drafts_missing_images(self, limit):
        """대표 또는 섹션 이미지가 비어 있는 초안 (생성 순서대로).
        섹션 이미지는 본문에 H2가 있어야 생성 가능 — 조건에서 같이 거른다."""
        if self.dialect == "postgres":
            # psycopg2는 SQL의 '%'를 파라미터 마커로 해석하므로 LIKE 와일드카드는
            # '%%'로 이스케이프해야 한다 — 누락 시 LIMIT %s 외 % 포함 리터럴에서
            # IndexError(tuple index out of range)로 매 실행 content batch가 실패
            sql = """
SELECT * FROM drafts
WHERE image_url = ''
   OR (section_images = ''
       AND (body LIKE '## %%' OR body LIKE E'%%\\n## %%'))
ORDER BY id LIMIT %s"""
        else:
            sql = """
SELECT * FROM drafts
WHERE image_url = ''
   OR (section_images = ''
       AND (body LIKE '## %' OR body LIKE '%' || char(10) || '## %'))
ORDER BY id LIMIT ?"""
        return self._qd(sql, (limit,), fetch=True)

    def list_drafts_unpublished(self, limit, platform=""):
        """별도 블로그 미발행 초안 (published_url 비어 있음) — 발행 클라이언트 대상."""
        where = "WHERE published_url = '' AND body != ''"
        if platform:
            where += " AND platform = ?"
        sql = (f"SELECT * FROM drafts {where} ORDER BY id LIMIT ?")
        params = (platform,) if platform else ()
        return self._qd(sql, params + (limit,), fetch=True)

    def keywords_without_drafts(self, limit, upcoming_growth_min=0.02):
        """초안이 없는 활성 키워드를 우선순위 순으로 — 콘텐츠 배치 신규 대상.
        스냅샷 없는 키워드는 priority 산출이 불가하므로 뒤로 밀어낸다.
        v21(A.4): '곧 뜰'(upcoming) 키워드를 최우선 — 상승 반전(growth≥2%) &
        수요 P50 미만(선점) & 기회 P50 이상(경쟁 미포화). 경쟁이 붙기 전
        초안을 먼저 만들어 선점한다. (프리셋 임계는 백분위 자가보정과 정합)"""
        _, opp_pct = self.percentiles("opportunity")
        opp_p50 = opp_pct.get(0.5, 20.0)
        _, d_pct = self.percentiles("demand_idx")
        demand_p50 = d_pct.get(0.5, 0.001)
        sql = f"""
SELECT k.id, k.keyword, k.category, {self.PRIORITY_SQL} AS priority
{self._KEYWORD_BASE}
WHERE k.active = 1
  AND NOT EXISTS (SELECT 1 FROM drafts dr WHERE dr.keyword_id = k.id)
ORDER BY CASE WHEN ds.demand_growth IS NOT NULL AND ds.demand_growth >= ?
              AND ds.demand_idx IS NOT NULL AND ds.demand_idx < ?
              AND ds.opportunity IS NOT NULL AND ds.opportunity >= ?
         THEN 0 ELSE 1 END,
         CASE WHEN ds.day IS NULL THEN 1 ELSE 0 END, priority DESC, k.id
LIMIT ?"""
        return self._qd(
            sql, (upcoming_growth_min, demand_p50, opp_p50, limit), fetch=True)

    # ---------- v17: 게시·AdPost 피드백 ----------

    def set_draft_published_url(self, draft_id, url, updated_at=""):
        # v21.1: URL 등록 = 게시 확정 — status·published_at 갱신으로 게시 로그에
        # 즉시 노출 (기존 draft 유지 시 발행 이력에서 누락)
        self._qd(
            "UPDATE drafts SET published_url = ?, status = 'published', "
            "published_at = CASE WHEN published_at = '' THEN ? "
            "ELSE published_at END, updated_at = ? WHERE id = ?",
            (url, updated_at, updated_at, draft_id),
        )

    def mark_draft_refreshed(self, draft_id, refreshed_at):
        self._qd(
            "UPDATE drafts SET refreshed_at = ?, updated_at = ? WHERE id = ?",
            (refreshed_at, refreshed_at, draft_id),
        )

    def find_draft_by_published_url(self, url):
        rows = self._qd(
            "SELECT * FROM drafts WHERE published_url = ? ORDER BY id DESC LIMIT 1",
            (url,), fetch=True,
        )
        return rows[0] if rows else None

    def find_draft_by_title(self, title):
        rows = self._qd(
            "SELECT * FROM drafts WHERE title = ? ORDER BY id DESC LIMIT 1",
            (title,), fetch=True,
        )
        return rows[0] if rows else None

    def record_adpost_metrics(self, draft_id, keyword_id, revenue, impressions,
                              clicks, score, published_at, updated_at, boost_delta):
        """v17: AdPost 리포트 지표 저장 + 성과 점수·키워드 boost 반영 (단일 커밋).
        record_draft_feedback와 동일한 트랜잭션 패턴 — 중간 실패 후 재시도의
        차액 유실 차단. 미게시 상태였으면 published_at을 함께 기록."""
        for attempt in (0, 1):
            try:
                if self.dialect == "postgres":
                    with self.conn.cursor() as cur:
                        cur.execute(
                            "UPDATE drafts SET adpost_revenue = %s, adpost_impressions = %s, "
                            "adpost_clicks = %s, performance_score = %s, "
                            "published_at = CASE WHEN published_at = '' THEN %s "
                            "ELSE published_at END, updated_at = %s WHERE id = %s",
                            (revenue, impressions, clicks, score,
                             published_at, updated_at, draft_id),
                        )
                        cur.execute(
                            "UPDATE keywords SET performance_boost = "
                            + self.BOOST_CLAMP_SQL["postgres"] + " WHERE id = %s",
                            (boost_delta, keyword_id),
                        )
                        self.conn.commit()
                else:
                    self.conn.execute(
                        "UPDATE drafts SET adpost_revenue = ?, adpost_impressions = ?, "
                        "adpost_clicks = ?, performance_score = ?, "
                        "published_at = CASE WHEN published_at = '' THEN ? "
                        "ELSE published_at END, updated_at = ? WHERE id = ?",
                        (revenue, impressions, clicks, score,
                         published_at, updated_at, draft_id),
                    )
                    self.conn.execute(
                        "UPDATE keywords SET performance_boost = "
                        + self.BOOST_CLAMP_SQL["sqlite"] + " WHERE id = ?",
                        (boost_delta, keyword_id),
                    )
                    self.conn.commit()
                return
            except CONNECTION_ERRORS:
                if attempt == 1:
                    raise
                self._connect()

    # ---------- v18: 실측 CPC/RPM · 게시 플래너 · 리프레시 · 수익 인사이트 ----------

    # 실측 CPC 만점 기준 — 애드포스트 CPC 스케일(수백~수천원)의 보수적 상한.
    # measured_tier = 0.5×정적 등급 + 0.5×clamp(cpc/3000) — 실측과 정적의 절충.
    CPC_FULL_SCALE = 3000.0
    MEASURED_TIER_MIN_POSTS = 3

    def refresh_category_cpc_stats(self, updated_at):
        """AdPost 실측 지표 → category_cpc_stats 재집계 (전량 교체, 표는 소형).
        클릭/노출 0인 카테고리는 cpc/rpm NULL — measured_tier도 NULL이 되어
        priority SQL이 정적 등급으로 폴백한다 (표본 부족 = 실측 불신)."""
        import config as config_mod
        rows = self._qd(
            "SELECT k.category AS category, COUNT(*) AS posts, "
            "COALESCE(SUM(d.adpost_revenue), 0) AS revenue, "
            "COALESCE(SUM(d.adpost_impressions), 0) AS impressions, "
            "COALESCE(SUM(d.adpost_clicks), 0) AS clicks "
            "FROM drafts d JOIN keywords k ON k.id = d.keyword_id "
            "WHERE d.adpost_revenue IS NOT NULL "
            "AND d.adpost_impressions IS NOT NULL "
            "AND d.adpost_clicks IS NOT NULL "
            "AND k.category != '' "
            "GROUP BY k.category",
            (), fetch=True,
        )
        tiers = config_mod.DEFAULT_CPC_TIERS
        computed = []
        for r in rows:
            cpc = (r["revenue"] / r["clicks"]
                   if r["clicks"] > 0 else None)
            rpm = (r["revenue"] / r["impressions"] * 1000.0
                   if r["impressions"] > 0 else None)
            static = tiers.get(r["category"], tiers.get("", 0.5))
            measured = None
            if cpc is not None:
                measured = round(
                    0.5 * static
                    + 0.5 * max(0.0, min(1.0, cpc / self.CPC_FULL_SCALE)), 3)
            computed.append((r["category"], r["posts"], r["revenue"],
                             r["impressions"], r["clicks"], cpc, rpm,
                             measured, updated_at))
        self._qd("DELETE FROM category_cpc_stats", ())
        for row in computed:
            self._qd(
                "INSERT INTO category_cpc_stats (category, posts, revenue, "
                "impressions, clicks, cpc, rpm, measured_tier, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                row,
            )
        return len(computed)

    def category_cpc_stats_list(self):
        return self._qd(
            "SELECT * FROM category_cpc_stats ORDER BY revenue DESC", (), fetch=True)

    def publish_plan(self, limit=10):
        """미게시 초안 게시 추천 대기열 — 이미지 완성 상태가 우선, 동일하면
        키워드 priority 순. 섹션 이미지 부족분은 Python에서 계산해 표시."""
        import json as json_mod
        import re as re_mod
        rows = self._qd(
            f"SELECT d.id, d.title, d.body, d.keyword_id, d.image_url, "
            f"d.section_images, d.created_at, d.platform, k.keyword, k.active, "
            f"{self.PRIORITY_SQL} AS priority "
            f"FROM drafts d JOIN keywords k ON k.id = d.keyword_id "
            f"LEFT JOIN daily_stats ds ON ds.keyword_id = k.id "
            f"AND ds.day = (SELECT MAX(day) FROM daily_stats d2 "
            f"WHERE d2.keyword_id = k.id) "
            "WHERE d.status = 'draft' "
            "ORDER BY CASE WHEN d.image_url = '' THEN 1 ELSE 0 END, "
            "priority DESC, d.id DESC LIMIT ?",
            (limit,), fetch=True,
        )
        plan = []
        for r in rows:
            h2s = [h for h in re_mod.findall(r"^##\s+(.+)$", r["body"] or "", re_mod.M)
                   if "자주 묻는 질문" not in h][:8]
            have = []
            if r["section_images"]:
                try:
                    parsed = json_mod.loads(r["section_images"])
                    have = parsed if isinstance(parsed, list) else []
                except (TypeError, json_mod.JSONDecodeError):
                    have = []
            # v21(A.1): 게시 리마인더 — 생성 후 경과일 (3일+ 강조 대상)
            age_days = 0
            if r["created_at"]:
                try:
                    from datetime import date as date_mod
                    import config as config_mod
                    created = date_mod.fromisoformat(r["created_at"][:10])
                    age_days = (config_mod.today_kst() - created).days
                except ValueError:
                    age_days = 0
            plan.append({
                "draft_id": r["id"], "title": r["title"],
                "keyword": r["keyword"], "priority": r["priority"],
                "platform": r["platform"],
                "has_main_image": bool(r["image_url"]),
                "section_images_ready": len(have),
                "section_images_needed": len(h2s),
                "created_at": r["created_at"],
                "age_days": max(0, age_days),
            })
        return plan

    def recent_published(self, limit=5):
        """v21(A.1): 게시 로그 — 최근 발행 초안 (발행일·플랫폼·URL·성과)."""
        return self._qd(
            "SELECT d.id AS draft_id, d.title, d.platform, d.published_at, "
            "d.published_url, d.performance_score, k.keyword FROM drafts d "
            "JOIN keywords k ON k.id = d.keyword_id "
            "WHERE d.status = 'published' AND d.published_at != '' "
            "ORDER BY d.published_at DESC, d.id DESC LIMIT ?",
            (limit,), fetch=True)

    def refresh_candidates(self, limit=5, min_age_days=14, score_lt=50):
        """리프레시 추천 — 게시 후 일정 기간 지나고 성과 저조(score < 50)인
        초안. 이미 리프레시한 원본(refreshed_at)은 제외, 키워드 비활성 제외."""
        import config as config_mod
        from datetime import timedelta
        cutoff = (config_mod.today_kst()
                  - timedelta(days=min_age_days)).isoformat()
        rows = self._qd(
            f"SELECT d.id, d.title, d.keyword_id, d.published_at, "
            f"d.performance_score, d.adpost_revenue, k.keyword, "
            f"{self.PRIORITY_SQL} AS priority "
            f"FROM drafts d JOIN keywords k ON k.id = d.keyword_id "
            f"LEFT JOIN daily_stats ds ON ds.keyword_id = k.id "
            f"AND ds.day = (SELECT MAX(day) FROM daily_stats d2 "
            f"WHERE d2.keyword_id = k.id) "
            "WHERE d.status = 'published' AND d.refreshed_at = '' "
            "AND d.published_at != '' AND d.published_at <= ? "
            "AND d.performance_score IS NOT NULL AND d.performance_score < ? "
            "AND k.active = 1 "
            "ORDER BY d.performance_score ASC, d.id DESC LIMIT ?",
            (cutoff, score_lt, limit), fetch=True,
        )
        return rows

    def top_performer_pattern(self, sample_min=10, top_n=30):
        """성과 상위(score ≥ 70) 초안 패턴 — 제목/첫문단/본문 길이, H2 수,
        표·FAQ 포함률. 표본 미달이면 None (패턴 가이드 비활성)."""
        import re as re_mod
        rows = self._qd(
            "SELECT title, first_paragraph, body FROM drafts "
            "WHERE status = 'published' AND performance_score >= 70 "
            "ORDER BY performance_score DESC, id DESC LIMIT ?",
            (top_n,), fetch=True,
        )
        if len(rows) < sample_min:
            return None
        title_lens, fp_lens, body_lens, h2_counts = [], [], [], []
        with_table = with_faq = 0
        for r in rows:
            title_lens.append(len(r["title"] or ""))
            fp_lens.append(len(r["first_paragraph"] or ""))
            body = r["body"] or ""
            body_lens.append(len(body))
            h2s = [h for h in re_mod.findall(r"^##\s+(.+)$", body, re_mod.M)
                   if "자주 묻는 질문" not in h]
            h2_counts.append(len(h2s))
            if "|" in body:
                with_table += 1
            if "자주 묻는 질문" in body:
                with_faq += 1
        n = len(rows)

        def avg(vals):
            return round(sum(vals) / n, 1)
        return {
            "sample": n,
            "title_len_avg": avg(title_lens),
            "first_paragraph_len_avg": avg(fp_lens),
            "body_len_avg": int(round(sum(body_lens) / n)),
            "h2_count_avg": round(sum(h2_counts) / n, 1),
            "table_pct": round(100.0 * with_table / n),
            "faq_pct": round(100.0 * with_faq / n),
        }

    def revenue_insights(self):
        """수익 인사이트 — 전체 합계, 월별 추이, 키워드 기여, 카테고리 실측."""
        totals = self._qd(
            "SELECT COUNT(*) AS posts, "
            "COALESCE(SUM(adpost_revenue), 0) AS revenue, "
            "COALESCE(SUM(adpost_impressions), 0) AS impressions, "
            "COALESCE(SUM(adpost_clicks), 0) AS clicks "
            "FROM drafts WHERE adpost_revenue IS NOT NULL "
            "AND adpost_impressions IS NOT NULL AND adpost_clicks IS NOT NULL",
            (), fetch=True)[0]
        monthly = self._qd(
            "SELECT substr(published_at, 1, 7) AS month, COUNT(*) AS posts, "
            "SUM(adpost_revenue) AS revenue "
            "FROM drafts WHERE adpost_revenue IS NOT NULL AND published_at != '' "
            "GROUP BY month ORDER BY month",
            (), fetch=True)
        top_keywords = self._qd(
            "SELECT k.keyword, k.category, COUNT(d.id) AS posts, "
            "SUM(d.adpost_revenue) AS revenue "
            "FROM drafts d JOIN keywords k ON k.id = d.keyword_id "
            "WHERE d.adpost_revenue IS NOT NULL "
            "GROUP BY k.id, k.keyword, k.category "
            "ORDER BY revenue DESC LIMIT 10",
            (), fetch=True)
        return {
            "totals": totals,
            "monthly": monthly,
            "top_keywords": top_keywords,
            "categories": self.category_cpc_stats_list(),
        }

    # ---------- v22.2(3.3): 운세 콘텐츠 생성 (멱등 큐) ----------

    def get_fortune_generation(self, ref_date, content_type):
        rows = self._qd(
            "SELECT * FROM fortune_generations WHERE ref_date = ? AND content_type = ?",
            (ref_date, content_type), fetch=True)
        return rows[0] if rows else None

    def upsert_fortune_generation(self, ref_date, content_type, content,
                                  grounding="", status="generated"):
        """생성 멱등 키 — 같은 (기준일·타입) 이미 생성 시 스킵(False).
        단, content가 빈 placeholder(생성 실패 잔재)면 재시도 허용 — 기존 행 갱신."""
        existing = self.get_fortune_generation(ref_date, content_type)
        if existing:
            if existing["content"]:
                return False
            self._qd(
                "UPDATE fortune_generations SET grounding = ?, updated_at = ? "
                "WHERE ref_date = ? AND content_type = ?",
                (grounding, config_mod.now_kst_iso(), ref_date, content_type),
            )
            return True
        self._qd(
            "INSERT INTO fortune_generations (ref_date, content_type, content, "
            "grounding, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (ref_date, content_type, content, grounding, status,
             config_mod.now_kst_iso()),
        )
        return True

    def update_fortune_generation(self, ref_date, content_type, content,
                                  status="generated"):
        """생성 완료 후 실데이터 저장 (placeholder 행 갱신)."""
        import config as config_mod
        self._qd(
            "UPDATE fortune_generations SET content = ?, status = ?, "
            "updated_at = ? WHERE ref_date = ? AND content_type = ?",
            (content, status, config_mod.now_kst_iso(), ref_date, content_type),
        )

    def list_fortune_generations(self, ref_date=None, limit=50):
        sql = ("SELECT * FROM fortune_generations "
               + ("WHERE ref_date = ? " if ref_date else "")
               + "ORDER BY ref_date DESC, id DESC LIMIT ?")
        params = (ref_date, limit) if ref_date else (limit,)
        return self._qd(sql, params, fetch=True)

    def close(self):
        if self.conn:
            self.conn.close()
