# 이미지 프로바이더 폴백 + 쿼터 모니터링 알림 — QA 검증 보고서 (dev-qa-report.md)

> 작성: 개발QA팀 · 일자: 2026-08-13 · 모드: small · 대상: `pipeline/image-fallback/`
> 검증 기준: `requirements.md` AC1-1~AC5-6 + NFR 6종 · 입력: `plan.md`·`tech-design.md`(승인 완료)·`implementation-report.md`
> 검증 방식: 전체 테스트 재실행 + 코드 리뷰 + **경계값·회귀·연동 시나리오 독립 재현** (mock 기반, 커밋 없음)

---

## 1. 최종 판정

# ✅ 승인 (조건부 — 필수 수정 1건, 커밋 전 반영 권장)

수용 기준 **AC 21건 전부 PASS**, NFR 6종 충족, 신규 테스트 9건 포함 전체 **386 passed / 10 skipped (0 실패)**,
semgrep 보안 스캔 0건. 실키 실측 불가 항목(유효한 DASHSCOPE_API_KEY 부재)은 공식 문서 계약과 코드 대조로 검증했다.

**필수 수정 (P2, 커밋 전 반영)**: DashScope 엔드포인트 호스트가 **베이징 지역 전용(`dashscope.aliyuncs.com`)으로 하드코딩** —
운영 키가 싱가포르(국제) 키면 폴백이 항상 인증 실패한다. `DASHSCOPE_BASE_URL` env 오버라이드(또는 기본값 조정) + `.env.example` 리전 명시 필요.
(수정량 ~3줄 — 재검증 불필요한 경미 수정, 상세 §5)

---

## 2. 실행 증거 요약

| 검증 항목 | 실행 | 결과 |
|---|---|---|
| 전체 pytest | `./.venv/Scripts/python.exe -m pytest -q` | **386 passed, 10 skipped** (기존 377 + 신규 9, 0 실패) |
| 대상 테스트 3파일 | `pytest tests/test_image_gen.py tests/test_content_batch.py tests/test_collect.py -v` | **46 passed** (v26 신규 9건 포함 전부 통과) |
| 보안 정적 스캔 | qa-tools semgrep `--config p/secrets --config p/python` (변경 소스 4파일) | **Findings 0** (187 rules) |
| 경계값 판정 함수 | `image_alert_triggered` 11개 케이스 독립 재현 | **전부 PASS** (연속 5/실패율 50% 경계·소표본 가드 포함) |
| stats 누적·연속 리셋 | mock POST/GET로 4회 호출 (실패→폴백성공, 성공, 실패→폴백성공, 실패→폴백실패) | attempts=4, failures=1, consecutive=1 — **PASS** |
| 키 미설정 회귀 | BAILIAN 키만 설정 + 401 → 폴백 미호출, 원본 예외·메시지 불변 | POST 1회뿐 — **PASS** |
| AC1-4 폴백 로그 | caplog 캡처 | WARNING 1건: 원본 원인(500: upstream down) + `wanx2.1-t2i-turbo` 포함 — **PASS** |
| AC4-4 note 병기 | `run_collection` E2E (content_batch mock) → DB `collection_runs.note` 확인 | `{"image_attempts":5,"image_failures":5,"image_alert":true}` — **PASS** |
| AC5-5 exit 전파 | `collect.main()` 6개 케이스 (alert/미임계/차단/전량실패/부분오류/alert 단독) | 전부 기대 exit code — **PASS** |
| AC4-2 신규 경로 집계 | 신규 초안 생성 경로를 실제 `_run_http` 경유로 재현 (대표 이미지 실패) | attempts=1, failures=1 — **PASS** |
| AC3-2 격리 | 초안 생성 예외 3건 → 배치 완주 + 오류 로그 3건 | **PASS** |
| public 시그니처 | HEAD 대비 AST 비교 (소스 4파일) | 기존 함수 시그니처 **불변** (`post_json`은 선택 `headers=None` 추가뿐) |
| 외부 의존성 | 변경 파일 import 검사 | 표준 라이브러리 + 프로젝트 내부 모듈만 (NFR-4) |
| 실키 실측 | 유효한 DASHSCOPE_API_KEY 없음 | **미수행 (공식 문서 계약 대조로 대체)** — §4 참조 |

---

## 3. 수용 기준별 판정 (AC → PASS/FAIL/미검증)

