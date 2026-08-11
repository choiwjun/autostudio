# AutoStudio 프로젝트 구조 분석

## 개요

네이버 블로그 애드포스트 수익화 자동화 플랫폼. 키워드 발굴 → AI 초안 생성 → 성과 측정 → 수익 최적화까지 이어지는 파이프라인을 로컬 PC 없이 GitHub(Supabase + Vercel + GitHub Actions)에서 운영한다. Python(FastAPI) 기반 단일 저장소로, 파이프라인의 각 단계가 모듈 단위로 분리되어 있다.

## 전체 구조

```
자동완성 크롤링 → 정제 → 네이버 API 스냅샷 → 점수화 → 데이터랩 수요 → 은퇴 판정
→ 2패스 LLM 초안(검수 8항목) → 이미지 생성 → 대시보드(Supabase/Vercel)
```

- `collect.py` — 배치 오케스트레이션 (발굴→스냅샷→수요→쇼핑클릭→은퇴→보존, 실행 잠금·예산)
- `autocomplete.py` / `refine.py` — 자동완성 BFS 확장 / 노이즈 정제
- `analyzer.py` / `outline.py` — 블로그 검색 신호 추출 / 상위글 골격 구조화
- `scoring.py` / `db.py` — 점수 공식 / 저장소 (SQLite↔Postgres 이중 SQL)
- `draft_pipeline.py` / `draft_generator.py` / `image_gen.py` — 2패스 초안 + 검수 / LLM 호출 / 이미지
- `platforms.py` — 플랫폼별(네이버/티스토리/애드센스/브랜드) 규칙 단일 소스
- `adpost.py` / `publish.py` / `publish_client.py` — AdPost 성과 CSV 파싱·점수 환산 / 플랫폼별 게시 문서 내보내기·자동 발행
- `datalab.py` / `shopping_insight.py` / `naver_client.py` / `llm_client.py` — 외부 API 공통 레이어 (재시도·오류 정규화)
- `server.py` / `static/` — FastAPI + 대시보드 SPA
- `engine/` — 운세 콘텐츠 생성 엔진 (일진·사주팔자 기반, `engine/fortune_content.py`)
- `.github/workflows/` — CI 테스트, 매일 07:17 KST 자동 수집 워크플로우

## 주요 모듈 요약

### 1. 키워드 발굴·점수화 파이프라인 (`collect.py` + `autocomplete.py` + `refine.py` + `scoring.py`)

네이버 자동완성 API를 시드 키워드로 BFS 확장하고 블랙리스트·길이·노이즈·브랜드 정제를 거쳐 활성 키워드를 관리한다. 조회 시마다 백분위 기반 자가보정 임계(프리셋 P50/P75, 은퇴 P25)로 점수화하며, opportunity·demand·priority 공식으로 게재 우선순위를 계산한다. 발견 14일 이상 + 성과 하위권이면 자동 은퇴시키고, `db.py`가 SQLite(개발)/Postgres(프로덕션) 이중 SQL을 지원한다.

### 2. AI 초안 생성 파이프라인 (`draft_pipeline.py` + `draft_generator.py` + `image_gen.py` + `platforms.py`)

1패스(H2 골격) → 2패스(섹션 확장) 2단계 LLM 생성 후 제목/즉답/길이/H2/표/FAQ/키워드 밀도/허위경험 8항목 검수를 거쳐 미달 시 실측 피드백을 주입해 1회 재생성한다. 서버리스 60초 예산에 맞춘 타임아웃 클램프와 `content_batch.py`의 시간 무제한 배치 생성(이미지 백필 + 신규 초안)을 지원한다. `platforms.py`가 네이버(플레인 텍스트)·티스토리·애드센스·브랜드별 포맷·어조·검수·태그를 단일 소스로 분기한다.

### 3. 대시보드 API 서버 (`server.py` + `static/`)

FastAPI 기반 REST API로 키워드 관리·수집 트리거·초안 조회/수정·게시 플래너(`/planner`)·수익 인사이트(`/revenue-insights`)·AdPost 리포트 임포트·이미지 다운로드 프록시 엔드포인트를 제공한다. 프로덕션은 `DASHBOARD_TOKEN` 필수(fail-closed)로 읽기·쓰기 전부 인증한다. Vercel 서버리스 한도 대비 시간 예산(이미지 38초, AdPost 임포트 50초)을 모듈 상수로 관리한다.

## 배포 및 운영

- 매일 07:17 KST GitHub Actions 스케줄 수집, PR/푸시 시 CI 테스트
- Supabase(Postgres) + Vercel(서버리스), 키는 GitHub Secrets/Vercel Env에만 저장
- 외부 API(네이버/데이터랩/쇼핑인사이트/LLM) 429·5xx·네트워크 오류 시 지수 백오프 재시도
- 상세 설계 문서: `docs/planning/` (PRD·TRD·DB 설계 등), `docs/superpowers/specs/`
