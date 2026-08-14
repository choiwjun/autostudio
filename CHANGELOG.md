# CHANGELOG

이 프로젝트의 버전 이력. 버전 규칙: 기능 단위로 커밋 메시지에 표기 (비공식 SemVer).

## v29.3 — 2026-08-14 (운세 생성 결과 레이아웃 수정)

### 수정
- 운세 생성 결과 테이블이 긴 본문 요약으로 가로로 밀려나는 문제 해결 (static/index.html)
  - `table-layout: fixed` + 열 폭 고정 — 긴 텍스트도 셀 안에서 줄바꿈
  - 셀 `word-break: break-word`·`overflow-wrap: anywhere`·`min-width: 0`
  - 컨테이너 `overflow-x: auto` — 그래도 넘치면 패널 안에서만 스크롤
  - 본문 `<pre>` width/max-width 100% + overflow-wrap — 펼쳐도 레이아웃 유지
- E2E 검증: 페이지 가로 스크롤 없음 (docScrollW 1280 = clientW 1280), 본문 펼친 후에도 정상

## v29.2 — 2026-08-14 (운세 생성 결과 개선 — 수동 게시 지원)

### 개선
- **본문 전체 보기/복사** — 생성 패널 각 항목에 "본문 보기"·"복사" 버튼. 수동 게시용으로 제목+본문 전체를 클릭 한 번에 복사
- **상태 라벨을 생성 맥락으로** — "발행 실패" → "발행 대기 (자동 발행 실패 이력)" (콘텐츠는 정상, 수동 게시 가능)
- **메시지 개선** — 이미 생성된 콘텐츠가 있으면 "이미 생성된 운세가 있습니다 — 아래에서 본문을 확인하고 복사해 게시하세요" 안내 (0건 생성이어도 정상 표시)
- 응답에 `body_full`·`sns_full` 추가 (전체 본문)

### 테스트
- 신규 검증: status 라벨 변환, body_full 포함 (test_api 3건 갱신)
- E2E 실측: 본문 보기 클릭 → 전체 본문 표시, 복사 버튼 5건 동작

## v29.1 — 2026-08-14 (운세 생성 실동작 — LLM 프로바이더 개선·검수 수정)

### 수정
- **운세 LLM 프로바이더 개선** (`engine/fortune_content._run_llm`)
  - 기존: Bailian Token Plan 고정 — 무효 키면 운세 생성 전면 실패 (빈 콘텐츠로 저장)
  - v29.1: `resolve_draft_provider()` 기반 — **OPENCODE_GO_API_KEY 우선**, 실패 시 Bailian 폴백 (draft_generator와 동일 체계)
  - 덕분에 운세 생성(daily_blog/daily_sns/weekly/monthly)이 실제 LLM 호출로 동작
- **기준일 검수 수정** (`check_reference_date`) — ISO(2026-08-14)만 찾던 것을 한국어 형식(2026년 8월 14일)도 허용. LLM이 자연스럽게 쓰는 한국어 날짜가 "기준일 미포함" 오탐으로 qc_failed 되는 문제 해결
- **동물 띠 제목 중복 수정** — `ZODIAC_ANIMAL_PROFILES` 키가 이미 '돼지띠'인데 코드가 '띠'를 또 붙여 "돼지띠띠" 생성. 기존 DB 12건 마이그레이션 완료
- **생성 결과 표시 개선** (`/fortune/generate` 응답 + 대시보드)
  - daily_sns는 text를 제목으로, daily_blog는 title/summary 표시
  - 빈 콘텐츠는 "내용 미생성 — LLM 키 확인 필요"로 구분
  - 마크다운 헤더 제거 후 본문 첫 문단만 미리보기
- **테스트 격리** — `_patch_generators`에 `generate_extended_blog` 모킹 추가 (조합 실행 시 실제 LLM 호출 방지)

### 테스트
- 전체 pytest **459 passed / 10 skipped**
- 실동작 검증: OPENCODE_GO_API_KEY로 daily_blog(3,140자)·daily_sns(514자) 실제 생성 확인

## v29 — 2026-08-14 (운세 생성·발행 분리 — 수동 게시 지원)

