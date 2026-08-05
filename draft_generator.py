# draft_generator.py — v8: 글 초안 생성 모듈 (Token Plan HTTP API)
# 상위글 골격(outline)을 프롬프트에 넣고 Token Plan OpenAI 호환 API로 초안을 받아온다.
# v7(2026-08-05)까지 opencode CLI를 썼으나 Vercel 서버리스에 바이너리가 없어
# 표준 라이브러리 urllib로 전환 — 로컬·GH Actions·Vercel 모두 동일 동작.
import json
import os
import urllib.error
import urllib.request

DRAFT_MODEL = "qwen3.8-max-preview"
DEFAULT_BASE_URL = "https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"

SYSTEM_PROMPT = (
    "너는 네이버 블로그 애드포스트 글을 잘 쓰는 작가다. "
    "검색에서 인용(조회수)이 되는 글의 구조를 정확히 따른다."
)

USER_PROMPT_TEMPLATE = """
주어진 키워드와 상위글 골격을 바탕으로 블로그 초안을 작성해줘.

## 키워드
{keyword}

## 상위글 골격 (질문형 소제목·비교·수치 — 검색에서 인용되는 구조)
{structure}

## 필수 규칙
1. 제목: 질문형 또는 "OOO 비교/추천" 형태, 30자 이내
2. 첫문단: 제목의 질문에 즉답 (3~4문장, 핵심 답부터)
3. 본문: 질문형 소제목(H2) 3~5개 + 각 2~3문단. 골격의 질문·비교·수치를 자연스럽게 활용
4. 말투: 친근한 존댓말, 숫자·근거 구체화

## 출력 형식 (JSON만 반환, 마크다운 코드블록 금지)
{{
  "title": "제목",
  "first_paragraph": "첫문단",
  "body": "본문 (소제목 포함 마크다운)"
}}
"""


class DraftGenerationError(Exception):
    pass


def _run_llm(prompt, timeout=90):
    api_key = os.getenv("BAILIAN_TOKEN_PLAN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise DraftGenerationError("Token Plan API 키가 필요합니다 (BAILIAN_TOKEN_PLAN_API_KEY)")
    base_url = os.getenv("BAILIAN_TOKEN_PLAN_BASE_URL", DEFAULT_BASE_URL)
    body = json.dumps({
        "model": DRAFT_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 2500,
        "enable_thinking": False,
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:300]
        raise DraftGenerationError(f"draft API http {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise DraftGenerationError(f"draft API unreachable: {e.reason}") from e
    except TimeoutError as e:
        raise DraftGenerationError(f"draft API timeout ({timeout}s)") from e
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise DraftGenerationError(f"draft API bad response: {str(data)[:200]}") from e
    return content


def parse_draft(raw):
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
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
    }


def generate_draft(keyword, structure, runner=None):
    """골격 구조를 프롬프트에 넣고 초안을 생성한다. runner는 테스트 주입용."""
    structure_text = structure if isinstance(structure, str) else json.dumps(
        structure, ensure_ascii=False)
    prompt = USER_PROMPT_TEMPLATE.format(
        keyword=keyword, structure=structure_text)
    run = runner or _run_llm
    raw = run(prompt, timeout=90)
    return parse_draft(raw)
