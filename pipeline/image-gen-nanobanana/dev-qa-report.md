# Google Nano Banana 이미지 생성 통합 — 개발QA 검증 보고서 (dev-qa-report)

> 작성: 개발QA팀 · 프로젝트: autostudio · 작업 디렉토리: `pipeline/image-gen-nanobanana/`
> 모드: small · 상위 문서: requirements.md(FR-1~FR-6, AC1-1~AC6-4, NFR 7종) · tech-design.md(승인 완료) · implementation-report.md
> 검증일: 2026-08-13 · 검증 환경: WSL + Windows 하이브리드 (Windows venv `./.venv/Scripts/python.exe`)

## 0. 최종 판정

# ✅ 승인 (조건부)

구현 품질·테스트·소비처 정합·보안 모두 검증 통과. **단, 아래 필수 후속 조치(계정/환경)를 수행하기 전까지는 나노바나나 실제 이미지 생성이 동작하지 않는다** (코드 결함이 아니라 계정 결제·환경변수 데이터 문제).

| # | 필수 후속 조치 | 대상 | 근거 |
|---|---|---|---|
| 1 | **Google 계정에 결제(billing) 활성화** — 나노바나나 4종은 전부 유료 전용(무료 티어 없음). 현재 키는 텍스트 모델 정상(실측)이나 이미지 모델 쿼터 `limit: 0` → 429 | 사용자(계정) | §2.2 |
| 2 | **Windows User 환경변수 `GEMINI_API_KEY` 값에서 trailing LF 제거** — 레지스트리 값이 `AIza…` + `\n`(끝 0x0A)으로 저장됨. 미조치 시 로컬 실행이 `ValueError: Invalid header value`로 즉시 실패하고 **폴백 체인·stats 집계까지 붕괴** | 사용자(환경) + 권장 코드 보강 | §2.3 |
| 3 | (권장) `_nanobanana_call`에서 키 읽기 시 `.strip()` 1줄 방어 — 붙여넣기 공백/개행 오염 차단 | 개발팀 | §2.3 |
| 4 | (재실측) 결제 활성화 후 **55s 내 성공 생성 1회 재실측** (NFR-1 완결) | QA 후속 | §2.2 |

---

## 1. 검증 요약

| 영역 | 방법 | 결과 |
|---|---|---|
| 실통신 (직접 REST + 코드 경로, 실키 1회) | 실제 `GEMINI_API_KEY`로 `generate_image()` 전체 경로 호출 | ✅ 인증·요청 계약·오류 정규화·폴백 진입 확인 / ❌ 이미지 생성 완료는 **계정 쿼터(429)로 차단** |
| 전체 회귀 테스트 | `./.venv/Scripts/python.exe -m pytest -q` | ✅ **395 passed / 10 skipped** (수집 405) |
| 신규 나노바나나 테스트 | `tests/test_image_gen.py -v` | ✅ 15 passed (기존 8 + 신규 7) |
| 코드 리뷰 | diff 전체 + 폴백 체인·stats·파싱·소비처 분기 | ✅ 이상 없음 (P3 참고 3건) |
| 정적 보안 | semgrep (p/secrets + p/python, 188 rules) | ✅ 0 findings |
| 시크릿 스캔 | 저장소 grep `AIza...` | ✅ 0건 (키 미노출) |
| 소비처 스모크 | server.py data URI 분기 8케이스 + publish.py 내보내기 4케이스 | ✅ 전부 PASS |
| 테스트 격리 | Windows env 키 상속 상태에서 pytest 실행 | ✅ conftest autouse 차단 실증 (키가 실제 상속됨을 확인 후 통과) |

---

## 2. ⭐ 실통신 검증 (실제 키, 1회 호출) — 가장 중요

### 2.1 환경 실측 (키 값은 일절 출력·기록하지 않음)

- Windows User 환경변수 `GEMINI_API_KEY` 존재 (AIza… 39자 + **trailing LF 1자 = 40자** — PowerShell `[Environment]::GetEnvironmentVariable(...,'User')` 실측: `len=40, tail=10`)
- WSL(Linux) 쪽 미설정. Windows venv(Windows 프로세스)는 레지스트리 env를 상속 → **실제 키가 pytest 프로세스에도 들어옴** (conftest 격리가 이를 차단함을 395 통과로 실증)
- 키 자체는 유효: `gemini-2.5-flash:generateContent` 텍스트 호출 200 OK (4.31s, 응답 "네") — **텍스트 모델은 정상 동작**

