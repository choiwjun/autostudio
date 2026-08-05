# draft_pipeline.py — v10: 2패스 생성 + 검수·재시도 파이프라인
# 애드포스트 수익 최적화 배치 [3][4]:
#   [3] 1패스(H2 골격+불릿) → 2패스(섹션 확장) — 긴 글 = 스크롤 = 광고 노출 증가
#   [4] 검수 6항목(제목/즉답/표/FAQ/밀도/허위1인칭) → 미달 시 1회 재생성
import json

from draft_generator import (
    DraftGenerationError, _append_faq_if_missing, _run_llm, parse_draft,
)
from intent import classify, intent_template

# [4] 검수 임계
TITLE_MAX_LEN = 30
KEYWORD_DENSITY_MIN = 0.005   # 키워드 1회/200자 이상 (~0.5%, 밀도 1~2%의 하한)
KEYWORD_DENSITY_MAX = 0.03    # 3% 초과는 도배
FAKE_EXPERIENCE = ("제가 직접", "직접 사용해", "직접 분석해", "제 경험", "제가 해")


def _outline_questions(structure):
    if isinstance(structure, str):
        try:
            structure = json.loads(structure)
        except json.JSONDecodeError:
            return []
    if not isinstance(structure, dict):
        return []
    return structure.get("questions", [])


def _outline_has_facts(structure):
    if isinstance(structure, str):
        try:
            structure = json.loads(structure)
        except json.JSONDecodeError:
            return False
    return bool(isinstance(structure, dict) and structure.get("facts"))


def pass1_outline(keyword, structure, runner=None):
    """1패스: H2 골격 + 섹션별 핵심 불릿을 생성한다 (구조 검증용)."""
    qs = _outline_questions(structure)[:5]
    q_text = "\n".join(f"- {q}" for q in qs) if qs else "- (골격 질문 없음 — 주제에서 추론)"
    prompt = f"""키워드 '{keyword}' 블로그 글의 H2 골격을 설계해줘.

상위글 골격 질문:
{q_text}

## 요구사항
1. H2 소제목 4~6개 (질문형 또는 정보형, 30자 이내)
2. 각 H2 아래에 2~4개 핵심 불릿 (섹션에서 다룰 내용 요약)
3. 마지막 H2는 '자주 묻는 질문'

## 출력 형식 (JSON만, 코드블록 금지)
{{
  "h2s": [{{"title": "H2 소제목", "bullets": ["핵심 1", "핵심 2"]}}]
}}
"""
    raw = (runner or _run_llm)(prompt, timeout=90)
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise DraftGenerationError(f"pass1 not json: {text[:200]}") from e
    h2s = data.get("h2s", [])
    if not h2s:
        raise DraftGenerationError("pass1 empty h2s")
    return h2s


def pass2_expand(keyword, h2s, intent, has_facts, runner=None):
    """2패스: 1패스 H2 골격을 섹션별로 확장해 최종 초안을 만든다."""
    skeleton = "\n".join(
        f"## {h['title']}\n" + "\n".join(f"- {b}" for b in h.get("bullets", []))
        for h in h2s)
    intent_section = intent_template(intent)
    grounding = "" if has_facts else (
        "\n## 데이터 그라운딩\n- 실측 수치(facts)가 없으므로 구체적 금액·수치 창작 금지.\n"
        "- '보통', '통상', '확인해야 하는 기준' 같은 검증 가능한 표현 사용.")
    prompt = f"""키워드 '{keyword}' 블로그 글을 아래 골격을 확장해 3000~5000자로 작성해줘.

## H2 골격 (각 섹션을 400~800자로 확장)
{skeleton}

## 필수 규칙
1. 첫문단: 키워드 질문에 즉답 (50~200자, 서론 금지)
2. 각 H2 섹션: 골격의 불릿을 자연스럽게 본문으로 확장, 2~3문단
3. 표(markdown table) 1~2개 이상 포함
4. 말투: 친근한 존댓말. 1인칭 허위 경험('제가 직접...') 금지 — 객관적 조언으로
5. 마지막에 '## 자주 묻는 질문' 섹션 (H3 질문 3~5개, 답변 40~120자)
{intent_section}
{grounding}

## 출력 형식 (JSON만, 코드블록 금지)
{{
  "title": "제목 (30자 이내)",
  "first_paragraph": "첫문단",
  "body": "본문 마크다운 (H2 골격 유지 + 확장)"
}}
"""
    raw = (runner or _run_llm)(prompt, timeout=120)
    draft = parse_draft(raw)
    if isinstance(h2s, list) and h2s:
        draft = _append_faq_if_missing(draft, {"questions": [h["title"] for h in h2s]})
    return draft


# ---------- [4] 검수 ----------

def check_title(draft):
    return len(draft.get("title", "")) <= TITLE_MAX_LEN


def check_first_paragraph(draft):
    fp = draft.get("first_paragraph", "")
    return 30 <= len(fp) <= 400


def check_tables(draft):
    body = draft.get("body", "")
    return body.count("|") >= 6  # 표 1개 이상 (행 2+컬럼 3 = 파이프 6개 이상)


def check_faq(draft):
    body = draft.get("body", "")
    return "자주 묻는 질문" in body or "\n## FAQ" in body


def check_keyword_density(draft, keyword):
    body = draft.get("body", "")
    if not body:
        return False
    # v10.1: 공백 포함 키워드("실비보험 추천") 전체 매칭은 희소 → 핵심 단어로 검사
    core = keyword.split()[0] if " " in keyword else keyword
    count = body.count(core)
    density = count / len(body)
    return KEYWORD_DENSITY_MIN <= density <= KEYWORD_DENSITY_MAX


def check_no_fake_experience(draft):
    body = draft.get("body", "")
    return not any(f in body for f in FAKE_EXPERIENCE)


def validate_draft(draft, keyword):
    """6항목 검수 — (통과: True, 실패 항목 리스트)"""
    checks = {
        "title": check_title(draft),
        "first_paragraph": check_first_paragraph(draft),
        "tables": check_tables(draft),
        "faq": check_faq(draft),
        "keyword_density": check_keyword_density(draft, keyword),
        "no_fake_experience": check_no_fake_experience(draft),
    }
    failed = [k for k, ok in checks.items() if not ok]
    return (not failed), failed


def generate_two_pass(keyword, structure, runner=None):
    """[3]+[4] 2패스 생성 + 검수. 미달 시 1회 재생성. 그래도 미달이면 최종 결과 반환."""
    intent = classify(keyword)
    has_facts = _outline_has_facts(structure)
    for attempt in (1, 2):
        try:
            h2s = pass1_outline(keyword, structure, runner)
            draft = pass2_expand(keyword, h2s, intent, has_facts, runner)
        except DraftGenerationError:
            if attempt == 1:
                continue
            raise
        ok, failed = validate_draft(draft, keyword)
        if ok:
            return draft, failed
        if attempt == 1:
            continue  # 1회 재생성
    return draft, failed