### 변경
- **운세 생성 전용 버튼/엔드포인트** — `POST /fortune/generate` (신규)
  - 운세 콘텐츠만 생성(LLM)하고 **발행하지 않음** — 사용자가 생성된 글을 보고 수동으로 게시하기 위한 용도
  - 응답: `{created, items[]}` — content_type별 최신 1건, `title`·`summary`·`preview` 포함
  - 기존 `fortune_generate_step(publish=False)` 재사용 (AC-8)
- **"자동 발행" 버튼으로 의미 분리** — 기존 `/fortune/publish`는 그대로 (BLOG_PUBLISH_ENABLED=1 환경에서 autoblog 실제 발행)
- 대시보드: 상단바 버튼 2개 — **운세 생성** (수동 게시용) / **자동 발행** (실제 발행)
  - 생성 결과 패널(`fortuneGenPanel`) 별도 — 기준일·타입·상태·제목·요약 표시

### 테스트
- 신규 3건: 무토큰 401 · 콘텐츠 반환(발행 미호출) · 발행 0회 보장
- 전체 pytest **407 passed / 10 skipped** (기존 404 + 신규 3)
- E2E 실측: "운세 생성" 클릭 → 콘텐츠 표시(고정 운세 5건 제목·요약), "자동 발행" 버튼 별도 존재

## v28 — 2026-08-13 (운세 발행 버튼 · POST /fortune/publish)

### 추가
- **운세 발행 버튼 + 엔드포인트** (`server.py`·`collect.py`·`static/index.html`) — 대시보드에서 수동으로 운세 생성·발행 트리거
  - `POST /fortune/publish`: 55초 예산 내 생성→발행, 항목별 결과 `{created, published, failed, skipped, enabled, message, items[]}` 반환 (AC-1)
  - 항목 단위 try/except — 실패 항목 `ok:false` + 사유, 응답 200 유지 (부분 성공 보존, AC-3)
  - 401 → "토큰 불일치 — autoblog DASHBOARD_TOKEN 확인 필요" / 429 → "쿼터 소진" 힌트 (AC-4/AC-5, `BlogPublishError.status_code`)
  - `BLOG_PUBLISH_ENABLED=0` → `enabled:false` + 안내, 발행 시도 0건 (AC-7/AC-9)
  - daily_sns는 `not_target`("발행 대상 아님") 구분 표시 (AC-10)
  - 기존 `_publish_all_fortune` 후보·상태 판정 로직을 헬퍼로 추출해 재사용 — 중복 구현 없음 (AC-8)
- `publish_client.py`: `BlogPublishError.status_code` 속성 추가 (메시지 포맷 불변)
- 대시보드: "운세 발행" 버튼 + 결과 패널 (요약 + 항목별 테이블, 401/429 힌트)

### 테스트
- 신규 7건: 무토큰 401·부분 결과·비활성·생성→발행·재시도·항목별 수집·예산 스킵
- 전체 pytest **404 passed / 10 skipped** (기존 395 + 신규 9, 기존 테스트 수정 0)

### 문서
- `pipeline/fortune-publish-button/` — requirements·plan·tech-design·implementation-report·dev-qa-report (md+html)

## v27 — 2026-08-13 (Google Nano Banana 이미지 생성 1차 프로바이더)

### 추가
- **나노바나나 1차 프로바이더** (`image_gen.py`, FR-1~FR-6) — `GEMINI_API_KEY` 설정 시
  이미지 생성(대표·섹션·백필 전 경로)이 Google Gemini 이미지 모델로 전환
  - 기본 모델 `gemini-3.1-flash-image`(Nano Banana 2), 16:9·1K·JPEG 요청 (AC1-2),
    모델·크기·베이스 URL env 오버라이드(`GEMINI_IMAGE_MODEL`·`GEMINI_IMAGE_SIZE`·`GEMINI_BASE_URL`)
  - raw REST Interactions API: `POST /v1beta/interactions` + `x-goog-api-key` 헤더,
    응답 `steps[].content[]`의 `type=="image"` 블록 파싱 (SDK 미사용 — NFR-5)
  - **data URI 저장 (FR-4)**: base64 응답을 `data:{mime};base64,{data}`로 저장 —
    DB 스키마·content_batch·db 호출부 무변경, 대시보드 `<img>` 렌더링 호환 (AC4-1/4-2)
  - 소비처 정합: `server.py` 다운로드 프록시 data URI 분기(AC4-3),
    `publish.py` 마크다운 data URI 생략+수동 업로드 경고 주석(AC4-4, 네이버 플레인 무영향)
  - 폴백 체인 (FR-3): 나노바나나 실패 → Bailian 1회 → DashScope 1회, 각 폴백 WARNING 로그
  - 키 가드 확장 (FR-6): `GEMINI_API_KEY`만으로 이미지 생성 동작 — `llm_client.has_api_key()` 불변
  - `GEMINI_API_KEY` 미설정 시 **기존 동작 100% 불변** (FR-2)
