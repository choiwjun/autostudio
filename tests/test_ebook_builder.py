# v30: K-3 EPUB 조립 + 검증 (test_ebook_builder.py) - T-K3-01~04
import db
import ebook_builder as eb


def make_db(tmp_path):
    d = db.Database(f"sqlite:///{tmp_path / 't.db'}")
    d.init()
    return d


def _seed_book(d, pen="Pen Name"):
    return d.insert_kdp_book(title="52주 절약 챌린지 워크북", status="ready",
                             lang="en", pen_name=pen,
                             description="A workbook for saving.",
                             keywords_json='["a","b","c","d","e","f","g"]',
                             category="Finance, Money", source_keyword="절약",
                             created_at="2026-08-14")


def _seed_chapters(d, bid, n=3):
    for i in range(1, n + 1):
        d.insert_kdp_chapter(bid, seq=i, title=f"챕터 {i}",
                             body_md=f"## 섹션 {i}\n본문 내용 {i}.", word_count=900,
                             status="done")


def test_build_epub_returns_bytes(tmp_path):
    # T-K3-01: ebooklib 조립 → EPUB 바이트
    d = make_db(tmp_path)
    bid = _seed_book(d)
    _seed_chapters(d, bid)
    book = d.get_kdp_book(bid)
    chapters = d.list_kdp_chapters(bid)
    data = eb.build_epub(book, chapters, cover_bytes=None)
    assert isinstance(data, (bytes, bytearray))
    assert len(data) > 0
    # EPUB 시그니처 (PK = zip)
    assert data[:2] == b"PK"
    d.close()


def test_validate_epub_structure_local(tmp_path):
    # T-K3-03/04: 로컬 구조 검증 — OPF·목차·챕터 존재
    d = make_db(tmp_path)
    bid = _seed_book(d)
    _seed_chapters(d, bid)
    book = d.get_kdp_book(bid)
    chapters = d.list_kdp_chapters(bid)
    data = eb.build_epub(book, chapters, cover_bytes=None)
    ok, issues = eb.validate_epub_structure(data)
    assert ok is True
    assert not issues
    d.close()


def test_markdown_to_html_conversion():
    # md → HTML (테이블·fenced_code)
    html = eb.markdown_to_html("# 제목\n\n| a | b |\n|---|---|\n| 1 | 2 |")
    assert "<h1" in html and "<table" in html


def test_make_cover_image_6x9(tmp_path):
    # T-K3: Pillow 6×9 텍스트 오버레이 — 배경 mock(단색) → PNG bytes
    bg = eb.make_cover_image("절약", "52주 절약 챌린지 워크북",
                             background_bytes=None)
    assert bg[:4] == b"\x89PNG"
