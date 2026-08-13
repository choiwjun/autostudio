# 이미지 프로바이더 폴백 + 쿼터 모니터링 — 간이 기술 설계 (tech-design.md)

> 작성: 개발팀 · 모드: small · 근거: `requirements.md` FR-1~FR-5 · 상태: **승인 대기**
> 실측 기준: 현행 소스(image_gen.py v15·content_batch.py v17·collect.py·llm_client.py v23) + **DashScope 공식 문서(help.aliyun.com, 2026-08-13 실측)**

## 1. 아키텍처 개요 (변경 전/후)

```
변경 전:  generate_image / generate_section_images
              └─ _run_http ── llm_client.post_json ──▶ Bailian (단일, 실패=누락+warning)
변경 후:  generate_image / generate_section_images   (public 시그니처·가드 불변)
              └─ _run_http (stats 집계 + 폴백 오케스트레이션)
                   ├─ _primary_generate ──▶ Bailian (기존 코드 그대로 이동)
                   └─ 실패 시 ── _dashscope_generate ──▶ DashScope wanx2.1 (1회, async task+폴링)
content_batch: 결과 dict 확장(image_attempts/image_failures/image_alert) + 임계 판정·ERROR 로그
collect:        run_collection 결과 merge → main() image_alert 시 exit 1 (+ note 병기)
```

## 2. 폴백 레벨 결정 — `_run_http` 레벨 (FR-1 정합)

**결정: `_run_http` 레벨에서 폴백을 구현한다.** (요구사항 §3 타깃 표의 "대표·섹션 공통 `_run_http` 레벨"과 일치)

근거:
1. **대표·섹션 공통 보장**: `generate_image`(대표)·`generate_section_images`(섹션, 섹션당 1회 호출) 모두 기본 runner로 `_run_http`를 경유 → 폴백이 두 경로에 **단일 구현**으로 적용됨 (AC1-1). public 함수 레벨이면 두 곳에 중복 구현 + runner 주입 의미가 흐려짐.
2. **재시도 1회 제한** (AC1-3): 호출 1회(섹션 1장)당 폴백 1회 — 섹션 8장이면 섹션별 1회씩 최대 8회 재시도가 발생하지만 이는 "이미지 1건당 1회"의 정합 해석 (요구사항 용어: 시도 = 이미지 생성 호출 1회).
3. **키 미설정 가드 불변** (AC2-2): 가드는 `generate_image`/`generate_section_images` 진입부에 그대로 — `_run_http`에 도달한 호출만 시도로 집계 (요구사항 §5 "키 미설정 가드에서 중단되는 경우 제외"와 일치).
4. **runner 주입 호환**: `tests/test_api.py` 등이 `_run_http`를 monkeypatch하는 기존 테스트 패턴 그대로 유효 (폴백·stats는 교체된 runner에선 동작하지 않음 — 기존 테스트 의미 불변).

## 3. DashScope API 계약 — **실측 결과 (요구사항 가정 대비 변경)**

### ⚠️ 핵심 실측: wanx2.1-t2i-turbo는 **HTTP 동기 호출 미지원, 비동기(task 생성→폴링) 전용**

출처: Aliyun Model Studio 공식 문서 `text-to-image-v2-api-reference` (2026-08-13 실측):
> "**wan2.5 及以下版本模型**: 支持 HTTP 异步调用…**不支持 HTTP 同步调用**" — wanx2.1-t2i-turbo(万相 2.1) 포함.
> 동기 호출은 wan2.6 이상만 지원. 비동기 헤더 누락 시 오류: "current user api does not support synchronous calls".

요구사항 §11 가정 4("동기 응답 지원 — `output.results[].url` 형식")는 **사실과 다름**. `output.results[].url` 형식 자체는 폴링 응답에서 확인됨 (형식 유지, 흐름만 async).

### 적용 계약 (공식 문서 기반)

**① Task 생성 (POST)**
```
POST https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis
Headers: Authorization: Bearer $DASHSCOPE_API_KEY · Content-Type: application/json
         X-DashScope-Async: enable   (필수 — 누락 시 동기 미지원 오류)
Body: { "model": "wanx2.1-t2i-turbo",
        "input": { "prompt": "<동일 프롬프트>" },
        "parameters": { "size": "1280*720", "n": 1 } }
응답: { "output": { "task_id": "...", "task_status": "PENDING" }, "request_id": "..." }
```
- size: wan2.2 이하 규격 [512,1440]×[512,1440] — 1280*720 유효 (AC1-1 "동일 파라미터 크기 1280*720, n=1" 충족)
- prompt 길이: wan2.1 계열 **500자 제한** — 현행 프롬프트(대표 ~300자, 섹션 ~200자) 이내
- n=1 (기본 4 — 비용 통제), watermark 기본 false (미전달)

