# KDP 파이프라인 구현 보고서 (K-1~K-4) — implementation-report.md

> 작성: 개발팀 · 프로젝트: autostudio · 작업 디렉토리: pipeline/kdp-implementation/
> 상태: **구현 완료 + 개발QA 재검증 반영(H-1·M-1~M-4·K2-1 수정)** · 전체 테스트 464 passed / 10 skipped
> 검증: TDD(red→green)→리팩터, conftest 외부키 격리, __pycache__ 정리 후 실행

---

## 1. 수용 기준(AC) 대응표

| AC | 구현 위치 | 판정 |
|---|---|---|
| AC-K1-1 | kdp_research.py: 영어 현지화(rule+LLM 폴백)·아마존 스냅샷(M-4 하드닝: URL quote·HTTPS 리다이렉트·5MB 상한)·틈새 판정·영어/한국어 병행·전환율 30% 게이트 | PASS |
| AC-K2-1 | kdp_book.py: 아웃라인 **K2-1 하한 강제(MIN_CHAPTERS 패딩)**·챕터 2패스·일관성 패스·예산 300초(부분 저장) | PASS |
| AC-K2-2 | QC 8항목 + **M-1 표지 AI 공개 문구(본문+표지)** + 실패 리포트 | PASS |
| AC-K3-1 | ebook_builder.py: ebooklib 조립·markdown·Pillow 6x9 표지(M-1 AI 문구)·로컬 구조 검증 + GH calibre/epubcheck | PASS |
| AC-K4-1 | 출간 큐 **M-2 원자적 게이트(트랜잭션)+M-3 체크리스트 검증·차단**·3권 초과 pending | PASS |
| AC-K4-2 | 48h 미검증 강조·verified+verified_at+mirror·**M-3 확인 POST 배선** | PASS |
| AC-DB-1 | 성과 입력 + **M-3 성과 입력 폼 배선**·손익분기표·월별 집계·측정 경로 수동 표기 | PASS |

---

## 2. 개발QA 수정 반영 (H-1·M-1~M-4·K2-1)

| ID | 결함 | 수정 | 테스트 |
|---|---|---|---|
| H-1 | K-1~K-3 배치 미연결, assembling 영구 정지 | kdp_pipeline에 research→generate→assemble 3단계 배치 연결(run_research/generate_book/build_epub 모듈 별칭) + 각 단계 count 기록 | test_run_pipeline_full_flow (end-to-end mock) |
| M-1 | 표지 AI 공개 문구 미구현(AC-K2-2) | make_cover_image에 'AI-generated' 하단 오버레이 + check_ai_disclosure cover 검사 + run_qc cover 전달 | test_check_ai_disclosure_requires_cover_text·test_run_qc_ai_disclosure_checks_cover |
| M-2 | 출간 게이트 동시성 미보장 | publish_day_gate 트랜잭션(BEGIN IMMEDIATE/Postgres FOR UPDATE) 원자화 — 오늘 published 재확인 후 max 미만만 전이 | test_publish_day_gate_atomic_concurrency (2 스레드 → 총 3권 초과 불가) |
| M-3 | 대시보드 dead UI | /kdp/publish-queue 책별 checklist + /kdp/publish 체크리스트 검증(미완료 400) + loadKdpQueue 체크리스트·출간 disabled/차단 + loadKdpMonitor 확인 POST + loadKdpPerf 성과 폼 | test_publish_blocks_incomplete_checklist·test_publish_queue_checklist_fields·test_performance_history_route |
| M-4 | 아마존 스냅샷 URL 하드닝 | urllib.parse.quote 인코딩 + allow_redirects=False·https 한정 수동 리다이렉트(최대 3회) + 5MB 스트리밍 크기 상한 | test_snapshot_url_encoded·test_snapshot_rejects_non_https_redirect |
| K2-1 | MIN_CHAPTERS(6) 미적용 | generate_outline 패딩(MIN~MAX 강제) | test_generate_outline_enforces_min_chapters |

---

## 3. 테스트 결과

### 신규 KDP 테스트 (53 passed)
- test_kdp_db.py 12 · test_kdp_research.py 9 · test_kdp_book.py 7 · test_kdp_qc.py 11
- test_ebook_builder.py 4 · test_kdp_api.py 10 · test_kdp_pipeline.py 4 = **53 passed**

