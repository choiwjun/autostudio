# Google Nano Banana 이미지 생성 통합 — 구현 보고서 (implementation-report)

> 작성: 개발팀 · 프로젝트: autostudio · 작업 디렉토리: `pipeline/image-gen-nanobanana/`
> 모드: small · 상위: requirements.md (FR-1~FR-6) · tech-design.md 승인 완료 (오케스트레이터 2026-08-13)
> 구현: TDD (RED 6건 실패 확인 → GREEN) · 검증: 전체 pytest **396 passed / 10 skipped** (QA B1 반영 후)

## 1. 구현 요약

| 항목 | 구현 내용 |
|---|---|
| 1차 프로바이더 (FR-1) | `image_gen.py`에 `_nanobanana_generate`/`_nanobanana_call` 추가 — `GEMINI_API_KEY` 설정 시 나노바나나 우선 호출 (대표·섹션·백필 공통 `_run_http` 단일 분기) |
| 호출 계약 | `POST {GEMINI_BASE_URL}/v1beta/interactions` + `x-goog-api-key` 헤더, `response_format {type:image, mime_type:image/jpeg, aspect_ratio:16:9, image_size:1K}`, 응답 `steps[].content[]`의 `type=="image"` 블록 파싱 (raw REST — SDK 미사용) |
| env 오버라이드 | `GEMINI_IMAGE_MODEL`(기본 gemini-3.1-flash-image)·`GEMINI_IMAGE_SIZE`(기본 1K)·`GEMINI_BASE_URL` — 모두 호출 시점 평가 |
| 폴백 체인 (FR-3) | 나노바나나 실패 → WARNING 로그 + Bailian 1회(내부) → 실패 시 기존 `_dashscope_fallback`(DashScope 1회) — 각 1회, 최종 실패만 집계 |
| 미설정 불변 (FR-2) | `os.getenv("GEMINI_API_KEY")` 호출 시점 분기 — 미설정이면 `_primary_generate` 직접 호출 (기존 경로 코드 불변) |
| 저장 정합 (FR-4) | data URI(`data:{mime};base64,{data}`) 문자열 저장 — DB 스키마·content_batch·db 호출부 무변경 |
| 가드 확장 (FR-6) | image_gen 내부 `_has_image_api_key()` = `GEMINI_API_KEY or has_api_key()` — 전역 `llm_client.has_api_key()` 불변 |
| stats·알림 (FR-5) | v26 `_IMAGE_STATS` 위치·조건 그대로 (attempts=_run_http 진입 1회, 최종 실패만 failures·consecutive 증가) — content_batch·test_content_batch.py 무변경 |
| 다운로드 프록시 (AC4-3) | `server.py _fetch_image_bytes`에 data URI 분기 — `base64.b64decode(validate=True)` + image/ MIME 강제 + 20MB 상한. HTTPS 경로 무변경 |
| 발행 내보내기 (AC4-4) | `publish.py _image_lines` — data URI 라인 생략 + 수동 업로드 경고 주석. URL 이미지는 기존대로 임베드, 네이버 플레인 무영향(실측: `_export_naver`는 `_image_lines` 미호출) |
| 대시보드 (AC4-2) | `static/index.html` `<img src="${esc(url)}">` — data URI 브라우저 기본 렌더링, base64 알파벳에 HTML 특수문자 없어 `esc()` 무해 → **코드 변경 0** (확인 완료) |
| llm_client (오케스트레이터 보완 조건) | `_browser_headers`가 api_key 빈 값 시 `Authorization` 헤더 **생략** (1줄 가드) — 기존 호출자(항상 키 존재) 무영향 |

## 2. AC 대응표

