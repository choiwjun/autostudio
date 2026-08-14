# 이미지 생성 프로바이더 — Google Nano Banana 통합 요구사항 명세

> 작성: 요구사항팀 · 프로젝트: autostudio · 작업 디렉토리: `pipeline/image-gen-nanobanana/`
> 원본 요청: 사용자가 **이미지 생성을 Google Nano Banana(Gemini 이미지 모델)로 사용** 결정 — "내가 우선은 이미지생성하는걸로할게 — 계속 진행해"
> 실측 기준: v26 코드(2026-08-13) + Google 공식 문서(ai.google.dev, 2026-08-13 크롤링 실측)

## 1. 배경 (실측 현황)

| 항목 | 실측 결과 (2026-08-13) |
|---|---|
| 현재 이미지 파이프라인 (v26) | `image_gen.py`: Bailian(Token Plan, `wan2.7-image`, `1280*720`) 1차 → 실패 시 DashScope(`wanx2.1-t2i-turbo` 비동기) 1회 폴백. 실패 집계(`_IMAGE_STATS`) + 임계 초과 시 `collect.py` exit 1 → GH Actions 잡 실패 알림 (FR-4/FR-5) |
| 호출 구조 | `generate_image()`(대표) / `generate_section_images()`(섹션 최대 8장) → 공통 `_run_http()` → `_primary_generate()`(Bailian) → `_dashscope_fallback()`(선택). public 시그니처: `generate_image(...) -> str(URL)` |
| 키 가드 | `llm_client.has_api_key()` = `BAILIAN_TOKEN_PLAN_API_KEY` 또는 `DASHSCOPE_API_KEY` 존재 시 True. 미설정 → `ImageGenerationError("이미지 키가 필요합니다 ...")` (텍스트 흐름 유지). **이 가드는 초안 LLM·배치 생략 판정에도 사용되므로 전역 변경 금지** |
| 저장 구조 | `drafts.image_url TEXT NOT NULL DEFAULT ''`(대표 1장, URL 문자열) + `drafts.section_images TEXT`(JSON 배열 — URL 문자열). SQLite/Postgres 2 dialect, **DB 스키마 대변경은 비용 큼** |
| image_url 소비처 | ① 대시보드 `static/index.html` — `<img src="${esc(url)}">` (data URI 렌더링 호환 — 브라우저 기본 지원) ② `server.py` `/drafts/{id}/image-download` 프록시 — `_fetch_image_bytes()`가 **HTTPS URL만 허용** (data URI는 현재 거부됨) ③ `publish.py` 마크다운 내보내기 — 티스토리/애드센스/브랜드에 `![...](image_url)` 임베드 (네이버는 플레인 텍스트 — 이미지 미사용) |
| 배치 환경 | GH Actions `daily-collect.yml` — env로 `BAILIAN_TOKEN_PLAN_API_KEY`·`OPENCODE_GO_API_KEY` 등 주입. `content_batch.run_content_batch()`가 백필+신규 생성 후 결과 dict(`image_attempts`·`image_failures`·`image_alert`) 반환 |
| 테스트 | 현재 **398개 수집**, `tests/test_image_gen.py` 8건 통과 (v26 폴백 T1~T3 포함), `tests/test_content_batch.py` 11건 (알림 임계 T4/T5 포함) |

## 2. Google Nano Banana 공식 문서 실측 (2026-08-13, ai.google.dev/gemini-api/docs/image-generation·pricing·interactions-api)

### 2.1 모델 4종 (모두 GA·유료 전용 — **무료 티어 없음** 실측 확인)

