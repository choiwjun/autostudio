# content_batch.py — v17: 초안·이미지 배치 생성 (스케줄 수집 잡 전용)
# 섹션 이미지 최대 8장 × 55초 순차 호출은 Vercel maxDuration 60초 안에서 끝날 수
# 없어 도중에 죽으면 API 비용만 쓰고 저장은 안 됐다 (버그 3). 시간 제약 없는
# GH Actions 컬렉트 잡에서 초안 생성과 대표·섹션 이미지 생성을 함께 끝낸다
# (고도화 4). 대상:
#   1) 기존 초안 이미지 백필 — 대시보드에서 만든 초안의 빈 대표/섹션 이미지
#   2) 신규 초안 — 초안 없는 활성 키워드를 우선순위 순으로 골격 분석 → 2패스
#      생성 → 이미지까지 일괄 처리 (상한: CONTENT_BATCH_MAX_NEW)
# 실패는 키워드 단위로 격리 — 한 건 실패가 배치 전체를 멈추지 않는다.
import json
import logging
import re
import time
from datetime import date

import config as config_mod
import llm_client
from analyzer import analyze_keyword
from draft_pipeline import generate_two_pass
from image_gen import (
    ImageGenerationError, generate_image, generate_section_images,
)
from naver_client import NaverAPIError, NaverClient
from outline import build_outline_structure

logger = logging.getLogger("content_batch")

IMAGE_BACKFILL_LIMIT = 5          # 1회 실행 백필 대상 초안 수 상한
HARD_DRAFT_BUDGET_SECONDS = 300   # 배치 초안 1건 생성 상한 (서버리스 아님)
SECTION_IMAGE_BATCH_BUDGET = 400  # 배치 초안 1건의 섹션 이미지 예산


def _section_titles(body):
    h2s = re.findall(r"^##\s+(.+)$", body or "", flags=re.M)
    return [h for h in h2s if "자주 묻는 질문" not in h][:8]


def _backfill_images(d, cfg, now, result, deadline):
    for draft in d.list_drafts_missing_images(IMAGE_BACKFILL_LIMIT):
        if time.monotonic() >= deadline:
            break
        keyword_row = d.get_keyword(draft["keyword_id"])
        keyword = keyword_row["keyword"] if keyword_row else ""
        created = 0
        if not draft["image_url"]:
            try:
                url = generate_image(keyword, draft["title"])
                d.update_draft_image(draft["id"], url, now)
                created += 1
            except ImageGenerationError as e:
                logger.warning("backfill main image draft=%s: %s", draft["id"], e)
        sections = _section_titles(draft["body"])
        existing = []
        if draft.get("section_images"):
            try:
                parsed = json.loads(draft["section_images"])
                if isinstance(parsed, list):
                    existing = parsed
            except json.JSONDecodeError:
                existing = []
        if sections and len(existing) < len(sections):
            try:
                new_urls = generate_section_images(
                    keyword, draft["title"], sections,
                    start_index=len(existing),
                    budget_seconds=min(
                        SECTION_IMAGE_BATCH_BUDGET,
                        max(0, deadline - time.monotonic())))
                if new_urls:
                    d.update_draft_section_images(
                        draft["id"],
                        json.dumps(existing + new_urls, ensure_ascii=False), now)
                    created += len(new_urls)
            except ImageGenerationError as e:
                logger.warning("backfill section images draft=%s: %s",
                               draft["id"], e)
        if created:
            result["draft_images_created"] += created
            d.log_collection(keyword, "image", f"배치 백필 {created}장", now)


def _create_draft(d, cfg, client, keyword_row, today, now, deadline):
    keyword = keyword_row["keyword"]
    reference_date = date.fromisoformat(today)
    snap = analyze_keyword(client, keyword, reference_date,
                           searched_at_kst=config_mod.now_kst_iso())
    evidence = snap.get("search_evidence") or {
        "status": "unavailable", "searched_at_kst": "", "reference_date": "",
        "items": []}
    structure = build_outline_structure(snap["top_descriptions"], evidence)
    d.upsert_outline(keyword_row["id"], today, structure)
    draft, failed = generate_two_pass(
        keyword, structure, current_date=reference_date,
        search_evidence=evidence, hard_budget_seconds=HARD_DRAFT_BUDGET_SECONDS)
    if failed:
        logger.warning("batch draft qc warnings kw=%s: %s", keyword, failed)
    draft_id = d.insert_draft(
        keyword_row["id"], draft["title"], draft["first_paragraph"],
        draft["body"], created_at=now)
    d.log_collection(keyword, "draft", "배치 초안 생성", now)
    created_images = 0
    try:
        url = generate_image(keyword, draft["title"])
        d.update_draft_image(draft_id, url, now)
        created_images += 1
    except ImageGenerationError as e:
        logger.warning("batch main image kw=%s: %s", keyword, e)
    sections = _section_titles(draft["body"])
    if sections:
        try:
            urls = []
            remaining_budget = min(
                SECTION_IMAGE_BATCH_BUDGET, max(0, deadline - time.monotonic()))
            new_urls = generate_section_images(
                keyword, draft["title"], sections,
                budget_seconds=remaining_budget)
            urls.extend(new_urls)
            # 예산 내 미완성분은 다음 실행 백필이 이어서 생성
            if urls:
                d.update_draft_section_images(
                    draft_id, json.dumps(urls, ensure_ascii=False), now)
                created_images += len(urls)
        except ImageGenerationError as e:
            logger.warning("batch section images kw=%s: %s", keyword, e)
    return created_images


def run_content_batch(d, cfg, today, now, client=None):
    """스케줄 수집 후반부에 실행되는 콘텐츠 배치. 반환: 카운트 dict.
    LLM 키 없으면 조용히 생략 (수집 전용 환경 호환)."""
    result = {"drafts_created": 0, "draft_images_created": 0}
    if not llm_client.has_api_key():
        d.log_collection("(content)", "skip", "LLM 키 없음 — 콘텐츠 배치 생략", now)
        return result
    started = time.monotonic()
    budget = cfg.get("content_batch_budget_seconds", 2400)
    deadline = started + budget
    client = client or NaverClient(cfg["client_id"], cfg["client_secret"])

    _backfill_images(d, cfg, now, result, deadline)

    max_new = cfg.get("content_batch_max_new", 2)
    for keyword_row in d.keywords_without_drafts(max_new):
        if time.monotonic() >= deadline:
            d.log_collection("(content)", "partial",
                             "시간 예산 초과로 콘텐츠 배치 중단", now)
            break
        try:
            created_images = _create_draft(
                d, cfg, client, keyword_row, today, now, deadline)
            result["drafts_created"] += 1
            result["draft_images_created"] += created_images
        except (NaverAPIError, ImageGenerationError) as e:
            logger.warning("batch draft failed kw=%s: %s",
                           keyword_row["keyword"], e)
            d.log_collection(keyword_row["keyword"], "error",
                             f"배치 초안 실패: {e}", now)
        except Exception as e:
            # 생성부 예외(DraftGenerationError 포함)는 키워드 단위 격리
            logger.warning("batch draft failed kw=%s: %s",
                           keyword_row["keyword"], e)
            d.log_collection(keyword_row["keyword"], "error",
                             f"배치 초안 실패: {e}", now)
    return result
