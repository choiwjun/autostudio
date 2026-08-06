# image_gen.py — v8: 블로그 이미지 생성 모듈 (Token Plan HTTP API)
# v7(2026-08-05)까지 bl CLI를 썼으나 Vercel 서버리스에 바이너리가 없어
# 표준 라이브러리 urllib로 전환 — 로컬·GH Actions·Vercel 모두 동일 동작.
# API 키 미설정 시 ImageGenerationError(명확한 안내)를 던져 텍스트 흐름은 유지한다.
# v15: 키 해석·HTTP·오류 정규화는 llm_client 공용 레이어 사용. timeout/title은
# 실제로 반영되도록 연결 (기존은 선언만 되고 무시되는 사어 인자였음).
import time

import llm_client

IMAGE_MODEL = "wan2.7-image"
IMAGE_SIZE = "1280*720"
DEFAULT_BASE_URL = "https://token-plan.ap-southeast-1.maas.aliyuncs.com"
IMAGE_TIMEOUT = 55

_SINGLE_SCENE_RULES = (
    "단일 장면 하나만 표현할 것, 한 장소와 한 시간대만 표현할 것, "
    "실사 사진 스타일, photorealistic, 자연스러운 조명과 현실적인 카메라 렌즈·질감, "
    "다큐멘터리 또는 에디토리얼 사진 분위기, 가로형 블로그 사진, 16:9 와이드 화면. "
    "카툰 금지, 일러스트 금지, 애니메이션 금지, 3D 렌더링 금지. "
    "콜라주 금지, 여러 패널 금지, 분할 화면 금지, 격자 구성 금지, "
    "몽타주 금지, 인포그래픽 금지, 포스터 금지, 스토리보드 금지, "
    "테두리와 프레임 금지, 장면을 여러 개 나누어 그리지 말 것. "
    "이미지 안에 텍스트 없음, 글자·숫자·간판·로고·워터마크를 넣지 말 것."
)


class ImageGenerationError(Exception):
    pass


def generate_image(keyword, title, prompt=None, runner=None, timeout=IMAGE_TIMEOUT):
    """제목 기반 이미지 프롬프트로 이미지를 생성, 이미지 URL을 반환한다."""
    if not llm_client.has_api_key():
        raise ImageGenerationError("이미지 키가 필요합니다 (BAILIAN_TOKEN_PLAN_API_KEY)")
    image_prompt = prompt or _build_prompt(keyword, title)
    run = runner or (lambda p: _run_http(p, timeout=timeout))
    return run(image_prompt)


def section_image_prompt(keyword, title, section):
    sec_text = str(section)[:60]
    return (
        f"네이버 블로그 본문 삽화. 주제: {keyword}. 글 제목: {title}. "
        f"현재 섹션의 핵심 장면: {sec_text}. "
        f"현실적인 사진 촬영 스타일. {_SINGLE_SCENE_RULES}"
    )


# v17: 이보다 잔여 예산이 짧으면 이미지 생성 시작 금지 — 도중에 서버리스 한도에
# 걸려 죽으면 API 비용만 쓰고 저장은 못 한다 (버그 3).
MIN_SECTION_IMAGE_TIMEOUT = 15


def generate_section_images(keyword, title, sections, runner=None, timeout=IMAGE_TIMEOUT,
                            start_index=0, budget_seconds=None):
    """v10 [5]: 섹션별 이미지 최대 8장 생성 — 본문 H2 소제목별 삽화 (체류·스크롤 증가).

    sections: 본문에서 추출한 H2 소제목 리스트. 실패한 섹션은 건너뛴다.
    v17 증분 생성: start_index부터 생성하고 budget_seconds 초과 시 중단 —
    호출 측이 반환분(부분 성공)을 즉시 저장하면 서버리스 중도 종료에도 비용
    손실이 없다. 반환: 이번에 생성된 URL 리스트 (부분 성공 가능)."""
    if not llm_client.has_api_key():
        raise ImageGenerationError("이미지 키가 필요합니다 (BAILIAN_TOKEN_PLAN_API_KEY)")
    urls = []
    started = time.monotonic()
    for sec in sections[start_index:8]:
        call_timeout = timeout
        if budget_seconds is not None:
            remaining = budget_seconds - (time.monotonic() - started)
            if remaining < MIN_SECTION_IMAGE_TIMEOUT:
                break
            call_timeout = min(timeout, remaining)
        run = runner or (lambda p, t=call_timeout: _run_http(p, timeout=t))
        try:
            urls.append(run(section_image_prompt(keyword, title, sec)))
        except ImageGenerationError:
            continue
    return urls


def _build_prompt(keyword, title):
    return (
        f"네이버 블로그 대표 이미지. 주제: {keyword}. 제목: {title}. "
        f"현실적인 사진 촬영 스타일. {_SINGLE_SCENE_RULES}"
    )


def _run_http(image_prompt, timeout=IMAGE_TIMEOUT):
    api_key = llm_client.resolve_api_key()
    base_url = llm_client.resolve_base_url(DEFAULT_BASE_URL)
    if base_url.endswith("/compatible-mode/v1"):
        base_url = base_url.rsplit("/compatible-mode/v1", 1)[0]
    data = llm_client.post_json(
        f"{base_url}/api/v1/services/aigc/multimodal-generation/generation",
        {
            "model": IMAGE_MODEL,
            "input": {
                "messages": [
                    {"role": "user", "content": [{"text": image_prompt}]}
                ]
            },
            "parameters": {"size": IMAGE_SIZE, "n": 1, "watermark": False},
        },
        api_key, timeout, ImageGenerationError, "image API",
    )
    try:
        content = data["output"]["choices"][0]["message"]["content"]
        # v15: content가 list[{type, image}]이 아닌 str/dict여도 전용 예외로 정규화
        # (기존은 AttributeError가 그대로 새나갔음)
        if not isinstance(content, list):
            raise TypeError(f"content is {type(content).__name__}")
        url = next(c["image"] for c in content
                   if isinstance(c, dict) and c.get("type") == "image")
    except (KeyError, IndexError, TypeError, StopIteration) as e:
        raise ImageGenerationError(f"image API bad response: {str(data)[:200]}") from e
    return url
