# 이미지 프로바이더 폴백 + 쿼터 모니터링 알림 — 요구사항 명세

> 작성: 요구사항팀 · 프로젝트: autostudio · 작업 디렉토리: `pipeline/image-fallback/`
> 근거: `docs/planning/13-image-fallback.md` (제안서, 2026-08-11) — 사용자가 **권장안 A+B 소형 패키지** 승인
> 원본 요청: VERIFICATION.md §6 미해결 항목 — 이미지 생성 Bailian Token Plan 단일 프로바이더, 쿼터 소진/장애 시 대표·섹션 이미지 전량 누락 + 실패가 로그에만 남아 무감지

## 1. 배경 (실측 현황)

| 항목 | 실측 결과 (2026-08-11) |
|---|---|
| 이미지 프로바이더 | **Bailian Token Plan 단일** — `image_gen.py` (모델 `wan2.7-image`, 크기 `1280*720`, timeout 55s) |
| 키 해석 | `llm_client.resolve_api_key()` — `BAILIAN_TOKEN_PLAN_API_KEY` → `DASHSCOPE_API_KEY` 순 폴백 (둘 다 Alibaba 계열). `.env.example`에는 `DASHSCOPE_API_KEY` 미기재 |
| 호출 경로 | `generate_image()`(대표) / `generate_section_images()`(섹션 최대 8장) → 공통 `_run_http()` → `llm_client.post_json()` |
| 실패 처리 | content_batch: `ImageGenerationError` catch → **warning 로그 후 스킵** (이미지 없는 초안 유지). 텍스트 LLM은 OpenCode Go ↔ Bailian 이중 폴백(v23)이 있으나 **이미지는 폴백 없음** |
| 쿼터 모니터링 | **없음** — 실패율/연속 실패 집계도, 알림도 없음 |
| 알림 전파 (중요) | `collect.py main()`은 ① 자동완성 차단 ② `errors` 있고 스냅샷 0건일 때만 `exit 1`. **ERROR 로그만으로는 GH Actions 잡이 실패하지 않음** → 실패 전파를 달성하려면 `collect.py` 최소 연동 필요 (§6 FR-5) |

## 2. 목표 & 비목표

### 목표
1. Bailian 이미지 쿼터 소진/장애 시에도 대표·섹션 이미지 생성이 계속되도록 **DashScope 폴백 경로** 제공
2. 이미지 실패 누적을 운영자가 감지할 수 있도록 **실패 집계 + 임계 초과 알림** (GH Actions 실패 전파)
3. 위 두 기능을 **배치(GH Actions) 기준, 최소 변경**으로 구현 (TDD, 테스트 5건)

### 비목표
- 서버리스 수동 생성(`server.py` `/drafts/{id}/image`) 폴백·알림 — **범위 제외** (사용자 결정)
- DB 스키마 변경 / 대시보드 UI 표시 — **범위 제외**
- Slack·이메일 등 별도 알림 채널 — **범위 제외** (GH Actions 실패 전파가 기본 알림, 사용자 결정)
- 타사 이미지 프로바이더(DALL-E·Stability 등) 도입 — **범위 제외** (제안서 옵션 C 비권장)

## 3. 타깃 (영향 파일)

| 파일 | 변경 성격 |
|---|---|
| `image_gen.py` | 폴백 경로 추가 (권장안 A) — 대표·섹션 공통 `_run_http` 레벨 |
| `content_batch.py` | 실패 집계 + 임계 판정 + ERROR 로그 + 결과 dict 확장 (권장안 B) |
| `collect.py` | **최소 연동** — `image_alert` 시 `exit 1` (실패 전파 실현, §6 FR-5) |
| `tests/test_image_gen.py` | 폴백 테스트 3건 |
| `tests/test_content_batch.py` | 집계·임계 테스트 2~3건 |
| `docs/planning/02-trd.md` | 이미지 섹션에 폴백·모니터링 반영 |
| `.env.example` | `DASHSCOPE_API_KEY` 옵션 항목 추가 (미설정 = 폴백 비활성 명시) |
| `CHANGELOG.md` · `docs/VERIFICATION.md` | 갱신 (§6 미해결 항목 해소 표시) |

