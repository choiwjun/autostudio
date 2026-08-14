# 운세 발행 버튼 추가 (대시보드 수동 발행) — 요구사항 명세

> 작성: 요구사항팀 · 프로젝트: autostudio · 작업 디렉토리: `pipeline/fortune-publish-button/`
> 원본 요청: 사용자 — "운세 발행 관련해서 운세발행 버튼을 프로그램에 하나 추가하고 401 429 확인해"
> 실측 기준: v27 코드 (2026-08-13) — server.py·collect.py·publish_client.py·static/index.html·tests/test_api.py·tests/test_fortune_publish.py

## 1. 배경 (실측 현황)

### 1.1 운세 발행 흐름 (코드 실측)

| 단계 | 위치 | 동작 |
|---|---|---|
| 생성 | `collect.py::fortune_generate_step(d, cfg, today)` | daily_sns/daily_blog(LLM) + weekly(월요일)/monthly(1일)(LLM) + 고정(일주 60·별자리 12·띠 12, 규칙 기반, `fortune_fixed_per_day` 상한). 멱등: 같은 (ref_date, content_type) 이미 생성 시 스킵. **반환값 = 생성 건수(int)** |
| 발행 | `collect.py::_publish_all_fortune(d, cfg, today)` | 발행 후보 순회: daily_blog(당일) + weekly_blog(월요일) + monthly_blog(1일) + day_pillar_blog 1~60 + zodiac_blog 1~12 + animal_blog 1~12. status가 `published`/`qc_failed`면 스킵, `generated`/`publish_failed`면 발행 시도. **반환값 없음(None)** — 실패 사유는 DB에 저장되지 않고 collection_log에만 기록 |
| 전송 | `publish_client.py::publish_fortune(cfg, d, ref, content, fortune_type)` | `POST {BLOG_API_URL}/api/posts`, `Authorization: Bearer {BLOG_TOKEN}`, slug 멱등 upsert. 실패 시 `BlogPublishError` raise — 메시지에 `HTTP {status}: {body}` 포함 (예: `HTTP 401: ...`) |
| 재시도 | `publish_client.py::_post` | 429·5xx는 지수 백오프 3회 재시도 (2·4·8초). **400·401은 재시도 없이 즉시 실패** (토큰 문제는 재시도 무의미 판정) |
| 스케줄 | `.github/workflows/daily-collect.yml` | 매일 07:17 KST — env로 `BLOG_API_URL`·`BLOG_TOKEN`(secrets)·`BLOG_PUBLISH_ENABLED: "1"` 주입 후 `python collect.py` |

### 1.2 401/429 원인 조사 결과 (오케스트레이터 실측 — 요구사항에 그대로 반영)

| 증상 | 원인 (실측) | 해결 주체 |
|---|---|---|
| **401 Unauthorized** | autostudio의 `BLOG_TOKEN`이 autoblog(autoblog-pearl.vercel.app) 서버가 기대하는 토큰과 불일치. 로컬 `.env.local` 토큰으로 `POST /api/posts` live probe → **401 재현 확인**. GH Actions secret 토큰은 유효했던 것으로 추정(429 이후 401 로그 순서) | **사용자 설정 작업** — autoblog 프로젝트의 DASHBOARD_TOKEN 확인·교체 필요. 코드로 해결 불가 |
| **429 Too Many Requests** | autoblog 쪽 Bailian token-plan **주간 쿼터 소진** ("Your token-plan 1-week quota has been exhausted") | **사용자 작업** — autoblog 서버 키/플랜 점검 필요 |
| 현재 데이터 상태 | `fortune_generations`: publish_failed 6건(zodiac/day_pillar) + generated 6건(daily_sns/daily_blog, 발행 전). **최근 발행 성공 0건** | — |

> 참고: daily_sns는 SNS 요약 콘텐츠로 **발행 대상이 아님** (`_publish_all_fortune` 후보에 없음 — 발행 후보는 `*_blog` 타입만). 대시보드 결과 표시에서 daily_sns는 "발행 대상 아님"으로 구분 표시해야 한다.

