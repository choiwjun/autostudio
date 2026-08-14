# image_gen.py — v8: 블로그 이미지 생성 모듈 (Token Plan HTTP API)
# v7(2026-08-05)까지 bl CLI를 썼으나 Vercel 서버리스에 바이너리가 없어
# 표준 라이브러리 urllib로 전환 — 로컬·GH Actions·Vercel 모두 동일 동작.
# API 키 미설정 시 ImageGenerationError(명확한 안내)를 던져 텍스트 흐름은 유지한다.
# v15: 키 해석·HTTP·오류 정규화는 llm_client 공용 레이어 사용. timeout/title은
# 실제로 반영되도록 연결 (기존은 선언만 되고 무시되는 사어 인자였음).
# v26: DashScope 폴백 (FR-1~FR-3) — Bailian 실패 시 wanx2.1-t2i-turbo로 1회 재시도.
#   wanx2.1은 동기 호출 미지원(공식 문서 실측) → task 생성 + 폴링(async) 흐름.
#   실패 집계 stats(attempts/failures/consecutive_failures)는 content_batch가
#   reset/get — public 함수 시그니처는 불변.
# v27: Google Nano Banana 1차 프로바이더 (FR-1~FR-6) — GEMINI_API_KEY 설정 시
#   Interactions API(raw REST)로 생성. 응답 base64는 data URI로 저장 (FR-4).
#   실패 시 기존 체인(Bailian → DashScope) 폴백, 키 미설정 시 기존 경로 100% 불변.
import logging
import os
import time

import llm_client

logger = logging.getLogger(__name__)

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

# v26: DashScope 폴백 (요구사항 FR-1) — wanx2.1-t2i-turbo는 비동기 전용:
# POST image-synthesis(X-DashScope-Async: enable) → GET /tasks/{id} 폴링.
# 공식 문서(help.aliyun.com/zh/model-studio/text-to-image-v2-api-reference) 실측:
# "wan2.5 및 이하 모델은 HTTP 동기 호출 미지원" — 응답은 output.results[].url.
DASHSCOPE_IMAGE_MODEL = "wanx2.1-t2i-turbo"
# QA P2: DashScope 리전별 호스트 — 키 발급 리전과 호스트가 다르면 인증 실패.
#   베이징(중국 본토)      = https://dashscope.aliyuncs.com      (기본값)
#   싱가포르·국제 리전     = https://dashscope-intl.aliyuncs.com
# DASHSCOPE_BASE_URL env로 오버라이드 (호출 시점 평가 — 테스트·런타임 반영).
DASHSCOPE_DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com"
DASHSCOPE_POLL_INTERVAL = 3.0   # 폴링 간격 (공식 권장 10s 이하 — RPS 20 제한 내)

# v27: Google Nano Banana (Gemini 이미지 모델) — 요구사항 FR-1~FR-6.
# 기본 gemini-3.1-flash-image (Nano Banana 2, 공식 go-to — 비용·속도·품질 균형).
# 1K 16:9 JPEG 요청 (AC1-2/AC4-6) — 블로그 16:9 가로 사진 요구 충족.
# 모델·크기·베이스 URL은 env로 호출 시점 오버라이드 (테스트·차단 대응, NFR-7).
GEMINI_IMAGE_MODEL = "gemini-3.1-flash-image"
GEMINI_IMAGE_MIME = "image/jpeg"
GEMINI_IMAGE_ASPECT_RATIO = "16:9"
GEMINI_IMAGE_SIZE = "1K"
GEMINI_DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com"


def _gemini_base_url():
    """Gemini 베이스 URL — GEMINI_BASE_URL env 오버라이드 (NFR-7, 호출 시점 평가)."""
    return os.getenv("GEMINI_BASE_URL", GEMINI_DEFAULT_BASE_URL)


