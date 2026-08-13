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
import publish_client
from analyzer import analyze_keyword
from draft_pipeline import generate_two_pass
from image_gen import (
    ImageGenerationError, generate_image, generate_section_images,
    get_image_stats, reset_image_stats,
)
from naver_client import NaverAPIError, NaverClient
from outline import build_outline_structure
from product_recommend import PRODUCT_BLOCK_CATEGORIES, search_products

logger = logging.getLogger("content_batch")

IMAGE_BACKFILL_LIMIT = 5          # 1회 실행 백필 대상 초안 수 상한
HARD_DRAFT_BUDGET_SECONDS = 300   # 배치 초안 1건 생성 상한 (서버리스 아님)
SECTION_IMAGE_BATCH_BUDGET = 400  # 배치 초안 1건의 섹션 이미지 예산
# v26 (FR-5): 이미지 실패 임계 — 연속 5건 또는 시도 5건+ 실패율 50% 초과
IMAGE_ALERT_CONSECUTIVE = 5
IMAGE_ALERT_MIN_ATTEMPTS = 5      # 실패율 판정 최소 시도 (소표본 노이즈 방지 — 가정 5)
IMAGE_ALERT_FAILURE_RATE = 0.5    # 실패율 임계 (50% 초과 시 알림)


def image_alert_triggered(attempts, failures, consecutive):
    """이미지 실패 임계 판정 (v26, AC5-1~AC5-3).
    - 연속 5건: 시도 수 무관
    - 실패율 50% 초과: 시도 5건 이상일 때만 적용 (소표본 노이즈 방지)"""
    if consecutive >= IMAGE_ALERT_CONSECUTIVE:
        return True
    if attempts >= IMAGE_ALERT_MIN_ATTEMPTS and \
            failures / attempts > IMAGE_ALERT_FAILURE_RATE:
        return True
    return False


def _section_titles(body):
    h2s = re.findall(r"^##\s+(.+)$", body or "", flags=re.M)
    return [h for h in h2s if "자주 묻는 질문" not in h][:8]


def _backfill_images(d, cfg, now, result, deadline):
    for draft in d.list_drafts_missing_images(IMAGE_BACKFILL_LIMIT):
        if time.monotonic() >= deadline:
            break
        keyword_row = d.get_keyword(draft["keyword_id"])
        keyword = keyword_row["keyword"] if keyword_row else ""
        platform = draft.get("platform") or "naver"
        ideas = _thumbnail_ideas(draft)
        created = 0
        if not draft["image_url"]:
            try:
                url = generate_image(keyword, draft["title"],
                                     thumbnail_ideas=ideas)
                d.update_draft_image(draft["id"], url, now)
                created += 1
            except ImageGenerationError as e:
                logger.warning("backfill main image draft=%s: %s", draft["id"], e)
        # v19: 네이버 플레인 텍스트는 H2가 없어 섹션 이미지 대상이 아님
        if platform == "naver":
            if created:
                result["draft_images_created"] += created
                d.log_collection(keyword, "image", f"배치 백필 {created}장", now)
            continue
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


def _thumbnail_ideas(draft):
    """초안 thumbnail_ideas JSON → 리스트 (이미지 프롬프트 재료)."""
    if not draft.get("thumbnail_ideas"):
        return []
    try:
        parsed = json.loads(draft["thumbnail_ideas"])
        return parsed if isinstance(parsed, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


def _product_block_for(client, keyword_row):
    """v21(B.3): 쇼핑 전환 적합 카테고리(요리/패션/IT 등) 초안에만 상품 블록.
    검색 실패·카테고리 미해당 시 '' (선택 사양 — 파이프라인 무해)."""
    if keyword_row.get("category") not in PRODUCT_BLOCK_CATEGORIES:
        return ""
    products = search_products(client, keyword_row["keyword"])
    if not products:
        return ""
    return json.dumps(products, ensure_ascii=False)


def _create_draft(d, cfg, client, keyword_row, today, now, deadline,
                  platform="naver"):
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
        search_evidence=evidence, hard_budget_seconds=HARD_DRAFT_BUDGET_SECONDS,
        pattern_guidance=d.top_performer_pattern(), platform=platform)
    if failed:
        logger.warning("batch draft qc warnings kw=%s: %s", keyword, failed)
    draft_id = d.insert_draft(
        keyword_row["id"], draft["title"], draft["first_paragraph"],
        draft["body"], created_at=now,
        tags=json.dumps(draft.get("tags") or [], ensure_ascii=False),
        platform=platform,
        thumbnail_ideas=json.dumps(
            draft.get("thumbnail_ideas") or [], ensure_ascii=False),
        product_block=_product_block_for(client, keyword_row))
    d.log_collection(keyword, "draft", "배치 초안 생성", now)
    created_images = 0
    try:
        url = generate_image(keyword, draft["title"],
                             thumbnail_ideas=draft.get("thumbnail_ideas"))
        d.update_draft_image(draft_id, url, now)
        created_images += 1
    except ImageGenerationError as e:
        logger.warning("batch main image kw=%s: %s", keyword, e)
    if platform == "naver":
        return draft_id, created_images  # v19: 네이버 플레인 텍스트는 섹션 이미지 없음
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
    return draft_id, created_images


