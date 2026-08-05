# image_gen.py — v8: 블로그 이미지 생성 모듈 (Token Plan HTTP API)
# v7(2026-08-05)까지 bl CLI를 썼으나 Vercel 서버리스에 바이너리가 없어
# 표준 라이브러리 urllib로 전환 — 로컬·GH Actions·Vercel 모두 동일 동작.
# API 키 미설정 시 ImageGenerationError(명확한 안내)를 던져 텍스트 흐름은 유지한다.
import json
import os
import urllib.error
import urllib.request

IMAGE_MODEL = "wan2.7-image"
DEFAULT_BASE_URL = "https://token-plan.ap-southeast-1.maas.aliyuncs.com"
IMAGE_TIMEOUT = 55


class ImageGenerationError(Exception):
    pass


def _has_valid_key():
    return bool(os.getenv("BAILIAN_TOKEN_PLAN_API_KEY") or os.getenv("DASHSCOPE_API_KEY"))


def generate_image(keyword, title, prompt=None, runner=None, timeout=IMAGE_TIMEOUT):
    """제목 기반 이미지 프롬프트로 이미지를 생성, 이미지 URL을 반환한다."""
    if not _has_valid_key():
        raise ImageGenerationError("이미지 키가 필요합니다 (BAILIAN_TOKEN_PLAN_API_KEY)")
    image_prompt = prompt or _build_prompt(keyword, title)
    run = runner or _run_http
    return run(image_prompt)


def generate_section_images(keyword, title, sections, runner=None, timeout=IMAGE_TIMEOUT):
    """v10 [5]: 섹션별 이미지 5~8장 생성 — 본문 H2 소제목별 삽화 (체류·스크롤 증가).

    sections: 본문에서 추출한 H2 소제목 리스트. 각 섹션 주제에 맞는 이미지를 생성해
    URL 리스트로 반환한다. 실패 시 해당 섹션은 건너뛴다 (텍스트 흐름 유지).
    """
    if not _has_valid_key():
        raise ImageGenerationError("이미지 키가 필요합니다 (BAILIAN_TOKEN_PLAN_API_KEY)")
    run = runner or _run_http
    urls = []
    for sec in sections[:8]:
        sec_text = str(sec)[:60]
        prompt = (
            f"네이버 블로그 본문 삽화. 주제: {keyword}. 섹션: {sec_text}. "
            f"밝고 선명한 일러스트 스타일, 텍스트 없음, 16:9"
        )
        try:
            urls.append(run(prompt))
        except ImageGenerationError:
            continue
    return urls


def _build_prompt(keyword, title):
    return (
        f"네이버 블로그 대표 이미지. 주제: {keyword}. "
        f"제목: {title}. 밝고 선명한 일러스트 스타일, 텍스트 없음, 16:9"
    )


def _run_http(image_prompt):
    api_key = os.getenv("BAILIAN_TOKEN_PLAN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    base_url = os.getenv("BAILIAN_TOKEN_PLAN_BASE_URL", DEFAULT_BASE_URL)
    if base_url.endswith("/compatible-mode/v1"):
        base_url = base_url.rsplit("/compatible-mode/v1", 1)[0]
    body = json.dumps({
        "model": IMAGE_MODEL,
        "input": {
            "messages": [
                {"role": "user", "content": [{"text": image_prompt}]}
            ]
        },
        "parameters": {"size": "1024*1024", "n": 1, "watermark": False},
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/api/v1/services/aigc/multimodal-generation/generation",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=IMAGE_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:300]
        raise ImageGenerationError(f"image API http {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise ImageGenerationError(f"image API unreachable: {e.reason}") from e
    except TimeoutError as e:
        raise ImageGenerationError(f"image API timeout ({IMAGE_TIMEOUT}s)") from e
    try:
        content = data["output"]["choices"][0]["message"]["content"]
        url = next(c["image"] for c in content if c.get("type") == "image")
    except (KeyError, IndexError, TypeError, StopIteration) as e:
        raise ImageGenerationError(f"image API bad response: {str(data)[:200]}") from e
    return url