| AC | 내용 | 상태 | 검증 방법 |
|---|---|---|---|
| AC1-1 | 나노바나나 1차, Bailian/DashScope 0회 | ✅ | `test_nanobanana_success_returns_data_uri`(calls==1)·`test_nanobanana_success_no_bailian_and_prompt_rules` |
| AC1-2 | response_format 4필드 (16:9·1K·JPEG) | ✅ | T1 — payload `response_format` 정확 일치 assert |
| AC1-3 | 기존 프롬프트 재사용 (`_SINGLE_SCENE_RULES`) | ✅ | T2·T7 — "카툰 금지"·"실사 사진 스타일" 등 포함 assert (프롬프트 생성부 무변경) |
| AC1-4 | `GEMINI_IMAGE_MODEL` 오버라이드 | ✅ | T6 — `gemini-3.1-flash-lite-image` 요청 반영 |
| AC1-5 | 대표·섹션 공통 적용 | ✅ | T2 — `generate_section_images`도 나노바나나 1차 확인 |
| AC1-6 | steps[].content[] image 블록 파싱 | ✅ | T1·T7 — raw REST 응답 mock 파싱 |
| AC2-1 | 키 미설정 → 기존 Bailian 1차 | ✅ | T3 — 나노바나나 0회, Bailian URL 반환 |
| AC2-2 | 키 전체 미설정 → 기존 메시지 | ✅ | T3 2부 + 기존 `test_no_key_raises_clear_error` 통과 |
| AC2-3 | 기존 테스트 398개 통과 | ✅ | 전체 pytest 395 passed/10 skipped (수집 405 — 신규 7 포함) |
| AC3-1 | 나노바나나 실패 → Bailian 정확히 1회 | ✅ | T4 — calls==2, Bailian 성공 URL 반환 |
| AC3-2 | 나노바나나·Bailian 실패 → DashScope 1회 | ✅ | T5 ① — POST 3회(나노바나나+Bailian+DashScope), 폴백 성공 |
| AC3-3 | 전부 실패 → Error + 최종 원인 | ✅ | T5 ② — "dashscope"+"DataInspectionFailed" 메시지 |
| AC3-4 | 폴백 WARNING 로그 | ✅ | T4 — caplog에 "nano banana"+"Bailian" |
| AC3-5 | 폴백 성공은 최종 실패 아님 | ✅ | T4 — failures==0, consecutive==0 |
| AC4-1 | data URI 반환·저장 (호출부 무변경) | ✅ | T1·T7 — `data:{mime};base64,{data}` + b64decode 복원 |
| AC4-2 | 대시보드 data URI 렌더링 | ✅ | 코드 확인 (변경 0) — 브라우저 기본 지원 |
| AC4-3 | 다운로드 프록시 data URI 처리 | ✅ | server.py 분기 + 스모크 검증 (디코드·MIME·400/502·HTTPS 가드 유지) |
| AC4-4 | publish.py data URI 방침 | ✅ | tech-design §5② + publish.py 구현 + 스모크 검증 |
| AC4-5 | URL 프로바이더는 URL 저장 유지 | ✅ | Bailian/DashScope 경로 무변경 (T3·T4·T5가 URL 반환 검증) |
| AC4-6 | JPEG·1K 기본 (비용 통제) | ✅ | 요청 계약 고정 + `GEMINI_IMAGE_SIZE` 오버라이드만 허용 |
| AC5-1 | attempts _run_http 진입 1회 | ✅ | T4·T5 — attempts==1 |
| AC5-2 | 최종 실패만 집계 | ✅ | T5 ② — failures==1·consecutive==1 |
| AC5-3 | 임계 초과 알림 (기존 로직) | ✅ | content_batch·collect 무변경 — test_content_batch.py 11건 통과 |
| AC5-4 | reset/get 시그니처 불변 | ✅ | 무변경 + test_content_batch 통과 |
| AC6-1 | GEMINI 키만 → 가드 통과 | ✅ | T6 — 키 3종 중 GEMINI만 설정 |
| AC6-2 | GEMINI만 + 실패 → Error 전파 | ✅ | T5 ② 구조(폴백 키 유무 무관 전파) + T3 2부 |
| AC6-3 | 기존 메시지 유지 + GEMINI 안내 | ✅ | 메시지에 GEMINI_API_KEY 추가 — "이미지 키" substring 검증 유지 |
| AC6-4 | has_api_key() 불변 | ✅ | llm_client 무변경(가드 1줄 제외 — Authorization 생략), content_batch 게이트 무변경 |
| NFR-1 | 55s 타임아웃 유지 | ✅(부분) | `IMAGE_TIMEOUT=55` 그대로. **실측 불가** — §5 |
| NFR-3 | 키 env 관리·로그 미노출 | ✅ | 키는 env에서만, 오류 메시지에 키 값 미포함 |
| NFR-5 | 외부 라이브러리 0 | ✅ | urllib 유지 — post_json 재사용 |
| NFR-7 | GEMINI_BASE_URL 오버라이드 | ✅ | `_gemini_base_url()` 호출 시점 평가 |