### 1.3 대시보드·서버 현황 (코드 실측)

- `server.py::create_app(cfg)` — FastAPI 앱 팩토리. 인증: `require_token(authorization: str = Header(default=""))` — development는 생략, 비개발은 `DASHBOARD_TOKEN`과 Bearer 비교 실패 시 401. 모든 엔드포인트가 `dependencies=[Depends(require_token)]` 사용. DB 접근은 `run_db(fn)` 헬퍼. **운세 관련 엔드포인트는 현재 없음**
- `static/index.html` — 상단바에 "지금 수집 실행" 버튼(`collectBtn`, `onclick="collect()"`). 인증은 `authHeaders()`가 `localStorage.dashboard_token`에서 Bearer 헤더 구성, `api(path, opts)` 헬퍼가 401 시 "토큰이 올바르지 않습니다" 안내. **운세 UI 없음**
- `config.py::load_config()` — `blog_api_url`(BLOG_API_URL), `blog_token`(BLOG_TOKEN), `blog_publish_enabled`(BLOG_PUBLISH_ENABLED=="1"), `dashboard_token`, `env` 포함. BLOG_PUBLISH_ENABLED 기본값 **0**
- `db.py` — `fortune_generations(ref_date, content_type, content, grounding, status, created_at, updated_at)`, UNIQUE(ref_date, content_type). status 값: `generated` / `published` / `publish_failed` / `qc_failed`(수동 검토 대상 — 자동 발행 안 함)
- 테스트 — `tests/test_api.py`(엔드포인트 패턴: `make_app(tmp_path, env=...)` + TestClient + monkeypatch), `tests/test_fortune_publish.py`(운세 발행 11건)

## 2. 목표 & 비목표

### 목표
- **운세 발행을 수동으로 트리거하는 대시보드 버튼** 추가 — 생성·발행 단계를 사용자가 직접 실행 가능하게 한다
- 401/429 등 발행 실패를 **항목별로 화면에 표시**해 "왜 안 되는지" 사용자가 즉시 파악 — 401이면 토큰 불일치, 429면 쿼터 소진 힌트
- 실패해도 서버가 죽지 않고 **부분 성공 보존** (성공 N건/실패 N건 + 사유)

### 비목표
- 토큰 교체/키 플랜 변경 등 **autoblog 쪽 설정 작업** (사용자 작업 — 코드 범위 아님)
- 401/429 자동 복구 로직 (자동 재시도는 publish_client 기존 재시도 정책 유지, 신규 재시도 정책 추가 금지)
- 발행 실패 사유의 DB 영구 저장 (collection_log 기록은 기존 유지 — 응답 표시용으로만 수집)
- 대시보드의 운세 생성·발행 상태 페이지/탭 신설 (버튼 + 결과 표시 영역만)
- 스케줄(GH Actions) 자동 발행 동작 변경

## 3. 타깃 (영향 파일)

| 파일 | 변경 내용 (예상) |
|---|---|
| `server.py` | `POST /fortune/publish` 엔드포인트 추가 (require_token 적용, collect 로직 호출, 항목별 결과 JSON 반환) |
| `collect.py` | 발행 시도 시 **항목별 결과(성공/실패+HTTP 상태)를 반환하는 함수** 추가 — 기존 `_publish_all_fortune` 후보 목록·상태 판정 로직을 헬퍼로 추출해 재사용 (중복 구현 금지) |
| `publish_client.py` | (필요 시) `BlogPublishError`에 `status_code` 속성 추가 — 메시지 문자열 파싱 대신 구조적 원인 전달 (기존 메시지 포맷·동작 불변) |
| `static/index.html` | "운세 발행" 버튼 + 결과 표시 영역(성공 N/실패 N + 항목별 사유, 401/429 힌트) |
| `tests/test_api.py` 또는 `tests/test_fortune_publish.py` | 신규 엔드포인트 테스트 추가 |
| **변경 금지** | `engine/fortune_content.py`, `db.py` 스키마, `config.py` 기본값, `.github/workflows/daily-collect.yml`, 기존 테스트 파일의 기존 테스트 케이스 |

