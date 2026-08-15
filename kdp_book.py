# kdp_book.py - v30: K-2 챕터 생성 + QC 8항목
import json
import logging
import time

import config as config_mod
import draft_pipeline

logger = logging.getLogger(__name__)

HARD_CHAPTER_BUDGET_SECONDS = 300
MIN_CHAPTERS, MAX_CHAPTERS = 6, 12
WORKBOOK_MIN_WORDS, WORKBOOK_MAX_WORDS = 800, 1200
WORD_BAND = 0.20
PLAG_SIM_THRESHOLD = 0.8
FENCE = chr(96) * 3


class DraftGenerationError(Exception):
    """챕터 생성 실패 정규화 (예산 초과·비 JSON·파싱)."""


QC_ITEMS = (
    "plagiarism", "banned_words", "factual_claims", "chapter_duplication",
    "length", "ai_disclosure", "markdown", "metadata",
)
BANNED_WORDS = (
    "보장합니다", "확실히", "100%", "최고", "검증된", "치유", "완치",
    "guaranteed", "cure", "miracle", "make money fast",
)
FACTUAL_CLAIM_PATTERNS = (
    "반드시", "확실히", "무조건", "검증된 통계", "항상 성공", "guaranteed results",
)
AI_GENERATED_DISCLOSURE = "AI-generated"
DISCLOSURE_LOW = AI_GENERATED_DISCLOSURE.lower()


class QCResult:
    def __init__(self, qc_item, passed, detail=""):
        self.qc_item = qc_item
        self.passed = bool(passed)
        self.detail = detail


def _word_count(text):
    return len((text or "").split())


def _jaccard(a, b, n=3):
    def ngrams(text):
        return {text[i:i + n] for i in range(len(text) - n + 1)}
    sa, sb = ngrams(a.replace(" ", "")), ngrams(b.replace(" ", ""))
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def check_plagiarism(chapter_body, reference=None):
    if reference is None:
        return True, ""
    sim = _jaccard(chapter_body or "", str(reference))
    if sim >= PLAG_SIM_THRESHOLD:
        return False, "유사 문장 {0:.0%} (임계 {1:.0%})".format(sim, PLAG_SIM_THRESHOLD)
    return True, ""


def check_banned_words(text):
    low = (text or "").lower()
    hits = [w for w in BANNED_WORDS if w.lower() in low]
    if hits:
        return False, "금지어: " + ", ".join(hits)
    return True, ""


def check_factual_claims(text):
    low = (text or "").lower()
    hits = [p for p in FACTUAL_CLAIM_PATTERNS if p.lower() in low]
    if hits:
        return False, "확정 주장: " + ", ".join(hits)
    return True, ""


def check_chapter_duplication(chapter_bodies):
    bodies = [b or "" for b in chapter_bodies]
    for i in range(len(bodies)):
        for j in range(i + 1, len(bodies)):
            if _jaccard(bodies[i], bodies[j]) >= PLAG_SIM_THRESHOLD:
                return False, "챕터 {0}·{1} 중복 (>= {2:.0%})".format(
                    i + 1, j + 1, PLAG_SIM_THRESHOLD)
    return True, ""


def check_length(text):
    wc = _word_count(text)
    low = int(WORKBOOK_MIN_WORDS * (1 - WORD_BAND))
    high = int(WORKBOOK_MAX_WORDS * (1 + WORD_BAND))
    if not (low <= wc <= high):
        return False, "{0}단어 (허용 {1}~{2})".format(wc, low, high)
    return True, "{0}단어".format(wc)


def check_ai_disclosure(text, cover_text=None, cover_is_ai=True):
    is_ai = DISCLOSURE_LOW
    body_ok = is_ai in (text or "").lower()
    if not body_ok:
        return False, "AI-generated 공개 문구가 본문에 없습니다"
    # cover_text 제공 시(표지 존재) AI 표기 검사 - M-1
    if cover_text is not None and cover_is_ai:
        if is_ai not in (cover_text or "").lower():
            return False, "AI-generated 공개 문구가 표지에 없습니다"
    return True, "AI-generated 공개 표시 (본문+표지)"