- **리전별 호스트 (QA P2)**: 기본 `https://dashscope.aliyuncs.com`(베이징),
  `DASHSCOPE_BASE_URL` env로 오버라이드 — 싱가포르·국제 키는
  `https://dashscope-intl.aliyuncs.com` (키 발급 리전과 호스트 불일치 시 인증 실패).
  호출 시점(`_dashscope_base_url()`) 평가 — import 시점 고정 아님

**② Task 조회·폴링 (GET)**
```
GET https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}
Headers: Authorization: Bearer $DASHSCOPE_API_KEY
응답(성공): { "output": { "task_status": "SUCCEEDED",
                          "results": [ { "url": "https://dashscope-result-.../1.png" } ] }, ... }
응답(실패): { "output": { "task_status": "FAILED", "code": "...", "message": "..." }, ... }
```
- 폴링 간격 3초, **예산 = 폴백 타임아웃(기존 55s) 내** (NFR-1: 이미지 1건 최대 지연 ≈ 기존 2배 110s 유지)
- SUCCEEDED → `output.results[0].url` 반환 / FAILED → 예외(원인 포함) / 예산 소진 → 타임아웃 예외
- 결과 URL 24시간 유효 — 기존 저장 흐름(즉시 DB 저장)과 정합

### llm_client 확장 (순수 추가 — 기존 동작 불변)
- `post_json(..., headers=None)`: 선택 헤더 병합 (X-DashScope-Async 전달용, 기본 None = 기존과 동일)
- `get_json(url, api_key, timeout, error_cls, err_prefix)`: GET + 동일 오류 정규화 (HTTP/URLError/Timeout/JSON 파싱 → 전용 예외)
- 공용 `_open_json` 헬퍼로 중복 제거 — **기존 post_json 동작·메시지 문자열 불변** (기존 테스트로 증명)

## 4. 키 해석 규칙 (FR-2·가정 3 반영)

| 환경 | Bailian 1차 호출 | DashScope 폴백 |
|---|---|---|
| BAILIAN 키만 | `resolve_api_key()`=Bailian 키 → 정상 | `os.getenv("DASHSCOPE_API_KEY")` 없음 → **폴백 미실행**, 기존 예외 그대로 전파 (AC2-1·AC2-3) |
| 두 키 모두 | Bailian 키 | DASHSCOPE 키로 폴백 (AC1-1) |
| DASHSCOPE 키만 | `resolve_api_key()`=DASHSCOPE 키로 Bailian 엔드포인트 호출 → 실패(401) 예상 | DASHSCOPE 키로 폴백 동작 (가정 3 — 불필요한 1차 호출 1회, 기능상 문제 없음) |
| 키 없음 | `generate_image` 진입부 가드가 raise (기존 메시지 "이미지 키가 필요합니다…") | 해당 없음 (AC2-2) |

- 폴백 키는 `resolve_api_key()`가 아니라 **`DASHSCOPE_API_KEY` 직접 조회** — Bailian 키가 DashScope 엔드포인트로 새는 것 방지 (NFR-2)

## 5. 실패 집계 설계 (FR-4)

### image_gen.py — 모듈 레벨 stats (public 시그니처 불변 유지)
```python
_IMAGE_STATS = {"attempts": 0, "failures": 0, "consecutive_failures": 0}
def reset_image_stats(): ...   # 배치 시작 시 content_batch가 호출
def get_image_stats(): ...     # 배치 종료 시 content_batch가 조회
```
- `_run_http` 진입 시 `attempts += 1` (가드 raise는 미도달 → 미집계 — 요구사항 용어 정의와 일치)
- 성공(1차 또는 폴백) 시 `consecutive_failures = 0`
- 최종 실패(폴백 없음/폴백 실패) 시 `failures += 1`, `consecutive_failures += 1`
- 섹션 이미지: `generate_section_images` 내부 per-section catch는 유지 — 각 섹션 실패가 stats에 이미 반영됨 (AC4-2: 신규+백필, 대표+섹션 전부 집계)

