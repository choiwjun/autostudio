# draft_pipeline.py — v10: 2패스 생성 + 검수·재시도 파이프라인
# 애드포스트 수익 최적화 배치 [3][4]:
#   [3] 1패스(H2 골격+불릿) → 2패스(섹션 확장) — 긴 글 = 스크롤 = 광고 노출 증가
#   [4] 검수 8항목(제목/즉답/길이/H2/표/FAQ/밀도/허위1인칭) → 미달 시 1회 재생성
# v11: 본문 길이·H2 개수 체크 추가 (길이=광고 슬롯, 애드포스트 핵심 변수),
#      density를 공백 무시+핵심어 후보 매칭으로 보정, 재생성 시간 예산 가드.
import json
import time

from draft_generator import (
    DraftGenerationError, _append_faq_if_missing, _run_llm, parse_draft,
)
from intent import classify, intent_template

# [4] 검수 임계
TITLE_MAX_LEN = 30
BODY_MIN_LEN = 3000           # 애드포스트: 길이 = 스크롤 = 광고 노출
H2_MIN_COUNT = 3              # FAQ 제외 본문 섹션 수 (프롬프트 4~6개, 병합 허용 3)
KEYWORD_DENSITY_MIN = 0.0025  # 400자에 1회 — 프롬프트 '10~15회 사용'과 정합
# (v14.1: 기존 '8~15회'는 하한 8~9회 때 밀도 0.002로 검수 하한 미달 — 하한을 10회로 정렬)
KEYWORD_DENSITY_MAX = 0.03    # 3% 초과는 도배
KEYWORD_DENSITY_BASE_CAP = 4000  # v11: 밀도 분모 상한 — 긴 글(5000자)이 불리하지 않게
FAKE_EXPERIENCE = ("제가 직접", "직접 사용해", "직접 분석해", "제 경험", "제가 해")
FAQ_MARKER = "자주 묻는 질문"


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


