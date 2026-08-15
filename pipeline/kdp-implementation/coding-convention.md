# autostudio — 코딩 관례 요약 (coding-convention.md)

> 작성: 개발팀 · 프로젝트: autostudio · 작업 디렉토리: pipeline/kdp-implementation/
> 대상: KDP 파이프라인(K-1~K-4) 구현 전 지침. 기존 코드(server.py·db.py·collect.py·content_batch.py·draft_pipeline.py·config.py·tests/)에서 **실제 관례**를 추출해 정리한 문서.
> 인계: 개발팀 → 기획/디자인QA 승인 게이트 → K-1~K-4 TDD 구현

---

## 1. 네이밍

### 1.1 함수/메서드
- **동사 우선, 의도 명시**: get_draft·insert_draft·generate_two_pass·pass1_outline·pass2_expand·validate_draft·run_collection·record_draft_feedback
- **공개 vs 내부**: 모듈 내부 전용 보조 함수는 밑줄 접두사 _backfill_images·_create_draft·_section_titles·_build_prompt. 서버 내부 헬퍼도 _generate_and_store_draft·_fetch_image_bytes·_with_parsed_tags.
- **진입점 진실**: collect.main()이 최종 엔트리. 열람/생성 함수와 진입점을 분리해 테스트 용이(monkeypatch).
- **hook/runner 주입**: 가격·시간·외부 의존을 인자로 받아 결정성 확보 — _create_draft(d, cfg, client, keyword_row, today, now, deadline), generate_two_pass(..., runner=None, current_date=None, search_evidence=None, hard_budget_seconds=None).

### 1.2 클래스 / 모듈
- DB 접근은 단일 Database 클래스로 캡슐화(메서드 단위 self-documenting). 함수형은 파이프라인 유틸(content_batch·image_gen·collect) 위주.
- 전용 예외 클래스: DraftGenerationError·ImageGenerationError·NaverAPIError·BlogPublishError — 모듈별 선언.
- 모듈 파일명은 소문자 스네이크(draft_pipeline·content_batch·image_gen·publish_client).

### 1.3 한글 docstring 스타일 (중요)
- 모든 공개 함수에 한국어 docstring. 첫 줄: 한 문장 요약 + v<버전> 마커·AC 참조.

    def record_draft_feedback(self, draft_id, keyword_id, published_at, score,
                              note, updated_at, boost_delta):
        """v10 [6]: 게시 후 성과 기록 — 서치어드바이저 수동 입력.
        score 0~100, note는 성과 메모. v14: 점수 갱신과 boost 가산을 단일 커밋으로."""
- **왜(why)·예방한 결함**(버그 번호, AC)을 기록. 단순 '무엇' 아닌 '왜'를 남긴다.
- 단락 구분은 사이 em-대시, 변경 이력은 '# v30:' 마커 주석.

### 1.4 상수
- 모듈 상수는 대문자 스네이크 + 도메인 단위 주석: HARD_DRAFT_BUDGET_SECONDS=300·MIN_CALL_TIMEOUT=15·IMAGE_TIMEOUT=55·IMAGE_ALERT_CONSECUTIVE=5.
- 값이 policy/계약이면 docstring에서 임계 근거 명시(draft_pipeline.py 검수 임계 블록).
- 데이터 정합 규칙: 일 3권·70% 구간 2.99~12.99·손익분기표 등 공통 상수는 config/모듈 상수로 단일화(하드코딩 금지, trd §5.3).

---

## 2. db.py 이중 SQL 패턴

### 2.1 SCHEMAS dict (SQLite/Postgres)
- SCHEMAS = {"sqlite": ..., "postgres": ...} — 두 엔진용 스키마를 쌍으로 정의.
- SQLite: id INTEGER PRIMARY KEY AUTOINCREMENT · Postgres: id SERIAL PRIMARY KEY.
- REAL ↔ DOUBLE PRECISION 대응. 테이블·컬럼·인덱스 전부 두 엔진 모두.
- 테이블 정의 전 '-- vN:' 주석으로 근거. 인덱스는 CREATE INDEX IF NOT EXISTS를 스키마 안에 함께.

### 2.2 조회 헬퍼 (_q_once / _q / _qd)
- _q_once(sqlite_sql, pg_sql, params, fetch): 실제 실행 + commit.
- _q(...): 연결 사망 시 1회 재연결 재시도(예외 CONNECTION_ERRORS, Serverless 유휴 커넥션 대비).
- _qd(sql, params, fetch): '?' 플레이스홀더 단일 SQL → pg용 %s 자동 변환(동적 SQL).
- 쌍형 SQL: INSERT ... ON CONFLICT (key) DO NOTHING(pg) ↔ INSERT OR IGNORE(sqlite).

