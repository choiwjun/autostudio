# HANDOFF — 작업 인계서 (2026-08-16)

> 작성: 오케스트레이터 (DeepSeek Harness 세션) · 프로젝트: autostudio
> 목적: 진행 중 작업을 다음 세션/에이전트가 즉시 이어받을 수 있도록 상태·산출물·필요 조치를 정리

---

## 1. 요약 — 지금 무엇이 진행 중인가

| 작업 | 상태 | 커밋 |
|---|---|---|
| v27~v29.6 운세 기능 (생성·발행 분리, 띠 합본, 대상 배지, 레이아웃) | ✅ 완료 + 배포 | `b7cab8c`~`7930795` |
| v29.7~v29.9 쇼츠+KDP 기획 다듬기 | ✅ 완료 + 배포 | `cbdc7b0`~`331f00f` |
| **v30 KDP 파이프라인 구현 (K-1~K-4)** — 주제 선정·책 생성·EPUB·출간 큐·48h 모니터링·대시보드 탭 | ✅ 완료 + 배포 (개발QA 승인, 464 passed) | `6f1634f` |
| **v30.1 KDP 백로그 해소 (R-1/R-2)** — 배치 research 자율 실행·배치 EPUB 표지 첨부 | ✅ 완료 + 배포 (467 passed, 회귀 0) | `41522de` |
| **쇼츠 구현 (S-1~S-4)** | ⏸ **다음 단계 — 미착수** (YouTube Data API v3 키 필요) | — |
| **KDP 파일럿** (52주 워크북 + 아마존 스냅샷 게이트) | ⏸ 대기 — **GH Actions 시크릿 4종 등록 필요** | — |