## 4. 범위

### 포함
- 배치(GH Actions daily-collect)의 대표 이미지·섹션 이미지 생성 전 경로 (신규 생성 + 백필)
- Bailian 실패 → DashScope(`wanx2.1-t2i-turbo`) 1회 재시도
- 배치 실행 단위 실패 집계 (시도/최종 실패/연속 실패)
- 임계 초과 시 ERROR 로그 + `collect.py` 연동으로 GH Actions 잡 실패
- TDD 테스트 5건 + 문서 3종 반영

### 제외
- `server.py` 서버리스 수동 생성 경로 (폴백·알림 모두)
- DB 스키마·마이그레이션, 대시보드/프론트 변경
- Slack·이메일·PagerDuty 등 외부 알림 연동
- 비동기 작업 폴링·재시도 큐 등 인프라 신설

## 5. 용어

| 용어 | 정의 |
|---|---|
| Bailian | 기본 이미지 프로바이더 (Token Plan, `wan2.7-image`) |
| DashScope | 폴백 이미지 프로바이더 (Aliyun DashScope, `wanx2.1-t2i-turbo`) |
| 최종 실패 | 폴백 포함 최종 시도까지 실패한 이미지 생성 호출 (호출부에서 `ImageGenerationError` 발생) |
| 시도(attempt) | 대표·섹션·백필을 통틀어 이미지 생성 호출 1회 (키 미설정 가드에서 중단되는 경우 제외) |
| 연속 실패 | 성공 없이 이어진 최종 실패 건수 |
| 실패율 | 배치 실행 내 `최종 실패 건수 / 시도 건수` |

## 6. 기능 요구사항 (FR)

### FR-1 — DashScope 폴백 활성화 (M)
Bailian 호출이 실패하면, `DASHSCOPE_API_KEY`가 설정된 경우 DashScope `wanx2.1-t2i-turbo`로 **1회 재시도**한다. 대표 이미지(`generate_image`)와 섹션 이미지(`generate_section_images`) 모두 적용.

**수용 기준 (검증 가능)**
- [ ] AC1-1: Bailian 호출이 실패(`ImageGenerationError` — HTTP 4xx/5xx·타임아웃·네트워크·응답 파싱 실패 모두)하고 `DASHSCOPE_API_KEY`가 설정되어 있으면, DashScope 엔드포인트로 동일 프롬프트·동일 파라미터(크기 `1280*720`, n=1)로 재시도가 정확히 1회 발생한다
- [ ] AC1-2: 폴백(DashScope)이 성공하면 성공 이미지 URL을 반환한다 — 호출부(`content_batch`)는 변경 없이 기존 성공 흐름(저장·카운트)을 탄다
- [ ] AC1-3: 폴백 시도는 **1회로 제한**된다 (2회 이상 재시도 금지 — 비용·지연 통제)
- [ ] AC1-4: 폴백 발생 시 WARNING 로그에 실패 원인(원본 예외 메시지)과 폴백 사용이 기록된다 (디버깅 가능성)

### FR-2 — 키 미설정 시 graceful 비활성 (M)
`DASHSCOPE_API_KEY`가 없으면 폴백 경로가 동작하지 않는다 — **기존 동작 100% 불변**.

