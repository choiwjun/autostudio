# 추출·추천필터링 개선고도화 (v14) — 설계 문서

- 일자: 2026-08-06
- 상태: **확정** — 안 A (데이터 기반 자가보정 파이프라인)
- 목표: 하드코딩 임계값·단순 블랙리스트·미반영 성장 신호를 정비해 "추천 품질이 실제 성과와 불일치" 문제를 데이터 기반으로 해결. 재보정 커밋(v12/v13형) 반복 종료.

## 배경

v12(수요 정규화)·v13(배지 재보정)이 연속으로 "임계값 재보정"이었던 것은 절대값 하드코딩 임계가 데이터 분포 변화를 따라가지 못했기 때문. 사용자 설문(브레인스토밍)에서 5개 문제 확정:

1. 추천 품질이 실제 성과와 불일치
2. 추출 결과에 노이즈가 많음
3. 임계값이 데이터에 따라 계속 어긋남
4. 카테고리 분류 부정확
5. 성과 피드백 부재 (→ **자동 프록시**: 데이터랩 검색량 추이, 수동 입력 제외)

**성공 기준** (사용자 확정):
- ① 재보정 반복이 끝나는 것 — 임계값이 데이터 분포를 따라감
- ② 상승 키워드(검색량 추이)가 추천 상위로 오는 것
- ③ 노이즈 유입률을 측정할 수 있는 것

**범위**: 파이프라인 순서대로 전 영역 (추출 → 필터 → 카테고리 → 점수/임계값 → 성장 프록시 피드백). LLM 정제(안 C)는 이번 범위에서 제외 — 후속 단계.

## 핵심 기존 사실 (설계 전제)

- `demand_growth`(데이터랩 30일 시계열 기울기, v9)는 이미 배치에서 수집·저장되고 `SORT_COLUMNS`에 있으나 **priority 점수에 미반영**
- `performance_boost`(수동 피드백 보상, v11)는 이미 존재 — 초안 발행 후 보너스로 priority에 합산
- `collection_log`에 reject 사유(substring/token/portal/stopword)가 이미 기록됨 — 거부율 지표는 "새 수집" 없이 집계만 필요
- `PRIORITY_SQL`(db.py)과 `scoring.v6_priority`가 이중 정의 — v12 원칙: 두 곳 동일 값 유지

---

## 1. 노이즈 필터 강화 (refine.py + collect.py)

### 1.1 신규 필터 규칙 (refine_keywords)

| 사유 코드 | 규칙 | 예시 |
|---|---|---|
| `len` | 공백 제거 후 1자 또는 25자 초과 | "와", "오늘의 맛집 추천 리스트 정리해보았습니다" |
| `noise` | 순수 특수문자만 / 숫자+단위만(숫자 외 토큰 0개) | "!!!", "2024", "10분" |
| `brand` | 단독 브랜드 토큰 차단 (브랜드 사전, 토큰 단독 매치) | "애플"은 차단, "아이폰 배터리 교체"는 통과 |

- `brand`는 토큰 단독 매치만 — 부분문자열 매치 금지 ("아이폰" 키워드는 오히려 유망 상품 검색어)
- 브랜드 사전: `BRAND_TOKENS = {"애플", "아이폰", "삼성", "갤럭시", "에어팟", "나이키", ...}` — 실측 리젝 로그 기반으로 확장 (문서 내 초기 사전 + 주간 리젝 리뷰로 증분)

### 1.2 거부율 지표 (collect.py)

- `discover()`의 `result`에 `found_raw`(발굴 후보 수), `rejected`(거부 수) 추가
- `run_collection`의 최종 result에 `reject_rate`(rejected/found_raw) 저장 → `finish_run`의 `note`에 기록
- 노이즈 유입률 = 일일 신규 거부 수 / 발굴 후보 수 (대시보드 노출은 §5)

## 2. 카테고리 분류 개선 (config.py + collect.py)

- `DEFAULT_KEYWORD_CATEGORY_RULES` 확장 — 발굴 실데이터(무카테고리 키워드 상위 목록) 기준으로 규칙 추가
- 미분류(시드 상속·규칙 매치 모두 실패) 시 **"기타"** 부여 — 현재는 빈 문자열이라 카테고리 필터에서 누락되고 CPC 등급도 기본값(0.5)에 불과
- "기타"는 CPC 기본값 유지(ELSE 0.5) — 기존 `CPC_TIER_SQL` 변경 없음

## 3. 자가보정 임계값 — 백분위 기반 프리셋 (핵심)

### 3.1 백분위 집계 (db.py)

- 활성 키워드(`k.active=1`)의 **최신 스냅샷** 기준 지표별 백분위 쿼리:
  - 대상 지표: `ai_cite_idx`, `demand_idx`, `opportunity`, `demand_growth`
  - 분위: P25, P50, P75, P90
