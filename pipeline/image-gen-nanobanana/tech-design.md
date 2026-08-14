# Google Nano Banana 이미지 생성 통합 — 기술 설계 (간이 tech-design, small 모드)

> 작성: 개발팀 · 프로젝트: autostudio · 상위: `requirements.md` FR-1~FR-6 + 오케스트레이터 승인 (FR-4 data URI 저장 기본 확정)
> 기준 코드: v26 (image_gen.py v8, llm_client.py v15, server.py v15.1 프록시, publish.py v19 플랫폼 export)
> 승인 게이트: **본 문서 승인 전 구현 금지**

## 1. 나노바나나 호출 설계 (FR-1, NFR-5·NFR-7)

### 1.1 엔드포인트·인증 (raw REST — SDK 미사용)

| 항목 | 값 |
|---|---|
| 엔드포인트 | `POST {GEMINI_BASE_URL}/v1beta/interactions` (기본 `https://generativelanguage.googleapis.com`) |
| 인증 | 헤더 `x-goog-api-key: $GEMINI_API_KEY` — `llm_client.post_json(headers=...)`로 전달 |
| 베이스 URL | `GEMINI_BASE_URL` env로 호출 시점 오버라이드 (NFR-7 — 테스트·차단 대응) |
| Bearer 정책 | `post_json`의 `Authorization`에는 **빈 키**를 전달 (`api_key=""`). API 키를 Bearer로 보내면 Google 게이트웨이가 OAuth 토큰으로 오판해 401 가능 → `x-goog-api-key` 단일 인증 유지 (리스크 §8) |
| 라이브러리 | 표준 라이브러리 urllib (llm_client 공용 레이어) — **외부 라이브러리 추가 0** (NFR-5) |

### 1.2 요청 본문 (AC1-2)

```json
{
  "model": "gemini-3.1-flash-image",
  "input": [{"type": "text", "text": "<기존 _build_prompt / section_image_prompt 결과>"}],
  "response_format": {
    "type": "image",
    "mime_type": "image/jpeg",
    "aspect_ratio": "16:9",
    "image_size": "1K"
  }
}
```

- `model`: 기본 `gemini-3.1-flash-image` (Nano Banana 2, 공식 go-to). `GEMINI_IMAGE_MODEL` env로 오버라이드 (AC1-4)
- `image_size`: 기본 `1K`. `GEMINI_IMAGE_SIZE` env로 2K/4K 오버라이드 허용 (비용 증가 명시 — AC4-6)
- `mime_type`: `image/jpeg` 고정 (PNG 대비 DB 용량 절감 — AC4-6)
- `aspect_ratio`: `16:9` 고정 (기존 1280*720과 동일 비율 — 블로그 레이아웃 호환, 요구사항 §11 가정 2)
- 프롬프트: `generate_image`의 `_build_prompt`(썸네일 콘셉트 포함) / `generate_section_images`의 `section_image_prompt`
  결과를 **그대로** 사용 — 재작성·강화 없음 (AC1-3, 제약 6)

### 1.3 응답 파싱 (AC1-6)

```json
{
  "steps": [
    {
      "content": [
        {"type": "text", "text": "..."},
        {"type": "image", "mime_type": "image/jpeg", "data": "<base64 바이트>"}
      ]
    }
  ]
}
```

- `steps[].content[]`를 순회해 `type == "image"` 블록의 `data`(base64) + `mime_type` 추출
- **SDK convenience 필드 `output_image`는 raw REST 응답에 없음 — 미사용** (요구사항 §2.2 실측)
- `mime_type` 누락 시 `image/jpeg` 기본값 (요청 mime 기준 — 응답이 PNG여도 응답의 mime_type 우선)
- 이미지 블록 없음 / 구조 불일치 → `ImageGenerationError("gemini image API bad response: ...")` (v26 파싱 정규화 패턴 동일)
- 반환값: `data:{mime_type};base64,{data}` 문자열 (FR-4, AC4-1)

### 1.4 시간 예산 (NFR-1)

- 타임아웃: 기존 `IMAGE_TIMEOUT=55` 단일 값 그대로 사용 (나노바나나 1차 + 폴백 합산 최대 ~110s — 배치 예산 1200s 내)
- **실측: 로컬에 GEMINI_API_KEY가 없어 1회 실측 불가** → QA 단계에서 첫 실통신 시 55s 내 완료 여부 확인 필요
  (thinking 모델 — 지연 초과 관측 시 대안 명시, §8)