- `llm_client.py`: `_browser_headers`가 api_key 빈 값 시 `Authorization` 헤더 생략
  (Gemini `x-goog-api-key` 인증용 — 기존 호출자 무영향)

### 환경변수
- `GEMINI_API_KEY` (선택 — 미설정 = 기존 체인), `GEMINI_IMAGE_MODEL`, `GEMINI_IMAGE_SIZE`, `GEMINI_BASE_URL`
- GH Actions `daily-collect.yml`에 `GEMINI_API_KEY` secret env 추가 (미등록 시 무해)

### 테스트
- 신규 7건 (T1~T7): 나노바나나 성공/data URI·폴백 0회·키 미설정 불변·Bailian 폴백·DashScope 폴백·가드·파싱
- `conftest.py`: autouse 픽스처로 `GEMINI_API_KEY` 테스트 격리 (Windows 환경변수 상속 방지 — 기존 테스트 수정 없음)
- 전체 pytest **404 passed / 10 skipped** (기존 395 + v28 신규 9)

### 문서
- `docs/planning/02-trd.md` 이미지 섹션 — 나노바나나 1차·data URI 저장·소비처 방침 반영
- `.env.example` — GEMINI 4종 옵션 항목
- `pipeline/image-gen-nanobanana/` — plan·tech-design·implementation-report (md+html)

## v26 — 2026-08-13 (이미지 프로바이더 폴백 · 쿼터 모니터링 알림)

> VERIFICATION.md §6 미해결 항목 해소 — proposal-13-image-fallback (권장안 A+B 소형 패키지)

### 추가
- **DashScope 이미지 폴백** (`image_gen.py`, FR-1~FR-3) — Bailian 이미지 호출 실패(4xx/5xx·타임아웃·파싱 실패) 시
  `DASHSCOPE_API_KEY`가 설정돼 있으면 `wanx2.1-t2i-turbo`로 **1회 재시도** (대표·섹션 공통 `_run_http` 레벨)
  - ⚠️ 공식 문서 실측: wanx2.1은 **동기 호출 미지원** → 비동기 흐름 구현
    (POST `image-synthesis` + `X-DashScope-Async: enable` → GET `/tasks/{id}` 3초 폴링, 예산 55s)
  - 키 미설정 시 폴백 비활성 — 기존 동작 100% 불변 (FR-2), 폴백도 실패 시 최종 원인 포함 예외 전파 (FR-3)
  - 폴백 발생 시 WARNING 로그 (원본 예외 메시지 + 폴백 모델, AC1-4)
- **이미지 실패 집계·임계 알림** (`content_batch.py`·`collect.py`, FR-4/FR-5)
  - 결과 dict에 `image_attempts`·`image_failures`·`image_alert` 추가 (백필+신규, 대표+섹션 전부 집계)
  - 임계: **연속 5건 또는 시도 5건+ 실패율 50% 초과** → ERROR 로그 + `image_alert: True`
  - `collect.py main()`: `image_alert`이면 `exit 1` → **GH Actions 잡 실패 전파** (기존 ERROR 로그만으로는
    잡이 실패하지 않던 문제 해소 — 실측 기반, AC5-5)
  - 배치 실행 이력: `collection_runs`에 result 컬럼이 없어(실측) **note JSON에 이미지 집계 병기** (AC4-4, 스키마 무변경)
