# product_recommend.py — v21(B.1): 네이버 쇼핑 검색 기반 상품 추천 모듈
# 네이버쇼핑커넥트 상품 블록(Phase B)의 상품 소스. 초안 키워드 → 상품 3개 추출.
# B.2(딥링크 변환)는 SHOPPING_CONNECT_PID 설정 후 활성화 — 미설정 시 링크 자리 표시.
import logging
import re

from naver_client import NaverAPIError

logger = logging.getLogger("product_recommend")

# 네이버 쇼핑 검색 API의 title은 <b> 강조 마크업 포함 — 제거 (v21.1 버그 수정)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
# 상품 링크에서 상품번호 추출 — shop.json link의 productId/channelProductNo
_PRODUCT_NO_RE = re.compile(r"(?:productId|channelProductNo|pid)=(\d+)")


def _extract_product_no(link):
    """네이버 쇼핑 링크 → 상품번호. 추출 실패 시 '' (딥링크 변환 불가)."""
    m = _PRODUCT_NO_RE.search(link or "")
    return m.group(1) if m else ""


def to_deep_link(link, pid):
    """네이버쇼핑커넥트 딥링크 변환 (v21 B.2).
    brandconnect.naver.com/affiliates/{PID}?channelProductNo={상품번호}
    상품번호 추출 실패 또는 PID 미설정 시 원본 링크 유지 (무해 폴백)."""
    if not pid:
        return link
    product_no = _extract_product_no(link)
    if not product_no:
        return link
    return (f"https://brandconnect.naver.com/affiliates/{pid}"
            f"?channelProductNo={product_no}")

# 카테고리 → 쇼핑 검색 최적 키워드 가중치 (B.3에서 초안 삽입 시 우선 대상)
PRODUCT_BLOCK_CATEGORIES = ("요리", "패션", "뷰티", "IT", "디지털", "인테리어", "반려동물")

PRODUCT_SEARCH_DISPLAY = 5   # 검색 5개 중 상위 3개 선택 (품질 여유)
PRODUCT_MAX = 3


def _parse_item(item):
    """네이버 쇼핑 검색 응답 항목 → 정규화 상품 dict. 필수 필드 누락 시 None."""
    title = _HTML_TAG_RE.sub("", str(item.get("title") or "")).strip()
    link = str(item.get("link") or "").strip()
    if not title or not link:
        return None
    try:
        price = int(item.get("lprice") or 0)
    except (TypeError, ValueError):
        price = 0
    return {
        "title": title,
        "link": link,
        "image": str(item.get("image") or "").strip(),
        "price": price,
        "mall": str(item.get("mallName") or "").strip(),
    }


def search_products(client, keyword, max_items=PRODUCT_MAX):
    """키워드 → 네이버 쇼핑 검색 → 상위 상품 리스트.
    실패(API 오류) 시 빈 리스트 — 상품 블록은 선택 사양이라 파이프라인을
    멈추지 않는다 (graceful degradation, 쇼핑클릭 지수와 동일 철학).
    반환: [{'title','link','image','price','mall'}] (최대 max_items)"""
    if not keyword or not keyword.strip():
        return []
    try:
        data = client.search_shop(keyword, display=PRODUCT_SEARCH_DISPLAY)
    except NaverAPIError as e:
        logger.warning("shop search failed kw=%s: %s", keyword, e)
        return []
    items = []
    for raw in data.get("items", []):
        if len(items) >= max_items:  # v31: append 전 검사 — max_items=0이어도 1개 반환하던 오프바이원
            break
        parsed = _parse_item(raw)
        if parsed and parsed["price"] > 0:  # 가격 없는 광고성/중고 제외
            items.append(parsed)
    return items


def product_block_markdown(keyword, products, pid=""):
    """상품 리스트 → 블로그 하단 '관련 상품' 블록 마크다운.
    v21(B.2): pid 설정 시 네이버쇼핑커넥트 딥링크로 변환 (상품번호 추출 실패·
    PID 미설정은 원본 링크 유지). 네이버 플레인 텍스트용은 publish.py가
    이 데이터를 재렌더링한다."""
    if not products:
        return ""
    lines = ["", "## 관련 상품", ""]
    for i, p in enumerate(products[:PRODUCT_MAX], 1):
        price = f"{p['price']:,}원" if p["price"] else "가격 확인"
        link = to_deep_link(p["link"], pid)
        mall = f" ({p['mall']})" if p["mall"] else ""
        lines.append(
            f"{i}. **{p['title']}** — {price} "
            f"[(보러 가기)]({link}){mall}")
    return "\n".join(lines) + "\n"


# 참고: 실제 렌더링은 publish._product_block_lines가 담당 (플랫폼별 분기).
# product_block_markdown은 검증·참조용으로 유지한다.
