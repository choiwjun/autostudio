# HANDOFF — 작업 인계서 (2026-08-16)

> 작성: 오케스트레이터 (DeepSeek Harness 세션) · 프로젝트: autostudio
> 목적: 진행 중 작업을 다음 세션/에이전트가 즉시 이어받을 수 있도록 상태·산출물·필요 조치를 정리

---

## 1. 요약 — 지금 무엇이 진행 중인가

| 작업 | 상태 | 커밋 |
|---|---|---|
| v27~v29.6 운세 기능 (생성·발행 분리, 띠 합본, 대상 배지, 레이아웃) | ✅ 완료 + 배포 | `b7cab8c`~`7930795` |
| v29.7~v29.9 쇼츠+KDP 기획 다듬기 | ✅ 완료 + 배포 | `cbdc7b0`~`331f00f` |
| v30 KDP 파이프라인 구현 (K-1~K-4) — 주제 선정·책 생성·EPUB·출간 큐·48h 모니터링·대시보드 탭 | ✅ 완료 + 배포 | `6f1634f` |
| v30.1 KDP 백로그 해소 (R-1/R-2) — 배치 research 자율 실행·배치 EPUB 표지 첨부 | ✅ 완료 + 배포 | `41522de` |
| v30.3 쇼츠 S-1 유튜브 수집 (`shorts_research.py` + `youtube_raw`) | ✅ 완료 + 배포 | `3d642e6` |
| **v30.4 적대적 QA 수정** — NaN 성과점수 만점 오염·NaN 가격 검증 우회·비-ASCII 인증 헤더 500·거대 정수 500·실패 INSERT 잠금 잔존·입력 가드 | ✅ 완료 + 배포 (487 passed) | `da23745` |
| **v31 알고리즘 전수 분석 + 결함 수정** — KDP ready 구조적 교착 해소(cover 판정·AI 표기 백매터·research 메타데이터 정합·생성 상한 2권/run)·만세력 DST TypeError 2건·2패스 1회차 초안 회수·최신성 연도 판정·물결표 범위·경량 4건 | ✅ 완료 + 배포 (509 passed) | `0470c6a` |
| **v31.1 쇼츠 S-2 주제 스코어링 + KDP 일관성 패스 실구현** — `shorts_topic.py`(개정 지표 4종·35/25/15/25점)·`shorts_topics` 테이블·channels.list 구독자 병합·KDP `consistency_pass` 챕터별 반영·NULL 컬럼 upsert 수정 | ✅ 완료 + 배포 (522 passed) | `0936c8b` |
| **v31.2 쇼츠 S-3 스크립트 생성·검수** — `shorts_script.py`(hook/본론/CTA/해시태그 + 검수 5종 + 실측 피드백 재시도)·`shorts_scripts` 테이블·GET/POST `/shorts/scripts` | ✅ 완료 + 배포 (535 passed) | `725c982` |
| **쇼츠 S-4** 배치 + 대시보드 탭 + 파일럿 | ⏸ **다음 단계** | — |
| **KDP 파일럿** (52주 워크북 + 아마존 스냅샷 게이트) | ⏸ 대기 — 배치는 시크릿 등록 완료로 **가동 상태** (v31 교착 해소로 ready 도달 가능해짐) | — |

