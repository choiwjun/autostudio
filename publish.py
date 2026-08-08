# publish.py — v17: 게시 파이프라인 (고도화 3)
# 네이버 블로그는 쓰기 공개 API가 없어 게시는 수동일 수밖에 없다 — 대신
# '붙여넣기 직전 상태'의 마크다운 문서를 만들어 복붙 마찰을 최소화한다.
# 대표·섹션 이미지는 해당 위치 마크다운 이미지 구문으로 삽입된다.
import json


def build_export_markdown(draft):
    """초안 dict → 게시용 마크다운 문자열.
    구조: H1 제목 → 대표 이미지 → 첫문단 → 본문(H2 직후 섹션 이미지 삽입).
    이미지 URL은 애드포스트/SEO에서 바로 렌더링 가능한 외부 URL."""
    lines = [f"# {draft['title']}", ""]
    urls = []
    if draft.get("section_images"):
        try:
            parsed = json.loads(draft["section_images"])
            if isinstance(parsed, list):
                urls = [u for u in parsed if u]
        except json.JSONDecodeError:
            urls = []
    if draft.get("image_url"):
        lines += [f"![대표 이미지]({draft['image_url']})", ""]
    lines += [draft["first_paragraph"], ""]
    img_i = 0
    for line in (draft.get("body") or "").splitlines():
        lines.append(line)
        is_section_h2 = (
            line.startswith("## ") and "자주 묻는 질문" not in line)
        if is_section_h2 and img_i < len(urls):
            img_i += 1
            lines += ["", f"![섹션 이미지 {img_i}]({urls[img_i - 1]})", ""]
    # v17.2: 태그 — 본문 끝 첨부, 네이버 블로그 태그란에 그대로 입력
    tags = []
    if draft.get("tags"):
        try:
            parsed = json.loads(draft["tags"])
            if isinstance(parsed, list):
                tags = [t for t in parsed if t]
        except json.JSONDecodeError:
            tags = []
    if tags:
        lines += ["", "---", "", "태그: " + ", ".join(tags)]
    return "\n".join(lines).rstrip() + "\n"
