# autostudio — K-1~K-4 KDP 파이프라인 기술 설계 (tech-design.md)

> 작성: 개발팀 · 프로젝트: autostudio · 작업 디렉토리: pipeline/kdp-implementation/
> 상위: docs/planning/12-kdp-pipeline.md · pipeline/shorts-kdp-research/{plan,trd,tasks,test-design}.md · pipeline/kdp-implementation/{storyboard,design-system,design-qa-report}.md
> 관례: pipeline/kdp-implementation/coding-convention.md
> 상태: 개발 산출물 2/2 — **승인 게이트 대상** (구현 금지, 승인 후 K-1~K-4 TDD)

---

## 0. 설계 요약 (핵심 결정)

| 결정 포인트 | 선택 | 근거 |
|---|---|---|
| DB 스키마 | kdp_books·kdp_chapters·kdp_covers·kdp_publish + **kdp_performance**·**kdp_qc_results** 신규 | 12-kdp §3 + 디자인QA QA-D3(성과/QC 저장 공백) 해소 |
| DB 이중 SQL | 기존 SCHEMAS dict + _q/_qd/_q_once/_migrate 재사용 | coding-convention §2, 신규 테이블 CREATE IF NOT EXISTS |
| 영어 현지화 | 기본 rule 기반(매핑+근사어) + LLM 번역 폴백(runner 주입) | 아마존 검색 관례 일치 + 테스트 결정성(LLM 0회 가능) |
| 아마존 스냅샷 | requests + HTML/JSON 파싱, 실패 시 graceful 폴백+로그 | 공개 API 없음, 테스트는 mock |
| 틈새 판정 | 상위 20권 가격·평점·권수 → 진입 가중 스코어 + 전환율 30% 게이트 | 12-kdp R-4·K-2 |
| 책 생성 | pass1_outline 재사용 + 챕터별 2패스 + 일관성 보정 LLM 1회 | draft_pipeline 자산 재활용 |
| 챕터 예산 | 챕터당 하드 예산 300초(content_batch 패턴), 부분 저장·재개 | trd §2 |
| QC 8항목 | 1·4는 rule기반(ngram/Jaccard) 인터페이스만, 2~8 규칙/로컬 | 설치 부담 회피(MVP 경량) |
| EPUB 조립 | ebooklib + markdown(md→HTML) + image_gen/Pillow 표지, 로컬 구조검증+GH calibre/epubcheck | 12-kdp §2.1 |
| API | GET/POST /kdp/books 등 — require_token, 서버리스 준수(생성은 배치) | server.py 관례 |
| 배치 | kdp-pipeline.yml(daily-collect 패턴) + calibre/openjdk + EPUB 검증 + 출간큐 + 48h + 성과 | tasks K-4 |
| 대시보드 | 기존 .tabs/.seg/.badge/.gauge/.mini-table/.revenue-bar/.steps/.panel/.skel/.empty/#status 재사용, 신규 CSS 금지, border-strong은 var(--border-strong) | design-system §3-4, QA-D1 |

---

## 1. DB 스키마 (K-1 기반 + K-4 확장)

> 12-kdp §3 + QA-D3 반영: 성과(AC-DB-1) + QC 결과 테이블 신규. kdp_publish에 QA-D6 미러 필드 추가.

### 1.1 테이블 정의 (SQLite 예시 — Postgres는 동일 타입 대응, SCHEMAS 쌍형)

[SQL 블록 시작]
-- v30: KDP 책 (주제 선정 → 생성 → 출간 상태 전이)
CREATE TABLE IF NOT EXISTS kdp_books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL UNIQUE,
    title_ko TEXT NOT NULL DEFAULT '',      -- 한국어 병행 후보(K-2)
    description TEXT NOT NULL DEFAULT '',
    keywords TEXT NOT NULL DEFAULT '[]',     -- JSON array (키워드 7개 검수)
    category TEXT NOT NULL DEFAULT '',
    category2 TEXT NOT NULL DEFAULT '',      -- KDP 카테고리 2개
    pen_name TEXT NOT NULL DEFAULT '',       -- 펜네임 (QC #8)
    status TEXT NOT NULL DEFAULT 'draft',    -- draft/assembling/ready/published/monitoring
    priority REAL NOT NULL DEFAULT 0,        -- 출간 큐 정렬
    source_keyword TEXT NOT NULL DEFAULT '', -- '곧 뜰' 원본 키워드(K-1)
    lang TEXT NOT NULL DEFAULT 'en',         -- en/ko (영어/한국어 병행 K-2)
    evidence TEXT NOT NULL DEFAULT '{}',     -- 스냅샷·틈새 판정 evidence JSON
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_kdp_books_status ON kdp_books(status, priority);

CREATE TABLE IF NOT EXISTS kdp_chapters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES kdp_books(id),
    seq INTEGER NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    body_md TEXT NOT NULL DEFAULT '',
    word_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending/done/partial/failed
    status_detail TEXT NOT NULL DEFAULT '',  -- 예산 초과 등
    created_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT '',
    UNIQUE(book_id, seq)
);

