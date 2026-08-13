# 이미지 프로바이더 폴백 + 쿼터 모니터링 알림 — 구현 보고서 (implementation-report.md)

> 작성: 개발팀 · 일자: 2026-08-13 · 모드: small (TDD) · 승인: 오케스트레이터 (tech-design 게이트 ✅)
> 요구사항: `pipeline/image-fallback/requirements.md` · 설계: `pipeline/image-fallback/tech-design.md`

## 1. 구현 요약

| 영역 | 구현 내용 | 파일 |
|---|---|---|
| 폴백 (FR-1~FR-3) | Bailian 실패 → DashScope `wanx2.1-t2i-turbo` 1회 재시도 — **`_run_http` 레벨**(대표·섹션 공통). 비동기(task 생성 + 3s 폴링, 예산 55s) | `image_gen.py` (+`llm_client.py` GET·헤더 지원) |
| 집계 (FR-4) | 모듈 stats(attempts/failures/consecutive_failures) — public 시그니처 불변. content_batch가 배치 단위 reset/get | `image_gen.py`·`content_batch.py` |
| 임계·알림 (FR-5) | 연속 5건 또는 시도 5건+ 실패율 50% 초과 → ERROR 로그 + `image_alert=True` → `collect.main()` `exit 1` (GH Actions 실패 전파) | `content_batch.py`·`collect.py` |
| 실행 이력 (AC4-4) | `collection_runs`에 result 컬럼 없음(실측) → **note JSON에 이미지 집계 병기** (스키마 무변경) | `collect.py` |
| 테스트 | 신규 11건 (T1~T3·T-P2 폴백, T4·T5a·T5b·T6·T-P4 집계·임계, T7a·T7b collect 전파) + 기존 1건 기대값 갱신 | `tests/` 3파일 |
| 문서 | 02-trd.md·.env.example·CHANGELOG(v26)·VERIFICATION §6 해소 표기 | `docs/` |

## 2. 수용 기준 대응표 (AC → 증거)

