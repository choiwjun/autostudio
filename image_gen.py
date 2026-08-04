# image_gen.py — v7: 블로그 이미지 생성 모듈
# Aliyun Bailian CLI(`bl image generate`, qwen 계열)로 대표 이미지를 생성한다.
# API 키 미설정/무효 시 DraftGenerationError(명확한 안내)를 던져 텍스트 흐름은 유지한다.
import json
import os
import subprocess

IMAGE_MODEL = "wan2.7-image"


class ImageGenerationError(Exception):
    pass


def _has_valid_key():
    return bool(os.getenv("BAILIAN_TOKEN_PLAN_API_KEY") or os.getenv("DASHSCOPE_API_KEY"))


def generate_image(keyword, title, prompt=None, runner=None, timeout=55):
    """제목 기반 이미지 프롬프트를 만들어 bl CLI로 생성, 이미지 URL을 반환한다."""
    if not _has_valid_key():
        raise ImageGenerationError("이미지 키가 필요합니다 (BAILIAN_TOKEN_PLAN_API_KEY)")
    image_prompt = prompt or _build_prompt(keyword, title)
    run = runner or _run_bl
    return run(image_prompt)


def _build_prompt(keyword, title):
    return (
        f"네이버 블로그 대표 이미지. 주제: {keyword}. "
        f"제목: {title}. 밝고 선명한 일러스트 스타일, 텍스트 없음, 16:9"
    )


def _run_bl(image_prompt):
    try:
        proc = subprocess.run(
            ["bl", "image", "generate",
             "--model", IMAGE_MODEL,
             "--prompt", image_prompt,
             "--output-format", "json"],
            capture_output=True, text=True, timeout=timeout,
        )
    except FileNotFoundError as e:
        raise ImageGenerationError("bl CLI not found") from e
    except subprocess.TimeoutExpired as e:
        raise ImageGenerationError(f"bl timeout ({timeout}s)") from e
    if proc.returncode != 0:
        raise ImageGenerationError(f"bl failed rc={proc.returncode}: {proc.stderr[-300:]}")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise ImageGenerationError(f"bl output not json: {proc.stdout[:200]}") from e
    url = data.get("url") or (data.get("output", [{}])[0].get("url") if data.get("output") else None)
    if not url:
        raise ImageGenerationError("bl returned no image url")
    return url