| 모델 | 이름 | 이미지당 비용 (유료) | 해상도 | 16:9 지원 | 비고 |
|---|---|---|---|---|---|
| `gemini-2.5-flash-image` | Nano Banana (레거시) | ~$0.0195–0.039 | 1024px(1K) | ✅ 1344×768 | 공식 문서가 **3.1로 이전 권장** |
| `gemini-3.1-flash-lite-image` | Nano Banana 2 Lite | ~$0.0168–0.0336 (1K) | **1K 전용** | ✅ (1:1·3:2·2:3·3:4·4:3·4:5·5:4·9:16·16:9·21:9) | 최속·최저가. 다중 참조/멀티턴 편집 비최적화 (본 과제는 단일 text→image라 무관) |
| `gemini-3.1-flash-image` | Nano Banana 2 | ~$0.034–0.067 (1K) / $0.101(2K) / $0.151(4K) | 0.5K/1K/2K/4K | ✅ 1K=1376×768, 2K=2752×1536 | **공식 "go-to" 만능 모델** (비용·속도·품질 균형). thinking 기본(minimal) |
| `gemini-3-pro-image` | Nano Banana Pro | ~$0.134 (1K/2K) / $0.24 (4K) | 1K/2K/4K | ✅ | 최고 품질·프로 자산용 — 블로그 삽화에 과분·비용 2~4배 |

> 사용자 확인 가격(~$0.017~0.076/이미지)과 실측 일치: Lite 1K ≈ $0.0168~0.0336, Flash 1K ≈ $0.034~0.067, Flash 4K ≈ $0.076(할인 티어). **무료 사용은 웹(AI Studio)에서만 가능** — API는 유료, 결제 수용 확정.

### 2.2 REST 계약 (Interactions API — 공식 권장, GA)

- 엔드포인트: `POST https://generativelanguage.googleapis.com/v1beta/interactions`
- 헤더: `x-goog-api-key: $GEMINI_API_KEY` + `Content-Type: application/json`
- 요청 본문:
```json
{
  "model": "gemini-3.1-flash-image",
  "input": [{"type": "text", "text": "<프롬프트>"}],
  "response_format": {
    "type": "image", "mime_type": "image/jpeg",
    "aspect_ratio": "16:9", "image_size": "1K"
  }
}
```
- 응답: `steps[].content[]` 배열에서 `type == "image"` 블록의 **`data`(base64 인코딩 바이트) + `mime_type`** (예: `image/png`, `image/jpeg`). SDK convenience 필드 `output_image`는 **SDK가 추가하는 값 — raw REST 응답에는 없음** → steps 순회 파싱 필요
- **⚠️ 핵심: API는 이미지 URL이 아닌 base64(inline)를 반환한다 (공식 예제: `base64.b64decode(content_block.data)` → 파일 저장)** — 현행 DB의 `image_url`(URL 문자열)과 정합 방안이 필요 (§6 FR-4)
- 모든 생성 이미지에 SynthID 워터마크 포함 (비가시 — 블로그 사용 무해, 사실로 기록)
- 한국(대한민국) 공식 지원국 목록 포함 ✅ — 리전 제약 없음
- `responseModalities`는 Interactions API에서 **deprecated** (신규 코드는 `response_format` 사용)

## 3. 목표 & 비목표

### 목표
1. `GEMINI_API_KEY`가 설정된 환경에서는 **나노바나나를 이미지 생성 1차 프로바이더**로 사용 — 실패 시 기존 체인(Bailian → DashScope) 폴백 (사용자 우선 사용 의도 반영)
2. `GEMINI_API_KEY` 미설정 환경에서는 **기존 동작 100% 불변** + 기존 테스트 전부 통과 (v26 FR-2 graceful 패턴 동일)
3. 나노바나나의 base64 응답을 현행 `image_url`/`section_images` 저장 구조와 **정합시키는 방안 확정** (기본 권장: data URI 저장 — 인프라 신설 없음)
4. v26 실패 집계·알림(시도/최종 실패/연속 실패 → `image_alert` → GH Actions)을 나노바나나 경로에도 **동일 적용**
5. 비용 통제 — 기본 1K·16:9·JPEG, 모델 env 오버라이드(`GEMINI_IMAGE_MODEL`)

### 비목표
- DB 스키마 대변경 / 신규 스토리지 인프라 신설 — **기본 범위 제외** (비용 큼, §6 FR-4 트레이드오프로만 기록)
- 서버리스 수동 생성(`server.py` `/drafts/{id}/image`)의 나노바나나 전환 — v26과 동일하게 **범위 제외** (배치 기준)
- Slack·이메일 등 별도 알림 채널 — **범위 제외** (기존 GH Actions 실패 전파 유지)
- Imagen·Veo·DALL-E 등 타 이미지 모델 도입 — **범위 제외**
- 프롬프트 재작성 — `_SINGLE_SCENE_RULES`(실사·16:9·단일 장면) **재사용 전제** (사용자 의도·기존 품질 기준 유지)