### 전체 스위트
`464 passed, 10 skipped in 88.02s` — 기존 454 + QA 수정 신규 10 (회귀 0)
- 실행: ./.venv/Scripts/python.exe -m pytest -q · 모듈 import 확인(server·kdp_pipeline·kdp_research·kdp_book·ebook_builder)

---

## 4. 핵심 설계·구현 결정

1. QC 1·4(MVP): 표절·챕터 중복 = ngram/Jaccard rule(임계 0.8). sentence-transformers 미설치(인터페이스만).
2. H-1 배치: run_pipeline이 research(①)→generate(②)→assemble(③)→출간 큐(④)→48h(⑤) 순차. generate_book이 QC 통과 시 ready 전이.
3. M-1 표지: 파이프라인 생성 표지는 전부 AI-generated — 표지에 'AI-generated' 공개 문구 강제 + QC #6이 본문·표지 모두 검사.
4. M-2 게이트: BEGIN IMMEDIATE(원자화) 내 오늘 published 재확인 — 동시 배치/API에도 3권 상한 보장.
5. M-3 체크리스트: 서버가 책별 checklist(키워드7·카테고리2·AI 표기) 반환/검증, UI는 출간 버튼 disabled+차단, 48h 확인·성과 입력 폼 배선.
6. M-4 스냅샷: quote 인코딩 + HTTPS 한정 리다이렉트(server.py _fetch_image_bytes 패턴 재사용).
7. 서버리스: 생성·검증은 배치, API는 조회·다운로드·수동 상태 전이·성과만. EPUB은 ready+만.

---

## 5. 미구현 / 보류 사항

| 항목 | 사유 |
|---|---|
| calibre·epubcheck 실제 러너 | GH Actions 환경 필요 — 워크플로우 구성, 로컬은 ebooklib 조립·구조 검증만 |
| sentence-transformers(표절/중복 고정밀) | 설치 부담 — MVP rule 기반, 인터페이스 확장 가능 |
| 자동 업로드(아마존) | 계정 제재 리스크 — 반자동(수동), 산출물·체크리스트 제공까지만 |
| 48h 미러·가격 자동 점검(L-1) | KDP 자동 수집 API 부재 — 수동 관찰값(verified, mirror_status) 저장 |
| KDP↔쇼츠 시너지(SY-1) | 별도 에픽(Should) |
| AI-assisted 구분(T-K2-06) | 파이프라인 생성물은 전부 AI-generated 판정 — assisted 구분은 수동 입력 시나리오 |

---

## 6. 실행·검증 방법

테스트:
  cd "/mnt/c/Users/wj941/OneDrive/바탕 화면/jproject/autostudio"
  rm -rf __pycache__   (또는 PYTHONDONTWRITEBYTECODE=1)
  ./.venv/Scripts/python.exe -m pytest tests/test_kdp_*.py -q   # 신규 53
  ./.venv/Scripts/python.exe -m pytest -q                        # 전체 464

서버 문법 (기동 없이): ./.venv/Scripts/python.exe -c "import server"
배치: ./.venv/Scripts/python.exe kdp_pipeline.py  # research→generate→assemble→출간→48h
대시보드: 배포 후 /static/index.html → "KDP 출간" 탭 (책 목록·출간큐 체크리스트·48h 확인·성과 입력)

---

## 7. 사용 스킬 로그

| 스킬 | 적용 지점 |
|---|---|
| test-driven-development | K-1~K-4 + QA 수정 전부 red→green→리팩터 |
| fable-prove-it | 통과 주장을 실제 pytest 출력(464/10)·import로 뒷받침, 미실행(calibre/epubcheck)은 보류 표기 |
| md-to-html | implementation-report.md → .html 병행 생성 |
| data-model·api | kdp_* 스키마·/kdp/* 라우트 설계 |
| wsl-windows-hybrid-runner | Windows venv pytest 실행, WSL↔Windows 네트워크 격리 |

---

*작성: 개발팀 · 상태: K-1~K-4 구현 완료 + 개발QA(H-1·M-1~M-4·K2-1) 반영 · 검증: 464 passed / 10 skipped*
