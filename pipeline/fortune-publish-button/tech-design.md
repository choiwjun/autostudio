# 운세 발행 버튼 (POST /fortune/publish) — 간이 기술 설계 (tech-design.md)

> 작성: 개발팀 · 모드: small · 상위: `requirements.md` FR-1~FR-5 + 오케스트레이터 승인 (OQ-1 예산 확정, OQ-2 status_code 권장)
> 실측 기준: v27 소스 (server.py·collect.py·publish_client.py·static/index.html·db.py) — 2026-08-13
> 승인 게이트: **본 문서 승인 전 구현 금지**

## 1. 아키텍처 개요 (변경 전/후)

```
변경 전 (v27):
  fortune_generate_step(d, cfg, today) ── 생성(LLM 1회/타입) ──▶ _publish_all_fortune(d, cfg, today)
      └─ 후보 순회 · 발행 · DB 상태 갱신 · collection_log 기록  (반환값 없음 — 실패 사유 미노출)

변경 후 (v28):
  [대시보드 버튼] ── POST /fortune/publish (require_token) ──▶ server.fortune_publish()
      ├─ (a) collect.fortune_generate_step(d, cfg, today, publish=False)   ← 생성만 (LLM 1회 시도)
      ├─ (b) collect.publish_all_fortune_items(d, cfg, today, budget_seconds=잔여)  ← 항목별 결과 수집
      └─ (c) 응답 {created, published, failed, skipped, enabled, message, items[]}

  collect.py 신규 헬퍼 (FR-3 — 중복 구현 금지):
      _fortune_publish_candidates(today)      → 후보 목록 (기존 순회 목록과 동일)
      _fortune_publish_item_result(...)       → 항목 1건 처리 (기존 상태 갱신·로그 동일) + 결과 레코드
      publish_all_fortune_items(d, cfg, today, budget_seconds=None) → 항목별 결과 리스트 반환
  _publish_all_fortune(d, cfg, today)          → publish_all_fortune_items 호출로 위임 (동작 불변)
```

## 2. collect.py 리팩터링 설계 (FR-3 — 동작 불변 필수)

### 2.1 후보 목록 헬퍼 — `_fortune_publish_candidates(today)`
기존 `_publish_all_fortune`의 후보 구성 로직을 그대로 이동:
`daily_blog(당일)` + `weekly_blog(월요일)` + `monthly_blog(1일)` + `day_pillar_blog 01~60` + `zodiac_blog 01~12` + `animal_blog 01~12` → `(content_type, fortune_type, ref_key)` 튜플 리스트. **daily_sns는 후보에 없음** (AC-10).

### 2.2 항목 처리 헬퍼 — `_fortune_publish_item_result(d, cfg, ctype, ftype, ref_key)`
기존 판정 순서를 **그대로** 이식 (회귀 방지):
1. 행 없음/`content` 빈 문자열 → 스킵 ("콘텐츠 없음 (미생성)")
2. `status == "published"` → 스킵 ("이미 발행됨")
3. `status == "qc_failed"` → 스킵 ("검수 대기 (qc_failed)") — 수동 검토 대상 자동 발행 금지
4. content JSON 파싱 실패/`title` 없음 → 스킵 ("콘텐츠 형식 오류")
5. `publish_client.publish_fortune(...)` 성공 → `log_collection("publish")` + `{ok: true, status: "published"}`
6. `BlogPublishError` → `update_fortune_generation(status="publish_failed")` + `log_collection("error")` + `{ok: false, status: "failed", reason: ...}`

DB 상태 갱신·collection_log 기록은 **기존 코드와 동일 라인** — 리턴만 추가된다. (NFR-5)

### 2.3 결과 수집 헬퍼 — `publish_all_fortune_items(d, cfg, today, budget_seconds=None)`
- 후보 순회하며 2.2 호출, 결과 리스트 반환
- `budget_seconds` 지정 시 항목 처리 전 `time.monotonic()` 경과 검사 — 초과하면 **남은 후보 전부** `{ok: false, status: "skipped", reason: "시간 예산"}` (OQ-1)
- `budget_seconds=None`이면 기존과 동일한 무제한 순회 (기존 호출 경로 불변)
- **주의**: `blog_publish_enabled`/`blog_api_url` 검사는 기존처럼 `_publish_all_fortune`(및 엔드포인트)에서 수행 — 헬퍼는 발행 활성 상태에서만 호출 (기존 가드 위치 불변)

### 2.4 위임 — `_publish_all_fortune(d, cfg, today)`
```python
def _publish_all_fortune(d, cfg, today):
    if not cfg.get("blog_publish_enabled") or not cfg.get("blog_api_url"):
        return
    publish_all_fortune_items(d, cfg, today)   # 반환값 무시 — 기존 동작 동일
```
**동작 불변 증명**: test_fortune_publish.py 11건 전부 수정 없이 통과 (publish_failed 재시도·qc_failed 미발행·비활성 스킵·고정 콘텐츠 발행·weekly/monthly 등).