## 4. 범위

### 포함
- `POST /fortune/publish` 엔드포인트 (require_token 적용 — v15 인증 체계 재사용)
- 대시보드 "운세 발행" 버튼 및 결과 표시
- 항목별 결과: 성공/실패 + 실패 원인(HTTP 상태 코드 401/429/5xx + 힌트 문구)
- `BLOG_PUBLISH_ENABLED=0`(또는 BLOG_API_URL 미설정) 시 안내 메시지 응답
- 신규 테스트 (아래 §12)

### 제외
- autoblog 서버 키/토큰/플랜 변경 (사용자 작업)
- 발행 성공률 모니터링/알림
- 운세 상세 조회 API (대시보드에 운세 목록 탭 신설 등)

## 5. 용어

| 용어 | 의미 |
|---|---|
| 운세 발행 | `fortune_generations`의 발행 후보(`*_blog` 타입, status=generated/publish_failed)를 autoblog `POST /api/posts`로 전송해 published 상태로 만드는 것 |
| 발행 후보 | `_publish_all_fortune`의 후보 목록: daily_blog(당일) · weekly_blog(월요일) · monthly_blog(1일) · day_pillar_blog 01~60 · zodiac_blog 01~12 · animal_blog 01~12 |
| 항목별 결과 | 후보 1건당 `{ref_date, content_type, status, ok, reason(선택)}` 형태의 결과 레코드 |
| autoblog | 별도 블로그 서버 (autoblog-pearl.vercel.app) — `POST /api/posts`로 발행 수신 |

## 6. 기능 요구사항 (FR)

### FR-1 — `POST /fortune/publish` 엔드포인트 (M) ⭐
- `server.py::create_app` 내부에 추가, `dependencies=[Depends(require_token)]` 적용 (기존 인증 체계 그대로 — development는 인증 생략, 비개발은 무토큰/오토큰 401)
- 동작 순서:
  1. (a) 미생성 콘텐츠 생성 — `collect.fortune_generate_step(d, cfg, today)` 호출 (기존 생성 로직 재사용, today=KST 오늘)
  2. (b) 미발행 콘텐츠 전부 발행 시도 — 기존 `_publish_all_fortune`의 후보 순회·상태 판정 로직을 재사용한 항목별 결과 수집 실행
  3. (c) 항목별 결과 JSON 반환 (성공/실패 + 사유)
- **수용 기준 (AC-1)**: `POST /fortune/publish` 호출 시 200 응답 + JSON에 `created`(신규 생성 건수), `published`(성공 건수), `failed`(실패 건수), `skipped`(스킵 건수), `items`(항목별 상세) 포함
- **수용 기준 (AC-2)**: 프로덕션 환경(env != development)에서 인증 헤더 없이 호출 시 **401** 응답 (기존 `require_token` 동작과 동일)
- **수용 기준 (AC-3)**: 실패 항목이 있어도 **HTTP 200 + 부분 성공 보존** — `items`에 실패 항목의 `ok: false` + `reason` 포함. 서버 500으로 죽지 않음
- **수용 기준 (AC-4)**: 토큰 불일치(401) 시 — 해당 항목 실패 사유에 HTTP 상태 `401`과 힌트 문구 "토큰 불일치 — autoblog DASHBOARD_TOKEN 확인 필요" 포함, 응답은 200 유지
- **수용 기준 (AC-5)**: 쿼터 소진(429) 시 — 실패 사유에 HTTP 상태 `429`와 힌트 문구 "쿼터 소진 — autoblog Bailian token-plan 주간 쿼터 확인" 포함, 응답은 200 유지

