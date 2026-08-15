# autostudio — KDP 대시보드 디자인 시스템 (design-system.md)

> 작성: 디자인팀 · 프로젝트: autostudio · 작업 디렉토리: `pipeline/kdp-implementation/`
> 상위: `static/index.html`(기존 대시보드 — v18 탭·다크 네오-글래스 팔레트) · `pipeline/kdp-implementation/storyboard.md`(화면 정의)
> 원칙 ▶ **기존 index.html의 토큰·컴포넌트를 그대로 재사용하고 확장**한다. 신규 팔레트·신규 컴포넌트 스타일 도입 금지. 모든 신규 요소는 기존 CSS 변수/클래스를 조합해 정의한다.
> 상태: 디자인 산출물 2/2 · 적용 대상: KDP 탭(책 목록·출간 큐·48h 모니터링·성과 입력)

---

## 1. 토큰 요약 (static/index.html에서 추출)

### 1.1 색상 (CSS 변수 — `:root`)

| 카테고리 | 토큰 | 값 | 용도 (기존) | KDP 재사용 |
|---|---|---|---|---|
| 브랜드/기본 | `--primary` | `#6366f1` | 포커스 테두리·활성 탭 | 버튼 포커스·프라이머리 그라데이션 |
| | `--primary-dark` | `#4f46e5` | — | — |
| 액센트 | `--accent-blue` | `#38bdf8` | gauge 파란 그라데이션·배지 | assembling 배지·챕터 진행률 바 |
| | `--accent-mint` | `#34d399` | 성공 배지·태그 | ready/verified 배지·PASS |
| | `--accent-amber` | `#fbbf24` | 경고 배지 (재료) | 가격·미러 경고 |
| | `--accent-pink` | `#f472b6` | KPI 상단바 | (참조) |
| 상태 | `--success` | `#34d399` | `.ok` 텍스트·`b-green` | PASS·verified·완료 |
| | `--warning` | `#fbbf24` | `.warn-txt`·`b-warn`·`b-gold` | monitoring·pending 강조·WARN |
| | `--danger` | `#f87171` | `.no` 텍스트·`b-warn` 강조 | FAIL·차단 메시지 |
| 배경 | `--bg0` `#0b1120` · `--bg1` `#111a30` · `--bg2` `#1e1b4b` | | 페이지 배경 그라데이션 | (불변) |
| | `--card` `rgba(255,255,255,.055)` | | 카드 배경 | (불변) |
| | `--card-solid` `#151f36` | | 모달 패널 | 책 상세·체크리스트 모달 |
| 테두리 | `--border` `rgba(255,255,255,.09)` · `--border-strong` `rgba(255,255,255,.16)` | | 테이블·카드·활성 경계 | 48h 미검증 행 강조 |
| 텍스트 | `--text` `#e2e8f0` · `--muted` `#94a3b8` · `--dim` `#64748b` | | 본문·보조·약화 | (불변) |

> 베이스 텍스트-경계 대비는 기존 검증된 콘트라스트 유지. KDP 탭도 동일 토큰만 사용 → 접근성 일관성 보장.

### 1.2 폰트 / 간격 / 반경

| 항목 | 값 (기존) |
|---|---|
| 폰트 | `Pretendard Variable` → `Pretendard` → 시스템 폰트 (본문 14px, 표 셀 12.5px(`.mini-table`)/13px(`table`), 헤더 11px) |
| 기본 간격 | `padding: 12px 16px`(셀) · 카드 `16px` · `gap: 8px`/`14px`(그리드) |
| 반경 | 카드 `16px` · 탭/세그먼트 `12px`/`10px` · 버튼 `10px`/`8px` · 배지 `999px` · 게이지 `3px` |
| 그림자 | 카드 hover `0 12px 34px rgba(0,0,0,.35)` · 배지 `0 0 12px rgba(…)` |

**KDP 탭 신규 규칙**: 위 수치를 그대로 따른다 — 새 반경(20px 등)·새 그림자·새 폰트 도입 금지.

---

## 2. 재사용 컴포넌트 매핑 (KDP 탭이 사용하는 기존 클래스)

