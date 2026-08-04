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
    shop_click_idx REAL,
    ai_cite_idx REAL,
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
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT ''
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
    shop_click_idx DOUBLE PRECISION,
    ai_cite_idx DOUBLE PRECISION,
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
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT ''
);
""",
}

_STATS_COLUMNS = (
    "total_sim", "total_date", "fresh_ratio", "shop_total", "shop_avg_price",
    "shop_category", "shop_error", "growth", "opportunity", "commercial",
    "demand_idx", "shop_click_idx", "ai_cite_idx",
)


class Database:
    # v6: priority = 0.35×ai_cite_idx + 0.35×demand_idx(≤1) + 0.30×CPC등급(카테고리)
    # SORT_COLUMNS에 쓰이는 priority 표현식 — SELECT에도 동일 alias로 노출 (server 조회용)
    CPC_TIER_SQL = (
        "CASE WHEN k.category IN ('보험','금융','재테크') THEN 1.0 "
        "WHEN k.category IN ('부동산','법률','건강','의료') THEN 0.9 "
        "WHEN k.category IN ('IT','디지털','교육','자격증') THEN 0.8 "
        "ELSE 0.5 END"
    )
    PRIORITY_SQL = (
        "ROUND(35.0 * COALESCE(ds.ai_cite_idx, 0) "
        "+ 35.0 * CASE WHEN COALESCE(ds.demand_idx, 0) > 1 THEN 1.0 "
        "ELSE COALESCE(ds.demand_idx, 0) END "
        f"+ 30.0 * {CPC_TIER_SQL}, 1)"
    )
    SORT_COLUMNS = {
        "opportunity": "ds.opportunity",
        "commercial": "ds.commercial",
        "click": "ds.shop_click_idx",  # v4: 쇼핑 클릭 지수 (쇼핑 검색 API 종료 대체)
        "demand": "ds.demand_idx",
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

    def _migrate(self):
        # v6: 기존 DB(스키마 변경 전 생성)에 신규 컬럼 추가 — CREATE TABLE IF NOT EXISTS는
        # 이미 존재하는 테이블에는 컬럼을 추가하지 않으므로 명시적 ALTER 필요.
        # (SQLite: PRAGMA 검사, Postgres: ADD COLUMN IF NOT EXISTS 네이티브)
        if self.dialect == "postgres":
            self._q(
                None,
                "ALTER TABLE daily_stats ADD COLUMN IF NOT EXISTS ai_cite_idx "
                "DOUBLE PRECISION",
                (),
            )
            return
        rows = self._qd(
            "SELECT name FROM pragma_table_info('daily_stats') WHERE name = 'ai_cite_idx'",
            (), fetch=True,
        )
        if not rows:
            self._qd("ALTER TABLE daily_stats ADD COLUMN ai_cite_idx REAL", ())

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
            stats.get("shop_click_idx"), stats.get("ai_cite_idx"),
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

    def update_shop_click_idx(self, keyword_id, day, shop_click_idx):
        # v4: 쇼핑 클릭 지수 (쇼핑인사이트 앵커 정규화)
        self._qd(
            "UPDATE daily_stats SET shop_click_idx = ? WHERE keyword_id = ? AND day = ?",
            (shop_click_idx, keyword_id, day),
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

    def find_retire_candidates(self, first_seen_before, since_day, opp_lt, click_lt):
        """발견 오래됨 + 최근 스냅샷 존재 + 최근 성과 전부 저조 → 은퇴 후보.
        v4: 쇼핑 검색 API 종료로 상업성은 항상 NULL이므로 은퇴는 기회점수 + 쇼핑 클릭 지수로 판정.
        최근 7일 창의 스냅샷 중 하나라도 기회/쇼핑 클릭 점수가 NULL이면 보호한다
        (미조회·분야 미매칭 키워드를 0점 취급해 오은퇴시키지 않음 — 스펙 §4.6).
        NULL은 수집 실패일 수 있으므로 '저성과' 판정의 근거가 될 수 없다."""
        sql = """
SELECT k.id, k.keyword FROM keywords k
WHERE k.active = 1 AND k.first_seen <= ?
  AND EXISTS (
    SELECT 1 FROM daily_stats ds WHERE ds.keyword_id = k.id AND ds.day >= ?
      AND ds.opportunity IS NOT NULL AND ds.shop_click_idx IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM daily_stats ds WHERE ds.keyword_id = k.id AND ds.day >= ?
      AND (ds.opportunity IS NULL OR ds.shop_click_idx IS NULL
           OR ds.opportunity >= ? OR ds.shop_click_idx >= ?))
