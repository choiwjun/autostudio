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