CREATE TABLE IF NOT EXISTS kdp_covers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES kdp_books(id),
    image_url TEXT NOT NULL DEFAULT '',
    size TEXT NOT NULL DEFAULT '6x9',
    created_at TEXT NOT NULL DEFAULT '',
    UNIQUE(book_id)
);

CREATE TABLE IF NOT EXISTS kdp_publish (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES kdp_books(id),
    publish_date TEXT NOT NULL DEFAULT '',
    price REAL NOT NULL DEFAULT 0,
    royalty_rate REAL NOT NULL DEFAULT 0.7,
    expected_royalty REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending/published/verified/failed
    verified_at TEXT NOT NULL DEFAULT '',
    mirror_status TEXT NOT NULL DEFAULT '',  -- QA-D6: 정상/이상
    price_ok INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT '',
    UNIQUE(book_id, publish_date)
);

-- v30 (QA-D3): 성과 입력 (AC-DB-1) — 월×책
CREATE TABLE IF NOT EXISTS kdp_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES kdp_books(id),
    year_month TEXT NOT NULL,                -- '2026-08'
    sales INTEGER NOT NULL DEFAULT 0,
    royalty REAL NOT NULL DEFAULT 0,
    measured_by TEXT NOT NULL DEFAULT 'manual', -- 수동 — Amazon KDP 리포트
    created_at TEXT NOT NULL DEFAULT '',
    UNIQUE(book_id, year_month)
);

-- v30 (QA-D3): QC 결과 저장 (8항목) — 책 단위 런 이력
CREATE TABLE IF NOT EXISTS kdp_qc_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES kdp_books(id),
    run_at TEXT NOT NULL,
    qc_item TEXT NOT NULL,                   -- 1..8 고정 이름(§3.2)
    passed INTEGER NOT NULL,                 -- 1/0
    detail TEXT NOT NULL DEFAULT '',         -- 실패 원인/실측
    UNIQUE(book_id, run_at, qc_item)
);
CREATE INDEX IF NOT EXISTS idx_kdp_qc_book_run ON kdp_qc_results(book_id, run_at);
[SQL 블록 끝]

### 1.2 _MIGRATE_COLUMNS 추가 방식
- KDP 테이블은 전부 신규 CREATE TABLE IF NOT EXISTS — migrate 불필요.
- 이후 컬럼 추가만 _MIGRATE_COLUMNS 등록(coding-convention §2.3).
- **기존 단일 db.Database에 메서드 추가**(별도 클래스 금지, SCHEMAS 확장).

### 1.3 db.py 메서드 (신규, _q/_qd 재사용)
- kdp_books: insert_kdp_book·get_kdp_book·list_kdp_books(status_filter, sort)·update_kdp_book_status·update_kdp_book_meta
- kdp_chapters: insert_kdp_chapter·list_kdp_chapters(book_id)·update_kdp_chapter
- kdp_covers: upsert_kdp_cover·get_kdp_cover
- kdp_publish: insert_kdp_publish·list_kdp_publish(status)·claim_publish_slot(일 3권 트랜잭션)·verify_kdp_publish(verified+verified_at+mirror)
- kdp_performance: upsert_kdp_performance·list_kdp_performance(month)·kdp_monthly_summary
- kdp_qc_results: replace_kdp_qc_results(book_id, run_at, results)·get_kdp_qc_results(book_id)
- 일 3권 게이트: 오늘 publish_date 건수 < 3 판정, 초과분 pending(AC-K4-1①).

---

## 2. kdp_research.py (K-1) — 주제 선정

### 2.1 입력
- 기존 db API: v20 '곧 뜰' 프리셋 상위(query_keywords(preset="upcoming", limit=N)) + 활성 키워드 + 카테고리(고CPC 우선).
- 입력 행: (keyword, category, ai_cite_idx, demand_idx, opportunity).