## 4. 타깃 (영향 파일)

| 파일 | 변경 성격 |
|---|---|
| `image_gen.py` | 나노바나나 1차 경로 추가 (`_nanobanana_generate` + `_run_http` 분기) — public 시그니처 불변 |
| `tests/test_image_gen.py` | 나노바나나 경로 테스트 6~7건 추가 (기존 8건 수정 금지) |
| `.env.example` | `GEMINI_API_KEY`·`GEMINI_IMAGE_MODEL`·`GEMINI_IMAGE_SIZE`·`GEMINI_BASE_URL` 옵션 추가 |
| `.github/workflows/daily-collect.yml` | `GEMINI_API_KEY` secret env 추가 (미설정 시 무해) |
| `server.py` | (tech-design 확정 시) 다운로드 프록시 data URI 지원 — 최소 변경 |
| `docs/planning/02-trd.md` | 이미지 섹션에 나노바나나 반영 |
| `CHANGELOG.md` | 갱신 |

## 5. 용어

| 용어 | 정의 |
|---|---|
| 나노바나나(Nano Banana) | Google Gemini 이미지 생성 모델군. 기본 모델: `gemini-3.1-flash-image` |
| 1차 프로바이더 | `GEMINI_API_KEY` 설정 시 최초 호출 대상 (나노바나나). 미설정 시 기존 Bailian |
| 폴백 체인 | 나노바나나 실패 → Bailian(`wan2.7-image`) → DashScope(`wanx2.1-t2i-turbo`) 순 1회씩 |
| 최종 실패 | 폴백 포함 최종 시도까지 실패한 이미지 생성 호출 (v26 정의 유지 — 실패 집계 대상) |
| data URI | `data:{mime_type};base64,{base64 데이터}` 형태의 인라인 이미지 문자열 (URL 아님) |
| 시도(attempt) | 이미지 생성 호출 1회 (키 미설정 가드에서 중단되는 경우 제외 — v26 정의 유지) |

## 6. 기능 요구사항 (FR)

### FR-1 — 나노바나나 1차 프로바이더 전환 (M)
`GEMINI_API_KEY`가 설정된 환경에서 이미지 생성(대표·섹션·백필 전 경로)은 나노바나나를 **최초 호출**한다. 기본 모델 `gemini-3.1-flash-image`(Nano Banana 2, 공식 go-to 모델 — 비용·속도·품질 균형), 16:9·1K·JPEG 요청. 모델은 `GEMINI_IMAGE_MODEL` env로 오버라이드 가능.

**수용 기준 (검증 가능)**
- [ ] AC1-1: `GEMINI_API_KEY` 설정 + 나노바나나 성공 → 성공 이미지가 반환되고, **Bailian·DashScope 호출은 0회** (1차 사용 확인)
- [ ] AC1-2: 요청 본문에 `response_format: {type:"image", mime_type:"image/jpeg", aspect_ratio:"16:9", image_size:"1K"}`가 포함된다 (블로그 16:9 가로 사진 요구 충족 — 기존 `1280*720`은 나노바나나에 없는 규격, 비율 16:9로 대체. 1K 16:9 = 1376×768)
- [ ] AC1-3: 요청 본문의 프롬프트는 기존 `_build_prompt`/`section_image_prompt` 결과(즉 `_SINGLE_SCENE_RULES` 포함)를 그대로 사용한다 (프롬프트 재작성 없음)
- [ ] AC1-4: `GEMINI_IMAGE_MODEL=gemini-3.1-flash-lite-image` 설정 시 해당 모델로 요청된다 (env 오버라이드 동작)
- [ ] AC1-5: 나노바나나 경로도 대표·섹션 이미지 **모두**에 적용된다 (`generate_image` + `generate_section_images` — 공통 `_run_http` 분기, v26과 동일한 단일 구현 지점)
- [ ] AC1-6: 응답 파싱은 `steps[].content[]`에서 `type=="image"` 블록의 `data`(base64)와 `mime_type`을 추출한다 (raw REST — SDK convenience `output_image` 미사용)