**현재 브랜치: main, origin과 동기화 완료 (v30 `6f1634f`·v30.1 `41522de` 커밋·푸시·배포 반영 — https://autostudio-eight.vercel.app)**

---

## 2. 파이프라인 운영 상태

- 사용자 요청: 모든 기능 작업을 **work-pipeline(9단계 팀 파이프라인)** 으로 실행
- 이번 턴: 쇼츠+KDP 기획 다듬기 = **standard 모드 5단계 완료** (요구사항→리서치→리서치QA→기획→기획QA) + QA 보강 2회 + 오픈소스 조사 반영
- **사용자 규칙 (중요)**: 커밋·푸시·배포는 **사용자가 명시적으로 말할 때만** — "진행해" 말고는 절대 금지. 글로벌 메모리 저장됨
- 완료된 팀 세션은 `rlm.list_subagents()` → `delete_subagent`로 삭제해 이름 충돌 방지 (이전 팀 이름 재사용 시 필수)

---

## 3. 쇼츠+KDP 기획 작업 상세

### 작업 디렉토리: `pipeline/shorts-kdp-research/`

| 산출물 | 내용 |
|---|---|
| `requirements.md` | 요구사항 명세 (standard 모드, 사용자 답변 Q1~Q7 포함) |
| `research-report.md` | 리서치 7주제 (쇼츠 시장·알고리즘·API 정책·KDP 시장·정책·시너지·운세) — 출처 54개 |
| `research-qa-report.md` | ✅ 승인(조건부) — 수치 40+건 교차 검증 |
| `plan.md` | PRD — **AC 22개**, F-1~F-7 + F-P(파일럿 게이트) |
| `trd.md` | 기술 요구사항 — 쿼터 예산(≤100 units), calibre/Java, TTS 라이선스 |
| `userflow.md` | 여정 5개 |
| `tasks.md` | **S-1~S-4 / K-1~K-4** 태스크 (총 ~27h, 의존성·AC 연결) |
| `test-design.md` | TC 66건 (AC↔TC 추적성 유지) |
| `planning-qa-report.md` | ✅ 승인 — 수치 모순 0건, 8건 매핑 실증 |
| `opensource-report.md` | **오픈소스 도구 조사 55개** — 라이선스·별·적용 모듈 매핑 |

### 개정 기획 문서 (docs/planning/)
- **`14-shorts-pipeline.md`** (+html) — 유튜브 쇼츠 파이프라인 (신규 고도화)
  - 핵심: 네이버 키워드가 아닌 **유튜브 인기 주제/채널/키워드** 기반
  - 전략: 쇼츠 광고(RPM $0.01~0.07)=보조, **KDP/운세 유입=실질 수익원**
  - 지표: 조회급상승·조회/구독·반응비(보조)·틈새 + 공유율(채널 소유 시 조건부)
  - 파일럿 exit criteria: 30일 조회 1만+·완주율 70%+
  - TTS: edge-tts(LGPL-3.0·비공식 API) → **MeloTTS(MIT·한국어) 대체 후보**
- **`12-kdp-pipeline.md`** (+html) — KDP 전자책 (개정)
  - **개선점 8건 전부 반영** + §10 매핑표 (NFR-4)
  - 일 3권 통일, 의존성(ebooklib AGPL→pypub 대안, calibre+openjdk), QC 8항목(sentence-transformers·textstat·LanguageTool+py-hanspell), 48h 모니터링, 영어/한국어 병행, 수익 모델(로열티·손익분기), KDP↔쇼츠 시너지
  - 파일럿: "52주 절약 챌린지" + 아마존 경쟁도 스냅샷 게이트, 90일 50권+
- **`11-fortune-channel.md`** §9 개정 — 쇼츠 이연 해소 (한국어 운세·영어권 KDP 쇼츠 포함)

### 핵심 결정 (OQ-1~5)
- OQ-1 수집 빈도: **매일 1회** (쿼터 100 units/일 = 1%)
- OQ-2 주제 비중: **운세 4 + KDP 3 + 일반 3** (10개 소재 → 5개 쇼츠)
- OQ-3 KDP 파일럿: **"52주 절약 챌린지" 유지 + 경쟁도 스냅샷 검증**
- OQ-4 TTS: **edge-tts 채택 → MeloTTS 대체 후보 (파일럿 전 검증)**
- OQ-5 채널: **분리 권장** (한국어 운세 / 영어 KDP)

---

## 4. 다음 단계

### ⚠️ 선행 조치 (KDP 파일럿 전 필수)
1. **GH Actions 시크릿 4종 등록** (GitHub → Settings → Secrets): `DATABASE_URL` · `OPENCODE_GO_API_KEY` · `BAILIAN_TOKEN_PLAN_API_KEY` · `GEMINI_API_KEY` — `kdp-pipeline.yml`(스케줄 06:30 KST)이 이 시크릿으로 동작. 미등록 시 배치가 조용히 실패
2. **calibre/epubcheck 러너 실측** — 배치 최초 실행 시 검증 (로컬은 EPUB 구조 검증만, 12-kdp §2.1)

### 쇼츠 구현 (14-shorts-pipeline.md §6, tasks.md S-1~S-4 — 미착수)
1. **S-1** DB 스키마(youtube_raw·shorts_topics·shorts_scripts) + `shorts_research.py` (유튜브 수집 — API v3) ~3h — **YouTube Data API v3 키 필수**
2. **S-2** `shorts_topic.py` (주제 판정·틈새 스코어 — 개정 지표) ~2h
3. **S-3** `shorts_script.py` (스크립트 생성 + 검수 + TTS/자막 — edge-tts 라이선스 게이트) ~3h
4. **S-4** 배치 + 대시보드 탭 + 파일럿 (10개 소재 → 5개 쇼츠)

### KDP 파일럿 (시크릿 등록 후)
- "52주 절약 챌린지" 워크북 1권 + 아마존 경쟁도 스냅샷 게이트 (OQ-3) → exit criteria 90일(50권+·리뷰 5개+)
- 배치 자율 research(R-1 해소됨)로 신규 주제 후보 자동 산출 → 대시보드에서 승인 → 생성 흐름 확인

---

## 5. 사용자 필요 조치

1. **GH Actions 시크릿 4종 등록** (KDP 배치용 — §4): `DATABASE_URL`·`OPENCODE_GO_API_KEY`·`BAILIAN_TOKEN_PLAN_API_KEY`·`GEMINI_API_KEY`
2. **YouTube Data API v3 키 발급** (쇼츠 S-1 전 필수) — Google Cloud Console에서 활성화 → `.env.local`에 `YOUTUBE_API_KEY` 추가
3. **KDP 계정** (출간 전) — 개인 가입, 펜네임, AI 생성 콘텐츠 공개 표기 준비
4. (기존 미해결) 네이버쇼핑커넥트 PID Vercel env 설정 / BLOG_TOKEN 교체 / Bailian 쿼터 / Google billing
5. 배포: Vercel CLI 인증됨 (`bricksoftc-7455`) — `vercel --prod --yes` (v30·v30.1 반영 완료)

---

## 6. 환경 메모 (반복 실패 방지)

- **pytest**: `./.venv/Scripts/python.exe -m pytest -q` (Windows venv — WSL에서 exe 직접 실행)
- **⚠️ pycache 함정**: server.py 등 수정 후 uvicorn 재기동 시 `__pycache__`가 stale이면 **구버전 코드 서빙** — 재기동 전 `rm -rf __pycache__` 또는 `PYTHONDONTWRITEBYTECODE=1` 사용
- **WSL↔Windows 네트워크 격리**: WSL curl로 Windows 서버 접근 불가 — HTTP 검증은 Windows 내부에서 (Playwright·Python 스크립트)
- **md-to-html 실제 경로**: `/home/wj941/.agents/skills/md-to-html` (`cd` 후 `.venv/bin/python scripts/md2html.py <in> <out>`) — 팀 스펙의 `~/.prime/...` 경로는 존재하지 않음
- **pytest 수집 오염**: 프로젝트 루트/`tests/` 외 `pipeline/*/` 아래 QA 임시 .py가 있으면 pytest가 수집해 오염 — 임시 스크립트는 사용 직후 삭제 (`.gitignore`에 `pipeline/*/_qa_tmp/` 추가됨)
- **팀 spawn 전**: 같은 이름 이전 팀 세션 삭제 필수 (`rlm.list_subagents()` → `delete_subagent`)
- **refine 스킬**: 프로젝트 `refine.py`가 섀도잉 — 스킬은 `/home/wj941/.npm-global/lib/node_modules/prime-agent/dist/skills/refine/src/refine/__init__.py`를 importlib로 직접 로드
- **프로덕션 DB**: `.env.local` DATABASE_URL = Supabase. 실운영 페이지: `https://autostudio-eight.vercel.app`