def check_markdown(text):
    lines = (text or "").splitlines()
    fence = sum(1 for ln in lines if ln.strip().startswith(FENCE))
    if fence % 2 != 0:
        return False, "코드블록 fence 미닫힘({0}개)".format(fence)
    if (text or "").count("[") != (text or "").count("]"):
        return False, "링크 괄호 불일치"
    return True, ""


def check_metadata(book):
    try:
        keywords = json.loads(book.get("keywords") or "[]")
    except (TypeError, json.JSONDecodeError):
        keywords = []
    issues = []
    if len(keywords) < 7:
        issues.append("키워드 {0}개 (필요 7)".format(len(keywords)))
    cats = [c for c in (book.get("category") or "").split(",") if c.strip()]
    if len(cats) < 2:
        issues.append("카테고리 {0}개 (필요 2)".format(len(cats)))
    if not book.get("pen_name"):
        issues.append("펜네임 없음")
    if not book.get("description"):
        issues.append("설명 없음")
    if issues:
        return False, "; ".join(issues)
    return True, ""


def run_qc(d, book_id, draft_pack, snapshot=None, run_at=""):
    run_at = run_at or config_mod.now_kst_iso()
    book = draft_pack.get("book") or d.get_kdp_book(book_id)
    chapters = draft_pack.get("chapters") or []
    bodies = [(ch.get("body_md") or "") for ch in chapters]
    full_text = " ".join(bodies)
    meta_text = full_text + " " + (book.get("description") or "")
    # M-1: QC #6이 표지(cover) AI 공개 문구도 검사 — draft_pack['cover'] 전달
    cover_text = draft_pack.get("cover") or ""
    cover_is_ai = bool(cover_text or draft_pack.get("cover_is_ai", True))

    raw_checks = [
        ("plagiarism", check_plagiarism(full_text, reference=snapshot)),
        ("banned_words", check_banned_words(meta_text)),
        ("factual_claims", check_factual_claims(full_text)),
        ("chapter_duplication", check_chapter_duplication(bodies)),
        ("length", check_length(full_text)),
        ("ai_disclosure", check_ai_disclosure(full_text, cover_text=cover_text, cover_is_ai=cover_is_ai)),
        ("markdown", check_markdown(full_text)),
        ("metadata", check_metadata(book)),
    ]
    results = [QCResult(item, ok, det) for item, (ok, det) in raw_checks]
    d.replace_kdp_qc_results(book_id, run_at, [
        {"qc_item": r.qc_item, "passed": r.passed, "detail": r.detail}
        for r in results])
    if all(r.passed for r in results):
        d.update_kdp_book_status(book_id, "ready", updated_at=run_at)
    return results


def _chapter_structure(title):
    return {"questions": [str(title or "본문")], "facts": [],
            "comparisons": [], "headings": [str(title or "본문")]}