| AC | 내용 | 판정 | 근거 (실행 증거) |
|---|---|---|---|
| AC1-1 | Bailian 실패(전 사유)+키 설정 → DashScope 재시도 정확히 1회, 동일 프롬프트·1280\*720·n=1 | ✅ PASS | T1 — POST 2회(1차+폴백 1회), 프롬프트·`{"size":"1280*720","n":1}`·`X-DashScope-Async: enable` 단언 + 독립 mock 재현 |
| AC1-2 | 폴백 성공 시 URL 반환, 호출부 무변경 | ✅ PASS | T1 (`url == dashscope url`) + content_batch 성공 흐름 코드 리뷰 (변경 없음) |
| AC1-3 | 재시도 1회 제한 | ✅ PASS | T1 `len(calls)==2` + 코드 구조 단일 호출 확인 |
| AC1-4 | 폴백 WARNING (원인+사용) | ✅ PASS | T1 (caplog 429·모델명) + 독립 캡처 (500: upstream down + wanx2.1-t2i-turbo) |
| AC2-1 | 키 미설정 → 폴백 미호출·기존 예외 전파 | ✅ PASS | T2 (POST 1회, 메시지 "401" 불변) + 독립 재현 (calls=1, stats 실패 집계) |
| AC2-2 | 키 미설정 가드·오류 메시지 유지 | ✅ PASS | `test_no_key_raises_clear_error` 통과, 가드 위치 코드 리뷰 (generate_image 진입부 불변) |
| AC2-3 | BAILIAN 키만 환경 = 변경 전과 동일 | ✅ PASS | T2 경로 + llm_client diff에서 `resolve_api_key`/`has_api_key` 무변경 확인 |
| AC3-1 | 폴백도 실패 → 최종 원인 포함 예외 | ✅ PASS | T3 (`DataInspectionFailed` 포함) + 독립 재현 (`...after dashscope fallback...: task failed: X boom`) |
| AC3-2 | content_batch 키워드 단위 격리 유지 | ✅ PASS | `test_draft_failure_is_isolated` + 독립 재현 (예외 3건 → 배치 완주, 오류 로그 3건) |
| AC4-1 | 결과 dict에 image_attempts·image_failures, 기존 키 유지 | ✅ PASS | T4/T5 + 키 미설정 스킵 경로 기본값 독립 확인 |
| AC4-2 | 백필+신규(대표+섹션) 모두 집계 | ✅ PASS | T4/T5 (백필 5건) + **독립 재현**: 신규 초안 경로 대표 이미지 실패 → attempts=1·failures=1 |
| AC4-3 | 메모리 내 집계, DB 스키마 무변경 | ✅ PASS | 모듈 dict 구현, git diff에 db.py·스키마 변경 없음 |
| AC4-4 | 배치 실행 이력 기록 | ✅ PASS (승인 대안) | `collection_runs`에 result 컬럼 **실측 부재 확인**(db.py 스키마) → note JSON 병기 E2E 검증 + 대시보드(`static/index.html`)가 found_raw만 읽어 미지 키 무해 확인 |
| AC5-1 | 연속 5건 → ERROR 1건 (시도 무관) | ✅ PASS | T4 + 경계: triggered(3,3,5)·(4,4,5) 모두 True |
| AC5-2 | 시도 5건+ 실패율 50% 초과 → ERROR / 소표본 가드 | ✅ PASS | T5a(3/5=60%) + 경계: (8,4)=50% 정확히 → **no alert**, (4,4,4) 소표본 → no alert |
| AC5-3 | 임계 미만 → ERROR 없음 | ✅ PASS | T5b (1/5=20% → ERROR 레코드 0건) |
| AC5-4 | ERROR 로그에 집계 수치+힌트 | ✅ PASS | "시도 %d건, 최종 실패 %d건, 연속 실패 %d건 — …키·쿼터 점검 필요" 단언 (T4) + collect.py 병기 로그 |
| AC5-5 | image_alert=True + collect main() exit 1 | ✅ PASS | T7a + 독립 6케이스 exit 검증 (alert 단독·차단·전량실패 우선순위 포함) |
| AC5-6 | 임계 초과여도 배치 정상 완주 | ✅ PASS | T4/T5 결과 dict·draft 저장 정상 + T7b (exit 0) |

**NFR 판정**

