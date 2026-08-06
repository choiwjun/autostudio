# AutoStudio — 네이버 블로그 애드포스트 키워드 발굴 + 초안 생성 파이프라인

네이버 블로그 애드포스트 수익화를 위한 **키워드 발굴 + AI 초안 생성 자동화 플랫폼**.
로컬 PC 없이 GitHub(Supabase + Vercel + GitHub Actions)에서 동작하며 로컬 부담은 0입니다.

## 파이프라인

```
자동완성 크롤링(발굴) → 정제(refine) → 네이버 API 스냅샷 → 점수화
→ 데이터랩 수요/쇼핑클릭 → 은퇴 판정 → 2패스 LLM 초안(검수 8항목) → 이미지 → 대시보드
```

- **발굴** — 시드 키워드를 네이버 자동완성으로 BFS 확장, 블랙리스트/길이/노이즈/브랜드 정제.
  노이즈는 확장 단계에서 경유지로도 배제(팬아웃 차단), 거부율은 실행 note에 기록.
- **점수화** — 수집 시 사전계산 (조회 시 재계산 금지)
  - `ai_cite_idx`: 질문형 패턴 + 최신성 + 카테고리 가중 (AI 브리핑 인용 가능성)
  - `opportunity`: 40×최신성 + 30×증감률(일 5% 만점) + 30×(1−경쟁 포화, 1만 글 포화)
  - `demand_idx`·`demand_growth`: 데이터랩 앵커('냉장고') 정규화 + 30일 시계열 기울기
  - `priority` = 30×AI인용 + 25×수요 + 15×성장 + 30×CPC등급 (+ 성과 boost, [-20,20] 클램프)
- **자가보정 임계 (v14)** — 프리셋/배지/은퇴 임계가 하드코딩 절대값 대신 활성 키워드
  최신 스냅샷의 백분위(프리셋 P50/P75, 은퇴 P25)를 조회 시마다 계산해 데이터 분포를
  따라감. 표본 < 20 또는 P50=0이면 절대값 폴백. `/keywords` 응답의 `thresholds` 필드로 노출.
- **초안 생성** — 1패스(H2 골격) → 2패스(섹션 확장) → 검수 8항목(제목/즉답/길이/H2/표/FAQ/
  키워드 밀도/허위경험) → 미달 시 실측 수치 피드백을 주입해 1회 재생성. 서버리스 예산 가드.
  outline이 추출한 수치·비교 문장은 그라운딩 블록으로 2패스 프롬프트에 주입되고,
  LLM 호출 타임아웃은 하드 예산(Vercel 60초 내)에 1회차부터 클램프됩니다.
- **콘텐츠 배치 (v17)** — 스케줄 수집(GH Actions)이 초안·대표/섹션 이미지를 시간 제약
  없이 자동 생성합니다. 대시보드 요청 경로는 증분 생성(요청당 38초 창, 생성 즉시 저장)으로
  서버리스 60초 한도 내 안전 동작. AdPost 리포트 CSV 임포트(`/adpost/import`)가
  수익·노출·클릭을 초안에 매칭해 성과 점수·priority를 자동 보정하고, 게시용 마크다운
  내보내기(`/drafts/{id}/export`)로 복붙 게시를 지원합니다.

