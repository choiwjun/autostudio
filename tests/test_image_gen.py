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