### FR-2 — GEMINI_API_KEY 미설정 시 기존 동작 100% 불변 (M)
`GEMINI_API_KEY`가 없으면 나노바나나 코드 경로가 **실행되지 않는다** — 기존 Bailian 1차 → DashScope 폴백 체인이 변경 전과 동일하게 동작.

**수용 기준**
- [ ] AC2-1: `GEMINI_API_KEY` 미설정 + Bailian 실패 → 나노바나나 호출 0회, 기존 DashScope 폴백만 동작 (AC1-1/AC1-4 테스트와 env 전환 검증)
- [ ] AC2-2: 키 전체 미설정 시 기존 `ImageGenerationError("이미지 키가 필요합니다 ...")` 가드·메시지가 유지된다 (`tests/test_image_gen.py::test_no_key_raises_clear_error` 계속 통과)
- [ ] AC2-3: **기존 테스트 398개 전부 통과** (신규 테스트 제외 — 회귀 없음)
- [ ] AC2-4: `GEMINI_API_KEY`만 설정된 환경에서는 나노바나나로 정상 생성된다 (FR-6 참조 — 키 가드 확장 필요)

### FR-3 — 나노바나나 실패 시 기존 체인 폴백 (M)
나노바나나 호출이 실패(HTTP 4xx/5xx·타임아웃·네트워크·응답 파싱 실패 모두)하면 기존 체인(Bailian → DashScope)으로 폴백한다. 각 폴백 시도는 1회로 제한 (v26 규칙 유지).

**수용 기준**
- [ ] AC3-1: 나노바나나 실패 + `BAILIAN_TOKEN_PLAN_API_KEY` 설정 → Bailian이 정확히 1회 호출된다. Bailian 성공 시 그 URL이 반환·저장된다
- [ ] AC3-2: 나노바나나·Bailian 실패 + `DASHSCOPE_API_KEY` 설정 → DashScope 폴백 1회가 동작한다 (기존 v26 폴백 로직 재사용)
- [ ] AC3-3: 전 경로 실패 → 기존과 동일하게 `ImageGenerationError`가 전파되고 메시지에 최종 실패 원인이 포함된다 (`content_batch` 키워드 단위 격리 동작 회귀 없음)
- [ ] AC3-4: 폴백 발생 시 WARNING 로그에 원본 실패 원인(나노바나나 예외)과 사용 프로바이더가 기록된다 (디버깅 가능성, v26 AC1-4 패턴)
- [ ] AC3-5: 나노바나나 실패→Bailian 성공은 **최종 실패로 집계되지 않는다** (v26 "최종 실패" 정의 유지 — 성공이면 연속 실패 리셋)

### FR-4 — base64 응답 저장 정합 (M) — ⭐ 핵심 설계 포인트
나노바나나는 URL이 아닌 **base64 인라인 데이터**를 반환한다. 현행 `drafts.image_url`(URL 문자열)·`section_images`(URL 배열) 구조에 정합시키는 방안을 확정한다.

**후보 (요구사항팀 실측 기반, 개발팀이 tech-design에서 확정):**