### 2.2 영어 현지화
- 기본 rule 기반(테스트 결정성): _L10N_RULES 매핑(카테고리→영어 도메인) + 근사어/형태소 규칙('절약'→saving, '52주'→52 week).
- rule 미적중 시 translation_runner(prompt) 1회(기본 _run_llm). **runner 주입**으로 테스트는 rule만.
- 아마존 검색어 관례: 2~4단어 명사구('{topic} workbook/guide/planner for {audience}').

### 2.3 아마존 검색 스냅샷 (requests, mock)
- 공개 API 없음 → 검색 상위 20권 HTML/JSON 파싱, 상품당 제목·가격·평점·리뷰수·권수.
- 파싱 실패 → AmazonSnapshotError catch → graceful 폴백(_unavailable_snapshot) + logger.warning. 테스트는 snapshot mock.
- 파서 안정: 선택자/구조 맵을 모듈 상수로 분리, UA 헤더 + 최소 2개 파싱 경로.

### 2.4 틈새 판정 + 전환율 게이트
- 틈새 스코어 = 권수·가격대·평점·리뷰 가중 합(경쟁 적음+수요 있음).
- 전환율 게이트(AC-K1-1④): 후보수/키워드수, 30% 미만이면 KDP KR 한국어 병행 비중 확대(lang='ko'). — T-K1-04
- 검색 0건 → 후보 제외(T-K1-02). 영어 현지화 불가·영어 수요 낮음 → 한국어 병행(T-K1-03).

### 2.5 산출·저장
- 후보(title, description, keywords[7], category, lang, evidence) → insert_kdp_book 저장, status='draft'.

### 2.6 모듈 시그니처(안)
[코드 시작]
def run_research(d, cfg, keywords, snapshot_fetcher=None, translator=None, limit=10) -> dict
def fetch_snapshot(query, fetcher=None) -> dict    # mock 대상, graceful 폴백
def niche_score(snapshot_rows) -> dict             # 틈새 판정
def english_candidate(keyword, category, translator=None, snapshot=None) -> dict|None
def korean_candidate(keyword, category, snapshot=None) -> dict|None
[코드 끝]

---

## 3. kdp_book.py (K-2) — 책 생성 + QC 8항목

### 3.1 생성 흐름
1. outline: pass1_outline(draft_pipeline) 재사용 — 챕터 6~12개+불릿 → kdp_chapters skeleton(seq·title, pending).
2. 챕터별 2패스: generate_two_pass 패턴(platform='brand' 마크다운) + runner/예산. 예산 HARD_CHAPTER_BUDGET_SECONDS=300, 초과 시 status='partial' 저장·재개(tasks K-2 엣지).
3. 일관성 보정 패스: 챕터 전부 done 후 consistency_pass(chapters, runner) — 어조·용어·시점 통일 LLM 1회, body_md 반영.
4. QC 8항목 run_qc → kdp_qc_results 저장, 전부 통과 시 book status='ready'(AC-K2-2).

### 3.2 QC 8항목 함수 정의 (MVP rule 기반 + 인터페이스)

| # | 항목 | 함수 | 구현(MVP, rule) | 확장(옵션) |
|---|---|---|---|---|
| 1 | 표절 유사성 | check_plagiarism | ngram/Jaccard 유사도 임계 초과 문장 검출(PLAG_SIM_THRESHOLD=0.8) | sentence-transformers 임베딩(설치 시) |
| 2 | 금지어 | check_banned_words | KDP 정책어·광고 과장·의료/투자 확정 표현 매칭(BANNED_WORDS) | — |
| 3 | 사실성 | check_factual_claims | '추정/약/대략' 미표기 수치·확정 주장 패턴 감지 + 출처 없음 | LanguageTool |
| 4 | 챕터 간 중복 | check_chapter_duplication | 챕터 쌍 ngram/Jaccard 유사도 >=0.8 | sentence-transformers |
| 5 | 길이 ±20% | check_length | 워크북 800~1,200단어/챕터 목표 ±20% (word_count) | textstat FK |
| 6 | AI 표기 | check_ai_disclosure | AI-generated(LLM 초안)=공개 문구 필요(본문+표지), AI-assisted=면제, 판정 근거 로그 | — |
| 7 | 마크다운 정합 | check_markdown | md 파싱 오류 검사 + EPUB 변환 경고 0(배치) | calibre/epubcheck |
| 8 | 메타데이터 | check_metadata | 키워드 7·카테고리 2·펜네임·설명·제목 길이 검사 | — |