def _has_image_api_key():
    """이미지 생성 키 가드 (FR-6) — GEMINI_API_KEY만 설정돼도 통과.
    전역 llm_client.has_api_key()는 초안 LLM·content_batch 게이트용으로
    **불변 유지** (AC6-4) — 확장은 image_gen 내부에서만."""
    return bool((os.getenv("GEMINI_API_KEY") or "").strip() or llm_client.has_api_key())


def _dashscope_base_url():
    """DashScope 리전별 베이스 URL (QA P2): 기본 베이징, env 오버라이드 지원."""
    return os.getenv("DASHSCOPE_BASE_URL", DASHSCOPE_DEFAULT_BASE_URL)

# v26: 배치 실행 단위 실패 집계 (FR-4) — content_batch가 reset/get 호출.
# public API 시그니처를 바꾸지 않고 모듈 상태로 집계 (서버리스 경로에도 무해).
_IMAGE_STATS = {"attempts": 0, "failures": 0, "consecutive_failures": 0}


def reset_image_stats():
    """배치 시작 시 집계 초기화 (v26)."""
    _IMAGE_STATS.update(attempts=0, failures=0, consecutive_failures=0)


def get_image_stats():
    """배치 종료 시 집계 조회 — 사본 반환 (v26)."""
    return dict(_IMAGE_STATS)


class ImageGenerationError(Exception):
    pass


def generate_image(keyword, title, prompt=None, runner=None, timeout=IMAGE_TIMEOUT,
                   thumbnail_ideas=None):
    """제목 기반 이미지 프롬프트로 이미지를 생성, 이미지 URL을 반환한다.
    v19: thumbnail_ideas — 초안이 생성한 썸네일 콘셉트를 프롬프트 재료로 사용
    (첫 번째 아이디어 우선, 없으면 기존 키워드+제목 프롬프트)."""
    if not _has_image_api_key():
        # AC2-2/AC6-3: 기존 "이미지 키" 메시지 유지 + GEMINI 안내 추가 (substring 검증 호환)
        raise ImageGenerationError(
            "이미지 키가 필요합니다 "
            "(BAILIAN_TOKEN_PLAN_API_KEY / DASHSCOPE_API_KEY / GEMINI_API_KEY)")
    image_prompt = prompt or _build_prompt(keyword, title, thumbnail_ideas)
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
    if not _has_image_api_key():
        raise ImageGenerationError(
            "이미지 키가 필요합니다 "
            "(BAILIAN_TOKEN_PLAN_API_KEY / DASHSCOPE_API_KEY / GEMINI_API_KEY)")
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


def _build_prompt(keyword, title, thumbnail_ideas=None):
    base = (
        f"네이버 블로그 대표 이미지. 주제: {keyword}. 제목: {title}. "
        f"현실적인 사진 촬영 스타일. {_SINGLE_SCENE_RULES}"
    )
    ideas = [str(i).strip() for i in (thumbnail_ideas or []) if str(i).strip()]
    if ideas:
        # v19: 초안이 제안한 썸네일 콘셉트를 우선 반영 — 키워드+제목만으로
        # 프롬프트를 만들어 이미지 품질이 주제에서 벗어나던 약점 보완
        base += f"\n썸네일 콘셉트(첫 번째 아이디어 우선): {ideas[0]}"
    return base


def _run_http(image_prompt, timeout=IMAGE_TIMEOUT):
    """이미지 생성 HTTP 호출 (v27: 나노바나나 1차 분기 + DashScope 폴백 오케스트레이션).
    - attempts는 진입 시 1 증가 (키 미설정 가드는 generate_image 진입부에서
      이미 raise되므로 시도로 집계되지 않음 — 요구사항 §5 용어 정의와 일치, AC5-1)
    - GEMINI_API_KEY 설정 시 나노바나나 1차 (실패 시 내부에서 Bailian 1회 재시도)
      미설정 시 기존 Bailian 1차 — 경로 불변 (AC2-1)
    - 성공 시 연속 실패 0으로 리셋 / 최종 실패 시 failures·consecutive 증가
    - 1차(나노바나나+Bailian 또는 Bailian) 실패 → DASHSCOPE_API_KEY가 있으면
      DashScope로 1회 재시도 (FR-1·FR-3)"""
    _IMAGE_STATS["attempts"] += 1
    try:
        if os.getenv("GEMINI_API_KEY"):
            url = _nanobanana_generate(image_prompt, timeout)
        else:
            url = _primary_generate(image_prompt, timeout)
    except ImageGenerationError as primary_err:
        url = _dashscope_fallback(image_prompt, timeout, primary_err)
    _IMAGE_STATS["consecutive_failures"] = 0
    return url