| 방안 | 내용 | 장점 | 단점/리스크 |
|---|---|---|---|
| **① data URI 저장 (기본 권장)** | `data:{mime};base64,{data}`를 `image_url`·`section_images`에 저장. 스키마 변경 없음 (TEXT 그대로) | 인프라 신설 0, DB 무변경, 대시보드 `<img src>` 렌더링 호환 (브라우저 기본 지원) | ① `server.py` 다운로드 프록시가 HTTPS URL만 허용 → data URI 지원 확장(소규모) 필요 ② DB 용량 증가: 1K 16:9 JPEG ≈ 150~400KB → base64 ≈ 200~530KB/장, 초안당 최대(대표1+섹션8) ≈ 2~5MB ③ `publish.py` 마크다운의 data URI는 티스토리/애드센스 에디터 임포트에서 미지원 가능성 (수동 이미지 업로드로 대체 필요. 네이버 플레인 경로는 이미지 미사용이라 무영향) |
| ② 외부 업로드 (Supabase Storage/GitHub raw/Vercel Blob 등) | base64를 업로드해 진짜 URL 획득 후 기존 형식 그대로 저장 | 전 소비처(프록시·publish) 무변경, 진짜 URL | **스토리지 신설·운영·비용·청소 로직** — 오케스트레이터 지침 "스토리지 신설은 비용이 크다"와 상충. 사용자 승인 필요 |
| ③ DB 컬럼 신설 (`image_data` 등) | base64 전용 컬럼 추가 | 저장 형식 분리 명확 | 스키마 마이그레이션(SQLite+Postgres 2 dialect)·조회/백필 SQL 변경 — **비권장** (비용 대비 이득 낮음) |

**수용 기준**
- [ ] AC4-1: 나노바나나 성공 시 반환값은 `data:{mime_type};base64,{data}` 형태 문자열이며, `generate_image`의 반환 타입(`str`)은 유지된다 — `content_batch`·`db.update_draft_image`·`update_draft_section_images` 호출부는 변경 없이 저장된다
- [ ] AC4-2: 대시보드(`static/index.html`)에서 data URI 이미지가 정상 표시된다 (브라우저 `<img>` data URI 지원 확인)
- [ ] AC4-3: `server.py` 다운로드 프록시가 data URI를 처리한다 (tech-design에서 확정 — HTTPS URL 강제 가드에 data URI 분기 추가 권장, 최소 변경). 처리하지 않는 경우 그 영향(다운로드 버튼 불능)을 tech-design에 명시
- [ ] AC4-4: `publish.py` 마크다운 내보내기의 data URI 처리 방침이 tech-design에 명시된다 (권장: 경고 주석/생략 — 사용자가 수동 업로드. 네이버 플레인 경로 무영향 확인)
- [ ] AC4-5: 기존 URL 기반 프로바이더(Bailian·DashScope) 성공 시에는 **기존 URL 저장 형식 그대로** (data URI로 변환 금지) — 혼합 저장이어도 소비처가 양쪽 모두 처리
- [ ] AC4-6: (비용 통제) 요청 `mime_type`은 `image/jpeg` 기본 — PNG 대비 DB 용량 절감. `image_size`는 `1K` 기본 (2K/4K는 env 오버라이드 허용, 비용 증가 명시)

### FR-5 — 실패 집계·알림 동일 적용 (M)
v26 FR-4/FR-5(시도/최종 실패/연속 실패 집계 → 연속 5건 또는 시도 5건+ 실패율 50% 초과 시 `image_alert` → `collect.py` exit 1 → GH Actions 실패)를 나노바나나 경로에 **동일 적용**한다.

**수용 기준**
- [ ] AC5-1: `_IMAGE_STATS["attempts"]` 증가는 `_run_http` 진입 시 1회 (나노바나나 경로 포함 — 기존 위치 불변)
- [ ] AC5-2: 최종 실패(나노바나나+Bailian+DashScope 전부 실패) 시 `failures`·`consecutive_failures` 증가 — 나노바나나 단독 실패(Bailian 성공)는 집계 안 됨 (AC3-5와 일치)
- [ ] AC5-3: 임계 초과 시 기존과 동일하게 ERROR 로그 + 결과 dict `image_alert: True` → `collect.py` exit 1 (GH Actions 잡 실패 전파 — 나노바나나 키/쿼터 점검 안내 메시지 포함)
- [ ] AC5-4: `reset_image_stats`/`get_image_stats` 시그니처·동작 불변 — `tests/test_content_batch.py` 알림 테스트 3건(T4/T5 계열) 수정 없이 통과

### FR-6 — GEMINI_API_KEY만 설정된 환경 지원 (S)
`GEMINI_API_KEY`만 있고 Bailian/DashScope 키가 없는 환경에서도 이미지 생성이 동작해야 한다 (현재 키 가드는 Bailian/DashScope 키만 인정 → 나노바나나 도입 후 가드 확장 필요). 단, `has_api_key()`는 초안 LLM·배치 생략 판정에 쓰이므로 **전역 변경 금지** — `image_gen.py` 내부 가드만 확장.