## 로컬 실행

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt   # 프로덕션만이면 requirements.txt
# .env.example을 .env로 복사해 설정 (개발은 SQLite 기본값으로 충분)
.venv\Scripts\python -m uvicorn server:app --port 8000   # http://localhost:8000
.venv\Scripts\python collect.py                          # 수집 배치 1회
python -m pytest tests -q                                # 테스트
```

키워드 추가·수집 트리거는 대시보드에서 합니다. 쓰기(수집/시드/초안)는 프로덕션에서
`DASHBOARD_TOKEN` 필수 — 로컬 개발(`ENV` 미설정)만 인증 생략. **v15부터 읽기 API도
인증 대상**이라 프로덕션 대시보드는 토큰 입력 후 사용 가능합니다.

## 배포 체크리스트

1. GitHub 저장소는 **private** 유지
2. Supabase 프로젝트 생성 — **무료 플랜 활성화** 필요
   - GitHub Secrets `DATABASE_URL` = Session pooler (포트 5432)
   - Vercel Env `DATABASE_URL` = Transaction pooler (포트 6543)
   - `db.<ref>.supabase.co` 호스트만 사용 (IPv6 주소는 Actions/Vercel에서 연결 실패)
3. GitHub Secrets: `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`, `DATABASE_URL`,
   `BAILIAN_TOKEN_PLAN_API_KEY` (콘텐츠 배치용 — 미등록 시 초안·이미지 배치만 생략)
4. `npx vercel --prod` 배포, Vercel Env에 `DASHBOARD_TOKEN`, `ENV=production`,
   `BAILIAN_TOKEN_PLAN_API_KEY` 설정
5. 매일 07:17 KST 자동 수집: `.github/workflows/daily-collect.yml`
6. PR/푸시 테스트: `.github/workflows/ci.yml`

## 환경변수

| 이름 | 설명 |
|---|---|
| `DATABASE_URL` | Postgres 접속 문자열. **비개발 환경 필수** (미설정 시 기동 거부, fail-closed) |
| `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` | 네이버 검색/데이터랩 API 키 |
| `BAILIAN_TOKEN_PLAN_API_KEY` | 초안·이미지 생성 LLM 키 (Token Plan) |
| `BAILIAN_TOKEN_PLAN_BASE_URL` | LLM 엔드포인트 오버라이드 (선택) |
| `DASHBOARD_TOKEN` | 대시보드 API 토큰. **비개발 환경 필수** (읽기·쓰기 전부 인증) |
| `ENV` | `development`(기본, 인증 생략) / 그 외 값은 전부 프로덕션 취급 (소문자 정규화) |
| `DATALAB_ANCHOR` | 수요지수 정규화 앵커 키워드 (기본 `냉장고`) |
| `ACTIVE_KEYWORD_CAP` / `DAILY_NEW_KEYWORD_CAP` | 활성 키워드 총량(기본 500) / 일일 신규 상한(0=무제한) |
| `CONTENT_BATCH_ENABLED` | 스케줄 수집의 초안·이미지 배치 (기본 1) |
| `CONTENT_BATCH_MAX_NEW` | 회당 신규 초안 상한 (기본 2) |
| `CONTENT_BATCH_BUDGET_SECONDS` | 배치 시간 예산 (기본 2400, Actions 60분 내) |

## 설계 제약

- 활성 키워드 상한 500개(`ACTIVE_KEYWORD_CAP`) — API 할당·Actions 예산·Supabase 무료
  한도를 고려한 계수 (예산 60초당 ~10개 스냅샷 순환)
- 발견 14일 이상 + 최근 7일 성과가 백분위 하위권(기회점수 P25) & 쇼핑클릭 < 0.5면 자동 은퇴
  (성과 boost ≥ 10 키워드는 보호, 기회점수 NULL은 수집 실패로 간주해 보호).
  클릭 데이터가 한 번도 없는 키워드(상위 슬롯 밖·분야 미매칭)는 기회점수 단독 판정 —
  과거 클릭 이력이 있는데 최근 NULL인 경우만 수집 공백으로 보호 (v17)
- 데이터랩 갱신은 상위 100개 고정 + 100개 순환(수요 갱신 오래된 순) 슬롯 — 활성 전체가
  ~5일 주기로 골고루 갱신됨 (v17)
- 날짜 키는 전부 KST (러너/서버리스는 UTC라 오염 방지)
- 보존: daily_stats 90일, top_results 30일, collection_log 180일
- 외부 API(네이버/데이터랩/쇼핑인사이트/LLM)는 429·5xx·네트워크 오류 시 지수 백오프 재시도

## 주요 설계 결정

- **쓰기 작업(시드/수집/은퇴)은 `DASHBOARD_TOKEN` 필수** — 프로덕션(`ENV≠development`)에서는
  토큰 미설정 시 기동 자체를 거부 (fail-closed). 읽기 API도 v15부터 동일 토큰 요구.
- 수집 실패는 조용히 성공 처리 금지 — 상태(partial/failed) 기록 + exit 1(실패 메일).
  대체 스케줄러(cron-job.org)가 `/collect`에 `{"trigger":"schedule"}`로 호출하면 전체
  파이프라인(발굴·수요·쇼핑클릭·은퇴·보존) 실행.
- 수동 수집 버튼은 시간 예산(45초) 내 스냅샷만 — 전체 수집은 스케줄러 담당.
- GitHub Actions 비활성화 방지: 50일 미커밋 시 keep-alive 빈 커밋.
- Supabase 무료 한도(7일) 대응: 미사용 시 정지되므로 `/status`의 '마지막 성공 수집'과
  Actions 실패 메일을 주기적으로 확인.
- 키는 GitHub Secrets/Vercel Env에만 저장, 커밋 금지 (`.env*`는 gitignore 대상,
  `.env.example`만 예외)

## 구조

| 모듈 | 역할 |
|---|---|
| `collect.py` | 배치 오케스트레이션 (발굴→스냅샷→수요→쇼핑클릭→은퇴→보존, 실행 잠금·예산) |
| `autocomplete.py` / `refine.py` | 자동완성 BFS 확장 / 노이즈 정제 |
| `analyzer.py` / `outline.py` | 블로그 검색 신호 추출 / 상위글 골격 구조화 |
| `scoring.py` / `db.py` | 점수 공식 / 저장소(SQLite↔Postgres 이중 SQL, 백분위, priority SQL) |
| `draft_pipeline.py` / `draft_generator.py` / `image_gen.py` | 2패스 초안 + 검수 / LLM 호출 / 이미지 |
| `content_batch.py` | 스케줄 수집의 초안·이미지 배치 생성 (이미지 백필 + 신규 초안) |
| `adpost.py` / `publish.py` | AdPost 리포트 CSV 파싱·점수 환산 / 게시용 마크다운 내보내기 |
| `llm_client.py` | LLM 공통 레이어 (키 해석·펜스 제거·오류 정규화) |
| `datalab.py` / `shopping_insight.py` / `naver_client.py` | 외부 API (재시도·오류 정규화) |
| `server.py` / `static/` | FastAPI + 대시보드 SPA |

## 설계 문서

`docs/superpowers/specs/` — 대시보드 설계·UX, v14 추출·추천필터링 개선고도화(데이터 기반
자가보정 임계) 등.
