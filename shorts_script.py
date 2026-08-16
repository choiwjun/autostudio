# shorts_script.py — v31: 쇼츠 파이프라인 S-3 스크립트 생성 + 검수
# (docs/planning/14-shorts-pipeline.md §3.3)
#
# 설계 결정 (스펙 "draft_pipeline 2패스 재활용"의 실구현 해석):
# 블로그용 2패스(골격→확장)는 본문 3000자+ 전제라 80~120자 쇼츠 스크립트에는
# 부적합. kdp_book.generate_chapter과 동일하게 draft_generator의 러너/파싱
# 기반 요소(_run_llm·strip_code_fence·DraftGenerationError)만 재활용하고
# 생성+검수는 쇼츠 전용 단일 패스(실패 시 피드백 1회 재시도 — v14.1 패턴)로
# 구성한다.
#
# 쇼츠 규칙 (스펙 §3.3): 30~45초(한국어 80~120자) · 후킹 3초(VVSA 첫 1~2초
# 결정 근거) · CTA(구독/시리즈).
# 검수: 길이 · 후킹 존재 · CTA 존재 · 금지어 · 허위 주장.
# (문법검사 py-hanspell/LanguageTool와 TTS 음성·faster-whisper 자막은
# 파일럿 전 TTS 라이선스 게이트 통과 후 추가 — 스펙 §3.3/S-4 게이트)
import json
import logging

import config as config_mod

logger = logging.getLogger("shorts_script")

# --- 스펙 §3.3 규칙 상수 ---
SCRIPT_MIN_CHARS = 80          # 30~45초 한국어 하한
SCRIPT_MAX_CHARS = 120         # 상한
HOOK_MAX_CHARS = 40            # 후킹 3초 분량 상한
CTA_MARKERS = ("구독", "시리즈", "다음 편", "채널")
HASHTAG_MIN = 3
HASHTAG_MAX = 5
MAX_ATTEMPTS = 2               # v14.1 패턴 — 피드백 1회 재시도

# 금지어·허위 주장 — kdp_book.BANNED/FACTUAL 계열에서 쇼츠 과장 표현 중심 차용
BANNED_WORDS = (
    "보장합니다", "보장드립니다", "확실히", "무조건", "반드시", "100%",
    "최고의", "완벽한", "기적의", "cure", "miracle", "guaranteed",
)
FACTUAL_CLAIM_PATTERNS = (
    "검증된 통계", "입증된", "공식 조사 결과", "과학적으로 증명",
)

STATUS_READY = "ready"
STATUS_QC_FAILED = "qc_failed"


class ScriptGenerationError(Exception):
    """스크립트 생성 실패 정규화 (비 JSON·형식 오류·러너 장애)."""