def _nanobanana_generate(image_prompt, timeout):
    """나노바나나 1차 호출 (FR-1) + 실패 시 Bailian 1회 재시도 (FR-3).
    - GEMINI_API_KEY 설정 환경에서만 _run_http가 이 경로를 호출 (AC2-1)
    - 실패 시 WARNING 로그(원본 원인 + Bailian 모델) 후 Bailian 재시도 (AC3-4)
    - Bailian 키 없으면 원본 예외 그대로 전파 (기존 DashScope 폴백 단계로)
    - 성공 반환: data URI (data:{mime};base64,{data}) 또는 Bailian URL (AC4-1/AC4-5)"""
    try:
        return _nanobanana_call(image_prompt, timeout)
    except ImageGenerationError as nb_err:
        logger.warning("image API nano banana failed (%s) — retry via Bailian %s",
                       nb_err, IMAGE_MODEL)
        if not llm_client.resolve_api_key():
            raise
        try:
            return _primary_generate(image_prompt, timeout)
        except ImageGenerationError as bailian_err:
            raise ImageGenerationError(
                f"image API failed after nano banana fallback "
                f"({IMAGE_MODEL}): {bailian_err}") from bailian_err


def _nanobanana_call(image_prompt, timeout):
    """Google Interactions API raw REST 호출 (FR-1, AC1-6) —
    POST {base}/v1beta/interactions, x-goog-api-key 헤더 인증.
    응답 steps[].content[]에서 type=="image" 블록의 data(base64)+mime_type 추출
    → data URI 문자열 반환 (FR-4). SDK 미사용 — 표준 라이브러리 urllib (NFR-5).
    Bearer: API 키를 Bearer로 보내면 게이트웨이가 OAuth 오판할 수 있어
    post_json에는 빈 키를 전달하고 x-goog-api-key 단일 인증 사용
    (llm_client가 빈 키 시 Authorization 헤더 생략 — v27 가드)."""
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()  # B1: trailing LF/공백 방어
    base_url = _gemini_base_url()
    data = llm_client.post_json(
        f"{base_url}/v1beta/interactions",
        {
            "model": os.getenv("GEMINI_IMAGE_MODEL", GEMINI_IMAGE_MODEL),
            "input": [{"type": "text", "text": image_prompt}],
            "response_format": {
                "type": "image",
                "mime_type": GEMINI_IMAGE_MIME,
                "aspect_ratio": GEMINI_IMAGE_ASPECT_RATIO,
                "image_size": os.getenv("GEMINI_IMAGE_SIZE", GEMINI_IMAGE_SIZE),
            },
        },
        "", timeout, ImageGenerationError, "gemini image API",
        headers={"x-goog-api-key": api_key},
    )
    try:
        for step in data["steps"]:
            for content in step.get("content") or []:
                if isinstance(content, dict) and content.get("type") == "image":
                    b64 = content.get("data")
                    if not b64:
                        continue
                    mime = content.get("mime_type") or GEMINI_IMAGE_MIME
                    return f"data:{mime};base64,{b64}"
        raise ImageGenerationError(
            f"gemini image API bad response: {str(data)[:200]}")
    except (KeyError, TypeError, StopIteration) as e:
        raise ImageGenerationError(
            f"gemini image API bad response: {str(data)[:200]}") from e


