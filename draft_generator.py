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
    "네이버 검색 D.I.A(Deep Intent Analysis)와 AEO(답변엔진 최적화) 기준에 맞춰 "
    "검색 의도를 정확히 충족하고, 실제 경험 기반의 구체적 정보를 담는 글을 쓴다. "
    "AI 생성 티가 나지 않도록 자연스럽고 독창적인 문장을 사용한다."
)

USER_PROMPT_TEMPLATE = """
주어진 키워드와 상위글 골격을 바탕으로 블로그 초안을 작성해줘.

## 키워드
{keyword}

## 상위글 골격 (질문형 소제목·비교·수치 — 검색에서 인용되는 구조)
{structure}

## 필수 규칙
1. 제목: 질문형 또는 "OOO 비교/추천" 형태, 30자 이내. 검색 의도(정보 탐색/비교/구매 판단)를 명확히 반영
2. 첫문단: 제목의 질문에 즉답 (50~200자, 핵심 답부터. 서론·인사말 금지)
3. 본문: 질문형 소제목(H2) 4~6개 + 각 2~3문단, 총 3000자 이상. 골격의 질문·비교·수치를 반드시 활용
4. 비교·수치 데이터는 표(markdown table)나 리스트로 구조화 (본문에 표 1~2개 이상 포함)
5. 말투: 친근한 존댓말, 숫자·근거 구체화
6. 각 H2 섹션에 구체적 사례·단계·기준을 넣어 정보의 깊이를 확보

## 골격 데이터 사용 (최우선)
- 아래 "상위글 골격"의 **questions 중 3~5개를 골라 그대로 H2 소제목(질문형)으로 사용**하고, 각 질문의 핵심 내용(상황·수치·기준)을 본문에 반영할 것
- **comparisons(비교)·facts(수치)는 반드시 본문에 인용**하고, 없으면 표·사례를 직접 만들어 채울 것
- 골격의 내용을 버리고 임의의 주제로 대체하지 말 것 — 골격은 검색 상위글에서 추출한 실제 인용 구조이므로 이를 중심으로 확장해야 함
- 모델이 스스로 상상한 내용만으로 채우지 말고, 반드시 골격 데이터를 축으로 글을 구성할 것

## 네이버 D.I.A 평가 대응 (7요소)
1. 의도 부합: 검색자가 키워드에서 원하는 정보(방법·비교·후기)에 정확히 답할 것
2. 경험 정보: "제가 직접 견적을 비교해봤다", "직접 사용해봤다", "직접 분석해보니" 같은 **1인칭 허위 경험 주장은 절대 금지**. 실제로 겪은 일이 아니므로 쓸 수 없다. 대신 "견적 비교 시 주의할 점", "약관을 비교할 때 봐야 할 항목", "보험 비교 사이트의 함정"처럼 **누구나 확인 가능한 객관적 조언·기준·체크리스트**로 표현할 것. 문장은 3인칭·무인칭(예: "비교할 때는", "확인해야 하는 항목은")으로 작성
3. 정보 충실성: 막연한 설명 대신 수치·가격·기간·단계 등 구체적 데이터로 채울 것 (숫자가 없으면 '통상', '일반적으로' 대신 구체적 기준값을 조사해 사용)
4. 어뷰징 회피: 키워드 반복(도배) 금지 — 제목 1회 + 본문 자연스럽게 3~5회
5. 독창성: 상위글을 베끼지 말고 자신만의 기준·해석·팁을 더할 것
6. 문서 구조: 제목-본문 일관성, 소제목으로 논리적 흐름 구성
7. 적시성: 최신 정보·최근 트렌드를 반영한 표현 사용

## AEO 대응 (AI 답변 인용)
1. FAQ 섹션 (필수): 본문의 "마지막"에 반드시 "## 자주 묻는 질문" 섹션을 추가할 것. 실제 검색어 형태의 질문(H3) 3~5개, 각 답변 40~120자
2. 첫문단은 AI가 통째로 인용해도 되는 완결된 답변이어야 함
3. 용어 정의: 처음 등장하는 전문 용어는 "~이란 ...이다" 형식의 정의 한 문장 포함

## 출력 형식 (JSON만 반환, 마크다운 코드블록 금지)
{{
  "title": "제목",
  "first_paragraph": "첫문단",
  "body": "본문 (소제목·표 포함 마크다운, 마지막에 '## 자주 묻는 질문' 섹션 반드시 포함)"
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
        "max_tokens": 3500,
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


def generate_draft(keyword, structure, runner=None):
    """골격 구조를 프롬프트에 넣고 초안을 생성한다. runner는 테스트 주입용."""
    structure_text = structure if isinstance(structure, str) else json.dumps(
        structure, ensure_ascii=False)
    prompt = USER_PROMPT_TEMPLATE.format(
        keyword=keyword, structure=structure_text)
    run = runner or _run_llm
    raw = run(prompt, timeout=90)
    draft = parse_draft(raw)
    if not isinstance(structure, str):
        draft = _append_faq_if_missing(draft, structure)
    return draft
