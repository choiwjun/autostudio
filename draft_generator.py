# draft_generator.py — v8: 글 초안 생성 모듈 (OpenAI 호환 HTTP API)
# 상위글 골격(outline)을 프롬프트에 넣고 LLM API로 초안을 받아온다.
# v7(2026-08-05)까지 opencode CLI를 썼으나 Vercel 서버리스에 바이너리가 없어
# 표준 라이브러리 urllib로 전환 — 로컬·GH Actions·Vercel 모두 동일 동작.
# v23: 프로바이더 전환 — OPENCODE_GO_API_KEY가 있으면 OpenCode Go
# (zen/go, deepseek-v4-flash), 없으면 기존 Bailian(Token Plan) 폴백.
# v15: HTTP·키 해석·펜스 제거·오류 정규화는 llm_client 공용 레이어 사용.
#      v8 단일패스 generate_draft는 v10 이후 프로덕션 미사용 사어 코드라 제거 —
#      초안 생성은 draft_pipeline.generate_two_pass(2패스+검수)가 유일 진입점.
import json

import llm_client

SYSTEM_PROMPT = (
    "너는 네이버 블로그 애드포스트 글을 잘 쓰는 작가다. "
    "네이버 검색 D.I.A(Deep Intent Analysis)와 AEO(답변엔진 최적화) 기준에 맞춰 "
    "검색 의도를 정확히 충족하는 글을 쓴다. "
    "AI 브리핑·AI 탭이 인용하기 좋은 구조(질문-답변·리스트·단계·표)와 "
    "두괄식 즉답(첫 문단에 핵심 답)을 사용한다. "
    "정보는 검증 가능한 구체적 기준·사례·수치 범위 중심으로 작성하되, "
    "경험·출처·기관명·통계를 창작하지 않는다 — 허위 1인칭 경험과 "
    "'조사에 따르면', '연구에 따르면'류 근거 없는 출처 표현은 금지다. "
    "AI 생성 티가 나지 않도록 자연스럽고 독창적인 문장을 사용한다."
)


class DraftGenerationError(Exception):
    pass


# v23.1: 폴백 대상 오류 — 할당량 소진(429)·서버 오류(5xx)·네트워크 불가.
# 401(키 오류)은 폴백해도 실패하므로 제외.
_FALLBACK_ERROR_MARKERS = ("http 429", "http 5", "unreachable")


def _should_fallback(err_text):
    return any(m in err_text for m in _FALLBACK_ERROR_MARKERS)


def _run_llm(prompt, timeout=90):
    # v23: 프로바이더 결정 — OPENCODE_GO_API_KEY가 있으면 OpenCode Go
    # (deepseek-v4-flash), 없으면 기존 Bailian(Token Plan) 폴백.
    # v23.1: opencode-go가 할당량/서버 오류로 실패하면 Bailian으로 재시도 —
    # 주간 쿼터 소진 시 초안 생성이 며칠간 마비되지 않도록.
    provider, base_url, model = llm_client.resolve_draft_provider()
    api_key = llm_client.resolve_draft_api_key()
    if not api_key:
        raise DraftGenerationError(
            "초안 LLM 키가 필요합니다 (OPENCODE_GO_API_KEY 또는 BAILIAN_TOKEN_PLAN_API_KEY)")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        # v11: 3000자+ 본문 — 한국어 토큰 비율상 4000 토큰은 본문 중간 절단 리스크
        "max_tokens": 5500,
    }
    if provider == "opencode-go":
        # v23: deepseek-v4-flash는 reasoning 모델 — 추론을 끄지 않으면
        # max_tokens를 추론이 소진해 본문이 잘린다. DeepSeek 공식 파라미터 사용.
        payload["thinking"] = {"type": "disabled"}
    else:
        payload["enable_thinking"] = False
    try:
        data = llm_client.post_json(
            f"{base_url}/chat/completions", payload,
            api_key, timeout, DraftGenerationError, "draft API",
        )
    except DraftGenerationError as e:
        if not (provider == "opencode-go" and _should_fallback(str(e))):
            raise
        bailian_key = llm_client.resolve_api_key()  # Bailian/DashScope
        if not bailian_key:
            raise
        bailian_url = llm_client.resolve_base_url(
            llm_client.DRAFT_BAILIAN_BASE_URL)
        payload = {
            "model": "deepseek-v4-flash-0731",
            "messages": payload["messages"],
            "temperature": 0.7,
            "max_tokens": 5500,
            "enable_thinking": False,
        }
        data = llm_client.post_json(
            f"{bailian_url}/chat/completions", payload,
            bailian_key, timeout, DraftGenerationError,
            "draft API(bailian fallback)",
        )
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise DraftGenerationError(f"draft API bad response: {str(data)[:200]}") from e
    return content


