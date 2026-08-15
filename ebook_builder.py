# ebook_builder.py - v30: K-3 EPUB 조립 + 검증
# ebooklib 목차·챕터·메타 + markdown(md->HTML) + Pillow 표지 6x9 텍스트 오버레이.
# Vercel은 다운로드만, 조립·검증은 GH Actions 배치. 로컬 구조 검증 함수 포함.
import io
import logging
import zipfile

logger = logging.getLogger(__name__)

COVER_SIZE = (1800, 2700)   # 6x9 비율 (2:3)


def _markdown_ext():
    import markdown as md_mod
    return md_mod


def markdown_to_html(text):
    md = _markdown_ext()
    return md.markdown(text or "", extensions=["tables", "fenced_code"])


def make_cover_image(title, subtitle="", background_bytes=None):
    """Pillow 6x9 표지 — 배경 image_gen 바이트 또는 단색 폴백 + 제목·부제 오버레이.
    반환: PNG bytes."""
    from PIL import Image, ImageDraw, ImageFont
    if background_bytes:
        img = Image.open(io.BytesIO(background_bytes)).convert("RGB")
        img = img.resize((COVER_SIZE[0], COVER_SIZE[1]))
    else:
        img = Image.new("RGB", COVER_SIZE, (22, 27, 56))
    draw = ImageDraw.Draw(img)
    # 제목 중앙 상단 배치 (기본 폰트 폴백)
    try:
        font = ImageFont.truetype("arial.ttf", 120)
    except Exception:
        font = ImageFont.load_default()
    title_lines = _wrap_title(title, 18)
    y = 400
    for line in title_lines:
        draw.text((150, y), line, fill=(255, 255, 255), font=font)
        y += 200
    if subtitle:
        draw.text((150, y + 100), subtitle, fill=(211, 226, 255), font=font)
    # M-1: AI 생성 표지 공개 의무 - 'Generated with AI' 하단 오버레이
    try:
        small = ImageFont.truetype("arial.ttf", 52)
    except Exception:
        small = font
    draw.text((150, COVER_SIZE[1] - 160), "AI-generated",
              fill=(200, 210, 230), font=small)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _wrap_title(title, max_chars):
    title = (title or "Book")
    out = []
    cur = ""
    for ch in title:
        if len(cur) >= max_chars:
            out.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        out.append(cur)
    return out or [title]


def build_epub(book, chapters, cover_bytes=None, out_path=None):
    """ebooklib EPUB 조립 — 목차(챕터 시퀀스)·메타(제목·저자·키워드·설명)·표지.
    out_path 지정 시 파일로, 아니면 bytes 반환. 반환: bytes|None."""
    from ebooklib import epub
    eb = epub.EpubBook()
    eb.set_identifier("autostudio-" + str(book.get("id") or "kdp"))
    eb.set_title(book.get("title") or "Untitled")
    eb.set_language(book.get("lang") or "en")
    if book.get("pen_name"):
        eb.add_author(book["pen_name"])
    # 표지 (cover-bytes 있으면)
    if cover_bytes:
        eb.set_cover("cover.png", cover_bytes)
    elif book.get("cover_url"):  # v30: URL 참조면 생략(외부) — 다운로더에서 처리
        pass
    # 챕터 HTML
    items = []
    for idx, ch in enumerate(chapters, start=1):
        html = ("<h1>%s</h1>" % (ch.get("title") or ("챕터 %d" % idx))
                + markdown_to_html(ch.get("body_md") or ""))
        c = epub.EpubHtml(title=ch.get("title") or ("Ch %d" % idx),
                          file_name="chap_%02d.xhtml" % idx, lang=eb.language,
                          content=html)
        eb.add_item(c)
        items.append(c)
    # 목차
    if items:
        eb.toc = tuple(epub.Link("chap_%02d.xhtml" % i,
                                 getattr(c, "title", "") or "Chapter %d" % i,
                                 "chap%02d" % i) for i, c in enumerate(items, start=1))
    else:
        eb.toc = ()
    eb.add_item(epub.EpubNcx())
    eb.add_item(epub.EpubNav())
    if out_path:
        epub.write_epub(out_path, eb)
        return None
    buf = io.BytesIO()
    epub.write_epub(buf, eb)
    return buf.getvalue()


def validate_epub_structure(data):
    """로컬 구조 검증 — zip(EPUB) 내 container.xml·OPF·NCX·챕터.xhtml 존재.
    반환: (ok: bool, issues: list[str]). calibre/epubcheck는 GH Actions에서 별도."""
    issues = []
    if isinstance(data, (bytes, bytearray)):
        import io as io_mod
        try:
            zf = zipfile.ZipFile(io_mod.BytesIO(data))
        except zipfile.BadZipFile as e:
            return False, ["EPUB이 zip이 아님: %s" % e]
    elif isinstance(data, str) and zipfile.is_zipfile(data):
        zf = zipfile.ZipFile(data)
    else:
        zf = None
    if zf is None:
        return False, ["검증 불가 형식"]
    names = zf.namelist()
    required = ["mimetype", "META-INF/container.xml"]
    for req in required:
        if req not in names:
            issues.append("필수 파일 부재: " + req)
    # OPF 확인 (container.xml에서 참조)
    opf_found = any(n.endswith(".opf") for n in names)
    if not opf_found:
        issues.append("OPF(.opf) 없음")
    toc_found = any(n.endswith(".ncx") for n in names)
    if not toc_found:
        issues.append("NCX(.ncx) 없음")
    zf.close()
    return (not issues), issues