### 2.2 직접 REST 실측 — `POST /v1beta/interactions` (실제 코드 경로 `_nanobanana_generate` → `_nanobanana_call`)

프롬프트: `_SINGLE_SCENE_RULES` 스타일 단문(209자), timeout 55s. 요청 스파이로 계약 실측:

| 항목 | 실측값 | 판정 |
|---|---|---|
| 엔드포인트 | `https://generativelanguage.googleapis.com/v1beta/interactions` | ✅ 계약 일치 |
| 인증 헤더 | `x-goog-api-key: ***` 단일, **Authorization(Bearer) 없음** (`api_key_used_for_bearer: empty`) | ✅ Bearer 생략 가드 동작 |
| 모델 | `gemini-3.1-flash-image` (기본) | ✅ |
| response_format | `{type:image, mime_type:image/jpeg, aspect_ratio:16:9, image_size:1K}` | ✅ AC1-2/AC4-6 |
| 프롬프트 | `_SINGLE_SCENE_RULES` 포함 (`카툰 금지`·`16:9`·`실사 사진 스타일` 검증) | ✅ AC1-3 |
| 응답 시간 | 0.72s (HTTP 429 거부 응답) — **55s 내** | ✅ (성공 케이스 지연은 미실측) |
| 인증 결과 | **401 아님** — `x-goog-api-key` 단일 인증이 게이트웨이 통과 | ✅ 핵심 리스크 해소 |
| 생성 결과 | **HTTP 429**: `Quota exceeded for metric: generate_content_free_tier_requests, limit: 0, model: gemini-3.1-flash-image` (lite 모델도 동일 `limit: 0`) | ❌ **계정 결제 미설정** (나노바나나 유료 전용) |
| 오류 정규화 | raw HTTPError/ValueError가 아닌 `ImageGenerationError("gemini image API http 429: …")` | ✅ v26 정규화 패턴 |
| 폴백 체인 | WARNING 실측: `image API nano banana failed (…) — retry via Bailian wan2.7-image` → Bailian/DashScope 키 없음 → 원본 예외 재전파 → `_dashscope_fallback`이 failures/consecutive 증가 후 전파 | ✅ AC3-4/AC6-2 **실전 재현** |

### 2.3 발견: Windows env 키 trailing LF → raw `ValueError` (재현 2회, API 비용 0)

- **재현**: env 값 그대로(개행 포함) 코드 실행 → urllib 헤더 검증에서 `ValueError: Invalid header value b'AIza…\n'` (네트워크 요청 전 0.08s 중단 — API 비용 0)
- **영향**: 이 예외는 `ImageGenerationError`가 아니므로 `_nanobanana_generate`·`_run_http`의 `except ImageGenerationError`를 통과하지 못해 **Bailian/DashScope 폴백 미실행, stats(failures/consecutive) 미집계** — 오류 계약·실패 집계 모두 붕괴
- **원인**: 환경변수 데이터 오염(레지스트리 값 끝 LF). GH Actions secret(사용자 직접 입력)은 가능성 낮으나 붙여넣기 오염 시 동일 경로 재현 가능
- **조치**: ① env var 재설정(필수) ② `_nanobanana_call` 키 읽기 시 `.strip()` 1줄(권장 — 동일 실패류 전면 차단)

---

## 3. 자동화 테스트 — 전체 회귀

```text
$ ./.venv/Scripts/python.exe -m pytest -q
395 passed, 10 skipped in 47.18s        (수집 405 — 신규 7 포함, 기존 388 유지)
```

- `tests/test_image_gen.py`: **15 passed** (기존 8건 무수정 — git diff로 0 removed / 227 added 확인, 신규 T1~T7)
- `tests/test_content_batch.py`: 수정 0 (git diff 확인) — 알림 임계(T4/T5 계열) 포함 통과 → AC5-3/AC5-4
- `content_batch.py`·`llm_client.resolve_api_key()`·`has_api_key()`: 수정 0 (git diff 확인) → AC6-4
- **테스트 격리 실증**: pytest 실행 시 Windows env 키가 실제 상속됨(§2.1)에도 395 통과 — conftest autouse 픽스처(`monkeypatch.delenv("GEMINI_API_KEY")`)가 GEMINI 미설정 전제의 기존 테스트를 보호. 신규 테스트는 본문에서 명시 설정

## 4. 코드 리뷰 (diff 전체 검토)

