# 디자인 QA 보고서 — KDP 대시보드 탭 (design-qa-report.md)

> **작성**: 디자인QA팀 · **프로젝트**: autostudio · **작업 디렉토리**: pipeline/kdp-implementation/
> 작성일: 2026-08-14
> **검증 대상**: storyboard.md · design-system.md (디자인팀 산출)
> **대조 원본**: plan.md(F-4·F-7, AC-K4-1·AC-K4-2·AC-DB-1) · userflow.md(여정 2·3) · docs/planning/12-kdp-pipeline.md(§3·4·5·6) · static/index.html(실존 클래스·토큰) · planning-qa-report.md
> **검증 방법**: design-qa(토큰/컨트라스트/hardcode·a11y 게이트 프레임) + design-review(Nielsen) + a11y-audit 관점 + **index.html 실존 클래스/토큰을 grep으로 실측 대조(추측 금지)** + 12-kdp §3 데이터 모델 대조(개발 가능성)

---

## 최종 판정: ⚠️ **조건부 승인 (Conditional Approval)**

> 판정 근거 요약: 검증 항목 6개 중 **4개 완전 PASS + 2개 조건부 PASS**. 차단(반려)급 결함 0건이나, design-system이 스스로 세운 '기존 실존 클래스만 참조' 원칙을 위반한 **🟠 QA-D1**(border-strong을 클래스로 오인)과, AC-DB-1 구현에 필요한 성과/QC **데이터 모델 공백** **🟠 QA-D3**이 확인됨. 2건 모두 30분 내외 소규모 수정이며 해소 시 승인 전환.

---

## 검증 항목별 결과 요약

| # | 검증 항목 | 결과 | 핵심 근거 |
|---|---|---|---|
| 1 | 기획 정합성 (plan F-4·F-7, 12-kdp §5·6) | ✅ **PASS** | 일3권 게이트·48h 모니터링·수동 입력·손익분기 수치 전부 plan/12-kdp와 일치(재계산 검증) |
| 2 | AC 매핑 완전성 (AC-K4-1·K4-2·DB-1) | ✅ **PASS** | 3개 AC 전부 §3/§4/§5+§6 매핑, 엣지케이스 전부 반영, KDP 범위 내 누락 0 |
| 3 | 스토리보드 품질 (와이어프레임·상태·예외) | ✅ **PASS** | 4개 화면 와이어프레임 + §6 공통 상태(빈/로딩/오류/게이트/48h) + 여정 2·3 예외 반영 |
| 4 | 디자인 시스템 정합 (실존 클래스만 참조?) | ⚠️ **조건부 PASS** | 대부분 재사용(실측)이나 🟠 border-strong 클래스 오인 + 🟡 #x/13px·12.5px 오기재 |
| 5 | 접근성 (대비·라벨 병기·aria·reduced-motion) | ✅ **PASS** | 기존 토큰만 사용, 배지 라벨 병기·aria-label·reduced-motion 명시 명확 |
| 6 | 개발 가능성 (12-kdp §3 데이터 모델 대조) | ⚠️ **조건부 PASS** | 대부분 매핑되나 🟠 성과/QC 저장 테이블·미러 필드 부재 |

**발견 문제 총 6건**: 🟠 중대 2 · 🟡 정보 4 · 🔴 차단 0

---

## 1. 기획 정합성 — ✅ PASS

### 1.1 일 3권 게이트 (plan AC-K4-1 · 12-kdp §5)
- 스토리보드 §3.1 '오늘 예약: 2/3권' + 3권 도달 시 추가 선택 불가 + 초과분 pending('내일 자동 허용') — plan AC-K4-1① 엣지 '3권 초과: 다음날 자동 허용'과 정확히 일치 ✅
- 12-kdp §5 '일 3권 통일(둘 다 실존)'과 정합, ready 책 priority 내림차순 처리 반영 ✅

### 1.2 48h 모니터링 (plan AC-K4-2 · 12-kdp §3·§6)
- §4 미검증(verified_at=null) 상단 정렬 + b-warn 배지 + 48h 경과 시 #status.warn/[재확인 알림] — AC-K4-2①(리스트 표시)·②(verified 저장)·③(가격·미러 경고) 전부 반영 ✅
- §4.2 'kdp_publish.status→verified + verified_at 기록'은 12-kdp §3 kdp_publish 모델과 정합 ✅

### 1.3 성과 입력 수동 원칙 (plan F-7 · AC-DB-1)
- §5.1 '측정 경로: 수동 — Amazon KDP 리포트' + API/Studio 옵션 input 비활성 — plan F-7 '수동 입력 원칙·측정 경로 구분(S-2)'과 일치. KDP 자동 수집 API 부재 명시 ✅