- `llm_client.py`: `post_json(headers=...)` 선택 헤더 + `get_json()` 추가 (순수 추가 — 기존 동작 불변)

### 환경변수
- `DASHSCOPE_API_KEY` 추가 (선택 — 미설정 = 폴백 비활성). **Bailian과 다른 계정 키 권장**
- `DASHSCOPE_BASE_URL` 추가 (선택 — QA P2) — DashScope 리전별 호스트 오버라이드:
  베이징 `https://dashscope.aliyuncs.com`(기본) / 싱가포르·국제 `https://dashscope-intl.aliyuncs.com`
  (키 발급 리전과 호스트 불일치 시 인증 실패 — 국제 키 사용 환경에서 필수)

### 테스트
- 신규 11건: 폴백 4 (T1~T3 + P2 리전 오버라이드) · 집계·임계 5 (T4·T5a·T5b·T6 + P4 신규 초안 경로)
  · collect 실패 전파 2 (T7a·T7b)
- `test_skips_without_llm_key` 기대값 갱신 (FR-4 계약 — 결과 dict에 신규 키 추가)
- 전체 pytest **388 passed / 10 skipped** (기존 377 + 신규 11)

### 문서
- `docs/planning/02-trd.md` 이미지 섹션 — 폴백·모니터링·성능(NFR-1) 반영, stale 문구(키 401) 갱신
- `.env.example` — `DASHSCOPE_API_KEY` 옵션 항목
- `docs/VERIFICATION.md` §6 — "미해결(별도 논의)" → 해소 표기

## v25 — 2026-08-11 (키워드 대시보드 UX 개선)

### 변경
- **기본 프리셋 전체 표시** — 대시보드 첫 로드·필터 초기화가 전체 키워드(활성 전체) 기준으로
  변경 (UX-1/UX-2, 기존 ai_pick 기본 → 명시적 선택). 페이지네이션에 `N건 (프리셋명)` 라벨 표시
- **쇼핑클릭 필터 옵션 통합** — 0.001+/0.01+ 중복 옵션을 '클릭 수집됨 (값 있음만)' 하나로 통합,
  전체 라벨을 '쇼핑클릭 전체 (미수집 포함)'로 명확화 (UX-3)
- **프리셋 툴팁** — AI픽/유망/상승/곧 뜰 버튼에 기준(백분위) 설명 title 추가 (UX-4)

### 테스트
- `tests/test_api.py` 기본 preset 기대값 2건 갱신 — 전체 pytest 377 passed

### 문서
- `docs/KEYWORD-UIUX.md` — UX-1~UX-5 해결 상태 반영 (분석 보고서 갱신, 커밋 a3b94ba)
- **배포 확인**: 프로덕션(autostudio-eight.vercel.app) 실측 — 기본 호출 전체(203건) vs ai_pick(59건),
  HTML 마커(UX-2/3/4) 반영 확인 완료

## v24 — 2026-08-11 (프롬프트 개선 · 리서치 반영)

### 추가
- **AI 브리핑·AI 탭 인용 구조 지시** (pass1/pass2) — 질문-답변·리스트·단계·표 구조로
  AI가 답변 근거로 인용하기 쉽게 작성 (P2-1)
- **허위 출처 검수** — '조사에 따르면'류 11종 패턴 감지 → 검수 실패 + 재생성 피드백 (P1-2)
- **정보형 템플릿 non-commodity** — 일반 상식 나열 금지, 구체적 기준·숫자·비교·함정 중심 (P2-2)
- **제목 지시 보강** — 연도·정보성·핵심 요약("N가지 방법") (P3)

### 변경
- SYSTEM_PROMPT: "실제 경험 기반" → "검증 가능한 정보" + 경험·출처·통계 창작 금지 (P1-1)

### 문서
- `docs/RESEARCH.md` — 블로그 프롬프트 개선 리서치 (5개 출처, 갭 분석)

## v23.1 — 2026-08-11 (할당량 폴백)

### 추가
- opencode-go 호출이 할당량(429)/서버 오류(5xx)로 실패하면 **Bailian 자동 폴백** —
  쿼터 소진 시 초안 생성 마비 방지 (테스트 3건)