## 2. `_run_http` 분기 설계 (FR-1·FR-2·FR-3)

```
_run_http(image_prompt, timeout)
  ├─ attempts += 1                                   (v26 위치 불변 — AC5-1)
  ├─ GEMINI_API_KEY 설정?
  │    ├─ YES → _nanobanana_generate()               ← 1차: 나노바나나
  │    │        ├─ 성공 → data URI 반환
  │    │        └─ 실패 → WARNING 로그 + Bailian(_primary_generate) 1회 재시도 (FR-3)
  │    │             ├─ 성공 → URL 반환 (최종 실패 아님 — AC3-5)
  │    │             └─ 실패 → 원인 포함 예외 재발생 (나노바나나 원인 병기 — AC3-4)
  │    └─ NO  → _primary_generate()                  ← 기존 경로 100% 불변 (AC2-1)
  ├─ 위 1차 실패 시 → _dashscope_fallback()          ← 기존 DashScope 폴백 재사용 (AC3-2)
  │        (DASHSCOPE_API_KEY 없으면 failures+1 후 원본 예외 재발생 — v26 그대로)
  └─ 성공 시 consecutive_failures = 0 (v26 위치 불변)
```

- **키 판정은 호출 시점 `os.getenv("GEMINI_API_KEY")` 평가** (DASHSCOPE_BASE_URL 패턴과 동일 — 테스트·런타임 반영)
- 나노바나나 실패 시의 Bailian 재시도는 `_nanobanana_generate` 내부에서 수행 —
  기존 `_dashscope_fallback` 시그니처·동작은 무변경 (폴백 체인 = 나노바나나 → Bailian → DashScope, 각 1회)
- 폴백 WARNING 로그 (AC3-4): 원본 실패 원인 + 사용 프로바이더 모델명 —
  `logger.warning("image API nano banana failed (%s) — retry via Bailian %s", err, IMAGE_MODEL)`
- stats (AC5-1/AC5-2): attempts는 `_run_http` 진입 시 1회 증가, failures·consecutive_failures는
  **최종 실패** 시에만 `_dashscope_fallback` 경로에서 증가 (v26 코드 위치·조건 불변 — 나노바나나 단독
  실패 + Bailian 성공은 집계 안 됨, AC3-5)

## 3. 키 가드 확장 (FR-6 — image_gen 내부만)

```python
def _has_image_api_key():
    return bool(os.getenv("GEMINI_API_KEY") or llm_client.has_api_key())
```

- `generate_image`·`generate_section_images` 진입부 가드를 위 내부 함수로 교체 (AC6-1)
- **`llm_client.has_api_key()`는 전역 불변** (AC6-4 — 초안 LLM·content_batch 생략 게이트 영향 0)
- 키 전체 미설정 시 메시지: `"이미지 키가 필요합니다 (BAILIAN_TOKEN_PLAN_API_KEY / DASHSCOPE_API_KEY / GEMINI_API_KEY)"`
  — 기존 테스트의 `"이미지 키"` substring 검증 유지 (AC2-2, AC6-3)
- ⚠️ `content_batch.run_content_batch`의 배치 생략 게이트는 `has_api_key()` 그대로 —
  GEMINI 키만 있는 환경에서는 배치가 생략되고, `generate_image` 직접 호출(서버리스/수동)만 동작
  (AC6-4 계약 — 배치 게이트 변경은 범위 외, report에 명시)

## 4. 저장 정합 — data URI (FR-4, AC4-1)

- 나노바나나 성공 반환: `data:{mime_type};base64,{data}` — `generate_image`의 `str` 반환 타입 불변
- `content_batch._create_draft` → `db.update_draft_image(draft_id, url, now)` /
  `db.update_draft_section_images(draft_id, json.dumps(urls), now)` — **호출부·SQL 무변경**
  (TEXT 컬럼에 문자열 그대로 저장 — SQLite/Postgres 공통, NFR-4)
