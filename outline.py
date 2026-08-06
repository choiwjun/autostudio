# outline.py — v7: 상위글 골격 추출 모듈 (v11: 문장 분리 기반 재작성)
# 블로그 검색 API description에서 질문형 소제목·비교·수치 구조를 뽑아
# 초안 생성 프롬프트에 들어갈 structure JSON을 만든다.
#
# v11 재작성 배경: description은 여러 문장이 이어진 스니펫인데, 기존은 스니펫
# 전체를 한 단위로 분류해 "질문 마커가 포함된 100자+ 홍보 문단"이 questions로
# 들어갔다 (초안 H2로 그대로 복사되는 표절·저품질 리스크). 이제 문장 단위로
# 분리한 뒤 분류하고, 질문은 소제목 후보라 길이 상한을 둔다.
import json
import re

_NUMERIC_RE = re.compile(r"\d+(?:[.,]\d+)?\s*(?:%|만원|원|개월|년|일|개|배|분|시간)")

_INTERROGATIVE_RE = re.compile(
    r"[?？]|어떻게|무엇|왜|언제|어디서|누가|몇|까요|인가요|할까요|하나요|"
    r"되나요|나요|지요|는지|은지|하는\s*법|방법은|가격은|차이는|기준은"
)
# v9: 블로그 서두 패턴 — 홍보성 도입부는 질문 후보에서 제외
_INTRO_PATTERNS = re.compile(r"확인해\s*보셨나요|받아보고|보았습니다|알아보게|보니|보면|이야기가 많은 이유")
_COMPARE_MARKERS = ("비교", "vs", "VS", "차이", "대비", "장단점", "어떤 게", "무엇이")

# v11: 문장 단위 상한 — 질문은 H2 소제목 후보라 짧아야 함
QUESTION_MAX_LEN = 60
SNIPPET_MAX_LEN = 100        # 비교·수치 문장 상한 (프롬프트 컨텍스트용)
HEADING_MAX_LEN = 40

# v11: 스니펫 → 문장 분리. 마침표/물음표/느낌표 뒤에 한글·영숫자가 이어지면 절단.
# v15: 숫자 사이 마침표(3.5만원)는 소수점이지 문장 끝이 아님 — '숫자+마침표' 위치는
# 절단 금지. 미적용 시 "3.5만원"이 "3."/"5만원"으로 쪼개져 facts 수치가 왜곡됐음.
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?？~])(?<!\d\.)\s*(?=[가-힣a-zA-Z0-9])")
# 해시태그(#실비보험)는 문장 경계를 깨므로 제거
_HASHTAG_RE = re.compile(r"#\S+")


def _clean(text):
    return re.sub(r"<[^>]+>", "", text).strip()


def _split_sentences(text):
    text = _HASHTAG_RE.sub(" ", text)
    return [s.strip() for s in _SENT_SPLIT_RE.split(text) if s.strip()]


def _is_question(text):
    # v9: 물음표/의문사/의문 어미가 있어야 질문. "추천" 단독은 질문 아님
    if _INTRO_PATTERNS.search(text):
        return False
    return bool(_INTERROGATIVE_RE.search(text))


def _is_compare(text):
    return any(m in text for m in _COMPARE_MARKERS)


def _has_number(text):
    return bool(_NUMERIC_RE.search(text))


def extract_outline(descriptions):
    """description 목록에서 골격 구조를 추출한다.

    - questions: 질문형 문장 (즉답 구조 소제목 후보 — 60자 이하만)
    - comparisons: 비교/차이 문장 (비교표 후보)
    - facts: 수치·통계가 있는 문장 (데이터 근거 후보)
    - headings: 대표 소제목 (질문형 우선, 최대 6개)

    v9: 세 분류는 독립 평가 (한 문장이 질문이면서 수치면 양쪽 포함).
    v11: 분류 단위가 스니펫 전체 → 문장으로 변경, 분류별 길이 상한 적용.
    """
    questions, comparisons, facts = [], [], []
    seen_q, seen_c, seen_f = set(), set(), set()
    for raw in descriptions:
        text = _clean(raw)
        if not text:
            continue
        for sent in _split_sentences(text):
            if len(sent) < 8:
                continue
            if _is_question(sent) and len(sent) <= QUESTION_MAX_LEN \
                    and sent not in seen_q:
                seen_q.add(sent)
                questions.append(sent)
            if _is_compare(sent) and len(sent) <= SNIPPET_MAX_LEN \
                    and sent not in seen_c:
                seen_c.add(sent)
                comparisons.append(sent)
            if _has_number(sent) and len(sent) <= SNIPPET_MAX_LEN \
                    and sent not in seen_f:
                seen_f.add(sent)
                facts.append(sent)

    headings = []
    for raw in descriptions:
        for sent in _split_sentences(_clean(raw)):
            if len(sent) < 8 or len(sent) > HEADING_MAX_LEN:
                continue
            if _is_question(sent) or _has_number(sent):
                if sent not in headings:
                    headings.append(sent)
            if len(headings) >= 6:
                break
        if len(headings) >= 6:
            break

    return {
        "questions": questions[:8],
        "comparisons": comparisons[:6],
        "facts": facts[:6],
        "headings": headings,
    }


def build_outline_structure(descriptions, search_evidence=None):
    """outlines.structure에 저장할 JSON 문자열을 만든다."""
    structure = extract_outline(descriptions)
    structure["search_evidence"] = search_evidence or {
        "status": "legacy",
        "searched_at_kst": "",
        "reference_date": "",
        "items": [],
    }
    return json.dumps(structure, ensure_ascii=False)