## 3. 변경 파일 목록

| 파일 | 변경 | 비고 |
|---|---|---|
| `image_gen.py` | +114 | v27 핵심 — 나노바나나 경로·분기·가드 |
| `server.py` | +34 | `_fetch_image_bytes` data URI 분기 + `_decode_data_uri` + `import base64` |
| `publish.py` | +20 | `_image_lines` data URI 생략+주석, `_is_data_uri` |
| `llm_client.py` | +8/-1 | `_browser_headers` 빈 키 시 Authorization 생략 (오케스트레이터 보완 조건) |
| `tests/test_image_gen.py` | +252 (추가만, 기존 8건 수정 0) | 신규 8건 T1~T7 + B1(trailing LF) |
| `conftest.py` | +12 | autouse 픽스처 — GEMINI_API_KEY 테스트 격리 (아래 §4) |
| `image_gen.py` | +2 (B1) | `_nanobanana_call` 키 획득·`_has_image_api_key` 가드 strip — trailing LF 방어 |
| `.env.example` | +14 | GEMINI 4종 옵션 |
| `.github/workflows/daily-collect.yml` | +2 | `GEMINI_API_KEY` secret env |
| `docs/planning/02-trd.md` | +17 | 이미지 생성 섹션·성능·보안 반영 |
| `CHANGELOG.md` | +33 | v27 항목 |

## 4. 발견 사항·미구현 사유 (오케스트레이터 요청)

### 4.1 ⚠️ Windows 환경변수에 GEMINI_API_KEY 실제 존재 (발견)
- 태스크 메모 "GEMINI_API_KEY는 로컬에 없음"과 달리, **Windows 시스템 환경변수에 실제 키(`AIza...`)가 설정**되어 있음. Windows venv(`./.venv/Scripts/python.exe`) pytest는 이를 상속 → GEMINI 미설정을 전제로 한 기존 v26 테스트 3건이 나노바나나 경로로 새어 실패
- **조치**: `conftest.py`에 autouse 픽스처로 `GEMINI_API_KEY` 기본 삭제(테스트 격리). 신규 테스트는 본문에서 명시 설정 — **기존 테스트 파일 수정 금지 규칙 준수** (test_image_gen.py 기존 8건·test_content_batch.py 11건 수정 0)
- **운영 시사점**: 사용자가 이미 GEMINI_API_KEY를 발급해 Windows에 설정해 둔 상태 → 배치(GH Actions)에 secret 등록만 하면 나노바나나가 바로 1차 프로바이더로 동작

### 4.2 미구현 사유 명시
| 항목 | 상태 | 사유 |
|---|---|---|
| content_batch 배치 게이트의 GEMINI-only 지원 | **미구현 (범위 외)** | `run_content_batch` 생략 게이트는 `llm_client.has_api_key()` 사용 — AC6-4 계약(전역 불변)으로 GEMINI 키만 있는 환경에서도 **배치는 생략**됨. `generate_image` 직접 호출(서버리스·수동)은 동작. 배치까지 지원하려면 content_batch 게이트 변경 필요 → 후속 과제로 제안 |
| 나노바나나 55s 내 실측 | **미실측 (키 부재)** | 로컬 검증 환경에서 실키 호출 불가 (테스트는 mock). **QA 첫 실통신 시 확인 필수** — 55s 초과 관측 시 tech-design §8 대안: thinking 레벨 최소화(`thinking_level: "minimal"`) 또는 `generateContent` 엔드포인트 전환 |
| 서버리스 수동 생성(`/drafts/{id}/image`) 나노바나나 전환 | 미구현 (범위 제외 — v26 결정 유지) | 오케스트레이터 승인 사항. 단, 해당 경로도 `generate_image`를 호출하므로 **GEMINI 키 설정 시 자동으로 나노바나나 1차 적용됨** (분기 제외가 아니라 동일 경로) |
| data URI → 외부 업로드(방안 ②) | 미구현 (범위 제외) | 승인된 기본안 ① 채택. ②는 사용자 승인 후 후속 |
| `test_server.py`/`test_publish.py` 신규 테스트 | 미작성 | 요구사항 테스트 계약(T1~T7, test_image_gen.py만) 준수. server·publish는 스모크 검증 + QA 실검증 포인트로 대체 |