**수용 기준**
- [ ] AC6-1: `GEMINI_API_KEY`만 설정 + 나노바나나 성공 → 정상 반환 (가드 통과)
- [ ] AC6-2: `GEMINI_API_KEY`만 설정 + 나노바나나 실패 → 기존 체인에 키가 없으므로 `ImageGenerationError` 전파 (최종 실패 집계) — 서버 500·배치 격리 동작 정상
- [ ] AC6-3: 키 전부 미설정 시 기존 오류 메시지 유지 (AC2-2). 메시지에 GEMINI 키 안내를 추가하는 것은 허용 (기존 테스트 `"이미지 키"` substring 검증 유지 확인)
- [ ] AC6-4: `llm_client.has_api_key()`의 동작(텍스트 LLM·content_batch 게이트)은 변경되지 않는다

## 7. 비기능 요구사항 (NFR)

| ID | 영역 | 요구사항 |
|---|---|---|
| NFR-1 | 성능 | 이미지 1건 타임아웃 기존 55s 유지 (나노바나나 1차 + 폴백 포함 최대 ~110s — 배치 예산 1200s·GH Actions 60분 내). 나노바나나 1K 16:9 응답이 55s 내 완료되는지 구현 시 1회 실측 (thinking 모델 — 지연 초과 시 `thinking_level` 최소화 또는 generateContent 대안 검토) |
| NFR-2 | 비용 | 기본 `gemini-3.1-flash-image` 1K ≈ $0.034~0.067/장 (사용자 수용 범위 $0.017~0.076 내). Lite 전환(`GEMINI_IMAGE_MODEL`) 시 ~$0.017~0.034로 절반. 2K/4K는 env 오버라이드로만 (비용 증가 명시). Grounding(google_search) 미사용 → 검색 과금 없음 |
| NFR-3 | 보안 | 키는 환경변수로만 관리 (기존 패턴), 로그·오류 메시지에 키 값 미포함, GH Actions secret으로만 주입, 프론트 노출 없음 |
| NFR-4 | 호환 | 기존 public API 시그니처·반환형 불변, 기존 테스트 398개 전부 통과, SQLite·Postgres 양쪽 저장 경로 동작 |
| NFR-5 | 의존성 | **외부 라이브러리 추가 금지** — 표준 라이브러리 `urllib` 유지 (Interactions API는 단순 REST POST — `llm_client.post_json` 재사용, `x-goog-api-key` 헤더는 기존 headers 파라미터로 전달) |
| NFR-6 | 운영 | 알림은 하루 1회(GH Actions 일일 배치) 기준 — 실시간 아님 명시 (v26 유지). 실패 집계는 `collection_runs.result`에 기록 (v26 유지) |
| NFR-7 | 지역 | 대한민국 공식 지원 (available-regions 실측 포함) — 리전 이슈 없음. `GEMINI_BASE_URL` env 오버라이드로 엔드포인트 변경 가능하게 설계 (테스트·차단 대응) |

## 8. 제약

1. **DB 스키마 대변경·스토리지 신설은 비용이 크다** (오케스트레이터 지침) — FR-4 기본안은 ① data URI 저장 (무인프라). ② 외부 업로드는 사용자/오케스트레이터 승인 필요
2. 외부 라이브러리 추가 금지 (NFR-5)
3. `llm_client.has_api_key()` 전역 변경 금지 — 이미지 가드는 image_gen 내부에서만 확장 (FR-6)
4. 서버리스 수동 생성 경로 범위 제외 (v26 결정 유지)
5. TDD — 테스트를 먼저 작성하고 구현
6. 프롬프트는 `_SINGLE_SCENE_RULES` 재사용 (재작성·강화 금지 — 기존 품질 기준 유지)

## 9. 우선순위 (M/S/C)