| NFR | 내용 | 판정 | 근거 |
|---|---|---|---|
| NFR-1 | 폴백 1회·55s 예산, 1건 최대 ~110s | ✅ PASS (소폭 여유) | 폴링 예산=timeout 내 강제(deadline), 최대 오버슛 ~4s (sleep 3s+GET 1s) — 1200s 배치 예산 내 충분 |
| NFR-2 | 키 env 전용·로그 미노출 | ✅ PASS | semgrep 0건 + 코드 리뷰 (Bearer 헤더 전용, 로그·예외 메시지에 키 값 없음) |
| NFR-3 | 기존 테스트 전체 통과·public API 불변 | ✅ PASS | 386 passed / 10 skipped, AST 시그니처 비교 (추가만 존재) |
| NFR-4 | 외부 라이브러리 금지 | ✅ PASS | 변경 4파일 import 검사 — 표준 라이브러리+내부 모듈만 |
| NFR-5 | 하루 1회 배치 알림 (실시간 아님) | ✅ PASS | GH Actions 일일 잡 exit 1 전파 설계·구현 확인 |
| NFR-6 | 실행 이력 기록 (사후 분석) | ✅ PASS | note JSON 병기 E2E 확인 |

**미검증 (실키)**: AC1-1/1-2/3-1의 **실제 DashScope API 응답** 파싱 — 유효한 키 부재로 실호출 불가.
공식 문서(help.aliyun.com/alibabacloud.com, 2026-08-13 실측)와 코드 대조 결과 **계약 정합** 확인 (§4).

---

## 4. DashScope API 계약 실측 대조 (QA 집중 포인트 1 — 실키 불가 대체 검증)

공식 문서 `text-to-image-v2-api-reference` (영문·중문 모두 직접 수신해 대조) — **구현 형식 전부 정합**:

| 계약 요소 | 공식 문서 | 구현 | 판정 |
|---|---|---|---|
| task 생성 엔드포인트 | `POST /api/v1/services/aigc/text2image/image-synthesis` | 동일 경로 ✅ | PASS |
| 비동기 헤더 | `X-DashScope-Async: enable` (누락 시 "current user api does not support synchronous calls") | 동일 ✅ | PASS |
| 요청 본문 | `{"model", "input":{"prompt"}, "parameters":{"size","n"}}` (wan2.5 이하 구버전 프로토콜) | 동일 ✅ | PASS |
| size 규격 (wan2.2 이하) | 가로·세로 [512, 1440] | 1280\*720 유효 ✅ | PASS |
| n | 1~4 (기본 4, 비용 통제 위해 1 권장) | n=1 ✅ | PASS |
| 프롬프트 한도 (wan2.1) | 500자 (초과 시 자동 절단) | 실측 402~447자 ✅ (여유 — §5-3) | PASS |
| task 생성 응답 | `output.task_id` + `task_status` | `data["output"]["task_id"]` ✅ | PASS |
| task 조회 | `GET /api/v1/tasks/{task_id}` | 동일 경로 ✅ | PASS |
| 성공 응답 | `output.results[].url` (URL 24h 유효) | `output["results"][0]["url"]` ✅ | PASS |
| 실패 응답 | `output.task_status=FAILED` + code/message | code/message 예외 포함 ✅ | PASS |
| 폴링 권장 | ~10s 간격 권장 (RPS 20 제한) | 3s 고정 — 0.33 RPS로 제한 내 ✅ | PASS (P3) |
| **호스트** | 베이징 `dashscope.aliyuncs.com` / 싱가포르 `dashscope-intl.aliyuncs.com` / 워크스페이스 `{WsId}.ap-southeast-1.maas.aliyuncs.com` — **리전별 키 불호환** | **`dashscope.aliyuncs.com` 하드코딩 (베이징 전용)** | ⚠️ **P2 (§5-1)** |

---

## 5. 발견 사항 (심각도 순)

### 5-1. [P2 — 필수 수정] DashScope 호스트가 베이징 리전 전용으로 하드코딩
- **위치**: `image_gen.py` `DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com"` (및 파생 엔드포인트 2곳)
- **근거 (공식 문서 실측)**: "华北2(北京)、新加坡…拥有独立的 API Key 与请求地址，不可混用，跨地域调用将导致鉴权失败" —
  `dashscope.aliyuncs.com`은 베이징 키 전용, 싱가포르(국제) 키 전용 고전 도메인은 `dashscope-intl.aliyuncs.com`.
