# refine.py
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


def refine_keywords(words):
    """반환: (kept, rejected). rejected = [(키워드, 사유)] — 사유는 collection_log에 저장되어
    리젝 로그 주간 리뷰로 규칙을 다듬는 입력이 된다 (스펙 §4.2).
    v3: 사유를 'substring'/'token'/'portal'/'stopword'로 구분해 반환 (일괄 '필터' 기록 제거)."""
    kept, rejected, seen = [], [], set()
    for w in words:
        w = " ".join(w.split())  # 공백 정규화 (중복 병합 겸용)
        if not w or w in seen:
            continue
        seen.add(w)
        tokens = set(w.split())
        reason = None
        if any(b in w for b in BLACKLIST_SUBSTRINGS):
            reason = "substring"
        elif tokens & BLACKLIST_TOKENS:
            reason = "token"
        elif tokens & PORTAL_TOKENS:
            reason = "portal"
        elif w in STOPWORDS:
            reason = "stopword"
        if reason:
            rejected.append((w, reason))
            continue
        kept.append(w)
    return kept, rejected
