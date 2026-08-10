# tests/test_product_recommend.py — v21(B.1): 네이버 쇼핑 검색 상품 추천
from naver_client import NaverAPIError
from product_recommend import (
    PRODUCT_BLOCK_CATEGORIES, product_block_markdown, search_products,
)


class FakeShopClient:
    def __init__(self, items=None, error=None):
        self._items = items or []
        self._error = error

    def search_shop(self, query, display=5, start=1, sort="sim"):
        if self._error:
            raise self._error
        return {"items": self._items}


def test_search_products_parses_and_filters():
    items = [
        {"title": "에어프라이어 5L", "link": "https://shopping.naver.com/1",
         "image": "https://img.example/1.jpg", "lprice": "15000", "mallName": "가전스토어"},
        {"title": "가격 없는 상품", "link": "https://shopping.naver.com/2", "lprice": "0"},
        {"title": "", "link": "https://shopping.naver.com/3", "lprice": "1000"},
        {"title": "상품4", "link": "", "lprice": "1000"},
        {"title": "에어프라이어 8L", "link": "https://shopping.naver.com/5",
         "lprice": "25000", "mallName": ""},
    ]
    products = search_products(FakeShopClient(items=items), "에어프라이어")
    assert len(products) == 2  # 가격 0·제목/링크 누락 제외
    assert products[0]["title"] == "에어프라이어 5L"
    assert products[0]["price"] == 15000
    assert products[0]["mall"] == "가전스토어"
    assert products[1]["price"] == 25000


def test_search_products_caps_at_max():
    items = [{"title": f"상품{i}", "link": f"https://x/{i}", "lprice": "1000"}
             for i in range(6)]
    products = search_products(FakeShopClient(items=items), "키워드", max_items=3)
    assert len(products) == 3


def test_search_products_api_error_returns_empty():
    client = FakeShopClient(error=NaverAPIError("http 429"))
    assert search_products(client, "키워드") == []
    assert search_products(client, "  ") == []  # 빈 키워드도 무해


def test_product_block_markdown():
    products = [{"title": "에어프라이어 5L", "link": "https://x/1",
                 "image": "", "price": 15000, "mall": "가전스토어"}]
    md = product_block_markdown("에어프라이어", products)
    assert "## 관련 상품" in md
    assert "에어프라이어 5L" in md and "15,000원" in md and "가전스토어" in md
    # PID 설정 시 딥링크 파라미터 추가 (B.2 자리)
    md2 = product_block_markdown("에어프라이어", products, pid="P123")
    assert "pid=P123" in md2
    # 상품 없으면 블록 미생성 — 파이프라인 무해
    assert product_block_markdown("키워드", []) == ""


def test_product_block_categories_defined():
    # B.3: 상품 블록 우선 카테고리 — 요리·패션·IT 등 쇼핑 전환 적합 분야
    assert "요리" in PRODUCT_BLOCK_CATEGORIES
    assert "IT" in PRODUCT_BLOCK_CATEGORIES