def run_content_batch(d, cfg, today, now, client=None):
    """스케줄 수집 후반부에 실행되는 콘텐츠 배치. 반환: 카운트 dict.
    LLM 키 없으면 조용히 생략 (수집 전용 환경 호환).
    v26 (FR-4/FR-5): 이미지 생성 시도·최종 실패 집계 + 임계 초과 시
    ERROR 로그·image_alert=True (collect.py가 exit 1로 전파)."""
    result = {"drafts_created": 0, "draft_images_created": 0,
              "image_attempts": 0, "image_failures": 0, "image_alert": False}
    if not llm_client.has_api_key():
        d.log_collection("(content)", "skip", "LLM 키 없음 — 콘텐츠 배치 생략", now)
        return result
    reset_image_stats()  # v26: 배치 단위 집계 시작
    started = time.monotonic()
    # v17.3: 기본 예산 2400→1200 — 발굴·스냅샷(500키워드)·수요·쇼핑 합계가
    # GH Actions 잡 timeout(60분)을 넘기면 도중 kill로 당일 수집이 유실됨.
    # 미완성분은 증분 설계라 다음 실행이 이어서 생성한다.
    budget = cfg.get("content_batch_budget_seconds", 1200)
    deadline = started + budget
    client = client or NaverClient(cfg["client_id"], cfg["client_secret"])

    _backfill_images(d, cfg, now, result, deadline)

    max_new = cfg.get("content_batch_max_new", 2)
    # v19: 배치 신규 초안 플랫폼 — 기본 네이버 (CONTENT_BATCH_PLATFORM으로 변경 가능)
    batch_platform = cfg.get("content_batch_platform") or "naver"
    for keyword_row in d.keywords_without_drafts(max_new):
        if time.monotonic() >= deadline:
            d.log_collection("(content)", "partial",
                             "시간 예산 초과로 콘텐츠 배치 중단", now)
            break
        try:
            draft_id, created_images = _create_draft(
                d, cfg, client, keyword_row, today, now, deadline,
                platform=batch_platform)
            result["drafts_created"] += 1
            result["draft_images_created"] += created_images
            # v22.3(2.x): 발행 활성 시 생성 초안을 별도 블로그에 자동 발행
            if cfg.get("blog_publish_enabled"):
                draft = d.get_draft(draft_id)
                try:
                    url = publish_client.publish_draft(
                        cfg, d, draft, keyword_row)
                    result.setdefault("blog_published", []).append(url)
                    d.log_collection(keyword_row["keyword"], "publish",
                                     f"별도 블로그 발행: {url}", now)
                except publish_client.BlogPublishError as e:
                    logger.warning("batch publish failed kw=%s: %s",
                                   keyword_row["keyword"], e)
                    d.log_collection(keyword_row["keyword"], "error",
                                     f"블로그 발행 실패: {e}", now)
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
    # v26 (FR-4/FR-5): 이미지 실패 집계 — 백필+신규(대표+섹션) 전부 image_gen stats에
    # 누적됨 (AC4-2). 임계 초과 시 ERROR 로그 + image_alert (AC5-1~AC5-5).
    stats = get_image_stats()
    result["image_attempts"] = stats["attempts"]
    result["image_failures"] = stats["failures"]
    if image_alert_triggered(
            stats["attempts"], stats["failures"],
            stats["consecutive_failures"]):
        result["image_alert"] = True
        logger.error(
            "이미지 생성 실패 임계 초과: 시도 %d건, 최종 실패 %d건, 연속 실패 %d건 — "
            "Bailian/DashScope 키·쿼터 점검 필요 (임계: 연속 %d건 또는 시도 %d건 이상 "
            "실패율 %.0f%% 초과)",
            stats["attempts"], stats["failures"],
            stats["consecutive_failures"], IMAGE_ALERT_CONSECUTIVE,
            IMAGE_ALERT_MIN_ATTEMPTS, IMAGE_ALERT_FAILURE_RATE * 100)
    return result
