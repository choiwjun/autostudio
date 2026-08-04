# draft_generator.py — v7: 글 초안 생성 모듈
# 상위글 골격(outline)을 프롬프트에 넣고 opencode CLI(deepseek-v4-flash)를
# 비대화형으로 1회 실행해 제목·첫문단·본문을 받아온다.
import json
import subprocess

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


def _run_opencode(prompt, timeout=55):
    # GitHub Actions/Vercel 서버리스에서 opencode CLI 실행. 로컬 검증: "1+1"→"2"
    try:
        proc = subprocess.run(
            ["opencode", "run", "-m", "opencode-go/deepseek-v4-flash", prompt],
            capture_output=True, text=True, timeout=timeout,
        )
    except FileNotFoundError as e:
        raise DraftGenerationError("opencode CLI not found") from e
    except subprocess.TimeoutExpired as e:
        raise DraftGenerationError(f"opencode timeout ({timeout}s)") from e
    if proc.returncode != 0:
        raise DraftGenerationError(
            f"opencode failed rc={proc.returncode}: {proc.stderr[-300:]}")
    return proc.stdout


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
    run = runner or _run_opencode
    raw = run(prompt)
    return parse_draft(raw)
