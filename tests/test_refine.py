# tests/test_refine.py
from refine import refine_keywords, reject_reason


def test_removes_duplicates_and_blank():
    kept, _ = refine_keywords(["맛집 추천", "맛집  추천", " ", ""])
    assert kept == ["맛집 추천"]


def test_substring_blacklist():
    kept, rejected = refine_keywords(["바카라사이트 후기", "성인용품 추천"])
    assert kept == []
    assert rejected == [("바카라사이트 후기", "substring"),
                        ("성인용품 추천", "substring")]


def test_token_blacklist_blocks_standalone_words():
    kept, rejected = refine_keywords(["성인 용품", "도박 후기"])
    assert kept == []
    assert all(r[1] == "token" for r in rejected)


def test_compound_words_survive():
    # v1 과차단 수정 검증
    kept, rejected = refine_keywords(
        ["성인병 예방 음식", "전세대출 금리 비교", "홍삼 선물세트"])
    assert kept == ["성인병 예방 음식", "전세대출 금리 비교", "홍삼 선물세트"]
    assert rejected == []


def test_stopwords_and_portal_tokens():
    # v3: 사유가 구분되어야 리젝 로그 주간 리뷰의 입력이 됨 (스펙 §4.2)
    kept, rejected = refine_keywords(["네이버 검색", "모르겠음", "정상 키워드"])
    assert kept == ["정상 키워드"]
    assert {r[1] for r in rejected} == {"portal", "stopword"}


# ---------- v14 §1.1: len / noise / brand ----------

def test_len_rule_blocks_too_short_or_too_long():
    long_kw = "오늘의 전국 맛집 추천 리스트 상세하게 정리해보았습니다만요"  # 공백 제외 26자
    assert len(long_kw.replace(" ", "")) > 25
    kept, rejected = refine_keywords(["와", long_kw])
    assert kept == []
    assert rejected[0] == ("와", "len")
    assert rejected[1][1] == "len"
    # 경계: 2자·25자는 통과
    k2, _ = refine_keywords(["맛집", "가" * 25])
    assert k2 == ["맛집", "가" * 25]


def test_noise_rule_blocks_specials_and_number_units():
    kept, rejected = refine_keywords(["!!!", "2024", "10분", "정상 키워드"])
    assert kept == ["정상 키워드"]
    assert all(r[1] == "noise" for r in rejected)


def test_noise_rule_keeps_mixed_tokens():
    # 비숫자 토큰이 섞이면 노이즈 아님
    kept, rejected = refine_keywords(["10분 요리", "아이폰 15"])
    assert kept == ["10분 요리", "아이폰 15"]
    assert rejected == []


def test_brand_rule_blocks_standalone_tokens_only():
    # v14 §1.1: 토큰 단독 매치만 — 부분문자열 매치 금지
    kept, rejected = refine_keywords(["애플", "아이폰 배터리 교체 방법", "갤럭시"])
    assert kept == ["아이폰 배터리 교체 방법"]
    assert rejected == [("애플", "brand"), ("갤럭시", "brand")]


def test_reject_reason_matches_refine_keywords():
    # BFS 사전 필터(expand_keywords exclude)와 정제가 동일 판별을 써야 함
    samples = ["바카라사이트 후기", "성인 용품", "네이버 검색", "모르겠음",
               "와", "!!!", "애플", "아이폰 배터리 교체", "정상 키워드"]
    kept, rejected = refine_keywords(samples)
    for kw, reason in rejected:
        assert reject_reason(kw) == reason
    for kw in kept:
        assert reject_reason(kw) is None
