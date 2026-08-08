# v17: 게시용 마크다운 내보내기 (고도화 3)
import json

from publish import build_export_markdown


def _draft(**over):
    base = {
        "title": "에어프라이어 추천 기준",
        "first_paragraph": "즉답 문단입니다.",
        "body": "## 섹션1\n내용1\n\n## 섹션2\n내용2\n\n## 자주 묻는 질문\n### q\na",
        "image_url": "",
        "section_images": "",
    }
    base.update(over)
    return base


def test_export_plain_structure():
    md = build_export_markdown(_draft())
    assert md.startswith("# 에어프라이어 추천 기준\n\n")
    assert "즉답 문단입니다." in md
    assert "## 섹션1" in md


def test_export_inserts_images_at_positions():
    draft = _draft(
        image_url="https://cdn.example.com/main.png",
        section_images=json.dumps(
            ["https://cdn.example.com/s1.png", "https://cdn.example.com/s2.png"]))
    md = build_export_markdown(draft)
    assert "![대표 이미지](https://cdn.example.com/main.png)" in md
    assert "![섹션 이미지 1](https://cdn.example.com/s1.png)" in md
    assert "![섹션 이미지 2](https://cdn.example.com/s2.png)" in md
    # 대표 이미지는 첫문단 앞, 섹션 이미지는 H2 직후
    assert md.index("대표 이미지") < md.index("즉답 문단입니다.")
    assert md.index("## 섹션1") < md.index("섹션 이미지 1") < md.index("## 섹션2")
    # FAQ 섹션에는 이미지 미삽입
    assert md.index("자주 묻는 질문") > md.index("섹션 이미지 2")


def test_export_survives_bad_section_json():
    draft = _draft(section_images="not json")
    md = build_export_markdown(draft)
    assert "## 섹션1" in md  # 이미지 없이 본문 유지


def test_export_includes_tags():
    # v17.2: 태그는 본문 끝 첨부 — 네이버 블로그 태그란에 그대로 붙여넣기
    draft = _draft(tags=json.dumps(
        ["에어프라이어 추천", "주방가전"], ensure_ascii=False))
    md = build_export_markdown(draft)
    assert "태그: 에어프라이어 추천, 주방가전" in md
    assert md.rstrip().endswith("태그: 에어프라이어 추천, 주방가전")


def test_export_without_tags_omits_section():
    assert "태그:" not in build_export_markdown(_draft())
    assert "태그:" not in build_export_markdown(_draft(tags="not json"))