**수용 기준**
- [ ] AC2-1: `DASHSCOPE_API_KEY` 미설정 + Bailian 실패 → DashScope 호출이 발생하지 않고, 기존과 동일하게 `ImageGenerationError`가 전파된다
- [ ] AC2-2: 키 미설정 가드(`llm_client.has_api_key()` False → "이미지 키가 필요합니다")와 오류 메시지는 기존 그대로 유지된다 (`tests/test_image_gen.py::test_no_key_raises_clear_error` 계속 통과)
- [ ] AC2-3: `BAILIAN_TOKEN_PLAN_API_KEY`만 설정된 환경에서는 코드 경로·동작이 변경 전과 동일하다 (폴백 관련 코드 미실행)

### FR-3 — 폴백 최종 실패 시 예외 전파 (M)
폴백(DashScope)도 실패하면 기존과 동일하게 `ImageGenerationError`를 전파한다 — 배치의 키워드 단위 격리·경고 로그·스킵 동작에 회귀가 없다.

**수용 기준**
- [ ] AC3-1: Bailian·DashScope 모두 실패 → `ImageGenerationError` 발생, 메시지에 최종 실패 원인 포함
- [ ] AC3-2: `content_batch`의 기존 try/except 격리(한 키워드 실패가 배치 전체 중단 안 함)가 그대로 동작한다

### FR-4 — 이미지 실패 집계 (M)
`content_batch.run_content_batch()` 실행 단위로 이미지 생성 시도·최종 실패를 집계하고, 결과 dict에 노출한다.

**수용 기준**
- [ ] AC4-1: 결과 dict에 `image_attempts`(시도 수)·`image_failures`(최종 실패 수)가 추가된다 (기존 키 `drafts_created`·`draft_images_created`는 유지)
- [ ] AC4-2: 백필 경로(`_backfill_images`)와 신규 생성 경로(`_create_draft`)의 실패가 모두 집계된다 (대표·섹션 포함)
- [ ] AC4-3: 집계는 프로세스 메모리 내에서만 수행 — DB 스키마 변경·신규 테이블 없음
- [ ] AC4-4: (부수 효과) `collect.py`가 결과를 `collection_runs.result`에 저장하므로 배치 실행 이력에 실패 집계가 자연 기록된다

### FR-5 — 임계 초과 알림 (M)
**연속 5건 실패 또는 실패율 50% 초과** 시 알림한다.

**수용 기준**
- [ ] AC5-1: 배치 내 이미지 최종 실패가 **연속 5건**에 도달하면 ERROR 레벨 로그 1건이 출력된다 (시도 수와 무관 — 예: 시도 5건 전부 실패)
- [ ] AC5-2: 배치 내 **실패율 50% 초과**(최종 실패/시도 > 0.5) 시 ERROR 로그 1건이 출력된다 (소표본 노이즈 방지: 실패율 판정은 시도 5건 이상일 때만 적용 — 연속 5건 규칙은 시도 수 무관)
- [ ] AC5-3: 임계 미만(예: 시도 5건 중 1건 실패)이면 ERROR 로그가 **없고** 기존 warning 로그만 유지된다
- [ ] AC5-4: ERROR 로그에는 집계 수치(시도/실패/연속 실패)와 원인 파악 힌트가 포함된다
- [ ] AC5-5: 임계 초과 시 결과 dict에 `image_alert: True`가 포함되고, **`collect.py main()`은 `image_alert`이면 `exit 1`** → GH Actions 잡 실패 → GitHub 기본 알림(메일)로 운영자 인지
- [ ] AC5-6: 임계 초과가 아니어도 배치 자체는 정상 완주한다 (부분 성공 보존 — 기존 설계 유지)

> **근거 (실측)**: ERROR 로그만으로는 GH Actions 잡이 실패하지 않는다 (`collect.py main()`은 특정 조건에서만 exit 1). "GH Actions 실패 전파로 알림"을 실제로 달성하는 유일한 경로가 `collect.py`의 `image_alert` → `exit 1` 연동이다. 변경량은 ~3줄 수준.

## 7. 비기능 요구사항 (NFR)