| 검토 항목 | 결과 | 근거 |
|---|---|---|
| 폴백 체인 각 1회 | ✅ | T4: 나노바나나 실패→Bailian **정확히 1회**·성공 URL 반환·`failures==0`(AC3-1/3-5). T5 ①: 나노바나나+Bailian 실패→DashScope 1회·POST 총 3회(AC3-2). 라이브에서도 폴백 WARNING 진입 실측 |
| stats 조건 v26 불변 | ✅ | `attempts` 증가는 `_run_http` 진입 1회(AC5-1), `failures`·`consecutive`는 `_dashscope_fallback` 최종 실패 시에만(AC5-2) — v26 코드 위치·조건 그대로 (diff 확인) |
| data URI 파싱 | ✅ | `steps[].content[]`에서 `type=="image"` 블록 `data`+`mime_type` 추출, mime 누락 시 `image/jpeg` 기본, 구조 불량 시 `ImageGenerationError` 정규화 (T1/T7 + 코드 검토) |
| server.py 분기 | ✅ | `_fetch_image_bytes` 선두 data URI 분기 — MIME `image/` 강제, `b64decode(validate=True)`, 20MB 상한, HTTPS 가드·리다이렉트·스트리밍 경로 무변경 |
| publish.py 방침 | ✅ | `_image_lines` — data URI는 라인 생략 + 수동 업로드 경고 주석, URL은 기존 임베드, 네이버(`_export_naver`)는 `_image_lines` 미호출이라 무영향 |
| 테스트 격리 | ✅ | conftest autouse — Windows env 키 상속 차단, 기존 테스트 파일 수정 0 |
| llm_client Bearer 생략 | ✅ | `_browser_headers` — api_key 빈 값 시 Authorization 생략. 기존 호출자(항상 키 존재)는 동작 불변. 라이브 실측으로 `empty` 확인 |
| 문법/파일 | ✅ | daily-collect.yml YAML 파싱 정상, .env.example·02-trd.md·CHANGELOG 반영 일치 |

### 참고 (P3, 수정 불필요)
1. `_nanobanana_call`의 `except (KeyError, TypeError, StopIteration)` — `StopIteration`은 실제 발생 경로 없음(무해)
2. `_decode_data_uri` — 디코드 **후** 크기 검사라 초대형 data URI(수백 MB)는 메모리에 전체 적재 후 거부. DB 저장값·토큰 보호라 노출 제한적이나, `len(b64)` 사전 검사가 더 견고(선택)
3. `data:;base64,...`(빈 MIME)은 `image/jpeg`로 기본 처리 — 관대하나 무해

## 5. 정적 보안 (semgrep)

```text
semgrep scan --config p/secrets --config p/python (변경 8개 파일)
✅ Scan completed successfully. Findings: 0 (0 blocking) · Rules run: 188
```
- 저장소 전체 grep `AIza[0-9A-Za-z_-]{20,}` → **0건** (키 미노출, NFR-3)
- 키는 env에서만 읽고 로그·오류 메시지에 키 값 미포함 (라이브 검증 중 키 마스킹 확인)

## 6. 소비처 스모크 (직접 실행)

### server.py 다운로드 프록시 (`_fetch_image_bytes` / `_decode_data_uri`)
| 케이스 | 기대 | 결과 |
|---|---|---|
| 정상 data URI (JPEG) | 디코드 (bytes, mime) | ✅ mime=image/jpeg |
| 비이미지 MIME (`data:text/plain…`) | 400 | ✅ |
| 오염 base64 | 400 | ✅ |
| 페이로드 없음 (`data:image/jpeg;base64,`) | 400 | ✅ |
| 빈 URL / None | 400 | ✅ |
| `http://` URL | 400 (HTTPS 가드 유지) | ✅ |
| 20MB 초과 data URI | 502 | ✅ |

### publish.py 마크다운 내보내기 (`build_export_markdown`)
| 케이스 | 기대 | 결과 |
|---|---|---|
| 대표 data URI | 라인 생략 + `<!-- 대표 이미지: data URI … 업로드하세요 -->` | ✅ |
| 섹션 data URI | 라인 생략 + `<!-- 섹션 이미지 N: … -->` | ✅ |
| 섹션 URL | 기존 `![섹션 이미지 N](url)` 임베드 유지 | ✅ |
| data URI 본문 누출 | 없음 (원본 문자열이 export에 등장하지 않음) | ✅ |
| URL 대표/섹션 | 기존 임베드 그대로 | ✅ |
| 네이버 export | data URI 미등장 (플레인 경로 무영향) | ✅ |