TAGS_MAX_COUNT = 10  # 네이버 태그 상한 여유 있게 — 프롬프트는 5~8개 요구
THUMBNAIL_IDEAS_MAX = 2  # v19: 썸네일 아이디어 — 대표 이미지 프롬프트 재료


def _normalize_tags(raw_tags):
    """태그 정규화 — #·공백 정리, 중복 제거, 상한 클램프. 없으면 빈 리스트."""
    if not isinstance(raw_tags, list):
        return []
    tags = []
    for raw in raw_tags:
        tag = str(raw).strip().lstrip("#").strip()
        if tag and tag not in tags:
            tags.append(tag)
    return tags[:TAGS_MAX_COUNT]


def _normalize_thumbnail_ideas(raw_ideas):
    """썸네일 아이디어 정규화 — 문자열 리스트 2개 상한, 빈 값 제거."""
    if not isinstance(raw_ideas, list):
        return []
    ideas = []
    for raw in raw_ideas:
        idea = str(raw).strip()
        if idea and idea not in ideas:
            ideas.append(idea)
    return ideas[:THUMBNAIL_IDEAS_MAX]


def parse_draft(raw):
    text = llm_client.strip_code_fence(raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise DraftGenerationError(f"draft not json: {text[:200]}") from e
    for key in ("title", "first_paragraph", "body"):
        if key not in data or not data[key]:
            raise DraftGenerationError(f"draft missing field: {key}")
    return {
        "title": data["title"].strip(),
        "first_paragraph": data["first_paragraph"].strip(),
        "body": data["body"].strip(),
        # 태그는 선택 필드 — 모델 누락 시 pass2_expand가 키워드로 보장
        "tags": _normalize_tags(data.get("tags")),
        # v19: 썸네일 아이디어 (선택) — 대표 이미지 프롬프트 재료
        "thumbnail_ideas": _normalize_thumbnail_ideas(data.get("thumbnail_ideas")),
    }


def _append_faq_if_missing(draft, structure, platform="naver"):
    """AEO: body에 FAQ 섹션이 없으면 골격의 질문으로 보정 (모델 누락 대비).
    v19: 플랫폼별 FAQ 포맷 — 네이버는 플레인 Q/A, 티스토리는 인용문 Q/A,
    애드센스/브랜드는 ### H3 질문 (기존 동작)."""
    body = draft["body"]
    if "자주 묻는 질문" in body or "\n## FAQ" in body:
        return draft
    questions = []
    if isinstance(structure, dict):
        questions = structure.get("questions", [])[:3]
    if not questions:
        return draft
    faq_lines = ["", "자주 묻는 질문" if platform == "naver"
                 else "## 자주 묻는 질문 (FAQ)" if platform == "tistory"
                 else "## 자주 묻는 질문", ""]
    for q in questions:
        short = q[:60] + ("..." if len(q) > 60 else "")
        if platform == "naver":
            faq_lines += [f"Q. {short}", "A. 본문에서 설명한 내용을 바탕으로 간결하게 답변합니다.", ""]
        elif platform == "tistory":
            faq_lines += [f"> **Q. {short}**", "> A. 본문에서 설명한 내용을 바탕으로 간결하게 답변합니다.", ""]
        else:
            faq_lines += [f"### {short}", "본문에서 설명한 내용을 바탕으로 간결하게 답변합니다.", ""]
    draft["body"] = body.rstrip() + "\n" + "\n".join(faq_lines)
    return draft
