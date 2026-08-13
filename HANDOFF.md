# HANDOFF — 작업 인계서 (2026-08-13)

> 작성: 오케스트레이터 (Prime Agent 세션) · 프로젝트: autostudio
> 목적: 진행 중 작업을 다음 세션/에이전트가 즉시 이어받을 수 있도록 상태·산출물·필요 조치를 정리

---

## 1. 요약 — 지금 무엇이 진행 중인가

| 작업 | 상태 | 커밋 |
|---|---|---|
| v26 이미지 DashScope 폴백 + 쿼터 알림 | ✅ 완료 (QA 승인, 파이프라인 종료) | `673fdb1` (커밋됨) |
| **v27 Google Nano Banana 이미지 통합** | ✅ 구현 완료 + QA 조건부 승인 + B1 수정 완료 | **미커밋** |
| **v28 운세 발행 버튼 (POST /fortune/publish)** | ✅ 구현 완료 (404 passed) + **QA 진행 중** | **미커밋** |
| 운세 발행 401/429 진단 | ✅ 원인 확정 (아래 §4) — 수정은 사용자 설정 필요 | — |

**⚠️ 워킹트리에 미커밋 변경 16파일 + 2개 파이프라인 산출물 디렉토리 (+1,011/-52줄) — 다음 세션은 먼저 아래 §3 검증 후 커밋할 것**

---

## 2. 파이프라인 운영 상태

- 사용자 요청: 모든 기능 작업을 **work-pipeline(9단계 팀 파이프라인)** 으로 실행. small 모드 = 요구사항팀 → 개발팀 → 개발QA팀
- v27/v28 모두 small 모드로 진행됨. 산출물은 각 `pipeline/<작업명>/` 아래 (requirements/plan/tech-design/implementation-report/dev-qa-report + .html)
- **진행 중**: dev-qa-team(`sub-a60be42b`)이 v28 QA 검증 중 — 실통신(autoblog 실제 401) 검증까지 완료한 상태(DB publish_failed 6→16건 증가 = 실패 사유 표시 검증 완료). **완료 답신 수신 대기** → 승인 시 §3 커밋 진행
- 완료된 팀 세션은 삭제해도 됨 (`rlm.list_subagents()` → `delete_subagent`). 이름 충돌 시 spawn 전 정리 필수
- 작업 디렉토리 컨벤션: `pipeline/<영문 snake_case>/` (프로젝트 루트)

---

## 3. 미커밋 작업 상세 (커밋 전 검증 항목 포함)

### v27 — Nano Banana 이미지 생성 통합
- **목적**: `GEMINI_API_KEY` 설정 시 이미지 생성 1차 프로바이더를 Google Nano Banana(`gemini-3.1-flash-image`, 16:9·1K·JPEG)로. 실패 시 Bailian→DashScope 폴백. 미설정 시 기존 동작 100% 불변
- **구현**: `image_gen.py`(interactions API + x-goog-api-key + steps 파싱 → data URI 저장), `llm_client.py`(빈 키 시 Authorization 생략 가드), `server.py`(다운로드 프록시 data URI 분기), `publish.py`(data URI 생략+수동 업로드 주석), `conftest.py`(테스트 격리 autouse), `.env.example`/`daily-collect.yml`/`02-trd.md`/`CHANGELOG.md`
- **QA**: ✅ 조건부 승인 → B1 수정 완료: GEMINI_API_KEY `.strip()` 2곳 (image_gen.py L70·L217) + 테스트 1건 → **396 passed**
- **산출물**: `pipeline/image-gen-nanobanana/`
- **운영 전제(사용자 조치)**: Google 계정 billing 활성화 + Windows env 키 trailing LF 제거 (§4)

### v28 — 운세 발행 버튼
- **목적**: 대시보드 "운세 발행" 버튼 + `POST /fortune/publish` 엔드포인트 — 수동으로 운세 생성·발행 트리거, 항목별 결과(성공/실패 사유) 표시
- **구현**: `server.py`(엔드포인트·55초 예산·응답 `{created,published,failed,skipped,enabled,message,items[]}`), `collect.py`(헬퍼 3종 + `_publish_all_fortune` 위임 + `fortune_generate_step(publish=True 기본값)`), `publish_client.py`(`BlogPublishError.status_code`), `static/index.html`(버튼+fortunePanel, esc 적용)
- **검증**: 404 passed / 10 skipped (396 + 신규 8, 기존 테스트 수정 0), JS 문법 OK
- **QA 진행 중**: 실통신 401 우아한 실패 표시 검증까지 완료 — 최종 보고서·판정 대기
- **산출물**: `pipeline/fortune-publish-button/`
- **QA 임시 파일**: `pipeline/fortune-publish-button/_qa_tmp/` — QA 완료 후 삭제 대상

