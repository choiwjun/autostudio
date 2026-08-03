# 네이버 블로그 키워드 대시보드

네이버 블로그(애드포스트/쇼핑커넥트) 수익을 위한 키워드 발굴 + 경쟁도/상업성/수요 분석 도구.
로컬 PC 없이 클라우드(Supabase + Vercel + GitHub Actions)에서 실행됩니다. 월 비용 0원.

## 아키텍처

- **DB**: Supabase Postgres (무료 500MB, Supavisor 풀러 경유)
- **대시보드/API**: Vercel Hobby (FastAPI ASGI, 무료)
- **매일 수집**: GitHub Actions cron (매일 07:17 KST, 무료)
- 기준 시간대: 모든 날짜 키는 KST (러너/서버리스의 UTC와 무관)

## 설치 (개발 환경)

1. `python -m venv .venv`
2. `.venv\Scripts\pip install -r requirements.txt`
3. `.env.example` → `.env` 복사 후 설정 (개발은 SQLite 기본값 그대로)
4. 대시보드 실행: `.venv\Scripts\python -m uvicorn server:app --port 8000` → http://localhost:8000
5. 시드키워드는 대시보드에서 추가 (로컬은 `DASHBOARD_TOKEN` 미설정 시 인증 생략)
6. 수집: `.venv\Scripts\python collect.py`

## 클라우드 배포

1. GitHub 레포 생성 후 푸시 (private 권장)
2. Supabase 프로젝트 생성 → **풀러 연결 문자열** 사용
   - GitHub Secrets `DATABASE_URL` = Session pooler (포트 5432)
   - Vercel Env `DATABASE_URL` = Transaction pooler (포트 6543)
   - `db.<ref>.supabase.co` 직결 주소 금지 (IPv6 전용 → Actions/Vercel에서 연결 실패)
3. GitHub Secrets: `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`, `DATABASE_URL`
4. `npx vercel --prod` 배포, Vercel Env에 `DASHBOARD_TOKEN` 포함 등록
5. 매일 07:17 자동 수집: `.github/workflows/daily-collect.yml`

## 점수 설명

- 기회점수 = 40×상위글신선도 + 30×성장정규화(일 5% 만점) + 30×(1−경쟁도(1만 글 포화))
  — 최소 2일치 데이터 필요
- 상업성 = 쇼핑 상품 수·가격대 기반 0~100
- 수요지수 = 데이터랩 앵커(기본 "냉장고") 대비 상대 수요 — 기회점수 상위 200개만 매일 확증
- 프록시 신호이므로 절대 기준이 아님 — 원시값과 함께 판단

## 키워드 수명주기

- 활성 총량 캡 1,000개 (`ACTIVE_KEYWORD_CAP`) — API 쿼터·Actions 분량이 이 캡 기준으로 산정됨
- 발견 14일 후에도 저성과(기회 < 35, 상업성 < 30)면 자동 은퇴
- 대시보드 "제외" 버튼으로 수동 제외/복원
- 보존: 스냅샷 90일, 상위글 발행일 30일, 로그 180일

## 운영 주의사항

- **쓰기 동작(시드/수집/제외)은 `DASHBOARD_TOKEN` 필요** — 대시보드 우측 상단에 입력·저장. **프로덕션(`ENV=production`)에서는 토큰 미설정 시 서버가 기동되지 않음(fail-closed)** — 로컬 개발만 인증 생략
- 자동완성은 비공식 엔드포인트 — 차단 시 자동 중단·로그 기록 + exit 1(실패 메일). 차단 시 cron-job.org(무료)가 `/collect`를 `{"trigger":"schedule"}`로 호출해 전체 파이프라인을 대체
- 수동 수집 버튼은 시간 예산(45초) 내 일부 갱신용 — 발굴·개별 호출까지 예산 적용. 전체 수집은 스케줄러 담당
- GitHub Actions 스케줄은 레포 60일 무활동 시 자동 비활성화 → 워크플로우가 keep-alive 커밋으로 자체 방지
- Supabase 무료는 7일 무활동 시 일시정지 — **대시보드에서 수동 복구** 필요. /status의 "마지막 성공 수집" 경고와 Actions 실패 메일을 무시하지 말 것
- 시크릿은 GitHub Secrets/Vercel Env에만 보관, 레포 커밋 금지