ORDER BY k.id"""
        return self._qd(sql, (first_seen_before, since_day, since_day, opp_lt, click_lt), fetch=True)

    def cleanup(self, stats_before_day, top_before_day, log_before_ts):
        self._qd("DELETE FROM daily_stats WHERE day < ?", (stats_before_day,))
        self._qd("DELETE FROM top_results WHERE day < ?", (top_before_day,))
        self._qd("DELETE FROM collection_log WHERE run_at < ?", (log_before_ts,))

    # ---------- 대시보드 목록 (단일 쿼리 + 페이징) ----------

    def _keyword_where(self, category, commercial_min, q, discovered_since, active,
                       opportunity_min=0.0, demand_min=0.0, click_min=0.0,
                       ai_cite_min=0.0):
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
        if click_min:        # v4: 쇼핑 클릭 지수 최소 (유망 프리셋·필터)
            where.append("ds.shop_click_idx >= ?")
            params.append(click_min)
        if ai_cite_min:      # v6: AI 인용 가능성 최소 (AI 유망 프리셋)
            where.append("ds.ai_cite_idx >= ?")
            params.append(ai_cite_min)
        if q:
            where.append("k.keyword LIKE ?")
            params.append(f"%{q}%")
        if discovered_since:
            where.append("k.first_seen >= ?")
            params.append(discovered_since)
        return (" WHERE " + " AND ".join(where)) if where else "", params

    def query_keywords(self, sort="opportunity", sort_dir="desc", category="",
                       commercial_min=0.0, q="", discovered_since="", active=1,
                       opportunity_min=0.0, demand_min=0.0, click_min=0.0,
                       ai_cite_min=0.0, limit=50, offset=0):
        col = self.SORT_COLUMNS.get(sort, "ds.opportunity")
        order = "ASC" if sort_dir == "asc" else "DESC"  # v3: 정렬 토글 (UX §6)
        where_sql, params = self._keyword_where(
            category, commercial_min, q, discovered_since, active,
            opportunity_min, demand_min, click_min, ai_cite_min)
        sql = f"""
SELECT k.id, k.keyword, k.active, k.first_seen, ds.day,
       COALESCE(NULLIF(ds.shop_category, ''), k.category) AS category,
       ds.opportunity, ds.commercial, ds.growth, ds.demand_idx, ds.shop_click_idx,
       ds.fresh_ratio, ds.total_sim, ds.shop_total, ds.ai_cite_idx,
       {self.PRIORITY_SQL} AS priority,
       (SELECT COUNT(*) FROM daily_stats h WHERE h.keyword_id = k.id) AS days
{self._KEYWORD_BASE}{where_sql}
ORDER BY CASE WHEN {col} IS NULL THEN 1 ELSE 0 END, {col} {order}, k.first_seen, k.id
LIMIT ? OFFSET ?"""
        return self._qd(sql, tuple(params + [limit, offset]), fetch=True)

    def count_keywords(self, category="", commercial_min=0.0, q="",
                       discovered_since="", active=1,
                       opportunity_min=0.0, demand_min=0.0, click_min=0.0,
                       ai_cite_min=0.0):
        where_sql, params = self._keyword_where(
            category, commercial_min, q, discovered_since, active,
            opportunity_min, demand_min, click_min, ai_cite_min)
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
                     image_url="", status="draft", created_at=""):
        self._q(
            "INSERT INTO drafts (keyword_id, title, first_paragraph, body, image_url, "
            "status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            "INSERT INTO drafts (keyword_id, title, first_paragraph, body, image_url, "
            "status, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (keyword_id, title, first_paragraph, body, image_url, status,
             created_at, created_at),
        )
        rows = self._qd("SELECT id FROM drafts ORDER BY id DESC LIMIT 1", (), fetch=True)
        return rows[0]["id"]

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

    def list_drafts_by_keyword(self, keyword_id):
        return self._qd(
            "SELECT * FROM drafts WHERE keyword_id = ? ORDER BY id DESC",
            (keyword_id,), fetch=True,
        )

    def close(self):
        if self.conn:
            self.conn.close()
