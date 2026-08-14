# Google Nano Banana 이미지 생성 통합 — 구현 계획 (간이 plan, small 모드)

> 작성: 개발팀 · 프로젝트: autostudio · 작업 디렉토리: `pipeline/image-gen-nanobanana/`
> 상위 문서: `requirements.md` (요구사항팀, FR-1~FR-6) · 오케스트레이터 승인: small 모드, FR-4 data URI 저장 기본 확정
> 기준: v26 코드 (2026-08-13, 테스트 388 passed / 10 skipped = 398 수집)

## 1. 목표

`GEMINI_API_KEY`가 설정된 환경에서는 이미지 생성(대표·섹션·백필 전 경로)의 1차 프로바이더를
**Google Nano Banana**(기본 `gemini-3.1-flash-image`, 16:9·1K·JPEG)로 전환하고,
실패 시 기존 체인(Bailian → DashScope)으로 폴백한다. `GEMINI_API_KEY` 미설정 환경은
**기존 동작 100% 불변** + 기존 테스트 398개 전부 통과가 최우선 제약이다.

핵심 난제는 나노바나나가 URL이 아닌 **base64 인라인 데이터**를 반환하는 점 — 승인된 기본안
**① data URI 저장**(`data:{mime};base64,{data}`)으로 DB 스키마 무변경·인프라 신설 없이 정합한다.

## 2. 수용 기준 (요구사항 AC → 구현 검증)

| ID | 수용 기준 | 구현 방법 (요약) |
|---|---|---|
| AC1-1/AC1-5 | GEMINI 키 설정 + 성공 → 나노바나나 1차, Bailian·DashScope 0회 (대표·섹션 공통) | `_run_http` 진입부 키 분기 → `_nanobanana_generate` 1차 (공통 단일 지점) |
| AC1-2 | `response_format {type:image, mime_type:image/jpeg, aspect_ratio:16:9, image_size:1K}` | 요청 본문에 고정 포함, `GEMINI_IMAGE_SIZE` env로 크기만 오버라이드 |
| AC1-3 | 프롬프트는 `_build_prompt`/`section_image_prompt` 그대로 | 프롬프트 생성부 무변경 (재작성 없음) |
| AC1-4 | `GEMINI_IMAGE_MODEL` env 오버라이드 | 호출 시점 `os.getenv` 평가 (테스트 친화) |
| AC1-6 | `steps[].content[]`에서 `type=="image"` 블록의 `data`+`mime_type` 파싱 | raw REST — SDK 미사용, steps 순회 파서 |
| AC2-1~AC2-3 | 키 미설정 시 나노바나나 0회 + 기존 체인 + 기존 테스트 398개 통과 | `os.getenv("GEMINI_API_KEY")` 호출 시점 분기 — 미설정 경로 코드 불변 |
| AC3-1~AC3-5 | 나노바나나 실패 → Bailian 1회 → 실패 시 DashScope 1회, 최종 실패만 집계 | `_nanobanana_generate` 내 Bailian 재시도 + 기존 `_dashscope_fallback` 체인 |
| AC4-1 | data URI 문자열 반환·저장 (호출부 무변경) | `data:{mime};base64,{data}` 문자열 — `str` 타입 그대로 |
| AC4-2 | 대시보드 `<img src>` data URI 렌더링 | `static/index.html` 확인만 (브라우저 기본 지원 — 코드 무변경) |
| AC4-3 | 다운로드 프록시 data URI 처리 | `server.py _fetch_image_bytes`에 data URI 분기 (base64 디코드 + 크기·MIME 검사) |
| AC4-4 | publish.py data URI 방침 명시 | `_image_lines`에서 data URI 라인 **생략 + 경고 주석** (수동 업로드 안내). 네이버 플레인 무영향 |
| AC4-5 | URL 기반 프로바이더는 URL 저장 유지 | Bailian/DashScope 경로 무변경 — 혼합 저장 허용 |
| AC5-1~AC5-4 | v26 stats·알림 동일 적용 | `_IMAGE_STATS` 위치 불변, `test_content_batch.py` 수정 금지 |
| AC6-1~AC6-4 | GEMINI 키만으로 동작 (가드 확장) | `image_gen` 내부 `_has_image_api_key()` — 전역 `has_api_key()` 불변 |
| NFR-1 | 55s 타임아웃 유지 + 실측 | `IMAGE_TIMEOUT=55` 유지. 실측 불가(로컬 키 없음) → thinking 최소화 옵션 명시 |
| NFR-5 | 외부 라이브러리 금지, urllib 유지 | `llm_client.post_json` 재사용 + `headers={"x-goog-api-key": ...}` |
| NFR-7 | `GEMINI_BASE_URL` 오버라이드 | 호출 시점 `os.getenv` 평가 (테스트·차단 대응) |