- SQLite: `PERCENTILE` 없음 → 정렬 + OFFSET 계산으로 분위값 도출 (COUNT → 오프셋 = ROUND(분위 × (n-1)))
- Postgres: `PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ...)` 사용
- 구현: 기존 `_q`/`_qd` 이중 SQL 패턴 준수 — `percentiles(metric)` 형태 단일 메서드, 지표별 SQL 분기

### 3.2 프리셋 정의 변경 (server.py)

| 프리셋 | 기존 (절대값) | 변경 (백분위) |
|---|---|---|
| `ai_pick` | ai_cite≥0.6 & demand≥0.001 | ai_cite ≥ P50 & demand ≥ P50 |
| `promising` | opp≥20 & demand≥0.001 | opportunity ≥ P75 & demand ≥ P50 |

- P50(중앙값)이 0이면 백분위 방식 무의미 → **폴백 절대값** 사용 (현재 값 유지). 활성 키워드 수 < 20이어도 폴백
- 배지(대시보드, `static/index.html`)도 동일: 애포 배지 = opportunity ≥ P75 (v13의 20 하드코딩 제거), 유망 배지 = P75&P50
- 배지·프리셋 임계는 **/keywords 응답에 함께 반환** (`thresholds: {ai_cite: 0.55, demand: 0.0021, opportunity: 21.3, ...}`) — 대시보드 툴팁·투명성용

### 3.3 계산 시점

- **조회 시(요청마다)** 계산 — 배치 재계산·캐시 불필요 (키워드 수 ≤ 500, 쿼리 1회 추가 비용 무시 가능). 데이터 분포가 바뀌면 프리셋이 즉시 따라감 → 재보정 커밋 원천 차단

## 4. 성장 신호 priority 반영 (scoring.py + db.py)

### 4.1 성장 정규화

- `demand_growth`는 실측 기울기(최근 7일 vs 이전 23일 평균 비율) — 범위 무제한(음수/양수)
- `growth_norm = clamp(growth / GROWTH_NORM_MAX, -0.5, 1.0)` — GROWTH_NORM_MAX=0.05 재사용 (일 5% 성장이 만점)
- NULL(미수집)이면 0 — 데이터랩 미지원 키워드의 기존 순위 영향 최소화

### 4.2 새 priority 공식 (v14)

```
priority = 30×ai_cite_idx + 25×demand_norm + 15×growth_norm + 30×CPC등급 + performance_boost
```

- 기존 35/35/30에서 성장 몫(15)을 수요에서 분리 — 성장은 보조 신호이므로 몫 축소
- `demand_norm`은 v12 그대로 (demand/0.01, ≤1 클램프)
- `PRIORITY_SQL`(db.py:214)과 `scoring.v6_priority` **동일 수식 유지** (v12 원칙)
- `v6_priority` 시그니처 확장: `v6_priority(ai_cite, demand, cpc, growth=None)` — growth 기본 None(0)

## 5. 측정·노출

- **거부율**: 대시보드 상단 컨트롤러에 최근 실행의 "발굴 n개 중 거부 n개 (xx%)" 표시 (collection_runs note 파싱)
- **임계 툴팁**: 프리셋 버튼/배지에 현재 적용 중인 백분위 임계 표시 ("ai_pick: 상위 50% ai인용·수요" — /keywords thresholds 필드)
- **상승 키워드 확인**: sort=priority 시 demand_growth 상위 키워드의 순위 상승을 시각 확인 (성공 기준 ②)

## 6. 테스트

| 영역 | 케이스 |
|---|---|
| refine | len/noise/brand 규칙별, 기존 substring/token/portal/stopword 회귀, "아이폰 배터리 교체" 통과 |
| 백분위 | 빈 테이블(폴백), 키워드 1개(폴백), 20개 미만(폴백), 동점, P50/P75 경계, SQLite/Postgres 동일 결과 |
| 프리셋 | 백분위 임계 적용, 폴백 발생, thresholds 응답 포함 |
| 성장 정규화 | growth None→0, 음수(-0.1→-0.5), 0, 0.05→1.0, 0.2→1.0 클램프 |
| priority | 새 가중치 수식, PRIORITY_SQL과 v6_priority 동일 결과 (테스트 1개로 정합 보장) |
| 회귀 | 기존 전체 테스트 (141 passed 유지) |

## 7. 범위 외 (후속)

- LLM 기반 키워드 정제·분류 (안 C) — 배치 내 LLM 호출 인프라 필요
- 수동 성과 입력 (조회수/수익 직접 입력) — 사용자 제외 확정
- 블로그 발행 연동

## 문서 개정 이력

| 버전 | 일자 | 변경 요약 |
|---|---|---|
| v1 | 2026-08-06 | 최초 확정 (브레인스토밍: 문제 5개 → 안 A 채택 → 성공 기준 3개) |
