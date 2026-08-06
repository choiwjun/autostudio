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


def post_json(url, payload, api_key, timeout, error_cls, err_prefix):
    """POST JSON → 응답 dict. HTTP 오류·타임아웃·잘못된 JSON 본문을 전부
    error_cls(모듈 전용 예외)로 정규화 — raw JSONDecodeError가 전용 핸들러를
    우회하던 경로 차단."""
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
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
