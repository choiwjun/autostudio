# llm_client.py — v15: LLM 호출 공통 레이어
# API 키·베이스 URL 해석, 코드펜스 제거, HTTP 요청+오류 정규화를 단일 소스로 관리.
# 기존 draft_generator/image_gen/draft_pipeline 3곳 복제로 펜스 제거가 대문자 ```JSON을
# 놓치고 JSONDecodeError가 전용 예외 핸들러를 우회하던 문제를 해소한다.
import json
import os
import urllib.error
import urllib.request


def resolve_api_key():
    """Bailian Token Plan 키, 없으면 DashScope 키 폴백. 미설정이면 ''."""
    return os.getenv("BAILIAN_TOKEN_PLAN_API_KEY") or os.getenv("DASHSCOPE_API_KEY") or ""


def has_api_key():
    return bool(resolve_api_key())


def resolve_base_url(default):
    return os.getenv("BAILIAN_TOKEN_PLAN_BASE_URL", default)


# v23: 블로그 초안 LLM — OpenCode Go(zen/go) 우선, 없으면 기존 Bailian 폴백.
# 이미지 생성(image_gen)·운세(fortune)는 기존 Bailian 전용으로 유지.
DRAFT_OPENCODE_BASE_URL = "https://opencode.ai/zen/go/v1"
DRAFT_BAILIAN_BASE_URL = "https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"


def resolve_draft_api_key():
    """초안 LLM 키 — OPENCODE_GO_API_KEY 우선, 없으면 Bailian/DashScope 폴백."""
    return os.getenv("OPENCODE_GO_API_KEY") or resolve_api_key()


def resolve_draft_provider():
    """초안 LLM 프로바이더 결정.

    - OPENCODE_GO_API_KEY 설정: opencode-go (deepseek-v4-flash, zen/go 엔드포인트)
    - 미설정: bailian (deepseek-v4-flash-0731, 기존 Token Plan) — 하위 호환
    반환: (provider, base_url, model) — base_url은 OPENCODE_GO_BASE_URL /
    BAILIAN_TOKEN_PLAN_BASE_URL 오버라이드를 각 프로바이더에만 적용.
    """
    if os.getenv("OPENCODE_GO_API_KEY"):
        return ("opencode-go",
                os.getenv("OPENCODE_GO_BASE_URL", DRAFT_OPENCODE_BASE_URL),
                "deepseek-v4-flash")
    return ("bailian",
            os.getenv("BAILIAN_TOKEN_PLAN_BASE_URL", DRAFT_BAILIAN_BASE_URL),
            "deepseek-v4-flash-0731")


def strip_code_fence(text):
    """모델이 JSON 출력에 씌운 ``` 펜스 제거 — 언어 태그를 대소문자 구분 없이 처리
    (```json 외 ```JSON/```Json 등). 펜스 없으면 원문 반환."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        first, _, rest = text.partition("\n")
        if first.strip().lower() == "json":
            text = rest
    return text.strip()


def _open_json(req, timeout, error_cls, err_prefix):
    """urllib 요청 실행 → JSON dict. HTTP 오류·타임아웃·잘못된 JSON 본문을 전부
    error_cls(모듈 전용 예외)로 정규화 — raw JSONDecodeError가 전용 핸들러를
    우회하던 경로 차단. post_json/get_json 공용 (v26)."""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:300]
        raise error_cls(f"{err_prefix} http {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise error_cls(f"{err_prefix} unreachable: {e.reason}") from e
    except TimeoutError as e:
        raise error_cls(f"{err_prefix} timeout ({timeout}s)") from e
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise error_cls(f"{err_prefix} bad json: {raw[:200]}") from e


def _browser_headers(api_key, content_type=None):
    headers = {
        "Authorization": f"Bearer {api_key}",
        # v23: OpenCode Go(zen/go)는 Cloudflare 앞단에서 urllib 기본 UA(1010)를
        # 차단 — 브라우저 계열 UA로 통일 (Bailian에도 무해)
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/126.0.0.0 Safari/537.36"),
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def post_json(url, payload, api_key, timeout, error_cls, err_prefix, headers=None):
    """POST JSON → 응답 dict. HTTP 오류·타임아웃·잘못된 JSON 본문을 전부
    error_cls(모듈 전용 예외)로 정규화 — raw JSONDecodeError가 전용 핸들러를
    우회하던 경로 차단.
    v26: headers — 추가 요청 헤더 (예: DashScope X-DashScope-Async). 기본 None =
    기존 동작과 동일."""
    req_headers = _browser_headers(api_key, content_type="application/json")
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=req_headers,
        method="POST",
    )
    return _open_json(req, timeout, error_cls, err_prefix)


def get_json(url, api_key, timeout, error_cls, err_prefix):
    """GET JSON → 응답 dict (v26 — DashScope 비동기 task 폴링용).
    오류 정규화는 post_json과 동일."""
    req = urllib.request.Request(
        url,
        headers=_browser_headers(api_key),
        method="GET",
    )
    return _open_json(req, timeout, error_cls, err_prefix)