def pass2_expand(keyword, h2s, intent, has_facts, runner=None, density_feedback=""):
    """2패스: 1패스 H2 골격을 섹션별로 확장해 최종 초안을 만든다.
    v14.1: density_feedback — 1차 검수에서 밀도 미달이면 실측 횟수·필요량을 주입해
    재생성이 같은 실패를 반복하지 않도록 함 (기존은 동일 프롬프트 맹재시도)."""
    skeleton = "\n".join(
        f"## {h['title']}\n" + "\n".join(f"- {b}" for b in h.get("bullets", []))
        for h in h2s)
    intent_section = intent_template(intent)
    grounding = "" if has_facts else (
        "\n## 데이터 그라운딩\n- 실측 수치(facts)가 없으므로 구체적 금액·수치 창작 금지.\n"
        "- '보통', '통상', '확인해야 하는 기준' 같은 검증 가능한 표현 사용.")
    prompt = f"""키워드 '{keyword}' 블로그 글을 아래 골격을 확장해 3200~5000자로 작성해줘.

## H2 골격 (각 섹션을 500~900자로 확장)
{skeleton}

## 필수 규칙
1. 첫문단: 키워드 질문에 즉답 (50~200자, 서론 금지)
2. 각 H2 섹션: 골격의 불릿을 자연스럽게 본문으로 확장, 2~3문단
3. 표(markdown table) 1~2개 이상 포함
4. 키워드 '{keyword}'를 본문 전체에 자연스럽게 10~15회 사용 (도배 금지, 문맥 속에 녹일 것)
5. 말투: 친근한 존댓말. 1인칭 허위 경험('제가 직접...') 금지 — 객관적 조언으로
6. 마지막에 '## 자주 묻는 질문' 섹션 1개만 (H3 질문 3~5개, 답변 40~120자). 다른 FAQ성 섹션 금지
{intent_section}
{grounding}
{density_feedback}
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


def check_body_length(draft):
    # v11: 애드포스트 핵심 변수 — 길이 미달은 광고 슬롯 손실이라 재생성 대상
    return len(draft.get("body", "")) >= BODY_MIN_LEN


def _h2_titles(body):
    return [ln[2:].strip() for ln in body.splitlines() if ln.startswith("## ")]


def check_h2_count(draft):
    # v11: FAQ 제외 본문 섹션 수 — 프롬프트는 4~6개 요구, 섹션 병합 허용해 3개부터 통과
    sections = [t for t in _h2_titles(draft.get("body", "")) if FAQ_MARKER not in t]
    return len(sections) >= H2_MIN_COUNT


def check_tables(draft):
    body = draft.get("body", "")
    return body.count("|") >= 6  # 표 1개 이상 (행 2+컬럼 3 = 파이프 6개 이상)


def check_faq(draft):
    body = draft.get("body", "")
    return FAQ_MARKER in body or "\n## FAQ" in body


def _keyword_cores(keyword):
    """v11: 밀도 검사 핵심어 후보 — 띄어쓰기 변형·부분 사용에 강건하게.
    전체 키워드(공백 제거) + 3자 이상 개별 토큰. '실비보험추천'처럼 붙여쓴
    키워드가 본문에 '실비보험 추천'으로 등장하는 경우를 공백 제거 매칭으로 잡는다.
    v14.2: 전 토큰이 3자 미만인 키워드('여름 휴가 추천')는 완전 구절 매칭만 남아
    자연스러운 변형('여름 휴가', '휴가 추천')이 전부 누락되던 과소집계 결함 —
    이 경우에만 2자 토큰을 핵심어로 허용 (3자+ 토큰이 있는 키워드는 기준 유지)."""
    cores = [keyword.replace(" ", "")]
    tokens = [t for t in keyword.split() if len(t) >= 3]
    if not tokens:
        tokens = [t for t in keyword.split() if len(t) >= 2]
    cores += tokens
    return list(dict.fromkeys(cores))


def keyword_density_stats(draft, keyword):
    """반환: (최다 핵심어 출현 횟수, 밀도) — 검수·재생성 피드백·경고 상세가 공용."""
    body = draft.get("body", "")
    if not body:
        return 0, 0.0
    body_norm = body.replace(" ", "").replace("\n", "")
    # 후보 중 최다 출현 핵심어 기준 — 부분 사용(예: '실비보험'만 반복)은 인정 안 함:
    # 전체 키워드(공백 제거 매칭) 또는 3자 이상 토큰으로 의도적 사용이 확인돼야 함
    count = max(body_norm.count(core) for core in _keyword_cores(keyword))
    # v11: 분모 상한 — 애드포스트 긴 글(5000자)이 밀도 감점으로 불리하지 않게
    return count, count / min(len(body), KEYWORD_DENSITY_BASE_CAP)


def check_keyword_density(draft, keyword):
    _, density = keyword_density_stats(draft, keyword)
    return KEYWORD_DENSITY_MIN <= density <= KEYWORD_DENSITY_MAX


def _enrich_failed(failed, draft, keyword):
    """v14.1: keyword_density 실패는 실측 수치 포함 상세로 교체 — '기준 미달'만으로는
    사용자가 횟수 부족인지 도배인지 알 수 없었음."""
    if "keyword_density" not in failed:
        return failed
    count, density = keyword_density_stats(draft, keyword)
    detail = (f"keyword_density ('{keyword}' {count}회·밀도 {density:.2%} — "
              f"허용 {KEYWORD_DENSITY_MIN:.2%}~{KEYWORD_DENSITY_MAX:.0%})")
    return [detail if f == "keyword_density" else f for f in failed]


def check_no_fake_experience(draft):
    body = draft.get("body", "")
    return not any(f in body for f in FAKE_EXPERIENCE)


def validate_draft(draft, keyword):
    """8항목 검수 — (통과: True, 실패 항목 리스트)"""
    checks = {
        "title": check_title(draft),
        "first_paragraph": check_first_paragraph(draft),
        "body_length": check_body_length(draft),
        "h2_count": check_h2_count(draft),
        "tables": check_tables(draft),
        "faq": check_faq(draft),
        "keyword_density": check_keyword_density(draft, keyword),
        "no_fake_experience": check_no_fake_experience(draft),
    }
    failed = [k for k, ok in checks.items() if not ok]
    return (not failed), failed


def generate_two_pass(keyword, structure, runner=None, retry_budget_seconds=None):
    """[3]+[4] 2패스 생성 + 검수. 미달 시 1회 재생성. 그래도 미달이면 최종 결과 반환.

    v11: retry_budget_seconds — 1회차 사이클이 예산을 넘겼으면 재생성을 건너뛰고
    경고와 함께 반환 (서버리스 타임아웃 방지: 2사이클 풀 실행이면 60초 한도 초과).
    v14.1: 밀도 미달 재생성은 실측 횟수·목표량을 프롬프트에 주입(맹재시도 제거).
    최종 미달 경고에는 실측 수치를 포함해 원인을 바로 파악할 수 있게 함."""
    intent = classify(keyword)
    has_facts = _outline_has_facts(structure)
    started = time.monotonic()
    draft, failed = None, []
    density_feedback = ""
    for attempt in (1, 2):
        try:
            h2s = pass1_outline(keyword, structure, runner)
            draft = pass2_expand(keyword, h2s, intent, has_facts, runner,
                                 density_feedback)
        except DraftGenerationError:
            if attempt == 1:
                continue
            raise
        ok, failed = validate_draft(draft, keyword)
        if ok:
            return draft, failed
        if attempt == 1:
            if retry_budget_seconds is not None \
                    and time.monotonic() - started > retry_budget_seconds:
                # 예산 초과 — 미달 항목은 실측 상세와 함께 응답 경고로 전달
                return draft, _enrich_failed(failed, draft, keyword)
            if "keyword_density" in failed:
                count, density = keyword_density_stats(draft, keyword)
                density_feedback = (
                    f"\n## 검수 피드백 (이번 작성분에 반드시 반영)\n"
                    f"- 키워드 '{keyword}'가 본문에 {count}회·밀도 {density:.2%}로 "
                    f"검수 하한({KEYWORD_DENSITY_MIN:.2%}) 미달.\n"
                    f"- 각 섹션·FAQ 답변에 문맥 속 자연스러운 언급을 추가해 "
                    f"10~15회(밀도 {KEYWORD_DENSITY_MIN:.2%}~{KEYWORD_DENSITY_MAX:.0%})로 높일 것.\n")
            continue  # 1회 재생성
    return draft, _enrich_failed(failed, draft, keyword)
