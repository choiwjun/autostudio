# 운세 발행 버튼 (POST /fortune/publish) — 구현 보고서 (implementation-report.md)

> 작성: 개발팀 · 모드: small · 승인: tech-design 승인 (오케스트레이터) → TDD 구현 완료
> 기준: v27 소스 + 신규 v28 구현 · 테스트: **404 passed / 10 skipped** (기존 396 + 신규 8, 기존 테스트 수정 0)

## 1. 구현 요약

| 파일 | 변경 내용 |
|---|---|
| `server.py` | `POST /fortune/publish` 엔드포인트 추가 (require_token, run_db) + `FORTUNE_PUBLISH_BUDGET_SECONDS = 55` |
| `collect.py` | 신규 헬퍼 3종: `_fortune_publish_candidates`(후보 목록) · `_fortune_publish_item_result`(항목 처리) · `publish_all_fortune_items`(결과 수집 + 예산) — `_publish_all_fortune`은 헬퍼로 위임 (동작 불변), `fortune_generate_step(publish=True)` 키워드 파라미터 추가 |
| `publish_client.py` | `BlogPublishError(status_code=None)` — 401/429/5xx 상태 구조적 전달, 메시지 포맷 `HTTP {status}: {body[:120]}` 불변 |
| `static/index.html` | "운세 발행" 버튼 + 결과 패널(`#fortunePanel`) — 기존 `authHeaders()`/`api()` 재사용, `esc()` 적용, 진행 중 비활성 |
| `tests/test_api.py` | 신규 5건 (T1~T4, T6) |
| `tests/test_fortune_publish.py` | 신규 2건 (T5, T7) |
| `tests/test_publish_client.py` | 신규 1건 (T8) |

## 2. AC 대응표

| AC | 검증 방법 | 결과 |
|---|---|---|
| AC-1 (200 + created/published/failed/skipped/items) | T2·T4 — 응답 스키마 단언 | ✅ |
| AC-2 (비개발 무토큰 401) | T1 — make_app(env="production") 무토큰 → 401 | ✅ |
| AC-3 (부분 성공 200 유지, 실패 항목 ok:false+reason) | T2 — 200/401 혼합, 서버 크래시 없음 + T5 (헬퍼 혼합) | ✅ |
| AC-4 (401 힌트 "토큰 불일치 — autoblog DASHBOARD_TOKEN 확인 필요") | T2·T5 — reason `HTTP 401 — 토큰 불일치 — …` | ✅ |
| AC-5 (429 힌트 "쿼터 소진 — autoblog Bailian token-plan 주간 쿼터 확인") | T5 — reason `HTTP 429 — 쿼터 소진 — …` | ✅ |
| AC-6 (버튼 → 호출 → 요약+항목별 렌더링) | 수동 확인 가능 DOM — `#fortunePanel` 요약 + mini-table (node --check 통과) | ✅ |
| AC-7 (`enabled:false` → "발행 비활성" 안내) | T3 + renderFortuneResult 분기 | ✅ |
| AC-8 (server.py에 requests.post 직호출·후보 하드코딩·slug 재구현 없음) | 코드 리뷰 — 엔드포인트는 collect 헬퍼만 호출 (server.py diff 확인) | ✅ |
| AC-9 (비활성 → 발행 0건, DB status 불변) | T3 — publish 호출 0회, daily_blog status=generated 유지 | ✅ |
| AC-10 (daily_sns "발행 대상 아님" 구분/제외, 발행 시도 없음) | T5 — 헬퍼 items에 daily_sns 부재 + 엔드포인트 `not_target` 레코드 추가 | ✅ |

## 3. 요구사항·승인 사항 반영 확인

| 승인 항목 | 구현 |
|---|---|
| OQ-1 (Vercel 60초) | ① 생성은 `fortune_generate_step(..., publish=False)` — LLM 1회 시도 (기존 구조 그대로, 실패 시 부분 수행 후 발행 진행) ② 발행은 `publish_all_fortune_items(budget_seconds=잔여)` — 총 55초 예산, 초과 후보는 `skipped("시간 예산")` (T7 + 응답 message "시간 예산 초과, 남은 항목은 재클릭으로 이어서 발행됩니다") |
| FR-3 (재사용) | `_publish_all_fortune` → `publish_all_fortune_items` 위임. 기존 test_fortune_publish.py 11건 **수정 없이** 통과 |
| OQ-2 (status_code) | `BlogPublishError.status_code` — T8 (401/429/503/네트워크 None), 기존 메시지 포맷 불변 |
| 기존 테스트 수정 금지 | 신규 8건 추가만 — 전체 404 passed (기존 396 유지) |