- 용량: 1K 16:9 JPEG ≈ 150~400KB → base64 ≈ 200~530KB/장, 초안당 최대(대표1+섹션8) ≈ 2~5MB —
  `drafts` TEXT 컬럼 수용, 다운로드 프록시 상한 20MB 내 (수용)
- Bailian/DashScope 성공 시 **URL 저장 그대로** (data URI 변환 금지 — AC4-5, 혼합 저장 허용)

## 5. 소비처 3종 처리 방침 (오케스트레이터 승인 사항)

### ① `server.py` `/drafts/{id}/image-download` 프록시 — data URI 분기 **추가** (AC4-3)

- `_fetch_image_bytes(url)` 선두에 `url.startswith("data:")` 분기 추가:
  - 파싱: `data:{mime};base64,{b64}` → `base64.b64decode` → (바이트, mime)
  - 검증: MIME이 `image/` 계열인지, 디코드 실패 시 400, 크기 > `IMAGE_DOWNLOAD_MAX_BYTES`(20MB) 시 502
  - HTTPS 가드·리다이렉트·스트리밍 경로는 **기존 그대로** (URL 기반 이미지 회귀 0)
- 처리하지 않을 경우의 영향: data URI 이미지의 다운로드 버튼이 400("HTTPS 이미지 URL이 아닙니다")으로
  실패 → 대표·섹션 다운로드 불능 → **분기 추가로 해소** (권장안 채택)

### ② `publish.py` 마크다운 내보내기 — data URI **생략 + 경고 주석** (AC4-4, 권장안 채택)

- `_image_lines(draft, marker, label)`에서 URL이 `data:`로 시작하면 이미지 라인을 **내보내지 않고**
  대신 경고 주석 삽입:
  - 대표: `<!-- 대표 이미지: data URI (에디터 임포트 미지원) — 블로그 에디터에서 직접 업로드하세요 -->`
  - 섹션: `<!-- 섹션 이미지 N: data URI (에디터 임포트 미지원) — 블로그 에디터에서 직접 업로드하세요 -->`
- 이유: 티스토리/애드센스/브랜드 에디터 임포트는 마크다운 `![...](data:...)`를 지원하지 않을 가능성이
  높아, 길이 수 KB~MB의 data URI가 본문에 그대로 삽입되는 것보다 **생략+안내**가 운영상 안전
  (사용자가 수동 업로드 — 요구사항 §6 권장안)
- **네이버 플레인 경로는 `_image_lines`를 호출하지 않음** (실측: `_export_naver`에 이미지 임베드 없음) — 무영향
- URL 기반 이미지(기존 Bailian/DashScope)는 기존대로 `![...](url)` 임베드 (기존 테스트 불변)

### ③ 대시보드 `static/index.html` — data URI 렌더링 **확인만** (AC4-2)

- `showDraftImage`/`showSectionImages`: `<img src="${esc(url)}">` — 브라우저 `<img>`는 data URI를
  기본 지원. `esc()`는 HTML 엔티티 이스케이프인데 base64 알파벳(`A-Za-z0-9+/=`)과 `data:image/jpeg;base64,`
  접두어에는 HTML 특수문자(`& < > " '`)가 없어 무해 → **코드 변경 0**
- 다운로드 버튼은 ①의 프록시 분기로 data URI도 동작

## 6. env · 워크플로우 · 문서 반영

| 항목 | 내용 |
|---|---|
| `.env.example` | `GEMINI_API_KEY=` (선택 — 미설정 = 기존 동작), `GEMINI_IMAGE_MODEL=gemini-3.1-flash-image`, `GEMINI_IMAGE_SIZE=1K`, `GEMINI_BASE_URL=` (선택) |
| `daily-collect.yml` | `GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}` (미등록 시 env 미설정 = 기존 체인 — 무해) |
| `02-trd.md` | 이미지 생성 섹션에 나노바나나 1차·폴백 체인·data URI 저장·모니터링 반영 |
| `CHANGELOG.md` | v27 항목 |

## 7. 테스트 설계 (TDD — tests/test_image_gen.py 신규 7건, 기존 8건 수정 금지)