| 기존 컴포넌트 | 클래스 (index.html) | KDP 사용 위치 |
|---|---|---|
| 탭 네비게이션 | `.tabs` + `.tabs button.on` | 최상단 "KDP 출간" 탭 추가 |
| 하위 탭(세그먼트) | `.seg` + `.seg button.on` | 책 목록 / 출간 큐 / 48h / 성과 |
| KPI 카드 | `.kpis` + `.kpi`/`.kpi-label`/`.kpi-value(.warn)`/`.kpi-sub` | §1.2 4개 KPI |
| 카드/패널 | `.card`/`.panel-card`/`.panel-card h3(.dim)` | 각 화면 섹션 |
| 테이블 | `table`(스티키 헤더) / `.mini-table` | 책 목록·QC·월별 집계 |
| 진행률 게이지 | `.gauge` + `.g-blue`/`.g-green` | 챕터 진행률 바(§4-2) |
| 성과 바 | `.revenue-bar` | 월별 로열티 누적 |
| 버튼 | `.btn`/`.btn-primary`/`.btn-sm`/`.btn-gen`/`.btn-mini` | EPUB·출간·저장·액션 |
| 상태 텍스트 | `.ok`/`.no`/`.warn-txt`/`.rise`/`.dim` | QC 결과·게이트·경고 |
| 배지 | `.badge` + `b-gold`/`b-green`/`b-blue`/`b-warn`/`b-gray` | 책 상태·pending·verified |
| 모달 | `#detail .panel`(`.panel-head`/`.panel-body`) · `.x`(닫기 버튼) | 책 상세·체크리스트·48h 확인 |
| 진행 단계 | `.steps`/`.step(.active/.done)/.dot` | 출간 파이프라인 단계 |
| 상태 | `.skel`/`.empty`/`#status(.warn)`/`#detailError` | §6 스토리보드 상태 정의 |
| 스피너 | `.spinner` | 실행 중 표시 |
---

## 3. KDP 탭 신규 추가 컴포넌트 정의 (기존 패턴 조합)

> 4개 신규 컴포넌트(책 상태 배지·챕터 진행률 바·업로드 체크리스트·48h 모니터링 리스트)는 **전부 기존 토큰/클래스 조합**으로 정의한다. 스타일 신설이 아니라 "기존 배지/게이지/체크리스트·테이블 패턴을 KDP 의미에 매핑"하는 것.

### 3-1. 책 상태 배지 (KDP 신규 의미 매핑)

- **기반 클래스**: 기존 `.badge`(`border-radius:999px; font-size:11px; font-weight:700`) + 색 변형 5종 그대로 재사용.
- 신규 색을 만들지 않고, 기존 `b-gold/green/blue/warn/gray` 5종을 KDP status 5종에 매핑한다:

| KDP status | 배지 조합 | 예시 사용 |
|---|---|---|
| draft | `.badge.b-gray` | 생성 전(중립) |
| assembling | `.badge.b-blue` | 챕터 생성/QC 진행중 |
| ready | `.badge.b-green` | 검수 통과·출간 대기 |
| published | `.badge.b-gold` | 출간 완료 |
| monitoring | `.badge.b-warn` | 출간 후 48h 검증 대기(경고성) |

- **파생 접미사 배지** (같은 틀): `pending`(출간 큐 초과분) → `.b-gray`, `verified` → `.b-green`, `검증 대기` → `.b-warn`.
- 텍스트 색은 기존 배지의 밝은 톤(`#fcd34d`/`#6ee7b7`/`#7dd3fc`/`#fdba74`/`#cbd5e1`)을 그대로 따름.

### 3-2. 챕터 진행률 바 (KDP 신규 — 수치 병기)

- **기반**: 기존 `.gauge`(width 56px · height 6px · radius 3px) + `.g-blue`(파란 그라데이션)를 재사용.
- 확장 규칙: 진행률 바 옆에 `완료/전체` 숫자(`x/y`)를 `.num`(tabular-nums)으로 병기 → "챕터 6/10" 표기.
```
<span class="gauge g-blue"><i style="width:60%"></i></span><span class="num">6/10</span>
# i의 width = (완료 챕터수 ÷ 전체 챕터수) × 100% — 기존 render 패턴 그대로.
```
- `assembling` 진행 중 행은 `.g-blue`, ready+ 행은 `.g-green`으로 전환 가능(기존 취향 유지).