| ID | 영역 | 요구사항 |
|---|---|---|
| NFR-1 | 성능 | 폴백 재시도 1회 제한, 타임아웃 기존 55s 유지 — 이미지 1건 최대 지연은 기존의 2배(약 110s)까지 허용 (배치 예산 1200s 내, GH Actions 60분 내) |
| NFR-2 | 보안 | 키는 환경변수로만 관리 (기존 패턴 유지), 로그·오류 메시지에 키 값 미포함, 프론트 노출 없음 |
| NFR-3 | 호환 | 기존 pytest 전체 통과 (현재 377 passed), 기존 public API 시그니처·반환형 불변 |
| NFR-4 | 의존성 | 외부 라이브러리 추가 금지 — 표준 라이브러리 `urllib` 유지 (GH Actions·Vercel 바이너리 제약) |
| NFR-5 | 운영 | 임계 초과 시 하루 1회(GH Actions 일일 배치) 실패 알림 — 실시간 알림 아님을 명시 |
| NFR-6 | 관측성 | 실패 집계가 배치 실행 이력(`collection_runs.result`)에 기록되어 사후 분석 가능 |

## 8. 제약

1. **DashScope 별도 계정 키 전제** — Bailian과 같은 Alibaba 계정이면 쿼터 소진이 동시 발생해 폴백이 무의미. `DASHSCOPE_API_KEY`가 별도 계정 키임을 전제 (키 미설정 시 graceful 비활성 — 사용자 결정)
2. 외부 라이브러리 추가 금지 (NFR-4)
3. DB 스키마 변경 금지, 서버리스 범위 제외 (사용자 결정)
4. TDD — 테스트를 먼저 작성하고 구현 (사용자 승인)

## 9. 우선순위 (M/S/C)

| 우선순위 | 항목 |
|---|---|
| **M (Must)** | FR-1 폴백 활성, FR-2 graceful 비활성, FR-3 예외 전파, FR-4 실패 집계, FR-5 임계 알림·실패 전파, 테스트 5건, 문서 반영 (02-trd·.env.example·CHANGELOG·VERIFICATION) |
| **S (Should)** | AC1-4 폴백 로그, AC4-4 실행 이력 기록, AC5-3 임계 미만 무회귀 테스트, 에지 케이스 테스트 (DASHSCOPE 키만 있는 환경) |
| **C (Could)** | 대시보드 표시·DB 스키마 (후속 작업), 서버리스 수동 생성 폴백 (후속 작업) |

## 10. 성공 기준 (종합)

1. **Bailian 장애/쿼터 소진 시나리오**: `DASHSCOPE_API_KEY`가 있으면 대표·섹션 이미지가 폴백으로 생성·저장된다 (신규·백필 경로 모두)
2. **키 미설정 환경**: 동작이 변경 전과 동일하고, 기존 테스트 전부 통과
3. **연속 5건 또는 실패율 50% 초과**: ERROR 로그 + `image_alert` → GH Actions 잡 실패로 운영자 인지 가능
4. **임계 미만**: 기존 warning 로그만, 잡은 성공
5. **문서 정합**: 02-trd.md 이미지 섹션·.env.example·CHANGELOG·VERIFICATION.md §6에 반영되어 제안서의 "기획 미반영" 해소

## 11. 오픈 질문 · 가정

### 해소된 결정 (사용자 승인 완료 — 인터뷰 생략 사유)
| 질문 | 결정 |
|---|---|
| DashScope 별도 키 보유 여부 | 키 있으면 폴백 활성, 없으면 비활성(graceful) |
| 알림 채널 | GH Actions 로그/실패 전파 (별도 Slack/이메일 없음) |
| 서버리스 수동 생성 실패 | 범위 제외 (이번엔 배치 기준) |

