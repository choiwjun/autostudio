# scripts/publish_drafts.py — v22.3(2.x): 별도 블로그(autoblog) 수동 발행
# 미발행 초안을 발행 API로 전송 (품질 리뷰 후 수동 실행 — BLOG_PUBLISH_ENABLED와 무관).
# 사용법:
#   python scripts/publish_drafts.py --limit 5            # 최신 5건
#   python scripts/publish_drafts.py --draft-id 42        # 특정 초안
#   python scripts/publish_drafts.py --platform naver     # 플랫폼 필터
# 환경변수: BLOG_API_URL, BLOG_TOKEN (필수 — 미설정 시 중단)
import argparse
import logging
import sys

sys.path.insert(0, ".")

import config as config_mod
import publish_client
from db import Database

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("publish_drafts")


def main():
    parser = argparse.ArgumentParser(description="미발행 초안 → autoblog 발행")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--draft-id", type=int)
    parser.add_argument("--platform", default="")
    args = parser.parse_args()

    cfg = config_mod.load_config()
    if not cfg.get("blog_api_url") or not cfg.get("blog_token"):
        sys.exit("BLOG_API_URL/BLOG_TOKEN 미설정 — 발행 불가")
    d = Database(cfg["db_url"])

    if args.draft_id:
        draft = d.get_draft(args.draft_id)
        targets = [draft] if draft else []
    else:
        targets = d.list_drafts_unpublished(args.limit, platform=args.platform)
    if not targets:
        logger.info("발행 대상 초안 없음")
        return 0

    ok, failed = 0, 0
    for draft in targets:
        keyword_row = d.get_keyword(draft["keyword_id"])
        try:
            url = publish_client.publish_draft(cfg, d, draft, keyword_row)
            logger.info("발행 완료: draft=%s → %s", draft["id"], url)
            ok += 1
        except publish_client.BlogPublishError as e:
            logger.error("발행 실패: draft=%s — %s", draft["id"], e)
            failed += 1
    logger.info("완료: %d건 발행, %d건 실패", ok, failed)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
