# VERIFICATION — 전체 알고리즘 감사 (5개 영역 통합)

> 검증일: 2026-08-11 (2차) · 방법: fable-method + code-review(병렬 분할) + fable-judge(적대적 재검증) + verifier(보고서)
> 범위: ① 발굴·정제·수집 ② 점수·임계·은퇴·DB ③ 초안·검수·이미지·플랫폼·배치 ④ 수익·발행·AdPost ⑤ 운세 엔진
> 자동 검증: pytest 358 passed / 10 skipped · 수동 시나리오: SQLite 실데이터 4종 + revenue 12종
> 1차 감사(키워드 전용) 결과는 본 문서에 병합 — 상세는 scratch/audit/INTEGRATED.md

## 종합 판정

**VERIFIED WITH CAVEATS** — blocker/major 없음. minor 16건 (실제 버그 2: B-1, R-1 / 문서 드리프트·개선 14건).

## 발견 요약 (우선순위)

| ID | 영역 | 심각도 | 발견 |
|---|---|---|---|
| R-1 | 수익 | minor | adpost CSV 열 부분문자열 매칭 — '클릭률' 열이 '클릭' 앞이면 clicks/impressions 오선택 (실측: clicks=3.5, impressions=0) |
| B-1 | 키워드 | minor | upcoming 프리셋 P50=0 폴백 우회 → 프리셋 필터 무력화 (전체 노출) |
| E-1 | 엔진 | minor | 운세 qc_failed 콘텐츠 영구 재시도 불가 (문서 '재생성 지시' 미구현) |
| E-2 | 엔진 | minor | weekly/monthly/고정 콘텐츠 grounding에 daily 그라운딩 저장 (메타데이터 오염) |
| D-1 | 초안 | minor | 재생성 피드백 4개 항목만 — body_length 등 무피드백 맹재시도 |
| D-2 | 초안 | minor | 네이버 structure 검수 정확 일치 요구 — 변형 시 반복 실패 |
| R-2 | 수익 | minor | URL 정규화 비대칭 → AdPost 매칭 실패 |
| R-3 | 수익 | minor | /adpost/import 제목 매칭 status 가드 없음 |
| R-4 | 수익 | minor | revenue_insights totals/monthly 필터 불일치 |
| R-5 | 수익 | minor | /refresh 게시·성과 가드 미약 |
| R-6 | 수익 | minor | 리프레시 boost 원본·신규 양쪽 +10 (분배 의도 확인 필요) |
| B-2 | 키워드 | minor | 문서 드리프트 4건 (README·스펙 stale) |
| B-3 | 키워드 | minor | PRIORITY_SQL vs v6_priority 정합 깨짐 (실측 -6.2) + 정합 테스트 실측 경로 미커버 |
| B-4 | 키워드 | minor | CPC 이중 절충 — 실측 신호 25%뿐 (표본 3건) |
| C-1 | 발굴 | nit | '작업 대출'(띄어쓰기) 우회 |
| E-4/E-5 | 엔진 | nit | 항진 단언(`is None or True`)·기대값 없는 ganji 테스트 — 약화된 테스트 |

## 영역별 상세

### ① 발굴·정제·수집 — ✅ 견고 (nit 1)
BFS 예산/연속실패 차단/팬아웃 차단(v14 exclude), refine 규칙(블랙리스트/길이/노이즈/브랜드),
discover 가드(상한·카테고리 비중 v21·시드 자동초기화) 모두 주장과 일치.
[C-1] '작업 대출' 띄어쓰기 우회 (v20 '대출' 토큰 제거와 상충) — nit.

### ② 점수·임계·은퇴·DB — ✅ 핵심 견고 (minor 3)
은퇴 가드(COUNT≥3, boost, NULL, clickless) 시나리오 실측 PASS. 백분위 half-up 오프셋 테스트 양호.
[B-1] upcoming P50=0 → opportunity_min=0.0 (폴백 20.0 우회) · [B-2] 문서 4건 · [B-3] 정합 테스트 구멍.

### ③ 초안·검수·이미지·플랫폼·배치 — ✅ 견고 (minor 2, nit 2)
2패스·하드 예산 55초·pass2 30초 예약·facts/comparisons 그라운딩·플랫폼 단일 소스·배치 격리 모두 정상.
[D-1] 재생성 피드백 불완전 · [D-2] 네이버 소제목 정확 일치.

### ④ 수익·발행·AdPost — ⚠️ 발견 밀집 (minor 6)
시나리오 12/12로 실측 확정. [R-1] CSV 열 오선택이 실사용 피해 최대 후보.

### ⑤ 운세 엔진 — ✅ 데이터 생성 견고 (minor 2, nit 4)
만세력/일진/고정 콘텐츠 규칙 생성 정상. [E-1] QC 실패 재시도 부재 · [E-2] grounding 오염 ·
[E-4/E-5] 약화된 테스트 2건.