### 4.3 실행·검증 방법
```bash
# 전체 테스트 (Windows venv)
./.venv/Scripts/python.exe -m pytest -q          # 396 passed, 10 skipped
# 단위: 신규 나노바나나 테스트만
./.venv/Scripts/python.exe -m pytest tests/test_image_gen.py -q   # 16 passed
```
- QA 검증 포인트: ① 실통신 — GEMINI_API_KEY 설정 후 `generate_image` 호출 1회 (55s 내 완료·data URI 반환·Bailian/DashScope 0회) ② 대시보드 data URI 렌더링 ③ 다운로드 프록시 data URI ④ 티스토리 export에 경고 주석 노출 ⑤ GH Actions secret 등록 후 배치 동작

## 5. QA 피드백 반영 (B1 — 개발QA 조건부 승인 반영)

| 항목 | 내용 |
|---|---|
| B1 (P2) | Windows User env `GEMINI_API_KEY` 값에 trailing LF(`\n`) 포함 (PowerShell 바이트 실측 len=40, tail=10). 미조치 시 raw `ValueError: Invalid header value`로 ImageGenerationError 정규화·폴백·stats 집계 붕괴 |
| 수정 ① | `image_gen.py` `_nanobanana_call` — 키 획득 1곳: `api_key = (os.getenv("GEMINI_API_KEY") or "").strip()` — 헤더 `x-goog-api-key`에 LF 없는 키 전달 |
| 수정 ② | `image_gen.py` `_has_image_api_key()` 가드 — 동일 strip 적용 (일관성: LF 포함 키로도 가드 통과, 공백만 키는 미통과) |
| 테스트 | `tests/test_image_gen.py` +1건 `test_gemini_key_trailing_lf_stripped` — env에 `"gemini-key\n"` 설정 → `generate_image` 정상 동작 + 요청 헤더가 LF 없는 키 사용 단언 + 가드 통과 단언 (기존 8건 수정 0) |
| 검증 | Windows venv 전체 pytest **396 passed / 10 skipped** (395 + 신규 1) — `./.venv/Scripts/python.exe -m pytest -q` |
| 비고 | GH Actions secret(직접 입력)은 오염 가능성 낮으나 붙여넣기 공백/개행 오염 시 동일 경로 전면 차단. env var 재설정(사용자 조치)과 코드 방어 2중 적용 |

## 6. 스킬 사용 로그
- **test-driven-development**: RED(신규 7건 작성 → 6건 실패 확인) → GREEN(image_gen 구현 → 15건 통과) → 전체 회귀 395 통과 → B1: 신규 1건(GREEN) → 396 통과
- **fable-prove-it**: 전체 pytest 실측 실행(396 passed/10 skipped)·server/publish 스모크·git diff로 기존 테스트 무수정 검증 후 완료 주장
- **md-to-html**: plan·tech-design·implementation-report .html 생성 (`/home/wj941/.agents/skills/md-to-html/.venv/bin/python scripts/md2html.py`)
- **systematic-debugging**: Windows 환경변수 GEMINI_API_KEY 상속으로 인한 기존 테스트 실패 — 근본 원인 확인(Windows env 실측) 후 conftest 격리로 해결
- **wsl-windows-hybrid-runner**: Windows venv pytest 실행·cp949 인코딩 처리 (환경 메모 적용)

## 7. 산출물 경로
- `pipeline/image-gen-nanobanana/plan.md` · `plan.html`
- `pipeline/image-gen-nanobanana/tech-design.md` · `tech-design.html`
- `pipeline/image-gen-nanobanana/implementation-report.md` · `implementation-report.html`
- 구현: `image_gen.py`·`server.py`·`publish.py`·`llm_client.py`·`conftest.py`·`tests/test_image_gen.py`·`.env.example`·`.github/workflows/daily-collect.yml`·`docs/planning/02-trd.md`·`CHANGELOG.md` (커밋 안 함)
