# kdp_research.py — v30: K-1 주제 선정
# '곧 뜰' 프리셋 키워드 + 아마존 검색 스냅샷 → 책 주제 후보 산출.
# - 영어 현지화: 기본 rule 기반(결정성, 테스트) + LLM 번역 폴백(runner 주입)
# - 아마존 공개 API 없음 → 검색 결과 HTML/JSON 파싱(스냅샷), 실패 시 graceful 폴백
# - 틈새 판정(경쟁 적음 + 수요 있음) + 전환율 30% 게이트 → KDP KR 한국어 병행(K-2)
import json
import logging

logger = logging.getLogger(__name__)

CONVERSION_GATE = 0.3  # 영어 전환율 미만 시 한국어 병행 비중 확대 (AC-K1-1④)
SNAPSHOT_TOP = 20      # 아마존 상위 20권 (12-kdp §4)


class AmazonSnapshotError(Exception):
    """아마존 검색 스냅샷 파싱·수신 실패 — graceful 폴백 대상."""


# v30: 카테고리→영어 도메인 매핑 (rule 기반 현지화 재료)
_L10N_RULES = [
    # (한글 토큰, 영어 도메인 후보)
    ("절약", ["saving"]),
    ("저축", ["saving"]),
    ("52주", ["52 week"]),
    ("챌린지", ["challenge"]),
    ("다이어트", ["diet"]),
    ("요가", ["yoga"]),
    ("걷기", ["walking"]),
    ("명상", ["mindfulness", "meditation"]),
    ("일기", ["journal", "diary"]),
    ("AI", ["AI"]),
    ("인공지능", ["AI"]),
    ("투자", ["investing"]),
    ("주식", ["stock"]),
    ("재테크", ["money", "personal finance"]),
    ("부동산", ["real estate"]),
    ("임대", ["rental"]),
    ("요리", ["cooking", "recipe"]),
    ("운동", ["fitness", "exercise"]),
    ("영어", ["english"]),
    ("초보", ["beginner", "for beginners"]),
    ("가이드", ["guide"]),
    ("워크북", ["workbook"]),
]

_DEFAULT_CATEGORY_EN = {
    "금융": "Personal Finance", "재테크": "Money", "건강": "Health",
    "IT": "Technology", "교육": "Self-Help", "요리": "Cooking",
    "부동산": "Real Estate", "여행": "Travel", "자기계발": "Self-Help",
}