### FR-2 — 대시보드 "운세 발행" 버튼 (M)
- `static/index.html` 상단바의 "지금 수집 실행" 버튼 옆에 "운세 발행" 버튼 추가 (`onclick` 핸들러, 기존 `authHeaders()`/`api()` 헬퍼 재사용)
- 클릭 → `POST /fortune/publish` 호출 → 응답을 화면에 표시:
  - 요약: "성공 N건 / 실패 N건 / 스킵 M건 (생성 C건)"
  - 항목별 목록: ref_date·content_type·결과(성공/실패) + 실패 사유
  - 401 힌트: "토큰 불일치" / 429 힌트: "쿼터 소진" 문구를 사유에 표시
  - 진행 중에는 버튼 비활성화 + "발행 중..." 표시 (기존 `collect()` 패턴과 동일한 UX)
- **수용 기준 (AC-6)**: 버튼 클릭 → 엔드포인트 호출 → 결과 영역에 요약+항목별 결과 렌더링 (수동 확인 가능한 DOM)
- **수용 기준 (AC-7)**: 응답에 `enabled: false`(BLOG_PUBLISH_ENABLED=0)면 "발행 비활성 — BLOG_PUBLISH_ENABLED=1 필요" 안내 표시 (실패 처리 아님)

### FR-3 — 기존 로직 재사용 (M)
- collect.py의 `fortune_generate_step`·`_publish_all_fortune`·후보 목록/상태 판정 로직을 **import해서 호출** — server.py에 발행 로직 중복 구현 금지
- 항목별 결과 수집이 필요한 경우 **collect.py에 결과 반환 함수를 추가**하고 `_publish_all_fortune`이 이를 내부적으로 사용하도록 리팩터링 (동작 불변 — 기존 테스트 `test_fortune_publish.py` 11건 전부 통과 유지)
- **수용 기준 (AC-8)**: `server.py`에 `requests.post` 직접 호출·후보 목록 하드코딩·slug 규칙 재구현이 없어야 함 (코드 리뷰/테스트로 검증)

### FR-4 — BLOG_PUBLISH_ENABLED=0 안내 (M)
- `cfg.get("blog_publish_enabled")`가 False 또는 `blog_api_url` 미설정이면: 발행 시도 없이 즉시 응답 — `{enabled: false, message: "발행 비활성 — BLOG_PUBLISH_ENABLED=1 및 BLOG_API_URL 설정 필요", ...}`
- 단, **생성 단계(FR-1-a)는 기존 동작대로 수행** — `_publish_all_fortune`의 기존 "비활성이면 조용히 return" 동작은 유지하되, 엔드포인트 응답으로는 안내를 노출
- **수용 기준 (AC-9)**: BLOG_PUBLISH_ENABLED=0 cfg로 호출 시 200 + `enabled: false` + 안내 message, 발행 시도 0건, DB status 불변

### FR-5 — 발행 후보 대상·상태 규칙 (S)
- 후보 대상: `*_blog` 타입만 (daily_sns 제외 — SNS 요약은 발행 대상 아님)
- status=published → 스킵(성공으로 표시하지 않음 — 이미 발행됨), status=qc_failed → 스킵(수동 검토 대상 — "검수 대기"로 표시)
- status=generated / publish_failed → 발행 시도
- content 비어 있으면 스킵 (미생성 — FR-1-a 생성 단계에서 시도)
- **수용 기준 (AC-10)**: daily_sns 항목이 응답 items에 "발행 대상 아님"으로 구분 표시되거나 제외되며, 발행 시도되지 않음

## 7. 비기능 요구사항 (NFR)

