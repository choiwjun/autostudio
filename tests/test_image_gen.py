# tests/test_image_gen.py
import pytest

import image_gen
from image_gen import ImageGenerationError, generate_image


def test_no_key_raises_clear_error(monkeypatch):
    monkeypatch.delenv("BAILIAN_TOKEN_PLAN_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    with pytest.raises(ImageGenerationError) as e:
        generate_image("에어프라이어", "제목")
    assert "이미지 키" in str(e.value)


def test_generate_uses_runner(monkeypatch):
    monkeypatch.setenv("BAILIAN_TOKEN_PLAN_API_KEY", "test-key")
    captured = {}

    def fake_run(prompt):
        captured["prompt"] = prompt
        return "https://img.example.com/1.png"

    url = generate_image("에어프라이어", "추천 제품", runner=fake_run)
    assert url == "https://img.example.com/1.png"
    assert "에어프라이어" in captured["prompt"]
    assert "16:9" in captured["prompt"]
    assert "실사 사진 스타일" in captured["prompt"]
    assert "photorealistic" in captured["prompt"]
    assert "카툰 금지" in captured["prompt"]
    assert "일러스트 금지" in captured["prompt"]
    assert "콜라주 금지" in captured["prompt"]
    assert "분할 화면 금지" in captured["prompt"]


def test_build_prompt_contains_topic():
    p = image_gen._build_prompt("보험 비교", "보험 비교 추천")
    assert "보험 비교" in p
    assert "텍스트 없음" in p
    assert "photorealistic" in p
    assert "3D 렌더링 금지" in p


def test_section_image_prompt_uses_photorealistic_style(monkeypatch):
    monkeypatch.setenv("BAILIAN_TOKEN_PLAN_API_KEY", "test-key")
    prompts = []

    def fake_run(prompt):
        prompts.append(prompt)
        return "https://img.example.com/section.png"

    urls = image_gen.generate_section_images(
        "보험 비교", "보험 비교 추천", ["보장 범위 비교"], runner=fake_run)
    assert len(urls) == 1
    assert "실사 사진 스타일" in prompts[0]
    assert "일러스트 금지" in prompts[0]
    assert "16:9" in prompts[0]


# ============ v26: DashScope 폴백 (TDD — 요구사항 FR-1~FR-3, 테스트 T1~T3) ============

def test_bailian_fail_falls_back_to_dashscope_once(monkeypatch, caplog):
    """T1 (AC1-1·AC1-2·AC1-3·AC1-4): Bailian 실패 + DASHSCOPE_API_KEY 설정 →
    DashScope 재시도 정확히 1회, 성공 URL 반환, 폴백 WARNING 로그."""
    import llm_client
    monkeypatch.setenv("BAILIAN_TOKEN_PLAN_API_KEY", "bailian-key")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dashscope-key")
    calls = []

    def fake_post_json(url, payload, api_key, timeout, error_cls, err_prefix, **kw):
        calls.append((url, payload, api_key, kw.get("headers")))
        if url.startswith("https://token-plan"):
            raise error_cls("image API http 429: quota exhausted")
        return {"output": {"task_id": "task-123", "task_status": "PENDING"}}

    def fake_get_json(url, api_key, timeout, error_cls, err_prefix):
        assert "task-123" in url
        return {"output": {"task_status": "SUCCEEDED",
                           "results": [{"url": "https://dashscope.example.com/1.png"}]}}

    monkeypatch.setattr(llm_client, "post_json", fake_post_json)
    monkeypatch.setattr(llm_client, "get_json", fake_get_json)
    url = generate_image("에어프라이어", "제목")
    assert url == "https://dashscope.example.com/1.png"          # AC1-2: 성공 URL 반환
    assert len(calls) == 2                                       # AC1-3: 재시도 정확히 1회
    primary_url, primary_payload, primary_key, primary_headers = calls[0]
    assert "token-plan" in primary_url and primary_key == "bailian-key"
    fb_url, fb_payload, fb_key, fb_headers = calls[1]
    assert fb_url == ("https://dashscope.aliyuncs.com/api/v1/services/"
                      "aigc/text2image/image-synthesis")
    assert fb_payload["model"] == "wanx2.1-t2i-turbo"
    # 동일 프롬프트 (AC1-1)
    bailian_prompt = primary_payload["input"]["messages"][0]["content"][0]["text"]
    assert fb_payload["input"]["prompt"] == bailian_prompt
    assert fb_payload["parameters"] == {"size": "1280*720", "n": 1}
    assert fb_key == "dashscope-key"
    assert fb_headers == {"X-DashScope-Async": "enable"}
    assert "429" in caplog.text and "wanx2.1-t2i-turbo" in caplog.text  # AC1-4


def test_no_dashscope_key_no_fallback(monkeypatch):
    """T2 (AC2-1·AC2-2·AC2-3): Bailian 실패 + 키 미설정 → 폴백 미호출,
    기존 예외 그대로 전파 (코드 경로 불변)."""
    import llm_client
    monkeypatch.setenv("BAILIAN_TOKEN_PLAN_API_KEY", "bailian-key")
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    calls = {"n": 0}

    def fake_post_json(url, payload, api_key, timeout, error_cls, err_prefix, **kw):
        calls["n"] += 1
        raise error_cls("image API http 401: invalid key")

    monkeypatch.setattr(llm_client, "post_json", fake_post_json)
    with pytest.raises(ImageGenerationError) as e:
        generate_image("에어프라이어", "제목")
    assert "401" in str(e.value)
    assert "dashscope" not in str(e.value).lower()
    assert calls["n"] == 1  # DashScope 호출 0회


def test_dashscope_fallback_failure_propagates_with_cause(monkeypatch):
    """T3 (AC3-1): 폴백(DashScope)도 실패 → ImageGenerationError 전파,
    메시지에 최종 실패 원인 포함."""
    import llm_client
    monkeypatch.setenv("BAILIAN_TOKEN_PLAN_API_KEY", "bailian-key")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dashscope-key")
    calls = {"n": 0}

    def fake_post_json(url, payload, api_key, timeout, error_cls, err_prefix, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise error_cls("image API http 500: upstream down")
        return {"output": {"task_id": "task-9", "task_status": "PENDING"}}

    def fake_get_json(url, api_key, timeout, error_cls, err_prefix):
        return {"output": {"task_status": "FAILED", "code": "DataInspectionFailed",
                           "message": "content rejected"}}

    monkeypatch.setattr(llm_client, "post_json", fake_post_json)
    monkeypatch.setattr(llm_client, "get_json", fake_get_json)
    with pytest.raises(ImageGenerationError) as e:
        generate_image("에어프라이어", "제목")
    msg = str(e.value)
    assert "dashscope" in msg
    assert "DataInspectionFailed" in msg


def test_dashscope_base_url_env_override(monkeypatch):
    """QA P2: DASHSCOPE_BASE_URL env 오버라이드 시 해당 호스트로 요청 —
    싱가포르·국제 키(dashscope-intl.aliyuncs.com) 폴백 인증 실패 방지."""
    import llm_client
    monkeypatch.setenv("BAILIAN_TOKEN_PLAN_API_KEY", "bailian-key")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dashscope-key")
    monkeypatch.setenv("DASHSCOPE_BASE_URL", "https://dashscope-intl.aliyuncs.com")
    urls = []

    def fake_post_json(url, payload, api_key, timeout, error_cls, err_prefix, **kw):
        urls.append(url)
        if url.startswith("https://token-plan"):
            raise error_cls("image API http 429: quota exhausted")
        return {"output": {"task_id": "task-intl", "task_status": "PENDING"}}

    def fake_get_json(url, api_key, timeout, error_cls, err_prefix):
        urls.append(url)
        return {"output": {"task_status": "SUCCEEDED",
                           "results": [{"url": "https://dashscope.example.com/i.png"}]}}

    monkeypatch.setattr(llm_client, "post_json", fake_post_json)
    monkeypatch.setattr(llm_client, "get_json", fake_get_json)
    url = generate_image("에어프라이어", "제목")
    assert url == "https://dashscope.example.com/i.png"
    assert any(u.startswith(
        "https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/"
        "text2image/image-synthesis") for u in urls)
    assert any(u.startswith(
        "https://dashscope-intl.aliyuncs.com/api/v1/tasks/task-intl")
        for u in urls)


# ============ v27: Google Nano Banana 1차 프로바이더 (TDD — FR-1~FR-6, 테스트 T1~T7) ============
# 규칙: 기존 8건 수정 금지. GEMINI_API_KEY 설정 시 나노바나나 1차 →
# 실패 시 Bailian → DashScope 체인 (각 1회). 미설정 시 기존 경로 100% 불변.
# stats: attempts=_run_http 진입 1회 / 최종 실패만 failures·consecutive 증가 (v26 유지).
# 응답 mock: raw REST 계약 — steps[].content[]의 type=="image" 블록 (data+mime_type).


def _nb_response(mime="image/jpeg", data="QUJDRA=="):
    """나노바나나 raw REST 응답 (AC1-6 파싱 대상)."""
    return {"steps": [{"content": [
        {"type": "text", "text": "ok"},
        {"type": "image", "mime_type": mime, "data": data},
    ]}]}


def _bailian_response(url):
    return {"output": {"choices": [
        {"message": {"content": [{"type": "image", "image": url}]}}]}}


def test_nanobanana_success_returns_data_uri(monkeypatch):
    """T1 (AC1-1·AC1-2·AC1-6·AC4-1): GEMINI 키 + 나노바나나 성공 →
    data URI 반환, 요청 계약(엔드포인트·response_format·x-goog-api-key) 검증."""
    import base64
    import llm_client
    image_gen.reset_image_stats()
    monkeypatch.delenv("BAILIAN_TOKEN_PLAN_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    calls = []

    def fake_post_json(url, payload, api_key, timeout, error_cls, err_prefix, **kw):
        calls.append((url, payload, api_key, kw.get("headers")))
        return _nb_response(mime="image/jpeg", data="QUJDRA==")

    monkeypatch.setattr(llm_client, "post_json", fake_post_json)
    url = generate_image("에어프라이어", "제목")
    assert url == "data:image/jpeg;base64,QUJDRA=="          # AC4-1 data URI
    assert len(calls) == 1                                    # AC1-1 폴백 0회
    call_url, payload, api_key, headers = calls[0]
    assert call_url == "https://generativelanguage.googleapis.com/v1beta/interactions"
    assert headers == {"x-goog-api-key": "gemini-key"}       # x-goog-api-key 인증
    assert payload["model"] == "gemini-3.1-flash-image"
    assert payload["response_format"] == {                   # AC1-2
        "type": "image", "mime_type": "image/jpeg",
        "aspect_ratio": "16:9", "image_size": "1K"}
    assert payload["input"][0]["type"] == "text"             # 구조 확인
    assert "에어프라이어" in payload["input"][0]["text"]
    assert api_key == ""                                     # Bearer 생략 정책 (x-goog-api-key만)
    # AC4-1: data URI 파싱 복원 검증
    header, _, b64 = url.partition(",")
    assert header == "data:image/jpeg;base64"
    assert base64.b64decode(b64) == b"ABCD"


def test_nanobanana_success_no_bailian_and_prompt_rules(monkeypatch):
    """T2 (AC1-1·AC1-3·AC1-5): 나노바나나 성공 시 Bailian/DashScope 0회,
    프롬프트는 _SINGLE_SCENE_RULES 포함, 대표·섹션 공통 경로 적용."""
    import llm_client
    image_gen.reset_image_stats()
    monkeypatch.delenv("BAILIAN_TOKEN_PLAN_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    calls = []

    def fake_post_json(url, payload, api_key, timeout, error_cls, err_prefix, **kw):
        calls.append((url, payload))
        return _nb_response()

    monkeypatch.setattr(llm_client, "post_json", fake_post_json)
    url = generate_image("에어프라이어", "제목")
    assert url.startswith("data:image/jpeg;base64,")
    assert len(calls) == 1
    assert "token-plan" not in calls[0][0] and "dashscope" not in calls[0][0]
    prompt = calls[0][1]["input"][0]["text"]
    assert "카툰 금지" in prompt and "일러스트 금지" in prompt     # AC1-3 재사용
    assert "실사 사진 스타일" in prompt and "16:9" in prompt
    # AC1-5: 섹션 이미지 경로도 동일한 나노바나나 1차 적용 (공통 _run_http)
    urls = image_gen.generate_section_images("보험 비교", "제목", ["보장 범위"], timeout=30)
    assert urls == ["data:image/jpeg;base64,QUJDRA=="]
    assert len(calls) == 2 and all("generativelanguage" in u for u, _ in calls)


def test_no_gemini_key_uses_bailian_primary(monkeypatch):
    """T3 (AC2-1·AC2-2): GEMINI 키 미설정 → Bailian 1차 그대로, 나노바나나 0회.
    키 전체 미설정 시 기존 오류 메시지 유지."""
    import llm_client
    monkeypatch.setenv("BAILIAN_TOKEN_PLAN_API_KEY", "bailian-key")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    calls = []

    def fake_post_json(url, payload, api_key, timeout, error_cls, err_prefix, **kw):
        calls.append(url)
        return _bailian_response("https://img.example.com/1.png")

    monkeypatch.setattr(llm_client, "post_json", fake_post_json)
    url = generate_image("에어프라이어", "제목")
    assert url == "https://img.example.com/1.png"             # AC2-1 기존 경로
    assert len(calls) == 1 and "generativelanguage" not in calls[0]
    # AC2-2: 키 전체 미설정 → 기존 메시지 (GEMINI 안내 포함 확장 허용)
    monkeypatch.delenv("BAILIAN_TOKEN_PLAN_API_KEY", raising=False)
    with pytest.raises(ImageGenerationError) as e:
        generate_image("에어프라이어", "제목")
    assert "이미지 키" in str(e.value)


def test_nanobanana_fail_falls_back_to_bailian_once(monkeypatch, caplog):
    """T4 (AC3-1·AC3-4·AC3-5): 나노바나나 실패 → Bailian 정확히 1회 →
    성공 URL 반환. 최종 실패 아님 (stats 집계 0), 폴백 WARNING 로그."""
    import llm_client
    image_gen.reset_image_stats()
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    monkeypatch.setenv("BAILIAN_TOKEN_PLAN_API_KEY", "bailian-key")
    calls = []

    def fake_post_json(url, payload, api_key, timeout, error_cls, err_prefix, **kw):
        calls.append(url)
        if url.startswith("https://generativelanguage"):
            raise error_cls("gemini image API http 429: quota exhausted")
        return _bailian_response("https://img.example.com/fallback.png")

    monkeypatch.setattr(llm_client, "post_json", fake_post_json)
    url = generate_image("에어프라이어", "제목")
    assert url == "https://img.example.com/fallback.png"
    assert len(calls) == 2                                     # AC3-1 정확히 1회 폴백
    assert calls[0].startswith("https://generativelanguage")
    assert "token-plan" in calls[1]
    stats = image_gen.get_image_stats()
    assert stats["attempts"] == 1
    assert stats["failures"] == 0 and stats["consecutive_failures"] == 0  # AC3-5
    assert "nano banana" in caplog.text and "Bailian" in caplog.text       # AC3-4


def test_nanobanana_bailian_fail_dashscope_fallback_and_all_fail(monkeypatch):
    """T5 (AC3-2·AC3-3·AC5-2): ① 나노바나나·Bailian 실패 → DashScope 1회 성공
    ② 전부 실패 → ImageGenerationError + failures·consecutive 집계."""
    import llm_client
    image_gen.reset_image_stats()
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    monkeypatch.setenv("BAILIAN_TOKEN_PLAN_API_KEY", "bailian-key")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dashscope-key")
    calls = {"n": 0}

    def fake_post_json(url, payload, api_key, timeout, error_cls, err_prefix, **kw):
        calls["n"] += 1
        if url.startswith("https://generativelanguage"):
            raise error_cls("gemini image API http 500: upstream down")
        if "token-plan" in url:
            raise error_cls("image API http 429: quota exhausted")
        return {"output": {"task_id": "task-nb", "task_status": "PENDING"}}

    def fake_get_json(url, api_key, timeout, error_cls, err_prefix):
        return {"output": {"task_status": "SUCCEEDED",
                           "results": [{"url": "https://dashscope.example.com/d.png"}]}}

    monkeypatch.setattr(llm_client, "post_json", fake_post_json)
    monkeypatch.setattr(llm_client, "get_json", fake_get_json)
    # ① DashScope 폴백 성공
    url = generate_image("에어프라이어", "제목")
    assert url == "https://dashscope.example.com/d.png"
    assert calls["n"] == 3                                     # 나노바나나+Bailian+DashScope POST
    stats = image_gen.get_image_stats()
    assert stats["attempts"] == 1 and stats["failures"] == 0   # 최종 성공 — 미집계

    # ② 전부 실패 → ImageGenerationError + 최종 실패 집계 (AC3-3, AC5-2)
    def fake_get_json_fail(url, api_key, timeout, error_cls, err_prefix):
        return {"output": {"task_status": "FAILED", "code": "DataInspectionFailed",
                           "message": "content rejected"}}

    image_gen.reset_image_stats()
    monkeypatch.setattr(llm_client, "get_json", fake_get_json_fail)
    with pytest.raises(ImageGenerationError) as e:
        generate_image("에어프라이어", "제목")
    msg = str(e.value)
    assert "dashscope" in msg and "DataInspectionFailed" in msg   # AC3-3 최종 원인
    stats = image_gen.get_image_stats()
    assert stats["attempts"] == 1
    assert stats["failures"] == 1 and stats["consecutive_failures"] == 1  # AC5-2


def test_gemini_key_only_guard_and_model_override(monkeypatch):
    """T6 (AC6-1·AC1-4): GEMINI_API_KEY만 설정 → 가드 통과 + 성공 경로.
    GEMINI_IMAGE_MODEL·GEMINI_IMAGE_SIZE env 오버라이드 반영."""
    import llm_client
    monkeypatch.delenv("BAILIAN_TOKEN_PLAN_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    monkeypatch.setenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-lite-image")
    monkeypatch.setenv("GEMINI_IMAGE_SIZE", "2K")
    captured = {}

    def fake_post_json(url, payload, api_key, timeout, error_cls, err_prefix, **kw):
        captured["payload"] = payload
        return _nb_response()

    monkeypatch.setattr(llm_client, "post_json", fake_post_json)
    url = generate_image("에어프라이어", "제목")
    assert url.startswith("data:image/jpeg;base64,")           # AC6-1 가드 통과
    assert captured["payload"]["model"] == "gemini-3.1-flash-lite-image"   # AC1-4
    assert captured["payload"]["response_format"]["image_size"] == "2K"
    assert captured["payload"]["response_format"]["mime_type"] == "image/jpeg"


def test_data_uri_parse_and_section_prompt(monkeypatch):
    """T7 (AC4-1·AC1-3): data URI 구조 파싱 — base64.b64decode로 원본 바이트 복원
    (PNG 매직 바이트), 섹션 프롬프트도 _SINGLE_SCENE_RULES 재사용."""
    import base64
    import llm_client
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    png = base64.b64encode(b"\x89PNG\r\n\x1a\n").decode()
    captured = {}

    def fake_post_json(url, payload, api_key, timeout, error_cls, err_prefix, **kw):
        captured["payload"] = payload
        return _nb_response(mime="image/png", data=png)

    monkeypatch.setattr(llm_client, "post_json", fake_post_json)
    url = image_gen.generate_section_images(
        "보험 비교", "보험 비교 추천", ["보장 범위 비교"], timeout=30)
    assert url == [f"data:image/png;base64,{png}"]             # AC4-1 응답 mime 우선
    header, _, b64 = url[0].partition(",")
    assert header == "data:image/png;base64"
    assert base64.b64decode(b64) == b"\x89PNG\r\n\x1a\n"   # 바이트 복원 검증
    prompt = captured["payload"]["input"][0]["text"]
    assert "보장 범위 비교" in prompt and "일러스트 금지" in prompt  # AC1-3


# ============ QA B1 (P2): Windows User env GEMINI_API_KEY trailing LF 방어 ============
# 개발QA 재현: 레지스트리 값이 'AIza…' + '\n'(끝 0x0A, len=40) — strip 없이 쓰면
# urllib가 "Invalid header value" raw 예외를 던져 ImageGenerationError 정규화·폴백·stats 붕괴.

def test_gemini_key_trailing_lf_stripped(monkeypatch):
    """B1 (AC1-2·QA P2): env 키에 trailing LF('\n')가 포함돼도 generate_image 정상 동작.
    _nanobanana_call의 api_key 획득 시 strip → x-goog-api-key 헤더에 LF 없는 키 사용,
    _has_image_api_key 가드도 strip 일관성 적용 (LF 포함 키로도 통과)."""
    import llm_client
    monkeypatch.delenv("BAILIAN_TOKEN_PLAN_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key\n")   # Windows User env 실측 재현 (trailing LF)
    captured = {}

    def fake_post_json(url, payload, api_key, timeout, error_cls, err_prefix, **kw):
        captured["headers"] = kw.get("headers")
        return _nb_response()

    monkeypatch.setattr(llm_client, "post_json", fake_post_json)
    url = generate_image("에어프라이어", "제목")
    assert url.startswith("data:image/jpeg;base64,")          # 정상 경로 (폴백 0회)
    assert captured["headers"] == {"x-goog-api-key": "gemini-key"}  # LF 제거된 키 사용
    assert image_gen._has_image_api_key()                     # 가드 strip 일관성