| 우선순위 | 항목 |
|---|---|
| **M (Must)** | FR-1 나노바나나 1차 전환(16:9·1K·JPEG·모델 기본), FR-2 미설정 불변+기존 테스트 398개 통과, FR-3 폴백 체인, FR-4 저장 정합(data URI 기본), FR-5 집계·알림 동일 적용, 테스트 6~7건, 문서 반영(.env.example·GH workflow·02-trd.md·CHANGELOG) |
| **S (Should)** | FR-6 GEMINI 키만 있는 환경 지원, AC4-3 다운로드 프록시 data URI 처리, AC3-4 폴백 WARNING 로그, GEMINI_IMAGE_SIZE 오버라이드 |
| **C (Could)** | 방안 ② 외부 업로드(사용자 승인 시 후속), Lite 모델 기본 전환·2K/4K 활용(비용 재평가 후), 대시보드 이미지 크기·용량 표시 개선 |

## 10. 성공 기준 (종합)

1. **GEMINI_API_KEY 설정 환경**: 대표·섹션 이미지가 나노바나나(1차)로 생성·저장되고, 실패 시 Bailian→DashScope 폴백이 동작한다. 생성 이미지는 대시보드에 표시된다
2. **GEMINI_API_KEY 미설정 환경**: 동작이 변경 전과 100% 동일하고, 기존 테스트 398개 전부 통과한다
3. **전 프로바이더 실패**: v26과 동일하게 `ImageGenerationError` 전파 + 실패 집계 → 임계 초과 시 `image_alert` → GH Actions 잡 실패로 운영자 인지
4. **저장 정합**: 나노바나나 base64 이미지가 `image_url`/`section_images`에 저장되어 대시보드·다운로드·발행 내보내기 소비처가 명시된 방침대로 동작한다 (tech-design에 방침 기록)
5. **비용 통제**: 기본 1K·16:9·JPEG로 이미지당 $0.034~0.067 (사용자 수용 범위), 모델·크기 env 오버라이드 가능

## 11. 오픈 질문 · 가정

### 해소된 결정 (사용자 승인 완료 — 인터뷰 생략 사유)
| 질문 | 결정 |
|---|---|
| 나노바나나 사용 여부 | **사용** — 이미지 생성 1차 프로바이더 ("이미지생성하는걸로할게") |
| 무료 티어 없음(유료, ~$0.017~0.076/이미지) 수용 | **수용 확정** (결제) — 무료는 웹 AI Studio에서만 |
| GEMINI_API_KEY 미설정 시 동작 | 기존 체인 100% 불변 (graceful — v26 FR-2 패턴) |
| 프롬프트 | `_SINGLE_SCENE_RULES` 재사용 (재작성 없음) |
| 실패 집계·알림 | 나노바나나 경로에도 동일 적용 (v26 FR-4/5 유지) |

### 오픈 질문 (구현 시 확정)
| 질문 | 소유자 | 상태 |
|---|---|---|
| base64 저장 방안 확정 — ① data URI(기본 권장) vs ② 외부 업로드(비용 큼) | 개발팀 tech-design + 사용자/오케스트레이터 승인 | **FR-4로 요구사항 명시**. ② 선택 시 사용자 승인 필요 (스토리지 신설 비용) |
| `server.py` 다운로드 프록시의 data URI 처리 범위 | 개발팀 | AC4-3 — 소규모 분기 권장. 미지원 시 다운로드 버튼 영향 명시 |
| `publish.py` 마크다운(data URI) 내보내기 방침 | 개발팀 | AC4-4 — 생략/경고 권장. 네이버 플레인 무영향 |
| 나노바나나 1장 지연 실측 (55s 내 완료 여부 — thinking 모델) | 개발팀 | 구현 시 1회 실측. 초과 시 `thinking_level`/generateContent 대안 |
| `GEMINI_API_KEY` 발급 | 사용자 | AI Studio에서 발급 (배포 전 완료 필요) |

