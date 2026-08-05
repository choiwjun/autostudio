# outline.py — v7: 상위글 골격 추출 모듈
# 블로그 검색 API description에서 질문형 소제목·비교·수치 구조를 뽑아
# 초안 생성 프롬프트에 들어갈 structure JSON을 만든다.
import json
import re

# v9: 질문 분류 엄격화 — 이전 _QUESTION_MARKERS("추천"/"방법"/"가격" 포함)는
# 홍보성 본문 전체를 질문으로 오분류해 골격이 '본문 조각'이 됐음.
# 이제 물음표/의문사/질문 어미가 있어야만 질문으로 판정한다.
_NUMERIC_RE = re.compile(r"\d+(?:[.,]\d+)?\s*(?:%|만원|원|개월|년|일|개|배|분|시간)")

_INTERROGATIVE_RE = re.compile(
    r"[?？]|어떻게|무엇|왜|언제|어디서|누가|몇|까요|인가요|할까요|하나요|"
    r"되나요|나요|지요|는지|은지|하는\s*법|방법은|가격은|차이는|기준은"
)
# v9: 블로그 서두 패턴 — "확인해 보셨나요", "받아보고" 같은 도입부는 질문 후보에서 제외
_INTRO_PATTERNS = re.compile(r"확인해\s*보셨나요|받아보고|보았습니다|알아보게|보니|보면|이야기가 많은 이유")
_COMPARE_MARKERS = ("비교", "vs", "VS", "차이", "대비", "장단점", "어떤 게", "무엇이")
_FACT_MARKERS = ("%", "만원", "원", "개월", "년", "배", "개", "위", "순위", "기준")


def _clean(text):
    return re.sub(r"<[^>]+>", "", text).strip()


def _is_question(text):
    # v9: 질문형만 — "? / 어떻게 / ~까요 / ~방법은" 등. "추천" 단독은 질문 아님.
    #     서두 패턴(확인해 보셨나요 등)은 제외해 홍보성 문장이 골격에 안 들어가게 함
    if _INTRO_PATTERNS.search(text):
        return False
    return bool(_INTERROGATIVE_RE.search(text))


def _is_compare(text):
    return any(m in text for m in _COMPARE_MARKERS)


def _has_number(text):
    return bool(_NUMERIC_RE.search(text))


def extract_outline(descriptions):
    """description 목록에서 골격 구조를 추출한다.

    - questions: 질문형 문장 (즉답 구조 소제목 후보)
    - comparisons: 비교/차이 문장 (비교표 후보)
    - facts: 수치·통계가 있는 문장 (데이터 근거 후보)
    - headings: 전체에서 뽑은 대표 소제목 (질문형 우선, 최대 6개)

    v9: 세 분류를 elif가 아닌 독립 평가 — 한 문장이 질문이면서 수치를 담으면
    questions와 facts 양쪽에 들어간다 (기존 elif는 질문이면 비교·수치를 버림).
    """
    questions, comparisons, facts = [], [], []
    seen_q, seen_c, seen_f = set(), set(), set()
    for raw in descriptions:
        text = _clean(raw)
        if not text or len(text) < 8:
            continue
        if _is_question(text) and text not in seen_q:
            seen_q.add(text)
            questions.append(text)
        if _is_compare(text) and text not in seen_c:
            seen_c.add(text)
            comparisons.append(text)
        if _has_number(text) and text not in seen_f:
            seen_f.add(text)
            facts.append(text)

    headings = []
    for raw in descriptions:
        t = _clean(raw)
        if not t or len(t) < 8:
            continue
        # v9: 소제목 후보는 질문형 + 짧은 문장(40자 이하)만 — 긴 홍보성 본문 제외
        short = t if len(t) <= 40 else t[:37] + "..."
        if len(t) > 40 and not _is_question(t):
            continue
        if short not in headings:
            headings.append(short)
        if len(headings) >= 6:
            break

    return {
        "questions": questions[:8],
        "comparisons": comparisons[:6],
        "facts": facts[:6],
        "headings": headings,
    }


def build_outline_structure(descriptions):
    """outlines.structure에 저장할 JSON 문자열을 만든다."""
    return json.dumps(extract_outline(descriptions), ensure_ascii=False)
