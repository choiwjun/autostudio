# 키워드 대시보드 알고리즘·UI/UX 분석 (2026-08-11)

> 대상: static/index.html 키워드 목록 탭 + server.py list_keywords + db.py query_keywords
> 실측: 프로덕션(autostudio-eight.vercel.app) API 실제 호출

## 1. 알고리즘 — 프리셋·임계·정렬 (실측)

| 프리셋 | 결과 (활성 206건 기준) | 동작 |
|---|---|---|
| 전체 | 206건 | 필터 없음 |
| **ai_pick (기본)** | **39건** | ai_cite ≥ P50(0.215) & demand ≥ P50(0.0023) |
| promising | 29건 | opportunity ≥ P75(4.2) & demand ≥ P50 |
| rising | 17건 | demand_growth ≥ 0.1 & demand ≥ P50 |
| upcoming | 11건 | growth>0 & demand<P50 & opportunity≥P50 |

- **백분위 자가보정 정상**: thresholds = {ai_cite: 0.215, demand: 0.0023, opportunity: 4.2} (percentile 소스) ✅
- **배지 = 서버 임계 단일 소스** (AI유망/유망/애포/수요낮음/보류 — recommend()가 thresholds 사용) ✅
- **정렬 NULL 처리 정상**: NULL은 항상 뒤로 (CASE WHEN IS NULL THEN 1) ✅
- **페이지네이션**: 50건/페이지, `206건 · 1/5페이지` 표시 ✅

## 2. UX 이슈 (우선순위)

### 🔴 UX-1: 첫 화면이 ai_pick이라 39/206건만 보임
- 초기 `preset = 'ai_pick'` — 대시보드 첫 로드가 **전체의 19%만 표시**
- "쇼핑클릭 전체에서만 많은 키워드가 나온다"는 인식의 원인: **"전체" 프리셋 버튼을 누르면 206건**, 기본/리셋은 39건
- 의도(v6 "추천 우선")는 이해되나 신규 사용자 혼란 큼
- 제안: ① 첫 방문 시 "AI픽 = AI인용·수요 상위 50% 키워드 (39건)" 안내 배너 ② 또는 기본 preset='' (전체)

### 🔴 UX-2: "필터 초기화"가 전체가 아닌 AI픽으로 복귀
- `resetFilters()`가 `preset = 'ai_pick'` 설정 — 사용자 기대("전체 보기")와 다름
- 제안: resetFilters는 `preset = ''`(전체)로, 또는 버튼 라벨 "기본 보기(추천)"로 명확화

### 🔴 UX-3: 쇼핑클릭 필터 무의미 (2건)
- 옵션 0.001+/0.01+ 모두 **동일 결과 2건** (여름 휴가 계열) — 클릭 수집이 2/39건이라 구조적
- 제안: 옵션 재구성("전체 / 클릭 수집됨") + **"미수집 포함" 체크박스** (서버 include_null)

### 🟡 UX-4: 프리셋 의미 설명 부재
- 버튼은 있으나 각 프리셋의 기준(백분위)을 설명하는 툴팁/부제 없음
- 제안: 프리셋 버튼 title 속성 (예: "AI인용·수요 상위 50%")

### 🟡 UX-5: 필터 조합 시 교집합 0 안내는 있음 (정상)
- 빈 상태: "검색 결과가 없습니다 — 필터 초기화" + 버튼 ✅

## 3. 정상 확인 목록
- 검색 디바운스 300ms, 프리셋 토글, 정렬 방향 토글, 제외 목록 포함, KPI(상위 Priority), 토큰 localStorage
- 서버-UI 파라미터 매핑 전부 정합 (category/click/discovered/q/show_inactive/preset/sort/page)

## 4. 권장 조치 (우선순위)
1. UX-3: 쇼핑클릭 필터 재설계 + 미수집 포함 (서버+UI, TDD)
2. UX-1/UX-2: 기본 프리셋·초기화 동작 정리 (ai_pick → 전체 여부 결정)
3. UX-4: 프리셋 툴팁 추가 (HTML만)