### 가정 (assumptions)
1. `DASHSCOPE_API_KEY`는 Bailian과 **다른 계정**의 키로 운영한다 (같은 계정이면 쿼터 소진 동시 발생 — 폴백 의미 없음)
2. 폴백 트리거는 "Bailian 호출 실패" 전부로 한다 (사유별 분기 없음 — 단순·일관·테스트 용이). 401(키 오류)도 폴백 대상 (DashScope 키가 유효하면 정상 생성 가능)
3. `DASHSCOPE_API_KEY`만 설정된 환경에서는 Bailian 호출이 실패(401 등)한 뒤 폴백으로 동작한다 (불필요한 1회 호출 발생 — 기능상 문제 없음, 개선 여지는 tech-design에서 판단)
4. `wanx2.1-t2i-turbo`는 동기 응답을 지원한다 (비동기 task 폴링 불필요) — 구현 시 실제 응답 형식 실측 후 DashScope 응답 파싱(`output.results[].url`) 확정
5. 실패율 판정은 시도 5건 이상일 때만 적용한다 (소표본 100% 알림 노이즈 방지) — 제안서 수치의 명시적 해석

### 미해결 (구현 시 확정)
| 질문 | 소유자 | 상태 |
|---|---|---|
| ERROR 로그만으로는 GH Actions 실패 불가 — `collect.py` 연동(exit 1) 범위 포함 | 사용자/오케스트레이터 | **요구사항 FR-5로 포함 제안** (변경 ~3줄). 반대 시 알림은 로그 노출까지만 가능 |
| DashScope 동기 응답 형식 실측 (`image-synthesis` 응답 구조) | 개발팀 | 구현 시 실측 |
| 폴백 실패 사유를 ERROR 로그에 포함할지 (원본 예외 메시지) | 개발팀 | AC5-4 권장 |

## 12. 테스트 요구사항 (TDD, 5건)

| # | 파일 | 시나리오 | 검증 (수용 기준) |
|---|---|---|---|
| T1 | `tests/test_image_gen.py` | Bailian 실패 + `DASHSCOPE_API_KEY` 설정 → DashScope 재시도 1회, 성공 URL 반환 | AC1-1, AC1-2, AC1-3 |
| T2 | `tests/test_image_gen.py` | Bailian 실패 + 키 미설정 → 폴백 미호출, 기존 예외 전파 | AC2-1 |
| T3 | `tests/test_image_gen.py` | 폴백(DashScope)도 실패 → `ImageGenerationError` 전파 (원본 원인 포함) | AC3-1 |
| T4 | `tests/test_content_batch.py` | 연속 5건 실패 → ERROR 로그 + 결과 dict `image_alert=True` | AC5-1, AC5-5 |
| T5 | `tests/test_content_batch.py` | 실패율 50% 초과(시도 5+ 중 3건 실패) → ERROR 로그 / 임계 미만(1건 실패) → ERROR 없음 | AC5-2, AC5-3 |

## 13. 작업 규모 모드 판정

**모드: `small`** (요구사항팀 판정)

| 기준 | 판정 근거 |
|---|---|
| 성격 | 단일 기능 묶음 — "이미지 생성 복원력" (폴백 + 모니터링은 한 기능의 두 축) |
| 요구사항 수 | 핵심 FR 5개 (FR-1~5) + 문서·테스트 — small 기준(1~5개) 충족 |
| 영향 범위 | 소스 3개 파일 내외(`image_gen.py`·`content_batch.py` + `collect.py` 최소 연동), 테스트 2개 파일, 문서 3종 — 신규 서비스·아키텍처 변경 없음 |
| 조사 필요성 | **외부 조사 불필요** (경쟁·시장 조사 무관, API 스펙은 구현 시 실측) |
| 인프라 | DB 스키마·서버리스·배포 인프라 무변경 |

→ **small 모드 절차**: ① 요구사항팀(본 문서) → ⑧ 개발팀(간이 plan/tech-design + TDD 구현) → ⑨ 개발QA팀(수용 기준 검증)

---

*산출물: 본 requirements.md · requirements.html · 요약 답신 (모드 판정 포함)*