- **영향**: 본 프로젝트 Bailian이 싱가포르 리전(`token-plan.ap-southeast-1`)이므로, 운영자가 국제 콘솔의 DashScope 키를 쓰면
  폴백 호출이 항상 인증 실패 → **FR-1의 실제 가치(이미지 복원)가 발휘되지 않을 가능성이 높음**.
  (다만 실패는 graceful — 집계·임계·알림·배치 완주는 정상 동작하므로 서비스 마비는 없음)
- **권장 수정 (~3줄)**: `DASHSCOPE_BASE_URL` env 오버라이드 추가(기본값 현행 유지) + `.env.example`에
  "리전 일치 키 사용(베이징 `dashscope.aliyuncs.com` / 싱가포르 `dashscope-intl.aliyuncs.com`)" 명시. 또는 운영 리전 확정 후 기본값 조정.
- **재현**: 코드 레벨 확정 (실키 불가 — 키 없음). 수정 후 별도 QA 재검증 불필요 (env 오버라이드 추가는 무회귀).

### 5-2. [P3] 폴링 간격 3s 고정 — 문서 권장(~10s)보다 공격적
- 영향: RPS 20 제한 대비 0.33 RPS로 문제 없음. 최대 오버슛 ~4s (sleep 3s + GET 타임아웃 1s) — NFR-1 "약 110s" 여유 내. 개선 권장 사항.

### 5-3. [P3] wan2.1 프롬프트 500자 한도 대비 여유 53~98자
- 실측: 대표 402자 / 대표+썸네일 447자 / 섹션 431자. 초장문 키워드·제목 시 초과 가능하나 공식 문서상 **자동 절단** (graceful). 모니터링 권장.

### 5-4. [P4] note의 이미지 키는 attempts>0일 때만 기록
- `image_attempts=0`(키 미설정 스킵) 실행은 note에 이미지 키 없음 — 분석 대상이 없으므로 무해. 현행 유지 가능.

### 5-5. [P4] 신규 초안 경로의 stats 집계 테스트 부재 (스위트 기준)
- 기존 `test_creates_draft_and_images_for_top_keyword`는 content_batch 레벨 monkeypatch로 `_run_http`를 우회해
  stats 집계를 직접 검증하지 않음 (백필 경로 T4/T5만 직접 커버). **구조적으로는 보장 확인** (개발QA 독립 재현 §2 —
  신규 경로 실패 → attempts=1·failures=1). 후속 테스트 1건 추가 권장.

---

## 6. 회귀·호환 검증 (QA 집중 포인트 2~5)

| 포인트 | 검증 | 결과 |
|---|---|---|
| 2. 임계 판정 경계값 | 11케이스 독립 재현 (연속 5 시도무관 / 시도 4 전부 실패 → no alert / 50% 정확히 → no alert / 60% → alert / 소표본 가드) | 전부 기대 일치 |
| 3. collect 연동·우선순위 | blocked·전량 실패·image_alert 각 exit 1, 부분 오류+무임계 exit 0 — 기존 조건 무회귀 | 전부 기대 일치 |
| 4. FR-2 회귀 | 키 미설정 환경: 폴백 0회·원본 예외·가드 메시지·`resolve_api_key`/`has_api_key` 무변경, 전체 386 통과 | 통과 |
| 5. AC4-4 대안 | `collection_runs` 스키마 실측(결과 컬럼 부재) → note JSON 병기 E2E (DB 저장 확인) + 대시보드 파싱 무해 확인 | 통과 |

---

## 7. 스킬 사용 로그 (dev-qa-team 스펙 요구)

| 스킬 | 적용 지점 |
|---|---|
| qa-tools | semgrep 정적 보안 스캔 실행 (`--config p/secrets --config p/python`, 변경 소스 4파일 — Findings 0), pytest 재실행 |
| md-to-html | 본 보고서 `.html` 병행 생성 |
| verification-before-completion | 모든 판정을 실행 증거(테스트 출력·독립 재현 스크립트)와 대조 후 기재 — 추측 없는 PASS/FAIL |
| code-review (방법론) | diff 심사 — 시그니처 불변(AST), 키 로그 미노출, 외부 라이브러리 0건, DB 스키마 무변경 |

---

## 8. 산출물

- 본 보고서: `pipeline/image-fallback/dev-qa-report.md` · `dev-qa-report.html`
- 검증 대상 산출물: `pipeline/image-fallback/` (requirements·plan·tech-design·implementation-report 각 .md/.html)
- 커밋: **안 함** (오케스트레이터가 게이트 통과 후 일괄 커밋 — P2 필수 수정 선반영 권장)