### 2.5 `fortune_generate_step` — 키워드 전용 파라미터 추가 (기본값 불변)
```python
def fortune_generate_step(d, cfg, today, *, publish=True):
    ...
    if publish:
        _publish_all_fortune(d, cfg, today)
    return created
```
- 기존 호출자(collect.run_collection·기존 테스트)는 기본값 True → **동작 100% 불변**
- 엔드포인트는 `publish=False`로 호출해 무예산 내부 발행을 건너뛰고, (b) 단계의 예산 적용 발행으로 단일화 (OQ-1 — 총 실행 60초 예산 통제)

## 3. publish_client.py — `BlogPublishError.status_code` (OQ-2)

```python
class BlogPublishError(Exception):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code
```
- `_post`의 모든 raise 지점에 `status_code=resp.status_code` 전달 (네트워크 오류는 None)
- **메시지 포맷 `HTTP {status}: {body[:120]}` 불변** (기존 테스트·로그 파서 호환 — NFR-5)
- 401(즉시 실패)·429(재시도 3회 후 최종 실패) 모두 status_code 보존 → 문자열 파싱 제거 (OQ-2 권장안)

## 4. 엔드포인트 설계 — `POST /fortune/publish`

### 4.1 라우트·인증·DB (v15 패턴 재사용)
- `create_app(cfg)` 내부에 추가, `dependencies=[Depends(require_token)]` (AC-2 — development 생략, 비개발 무토큰 401)
- DB: 기존 `run_db(fn)` 헬퍼 사용 (lock + CONNECTION_ERRORS 재연결) — cfg는 `create_app(cfg)` 클로저 그대로
- today: `config_mod.today_kst().isoformat()` (A-3 — KST)

### 4.2 동작 순서 (FR-1)
```python
FORTUNE_PUBLISH_BUDGET_SECONDS = 55   # 모듈 상수 — Vercel 60초 한도 대비 마진 5초 (테스트가 결정적 패치 가능)
@app.post("/fortune/publish", dependencies=[Depends(require_token)])
def fortune_publish():
    import collect, time as time_mod
    today = config_mod.today_kst().isoformat()
    started = time_mod.monotonic()
    enabled = bool(cfg.get("blog_publish_enabled") and cfg.get("blog_api_url"))
    def _run(d):
        try:
            created = collect.fortune_generate_step(d, cfg, today, publish=False)  # (a) 생성 — LLM 1회 시도
        except Exception as e:                                   # 생성 실패도 발행은 진행 (부분 수행)
            logger.warning("fortune generate step failed: %s", e); created = 0
        if not enabled:                                          # FR-4 — 발행 시도 0건
            return created, []
        remaining = max(0, FORTUNE_PUBLISH_BUDGET_SECONDS - int(time_mod.monotonic() - started))
        return created, collect.publish_all_fortune_items(d, cfg, today, budget_seconds=remaining)  # (b)
    created, items = run_db(_run)
    ... # (c) 응답 구성
```

### 4.3 응답 JSON 스키마 (AC-1)
```json
{
  "created": 2, "published": 1, "failed": 1, "skipped": 84,
  "enabled": true,
  "message": "발행 완료 — 성공 1건 / 실패 1건 / 스킵 84건 (생성 2건)",
  "items": [
    {"ref": "2026-08-13", "content_type": "daily_blog", "ok": true,  "status": "published", "reason": ""},
    {"ref": "01",         "content_type": "zodiac_blog", "ok": false, "status": "failed",   "reason": "HTTP 401 — 토큰 불일치 — autoblog DASHBOARD_TOKEN 확인 필요"},
    {"ref": "02",         "content_type": "zodiac_blog", "ok": false, "status": "skipped",  "reason": "시간 예산"},
    {"ref": "2026-08-13", "content_type": "daily_sns",   "ok": false, "status": "not_target", "reason": "발행 대상 아님 — SNS 요약은 발행 후보가 아님 (*_blog만)"}
  ]
}
```
- 집계: `published`=ok 건수, `failed`=status=="failed" 건수, `skipped`=status in ("skipped","not_target") 건수
- `message` — enabled=False: `"발행 비활성 — BLOG_PUBLISH_ENABLED=1 및 BLOG_API_URL 설정 필요"` (AC-9) / 예산 조기 종료 시 "시간 예산 초과 — 재클릭으로 이어서 발행" 문구 병기
- daily_sns 항목: 오늘자 daily_sns 행이 **존재할 때만** `not_target` 레코드 추가 (AC-10 — 구분 표시, 발행 시도 없음)

### 4.4 401/429 힌트 매핑 (AC-4·AC-5 — `status_code` 기반)
| status_code | reason |
|---|---|
| 401 | `HTTP 401 — 토큰 불일치 — autoblog DASHBOARD_TOKEN 확인 필요` |
| 429 | `HTTP 429 — 쿼터 소진 — autoblog Bailian token-plan 주간 쿼터 확인` |
| 기타(5xx·400 등) | 기존 메시지(`HTTP {status}: {body[:120]}`) 그대로 — 120자 이내 (A-5) |
| None(네트워크) | `network error: ...` (120자 이내) |

