# refine.py — 발굴 키워드 정제 (노이즈·유해어 차단)
# 부분문자열: 오탐 여지가 거의 없는 문자열만
BLACKLIST_SUBSTRINGS = {
    "야동", "바카라", "카지노", "슬롯", "작업대출", "마약", "수면제",
    "비아그라", "시알리스", "성인용품", "랜덤채팅", "유흥",
}

# 토큰: 단독 단어일 때만 차단 → "성인병 예방", "전세대출 금리"는 통과
BLACKLIST_TOKENS = {"성인", "도박", "대출", "불법", "사기", "토토"}

# 포털/플랫폼명이 토큰으로 포함된 브랜드 검색어 제거
PORTAL_TOKENS = {
    "네이버", "카카오", "다음", "구글", "유튜브", "인스타", "인스타그램",
    "페이스북", "트위터",
}

STOPWORDS = {"모르겠음", "없음", "뭐지", "궁금"}

# v14 §1.1: 단독 브랜드 검색어 차단 — 키워드 전체가 브랜드 토큰 하나뿐일 때만.
# 부분문자열·다중토큰 매치 금지: "아이폰" 단독은 차단해도 "아이폰 배터리 교체"는
# 유망 상품 검색어라 통과 (스펙 예시). 초기 사전 + 리젝 로그 주간 리뷰로 증분.
BRAND_TOKENS = {
    "애플", "아이폰", "삼성", "갤럭시", "에어팟", "나이키", "아디다스",
    "스타벅스", "쿠팡", "다이소", "토스",
}

# v14 §1.1: 길이 임계 (공백 제거 기준)
KEYWORD_MIN_LEN = 2
KEYWORD_MAX_LEN = 25

# v14 §1.1: '숫자+단위' 토큰 판별용 문자 집합 — "2024", "10분" 같은 순수 수치만
# 남은 키워드는 검색 수요 신호가 없어 차단 ("10분 요리"는 비숫자 토큰이 있어 통과)
_UNIT_CHARS = set("0123456789.,%분초일원천억배개명")
_UNIT_WORDS = ("시간", "개월", "그램")


def _noise_token(token):
    t = token
    for w in _UNIT_WORDS:
        t = t.replace(w, "")
    return bool(t) and all(c in _UNIT_CHARS for c in t) and any(c.isdigit() for c in t)


def _is_noise(w):
    """순수 특수문자만 남거나, 모든 토큰이 숫자+단위뿐이면 노이즈."""
    tokens = w.split()
    if all(not any(c.isalnum() for c in t) for t in tokens):
        return True
    return all(_noise_token(t) for t in tokens)


def reject_reason(w):
    """단일 키워드의 차단 사유를 반환 — None이면 통과.
    refine_keywords와 발굴 BFS 사전 필터(expand_keywords의 exclude)가 공용해
    정제 기준이 한 곳에서만 관리되도록 한다 (v14 §1)."""
    w = " ".join(w.split())  # 공백 정규화
    if not w:
        return "len"
    if any(b in w for b in BLACKLIST_SUBSTRINGS):
        return "substring"
    tokens = set(w.split())
    if tokens & BLACKLIST_TOKENS:
        return "token"
    if tokens & PORTAL_TOKENS:
        return "portal"
    if w in STOPWORDS:
        return "stopword"
    compact_len = len(w.replace(" ", ""))
    if compact_len < KEYWORD_MIN_LEN or compact_len > KEYWORD_MAX_LEN:
        return "len"
    if _is_noise(w):
        return "noise"
    if w in BRAND_TOKENS:  # 키워드 전체가 브랜드 토큰 단독일 때만 (부분 매치 금지)
        return "brand"
    return None


def refine_keywords(words):
    """반환: (kept, rejected). rejected = [(키워드, 사유)] — 사유는 collection_log에 저장되어
    리젝 로그 주간 리뷰로 규칙을 다듬는 입력이 된다 (스펙 §4.2).
    v3: 사유를 'substring'/'token'/'portal'/'stopword'로 구분해 반환 (일괄 '필터' 기록 제거).
    v14: 'len'(1자·25자 초과) / 'noise'(특수문자·숫자+단위만) / 'brand'(단독 브랜드 토큰) 추가."""
    kept, rejected, seen = [], [], set()
    for w in words:
        w = " ".join(w.split())  # 공백 정규화 (중복 병합 겸용)
        if not w or w in seen:
            continue
        seen.add(w)
        reason = reject_reason(w)
        if reason:
            rejected.append((w, reason))
            continue
        kept.append(w)
    return kept, rejected
