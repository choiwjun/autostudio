# tests/test_refine.py
from refine import refine_keywords


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