def _primary_generate(image_prompt, timeout):
    """Bailian(Token Plan) 1차 호출 — v15 코드 경로 그대로 (FR-2 불변)."""
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


def _dashscope_fallback(image_prompt, timeout, primary_err):
    """Bailian 실패 시 DashScope 폴백 (FR-1~FR-3).
    - DASHSCOPE_API_KEY 미설정 → 폴백 미실행, 원본 예외 그대로 전파 (AC2-1)
    - 폴백 실패 → ImageGenerationError에 최종 실패 원인 포함 (AC3-1)
    - 폴백 발생 시 WARNING 로그 (원본 예외 메시지 + 폴백 모델 — AC1-4)"""
    api_key = os.getenv("DASHSCOPE_API_KEY") or ""
    if not api_key:
        # AC2-1/AC2-3: 키 미설정 = graceful 비활성 — 기존 코드 경로·예외 불변
        _IMAGE_STATS["failures"] += 1
        _IMAGE_STATS["consecutive_failures"] += 1
        raise
    logger.warning("image API primary failed (%s) — retry via DashScope %s",
                   primary_err, DASHSCOPE_IMAGE_MODEL)
    try:
        url = _dashscope_generate(image_prompt, timeout)
    except ImageGenerationError as e:
        _IMAGE_STATS["failures"] += 1
        _IMAGE_STATS["consecutive_failures"] += 1
        raise ImageGenerationError(
            f"image API failed after dashscope fallback "
            f"({DASHSCOPE_IMAGE_MODEL}): {e}") from e
    return url


def _dashscope_generate(image_prompt, timeout):
    """DashScope wanx2.1-t2i-turbo 비동기 text2image (공식 문서 계약 실측 반영):
    POST image-synthesis(X-DashScope-Async: enable) → GET /tasks/{id} 폴링(3s)
    → output.results[0].url. 전체 예산 = timeout(기존 55s 유지 — NFR-1)."""
    api_key = os.getenv("DASHSCOPE_API_KEY") or ""
    started = time.monotonic()
    deadline = started + timeout

    def _remaining():
        return deadline - time.monotonic()

    base_url = _dashscope_base_url()  # QA P2: 리전별 호스트 (env 오버라이드)
    data = llm_client.post_json(
        f"{base_url}/api/v1/services/aigc/text2image/image-synthesis",
        {
            "model": DASHSCOPE_IMAGE_MODEL,
            "input": {"prompt": image_prompt},
            "parameters": {"size": IMAGE_SIZE, "n": 1},
        },
        api_key, max(1.0, min(timeout, _remaining())),
        ImageGenerationError, "dashscope image API",
        headers={"X-DashScope-Async": "enable"},
    )
    try:
        task_id = data["output"]["task_id"]
    except (KeyError, TypeError) as e:
        raise ImageGenerationError(
            f"dashscope image API bad response: {str(data)[:200]}") from e
    while True:
        remaining = _remaining()
        if remaining <= 0:
            raise ImageGenerationError(
                f"dashscope image API timeout ({timeout}s) — "
                f"task {task_id} not finished")
        data = llm_client.get_json(
            f"{base_url}/api/v1/tasks/{task_id}", api_key,
            max(1.0, remaining), ImageGenerationError, "dashscope image API")
        output = data.get("output") or {}
        status = output.get("task_status", "")
        if status == "SUCCEEDED":
            try:
                return output["results"][0]["url"]
            except (KeyError, IndexError, TypeError) as e:
                raise ImageGenerationError(
                    f"dashscope image API bad response: {str(data)[:200]}") from e
        if status == "FAILED":
            raise ImageGenerationError(
                f"dashscope image API task failed: "
                f"{output.get('code', '')} {output.get('message', '')}".strip())
        time.sleep(DASHSCOPE_POLL_INTERVAL)