### 커밋 제안 (QA 승인 후)
1. `feat: Google Nano Banana 이미지 생성 통합 (v27) — GEMINI_API_KEY 1차 프로바이더, data URI 저장, 폴백 체인`
2. `feat: 운세 발행 버튼 — POST /fortune/publish + 대시보드 수동 발행 (v28)`
3. (필요 시) `docs: HANDOFF 갱신` / 파이프라인 산출물 포함 여부 — 지금까지는 산출물도 함께 커밋하는 관례 (v26처럼)

---

## 4. 운세 발행 401/429 진단 결과 (사용자 조치 필요)

| 증상 | 원인 | 조치 |
|---|---|---|
| **401 invalid token** (autoblog 발행 실패) | autostudio `BLOG_TOKEN` ≠ autoblog 서버 기대 토큰 (로컬 토큰 live probe로 재현) | autoblog(autoblog-pearl.vercel.app) 프로젝트의 `DASHBOARD_TOKEN`을 확인해 autostudio의 `.env.local` **BLOG_TOKEN**과 GH Actions secret `BLOG_TOKEN`을 일치시킬 것 |
| **429 quota** | autoblog 쪽 Bailian token-plan **주간 쿼터 소진** ("token-plan 1-week quota has been exhausted") | autoblog 서버의 Bailian 키/플랜 점검 (쿼터 리셋 대기 or 키 교체) |
| 현재 상태 | fortune_generations: publish_failed 16건 + generated 6건 — **발행 성공 0건** (최근) | 위 토큰/쿼터 해결 후 대시보드 "운세 발행" 버튼으로 재발행 가능 (publish_failed 자동 재시도 로직 있음) |

**참고**: 네이버 API 연동(수집·활용)은 정상 — daily_stats 2,238행/11일, 매일 스케줄 수집 동작. 401/429는 네이버가 아니라 autoblog 발행 경로의 문제.

---

## 5. 사용자 필요 조치 요약 (다음 세션이 안내할 것)

1. **Google AI Studio billing 활성화** — 나노바나나(유료 전용) 이미지 생성 활성화. 현재 키는 free_tier limit 0 → 429
2. **Windows User env `GEMINI_API_KEY` trailing LF 제거** — PowerShell: `[Environment]::SetEnvironmentVariable("GEMINI_API_KEY", "<키>", "User")` (값 끝 개행 제거). 코드는 strip 방어 완료됨
3. **BLOG_TOKEN 교체** (§4) — autoblog 토큰과 일치
4. **autoblog Bailian 쿼터** (§4) — 429 해소 확인
5. 배포 필요 시: Vercel 인증이 이 WSL 환경에 없음 (`vercel login` 필요) — GitHub 연동 없이 수동 배포 방식

---

## 6. 환경 메모 (반복 실패 방지)

- **pytest**: `./.venv/Scripts/python.exe -m pytest -q` (Windows venv — WSL에서 exe 직접 실행, `/tmp` 사용 금지 — Windows python이 못 봄. 스크립트는 프로젝트 루트에 둘 것)
- **md-to-html 실제 경로**: `/home/wj941/.agents/skills/md-to-html` (`cd` 후 `.venv/bin/python scripts/md2html.py <in> <out>`) — 팀 스펙의 `~/.prime/...` 경로는 **존재하지 않음**
- **Windows env 키 상속**: Windows User env 변수가 WSL 테스트에 상속될 수 있음 → conftest.py autouse 픽스처가 GEMINI_API_KEY 격리 (v27에서 추가, 유지)
- **프로덕션 DB**: `.env.local`의 `DATABASE_URL` = Supabase(프로덕션). 읽기 전용 조회 시 psycopg2 사용
- **401 live probe**: autoblog `POST /api/posts` — 토큰 검증은 본문 검증보다 먼저 (401이 먼저 옴)