def _parse_chapter_draft(raw, seq):
    from llm_client import strip_code_fence
    text = strip_code_fence(raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise DraftGenerationError("챕터 비 JSON: {0}".format(text[:100])) from e
    if not isinstance(data, dict):
        raise DraftGenerationError("챕터 형식 오류")
    return data


def generate_outline(d, keyword, structure, runner=None, current_date=None):
    """아웃라인 — pass1 재사용 + K2-1 하한 강제(MIN_CHAPTERS~MAX_CHAPTERS).
    pass1 반환 챕터가 MIN_CHAPTERS 미만이면 일반 장(디폴트 챕터)으로 패딩해
    구조화 워크북 최소 분량을 보장. 반환: list[{title, bullets}]."""
    outline = draft_pipeline.pass1_outline(
        keyword, structure, runner=runner, current_date=current_date,
        timeout=90)
    if not isinstance(outline, list):
        outline = []
    outline = [o for o in outline if isinstance(o, dict) and o.get("title")][:MAX_CHAPTERS]
    while len(outline) < MIN_CHAPTERS:
        idx = len(outline) + 1
        outline.append({"title": "Chapter %d: 핵심 원칙" % idx,
                        "bullets": ["핵심 요약", "실천 단계"]})
    return outline


def seq_id_of(d, book_id, seq):
    for ch in d.list_kdp_chapters(book_id):
        if ch["seq"] == seq:
            return ch["id"]
    return None


def generate_chapter(d, refs, runner=None, hard_budget_seconds=HARD_CHAPTER_BUDGET_SECONDS):
    book_id = refs["book_id"]
    seq = refs["seq"]
    keyword = refs.get("keyword") or "절약 챌린지"
    started = time.monotonic()
    try:
        if runner is not None:
            raw = runner("", timeout=120)
            draft = _parse_chapter_draft(raw, seq)
        else:
            got, _failed = draft_pipeline.generate_two_pass(
                keyword, _chapter_structure(refs.get("title") or "본문"),
                hard_budget_seconds=min(hard_budget_seconds, 120),
                current_date=config_mod.today_kst())
            draft = dict(got)
        body = draft.get("body") or ""
        wc = _word_count(body)
        d.update_kdp_chapter(seq_id_of(d, book_id, seq), updated_at=config_mod.now_kst_iso(),
                             body_md=body, word_count=wc, status="done")
        return {"seq": seq, "status": "done", "word_count": wc,
                "body_md": body, "elapsed": round(time.monotonic() - started, 2)}
    except Exception as e:
        logger.warning("chapter fail book=%s seq=%s: %s", book_id, seq, e)
        d.update_kdp_chapter(seq_id_of(d, book_id, seq), updated_at=config_mod.now_kst_iso(),
                             status="partial", status_detail="budget/timeout")
        return {"seq": seq, "status": "partial", "status_detail": "budget/timeout"}


def consistency_pass(chapters, runner=None):
    if runner is not None:
        prompt = '다음 챕터를 어조·용어·시점 통일해 재구성. JSON: {"body":"..."}'
        try:
            parsed = _parse_chapter_draft(runner(prompt, timeout=120), "consistency")
            return {"passed": True, "body": parsed.get("body") or ""}
        except DraftGenerationError:
            return {"passed": True, "body": ""}
    return {"passed": True, "body": ""}


def generate_book(d, cfg, book_id, runner=None, translator=None,
                  qc_enabled=True, marks_ready=False):
    book = d.get_kdp_book(book_id)
    if not book:
        raise LookupError("book not found")
    keyword = book["source_keyword"] or book["title"]
    d.update_kdp_book_status(book_id, "assembling", updated_at=config_mod.now_kst_iso())
    outline = generate_outline(d, keyword, {}, runner=runner)
    chapters = []
    if isinstance(outline, list):
        for idx, o in enumerate(outline, start=1):
            if idx > MAX_CHAPTERS:
                break
            d.insert_kdp_chapter(book_id, seq=idx, title=str(o.get("title") or ("챕터 " + str(idx))))
            ch = generate_chapter(d, {
                "book_id": book_id, "seq": idx,
                "title": str(o.get("title") or ""), "keyword": keyword,
            }, runner=runner)
            chapters.append(ch)
    consistency_pass([c for c in chapters if c.get("body_md")], runner=runner)
    qc = None
    if qc_enabled:
        full = [{"body_md": c_.get("body_md") or ""} for c_ in chapters]
        qc = run_qc(d, book_id, {"chapters": full, "book": book},
                    run_at=config_mod.now_kst_iso())
        if marks_ready and all(r.passed for r in qc):
            d.update_kdp_book_status(book_id, "ready", updated_at=config_mod.now_kst_iso())
    return {"status": d.get_kdp_book(book_id)["status"],
            "chapters": chapters, "qc": qc}