## v23 — 2026-08-11 (초안 LLM 프로바이더 전환)

### 변경
- 초안 생성 LLM: Bailian(Token Plan) → **OpenCode Go (zen/go, deepseek-v4-flash)** 우선
  - `OPENCODE_GO_API_KEY` 설정 시 사용, 미설정 시 Bailian 폴백
  - deepseek-v4-flash는 reasoning 모델 — `thinking: {"type": "disabled"}`로 추론 OFF
  - 브라우저 UA 추가 (zen/go Cloudflare 앞단 차단 대응)
- 이미지 생성은 Bailian 유지 (변경 없음)

### 환경변수
- `OPENCODE_GO_API_KEY` 추가 (GitHub Secrets / Vercel Env / .env.local)

## v22.3.2 — 2026-08-11 (마지막 v22)

- daily-collect에 autoblog 발행 env 추가 — 운세 자동 발행 활성화
- product_recommend f-string syntax error 수정

## v22.3 — 2026-08-10 (운세 채널 자동화)

- 운세 콘텐츠 자동 생성·발행 (daily/weekly/monthly/일주·별자리·띠 고정 콘텐츠)
- `engine/` 만세력 엔진 포팅 (calendar/day_pillar/fortune_content/fortune_extra)
- 별도 블로그(autoblog) 발행 클라이언트 + 게시 API

## v22.2 — 2026-08-09 (만세력 엔진)

- myunglab 만세력 데이터 → SQLite 변환 (`engine/data/engine.db` 커밋)
- 한국 법정 시간(표준/일광절약) 포팅, 60일주 문구 세트

## v22.1 — 2026-08-07

- 운세 채널 기획 확정 (11-fortune-channel), B2B/B2C 분리

## v21 — 2026-08-06 (출구 뚫기 + 카테고리 리밸런싱)

- 카테고리 비중 가드 (시드/발굴), '곧 뜰'(upcoming) 프리셋 — 초안 우선순위 연결

## v20 — 2026-08-05 (변별력 회복)

- GROWTH_NORM_MAX 0.05 → 0.15, demand 정규화 0.01 → 0.02, 카테고리별 fresh window
- 은퇴 스냅샷 3개 가드, 실측 CPC 베이지안 스무딩(prior=3)

## v19 — 2026-08-05 (멀티 플랫폼)

- 네이버(플레인)/티스토리/애드센스/브랜드 플랫폼 분기 (platforms.py 단일 소스)
- 썸네일 아이디어, 배치 플랫폼 지정

## v18 — 2026-08-04 (수익 최적화)

- AdPost 리포트 임포트, 카테고리 실측 CPC/RPM, 게시 플래너, 리프레시, 수익 인사이트

## v17 — 2026-08-04 (콘텐츠 배치)

- 스케줄 수집의 초안·이미지 배치 (시간 제약 없는 GH Actions), 이미지 증분 생성
- 하드 예산 55초 + 호출 타임아웃 클램프, outline facts/comparisons 그라운딩

## v16 — 2026-08-03

- 발행 기준일 공유 (temporal_relevance), v15 인증 fail-closed 강화

## v15 — 2026-08-03

- llm_client 공용 레이어 (펜스 제거·오류 정규화), ENV 소문자 정규화, 읽기 API 인증

## v14 — 2026-08-03 (자가보정 임계)

- 백분위 기반 임계 (P50/P75/P25), priority 가중치 30/25/15/30, 성장 신호 반영
- 정제 규칙 개선 (len/noise/brand), BFS 팬아웃 차단

## v13 — 2026-08-02

- 배지/프리셋 임계 재보정

## v12 — 2026-08-01 (수요 정규화)

- demand_idx 앵커 정규화 ('냉장고'), priority demand 항 복원

## v11 — 2026-08-01

- 본문 길이·H2 개수 검수, 밀도 공백 무시 보정, 재생성 시간 예산

## v10 — 2026-07-31 (2패스 + 검수 8항목)

- 1패스(H2 골격) → 2패스(섹션 확장) + 검수 8항목 + 1회 재생성
- 의도 분류 (정보/비교/구매)