- QC_ITEMS 상수(항목명·임계)로 단일화. 실패는 kdp_qc_results에 저장, 재생성 지시·리포트(T-K2-03/04).

### 3.3 모듈 시그니처(안)
[코드 시작]
def generate_book(d, cfg, book_id, runner=None, translator=None) -> dict
def generate_outline(d, keyword, structure, runner=None) -> list[dict]   # 6~12 챕터
def generate_chapter(d, book_id, seq, runner=None, hard_budget_seconds=300) -> dict
def consistency_pass(chapters, runner=None) -> list[dict]
def run_qc(d, book_id, draft_pack, snapshot=None) -> list[QCResult]
[코드 끝]

---

## 4. ebook_builder.py (K-3) — EPUB 조립 + 검증

### 4.1 조립 (ebooklib)
- build_epub(book, chapters, cover_image_bytes) -> bytes/path
  - 목차=챕터 시퀀스(kdp_chapters), 챕터 HTML = markdown.markdown(body_md, extensions=[tables, fenced_code]).
  - 메타: 제목·펜네임·키워드·설명. 표지 타입/크기 지정.
  - ebooklib·markdown·Pillow는 함수 내 지연 로드(미설치 시 명확한 오류).

### 4.2 표지 (image_gen + Pillow 6×9)
- make_cover_image(keyword, title, background_bytes=None) -> bytes
  - image_gen.generate_image로 배경 → Pillow 6×9(0.667) 캔버스 + 제목·부제 텍스트 오버레이.
  - 배경 실패 시 단색 배경 + 텍스트 폴백(graceful).

### 4.3 검증
- 로컬(MVP): validate_epub_structure(bytes) -> (ok, issues) — zip 구조·OPF·목차·챕터 존재(순수 파이썬).
- GH Actions: calibre ebook-polish --check(Java 불필요 폴백) + ebook-convert + (선택) epubcheck(Java). 에러·경고 0(AC-K3-1).
- 변환 경고 -> 원인 로그 + 재생성 지시(T-K3-04).

---

## 5. server.py API (K-1~K-4) — require_token

> 서버리스 60초 준수: 생성/검수/EPUB 조립은 GH 배치. API는 조회·다운로드·수동 상태 전이·성과 입력만.

| 메서드·경로 | 용도 | 비고(AC) |
|---|---|---|
| GET /kdp/books | 책 목록(list_kdp_books), 상태 필터 | AC-K1-1 |
| POST /kdp/books | 수동 책 생성 트리거(후보 수락) | K-1 |
| GET /kdp/books/{id} | 책 상세(+챕터·QC·표지·출간) | K-2/4 모달 |
| POST /kdp/books/{id}/generate | 생성 시작 -> 배치 큐 표시(즉시 반환, 비동기) | AC-K2-1 |
| POST /kdp/books/{id}/qc | QC 8항목 재실행 | AC-K2-2 |
| GET /kdp/books/{id}/epub | EPUB 다운로드(ready+만) | AC-K3-1 |
| GET /kdp/publish-queue | 출간 큐(일 3권 게이트) | AC-K4-1 |
| POST /kdp/publish | 출간 시작(체크리스트 검증) -> status 전이 | AC-K4-1③ |
| POST /kdp/publish/{id}/verify | 48h 확인 -> verified+verified_at+mirror | AC-K4-2② |
| GET /kdp/monitoring | 48h 미검증 책 목록(상단 정렬) | AC-K4-2① |
| POST /kdp/performance | 성과 입력(manual 고정) | AC-DB-1① |
| GET /kdp/breakeven | 손익분기표(가격->로열티·권수) | AC-DB-1③ |

- 모든 라우트 dependencies=[Depends(require_token)](server.py 관례), /api 프리픽스 미들웨어 존중.
- Pydantic 모델: BookGenerateIn·PublishIn·VerifyIn·PerformanceIn.
- 생성은 배치 트리거 큐 기록 후 즉시 반환(비동기, K-2 예산 엣지는 배치가 처리).

---

## 6. 배치 (K-4) — .github/workflows/kdp-pipeline.yml

### 6.1 워크플로우 (daily-collect.yml 패턴)
[코드 시작]
name: kdp-pipeline
on:
  schedule:
    - cron: '30 21 * * *'   # 매일 06:30 KST (전날 21:30 UTC) - 수집 잡과 시간 분리
  workflow_dispatch:
concurrency:
  group: kdp-pipeline
  cancel-in-progress: false