**현재 브랜치: main, origin과 동기화 완료 (v31.2 `725c982` 커밋·푸시·배포 반영 — https://autostudio-eight.vercel.app)**

---

## 2. 파이프라인 운영 상태

- 사용자 요청: 모든 기능 작업을 **work-pipeline(9단계 팀 파이프라인)** 으로 실행
- 이번 턴 (2026-08-16 오후, PC 포맷 후 새 환경): 적대적 QA → 알고리즘 전수 분석·수정 → 쇼츠 S-2/S-3 구현 + 개발 환경 재세팅(Windows+WSL2+Docker+gh) 및 로컬 `.env.local` 복구(Vercel production pull)
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

### 쇼츠 구현 (14-shorts-pipeline.md §6, tasks.md S-1~S-4)
1. ~~S-1 수집~~ ✅ v30.3 + v31.1(channels.list 구독자 병합·S-2 자동 연계)
2. ~~S-2 주제 스코어링~~ ✅ v31.1
3. ~~S-3 스크립트 생성·검수~~ ✅ v31.2 — TTS/자막·문법검사(hanspell/LanguageTool)만 라이선스 게이트 통과 후 추가 예정
4. **S-4 배치 + 대시보드 탭 (소재 목록·스크립트 보기/복사) — 다음 작업** (~3h, 데이터 API는 `/shorts/topics`·`/shorts/scripts`로 이미 노출 — 프론트엔드 중심)
5. **파일럿**: 소재 10개(운세 4+KDP 3+일반 3) → 5개 쇼츠 제작 → 반응 확인 (전제: 채널 개설 + TTS 게이트)

### KDP 파일럿 (배치 가동 중)
- GH Actions 시크릿 **7종 등록 완료** (DATABASE_URL·NAVER 2종·BAILIAN·OPENCODE·BLOG 2종·YOUTUBE_B64 — `GEMINI_API_KEY`만 미등록, 이미지 생성 skip 경로로 동작)
- v31 교착 해소로 배치가 책을 ready로 전이 가능해짐 — **다음 배치 실행에서 kdp-pipeline 결과 관찰** (ready 전이·EPUB 조립·일 3권 게이트)
- "52주 절약 챌린지" 워크북 + 아마존 경쟁도 스냅샷 게이트 (OQ-3) → exit criteria 90일(50권+·리뷰 5개+)

### 지연된 품질 항목 (v31 알고리즘 분석에서 보류 — 수요 있을 때)
- KDP length QC 밴드(책 전체 640~1440단어) vs 챕터 6~12개 구조 모순 — 설계 의도 확인 후 조정 (현행은 챕터당 ~170단어로만 통과)
- kdp_research 스냅샷 파서 price/rating/reviews 미추출 → 틈새 점수가 권수 항으로 퇴화 (v31.1: unavailable 마킹만 추가)
- draft_generator LLM 폴백이 같은 timeout으로 2차 호출 → 하드 예산(55s) 초과 여지
- AdPost 제목 매칭(`ORDER BY id DESC`)이 리프레시 재생성본에 과거 성과 부착 가능
- 검수 피드백 없는 맹재시도 항목(faq/tables/h2_count)·키워드 밀도 2자 토큰 과대산정 문서화
- 사소: 만세력 범위 주석(1899 vs 1908)·zodiac 연도 하드코딩(2027년에 문제)·autocomplete max_requests 실측 3배 HTTP

---

## 5. 사용자 필요 조치

1. ~~GH Actions 시크릿 등록~~ ✅ **7종 등록 완료** (§4 참조 — `GEMINI_API_KEY`만 선택 미등록)
2. ~~YouTube Data API v3 키~~ ✅ `YOUTUBE_SERVICE_ACCOUNT_KEY_B64` 등록 완료 (2026-08-16) — 로컬용 원본 json은 포맷으로 소실, 로컬 테스트 필요 시 Google Cloud에서 재생성
3. **채널 구분 결정** (파일럿 전) — 운세(한국어)/KDP(영어) 최소 2채널 권장 (OQ-5)
4. (파일럿 전) **TTS 검증 게이트** — edge-tts 한국어 품질 청취 + 상업 라이선스 확인, 대체재 **MeloTTS**(MIT·한국어) 우선 검토
5. **KDP 계정** (출간 전) — 개인 가입, 펜네임, AI 생성 콘텐츠 공개 표기 준비
6. (선택) 쇼츠 제작 도구 — CapCut/Shotcut (자동화 아님)
7. (기존 미해결) 네이버쇼핑커넥트 PID Vercel env 설정 / Bailian 쿼터 / Google billing

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
- **(2026-08-16 재세팅)** PC 포맷 후 환경 재구축 완료: Windows(git/Python 3.12/Node 24/VS Code/gh/Docker) + WSL2 Ubuntu 26.04. 로컬 `.env.local`은 **Vercel(bricksoftc-7455) production에서 pull하여 복구** — NAVER/BAILIAN/OPENCODE/DATABASE_URL(pooler)/DASHBOARD_TOKEN 포함. placeholder `.env`는 `.env.placeholder-backup`으로 이동 (load 순서상 `.env`가 우선이라 실제 키를 가림 — 복원 금지)
- **배포 주소 함정**: `autostudio-mu.vercel.app`은 **옛 배포의 고유 URL (500)** — 현행 프로덕션은 `autostudio-eight.vercel.app`만 사용. GitHub repo homepage는 v31 세션에서 eight로 갱신 완료
- **GitHub Secrets 읽기 불가**: 로컬 키 분실 시 Vercel에서 pull (위 항목) — GH Actions secrets은 정책상 재조회 불가, 필요 시 각 콘솔에서 재발급
