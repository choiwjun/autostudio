# outline.py — v7: 상위글 골격 추출 모듈
# 블로그 검색 API description에서 질문형 소제목·비교·수치 구조를 뽑아
# 초안 생성 프롬프트에 들어갈 structure JSON을 만든다.
import json
import re

_QUESTION_RE = re.compile(r"(?:^|[?？])\s*(.+?)\s*[?？]|(?:어떻게|무엇|왜|하는\s*법|방법|추천|비교|가격|후기)")
_NUMERIC_RE = re.compile(r"\d+(?:[.,]\d+)?\s*(?:%|만원|원|개월|년|일|개|배|분|시간)")

_QUESTION_MARKERS = ("? ", "? ", "?", "?", "어떻게", "무엇", "왜 ", "방법", "추천", "가격")
_COMPARE_MARKERS = ("비교", "vs", "VS", "차이", "대비", "장단점", "어떤 게", "무엇이")
_FACT_MARKERS = ("%", "만원", "원", "개월", "년", "배", "개", "위", "순위", "기준")


def _clean(text):
    return re.sub(r"<[^>]+>", "", text).strip()


def _is_question(text):
    return any(m in text for m in _QUESTION_MARKERS)


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
    """
    questions, comparisons, facts = [], [], []
    seen_q, seen_c, seen_f = set(), set(), set()
    for raw in descriptions:
        text = _clean(raw)
        if not text:
            continue
        if len(text) < 8:
            continue
        if _is_question(text) and text not in seen_q:
            seen_q.add(text)
            questions.append(text)
        elif _is_compare(text) and text not in seen_c:
            seen_c.add(text)
            comparisons.append(text)
        elif _has_number(text) and text not in seen_f:
            seen_f.add(text)
            facts.append(text)

    headings = []
    for text in descriptions:
        t = _clean(text)
        if not t or len(t) < 8:
            continue
        if _is_question(t) or _has_number(t):
            short = t[:40]
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
