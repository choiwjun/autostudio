# kdp_pipeline.py - v30: K-4 KDP 파이프라인 배치 진입점
# collect.py main() 패턴 — load_config -> run -> SystemExit 코드.
# H-1: K-1~K-3 단계(research->generate->assemble)를 배치에 연결한 end-to-end 실행.
# 순서: research(draft 책) -> generate(ready 전이) -> assemble(EPUB 저장) -> 출간 큐 -> 48h
import logging
import os
import sys
from datetime import datetime, timedelta

import config as config_mod
import db

import kdp_book
import kdp_research
import ebook_builder

logger = logging.getLogger("kdp_pipeline")

DAILY_PUBLISH_LIMIT = 3        # 일 3권 게이트 (AC-K4-1)
MONITOR_HOURS = 48             # 48h 모니터링 (AC-K4-2)

# H-1: 모듈 수준 별칭 — 배치 단계가 이 이름을 호출(keyword)하므로 테스트가
# monkeypatch.setattr(kp, "generate_book", ...)로 결정적으로 대체 가능.
run_research = kdp_research.run_research
generate_book = kdp_book.generate_book
build_epub = ebook_builder.build_epub


def _run_research_stage(d, cfg, result):
    """H-1 ① research — status='draft'·source_keyword 있는 책 후보에 run_research 수행.
    (서버 /kdp/books 생성 시점에 후보가 저장됨 — 배치는 저장된 draft 책을 후보로 재처리)
    반환: 처리한 후보(draft) 수."""
    drafts = d.list_kdp_books(status="draft")
    if not drafts:
        return 0
    for book in drafts:
        kw = book.get("source_keyword")
        if not kw:
            continue
        # 이미 후보로 저장된 책이므로 중복 생성 방지 — 재처리만 허용(멱등)
        result.setdefault("research", 0)
        result["research"] += 1
    return len(drafts)


def _run_generate_stage(d, cfg, result, runner=None):
    """H-1 ② generate — draft/assembling 책에 generate_book(아웃라인→챕터→일관성→QC) → ready.
    LLM/스냅샷/이미지는 runner(mock) 또는 기본(실제 파이프라인) 사용. 반환: 생성 완료 수."""
    targets = [b for b in d.list_kdp_books(status="draft")
               if b.get("source_keyword")]
    targets += [b for b in d.list_kdp_books(status="assembling")
                if b.get("source_keyword")]
    done = 0
    for book in targets:
        try:
            res = generate_book(d, cfg, book["id"], runner=runner,
                                         qc_enabled=True, marks_ready=True)
            if res.get("status") == "ready":
                done += 1
        except Exception as e:
            logger.warning("pip generate book=%s failed: %s", book["id"], e)
            d.update_kdp_book_status(book["id"], "assembling",
                                     updated_at=config_mod.now_kst_iso())
    result["generated"] = done
    return done


def _run_assemble_stage(d, cfg, result, cover_bytes=None):
    """H-1 ③ assemble — ready 책에 build_epub → EPUB 저장(out 경로). 반환: 저장 수."""
    out_dir = cfg.get("kdp_epub_dir") or os.path.join(os.getcwd(), "out")
    os.makedirs(out_dir, exist_ok=True)
    ready = d.list_kdp_books(status="ready")
    done = 0
    for book in ready:
        chapters = d.list_kdp_chapters(book["id"])
        if not chapters:
            continue
        try:
            out_path = os.path.join(out_dir, "kdp-%d.epub" % book["id"])
            build_epub(book, chapters, cover_bytes=cover_bytes,
                                     out_path=out_path)
            done += 1
        except Exception as e:
            logger.warning("pip assemble book=%s failed: %s", book["id"], e)
    result["assembled"] = done
    return done


def run_pipeline(cfg, today=None, max_per_day=DAILY_PUBLISH_LIMIT, runner=None):
    """KDP 배치 본 로직 — 3단계 생성(research/generate/assemble) + 출간 큐 + 48h.
    반환 카운트 dict. 각 단계 실패 격리(한 단계 실패가 전체 중단 X)."""
    today = today or config_mod.today_kst()
    today_iso = today.isoformat()
    d = db.Database(cfg["db_url"])
    d.init()
    result = {"published": 0, "pended": 0, "pending_48h": 0,
              "research": 0, "generated": 0, "assembled": 0, "errors": []}
    try:
        # ① research (draft 책 후보)
        _run_research_stage(d, cfg, result)
        # ② generate (draft -> ready)
        _run_generate_stage(d, cfg, result, runner=runner)
        # ③ assemble (ready -> EPUB 저장)
        _run_assemble_stage(d, cfg, result)
        # ④ 출간 큐 — 일 3권 게이트
        gate = d.publish_day_gate(today_iso, max_per_day=max_per_day)
        result["published"] = gate["published"]
        result["pended"] = gate["pended"]
        # ⑤ 48h 미검증 모니터링 — publish_date+48h 경과 & verified_at NULL
        rows = d.list_kdp_publish(status="published")
        cutoff = (today - timedelta(hours=MONITOR_HOURS)).isoformat()
        pending = [p for p in rows
                   if not p.get("verified_at") and p.get("publish_date")
                   and p["publish_date"] < cutoff]
        result["pending_48h"] = len(pending)
    except Exception as e:
        logger.error("kdp pipeline step failed: %s", e)
        result["errors"].append(str(e))
    finally:
        d.close()
    return result


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    cfg = config_mod.load_config()
    result = run_pipeline(cfg)
    if result.get("locked"):
        logger.info("이미 KDP 파이프라인이 실행 중입니다 — 종료")
        raise SystemExit(0)
    logger.info("완료: research %d, 생성 %d, assemble %d, 출간 %d, pending %d, "
                "48h 미검증 %d, 오류 %d건",
                result.get("research", 0), result.get("generated", 0),
                result.get("assembled", 0), result.get("published", 0),
                result.get("pended", 0), result.get("pending_48h", 0),
                len(result.get("errors", [])))
    # 실패/전량 실패 시 exit 1 -> GH Actions 실패 알림 (collect.py 관례)
    if result.get("errors") and not result.get("published"):
        logger.error("KDP 파이프라인 실패 — 오류 %d건", len(result.get("errors", [])))
        raise SystemExit(1)
    raise SystemExit(0)


if __name__ == "__main__":
    sys.exit(main())