### content_batch.py — 판정 (AC5-1~5-3)
```python
IMAGE_ALERT_CONSECUTIVE = 5
IMAGE_ALERT_MIN_ATTEMPTS = 5   # 실패율 판정 최소 시도 (소표본 노이즈 방지 — 가정 5)
def image_alert_triggered(attempts, failures, consecutive):
    if consecutive >= IMAGE_ALERT_CONSECUTIVE: return True
    if attempts >= IMAGE_ALERT_MIN_ATTEMPTS and failures * 2 > attempts: return True
    return False
```
- `run_content_batch` 시작: `image_gen.reset_image_stats()` → 종료: stats 조회 → 결과 dict 반영 + 임계 시 `logger.error` (집계 수치 + 원인 파악 힌트 포함 — AC5-4) + `image_alert=True` (AC5-5)
- 결과 dict: `{"drafts_created", "draft_images_created", "image_attempts", "image_failures", "image_alert"}` — **키 미설정 스킵 경로에도 신규 키 기본값 포함** (일관성)
- 배치 자체는 임계와 무관하게 정상 완주 (AC5-6 — 기존 격리·부분 성공 보존)

## 6. collect.py 연동 (FR-5 — AC5-5)

- `run_collection`: 결과 dict 초기값에 `image_attempts/image_failures/image_alert` 추가 + content_batch 결과 merge (~3줄)
- `main()`: 기존 exit-1 조건(차단/전량 실패)에 `if result.get("image_alert"): raise SystemExit(1)` 추가 → GH Actions 잡 실패 → GitHub 메일 알림
- 완료 로그에 이미지 시도/실패 수치 추가 (관측성)

### ⚠️ AC4-4 실측 불일치 대응 (설계 확정)
요구사항 AC4-4는 "collect.py가 결과를 `collection_runs.result`에 저장"을 전제하나 **실측상 해당 컬럼이 없다** (스키마: new_keywords/snapshotted/errors/note만 존재 — db.py 확인). DB 스키마 변경은 범위 제외이므로:
→ **기존 `note` JSON 메커니즘에 이미지 집계를 병기** (`{"found_raw":…, "image_attempts":…, "image_failures":…, "image_alert":…}`). 대시보드가 note의 found_raw만 읽고 미지 키는 무시함을 확인(static/index.html) — 추가 키는 무해. 발굴 없고 이미지 집계만 있으면 이미지 키만 기록. (스키마 무변경·NFR-6 사후 분석 충족)

## 7. 예외·로그 설계 (AC3-1·AC1-4)

- **AC1-4 (폴백 WARNING)**: `_dashscope_fallback`에서 폴백 직전 `logger.warning("image API primary failed (%s) — retry via DashScope %s", primary_err, "wanx2.1-t2i-turbo")` — 원본 예외 메시지 포함
- **AC3-1 (최종 실패 원인)**: 폴백 실패 시 `raise ImageGenerationError(f"image API failed after dashscope fallback: {e}") from e` — 메시지에 DashScope 실패 원인, 예외 체인에 원본 보존
- **AC2-1 (키 미설정)**: `_dashscope_fallback`는 키 없으면 카운터만 갱신하고 **원본 예외를 그대로 re-raise** (메시지 불변)
- **AC5-4 (ERROR 로그)**: `logger.error("이미지 생성 실패 임계 초과: 시도 %d건, 최종 실패 %d건, 연속 실패 %d건 — Bailian/DashScope 키·쿼터 점검 필요…")`
- NFR-2: 키 값은 로그·예외 메시지에 절대 미포함 (기존 패턴 유지 — post_json은 Bearer 헤더로만 사용)

## 8. 문서 반영 (구현·테스트 통과 후)

| 파일 | 반영 내용 |
|---|---|
| `docs/planning/02-trd.md` | 이미지 섹션: 폴백(wanx2.1 async)·실패 집계·알림 반영, "키 401 무효" stale 문구 갱신 |
| `.env.example` | `DASHSCOPE_API_KEY` 옵션 항목 추가 (미설정 = 폴백 비활성 명시) |
| `CHANGELOG.md` | v26 항목 (폴백·모니터링·테스트 수) |
| `docs/VERIFICATION.md` | §6 "미해결(별도 논의)" → 해소 표기 |

## 9. 리스크·가정

| 항목 | 내용 |
|---|---|
| 실측 대비 변경 | ① wanx2.1 동기→**async(생성+폴링)** 전환 ② AC4-4 result 컬럼→**note JSON 병기** — 둘 다 요구사항의 "구현 시 실측/대비" 위임 범위 |
| 실키 실측 불가 | 유효한 DASHSCOPE_API_KEY가 없어 실제 호출 검증은 불가 — 공식 문서 계약으로 구현, 파싱은 실패 시 전용 예외로 정규화. 개발QA팀이 키 보유 시 실측 권장 |
| 폴백 지연 | 1건 최대 ~110s (55s×2) — 배치 예산 1200s·GH Actions 60분 내 (NFR-1 충족) |
| 호환성 | public 시그니처·반환형 불변 (stats는 모듈 함수로 은닉), llm_client는 순수 추가, 기존 377 테스트 전부 통과 목표 |