def _parse_script(raw):
    """LLM 응답 → {hook, script, cta, hashtags}. 형식 오류는 정규화 예외로."""
    from llm_client import strip_code_fence
    text = strip_code_fence(raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ScriptGenerationError("비 JSON 응답: {0}".format(text[:100])) from e
    if not isinstance(data, dict):
        raise ScriptGenerationError("응답 형식 오류 (dict 아님)")
    return data


def _normalize_hashtags(raw):
    out = []
    for h in raw if isinstance(raw, list) else []:
        tag = str(h or "").strip().lstrip("#").strip()
        if tag:
            out.append("#" + tag)
    # 중복 제거 후 상한
    return list(dict.fromkeys(out))[:HASHTAG_MAX]


def validate_script(hook, script_md, cta, hashtags):
    """검수 5종 — 반환: (통과여부, 실패 코드 리스트).
    실패 코드는 재시도 피드백과 qc_detail 양쪽에 사용 (실측 주입, v14.1 패턴)."""
    failed = []
    total = len(script_md or "")
    if not (SCRIPT_MIN_CHARS <= total <= SCRIPT_MAX_CHARS):
        failed.append("length")
    hook = (hook or "").strip()
    if not hook or len(hook) > HOOK_MAX_CHARS:
        failed.append("hook")
    if not any(m in (cta or "") for m in CTA_MARKERS):
        failed.append("cta")
    text = "{0}\n{1}\n{2}".format(hook, script_md or "", cta or "").lower()
    if any(w.lower() in text for w in BANNED_WORDS):
        failed.append("banned_words")
    if any(p.lower() in text for p in FACTUAL_CLAIM_PATTERNS):
        failed.append("factual_claims")
    if not (HASHTAG_MIN <= len(hashtags or []) <= HASHTAG_MAX):
        failed.append("hashtags")
    return not failed, failed


def _feedback(failed, hook, script_md, cta, hashtags):
    """실패 코드 → 실측 피드백 문장 (맹재시도 방지)."""
    parts = []
    if "length" in failed:
        parts.append(
            "- 대본이 {0}자로 허용 범위({1}~{2}자)를 벗어남 — 정확히 범위 안으로 "
            "줄이거나 늘릴 것.".format(len(script_md or ""),
                                    SCRIPT_MIN_CHARS, SCRIPT_MAX_CHARS))
    if "hook" in failed:
        parts.append(
            "- 후킹 문장이 비었거나 {0}자 초과 — 첫 3초를 사로잡는 질문·충격 사실 "
            "형태로 다시 쓸 것.".format(HOOK_MAX_CHARS))
    if "cta" in failed:
        parts.append(
            "- CTA에 행동 유도가 없음 — '{0}' 중 하나를 포함해 마무리할 것.".format(
                "/".join(CTA_MARKERS)))
    if "banned_words" in failed:
        parts.append("- 과장·보장 표현 금지어 포함 — 사실 기반 온화한 표현으로 교체.")
    if "factual_claims" in failed:
        parts.append("- 검증되지 않은 출처·통계 표현 포함 — 제거하거나 '통상' 수준으로 완화.")
    if "hashtags" in failed:
        parts.append("- 해시태그 {0}~{1}개 필요 (현재 {2}개).".format(
            HASHTAG_MIN, HASHTAG_MAX, len(hashtags or [])))
    return "\n".join(parts)


def build_prompt(topic, ref_titles, qc_feedback=""):
    ref_block = ""
    if ref_titles:
        refs = "\n".join("- " + t for t in ref_titles[:5])
        ref_block = ("\n## 참고 인기 영상 제목 (트렌드 파악용 — 문구를 그대로 "
                     "옮기지 말 것)\n" + refs + "\n")
    feedback_block = ""
    if qc_feedback:
        feedback_block = ("\n## 이전 초안 검수 피드백 (반드시 반영)\n"
                          + qc_feedback + "\n")
    return (
        "유튜브 쇼츠 스크립트를 한국어로 작성하라.\n\n"
        "## 주제\n" + topic + "\n\n"
        + ref_block + feedback_block +
        "## 규칙 (모두 충족해야 함)\n"
        "1. 대본(hook+script+cta 합산) {0}~{1}자 — 30~45초 분량\n"
        "2. hook: 첫 3초 후킹 — 질문이나 충격적 사실, {2}자 이내\n"
        "3. script: 본론 — 구체적이고 실용적인 정보만 (일반 상식 나열 금지)\n"
        "4. cta: 마무리 행동 유도 — '{3}' 중 하나 포함\n"
        "5. 과장·보장 표현(보장/확실히/100%/최고의 등)과 검증되지 않은 통계·"
        "출처 창작 금지\n"
        "6. 해시태그 {4}~{5}개\n\n"
        'JSON만 반환: {{"hook": "...", "script": "...", "cta": "...", '
        '"hashtags": ["...", "..."]}}'.format(
            SCRIPT_MIN_CHARS, SCRIPT_MAX_CHARS, HOOK_MAX_CHARS,
            "/".join(CTA_MARKERS[:2]), HASHTAG_MIN, HASHTAG_MAX)
    )


def _compose(hook, script, cta):
    return "{0}\n\n{1}\n\n{2}".format((hook or "").strip(),
                                      (script or "").strip(),
                                      (cta or "").strip())


def generate_script(d, topic, runner=None, topic_row=None):
    """S-3 진입점 — shorts_topics 후보 1건에서 스크립트 생성·검수·저장.
    반환: {script_id, topic, status, failed} — 검수 최종 미달은 qc_failed로
    저장되고 예외가 아니다 (대시보드에서 원인 확인 후 재생성).
    topic_row 미지정 시 DB에서 label 조회 — 없으면 404 상당의 None 반환."""
    from draft_generator import _run_llm
    run = runner or _run_llm

    row = topic_row
    if row is None:
        rows = d.list_shorts_topics()
        row = next((r for r in rows if r.get("label") == topic), None)
    if row is None:
        return None

    import json as json_mod
    evidence = {}
    try:
        evidence = json_mod.loads(row.get("evidence") or "{}")
    except (TypeError, json_mod.JSONDecodeError):
        evidence = {}
    ref_ids = [v for v in (evidence.get("sample_video_ids") or [])
               if isinstance(v, str)]
    ref_titles = d.youtube_video_titles(ref_ids)

    qc_feedback = ""
    best = None  # 마지막 유효 파싱 결과 — qc_failed 저장용
    failed = ["generation"]
    for attempt in range(MAX_ATTEMPTS):
        try:
            raw = run(build_prompt(topic, ref_titles, qc_feedback), timeout=60)
        except Exception as e:  # noqa: BLE001 — 러너 장애(키 미설정·네트워크) 정규화
            raise ScriptGenerationError(
                "LLM 호출 실패: {0}".format(e)) from e
        try:
            data = _parse_script(raw)
        except ScriptGenerationError as e:
            logger.warning("script parse fail topic=%s attempt=%d: %s",
                           topic, attempt + 1, e)
            if best is not None:
                break  # v31 패턴 — 2회차 실패 시 1회차 유효 파싱분 회수
            if attempt + 1 >= MAX_ATTEMPTS:
                raise
            qc_feedback = "- 이전 응답이 JSON 형식이 아님 — 지정된 JSON 키만 반환할 것."
            continue
        hook = str(data.get("hook") or "").strip()
        script = str(data.get("script") or "").strip()
        cta = str(data.get("cta") or "").strip()
        hashtags = _normalize_hashtags(data.get("hashtags"))
        script_md = _compose(hook, script, cta)
        best = (hook, script_md, cta, hashtags)
        ok, failed = validate_script(hook, script_md, cta, hashtags)
        if ok:
            break
        if attempt + 1 >= MAX_ATTEMPTS:
            break
        qc_feedback = _feedback(failed, hook, script_md, cta, hashtags)

    now = config_mod.now_kst_iso()
    ok, failed = validate_script(*best) if best else (False, ["generation"])
    if best is None:
        # 파싱 자체가 2회 모두 실패한 경우 — 생성 실패로 정규화 (503 유도)
        raise ScriptGenerationError("스크립트 생성 실패 — 잠시 후 재시도")
    status = STATUS_READY if ok else STATUS_QC_FAILED
    script_id = d.insert_shorts_script(
        topic=topic, hook=best[0], script_md=best[1],
        hashtags_json=json.dumps(best[3], ensure_ascii=False),
        ref_video_ids_json=json.dumps(ref_ids, ensure_ascii=False),
        status=status,
        qc_detail_json=json.dumps(failed, ensure_ascii=False),
        created_at=now, updated_at=now)
    return {"script_id": script_id, "topic": topic, "status": status,
            "failed": failed}


if __name__ == "__main__":
    import db
    import sys
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    cfg = config_mod.load_config()
    conn = db.Database(cfg["db_url"])
    conn.init()
    label = sys.argv[1] if len(sys.argv) > 1 else ""
    topic_row = next((r for r in conn.list_shorts_topics()
                      if not label or r["label"] == label), None)
    if topic_row is None:
        logger.error("후보 주제가 없습니다 — 먼저 S-1/S-2 수집을 실행하세요")
        sys.exit(1)
    res = generate_script(conn, topic_row["label"])
    logger.info("S-3 결과: %s", res)
    conn.close()