### 2.3 _MIGRATE_COLUMNS + _migrate (마이그레이션)
- 신규 컬럼은 SCHEMAS 갱신 + _MIGRATE_COLUMNS = ((table, col, sqlite_decl, pg_decl), ...)에 등록.
- _migrate(): Postgres는 ALTER TABLE ADD COLUMN IF NOT EXISTS 네이티브, SQLite는 pragma_table_info 검사 후 ALTER. 전부 개별 가드.
- 신규 테이블은 CREATE TABLE IF NOT EXISTS만으로 충분(기존 테이블 컬럼 추가만 migrate 필요).

### 2.4 id 반환 관례
- RETURNING id(pg) + cur.lastrowid(sqlite). INSERT 후 재읽기 금지(다중 인스턴스 레이스).

---

## 3. 예외 처리 관례

- 전용 예외 클래스 + 모듈 정의, raise ... from e로 원인 체인.
- err_prefix: HTTP 계층에서 전용 예외 → 명확한 상태 코드 정규화.
  - DraftGenerationError → HTTPException(503, str(e)) (server L358-362)
  - ImageGenerationError → HTTPException(503, str(e)) (L783-785)
  - NaverAPIError → 검색 스냅샷 실패 시 logger.warning + graceful 폴백(_unavailable_search_evidence).
  - 입력 오류 → HTTPException(400, 한국어 안내), 미존재 → HTTPException(404, "not found").
- graceful 폴백: 외부 실패가 전체를 죽이지 않게. logger.warning 후 계속 진행.
- 파이프라인 실패는 키워드/챕터 단위 격리(except (NaverAPIError, ImageGenerationError) ... continue, content_batch L237-247).
- 키/환경 미설정은 fail-closed(config L136-139, create_app L256-258).

---

## 4. 테스트 관례

### 4.1 구조
- tests/test_<module>.py, import pytest, 파일 상단 한글 주석.
- DB 테스트: tmp_path SQLite + make_db(tmp_path) 헬퍼:

    def make_url(tmp_path): return f"sqlite:///{tmp_path / 't.db'}"
    def make_db(tmp_path):
        d = Database(make_url(tmp_path)); d.init(); return d
    # 마지막 d.close()

### 4.2 외부 차단
- conftest.py autouse 픽스처(_clear_gemini_api_key·_clear_external_api_keys)가 외부 키/네트워크 차단.
- LLM 호출은 runner mock(결정성) 또는 monkeypatch.setattr(module, "fn", ...)(모듈 import 이름 바인딩 주의).

### 4.3 서버 테스트
- TestClient + create_app(cfg) 테스트용 cfg 주입. require_token은 env=development로 우회.

### 4.4 시간(KST)
- config.today_kst()·now_kst_iso() 사용(KST = timezone(timedelta(hours=9)) 고정 오프셋).

---

## 5. config 관례 (config.py)

- load_config(load_env=True)이 dict 반환, os.getenv("KEY", default).
- int: int(os.getenv("KEY", "default")), bool: os.getenv("KEY", "0") == "1".
- 요구 기반 기본값 dict(DEFAULT_FOCUS_SEEDS·DEFAULT_CPC_TIERS)도 config에 노출.
- fail-closed: 비개발 환경 필수 키 미설정 시 raise RuntimeError.
- 서버는 create_app(cfg) — 테스트·배포 모두 cfg 주입(app = create_app(config_mod.load_config())).

---

## 6. 시간 처리

- today_kst() → date(기준일), now_kst_iso() → ISO 문자열(이력·스탬프).
- minutes_ago_kst_iso(n), datetime.now(KST). 예산은 time.monotonic() + deadline = started + budget 패턴.

---

## 7. 버전 주석 관례

- 변경 코드 앞 '# v37:' 마커로 배치/단계 구분 + 이유 + 예방 결함 기록.
- KDP 코드는 기존 최고 버전 이후 'v31:' 등으로 시작(현재 conftest.py에 v30 마커 존재).

---

## 8. 배치 진입점 관례 (collect.py main)

    def main():
        logging.basicConfig(level=logging.INFO, format=...)
        cfg = config_mod.load_config()
        result = run_collection(cfg, trigger="schedule")
        if result.get("locked"): logger.info(...); raise SystemExit(0)
        logger.info("완료: ...", ...)
        if <실패 조건>: raise SystemExit(1)   # GH Actions 실패 알림
        raise SystemExit(0)
    if __name__ == "__main__":
        sys.exit(main())

- 표준 출력 대신 구조화 로그, 종료 코드로 GH Actions 결과 반영(실패 임계·전량 실패 → exit 1).
- GitHub Actions는 python collect.py 실행, DATABASE_URL 등 시크릿 env 주입.

---

## 9. 서버리스(Vercel) 제약 관례

- 모듈 상수로 예산 명시(테스트가 결정적으로 패치): FORTUNE_PUBLISH_BUDGET_SECONDS=55, SECTION_IMAGE_WINDOW_SECONDS=38.
- 생성·LLM·검증은 GH Actions 배치 전용, API는 경량(조회·다운로드·상태 전이)만.
- /api 프리픽스 스트립 미들웨어, strip_api_prefix, create_app 내부 require_token 의존.

---

*작성: 개발팀 · 1단계 산출물 1/2 · 상태: 관례 추출 완료*