## 5. Vercel 60초 예산 정책 (OQ-1 확정 지침 반영)

| 단계 | 정책 |
|---|---|
| 생성 (a) | `fortune_generate_step` 재사용 — **LLM 생성 1회 시도/타입** (기존 구조 그대로 — 재시도 없음, 실패 시 부분 수행 후 발행 진행) |
| 발행 (b) | `budget_seconds = max(0, 55 - 경과)` — 항목 시작마다 경과 검사, 초과 시 **남은 후보 전부 `skipped("시간 예산")`** |
| 총합 | 55초 상한 (60초 서버리스 한도 - 5초 마진). 401(즉시 실패)·400(즉시 실패)은 항목당 ~1초로 빠르게 완료 — 실제 운영 실패(401) 시 예산 소진 없이 전 항목 실패 사유 수집 |
| 위험 고지 | LLM 키 있는 환경에서 생성 2회 호출이 55초를 넘으면 발행이 `시간 예산`으로 축소될 수 있음 — 버튼 재클릭(멱등)으로 이어서 처리 가능 (NFR-4 멱등: slug upsert + published 스킵) |

## 6. 대시보드 — static/index.html (FR-2)

- 상단바: "지금 수집 실행" 옆에 `<button class="btn btn-primary" id="fortuneBtn" onclick="publishFortune()">운세 발행</button>` (NFR-6 — `<button>`+라벨)
- `publishFortune()`: `fortuneBusy` 가드(진행 중 비활성 + "발행 중..." 표시, 기존 `collect()` 패턴 동일) → `api('/fortune/publish', {method:'POST', headers:authHeaders()})` (기존 헬퍼 재사용, 401 시 기존 "토큰이 올바르지 않습니다" 안내)
- 결과 렌더링 (`#fortunePanel` — 상단바 하단 인라인 카드, `renderFortuneResult`):
  - 요약: `setStatus("성공 N건 / 실패 N건 / 스킵 M건 (생성 C건)")`
  - 항목별: ref_date·content_type·상태 라벨(성공/실패/스킵/발행 대상 아님)·사유 (모두 `esc()` — XSS 방지, autoblog body 원문 포함 가능)
  - `enabled:false` → "발행 비활성 — BLOG_PUBLISH_ENABLED=1 필요" 안내 (AC-7 — 실패 처리 아님)
  - 실패 행은 warn 스타일, 401/429 사유는 서버 reason에 이미 포함된 힌트 문구 그대로 표시

## 7. 테스트 계획 (TDD — 신규만, 기존 수정 0)

| # | 파일 | 검증 |
|---|---|---|
| T1 | test_api.py | production 무토큰 → 401 (make_app(env="production") 패턴) |
| T2 | test_api.py | 후보 2건(200/401) → 200·items ok/실패 reason 401·서버 크래시 없음 |
| T3 | test_api.py | disabled → enabled:false+안내, publish 호출 0회 |
| T4 | test_api.py | LLM 키 없음+고정 미생성 → created>0 후 발행 (fortune_generate_step 경유) |
| T5 | test_fortune_publish.py | 헬퍼 혼합(200/401/429/5xx/qc_failed/published) → 항목별 상태·사유, daily_sns 비포함 |
| T6 | test_api.py | publish_failed 행 재발행 → published |
| T7+ | test_fortune_publish.py | budget_seconds=0 → 전 항목 skipped("시간 예산") |
| T8+ | test_publish_client.py | status_code (401/429/None) + 메시지 포맷 불변 |

테스트 픽스처: 기존 `make_app`/`_Resp`/`_cfg` 패턴 재사용, `monkeypatch.setattr(publish_client.requests, "post", ...)` + `publish_client.time.sleep` 패치(429 백오프), `llm_client.has_api_key` 패치.

## 8. 제약·리스크

| 항목 | 내용 |
|---|---|
| 기존 테스트 수정 금지 | 신규 추가만 — `_publish_all_fortune` 위임은 11건 회귀로 증명 |
| 재시도 정책 불변 | `publish_client._post` 429·5xx 백오프 3회 / 400·401 즉시 실패 — 신규 재시도 없음 |
| Vercel 60초 | 55초 예산 + skipped("시간 예산") — 멱등 재클릭으로 이어서 처리 |
| 실통신 불가 | autoblog 401(토큰 불일치) — 테스트는 전부 mock. 실패 사유 표시 로직이 실제 401을 우아하게 처리하는지가 QA 핵심 포인트 |
| AC-8 | server.py는 collect 헬퍼만 호출 — requests.post 직호출·후보 하드코딩·slug 재구현 부재를 코드 리뷰로 검증 |
