# 이미지 프로바이더 폴백 + 쿼터 모니터링 알림 — 간이 계획 (plan.md)

> 작성: 개발팀 · 모드: small (요구사항팀 판정) · 근거: `requirements.md` (FR-1~FR-5, 테스트 5건)
> 승인 게이트: 본 plan + `tech-design.md` 승인 후 TDD 구현 시작

## 1. 목표

1. Bailian 이미지 쿼터 소진/장애 시 대표·섹션 이미지가 **DashScope(wanx2.1-t2i-turbo)로 폴백**되어 계속 생성되게 한다 (FR-1)
2. 배치 실행 단위 이미지 실패(시도/최종 실패/연속 실패)를 집계하고, 임계(연속 5건 또는 시도 5건+ 실패율 50% 초과) 초과 시 ERROR 로그 + `image_alert` → **GH Actions 잡 실패 전파**로 운영자 인지 (FR-4·FR-5)
3. `DASHSCOPE_API_KEY` 미설정 시 **기존 동작 100% 불변** (FR-2), 폴백도 실패하면 기존 예외 전파 (FR-3)

## 2. 수용 기준 대응 (AC → 구현 항목)

| AC | 구현 항목 | 파일 |
|---|---|---|
| AC1-1/1-2/1-3 | Bailian 실패 → DashScope 재시도 **정확히 1회**, 성공 URL 반환 | `image_gen.py` `_run_http` + `_dashscope_generate` |
| AC1-4 | 폴백 시 WARNING 로그 (원본 예외 메시지 + 폴백 사용) | `image_gen.py` |
| AC2-1/2-2/2-3 | 키 미설정 시 폴백 미호출·기존 예외 전파, 가드 메시지 유지 | `image_gen.py` (가드 위치 불변) |
| AC3-1/3-2 | 폴백 실패 → `ImageGenerationError` (최종 원인 포함), 배치 격리 유지 | `image_gen.py` |
| AC4-1/4-2/4-3 | 결과 dict에 `image_attempts`·`image_failures` 추가 (백필+신규 모두 집계, 메모리 내) | `content_batch.py` + `image_gen.py` stats |
| AC4-4 | 배치 실행 이력 기록 — **`collection_runs`에 result 컬럼이 없음(실측)** → 기존 `note` JSON에 이미지 집계 병기로 실현 (스키마 변경 금지 준수) | `collect.py` |
| AC5-1/5-2/5-3/5-4 | 임계 판정(연속 5건 / 시도 5건+ 실패율>50%), ERROR 로그 1건, 임계 미만 시 ERROR 없음 | `content_batch.py` |
| AC5-5 | 결과 dict `image_alert: True` → `collect.main()` `exit 1` (~3줄) | `collect.py` |
| AC5-6 | 임계 초과여도 배치 정상 완주 (부분 성공 보존) | `content_batch.py` (기존 격리 유지) |

## 3. 구현 범위 (Must 전부) / 제외

**포함**: `image_gen.py` 폴백 + stats, `content_batch.py` 집계·판정·ERROR 로그, `collect.py` 연동(3줄+note 병기), `llm_client.py` (GET·헤더 지원 — 순수 추가, 기존 동작 불변), 테스트 5건+α, 문서 4종(02-trd·.env.example·CHANGELOG·VERIFICATION).

**제외**: `server.py` 서버리스 수동 생성, DB 스키마, 대시보드, 외부 알림 채널, 외부 라이브러리(urllib 유지).

## 4. 테스트 계획 (TDD — 테스트 먼저)

| # | 파일 | 시나리오 | 검증 AC |
|---|---|---|---|
| T1 | `tests/test_image_gen.py` | Bailian 실패 + DASHSCOPE 키 설정 → DashScope 1회 재시도·성공 URL | AC1-1, 1-2, 1-3, 1-4 |
| T2 | `tests/test_image_gen.py` | Bailian 실패 + 키 미설정 → 폴백 미호출·기존 예외 전파 | AC2-1 |
| T3 | `tests/test_image_gen.py` | 폴백도 실패 → `ImageGenerationError` (최종 원인 포함) | AC3-1 |
| T4 | `tests/test_content_batch.py` | 연속 5건 실패(백필 5건) → ERROR 로그 + `image_alert=True` | AC5-1, 5-5 |
| T5 | `tests/test_content_batch.py` | 시도 5건 중 3건 실패(율 60%) → ERROR / 1건 실패(율 20%) → ERROR 없음 | AC5-2, 5-3 |
| T6+ | `tests/test_content_batch.py` | 판정 함수 단위 (연속 4건·시도 4건 실패율 100% → alert 없음: 소표본 가드) | AC5-2 |
| T7+ | `tests/test_collect.py` | `run_collection` 결과 `image_alert=True` → `main()` `SystemExit(1)` / 미임계 → `exit 0` | AC5-5 |
| T8+ | `tests/test_content_batch.py` | 키 미설정 스킵 결과 dict 갱신 (신규 키 기본값 포함) | AC4-1 |

**기존 테스트 수정 (의도적 계약 변경 1건)**: `tests/test_content_batch.py::test_skips_without_llm_key`가 결과 dict **정확 일치**를 단언 → FR-4로 dict 확장되므로 기대값에 신규 키 추가.

## 5. 검증 방법

1. `./.venv/Scripts/python.exe -m pytest -q` 전체 통과 (기존 377 passed 유지 + 신규 ~8건)
2. fable-prove-it — 각 수용 기준을 테스트/실행 증거로 대조
3. code-review — diff 심사 (외부 라이브러리 없음·시그니처 불변·키 로그 미노출 확인)

## 6. 산출물

`plan.md`·`plan.html` / `tech-design.md`·`tech-design.html` / `implementation-report.md`·`implementation-report.html` (모두 `pipeline/image-fallback/` 아래) + 소스 구현 + 문서 4종 갱신