### 1.4 손익분기 수치 (plan §2.2 · 12-kdp §1.2) — 재계산 검증
| 가격 | 로열티/권(보드) | 재계산 | $100=권수(보드) | 재계산 | 판정 |
|---|---|---|---|---|---|
| $2.99 | $2.03 | 2.99×0.70−0.06=2.03 ✅ | 49 | 100/2.03=49 | ✅ |
| $4.99 | $3.43 | 4.99×0.70−0.06=3.43 ✅ | 29 | 100/3.43=29 | ✅ |
| $9.99 | $6.93 | 9.99×0.70−0.06=6.93 ✅ | 14 | 100/6.93=14 | ✅ |
| $12.99 | $9.03 | 12.99×0.70−0.06=9.03 ✅ | 11 | 100/9.03=11 | ✅ |
> 모든 수치가 plan/12-kdp·planning-qa(§6 계산 재검증)와 완전 일치. NFR-3 수치 정합 유지 ✅

---

## 2. AC 매핑 완전성 — ✅ PASS

### 2.1 필수 AC 3개 매핑 (스토리보드 §1.3 실증)
| AC | 구성 요소 | 매핑 (스토리보드 §/요소) | 판정 |
|---|---|---|---|
| AC-K4-1 | ① 일 3권 게이트 | §3.1 오늘 예약 2/3·초과분 pending | ✅ |
| | ② 업로드 체크리스트 | §3.2 체크리스트 모달(AI표기·가격·키워드7·카테고리2) | ✅ |
| | ③ 수동 업로드 후 전이 | §3.1 출간 시작→§3.2→published | ✅ |
| | 엣지 '체크 미완료 차단' | §3.3 차단 배너 + btn:disabled | ✅ |
| AC-K4-2 | ① 미검증 리스트 | §4.1 상단 정렬 + b-warn | ✅ |
| | ② verified 저장 | §4.2 status→verified + verified_at | ✅ |
| | ③ 가격·미러 경고 | §4.1 no/warn-txt + 재확인 알림 | ✅ |
| AC-DB-1 | ① 성과 입력 폼 | §5.1 수동 입력 폼 | ✅ |
| | ② 측정 경로 표시 | §5.1 수동 라벨·API/Studio 비활성 | ✅ |
| | ③ 손익분기표 | §5.1 손익분기표(정보성) | ✅ |
| | ④ 월별 집계 | §5.1 월×책 그리드 + revenue-bar 합계 | ✅ |

### 2.2 보조 흐름 매핑 (KDP 범위 내)
- 책 목록 상태 추적(K-2)·EPUB 다운로드(K-3)·QC 8항목·책 상세 모달 → §2 전부 매핑 ✅
- **결론**: plan AC 17개 중 KDP 탭 직접 대상 AC(K4-1/K4-2/DB-1) 누락 없이 완전 매핑. KDP 범위 외(쇼츠/시너지/운세)는 의도대로 제외(§1 '쇼츠 탭 제외') — 범위 적절 ✅

---

## 3. 스토리보드 품질 — ✅ PASS