### 가정 (assumptions)
1. `GEMINI_API_KEY`는 발급 완료 전제 (사용자 작업 — GH Actions secret 등록 포함)
2. 나노바나나 1K 16:9(1376×768)는 기존 1280×720과 **비율 동일(16:9)** — 블로그 레이아웃 호환 (픽셀 차이는 무해)
3. 이미지당 비용 실측: Flash 1K ≈ $0.034~0.067 / Lite 1K ≈ $0.0168~0.0336 (표준 티어 기준) — 사용자 인지 범위 내
4. Interactions API는 동기 완료 응답 (55s 내) — 비동기 폴링 불필요. 초과 실측 시 대안 검토 (§11)
5. 한국 리전에서 API 정상 동작 (공식 지원국 목록 실측 포함)
6. SynthID 워터마크(비가시)는 블로그 사용에 무해
7. 응답 파싱은 raw REST `steps[].content[]` 기준 — SDK convenience 필드 미사용 (SDK 미설치 전제, NFR-5)
8. 실패율 판정 임계(연속 5건·실패율 50%·시도 5건+)는 v26 수치 그대로 유지

## 12. 테스트 요구사항 (TDD, 6~7건 — 기존 8건 수정 금지)

| # | 파일 | 시나리오 | 검증 (수용 기준) |
|---|---|---|---|
| T1 | `tests/test_image_gen.py` | GEMINI 키 설정 + 나노바나나 성공 (llm_client.post_json mock) → data URI 반환 | AC1-1, AC1-2, AC1-6, AC4-1 |
| T2 | `tests/test_image_gen.py` | GEMINI 키 설정 + 나노바나나 성공 → Bailian/DashScope 호출 0회, 프롬프트 `_SINGLE_SCENE_RULES` 포함 | AC1-1, AC1-3 |
| T3 | `tests/test_image_gen.py` | GEMINI 키 미설정 → Bailian 1차 그대로, 나노바나나 호출 0회 | AC2-1, AC2-2 |
| T4 | `tests/test_image_gen.py` | 나노바나나 실패 → Bailian 1회 → 성공 시 URL 반환 (최종 실패 아님) | AC3-1, AC3-5 |
| T5 | `tests/test_image_gen.py` | 나노바나나·Bailian 실패 → DashScope 폴백 1회 / 전부 실패 → ImageGenerationError + failures 집계 | AC3-2, AC3-3, AC5-2 |
| T6 | `tests/test_image_gen.py` | GEMINI_API_KEY만 설정 → 키 가드 통과 + 성공 경로 / GEMINI_IMAGE_MODEL 오버라이드 반영 | AC6-1, AC1-4 |
| T7 | `tests/test_image_gen.py` | data URI 문자열 파싱 검증 (mime_type·base64 payload — `base64.b64decode` 후 이미지 바이트 복원) + WARNING 로그(폴백 시) | AC4-1, AC3-4 |
| — | `tests/test_content_batch.py` | **수정 금지** — 기존 11건(알림 임계 포함)이 그대로 통과해야 함 | AC5-3, AC5-4, AC2-3 |

## 13. 작업 규모 모드 판정

**모드: `small`** (요구사항팀 판정)

| 기준 | 판정 근거 |
|---|---|
| 성격 | 단일 기능 묶음 — "이미지 생성 1차 프로바이더 추가 + base64 저장 정합" (폴백·집계는 v26 기반 위 재사용) |
| 요구사항 수 | 핵심 FR 6개 (FR-1~6) + 테스트·문서 — small 기준(1~5개)에 근접, 단일 기능 범위 내 |
| 영향 범위 | 소스 2개 파일 내외(`image_gen.py` + `server.py` 최소 분기), 테스트 1개 파일(기존 파일에 추가), 문서 4종 — 신규 서비스·아키텍처 변경 없음 |
| 조사 필요성 | **외부 조사 불필요** — API 계약·가격·비율·지역은 요구사항팀이 공식 문서로 실측 완료 (§2). 경쟁·시장 조사 무관 |
| 인프라 | DB 스키마 무변경(FR-4 ① 기준), 스토리지 신설 없음, 배포 인프라 무변경 (GH Actions env 1줄 추가) |

→ **small 모드 절차**: ① 요구사항팀(본 문서) → ⑧ 개발팀(간이 plan/tech-design — **FR-4 저장 방안 확정 포함** + TDD 구현) → ⑨ 개발QA팀(수용 기준 검증)

---

*산출물: 본 requirements.md · requirements.html · 요약 답신 (모드 판정 포함)*