## 4. 자체 검증 결과 (fable-prove-it)

| 검증 | 명령/증거 | 결과 |
|---|---|---|
| 전체 테스트 | `./.venv/Scripts/python.exe -m pytest -q` → **404 passed, 10 skipped** | ✅ |
| 신규 테스트 단독 | test_api·test_fortune_publish·test_publish_client 신규 8건 전부 pass (TDD red→green 확인) | ✅ |
| JS 문법 | index.html 인라인 스크립트 추출 → `node --check` → JS SYNTAX OK | ✅ |
| 기존 동작 불변 | test_fortune_publish.py 11건 (publish_failed 재시도·qc_failed 미발행·비활성 스킵·고정 콘텐츠·weekly/monthly) 수정 없이 통과 | ✅ |

## 5. 미구현·한계 (사유 명시)

| 항목 | 상태 | 사유 |
|---|---|---|
| **autoblog 실통신 검증** | ❌ 미실시 | autoblog(autoblog-pearl.vercel.app) `BLOG_TOKEN`이 서버 기대 토큰과 불일치 — **실제 401로 막혀 있음** (사용자 설정 작업: autoblog DASHBOARD_TOKEN 교체 필요). 테스트는 전부 mock 기반. 실패 사유 표시 로직(`status_code` 기반 401/429 힌트)이 실제 401을 우아하게 처리하는지는 **QA 실통신 검증 포인트** |
| 429 쿼터 소진 자동 복구 | ❌ 제외 | 요구사항 비목표 (autoblog Bailian token-plan 주간 쿼터 — 사용자 작업). 재시도 정책은 기존 `_post` 유지 (신규 재시도 없음) |
| LLM 키 환경에서 생성 단계 55초 초과 | ⚠️ 한계 고지 | 생성(LLM 2회)이 예산을 넘으면 발행이 `시간 예산`으로 축소될 수 있음 — 멱등(slug upsert + published 스킵)이라 버튼 재클릭으로 이어서 처리 가능 |
| 실패 사유 DB 영구 저장 | ❌ 제외 | 요구사항 비목표 (collection_log 기록은 기존 유지, 응답 표시용으로만 수집) |

## 6. QA 집중 포인트 (개발QA팀 전달)

1. **실제 401 환경 우아한 실패 표시**: 로컬에서 실제 autoblog 호출 시 401이 발생하는 환경 — 버튼 클릭 → 각 항목 reason에 `HTTP 401 — 토큰 불일치 — autoblog DASHBOARD_TOKEN 확인 필요` 표시, 응답 200 유지, 서버 크래시 없음. (실측 재현: 로컬 `.env.local` 토큰으로 live probe 시 401 — 요구사항 §1.2)
2. **예산 초과 멱등 재클릭**: 429/5xx 다수 항목 환경(재시도 지연)에서 55초 예산 초과 → `skipped("시간 예산")` 항목이 응답에 포함되고, 재클릭 시 이전 실패분(publish_failed)이 재발행 시도되어 진행됨 (T6·T7로 로직 검증, 실통신은 시간 관계상 mock)
3. **daily_sns 미발행**: 응답 items에 daily_sns는 `not_target`("발행 대상 아님")로만 표시되고 발행 시도 0회 (T5·AC-10)
4. **401 vs 429 힌트 구분**: reason 문자열이 401은 "토큰 불일치", 429는 "쿼터 소진"으로 구분되는지 (T5)
5. **BLOG_PUBLISH_ENABLED=0**: 생성은 수행되고 발행은 안 되며 "발행 비활성 — BLOG_PUBLISH_ENABLED=1 및 BLOG_API_URL 설정 필요" 안내 (T3)
6. **프로덕션 인증**: 무토큰 401 (T1) — 토큰 저장 후 버튼 동작 확인

## 7. 산출물

- `pipeline/fortune-publish-button/plan.md`·`plan.html` / `tech-design.md`·`tech-design.html` / `implementation-report.md`·`implementation-report.html`
- 구현: `server.py` · `collect.py` · `publish_client.py` · `static/index.html` · `tests/test_api.py`(+5) · `tests/test_fortune_publish.py`(+2) · `tests/test_publish_client.py`(+1)
- 커밋: **하지 않음** (오케스트레이터 일괄 커밋 예정)