### 3-3. 업로드 체크리스트 (KDP 신규 — 기존 `.draft-block` + `.ok/.no/.warn-txt`)

- **기반**: 기존 게시 플래너의 "발행 절차 체크리스트"(`.draft-block`) 패턴과 `.ok`/`.no`/`.warn-txt` 텍스트 상태를 재사용.
- 항목(12-kdp §5): ① AI 생성 콘텐츠 공개 표기(QC#6) ② 가격 70% 구간 $2.99~$12.99 ③ 키워드 7개 ④ 카테고리 2개.
- 상태 표현: `완료 = .ok("✓")`, `부족 = .warn-txt`, `차단 = .no`. 완료 요약 `x/4`를 헤더에 병기.
- 저장/차단 동작은 storyboard.md §3.3 "게이트 차단" 규칙에 따른다.

### 3-4. 48h 모니터링 리스트 (KDP 신규 — 테이블 + 배지 + 경고 조합)

- **기반**: 기존 `table`(스티키 헤더)+`.mini-table` + `.badge.b-warn` + `.no`/`.warn-txt` + `.btn-sm` 조합.
- 컬럼: 제목 · 출간일 · 책 상태 · 가격 · 미러 · 48h 경과 · 확인 액션.
- 미검증 책 강조: 값 `status=published & verified_at=NULL` → 행 상단 정렬 + `.badge.b-warn`("검증 대기") + 행 테두리 강조(`inline style: border 1px solid var(--border-strong)` — index.html엔 `.border-strong` 클래스가 없고 CSS 변수만 존재).
- 가격/미러 이상: 해당 셀 `.no`(빨강)/`.warn-txt`(주황) + 우측 `[재확인 알림]`(`.btn-sm`). `[확인]` 클릭 → 다이얼로그 → `verified` 저장.
- 미러 확인값 저장(QA-D6): 48h 확인 다이얼로그에서 미러 상태를 `kdp_publish.mirror_status`(정상/이상) 필드에 저장 권장 — `verified`와 함께 기록해 이후 재확인·경고 추적의 근거로 삼는다 (12-kdp §3 `kdp_publish`에 mirror_status 필드 신규 추가 제안).
- **측정 경로 노출(AC-DB-1②)**: 성과 탭 입력 폼 옆에 `수동 — Amazon KDP 리포트` 라벨 고정 표시. API/Studio 옵션은 input 비활성(`.btn:disabled` 취급)으로 둠 — "채널 비소유 시 입력 비활성" 기존 규칙과 정합.

---

## 4. 접근성 (a11y) · 모션 정합

- 기존 `prefers-reduced-motion: reduce` 블록(오로라·KPI·스켈레톤 애니메이션 off)은 KDP 신규 요소에도 동일 적용. 신규 애니메이션 불필요.
- 모든 인터랙션 버튼/탭에 기존처럼 `aria-label` 부여(기존 탭·세그먼트 패턴).
- 색상 대비는 기존 토큰만 사용하므로 신규 대비 위험 없음. 배지 색만으로 판단하지 않도록 배지 **라벨 텍스트와 함께** 표기(색만으론 구분 불가).

---

## 5. 스킬 사용 로그 (이번 산출물에 적용된 스킬/지식)

| 스킬/참고 | 적용 지점 |
|---|---|
| `design-system` | 3계층 토큰(primitive→semantic→component) 관점에서 KDP 신규 컴포넌트가 "기존 primitive 토큰 조합"임을 명시 — 신규 팔레트 금지 원칙의 근거 (§3) |
| `design-auditor` | 색상 대비·일관성·시각 계층 점검 — 기존 토큰만 재사용해 대비 위험 제거(§4), 상태 색을 배지 라벨 텍스트와 병기 |
| 기존 대시보드 패턴 분석 | index.html v18 탭/seg/badge/gauge/modal/skel/empty 패턴을 inventory화(§2)해 KDP 탭이 이를 조합(§3) |
| `work-pipeline` | 디자인팀 산출 절차 준수 — 입력 문서(plan/userflow/12-kdp) 전부 읽고 AC 매핑 후 스토리보드·DS 각 1회 산출 |

---

*작성: 디자인팀 · 상태: 디자인 산출물 2/2 · 상위: index.html + storyboard.md · 인계: 디자인QA팀 → 개발팀(K-4 대시보드)*