# adpost.py — v17: 애드포스트 리포트 CSV → 성과 피드백 자동화 (고도화 1)
# 애드포스트 공개 API가 없어 리포트 CSV 내보내기를 섭취한다. 게시물별
# 수익·노출·클릭을 초안에 매칭(게시 URL → 제목 순)해 performance_score로
# 환산하고 키워드 priority 보정(기존 피드백 루프)에 자동으로 연결한다.
# 수익 = 유입 × 체류 × CPC 중 이 루프는 '실측 수익'으로 선순환을 닫는 마지막 고리.
import csv
import io
import re

# 성과 점수 만점 기준 — 신생 블로그 실측 대비 보수적 초기값.
# 데이터가 쌓이면 실측 분포에 맞춰 재보정 (percentile 임계와 동일한 철학).
REVENUE_FULL = 3000.0       # 원 — 게시물 월 수익 만점 기준
IMPRESSIONS_FULL = 5000.0   # 노출 만점 기준
CLICKS_FULL = 100.0         # 클릭 만점 기준

# 헤더 매칭은 부분문자열·대소문자 무관 (애드포스트 내보내기 양식 변동 흡수)
_TITLE_KEYS = ("게시물 제목", "게시물", "제목", "title")
_URL_KEYS = ("url", "링크", "주소")
_REVENUE_KEYS = ("수익", "revenue")
_IMPRESSION_KEYS = ("노출", "impression", "조회")
_CLICK_KEYS = ("클릭", "click")


def adpost_performance_score(revenue, impressions, clicks):
    """AdPost 지표 → 0~100 성과 점수 (수익 60 + 노출 25 + 클릭 15).
    boost_for_score 게이트(≥70/+10, <30/−10)와 정합하는 스케일."""
    return round(
        60.0 * min(1.0, max(0.0, revenue) / REVENUE_FULL)
        + 25.0 * min(1.0, max(0.0, impressions) / IMPRESSIONS_FULL)
        + 15.0 * min(1.0, max(0.0, clicks) / CLICKS_FULL), 1)


def _norm_header(header):
    return re.sub(r"\s+", "", (header or "").lower())


def _norm_url(url):
    return (url or "").strip().rstrip("/")


def _parse_number(raw):
    """'1,234원'·'12.5'·빈 문자열 → float (파싱 불가 0.0)."""
    cleaned = re.sub(r"[^\d.\-]", "", str(raw or ""))
    if not cleaned or cleaned in ("-", "."):
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _decode(raw_bytes):
    # 애드포스트 내보내기: UTF-8 BOM 또는 CP949 — 둘 다 시도
    for encoding in ("utf-8-sig", "cp949"):
        try:
            return raw_bytes.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw_bytes.decode("utf-8", errors="replace")


def parse_adpost_csv(raw_bytes):
    """AdPost 리포트 CSV 바이트 → 행 리스트.
    반환: [{'title', 'url', 'revenue', 'impressions', 'clicks'}].
    필수 열(제목/URL 중 하나 + 수익) 없으면 ValueError."""
    text = _decode(raw_bytes)
    reader = csv.reader(io.StringIO(text))
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    if not rows:
        raise ValueError("CSV가 비어 있습니다")
    header = [_norm_header(c) for c in rows[0]]

    def find(keys):
        for i, cell in enumerate(header):
            if any(key in cell for key in keys):
                return i
        return None

    title_i, url_i = find(_TITLE_KEYS), find(_URL_KEYS)
    revenue_i, imp_i, click_i = (
        find(_REVENUE_KEYS), find(_IMPRESSION_KEYS), find(_CLICK_KEYS))
    if title_i is None and url_i is None:
        raise ValueError("게시물 제목/URL 열을 찾을 수 없습니다")
    if revenue_i is None:
        raise ValueError("수익 열을 찾을 수 없습니다")
    parsed = []
    for row in rows[1:]:
        def cell(index):
            return row[index].strip() if index is not None and index < len(row) else ""
        title, url = cell(title_i), _norm_url(cell(url_i))
        if not title and not url:
            continue
        parsed.append({
            "title": title,
            "url": url,
            "revenue": _parse_number(cell(revenue_i)),
            "impressions": _parse_number(cell(imp_i)),
            "clicks": _parse_number(cell(click_i)),
        })
    return parsed
