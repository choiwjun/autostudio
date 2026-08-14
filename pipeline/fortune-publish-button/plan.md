# 운세 발행 버튼 (POST /fortune/publish + 대시보드 버튼) — 간이 계획 (plan.md)

> 작성: 개발팀 · 모드: small (요구사항팀 판정) · 상위 문서: `requirements.md` (FR-1~FR-5, AC-1~AC-10)
> 오케스트레이터 승인: small 모드 · OQ-1(60초 예산) 확정 지침 · FR-3 재사용 원칙 · OQ-2(status_code 속성) 권장
> 승인 게이트: 본 plan + `tech-design.md` 승인 후 TDD 구현 시작 (승인 전 구현 금지)

## 1. 목표

1. 대시보드에서 **운세 발행을 수동 트리거**하는 `POST /fortune/publish` 엔드포인트 추가 (FR-1)
2. "운세 발행" 버튼 + 결과 표시(요약 + 항목별 사유, 401/429 힌트) 추가 (FR-2)
3. 기존 생성·발행 로직 **재사용** — collect.py에 항목별 결과 반환 헬퍼 추가, `_publish_all_fortune` 위임 리팩터링 (FR-3, 기존 테스트 11건 불변)
4. `BLOG_PUBLISH_ENABLED=0` 시 생성은 수행 + "발행 비활성" 안내 응답 (FR-4)
5. 발행 후보 규칙 명시 — `*_blog`만, published/qc_failed 스킵, daily_sns "발행 대상 아님" (FR-5)

## 2. 수용 기준 대응 (AC → 구현 항목)

| AC | 구현 항목 | 파일 |
|---|---|---|
| AC-1 | 200 + `{created, published, failed, skipped, enabled, message, items[]}` | `server.py` |
| AC-2 | `dependencies=[Depends(require_token)]` — 비개발 무토큰 401 | `server.py` |
| AC-3 | 항목 단위 try/except — 실패 항목 `ok:false`+`reason`, 응답 200 유지 | `collect.py` 헬퍼 |
| AC-4 | 401 → reason에 "HTTP 401" + "토큰 불일치 — autoblog DASHBOARD_TOKEN 확인 필요" | `collect.py` (status_code 기반) |
| AC-5 | 429 → reason에 "HTTP 429" + "쿼터 소진 — autoblog Bailian token-plan 주간 쿼터 확인" | `collect.py` |
| AC-6 | 버튼 클릭 → 엔드포인트 호출 → 요약+항목별 결과 DOM 렌더링 | `static/index.html` |
| AC-7 | `enabled:false` → "발행 비활성 — BLOG_PUBLISH_ENABLED=1 필요" 안내 | `static/index.html` |
| AC-8 | server.py에 requests.post 직호출·후보 하드코딩·slug 재구현 없음 (collect import만) | `server.py` |
| AC-9 | 비활성 cfg → 200 + `enabled:false` + 안내, 발행 시도 0건, DB status 불변 | `server.py` |
| AC-10 | daily_sns는 items에 `not_target`("발행 대상 아님")으로 구분 표시, 발행 시도 없음 | `server.py`(응답 구성) |

## 3. 구현 범위 / 제외

**포함**: `server.py` 엔드포인트(+예산 상수), `collect.py` 헬퍼 3종(후보 목록·항목 처리·결과 수집) + `_publish_all_fortune` 위임 + `fortune_generate_step(publish=...)` 키워드 파라미터(기본 True — 기존 동작 불변), `publish_client.py` BlogPublishError.status_code(메시지 포맷 불변), `static/index.html` 버튼+결과 패널, 신규 테스트(요구 T1~T6 + status_code·예산 2건), 문서 3종(+html).

**제외**: autoblog 토큰/플랜 변경(사용자 작업), 401/429 자동 복구, 실패 사유 DB 영구 저장, 운세 상태 페이지 신설, GH Actions/스케줄 변경, `db.py`·`config.py`·`engine/fortune_content.py` 변경, 기존 테스트 수정.

## 4. 테스트 계획 (TDD — 테스트 먼저, 기존 수정 금지)

| # | 파일 | 시나리오 | 검증 AC |
|---|---|---|---|
| T1 | `tests/test_api.py` | production 무토큰 POST /fortune/publish → 401 | AC-2 |
| T2 | `tests/test_api.py` | 후보 2건(200/401) → 200 응답, items ok true/false, 실패 reason에 401·토큰 힌트 | AC-1, AC-3, AC-4 |
| T3 | `tests/test_api.py` | blog_publish_enabled=False → enabled:false+안내, publish 호출 0회 | AC-7, AC-9 |
| T4 | `tests/test_api.py` | LLM 키 없음+고정 콘텐츠 미생성 → 생성(created>0)→발행 (fortune_generate_step 경유) | AC-1, FR-1-a |
| T5 | `tests/test_fortune_publish.py` | 헬퍼 직접 호출 — 200/401/429/5xx/qc_failed/published 혼합 → 항목별 상태·사유, daily_sns 비포함 | AC-3~AC-5, AC-10, FR-5 |
| T6 | `tests/test_api.py` | status=publish_failed 행 재발행 성공 → published 갱신 | FR-1-b, NFR-4 |
| T7+ | `tests/test_fortune_publish.py` | 예산 0 → 전 항목 skipped("시간 예산") | OQ-1 |
| T8+ | `tests/test_publish_client.py` | BlogPublishError.status_code (401 즉시/429 재시도 후/네트워크 None), 메시지 포맷 불변 | OQ-2 |

**기존 테스트 수정: 0건** (신규 추가만 — `_publish_all_fortune` 동작은 test_fortune_publish.py 11건으로 회귀 증명)

## 5. 검증 방법

1. `./.venv/Scripts/python.exe -m pytest -q` 전체 통과 (기존 396 passed 유지 + 신규 ~8건)
2. fable-prove-it — AC별 테스트/실행 증거 대조
3. JS 문법 검증 — node --check (index.html 인라인 스크립트 추출)
4. AC-8 코드 리뷰 — server.py에 requests.post/후보 목록/slug 규칙 부재 확인

## 6. 산출물

`plan.md`·`plan.html` / `tech-design.md`·`tech-design.html` / `implementation-report.md`·`implementation-report.html` (모두 `pipeline/fortune-publish-button/`) + 소스 구현(server.py·collect.py·publish_client.py·static/index.html) + 신규 테스트