| # | 테스트 | mock 구성 | 검증 |
|---|---|---|---|
| T1 | `test_nanobanana_success_returns_data_uri` | `llm_client.post_json` → steps[image 블록] 응답 | 반환값 `data:image/jpeg;base64,...` (AC4-1), 요청 URL에 `/v1beta/interactions`, 본문에 `response_format` 4필드 (AC1-2), 헤더에 `x-goog-api-key` (AC1-6 파싱) |
| T2 | `test_nanobanana_no_bailian_calls_and_prompt` | post_json 성공 | Bailian/DashScope 호출 0회 (AC1-1), 프롬프트에 `_SINGLE_SCENE_RULES` 포함 (AC1-3) |
| T3 | `test_no_gemini_key_uses_bailian_primary` | GEMINI 키 미설정, post_json → Bailian 응답 | 나노바나나 0회, Bailian 1차 (AC2-1), 키 전체 미설정 시 기존 메시지 (AC2-2) |
| T4 | `test_nanobanana_fail_falls_back_to_bailian` | GEMINI 키 설정, post_json 1회차 raise → 2회차 Bailian 성공 | Bailian 정확히 1회 (AC3-1), URL 반환·집계 0 (AC3-5), WARNING 로그 (AC3-4) |
| T5 | `test_nanobanana_bailian_fail_dashscope_fallback` | GEMINI·Bailian·DashScope 키 설정, 전부 실패 | DashScope 1회 (AC3-2), `ImageGenerationError` + failures/consecutive 집계 (AC3-3, AC5-2) |
| T6 | `test_gemini_key_only_guard_and_model_override` | GEMINI 키만 설정, post_json 성공 + `GEMINI_IMAGE_MODEL` 설정 | 가드 통과 (AC6-1), 요청 model 오버라이드 (AC1-4) |
| T7 | `test_data_uri_parse_and_fallback_log` | 성공 응답 → data URI → `base64.b64decode` 복원 검증 | `data:{mime};base64,{data}` 파싱 (AC4-1), T4와 함께 폴백 WARNING 로그 캡처 (AC3-4) |

- 기존 8건: v26 폴백 T1~T3 포함 **수정 금지** — 전부 통과해야 함
- `tests/test_content_batch.py` 11건: **수정 금지** (AC5-3/AC5-4)
- 검증 게이트: `./.venv/Scripts/python.exe -m pytest -q` → 기존 388 + 신규 7 = **395 passed / 10 skipped**

## 8. 리스크·미검증 항목

| 리스크 | 판정·대응 |
|---|---|
| ① `Authorization: Bearer `(빈 값) 병행 — 게이트웨이가 거부할 가능성 | 빈 Bearer는 미인증으로 처리되는 것이 일반적 (ESPv2 계열). **실통신 확인 필수** — 거부 관측 시 `llm_client._browser_headers`에 빈 키 스킵 가드 1줄 추가 (후속 조치, 이번 범위의 최소 변경 유지) |
| ② 나노바나나 1K 16:9 55s 내 완료 미실측 (키 부재) | 실측 불가 — QA 첫 실통신 시 확인. 초과 시 **thinking 최소화 옵션**: 요청에 thinking 레벨 축소(`thinking_level: "minimal"`) 또는 `generateContent` 엔드포인트 대안 검토 (NFR-1, 구현 시점 결정 사항으로 유보) |
| ③ data URI DB 용량 | JPEG 1K 기본 + 초안당 ~2~5MB 수용 (스키마 무변경) |
| ④ 나노바나나 응답이 `mime_type` 미포함 | `image/jpeg` 기본값 (요청 기준) |
| ⑤ GEMINI 키만 있는 환경에서 content_batch 생략 | AC6-4 계약 유지 — 배치 게이트 변경은 범위 외 (report에 명시) |
| ⑥ 모델 env를 호출 시점 평가 → 테스트 간 env 누수 | monkeypatch.setenv 기반 테스트 — 각 테스트가 독립 설정 |

## 9. 구현 순서 (승인 후)

1. TDD — 신규 7건 테스트 작성 → 실패 확인
2. `image_gen.py` 구현 (상수·파서·나노바나나 경로·가드·분기)
3. `server.py` data URI 분기 · `publish.py` 생략+주석
4. 문서 4종 (.env.example·workflow·02-trd.md·CHANGELOG)
5. 전체 pytest 통과 확인 (fable-prove-it)
6. `implementation-report.md/html` 작성 → 요약 답신
