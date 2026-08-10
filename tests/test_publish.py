# v17: 게시용 문서 내보내기 — v19 플랫폼별 포맷 (네이버 플레인 / 티스토리 마크다운+목차 / 애드센스·브랜드)
import json

import pytest

from publish import build_export_markdown


def _draft(**over):
    base = {
        "title": "에어프라이어 추천 기준",
        "first_paragraph": "즉답 문단입니다.",
        "body": "## 1. 섹션1\n내용1\n\n## 2. 섹션2\n내용2\n\n## 3. 자주 묻는 질문 (FAQ)\n### q\na",
        "image_url": "",
        "section_images": "",
        "platform": "tistory",
    }
    base.update(over)
    return base


def test_export_tistory_markdown_structure():
    md = build_export_markdown(_draft())
    assert md.startswith("# 에어프라이어 추천 기준\n\n")
    assert "> **한줄 요약:** 즉답 문단입니다." in md
    assert "**목차**" in md
    assert "1. 섹션1" in md and "2. 섹션2" in md
    assert "## 1. 섹션1" in md


def test_export_tistory_inserts_images_at_positions():
    draft = _draft(
        image_url="https://cdn.example.com/main.png",
        section_images=json.dumps(
            ["https://cdn.example.com/s1.png", "https://cdn.example.com/s2.png"]))
    md = build_export_markdown(draft)
    assert "![대표 이미지](https://cdn.example.com/main.png)" in md
    assert "![섹션 이미지 1](https://cdn.example.com/s1.png)" in md
    assert "![섹션 이미지 2](https://cdn.example.com/s2.png)" in md
    # 대표 이미지는 본문 앞, 섹션 이미지는 H2 직후 (한줄요약 블록보다는 뒤)
    assert md.index("대표 이미지") > md.index("즉답 문단입니다.")
    assert md.index("## 1. 섹션1") < md.index("섹션 이미지 1") < md.index("## 2. 섹션2")
    # FAQ 섹션에는 이미지 미삽입
    assert md.index("자주 묻는 질문") > md.index("섹션 이미지 2")


def test_export_survives_bad_section_json():
    md = build_export_markdown(_draft(section_images="not json"))
    assert "## 1. 섹션1" in md  # 이미지 없이 본문 유지


def test_export_includes_tags_per_platform():
    # v19: 티스토리는 쉼표(# 없음), 네이버/애드센스/브랜드는 #+공백
    tags = json.dumps(["에어프라이어 추천", "주방가전"], ensure_ascii=False)
    md = build_export_markdown(_draft(tags=tags))
    assert "**태그:** 에어프라이어 추천, 주방가전" in md
    md_naver = build_export_markdown(_draft(tags=tags, platform="naver"))
    assert "[태그]" in md_naver and "#에어프라이어 추천 #주방가전" in md_naver
    md_ads = build_export_markdown(_draft(tags=tags, platform="adsense"))
    assert "#에어프라이어 추천 #주방가전" in md_ads


def test_export_naver_plain_text():
    # v19: 네이버는 플레인 텍스트 — 마크다운 기호 금지, [제목]/[본문]/[태그] 구조
    draft = _draft(
        platform="naver",
        body="에어프라이어 추천 기준\n\n내용입니다. 선택 기준을 정리합니다.\n\n"
             "자주 묻는 질문\n\nQ. 세척은?\nA. 분리 세척입니다.\n",
        tags=json.dumps(["에어프라이어 추천"], ensure_ascii=False),
        thumbnail_ideas=json.dumps(["컨셉1", "컨셉2"], ensure_ascii=False))
    md = build_export_markdown(draft)
    assert md.startswith("[제목]\n에어프라이어 추천 기준")
    assert "[본문]" in md and "[태그]" in md
    assert "[썸네일 아이디어]" in md and "1. 컨셉1" in md
    assert "##" not in md and "**" not in md and "|" not in md


def test_export_thumbnail_ideas_markdown():
    draft = _draft(thumbnail_ideas=json.dumps(["컨셉A"], ensure_ascii=False))
    md = build_export_markdown(draft)
    assert "**썸네일 아이디어:**" in md and "1. 컨셉A" in md


def test_export_without_tags_omits_section():
    assert "태그:" not in build_export_markdown(_draft())
    assert "태그:" not in build_export_markdown(_draft(tags="not json"))


def test_export_brand_adds_indirect_cta():
    md = build_export_markdown(_draft(platform="brand"))
    assert "관련 서비스/제품 페이지" in md


def test_export_defaults_to_naver_when_platform_missing():
    # v19: 구버전 초안(platform 없음)은 네이버 플레인 텍스트로 처리
    draft = _draft()
    draft.pop("platform")
    md = build_export_markdown(draft)
    assert md.startswith("[제목]")


def test_export_product_block_per_platform(monkeypatch):
    # v21(B.4): 상품 블록 렌더링 — 네이버=링크 텍스트, 마크다운=링크 리스트
    products = json.dumps([{
        "title": "에어프라이어 5L",
        "link": "https://shopping.naver.com/gold/gold.naver?productId=9581015846",
        "image": "", "price": 15000, "mall": "가전스토어"}], ensure_ascii=False)
    monkeypatch.setenv("SHOPPING_CONNECT_PID", "983190190858208")
    naver = build_export_markdown(_draft(platform="naver", product_block=products))
    assert "[관련 상품]" in naver
    assert "brandconnect.naver.com/affiliates/983190190858208" in naver
    assert "에어프라이어 5L — 15,000원" in naver
    # v22.1: 네이버 플레인 텍스트는 마크다운 마커('- ') 금지 — 숫자 넘버링
    assert "1. 에어프라이어 5L" in naver
    assert "\n- " not in naver
    tistory = build_export_markdown(_draft(platform="tistory", product_block=products))
    assert "## 관련 상품" in tistory
    assert "[(보러 가기)]" in tistory
    # 상품 블록 없으면 섹션 미생성
    assert "관련 상품" not in build_export_markdown(_draft())


def test_export_product_block_bad_json_omitted():
    md = build_export_markdown(_draft(platform="tistory", product_block="not json"))
    assert "관련 상품" not in md
