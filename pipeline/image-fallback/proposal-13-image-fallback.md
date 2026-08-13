# 이미지 프로바이더 폴백 · 쿼터 모니터링 제안 (2026-08-11)

> 상태: **별도 논의** (VERIFICATION.md §6 미해결 항목) — 구현 전 결정 필요 사항 정리
> 근거: VERIFICATION.md "이미지 프로바이더 폴백/쿼터 모니터링 알림 — 기획서에 미반영 상태"

## 1. 현황 (실측)

| 항목 | 현재 동작 |
|---|---|
| 이미지 프로바이더 | **Bailian Token Plan 단일** (`image_gen.py`, 모델 `wan2.7-image`) |
| 키 해석 | `BAILIAN_TOKEN_PLAN_API_KEY` → `DASHSCOPE_API_KEY` 폴백 (`llm_client.resolve_api_key`) — **둘 다 Alibaba 계열** |
| 실패 처리 | content_batch: warning 로그 후 스킵 (이미지 없는 초안 유지) · server.py `/drafts/{id}/image`: 503 반환 |
| 쿼터 모니터링 | **없음** — 실패율/연속 실패 집계도, 알림도 없음 |
| 텍스트 LLM 대비 | 초안 LLM은 OpenCode Go ↔ Bailian **이중 폴백**(v23)이 있으나 이미지는 없음 |

## 2. 문제

1. **단일 장애점** — Bailian 이미지 쿼터 소진/장애 시 대표 이미지·섹션 이미지가 전부 누락.
   (v23에서 초안 LLM이 쿼터 소진 503으로 마비된 사례 — 이미지도 동일 리스크)
2. **무감지** — 배치 로그에만 남고, 이미지 실패가 누적돼도 운영자가 알 수 없음.
3. **기획 미반영** — 02-trd.md 이미지 섹션에 폴백/모니터링 없음.

## 3. 옵션 비교

### 옵션 A — DashScope 이미지 API 폴백 (권장)
- `image_gen.py`에 폴백 경로 추가: Bailian 실패 시 `https://dashscope.aliyuncs.com`의
  `wanx2.1-t2i-turbo`(텍스트→이미지) 재시도
- 장점: **추가 키 없이 가능** (`DASHSCOPE_API_KEY`는 이미 해석 경로에 존재 — 별도 키면 유효),
  코드 ~40줄, 테스트 3건 내외, 텍스트 LLM 폴백 패턴과 대칭
- 단점: 같은 Alibaba 계정이면 쿼터 소진이 동시 발생해 무의미 → **별도 DashScope 계정 키 필요**
- 한계: Bailian 401/네트워크 오류에는 유효, 쿼터 소진(공통 계정)에는 무효

### 옵션 B — 실패 메트릭 + 알림 (권장, A와 병행)
- content_batch에 이미지 실패 누적 카운터 → 배치 종료 시 결과 dict에 `image_failures` 기록
- 임계 초과(예: **연속 5건 또는 실패율 50%**) 시:
  - 최소: 배치 로그에 `ERROR` 등급으로 노출 → GitHub Actions 실패 전파(기본 알림)
  - 확장: 대시보드 신규 표시 (DB `drafts.image_fail_count` 또는 배치 결과 로그 테이블)
- 장점: 별도 인프라 불필요, GH Actions 알림 체계 재사용, 구현 소형
- 단점: 실시간 아님 (일일 배치 기준), 서버리스 수동 생성(server.py) 실패는 로그만

### 옵션 C — 타사 이미지 프로바이더 (DALL-E 등)
- OpenAI/Stability 등 추가 키·비용·심사 필요 — 개인 프로젝트 부담 큼. **비권장**

## 4. 권장안

**A(폴백) + B(메트릭·알림) 소형 패키지로 구현** — 작업량: image_gen.py 폴백 + content_batch
실패 집계 + 테스트 4~5건 (TDD), 기획 문서 02-trd.md 반영. 서버·스키마 변경 없음.

## 5. 결정 필요 사항

1. **DashScope 별도 키 보유 여부** — 있으면 A 즉시 구현, 없으면 B만 먼저
2. **알림 채널** — GH Actions 로그/실패 전파(기본)로 충분한지, Slack/이메일 추가할지
3. **서버리스 수동 생성(server.py) 실패 알림** — 범위 포함 여부 (대시보드 표시까지?)

## 6. 구현 시 작업 항목 (예정, 승인 후)

- [ ] `image_gen.py`: DashScope 폴백 경로 (fallback runner, 실패 사유별 폴백 여부 판단)
- [ ] `content_batch.py`: 이미지 실패 집계 + 임계 로그
- [ ] `tests/test_image_gen.py`·`tests/test_content_batch.py`: 폴백·집계 테스트
- [ ] `docs/planning/02-trd.md`: 이미지 섹션에 폴백·모니터링 반영
- [ ] CHANGELOG·VERIFICATION.md 갱신
