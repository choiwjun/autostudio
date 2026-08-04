# 네이버 블로그 콘텐츠 자동화 TRD (기술 요구사항 명세)

> 작성일: 2026-08-04 · 버전: v1

## 1. 기술 스택

### 글 텍스트 생성
- `opencode run -m opencode-go/deepseek-v4-flash` (비대화형 1회성 실행, 검증 완료 — "1+1"→"2")
- 프롬프트에 상위글 골격(구조 JSON)을 넣고 초안을 받아옴

### 이미지 생성
- Aliyun Bailian CLI: `bl image generate` (qwen 계열: wan2.7-image / qwen-image)
- ⚠️ 현재 API 키 401 무효 — 재발급 필요 (사용자 작업). 유효한 BAILIAN_TOKEN_PLAN_API_KEY가 `.qwen/settings.json`에 존재

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
- 이미지 생성 API 키는 서버 환경 변수로만 관리 (프론트 노출 금지)

## 4. 성능 요구사항

- 초안 생성 응답: 60초 이내 (opencode CLI 1회 실행, Vercel 함수 60초 상한 내)
- 이미지 생성: 비동기 처리 — 생성 중 "생성 중..." 상태 표시, 완료 후 URL 저장
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