---

## 7. AC·NFR 매핑 (전수)

| AC | 내용 | 판정 | 근거 |
|---|---|---|---|
| AC1-1 | 나노바나나 1차, Bailian/DashScope 0회 | ✅ | T1/T2 (calls==1) + 라이브 경로 진입 |
| AC1-2 | response_format 4필드 (16:9·1K·JPEG) | ✅ | T1 + **라이브 요청 실측 일치** |
| AC1-3 | 기존 프롬프트 재사용 (`_SINGLE_SCENE_RULES`) | ✅ | T2/T7 + 라이브 prompt_has_rules |
| AC1-4 | `GEMINI_IMAGE_MODEL` 오버라이드 | ✅ | T6 (lite 모델 반영) |
| AC1-5 | 대표·섹션 공통 적용 | ✅ | T2 (`generate_section_images` 동일 분기) |
| AC1-6 | steps[].content[] image 블록 파싱 | ✅ | T1/T7 (raw REST mock 파싱 + b64 복원) |
| AC2-1 | 키 미설정 → Bailian 1차 그대로, 나노바나나 0회 | ✅ | T3 + conftest 격리 하 395 통과 |
| AC2-2 | 키 전체 미설정 기존 메시지 유지 | ✅ | T3 2부 + 기존 테스트 통과 |
| AC2-3 | 기존 테스트 전부 통과 | ✅ | 395 passed/10 skipped (기존 388) |
| AC2-4 | GEMINI 키만 설정 → 나노바나나 경로 | ✅ | T6 + **라이브 가드 통과·경로 진입** |
| AC3-1 | 나노바나나 실패 → Bailian 정확히 1회, URL 반환 | ✅ | T4 (calls==2) |
| AC3-2 | Bailian까지 실패 → DashScope 1회 | ✅ | T5 ① (POST 3회) |
| AC3-3 | 전부 실패 → ImageGenerationError + 최종 원인 | ✅ | T5 ② + **라이브 재현** (429 원인 포함 전파) |
| AC3-4 | 폴백 WARNING 로그 (원인 + 프로바이더) | ✅ | T4 caplog + **라이브 STDERR 실측** |
| AC3-5 | 폴백 성공은 최종 실패 아님 (집계 0) | ✅ | T4 (failures==0, consecutive==0) |
| AC4-1 | data URI 반환·저장 (호출부 무변경) | ✅ | T1/T7 (data URI + b64decode 복원). 라이브 성공 반환은 쿼터로 미실측 — 단위 검증으로 갈음 |
| AC4-2 | 대시보드 data URI 렌더링 | ✅ | static/index.html 변경 0 — `<img src>` data URI 브라우저 기본 지원 (코드 확인) |
| AC4-3 | 다운로드 프록시 data URI 처리 | ✅ | 스모크 8케이스 (§6) |
| AC4-4 | publish.py data URI 방침 (생략+주석) | ✅ | 스모크 6케이스 (§6) + tech-design §5② 일치 |
| AC4-5 | URL 프로바이더는 URL 저장 유지 | ✅ | T3/T4/T5 URL 반환 + 코드 경로 무변경 |
| AC4-6 | JPEG·1K 기본 (비용 통제) | ✅ | **라이브 요청 실측** (mime image/jpeg, size 1K) + T6 2K 오버라이드 |
| AC5-1 | attempts _run_http 진입 1회 | ✅ | T4/T5 (attempts==1) + 코드 위치 확인 |
| AC5-2 | 최종 실패만 failures·consecutive 증가 | ✅ | T5 ② + **라이브 재현** (429 최종 실패 경로) |
| AC5-3 | 임계 초과 알림 (기존 로직) | ✅ | content_batch 무변경 + test_content_batch 11건 통과 |
| AC5-4 | reset/get 시그니처 불변 | ✅ | 무변경 + test_content_batch 통과 |
| AC6-1 | GEMINI 키만 → 가드 통과 | ✅ | T6 + **라이브 가드 통과** |
| AC6-2 | GEMINI만 + 실패 → Error 전파 (최종 실패 집계) | ✅ | **라이브 재현** — 429 → 폴백 키 없음 → 원본 예외 전파 |
| AC6-3 | 키 전부 미설정 기존 메시지 유지 | ✅ | T3 2부 + 기존 `test_no_key_raises_clear_error` 통과 |
| AC6-4 | `has_api_key()` 불변 (배치 게이트 영향 0) | ✅ | llm_client·content_batch 수정 0 (git diff) |