## 검증 기록
- pytest 전체: 358 passed, 10 skipped (0 errors)
- 키워드 시나리오: [A] 실측 CPC 드리프트 -6.2 / [C] P50=0 폴백 우회 / [D] 은퇴 가드 PASS
- revenue 시나리오: 12/12 PASS (S1 이중희석·S2 CSV 오선택·S3 URL 비대칭·S5 boost·S7 필터 불일치·S8 refresh 가드·S10 음수 cpc)


## 4. 수정 내역 (2026-08-11, 14개 커밋)

| ID | 수정 | 커밋 |
|---|---|---|
| R-1 | adpost CSV 열 정확 일치 우선 + 률/율 제외 | 2b84a83 |
| B-1 | upcoming 프리셋 P50=0 폴백 | 50792d9 |
| E-1 | 운세 qc_failed 재생성 허용 | ef85259 |
| E-2 | weekly/monthly/고정 grounding 정합 | 01aac75 |
| D-1 | 재생성 피드백 본문·첫문단 실측 주입 | 9d2908b |
| D-2 | 네이버 소제목 부분 일치 | 205d286 |
| R-2 | published_url trailing slash 정규화 | 08450fb |
| R-3 | AdPost 제목 매칭 게시 상태 가드 | 255278d |
| R-4 | 수익 인사이트 집계 기준 통일 | 455cef5 |
| B-4 | CPC 이중 절충 제거 (순수 실측 + 베이지안 단일) | 6723098, de63dfd |
| C-1 | '작업 대출' 띄어쓰기 차단 | d2ba514 |
| E-4/E-5 | 항진 단언 제거·기대값 고정 | e7d0105 |
| E-3/N-1~3 | 사어 코드·stale 주석 정리 | 4f66382 |
| R-5 | 리프레시 게이트 (게시 14일+·성과<50) | c3298d9 |
| B-3 | 정합 테스트 실측 CPC 경로 추가 | 83c8498 |
| B-2 | README 문서 드리프트 갱신 | 0e57f4f |

**최종 검증: pytest 369 passed / 10 skipped / 0 errors** (기존 358 + 신규 11)
**R-6 결론**: 리프레시 boost는 '분배'가 아닌 키워드 단위 공유 설계 (mark_draft_refreshed는 boost 미변경) — 버그 아님, 의도된 구조로 판정.


## 5. 프롬프트 개선 (2026-08-11, 리서치 기반 — docs/RESEARCH.md)

| ID | 개선 | 결과 |
|---|---|---|
| P1-1 | SYSTEM_PROMPT: '실제 경험 기반' → 검증 가능 정보 + 경험·출처·통계 창작 금지 + AI 브리핑 인용 구조 | ✅ 커밋 886325b |
| P1-2 | 허위 출처('조사·연구·통계에 따르면') 검수 + 재생성 피드백 (FAKE_SOURCE_PATTERNS 11종) | ✅ 커밋 9add933 |
| P2-1 | pass1/pass2 AI 브리핑·AI 탭 인용 구조 지시 | ✅ 커밋 faa9411 |
| P2-2 | 정보형 템플릿 non-commodity (일반 상식 나열 금지·구체적 기준/숫자/비교/함정) | ✅ 커밋 faa9411 |
| P3 | 제목 지시: 연도·정보성·핵심 요약('N가지 방법') | ✅ 커밋 faa9411 |

**검증**: pytest 377 passed / 10 skipped (기존 358 + 신규 19) · 프로덕션 스모크:
POST /drafts 200 (43초) — 제목 '2026 다이어트방법 총정리, 요요 없이 빼는 5가지 핵심'(연도+요약 반영),
허위 경험·출처 표현 0건, FAQ 포함, 플레인 텍스트 정상.
**배포**: vercel --prod 수동 (GitHub 연동 없음 — 프로젝트 link null).


## 6. 기획 문서 갱신 (2026-08-11)

| 문서 | 갱신 내용 |
|---|---|
| README.md | 배포 체크리스트 — GitHub 연동 없음(수동 배포 필수) + 배포 절차 + LLM 쿼터 주의 |
| CHANGELOG.md | 신규 — v10~v24 버전 이력 |
| 11-fortune-channel.md | v23/v24 반영 (opencode-go 전환·프롬프트 개선), 도메인 현황 (space-daily.com = spacecl) |
| 06-tasks.md | v1 태스크 아카이브 처리 (구현 완료 스탬프) |

**해소 (v26, 2026-08-13)**: 이미지 프로바이더 폴백/쿼터 모니터링 알림 — `pipeline/image-fallback/requirements.md` 기획
및 구현 완료 (proposal-13 권장안 A+B 소형 패키지, TDD 테스트 9건, pytest 386 passed).
- 폴백: Bailian 실패 → DashScope `wanx2.1-t2i-turbo` 1회 재시도 (비동기 task 생성+폴링 — 동기 미지원 실측 반영)
- 알림: 연속 5건 또는 시도 5건+ 실패율 50% 초과 → ERROR 로그 + `collect.py` `image_alert` `exit 1` → GH Actions 잡 실패 전파
- 구현 상세: `pipeline/image-fallback/implementation-report.md` · `docs/planning/02-trd.md` · CHANGELOG v26