| ID | 항목 | 요구사항 |
|---|---|---|
| NFR-1 | 응답 시간 | Vercel 60초 서버리스 한도 고려 — 발행 단계는 항목당 최대 (재시도 3회 포함) 수십 초 가능. **LLM 생성 포함 시 60초 초과 위험** — §11 오픈 질문 OQ-1에서 예산 정책 확정. 최소한 발행 실패(401/429 즉시 실패) 시 빠르게 완료 |
| NFR-2 | 인증 | v15 체계 재사용 — 비개발 환경 무토큰 401, development 생략. 토큰은 localStorage 기존 저장 방식 |
| NFR-3 | 부분 성공 | 어떤 항목이 실패해도 다른 항목의 발행 결과는 정상 집계·반환 (예외 전파 금지 — 항목 단위 try/except) |
| NFR-4 | 멱등 | 버튼 연타·재호출 시 slug upsert 기반 중복 발행 없음 (기존 autoblog 멱등 + `published` 스킵 규칙) |
| NFR-5 | 호환성 | 기존 `_publish_all_fortune`·`publish_client` 동작·시그니처 불변 (기존 테스트 전부 통과), BlogPublishError 메시지 포맷 불변 |
| NFR-6 | 접근성 | 버튼은 `<button>` + 라벨 텍스트, 결과 영역은 텍스트 기반 (기존 대시보드 패턴 준수) |

## 8. 제약

- **Vercel 서버리스 60초 한도** — 서버 엔드포인트는 실험적으로 느린 작업(LLM 생성)을 무제한 수행 불가
- **autoblog 측 설정(토큰/플랜)은 코드 변경 불가** — 401/429는 코드로 해결 불가, 표시·안내만 가능
- `publish_client._post`의 기존 재시도 정책(429·5xx 백오프 3회, 400·401 즉시 실패) 유지 — 신규 재시도 로직 추가 금지
- 기존 테스트 수정 금지 — 신규 테스트만 추가 (conftest의 `_clear_gemini_api_key` autouse 픽스처는 그대로 적용)

## 9. 우선순위 (M/S/C)

| ID | 우선순위 | 사유 |
|---|---|---|
| FR-1 (엔드포인트) | **M** | 핵심 요청 — 수동 발행 트리거 |
| FR-2 (버튼+결과 표시) | **M** | 핵심 요청 — "버튼 추가", 401/429 확인 |
| FR-4 (비활성 안내) | **M** | 사용자 환경이 기본 비활성일 수 있어 필수 안내 |
| FR-3 (재사용) | **M** | 설계 원칙 — 중복 금지 |
| FR-5 (후보 규칙 명시) | S | 동작 명세 — 구현 시 자연히 포함 |

## 10. 성공 기준 (종합)

1. 대시보드에 "운세 발행" 버튼이 보이고, 클릭 시 발행 결과(성공/실패 + 사유)가 화면에 표시된다
2. 현재 실패 상태(401 토큰 불일치)에서 버튼 클릭 시 — 각 항목 실패 사유에 **401 + "토큰 불일치" 힌트**가 표시되고 서버는 200을 유지한다 (사용자가 autoblog 토큰 교체 필요를 인지)
3. 429 쿼터 소진 상황에서 — 실패 사유에 **429 + "쿼터 소진" 힌트** 표시
4. BLOG_PUBLISH_ENABLED=0이면 "발행 비활성" 안내가 표시된다
5. 기존 테스트 전체 통과 + 신규 테스트 통과
6. (사용자 설정 후) 토큰 교체·플랜 복구 시 버튼만으로 미발행분 전부 발행 완료 가능

## 11. 오픈 질문 · 가정

### 오픈 질문 (구현 시 확정 — 개발팀/기획팀 판단)
- **OQ-1 (응답 예산)**: 수동 발행 시 LLM 미생성분(예: 당일 daily_sns/daily_blog) 생성까지 포함할지, 아니면 "생성은 기존 스케줄에 맡기고 발행만" 수행할지 — Vercel 60초 한도와 생성 시간(LLM 1건당 최대 90초 타임아웃) 충돌. **권장**: 요청은 "미생성 콘텐츠 생성"을 포함하되, LLM 생성은 기존 스케줄(GH Actions)이 담당하므로 엔드포인트는 **생성 1회 시도 + 발행 집중**이 현실적. 확정은 구현 시 60초 예산 기준으로 결정
- **OQ-2 (실패 사유 추출)**: `BlogPublishError` 메시지 문자열 파싱 vs `status_code` 속성 추가 — **권장**: 속성 추가 (백워드 호환, 기존 메시지 포맷 유지)
- **OQ-3 (결과 표시 위치)**: 상단바 버튼 옆 결과 토스트 vs 상태줄(`#status`) vs 전용 결과 패널 — **권장**: `#status` 요약 + 버튼 하단 인라인 결과 목록 (탭 신설 없이)