- **와이어프레임 명확성**: 화면 A(책 목록)·B(출간 큐)·C(48h)·D(성과) 4개 전부 ASCII 와이어프레임 + 클래스·상태·동작 주석. 구현자가 요소/클래스/데이터 시각화 매핑 가능 ✅
- **상태 정의 완비 (§6)**: 빈 상태(6종)·로딩(skel·spinner·steps)·오류(API 401/리스트/상세/EPUB/작업)·게이트 차단(§6.4)·48h 미확인(§6.5) — 기존 index.html 상태 패턴 재사용 ✅
- **여정 2·3 예외 반영**: 검색 0건(§6.1)·예산 초과(§2.2 pending 챕터)·QC 실패(§2.2 no)·체크 미완료(§3.3)·48h 미확인(§4.1) 전부 반영 ✅
- **Nielsen 휴리스틱**: 상태 가시성(#status.warn/KPI warn)·사용자 통제·자유(취소/뒤로)·오류 예방(게이트 비활성)·일관성(기존 패턴) 양호 ✅

### 발견 (🟡)
| ID | 문제 | 심각도 |
|---|---|---|
| QA-D2 | 예시 수치 화면 간 불일치: §1.2 KPI 'KDP 책 6권·ready 4권·48h 미검증 1권' vs §2.1 책목록(4행, ready 1권) vs §4.1 모니터링(2행 모두 2h/26h=48h 미경과). 와이어프레임이라 차단 아님, 개발 스켈레톤 정합 위해 통일 권고 | 🟡 정보 |

---

## 4. 디자인 시스템 정합 — ⚠️ 조건부 PASS

### 4.1 실존 클래스 대조 (index.html grep 실측) — 대부분 PASS
| 참조 | index.html | 판정 |
|---|---|---|
| .tabs + button.on | L144·L151 | ✅ |
| .tabpane(+.on) · tabKeywords/Planner | L153-154 | ✅ |
| .seg + button.on | L178·L184 | ✅ |
| .card / .panel-card(+h3 .dim) | L71 / L155 | ✅ |
| .kpis .kpi .kpi-label .kpi-value(.warn) .kpi-sub | L50-68 | ✅ |
| .badge + b-gold/green/blue/warn/gray | L216-226 | ✅ (색 정확) |
| .gauge + g-blue/g-green + .num | L205-209·L204 | ✅ (56·6·3px) |
| .revenue-bar | L174 | ✅ |
| .mini-table | L170 | ✅ |
| .btn .btn-primary .btn-sm .btn-gen .btn-mini .btn:disabled | L136-141·L138 | ✅ |
| .ok .no .warn-txt .rise .dim | L164-166·L210-211 | ✅ |
| #detail .panel(-head/-body) #detailError | L247-258 | ✅ |
| .steps/.step(.active/.done)/.dot | L290-299 | ✅ |
| .skel .empty #status(.warn) .spinner | L229·L232·L75-76·L281 | ✅ |
| prefers-reduced-motion: reduce 블록 | L304-307 | ✅ |
| CSS 토큰 (--primary #6366f1·--accent-blue #38bdf8·--success #34d399·--warning #fbbf24·--danger #f87171·--bg0/1/2·--card·--card-solid #151f36·--border(.strong)·--text/muted/dim) | :root L12-18 | ✅ 전부 정확 |
| 배지 텍스트 색 (#fcd34d/#6ee7b7/#7dd3fc/#fdba74/#cbd5e1) | L218-226 | ✅ 정확 |

> 신규 컴포넌트 4종(책 상태 배지·챕터 진행률 바·업로드 체크리스트·48h 모니터링 리스트)은 design-system §3에서 전부 기존 배지/게이지/draft-block·테이블 조합으로 정의 — **신규 팔레트·스타일 도입 없음** ✅

### 4.2 원칙 위반 지점 (참조 클래스가 실존하지 않음)
| ID | 문제 | index.html 실측 | 심각도 |
|---|---|---|---|
| QA-D1 | **border-strong을 클래스로 오인 참조**: design-system §3-4 '행에 border-strong 클래스 추가' + storyboard §4.1·§6.5 '행 테두리(border-strong)'. index.html에서 border-strong은 **CSS 변수 --border-strong(=rgba(255,255,255,.16))뿐, .border-strong 클래스는 부재**(L17 변수 1개, L61/L136은 var(--border-strong) 사용). 개발팀이 없는 클래스를 만들면 '신규 스타일 도입' 원칙 위반 | grep: 변수만 1개, 클래스 선언 0 | 🟠 **중대** |
| QA-D4 | design-system §2 '모달 닫기 #x' — index.html 닫기 버튼은 **.x 클래스**(L518·L531). #x(id) 부재 | .x 클래스 2건 | 🟡 정보 |
| QA-D5 | design-system §1.2 '표 13px' — 실제 .mini-table td 12.5px(L171), 헤더 11px | L171 12.5px | 🟡 정보 |

---

## 5. 접근성 — ✅ PASS

- **색 대비**: design-system §4 '기존 토큰만 사용→신규 대비 위험 없음' + §3 배지 라벨 텍스트 병기(색 단독 판단 금지). 색맹 배려 충족 ✅
- **배지 색 단독 사용 금지**: §2.1 상태 배지·§3-1 접미사 배지 전부 라벨 포함, title/aria 활용 — WCAG 2.2 1.4.1 충족 ✅
- **aria-label**: design-system §4 '모든 인터랙션 버튼/탭에 aria-label'. 기존 index.html이 tabs/seg에 role=tablist/aria-label/role=group 사용(실측 L404·L384) → 동일 규칙 신규 탭 적용 명시 ✅
- **reduced-motion**: 기존 @media prefers-reduced-motion 블록(L304)이 aurora·kpi-value·skel off → 신규 .spinner·KPI 워너도 동일 블록 포함(명시). 신규 애니메이션 불필요 선언 ✅
- **대비 수치**: #status.warn(danger #f87171)·배지 밝은 텍스트(#fcd34d 등) 모두 기존 검증 토큰·다크 배경 이슈 없음. raw hex 하드코드 0(design-qa 게이트 통과 예상) ✅
- 참고: 48h/게이트 강조가 색+라벨+테두리 3중 수단으로 전달되나, 🟠 QA-D1(border-strong 클래스 부재) 해소 시 테두리 강조가 실제 구현 가능 — **QA-D1과 연계** 🟡

---

## 6. 개발 가능성 — ⚠️ 조건부 PASS (AC-DB-1 데이터 모델 공백)

### 6.1 UI 요소 ↔ 12-kdp §3 데이터 모델 필드 매핑
| 스토리보드 UI 요소 | 필요 필드 | 12-kdp §3 모델 | 판정 |
|---|---|---|---|
| 책 목록 제목·카테고리·상태·생성일 | title/category/status/created_at | kdp_books | ✅ |
| 챕터 진행률(6/10) | kdp_chapters 건수 유도 | kdp_chapters | ✅ |
| 챕터 테이블 제목·상태·단어수 | title/status/word_count | kdp_chapters | ✅ |
| 출간 큐 가격 | price | kdp_publish | ✅ |
| 출간 체크리스트 가격·키워드7·카테고리2 | price·keywords·category | kdp_publish + kdp_books | ✅ |
| 48h 출간일·verified | publish_date/status/verified_at | kdp_publish | ✅ |
| 책 상세 QC 8항목 결과 | QC 결과 저장 | ❌ 부재 | 🟠 |
| 성과 입력 판매수·로열티·월·측정경로 | 성과(판매/로열티) 데이터 | ❌ 부재 | 🟠 |
| 48h 미러 확인 결과 | 미러 상태 | ❌ 부재 | 🟡 |
| EPUB 다운로드 | EPUB 파일 경로 | ❌ 파일 컬럼 부재(서버 산출 가능) | 🟡 |

### 6.2 지적 (개발팀 인계 전 보완)
| ID | 문제 | 근거 | 심각도 |
|---|---|---|---|
| QA-D3 | **AC-DB-1 구현용 성과 데이터 테이블 부재**: 12-kdp §3에 kdp_books/chapters/covers/publish만 있고 판매·로열티·월별집계·측정경로 저장 테이블이 없음(§2 단계 10 '성과 추적' 언급만). 개발팀이 §5 성과 입력 구현하려면 kdp_performance(book_id·year_month·sales·royalty·measure_path) 정의가 우선 필요. QC 8항목 결과 저장 테이블도 부재 | 12-kdp §3 대조 | 🟠 **중대** |
| QA-D6 | 미러(§4.1 컬럼)·가격 상세는 사용자 수동 확인값 — 저장/미저장 결정 미명시. 미러는 수동 관찰값이면 체크박스로 충분, 스토리보드에 명시 권고 | — | 🟡 정보 |

> 요약: 책 목록/출간 큐/48h의 상태·날짜·가격 필드는 전부 12-kdp §3에 존재해 개발 가능. 문제는 AC-DB-1(성과)과 QC 결과로, 해당 UI가 데이터 모델 너머의 신규 테이블을 필요로 함 — 디자인 결함이 아니라 **기획 데이터 모델 공백**을 디자인이 드러낸 것. K-4에서 §3 확장으로 해소.

---

## 발견 문제 종합 (심각도)

| ID | 문제 | 심각도 | 수정 요구사항 |
|---|---|---|---|
| QA-D1 | border-strong을 클래스로 참조 — index.html엔 --border-strong **변수**만 있음 | 🟠 중대 | 'border-strong 클래스' 표기를 제거하고 기존 패턴(var(--border-strong) 인라인/기존 테두리 강조)으로 명시. 신규 클래스 도입 금지 원칙 준수(design-system §3-4·storyboard §4.1·§6.5) |
| QA-D3 | AC-DB-1 성과(판매·로열티·월별집계·측정경로) + QC 결과 저장 데이터 모델 부재 | 🟠 중대 | 개발팀 K-4 전 12-kdp §3에 kdp_performance·QC 결과 테이블 정의 추가. 스토리보드 §5·§2.2에 '신규 테이블 필요' 주석 |
| QA-D2 | 예시 수치 화면 간 불일치 (KPI 6/4권 vs 책목록 4행, 48h 미검증 1권 vs 모니터링 2행) | 🟡 정보 | 와이어프레임 예시 수치 통일 |
| QA-D4 | design-system §2 모달 닫기 #x → 실존 .x 클래스 | 🟡 정보 | #x→.x 로 수정 |
| QA-D5 | design-system §1.2 '표 13px' → 실제 12.5px | 🟡 정보 | 12.5px로 정정 |
| QA-D6 | 미러 수동 확인값 저장 여부 미명시 | 🟡 정보 | §4.1 미러 컬럼의 수동 확인 주석 |

**심각도 기준**: 🔴 차단(반려) / 🟠 중대(조건부) / 🟡 정보. 🔴 0건. 🟠 2건(QA-D1·D3) — 수정 용이(30분 내외).

---

## 수정 요구사항 (조건부 승인 충족 조건)

1. **[🟠 QA-D1] 필수**: border-strong 클래스 참조 제거, 기존 var(--border-strong) 기반 테두리 강조로 명시 — design-system.md §3-4·storyboard.md §4.1·§6.5 수정.
2. **[🟠 QA-D3] 필수**: 12-kdp §3에 kdp_performance(판매·로열티·월별집계·측정경로)+QC 결과 저장 테이블 추가(스토리보드 §5·§2.2 주석). 데이터 모델 개정은 기획/개발 경유가 자연스러우므로, 디자인QA는 '필요 테이블 부재'를 명확히 전달 → 개발팀 K-4에서 해소 병행.
3. **[🟡 QA-D2/D4/D5/D6] 권장**: 예시 수치 통일·.x·12.5px·미러 주석 정리(30분 이내, 차단 사유 아님).

> QA-D3은 요구사항/기획QA에서 미확인된 **데이터 모델 공백**으로 이번 디자인QA가 최초 검출 — 개발팀에 반드시 전달.

---

## 검증 제한 (미검증 항목)

| 항목 | 사유 | 상태 |
|---|---|---|
| 실제 색상 대비 렌더 측정(headless Chromium) | 실행 환경 미준비 — 정적 대조만 수행. 기존 토큰 재사용으로 위험 낮음 | 🟡 정적 대조 대체 |
| 신규 탭 추가 시 기존 JS 이벤트(tablist/switchTab) 충돌 | 개발팀 K-4 구현 단계 검증 대상 | 미검증 |

---

## 부록: 사용 스킬 로그

| 스킬/도구 | 적용 지점 |
|---|---|
| **design-qa** | 토큰/컨트라스트/hardcode/자동 a11y 게이트 프레임 — index.html 실존 클래스·토큰 대조 기준, 신규 raw hex/px 여부 점검 |
| **design-review (Nielsen)** | §3 스토리보드 UX 휴리스틱(상태 가시성·통제·오류예방·일관성) |
| **a11y-audit** | §5 색 대비·배지 라벨 병기(1.4.1)·aria-label·reduced-motion 규칙 |
| **work-pipeline** | 디자인QA 게이트 절차·한국어 산출물 규칙·스킬 로그 요구 준수 |
| **직접 실측 (grep/read, index.html)** | 참조된 전체 클래스·토큰을 index.html에서 grep 실측 — .border-strong 클래스 부재, .x 클래스, 12.5px 발견, 토큰 값 정확성 확인(추측 배제) |
| **12-kdp §3 데이터 모델 대조** | 개발 가능성 — UI 필드↔kdp_books/chapters/publish 매핑, 성과/QC/미러 테이블 공백 검출 |
| **md-to-html** | 본 보고서 .html 병행 생성(design-qa-report.html) |

---

## 최종 판정: ⚠️ 조건부 승인

**승인 사유**: 기획 정합성·AC 매핑 완전성·스토리보드 품질·접근성 4개 완전 PASS, 실존 클래스/토큰 재사용 및 신규 컴포넌트 4종의 조합 정의도 충실. 기획QA 승인 조건(QA-01~04)과 충돌 없음.

**조건부 사유**: 🟠 QA-D1(border-strong 클래스 오인)과 🟠 QA-D3(성과/QC 저장 데이터 모델 공백) 2건이 개발팀 인계 전 해소 또는 명시되어야 구현 혼선이 없다. 둘 다 30분 내외 소규모 수정.

**개발팀 인계 시 참고**: 스토리보드·design-system은 그대로 구현 가능 수준. QA-D3의 kdp_performance/QC 테이블 확장을 K-4 첫 단계로 수행. 미검증 항목은 실측 대비 게이트(headless Chromium)뿐 — 신규 하드코드 색/px 없음이 확인되어 위험 낮음.

---

*작성: 디자인QA팀 · 상태: 검증 완료 · 판정: ⚠️ 조건부 승인 (QA-D1·D3 필수, D2·D4·D5·D6 권장) · 인계: 디자인팀(수정) → 개발팀(K-4 대시보드)*