def _run_llm_translate(prompt):
    """기본 LLM 번역 — 이 모듈에서는 import 지연으로 사용 (외부 키 미설정 시 오류 전파)."""
    import llm_client
    from llm_client import strip_code_fence
    raw = llm_client._run_llm(prompt)
    text = strip_code_fence(raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise AmazonSnapshotError(f"번역 결과가 JSON이 아닙니다: {raw[:120]}") from e
    if not isinstance(data, dict):
        raise AmazonSnapshotError("번역 결과 형식 오류")
    return data


def _rule_english_parts(keyword):
    """rule 기반 영어 근사어 — 매칭된 토큰 집합 반환(빈 리스트 = 미적중)."""
    parts = []
    for token, en in _L10N_RULES:
        if token in keyword:
            parts.extend(en)
    # 중복 제거 + 순서 유지
    seen = set()
    out = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def english_candidate(keyword, category, translator=None, snapshot=None):
    """영어 현지화 후보 산출.
    rule 힌트가 있으면 제목·키워드 구성(완전 결정성). 힌트가 없으면 translator 폴백.
    snapshot이 있고 items가 비어 있으면 수요 미검증 → None(제외). 반환 dict|None.
    v31 (알고리즘 QA): 키워드 7개·카테고리 2개 저장 — kdp_book.check_metadata
    (7키워드/2카테고리 요구)와 서버 출간 체크리스트가 research 산출물을
    통과할 수 있게 저장값을 요구치에 정합 (기존 5/1개 저장이 QC를 영구 실패시킴)."""
    if snapshot is not None and not snapshot.get("items"):
        return None  # T-K1-02: 검색 0건 → 수요 미검증 → 후보 제외
    parts = _rule_english_parts(keyword)
    if parts:
        topic = " ".join(dict.fromkeys(parts))[:60]
        title = f"{topic} Workbook: A Complete Guide for Beginners".strip()
        return {
            "title": title,
            "keywords": _pad_keywords(
                [topic, "workbook", "guide", "beginner",
                 category_en(category)], category_en(category)),
            "category": f"{category_en(category)},Education",
            "lang": "en",
        }
    if translator is None:
        return None  # rule 미적중 + 번역기 없음 → 한국어 병행 후보로
    # LLM 번역 폴백
    prompt = (
        "다음 키워드를 아마존 KDP 책 주제 후보로 영어로 변환해라. "
        "키워드: " + keyword + " (분야: " + category + ") "
        + 'JSON만 반환: {"title": "영어 책 제목", "keywords": ["영어 키워드 3~7개"], '
        + '"category": "영어 카테고리 1개"}'
    )
    data = translator(prompt)
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as e:
            raise AmazonSnapshotError(f"번역 결과가 JSON이 아닙니다: {data[:80]}") from e
    if not isinstance(data, dict):
        raise AmazonSnapshotError("번역 결과 형식 오류")
    cat = str(data.get("category") or category_en(category))
    return {
        "title": str(data.get("title") or keyword),
        "keywords": _pad_keywords(
            [str(k) for k in (data.get("keywords") or []) if str(k).strip()][:7],
            cat),
        "category": f"{cat},Education",
        "lang": "en",
    }


def category_en(category):
    return _DEFAULT_CATEGORY_EN.get(category, category or "Self-Help")


def _pad_keywords(keywords, fallback_token="workbook"):
    """v31 (알고리즘 QA): KDP 출간 요구 키워드 7개 하한 — 부족분을 무난한
    일반 키워드로 결정적 패딩 (LLM 산출이 3개만 와도 QC/체크리스트 통과)."""
    base = [k for k in keywords if str(k).strip()]
    for filler in ("workbook", "guide", "beginners", "self-study",
                   "practice", "exercises", "how-to"):
        if len(base) >= 7:
            break
        if filler not in base:
            base.append(filler)
    while len(base) < 7:  # fallback_token 조차 중복인 극단 경계
        if len(base) >= 7:
            break
        base.append(f"{fallback_token} {len(base)}")
    return base[:7]


def korean_candidate(keyword, category, snapshot=None):
    """K-2: KDP KR 한국어 전자책 병행 후보 (영어 수요 낮음/현지화 어려움 시).
    v31 (알고리즘 QA): 영어 후보와 동일하게 키워드 7개·카테고리 2개 정합."""
    if snapshot is not None and not snapshot.get("items"):
        return None
    cat = category or "기타"
    return {
        "title": f"{keyword} 워크북",
        "keywords": [k for k in (keyword, cat, "가이드", "초보", "실습", "독학",
                                 "문제집") if k and str(k).strip()][:7],
        "category": f"{cat},교육",
        "lang": "ko",
    }


def fetch_snapshot(query, fetcher=None):
    """아마존 검색 경쟁도 스냅샷 — 상위 20권 가격·평점·권수.
    공개 API 없음 → fetcher(기본 requests HTML/JSON 파싱). 실패 시 graceful 폴백(unavailable)."""
    if fetcher is None:
        fetcher = _fetch_snapshot_http
    try:
        return fetcher(query)
    except AmazonSnapshotError as e:
        logger.warning("amazon snapshot unavailable query=%s: %s", query, e)
        return {"status": "unavailable", "searched_at_kst": "", "items": []}


SNAPSHOT_TIMEOUT = 20
SNAPSHOT_MAX_BYTES = 5 * 1024 * 1024   # 응답 크기 상한 (5MB)
SNAPSHOT_MAX_REDIRECTS = 3             # 수동 리다이렉트 상한


def _fetch_snapshot_http(query):
    """아마존 검색 페이지 HTTP GET + 상위 20권 파싱 (M-4 하드닝).
    - URL 인코딩: urllib.parse.quote로 query를 쿼리 파라미터에 안전 삽입
    - 리다이렉트: allow_redirects=False + https 한정 수동(최대 3회), 비HTTPS 거부
    - 크기 상한: 스트리밍 SNAPSHOT_MAX_BYTES 초과 시 거부
    실패 시 AmazonSnapshotError로 graceful 폴백."""
    from urllib.parse import quote
    import requests
    base = "https://www.amazon.com/s?k="
    current = base + quote(query, safe="")
    seen = 0
    while seen <= SNAPSHOT_MAX_REDIRECTS:
        try:
            resp = requests.get(
                current, timeout=SNAPSHOT_TIMEOUT, allow_redirects=False,
                stream=True,
                headers={"User-Agent": "Mozilla/5.0 (KDP research)",
                         "Accept-Language": "en-US"})
        except requests.RequestException as e:
            raise AmazonSnapshotError("amazon request failed: %s" % e) from e
        if resp.status_code in (301, 302, 303, 307, 308):
            loc = resp.headers.get("Location", "")
            if not loc.startswith("https://"):
                raise AmazonSnapshotError("아마존 리다이렉트가 HTTPS가 아닙니다")
            current = loc
            seen += 1
            continue
        if resp.status_code != 200:
            raise AmazonSnapshotError("amazon status %d" % resp.status_code)
        chunks, size, done = [], 0, False
        with resp:
            for chunk in resp.iter_content(chunk_size=65536):
                size += len(chunk)
                if size > SNAPSHOT_MAX_BYTES:
                    done = True
                    break
                chunks.append(chunk)
        if done:
            raise AmazonSnapshotError("아마존 응답이 크기 상한 초과")
        html = b"".join(chunks).decode("utf-8", errors="replace")
        items = _parse_snapshot_html(html, query)
        if not items:
            raise AmazonSnapshotError("no parseable results")
        return {"status": "available", "searched_at_kst": "", "items": items}
    raise AmazonSnapshotError("redirect limit exceeded")


def _parse_snapshot_html(html, query):
    """HTML에서 상위 20권 (제목·가격·평점·리뷰·권수) 파싱 — 경량 파서(클래스 힌트).
    실제 필요한 건 수요/경쟁 판정용 수치이므로, 못 찾으면 빈 리스트 → 실패 폴백."""
    import re
    items = []
    for m in re.finditer(r'data-asin="([A-Z0-9]{10})"', html):
        asin = m.group(1)
        if asin in {it.get("asin") for it in items}:
            continue
        items.append({"asin": asin, "title": "", "price": None,
                      "rating": None, "reviews": None})
        if len(items) >= SNAPSHOT_TOP:
            break
    return items


def niche_score(snapshot_rows):
    """틈새 판정 — 경쟁 적음(권수 0·리뷰 적음·평점 낮음) + 수요 있음(도서 존재).
    score ∈ [0,1], 높을수록 틈새(경쟁 낮음). rows: {price, rating, reviews}."""
    rows = list(snapshot_rows or [])
    if not rows:
        return {"score": 1.0, "books": 0, "avg_rating": 0.0, "avg_reviews": 0}
    n = len(rows)
    avg_reviews = sum(float(r.get("reviews") or 0) for r in rows) / n
    avg_rating = sum(float(r.get("rating") or 0) for r in rows) / n
    # 가중: 권수 적음(1 - n/SNAPSHOT_TOP), 리뷰 적음, 평점 낮음 → 경쟁 낮음
    review_penalty = min(1.0, avg_reviews / 500.0)     # 리뷰 많으면 경쟁 ↑
    rating_penalty = min(1.0, avg_rating / 5.0)        # 평점 높으면 경쟁 ↑
    book_penalty = min(1.0, n / float(SNAPSHOT_TOP))   # 도서 많으면 경쟁 ↑
    score = round(1.0 - 0.5 * book_penalty - 0.3 * review_penalty - 0.2 * rating_penalty, 3)
    return {"score": score, "books": n, "avg_rating": avg_rating,
            "avg_reviews": avg_reviews}


DEFAULT_PEN_NAME_EN = "AutoStudio Press"
DEFAULT_PEN_NAME_KO = "오토스튜디오"


def _default_description(c):
    title = c.get("title") or ""
    if c.get("lang") == "ko":
        return f"{title} — 초보자를 위한 단계별 실습 워크북."
    return f"{title} — a step-by-step practice workbook for beginners."


def run_research(d, cfg, keywords, snapshot_fetcher=None, translator=None, limit=10):
    """K-1 주제 선정 본 로직. keywords: [(keyword, category), ...].
    각 키워드 → 영어/한국어 양쪽 후보 산출 → 틈새·스냅샷 검증 → kdp_books 저장.
    반환 {candidates, conversion_rate, suggestion, skipped}.
    v31 (알고리즘 QA): snapshot_fetcher 미지정 시에도 기본 HTTP fetcher로 스냅샷을
    시도 — 기존 `if snapshot_fetcher else None`이 배치 경로의 검증을 전면
    생략해 모든 후보가 score=1.0(경쟁 0)으로 저장됐음. 스냅샷 'unavailable'
    (차단·장애)은 '검증됐고 0건'과 구분해 후보 제외 대신 미검증 마킹."""
    candidates = []
    skipped = []
    for keyword, category in keywords:
        snap = fetch_snapshot(keyword, snapshot_fetcher)
        verified = snap if snap and snap.get("status") != "unavailable" else None
        en = english_candidate(keyword, category, translator=translator, snapshot=verified)
        if en:
            en["niche"] = niche_score(snap["items"] if snap else [])
            en["snapshot_status"] = snap.get("status", "skipped") if snap else "skipped"
            en["source_keyword"] = keyword  # R-1: 후보별 원본 키워드 추적
            candidates.append(en)
        # 영어 미적중(수요 없음/현지화 불가) → 한국어 병행 후보
        ko = korean_candidate(keyword, category, snapshot=verified)
        if en is None and ko:
            ko["niche"] = niche_score(snap["items"] if snap else [])
            ko["snapshot_status"] = snap.get("status", "skipped") if snap else "skipped"
            ko["source_keyword"] = keyword  # R-1: 후보별 원본 키워드 추적
            candidates.append(ko)
        elif en is None and ko is None:
            skipped.append(keyword)
        # 수요 미검증(스냅샷 0건) → en/ko 모두 None → skipped
    total = len(keywords) or 1
    en_count = sum(1 for c in candidates if c.get("lang") == "en")
    conversion_rate = round(en_count / total, 3)
    suggestion = ""
    if conversion_rate < CONVERSION_GATE:
        suggestion = ("영어 전환율이 {:.0%}로 낮습니다 — KDP KR 한국어 전자책 "
                      "병행 비중을 확대하세요.".format(conversion_rate))
    # 저장 (title UNIQUE — 중복 무시)
    # R-1: source_keyword에 원본 키워드 기록 — 배치 generate 스테이지가
    # 'source_keyword 있는 draft 책'을 대상으로 하므로 end-to-end 연결에 필수.
    # v31: pen_name/description 기본값 채움 — QC #8(metadata)가 이 둘을 요구.
    persisted = []
    for c in candidates[:limit]:
        pen = (DEFAULT_PEN_NAME_KO if c.get("lang") == "ko"
               else DEFAULT_PEN_NAME_EN)
        niche = dict(c.get("niche") or {})
        niche["snapshot_status"] = c.get("snapshot_status", "skipped")
        kid = d.insert_kdp_book(
            title=c["title"], status="draft", lang=c["lang"], priority=0.0,
            source_keyword=c.get("source_keyword", ""), created_at="",
            description=_default_description(c),
            pen_name=pen,
            keywords_json=json.dumps(c["keywords"], ensure_ascii=False),
            category=c["category"],
            evidence_json=json.dumps(niche, ensure_ascii=False))
        c["id"] = kid
        persisted.append(c)
    return {"candidates": persisted, "conversion_rate": conversion_rate,
            "suggestion": suggestion, "skipped": skipped}