jobs:
  kdp:
    runs-on: ubuntu-latest
    timeout-minutes: 60
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - name: Install Python deps
        run: pip install -r requirements.txt -r requirements-dev.txt
      - name: Install calibre + Java + epubcheck
        run: |
          sudo apt-get update && sudo apt-get install -y calibre openjdk-17-jre-headless
      - name: Run KDP pipeline
        run: python kdp_pipeline.py
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          OPENCODE_GO_API_KEY: ${{ secrets.OPENCODE_GO_API_KEY }}
          BAILIAN_TOKEN_PLAN_API_KEY: ${{ secrets.BAILIAN_TOKEN_PLAN_API_KEY }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
[코드 끝]

- keep-alive 단계는 daily-collect와 동일 패턴(60일 자동 비활성 방지).
- YOUTUBE·BLOG 불필요(KDP는 유튜브/운세 블로그 안 씀).

### 6.2 출간 큐 + 48h 모니터링 + 성과 (K-4)
- 일 3권 게이트: kdp_pipeline.py가 오늘 publish_date 건수 검사 -> 3권 이상 초과분 pending(AC-K4-1).
- 48h: publish_date+48h < now & verified_at=NULL & status=published -> monitoring 강조+로그(AC-K4-2). 서버 조회 시 계산.
- 성과: 수동(POST /kdp/performance, measured_by=manual 고정). 자동 수집 API 없음(F-7).

---

## 7. static/index.html KDP 탭 (K-4)

> storyboard.md §2~§5 + design-system.md 조합. 신규 CSS 금지, 기존 클래스만 재사용.

- 최상단 .tabs에 "KDP 출간" 추가 + tabKdp(.tabpane) 신설. switchTab('kdp') 확장(kdpLoaded 지연 로드).
- 내부 .seg 4세그먼트: 책 목록/출간 큐/48h/성과(.seg button.on).
- 컴포넌트 조합:
  - KPI 4개: .kpis .kpi-label .kpi-value(.warn) .kpi-sub (48h 미검증은 .warn)
  - 책 목록 table(스티키 헤더)+상태 배지 .badge.b-gray/blue/green/gold/warn (storyboard §2.1)
  - 챕터 진행률 .gauge.g-blue + .num (x/y)
  - EPUB 버튼 .btn.btn-sm.btn-gen(ready+만), draft/assembling .btn:disabled
  - 48h 리스트 table+.badge.b-warn+.no/.warn-txt; 미검증 행 테두리 -> inline style border:1px solid var(--border-strong) (QA-D1 — 클래스 아닌 변수)
  - 출간 체크리스트 .draft-block + .ok/.no/.warn-txt 요약 x/4 (design-system §3-3)
  - 성과 .mini-table(손익분기)+.revenue-bar(월별 로열티)+입력 폼(측정 경로 '수동 - Amazon KDP 리포트' 고정, API/Studio 비활성)
  - 모달 #detail .panel(.panel-head/.panel-body)+.x(닫기)
  - 상태 .skel(8행)·.empty·#status.warn·.spinner (storyboard §6)
  - 단계 .steps/.step(.active/.done)/.dot (출간 파이프라인)
- a11y: role=tablist/aria-label, 배지 라벨 병기(색 단독 금지), prefers-reduced-motion 존중.

---

## 8. 테스트 계획

> T-K1-01~04·T-K2-01~06·T-K3-01~04·T-K4-01~06·T-DB-01~02 -> 신규 tests/test_kdp_*.py.

| 테스트 파일 | 커버 TC | 전략(mock) |
|---|---|---|
| tests/test_kdp_db.py | 스키마·메서드·일3권 | tmp_path SQLite + make_db, 기존 패턴 |
| tests/test_kdp_research.py | T-K1-01~04 | 아마존 스냅샷 fetcher mock, rule 현지화 결정성, 틈새, 30% 게이트, 0건 제외, 한국어 병행 |
| tests/test_kdp_book.py | T-K2-01~06 | llm runner mock(pass1/pass2/consistency), 챕터 예산 초과(부분 저장), QC 각 함수, 중복>=0.8, AI 본문+표지, 길이±20% |
| tests/test_ebook_builder.py | T-K3-01~04 | image_gen·markdown mock, validate_epub_structure 로컬, 표지 6×9 Pillow |
| tests/test_kdp_api.py | T-K4-01~06 | TestClient + create_app(cfg), 게이트·체크리스트 차단·48h·mirror/가격, performance, breakeven |
| tests/test_kdp_qc.py | QC 상세 | QC 8항목 rule 단위 + 리포트 저장 |

- mock: 아마존=fetcher mock, LLM=runner mock(결정성), 이미지=image_gen.generate_image monkeypatch(URL stub), calibre/epubcheck=서브프로세스 stub(실측 GH).
- conftest autouse 외부키 픽스처로 네트워크/LLM 차단(coding-convention §4.2).

---

## 9. 리스크

| 리스크 | 영향 | 완화 |
|---|---|---|
| 아마존 스냅샷 HTML 파싱 취약 | 수요 검증 실패 | graceful 폴백+로그, 파싱 경로 2개, mock 테스트, 파서 상수 분리 |
| sentence-transformers 설치 부담 | 무거움 | MVP ngram/Jaccard rule기반 + 인터페이스만, 설치 옵션(폴백) |
| Vercel 60초 | 생성/조립 중단 | 생성·검증은 배치, API는 조회·다운로드·상태 전이, 모듈 예산 상수 |
| ebooklib AGPL-3.0 | 외부 SaaS화 시 파생 공개 | 내부 OK, 서비스화 시 pypub(MIT) 대체(12-kdp §2.1) |
| calibre/epubcheck Java 의존 | 배치 실패 | openjdk 설치 + ebook-polish --check 폴백 |
| __pycache__ stale | 오탐/불일치 | 삭제 or PYTHONDONTWRITEBYTECODE=1, 수정 후 실행 전 정리 |
| 일 3권 게이트 레이스 | 초과 출간 | claim_publish_slot 트랜잭션(UNIQUE + COUNT 게이트) |

---

## 10. 구현 순서 (K-1~K-4)

1. K-1: db.py SCHEMAS + kdp 메서드 -> test_kdp_db -> kdp_research + test_kdp_research
2. K-2: kdp_book + test_kdp_book + test_kdp_qc (QC 8항목)
3. K-3: ebook_builder + test_ebook_builder
4. K-4: kdp_pipeline(배치) + server.py 라우트 + test_kdp_api + static/index.html KDP 탭

> TDD: 각 단계 테스트 먼저(red) -> 최소 구현(green) -> 리팩터. 구현은 **승인 후** 지시받은 때만.

---

*작성: 개발팀 · 1단계 산출물 2/2 · 상태: 설계 완료 - 승인 게이트 대기 (구현 금지)*

### 6.3 kdp_pipeline.py (배치 진입점 — collect.py main() 패턴)

> collect.py의 main()과 동일 구조: load_config → run → SystemExit 코드. GitHub Actions는 python kdp_pipeline.py 실행.

[코드 시작]
import logging
import sys

import config as config_mod
import db


def run_pipeline(cfg, client=None, today=None):
    """KDP 배치 본 로직 — 출간 큐(일 3권 게이트)·48h 모니터링·성과 집계.
    각 단계는 실패 격리(한 단계 실패가 배치 전체를 중단하지 않게), 반환 카운트 dict."""
    d = db.Database(cfg["db_url"])
    d.init()
    result = {"published": 0, "pended": 0, "pending_48h": 0,
              "errors": []}
    try:
        # ① 출간 큐 — day 게이트: 오늘 예약 3권 초과분 pending
        # ② 48h 미검증 모니터링 — publish_date+48h 경과 & verified_at=NULL 강조
        # ③ (성과는 수동 — 대시보드 /kdp/performance에서 입력)
        pass
    finally:
        d.close()
    return result


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    cfg = config_mod.load_config()
    result = run_pipeline(cfg)
    logger = logging.getLogger("kdp_pipeline")
    if result.get("locked"):            # 병행 실행 락(선택)
        logger.info("이미 KDP 파이프라인이 실행 중입니다 — 종료")
        raise SystemExit(0)
    logger.info("완료: 출간 %d권, pending %d권, 48h 미검증 %d권, 오류 %d건",
                result.get("published", 0), result.get("pended", 0),
                result.get("pending_48h", 0), len(result.get("errors", [])))
    # 실패 임계(전량 실패 등) 시 exit 1 → GH Actions 실패 알림 전파 (collect.py 관례)
    if result.get("errors") and not result.get("published"):
        raise SystemExit(1)
    raise SystemExit(0)


if __name__ == "__main__":
    sys.exit(main())
[코드 끝]

- 이미지/LLM 경고(예: 표지 생성 실패 임계)가 있으면 exit 1로 전파(collect.py image_alert 패턴 재사용).
- EPUB 검증은 이 워크플로우의 별도 step(calibre/epubcheck)에서 수행, 실패 시 해당 step이 잡을 실패시킴.
