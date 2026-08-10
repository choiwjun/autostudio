# scripts/fortune_generate.py — v22.2(3.3): 오늘의 운세 콘텐츠 생성 CLI
# 일일 배치(daily-collect)에서 호출 — SNS 요약본 + 블로그 상세본 생성.
# 생성 멱등: 같은 (기준일, 타입)이 이미 있으면 스킵.
# 발행은 Phase 2(별도 블로그 발행 API) 후 연결 — 지금은 큐 저장 + 파일 출력.
import json
import os
import sys

import config as config_mod
import db
from engine.fortune_content import (
    build_daily_grounding, generate_blog_detail, generate_sns_summary,
    validate_content,
)

OUT_DIR = "data/fortune"


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    db_url = argv[0] if argv and not argv[0].startswith("--") else ""
    cfg = config_mod.load_config()
    d = db.Database(db_url or cfg["db_url"])
    d.init()
    today = config_mod.today_kst()
    ref = today.isoformat()

    grounding = build_daily_grounding(today)
    grounding_json = json.dumps(grounding, ensure_ascii=False)

    created = []
    try:
        # SNS 요약본 (프롬프트 A)
        if d.upsert_fortune_generation(ref, "daily_sns", "",
                                       grounding=grounding_json):
            sns = generate_sns_summary(grounding)
            ok, fails = validate_content(sns, ref, "sns")
            if not ok:
                print(f"SNS 검수 실패: {fails}", file=sys.stderr)
            content = json.dumps({"text": sns["text"],
                                  "hashtags": sns.get("hashtags", [])},
                                 ensure_ascii=False)
            d.upsert_fortune_generation(ref, "daily_sns", content,
                                        grounding=grounding_json)
            created.append("daily_sns")
        # 블로그 상세본 (프롬프트 B)
        if d.upsert_fortune_generation(ref, "daily_blog", "",
                                       grounding=grounding_json):
            blog = generate_blog_detail(grounding)
            ok, fails = validate_content(blog, ref, "blog")
            if not ok:
                print(f"블로그 검수 실패: {fails}", file=sys.stderr)
            content = json.dumps(blog, ensure_ascii=False)
            d.upsert_fortune_generation(ref, "daily_blog", content,
                                        grounding=grounding_json)
            created.append("daily_blog")
    finally:
        d.close()

    # 파일 출력 (큐 확인용)
    if created:
        os.makedirs(OUT_DIR, exist_ok=True)
        path = os.path.join(OUT_DIR, f"{ref}.json")
        d2 = db.Database(db_url or cfg["db_url"])
        d2.init()
        rows = d2.list_fortune_generations(ref)
        with open(path, "w", encoding="utf-8") as f:
            json.dump([dict(r) for r in rows], f, ensure_ascii=False, indent=1)
        d2.close()
        print(f"생성 완료 ({', '.join(created)}) → {path}")
    else:
        print(f"스킵 — {ref} 이미 생성됨 (멱등)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
