# 네이버 블로그 콘텐츠 자동화 TRD (기술 요구사항 명세)

> 작성일: 2026-08-04 · 버전: v1

## 1. 기술 스택

### 글 텍스트 생성
- `opencode run -m opencode-go/deepseek-v4-flash` (비대화형 1회성 실행, 검증 완료 — "1+1"→"2")
- 프롬프트에 상위글 골격(구조 JSON)을 넣고 초안을 받아옴

### 이미지 생성
- **v27 1차 프로바이더 — Google Nano Banana** (`image_gen.py`): `GEMINI_API_KEY` 설정 시
  Interactions API(raw REST — SDK 미사용)로 생성 (FR-1).
  - `POST {GEMINI_BASE_URL}/v1beta/interactions` + 헤더 `x-goog-api-key` (Bearer 미사용)
  - 요청: `response_format {type:"image", mime_type:"image/jpeg", aspect_ratio:"16:9", image_size:"1K"}`
    (모델 기본 `gemini-3.1-flash-image`, `GEMINI_IMAGE_MODEL`·`GEMINI_IMAGE_SIZE` env 오버라이드)
  - 응답: `steps[].content[]`에서 `type=="image"` 블록의 `data`(base64)+`mime_type` 파싱
  - **저장 정합 (FR-4)**: base64를 `data:{mime};base64,{data}` **data URI**로 저장 —
    DB 스키마 무변경(`image_url`·`section_images` TEXT 그대로), 대시보드 `<img>` 렌더링 호환
  - 소비처: ① 다운로드 프록시 `server.py _fetch_image_bytes` data URI 분기(디코드+크기 검사)
    ② `publish.py` 마크다운 내보내기 — data URI 라인 생략+수동 업로드 경고 주석 (네이버 플레인 무영향)
  - 실패 시 기존 체인 폴백 (FR-3): 나노바나나 → Bailian(`wan2.7-image`) → DashScope, 각 1회
  - `GEMINI_API_KEY` 미설정 시 **기존 경로 100% 불변** (FR-2), 키 가드는 image_gen 내부만 확장 (FR-6)
- Aliyun Bailian HTTP API (`image_gen.py`): 모델 `wan2.7-image`, 크기 `1280*720`, timeout 55s, 표준 라이브러리 urllib (v15) — 나노바나나 미설정/실패 시 1차
- **v26 폴백**: Bailian 호출 실패 시 DashScope `wanx2.1-t2i-turbo`로 1회 재시도 (FR-1).
  `DASHSCOPE_API_KEY`가 **Bailian과 다른 계정**의 키일 것을 전제 — 미설정 시 폴백 비활성 (FR-2)
- ⚠️ `wanx2.1-t2i-turbo`는 **HTTP 동기 호출 미지원**(공식 문서 실측) — 비동기 흐름:
  POST `/api/v1/services/aigc/text2image/image-synthesis`(헤더 `X-DashScope-Async: enable`)
  → GET `/api/v1/tasks/{task_id}` 3초 폴링(예산 55s) → `output.results[].url` (v26)
- **v26 모니터링 (FR-4/FR-5)**: content_batch가 시도/최종 실패/연속 실패 집계 —
  연속 5건 또는 시도 5건+ 실패율 50% 초과 시 ERROR 로그 + `image_alert` → `collect.py` exit 1
  → GH Actions 잡 실패 전파 (배치 실행 이력은 `collection_runs.note` JSON에 병기)

### 서버리스
- GitHub Actions 배치 (매일 07:17 KST 수집과 별개로, 글 생성은 사용자 트리거)
- Vercel 서버리스 (FastAPI ASGI, 기존 대시보드 API 확장)
- 로컬 PC 불필요 — 전부 클라우드에서 실행

### 데이터베이스
- Supabase Postgres (기존 사용 중, 초안·이미지 URL 저장)

## 2. 아키텍처

```
[사용자] → Vercel 대시보드 (static/index.html)
              │ POST /drafts {keyword_id}
              ▼
         Vercel 서버리스 (server.py)
              │
      ┌───────┴────────┐
      ▼                ▼
  GitHub Actions    Bailian qwen
  (opencode CLI     (이미지 생성,
   초안 생성)         키 재발급 후)
      │                │
      └───────┬────────┘
              ▼
      Supabase Postgres
      (drafts / outline)
```

- 구조: Monolith (기존 FastAPI 앱에 엔드포인트 추가)
- 패턴: 저장소 계층(db.py) → 서비스 계층(초안 생성) → API(server.py) → 프론트(단일 HTML)

## 3. 보안 요구사항

- 인증: 기존 `DASHBOARD_TOKEN` 체계 재사용 (프로덕션 fail-closed 유지, development는 토큰 생략)
- 글 생성/이미지 생성 엔드포인트는 전부 `require_token` 적용
- 이미지 생성 API 키(Bailian/DashScope/GEMINI)는 서버 환경 변수로만 관리 (프론트 노출 금지, NFR-3)

## 4. 성능 요구사항

- 초안 생성 응답: 60초 이내 (opencode CLI 1회 실행, Vercel 함수 60초 상한 내)
- 이미지 생성: 비동기 처리 — 생성 중 "생성 중..." 상태 표시, 완료 후 URL 저장
- 이미지 1건 최대 지연: 기존 55s → 폴백 포함 최대 약 110s (NFR-1 — 배치 예산 1200s·GH Actions 60분 내)
  (v27: 나노바나나 1차 + Bailian + DashScope 폴백 포함 최대 ~165s — 배치 예산 내)
- 동시 접속: 개인용 대시보드이므로 1명 가정 (별도 부하 대비 없음)

## 5. 개발 환경

- Python 3.11+ (기존과 동일)
- FastAPI 0.115.6 (기존 requirements.txt 유지)
- Node.js: opencode CLI 실행용 (GitHub Actions 러너에 설치)
- Docker: 불필요 (서버리스)
- 테스트: pytest + httpx (기존 84개 테스트 유지·확장)

## Loop Metadata

- Upstream documents referenced: 01-prd.md (Must 기능 3개)
- Downstream documents affected: 04-database-design.md, 07-coding-convention.md, 06-tasks.md
- Open questions: 이미지 생성용 qwen 키 재발급 (사용자 작업)
- Assumptions: opencode CLI는 GitHub Actions에서 실행 가능, Vercel 함수에서의 실행은 후순위 검증
- Validation criteria: 글 생성 엔드포인트가 초안 JSON 반환, 이미지 URL 저장
- Risks: Vercel 서버리스의 60초 제한과 opencode CLI 의존성 — 초안 생성은 GitHub Actions 배치로 우회 가능