| NFR | 내용 | 판정 | 근거 |
|---|---|---|---|
| NFR-1 | 55s 타임아웃 유지 + 1회 실측 | ⚠️ 부분 | `IMAGE_TIMEOUT=55` 유지 확인, 라이브 응답 0.72s(거부) — **성공 생성 지연은 결제 활성화 후 재실측 필요** |
| NFR-2 | 비용 통제 (1K·16:9·JPEG 기본) | ✅ | 라이브 요청 실측 + 모델/크기 env 오버라이드만 허용 |
| NFR-3 | 키 env 관리·로그 미노출 | ✅ | semgrep 0건 + 저장소 grep 0건 + 라이브 마스킹 |
| NFR-4 | 시그니처·반환형 불변, SQLite/Postgres 호환 | ✅ | public API 무변경 (diff) + 395 통과 |
| NFR-5 | 외부 라이브러리 추가 0 (urllib) | ✅ | diff 확인 — import 추가 없음 (server.py `base64` 표준 라이브러리 제외) |
| NFR-6 | 알림 일 1회 (v26 유지) | ✅ | content_batch 무변경 |
| NFR-7 | GEMINI_BASE_URL env 오버라이드 | ✅ | `_gemini_base_url()` 호출 시점 평가 (코드 확인) |

---

## 8. 발견 사항·버그 목록

| # | 심각도 | 제목 | 재현 | 영향 | 조치 |
|---|---|---|---|---|---|
| B1 | **P2** (환경+방어) | Windows User env `GEMINI_API_KEY`에 trailing LF — 코드가 그대로 쓰면 raw `ValueError`로 폴백·stats 붕괴 | 2회 (실키, 비용 0) | 로컬 Windows 실행 시 이미지 생성 전면 불능 + 오류 계약 위반 | env var 재설정(필수) + `_nanobanana_call` `.strip()`(권장) |
| B2 | **P2** (계정) | GEMINI 키에 이미지 모델 쿼터 0 (`free_tier_requests limit: 0`) — 나노바나나 유료 전용인데 결제 미연결 | 2회 (flash/lite 모델) | 나노바나나 실제 생성 불가 (GH Actions 포함) — 텍스트 모델은 정상 | 사용자: AI Studio/Cloud Console 결제 활성화 |
| B3 | P3 | `_decode_data_uri` 디코드 후 크기 검사 (초대형 data URI 메모리) | 정적 분석 | 제한적 (DB값·토큰 보호) | 선택 — `len(b64)` 사전 검사 |
| B4 | P3 | `StopIteration` catch 불필요 / 빈 MIME 기본 처리 | 정적 분석 | 무해 | 참고 |

---

## 9. 스킬 사용 로그

| 스킬 | 사용 지점 |
|---|---|
| **fable-prove-it** | 모든 주장을 실행 증거로 검증 — 395 pytest 실측, 실키 1회 호출 실측(요청 스파이+타이밍), 스모크 8+6케이스 직접 실행, PowerShell로 env 값 바이트 실측, semgrep·grep 실행 후 완료 주장 |
| **qa-tools** | semgrep 실행 (`/home/wj941/.agents/skills/qa-tools/.venv/bin/semgrep scan --config p/secrets --config p/python`, 0 findings) |
| **systematic-debugging** | 실키 호출이 `ValueError: Invalid header value`로 실패 → 근본 원인 추적(코드가 아니라 env 값의 trailing LF) → PowerShell `GetEnvironmentVariable`로 레지스트리 값 바이트 실측으로 확정 |
| **wsl-windows-hybrid-runner** | Windows venv pytest·실키 스크립트 실행, cmd.exe env 조회, WSL↔Windows env 상속 특성(레지스트리 env 우선) 활용 |
| **md-to-html** | 본 보고서 .html 생성 (실제 경로 `/home/wj941/.agents/skills/md-to-html/.venv/bin/python scripts/md2html.py`) |

## 10. 산출물

- `pipeline/image-gen-nanobanana/dev-qa-report.md` · `dev-qa-report.html` (본 보고서)
- 검증 스크립트는 실행 후 삭제 (키 미보존 — 로그·파일 어디에도 키 값 없음)

---

*작성: 개발QA팀 · 검증 완료 · 판정: ✅ 승인 (조건부 — 필수 후속: 계정 결제 활성화 + Windows env 개행 정리)*