| AC | 내용 | 구현 | 검증 증거 |
|---|---|---|---|
| AC1-1 | Bailian 실패(전 사유)+키 설정 → DashScope 1회 재시도 (동일 프롬프트·1280*720·n=1) | ✅ `_run_http`→`_dashscope_fallback`→`_dashscope_generate` | T1 + AC검증 스크립트(POST 2회=1차+폴백, 프롬프트·파라미터 일치 단언) |
| AC1-1 보강 (QA P2) | DashScope **리전별 호스트** — 베이징 기본 `dashscope.aliyuncs.com`, `DASHSCOPE_BASE_URL` env 오버라이드 (싱가포르·국제=`dashscope-intl.aliyuncs.com`, 호출 시점 평가) | ✅ `_dashscope_base_url()` — POST·폴링 GET 모두 동일 호스트 사용 | T-P2 (env 오버라이드 시 intl 호스트로 POST·GET 단언) |
| AC1-2 | 폴백 성공 시 URL 반환 — 호출부 무변경 | ✅ 성공 시 `output.results[0].url` 반환 | T1 (`url == dashscope url`), content_batch 기존 성공 흐름 유지 |
| AC1-3 | 재시도 1회 제한 | ✅ `_dashscope_generate` 단일 호출 구조 | T1 (post_json 총 2회 단언) |
| AC1-4 | 폴백 WARNING 로그 (원인+사용) | ✅ `logger.warning("image API primary failed (%s) — retry via DashScope %s")` | T1 (caplog에 429·모델명), AC검증 로그 확인 |
| AC2-1 | 키 미설정 → 폴백 미호출·기존 예외 전파 | ✅ `os.getenv("DASHSCOPE_API_KEY")` 없으면 카운터만 갱신 후 원본 re-raise | T2 (POST 1회뿐, 메시지 "401" 불변) |
| AC2-2 | 키 미설정 가드·오류 메시지 유지 | ✅ 가드 위치 불변 (`generate_image` 진입부) | 기존 `test_no_key_raises_clear_error` 통과 + AC검증 |
| AC2-3 | Bailian 키만 설정 환경 = 변경 전과 동일 | ✅ 폴백 코드 미실행 (T2 경로) | T2 + 전체 386 통과 |
| AC3-1 | 폴백도 실패 → 최종 원인 포함 예외 | ✅ `ImageGenerationError("...after dashscope fallback...: {e}") from e` | T3 (`DataInspectionFailed` 포함) |
| AC3-2 | content_batch 격리 유지 | ✅ 변경 없음 (try/except 구조 그대로) | 기존 `test_draft_failure_is_isolated` 통과 |
| AC4-1 | 결과 dict에 image_attempts·image_failures (기존 키 유지) | ✅ `{"drafts_created", "draft_images_created", "image_attempts", "image_failures", "image_alert"}` | T4/T5/T8 |
| AC4-2 | 백필+신규 모두 집계 (대표·섹션) | ✅ stats는 `_run_http`에서 집계 — 두 경로 모두 경유 (섹션 per-call 포함) | T4/T5 (백필 5건) + **T-P4 (신규 초안 경로: 대표 성공·섹션1 실패·섹션2 성공 → attempts 3·failures 1)** |
| AC4-3 | 메모리 내 집계, DB 무변경 | ✅ 모듈 dict — DB 스키마 터치 없음 | git diff에 db.py 없음 |
| AC4-4 | 배치 실행 이력 기록 | ⚠️ **실측 대비 변경**: `collection_runs`에 result 컬럼 **없음** → 승인받은 대안 **note JSON 병기** (`image_attempts/failures/alert`) | 코드 리뷰 + `test_reject_rate_recorded_in_run_note` 통과(기존 키 보존) |
| AC5-1 | 연속 5건 → ERROR 1건 | ✅ `image_alert_triggered` 연속 5건 규칙 | T4 (ERROR 레코드 1건+) |
| AC5-2 | 시도 5건+ 실패율 50% 초과 → ERROR | ✅ `attempts >= 5 and failures/attempts > 0.5` | T5a (3/5=60%→alert), T6 경계 |
| AC5-3 | 임계 미만 → ERROR 없음 | ✅ 판정 함수 거짓 시 로그 없음 | T5b (1/5=20%→레코드 0건) |
| AC5-4 | ERROR 로그에 집계 수치+힌트 | ✅ "시도 %d건, 최종 실패 %d건, 연속 실패 %d건 — Bailian/DashScope 키·쿼터 점검 필요" | T4 메시지 단언 |
| AC5-5 | image_alert=True + collect main() exit 1 | ✅ merge 3줄 + `if result.get("image_alert"): raise SystemExit(1)` (+ERROR 로그) | T7a (exit code 1), T7b (exit 0) |
| AC5-6 | 임계 초과여도 배치 정상 완주 | ✅ 집계는 종료 시점 판정 — 배치 흐름 무중단 | T4/T5 결과 dict + draft 저장 정상 |

**NFR**: NFR-1 폴백 1회·55s 예산(폴링 포함 ~110s 최대) ✅ · NFR-2 키는 env 전용·로그/예외에 키 값 미포함(코드 리뷰 확인) ✅ ·
NFR-3 **388 passed / 10 skipped (기존 377 + 신규 11, 0 실패)**, public 시그니처 불변(AST 확인) ✅ · NFR-4 표준 라이브러리만(urllib 유지) ✅ ·
NFR-5 일일 배치 알림(실시간 아님 명시) ✅ · NFR-6 note JSON 기록 ✅

## 3. QA 피드백 반영 (개발QA팀 조건부 승인)

| ID | 내용 | 반영 |
|---|---|---|
| P2 (필수) | DashScope 호스트 리전 하드코딩 — 국제(싱가포르) 키면 인증 실패 | ✅ `DASHSCOPE_BASE_URL` env 오버라이드 (기본 `dashscope.aliyuncs.com`=베이징, 국제=`dashscope-intl.aliyuncs.com` 주석 명시, 호출 시점 평가) + `.env.example` 항목 + 테스트 T-P2 (intl 호스트로 POST·폴링 GET 단언) |
| P4 (권장) | 신규 초안 경로 stats 집계 자동 테스트 부재 | ✅ T-P4 — 대표 성공·섹션1 실패·섹션2 성공 → attempts 3·failures 1·alert False + 섹션 격리(1장만 저장) 단언 |
| P3 2건 | 폴링 3s 고정·프롬프트 500자 | 기록만 (후속 개선 — 이번 범위 아님) |

## 4. 실측 대비 변경 (승인 완료 — 오케스트레이터 게이트)