## 3. 구현 범위

### 변경 (소스)
| 파일 | 변경 성격 |
|---|---|
| `image_gen.py` | ⭐ 핵심 — 나노바나나 1차 경로 + `_run_http` 분기 + 내부 키 가드 확장 (FR-6) |
| `server.py` | `_fetch_image_bytes` data URI 분기 추가 (AC4-3, 최소 변경) |
| `publish.py` | `_image_lines` data URI 생략+경고 주석 (AC4-4) |

### 변경 (문서·설정)
| 파일 | 변경 |
|---|---|
| `.env.example` | `GEMINI_API_KEY`·`GEMINI_IMAGE_MODEL`·`GEMINI_IMAGE_SIZE`·`GEMINI_BASE_URL` |
| `.github/workflows/daily-collect.yml` | `GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}` env 1줄 |
| `docs/planning/02-trd.md` | 이미지 생성 섹션에 나노바나나 반영 |
| `CHANGELOG.md` | v27 항목 추가 |
| `tests/test_image_gen.py` | 신규 7건 추가 (기존 8건 **수정 금지**) |

### 비변경 (명시적 제외)
- `llm_client.py` — `has_api_key()`·`post_json` 시그니처 불변 (내부 동작 무변경)
- `content_batch.py`·`collect.py`·`db.py` — stats 집계·알림·저장 호출부 무변경
- `tests/test_content_batch.py` — 알림 테스트 11건 그대로
- DB 스키마 · 스토리지 인프라 · 서버리스 수동 생성(`/drafts/{id}/image`) 경로

## 4. 테스트 계획 (TDD, tests/test_image_gen.py 신규 7건)

| # | 시나리오 | 검증 AC |
|---|---|---|
| T1 | GEMINI 키 + 나노바나나 성공 → data URI 반환, 요청 본문·헤더 검증 | AC1-1, AC1-2, AC1-6, AC4-1 |
| T2 | GEMINI 키 + 성공 → Bailian/DashScope 0회, 프롬프트 `_SINGLE_SCENE_RULES` 포함 | AC1-1, AC1-3 |
| T3 | GEMINI 키 미설정 → Bailian 1차 그대로, 나노바나나 0회 | AC2-1, AC2-2 |
| T4 | 나노바나나 실패 → Bailian 1회 → 성공 URL 반환 (최종 실패 아님) | AC3-1, AC3-5 |
| T5 | 나노바나나·Bailian 실패 → DashScope 1회 / 전부 실패 → Error + failures 집계 | AC3-2, AC3-3, AC5-2 |
| T6 | GEMINI 키만 설정 → 가드 통과 + `GEMINI_IMAGE_MODEL` 오버라이드 | AC6-1, AC1-4 |
| T7 | data URI 파싱(b64decode 복원) + 폴백 WARNING 로그 | AC4-1, AC3-4 |

검증 게이트: `./.venv/Scripts/python.exe -m pytest -q` 전체 통과 (기존 388 + 신규 7 = 395 passed, 10 skipped).

## 5. 문서 산출물

`plan.md/html` · `tech-design.md/html` (승인 게이트 후) · `implementation-report.md/html`

## 6. 리스크

| 리스크 | 대응 |
|---|---|
| GEMINI_API_KEY 로컬 부재 → 실통신 검증 불가 | mock 기반 테스트 + QA 실검증 포인트 명시 (report) |
| 55s 내 응답 여부 미실측 (thinking 모델) | tech-design에 thinking 최소화 옵션·generateContent 대안 명시 |
| `Authorization: Bearer`(빈 값) + `x-goog-api-key` 병행 — 게이트웨이 거부 가능성 | 빈 Bearer는 미인증으로 처리되는 것이 일반적. 실패 시 `llm_client._browser_headers`에 빈 키 스킵 가드 1줄 추가 예정 (리스크 기록) |
| data URI DB 용량 증가 (초안당 최대 ~2~5MB) | JPEG 1K 기본 (AC4-6), 스키마 무변경 — 수용 |