### 가정 (assumptions)
- **A-1**: 사용자 인터뷰 불필요 — 요청이 명확(버튼 추가 + 401/429 확인)하고 오케스트레이터가 원인 조사 완료. 가정은 이 문서로 갈음
- **A-2**: 401/429 해결은 autoblog 쪽 사용자 설정 작업 — 이 과제는 "확인(표시)"까지 담당
- **A-3**: today(기준일)는 KST 기준 — 기존 `config_mod.today_kst()`/`collect.now_kst()` 사용
- **A-4**: 개발 환경(ENV=development)은 인증 생략 — 기존 동작과 동일, 로컬 테스트 편의 유지
- **A-5**: 응답에 실패 사유 전문(autoblog body 원문) 포함 가능 — 단 120자 이내로 자르는 기존 규칙 준수
- **A-6**: daily_sns는 발행 대상이 아님 (코드 실측 확인) — 화면에 "발행 대상 아님" 구분 표시

## 12. 테스트 요구사항 (TDD, 6건 예상)

> 기존 테스트(`test_api.py` 31건 + `test_fortune_publish.py` 11건 등) **수정 금지**, 신규 추가만.

| # | 테스트 | 검증 |
|---|---|---|
| T1 | `test_fortune_publish_endpoint_requires_token` | production env에서 무토큰 `POST /fortune/publish` → 401 (make_app(env="production") 패턴) |
| T2 | `test_fortune_publish_endpoint_partial_results` | 발행 후보 2건(1 성공 1 실패) 준비 후 monkeypatch로 publish_client.requests.post가 200/401 반환 → 200 응답, items에 ok=true/false, 실패 reason에 401 포함, 서버 크래시 없음 |
| T3 | `test_fortune_publish_endpoint_disabled` | cfg `blog_publish_enabled=False` → 200 + `enabled:false` + 안내 message, publish 호출 0회 |
| T4 | `test_fortune_publish_endpoint_generates_then_publishes` | LLM 키 없음(has_api_key=False) + 고정 콘텐츠 미생성 → `fortune_generate_step` 호출 확인(created>0 가능) 후 발행 시도 (기존 `test_fortune_step_publishes_on_success` 패턴) |
| T5 | `test_fortune_publish_collect_helper_returns_items` | collect.py 신규 결과 반환 헬퍼 — 401/429/5xx/성공 혼합 시 항목별 상태·사유 정확성, daily_sns 비포함 |
| T6 | `test_fortune_publish_endpoint_retries_previous_failures` | status=publish_failed 행이 재발행 시도되고 성공 시 published 갱신 (기존 `test_fortune_publish_failed_retries_next_run` 패턴 확장) |

## 13. 작업 규모 모드 판정

**판정: small**

| 기준 | 판정 근거 |
|---|---|
| 작업 범위 | 단일 기능(엔드포인트 1개 + 버튼 1개 + 결과 표시) — 신규 서비스 아님, 신규 DB 스키마 없음 |
| 문서 규모 | 소형 — plan/tech-design 간이화 가능, 요구사항 5건(FR) 수준 |
| 외부 조사 | 불필요 — 401/429 원인 조사 완료(오케스트레이터), 경쟁 조사 없음 |
| 팀 구성 | 요구사항 → 개발 → 개발QA (3단계) |
| 산출물 | requirements.md(+html) → 간이 plan.md → 개발(server.py·collect.py·index.html·테스트) → 개발QA 리포트 |

> small 모드 계약에 따라 plan.md는 간이 버전(기능 명세 + tasks.md 중심)으로 진행한다.
