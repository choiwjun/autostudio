# publish.py — v17: 게시 파이프라인 (고도화 3)
# 네이버 블로그는 쓰기 공개 API가 없어 게시는 수동일 수밖에 없다 — 대신
# '붙여넣기 직전 상태'의 문서를 만들어 복붙 마찰을 최소화한다.
# v19: 플랫폼별 내보내기 — 네이버(플레인 텍스트) / 티스토리(마크다운+목차+FAQ) /
#      애드센스(마크다운) / 브랜드(마크다운+간접 CTA). 태그 형식도 플랫폼별 분기.
import json

import platforms as platforms_mod


def _json_list(raw):
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


def _section_heading_lines(body):
    """마크다운 본문의 H2 소제목 행 — 목차 생성용."""
    return [ln[3:].strip() for ln in (body or "").splitlines()
            if ln.startswith("## ") and "자주 묻는 질문" not in ln]


def _image_lines(draft, marker, label):
    urls = [u for u in _json_list(draft.get("section_images")) if u]
    lines = []
    if draft.get("image_url"):
        lines += [f"![{label}]({draft['image_url']})", ""]
    img_i = 0
    for line in (draft.get("body") or "").splitlines():
        lines.append(line)
        if line.startswith("## ") and "자주 묻는 질문" not in line and img_i < len(urls):
            lines += ["", f"![섹션 이미지 {img_i + 1}]({urls[img_i]})", ""]
            img_i += 1
    return lines


def _thumbnail_ideas_block(draft, platform):
    ideas = _json_list(draft.get("thumbnail_ideas"))
    if not ideas:
        return ""
    header = "[썸네일 아이디어]" if platform == "naver" else "**썸네일 아이디어:**"
    lines = [header]
    for i, idea in enumerate(ideas, 1):
        lines.append(f"{i}. {idea}")
    return "\n".join(lines)


def _export_naver(draft):
    lines = ["[제목]", draft["title"], "",
             "[본문]", draft["first_paragraph"], ""]
    lines += (draft.get("body") or "").splitlines()
    tags = platforms_mod.format_tags(_json_list(draft.get("tags")), "naver")
    if tags:
        lines += ["", "[태그]", tags]
    block = _thumbnail_ideas_block(draft, "naver")
    if block:
        lines += ["", block]
    return "\n".join(lines).rstrip() + "\n"


def _export_tistory(draft):
    headings = _section_heading_lines(draft["body"])
    lines = [f"# {draft['title']}", "",
             f"> **한줄 요약:** {draft['first_paragraph']}", ""]
    if headings:
        lines += ["**목차**"] + [f"{i + 1}. {h}" for i, h in enumerate(headings)] + ["", "---", ""]
    lines += _image_lines(draft, "본문", "대표 이미지")
    tags = platforms_mod.format_tags(_json_list(draft.get("tags")), "tistory")
    if tags:
        lines += ["", "---", "", "**태그:** " + tags]
    block = _thumbnail_ideas_block(draft, "tistory")
    if block:
        lines += ["", block]
    return "\n".join(lines).rstrip() + "\n"


def _export_markdown(draft, platform):
    lines = [f"# {draft['title']}", "", draft["first_paragraph"], ""]
    lines += _image_lines(draft, "본문", "대표 이미지")
    if platform == "brand":
        lines += ["", "더 자세한 내용이 궁금하시다면 관련 서비스/제품 페이지를 확인해 보세요.", ""]
    tags = platforms_mod.format_tags(_json_list(draft.get("tags")), platform)
    if tags:
        lines += ["", "---", "", "**태그:** " + tags]
    block = _thumbnail_ideas_block(draft, platform)
    if block:
        lines += ["", block]
    return "\n".join(lines).rstrip() + "\n"


def build_export_markdown(draft, platform=None):
    """초안 dict → 플랫폼별 게시용 문서 문자열.
    플랫폼: naver(플레인 텍스트) / tistory(마크다운+목차+FAQ) /
    adsense·brand(마크다운). 미지정 시 초안의 platform 필드 사용."""
    platform = platform or draft.get("platform") or platforms_mod.DEFAULT_PLATFORM
    if platform == "naver":
        return _export_naver(draft)
    if platform == "tistory":
        return _export_tistory(draft)
    return _export_markdown(draft, platform)
