# draft_generator.py — v8: 글 초안 생성 모듈 (Token Plan HTTP API)
# 상위글 골격(outline)을 프롬프트에 넣고 Token Plan OpenAI 호환 API로 초안을 받아온다.
# v7(2026-08-05)까지 opencode CLI를 썼으나 Vercel 서버리스에 바이너리가 없어
# 표준 라이브러리 urllib로 전환 — 로컬·GH Actions·Vercel 모두 동일 동작.
# v15: HTTP·키 해석·펜스 제거·오류 정규화는 llm_client 공용 레이어 사용.
#      v8 단일패스 generate_draft는 v10 이후 프로덕션 미사용 사어 코드라 제거 —
#      초안 생성은 draft_pipeline.generate_two_pass(2패스+검수)가 유일 진입점.
import json

import llm_client

DRAFT_MODEL = "deepseek-v4-flash-0731"
DEFAULT_BASE_URL = "https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"

SYSTEM_PROMPT = (
    "너는 네이버 블로그 애드포스트 글을 잘 쓰는 작가다. "
    "네이버 검색 D.I.A(Deep Intent Analysis)와 AEO(답변엔진 최적화) 기준에 맞춰 "
    "검색 의도를 정확히 충족하고, 실제 경험 기반의 구체적 정보를 담는 글을 쓴다. "
    "AI 생성 티가 나지 않도록 자연스럽고 독창적인 문장을 사용한다."
)


class DraftGenerationError(Exception):
    pass


def _run_llm(prompt, timeout=90):
    api_key = llm_client.resolve_api_key()
    if not api_key:
        raise DraftGenerationError("Token Plan API 키가 필요합니다 (BAILIAN_TOKEN_PLAN_API_KEY)")
    base_url = llm_client.resolve_base_url(DEFAULT_BASE_URL)
    data = llm_client.post_json(
        f"{base_url}/chat/completions",
        {
            "model": DRAFT_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
            # v11: 3000자+ 본문 — 한국어 토큰 비율상 4000 토큰은 본문 중간 절단 리스크
            "max_tokens": 5500,
            "enable_thinking": False,
        },
        api_key, timeout, DraftGenerationError, "draft API",
    )
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise DraftGenerationError(f"draft API bad response: {str(data)[:200]}") from e
    return content


TAGS_MAX_COUNT = 10  # 네이버 태그 상한 여유 있게 — 프롬프트는 5~8개 요구


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
    }


def _append_faq_if_missing(draft, structure):
    """AEO: body에 FAQ 섹션이 없으면 골격의 질문으로 보정 (모델 누락 대비)."""
    body = draft["body"]
    if "자주 묻는 질문" in body or "\n## FAQ" in body:
        return draft
    questions = []
    if isinstance(structure, dict):
        questions = structure.get("questions", [])[:3]
    if not questions:
        return draft
    faq_lines = ["", "## 자주 묻는 질문", ""]
    for q in questions:
        short = q[:60] + ("..." if len(q) > 60 else "")
        faq_lines.append(f"### {short}")
        faq_lines.append("본문에서 설명한 내용을 바탕으로 간결하게 답변합니다.")
        faq_lines.append("")
    draft["body"] = body.rstrip() + "\n" + "\n".join(faq_lines)
    return draft