| # | 요구사항 가정 | 실측 결과 | 채택 설계 |
|---|---|---|---|
| 1 | wanx2.1-t2i-turbo 동기 응답 `output.results[].url` (요구 §11 가정 4) | **HTTP 동기 미지원** — 공식 문서 "wan2.5 이하 모델: 不支持 HTTP 同步调用" (2026-08-13 실측) | **비동기 흐름**: POST image-synthesis(`X-DashScope-Async: enable`) → GET /tasks/{id} 폴링(3s, 예산 55s) → `output.results[].url` (응답 형식은 동일) |
| 2 | AC4-4 "collection_runs.result에 저장" | **result 컬럼 없음** (스키마: new_keywords/snapshotted/errors/note만) | **note JSON 병기** — 스키마 무변경(NFR 제약)으로 사후 분석 충족, 대시보드 미지 키 무시 확인 |

미구현 사유 (범위 제외 — 요구사항 §4·§8 준수): 서버리스(`server.py`) 폴백·알림, DB 스키마/마이그레이션, 대시보드 UI, Slack·이메일 알림, 외부 라이브러리. 전부 후속 작업으로 명시.

## 5. 실행·검증 방법

```bash
# 1) 전체 테스트 (Windows venv — WSL에서 직접 실행)
./.venv/Scripts/python.exe -m pytest -q          # → 386 passed, 10 skipped

# 2) 신규 테스트만
./.venv/Scripts/python.exe -m pytest tests/test_image_gen.py tests/test_content_batch.py tests/test_collect.py -q

# 3) 운영 환경 동작 (실키 필요)
#   - DASHSCOPE_API_KEY 설정 + BAILIAN_TOKEN_PLAN_API_KEY 설정 → 배치(GH Actions daily-collect) 실행
#   - Bailian 실패 시 로그: "image API primary failed (...) — retry via DashScope wanx2.1-t2i-turbo"
#   - 연속 5건/실패율 50% 초과 시: ERROR "이미지 생성 실패 임계 초과: 시도 N건..." + 잡 실패(exit 1) → GitHub 메일
#   - collection_runs.note에 image_attempts/image_failures/image_alert JSON 기록 확인
```

### 실키 실측 미수행 항목 (개발QA팀 확인 권장)
- 유효한 `DASHSCOPE_API_KEY`가 없어 **실제 DashScope 호출 검증은 미수행** — 공식 문서 계약 기반 구현, 파싱 실패는 전용 예외로 정규화됨.
  개발QA팀이 키 보유 시: POST 응답 `output.task_id`·폴링 `output.results[].url` 형식 실측 권장 (형식 상이 시 `_dashscope_generate` 파싱만 수정).
- **리전 확인 필수 (P2)**: 사용 중인 키의 발급 리전이 싱가포르·국제면 `DASHSCOPE_BASE_URL=https://dashscope-intl.aliyuncs.com` 설정 필요 (기본값은 베이징).

## 6. 코드 리뷰 요약 (리스크 중심)

- **정상**: public 시그니처 불변 (AST 비교), 기존 오류 메시지·헤더 구성 불변, 키 값 로그 미노출(NFR-2), 외부 라이브러리 0건 추가, DB 스키마 무변경
- **minor**: ① 폴링 sleep 3s 고정 — 예산 초과 최대 ~3s 오버슛 가능 (허용 범위) ② `_IMAGE_STATS` 모듈 전역 — 단일 프로세스 배치 기준, 서버리스 동시성에선 미사용(무해)
- **의도적 계약 변경 1건**: `run_content_batch` 결과 dict 확장 → `test_skips_without_llm_key` 정확 일치 단언 갱신 (승인됨)

## 7. 산출물

- `pipeline/image-fallback/plan.md`·`plan.html` / `tech-design.md`·`tech-design.html` / `implementation-report.md`·`implementation-report.html`
- 소스: `image_gen.py`·`content_batch.py`·`collect.py`·`llm_client.py`·`tests/test_image_gen.py`·`tests/test_content_batch.py`·`tests/test_collect.py`
- 문서: `docs/planning/02-trd.md`·`.env.example`·`CHANGELOG.md`·`docs/VERIFICATION.md`
- 커밋: **안 함** (오케스트레이터가 게이트 통과 후 일괄 커밋)
