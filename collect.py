# collect.py
import sys
import time
from datetime import date, datetime, timedelta

import config as config_mod
import db
from analyzer import analyze_keyword
from autocomplete import expand_keywords
from datalab import DatalabError, fetch_demand_ratios
from naver_client import NaverAPIError, NaverClient
from refine import refine_keywords
from scoring import commercial_score, growth_rate, opportunity_score

RUN_LOCK_STALE_MINUTES = 60  # v3: GH Actions timeout-minutes(60)와 정합 (기본값, cfg로 조정)
MANUAL_DISCOVERY_MAX_NEW = 30       # 첫 실행(활성 0개)의 수동 발굴 축소 상한
MANUAL_DISCOVERY_MAX_REQUESTS = 40
RETIRE_MIN_AGE_DAYS = 14
RETIRE_WINDOW_DAYS = 7
RETIRE_OPPORTUNITY_LT = 35.0
RETIRE_COMMERCIAL_LT = 30.0
STATS_RETENTION_DAYS = 90
TOP_RESULTS_RETENTION_DAYS = 30
LOG_RETENTION_DAYS = 180
DATALAB_TOP_N = 200
DATALAB_WINDOW_DAYS = 30


def compute_scores(d, keyword_id, day, stats):
    """점수 사전계산 (조회 시 재계산 금지 — 스펙 §4.5).
    v3: 증감률·기회점수는 전일(day-1) 스냅샷 대비만 산출 — 공백(2일 이상)이면
    NULL ("데이터 쌓는 중"). 최근 과거 스냅샷으로 며칠치 증가율을 하루치로 계산하지 않음."""
    prev = d.get_prev_stats(keyword_id, day)
    growth = opportunity = None
    prev_day = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
    if prev and prev["day"] == prev_day:
        growth = growth_rate(prev["total_date"], stats["total_date"])
        opportunity = opportunity_score(
            stats["fresh_ratio"], growth, stats["total_sim"])
    commercial = None if stats.get("shop_error") else commercial_score(
        stats["shop_total"], stats["shop_avg_price"])
    return growth, opportunity, commercial


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def discover(d, cfg, today, now, trigger, result, budget_seconds=None):
    seeds = d.list_seeds()
    if not seeds:
        return
    if trigger == "manual" and d.count_active() > 0:
        return  # 수동 수집은 스냅샷 갱신 전용 — 발굴은 스케줄러 몫 (첫 실행만 예외)
    max_new = cfg["daily_new_keyword_cap"]
    max_requests = cfg["autocomplete_max_requests"]
    if trigger == "manual":
        max_new = min(max_new, MANUAL_DISCOVERY_MAX_NEW)
        max_requests = min(max_requests, MANUAL_DISCOVERY_MAX_REQUESTS)
    cap_room = cfg["active_keyword_cap"] - d.count_active()
    remaining = min(max_new - d.count_new_keywords_today(today), cap_room)
    if remaining <= 0:
        d.log_collection("(seed)", "skip", "일일/총량 상한 도달", now)
        return
    try:
        # v3: 예산을 발굴에도 적용(잔여 예산 기반 타임아웃·중단), 유래 키워드(origins) 추적
        found, origins, stopped = expand_keywords(
            [s["keyword"] for s in seeds], url=cfg["autocomplete_url"],
            known=d.all_keyword_names(), max_new=remaining,
            max_depth=cfg["autocomplete_max_depth"], max_requests=max_requests,
            budget_seconds=budget_seconds)
    except Exception as e:
        d.log_collection("(seed)", "error", f"autocomplete: {e}", now)
        result["crawl_stopped"] = "blocked"
        return
    result["crawl_stopped"] = stopped
    if stopped == "blocked":
        d.log_collection("(seed)", "blocked", "자동완성 연속 실패로 중단", now)
    elif stopped == "budget":
        d.log_collection("(seed)", "blocked", "시간 예산 초과로 발굴 중단", now)
    # v3: 시드에서 직접 파생된 1차 키워드는 시드 분야 상속 (2차 이상은 shop 데이터로 채움)
    seed_cat = {s["keyword"]: s["category"] for s in seeds}
    kept, rejected = refine_keywords(found)
    for kw, reason in rejected:
        d.log_collection(kw, "reject", reason, now)  # v3: 사유 기록 (substring/token/...)
    for kw in kept[:remaining]:
        cat = seed_cat.get(origins.get(kw, ""), "")
        d.upsert_keyword(kw, category=cat, day=today)
        d.log_collection(kw, "new", "발굴", now)
    result["new_keywords"] = len(kept[:remaining])


def snapshot(d, cfg, client, today, now, started, budget_seconds, result):
    base_date = date.fromisoformat(today)
    for kw in d.list_active_keywords_stale_first():
        if budget_seconds is not None and time.monotonic() - started >= budget_seconds:
            result["partial"] = True
            break
        if kw["last_day"] == today:
            continue  # 같은 날짜 재수집 스킵 (멱등)
        if budget_seconds is not None:
            # v3: 키워드당 최악 3회 호출(blog 2 + shop 1)이 잔여 예산을 넘지 않도록
            # 호출 타임아웃 축소 — 루프 사이 체크만으로는 30초 오버슛이 가능했음 (스펙 §4.9)
            remaining = budget_seconds - (time.monotonic() - started)
            client.timeout = max(
                1.0, min(getattr(client, "timeout", 10.0) or 10.0, remaining / 3))
        try:
            stats = analyze_keyword(client, kw["keyword"], base_date)
            growth, opportunity, commercial = compute_scores(
                d, kw["id"], today, stats)
            stats.update({"growth": growth, "opportunity": opportunity,
                          "commercial": commercial})
            if stats.get("shop_error"):
                d.log_collection(kw["keyword"], "partial",
                                 f"shop: {stats['shop_error']}", now)
            d.insert_daily_stats(kw["id"], today, stats)
            d.insert_top_results(kw["id"], today, stats["top_post_dates"])
            result["snapshotted"] += 1
        except NaverAPIError as e:
            d.log_collection(kw["keyword"], "error", str(e), now)
            result["errors"].append(str(e))
        except Exception as e:
            d.log_collection(kw["keyword"], "error", f"unknown: {e}", now)
            result["errors"].append(str(e))
        time.sleep(0.3)


def update_demand(d, cfg, today, now):
    if not cfg.get("datalab_enabled", True):
        return 0
    start = (date.fromisoformat(today)
             - timedelta(days=DATALAB_WINDOW_DAYS)).isoformat()
    updated = 0
    for batch in _chunks(d.top_by_opportunity(today, DATALAB_TOP_N), 4):
        try:
            ratios = fetch_demand_ratios(
                cfg["client_id"], cfg["client_secret"],
                [b["keyword"] for b in batch], cfg["datalab_anchor"], start, today)
        except DatalabError as e:
            d.log_collection("(datalab)", "error", str(e), now)
            break  # 수요 단계만 중단 — 나머지 파이프라인은 정상 (스펙 §4.4)
        for b in batch:
            if b["keyword"] in ratios:
                d.update_demand_idx(b["id"], today, ratios[b["keyword"]])
                updated += 1
        time.sleep(0.2)
    return updated


def retire(d, today, now):
    base = date.fromisoformat(today)
    victims = d.find_retire_candidates(
        (base - timedelta(days=RETIRE_MIN_AGE_DAYS)).isoformat(),
        (base - timedelta(days=RETIRE_WINDOW_DAYS)).isoformat(),
        RETIRE_OPPORTUNITY_LT, RETIRE_COMMERCIAL_LT)
    for v in victims:
        d.set_active(v["id"], 0)
        d.log_collection(v["keyword"], "retire", "저성과 자동 비활성", now)
    return len(victims)


def run_collection(cfg, client=None, today=None, trigger="schedule",
                   budget_seconds=None):
    started = time.monotonic()
    today = today or config_mod.today_kst().isoformat()  # 날짜 키는 KST 고정
    # v3: 잠금 타임스탬프는 마이크로초 — 초 단위 now_kst_iso()로는 동일 초에 시작된
    # 기존 running 행과 소유권 비교(시작 시각 일치)가 충돌해 잠금이 무시될 수 있음
    now = datetime.now(config_mod.KST).isoformat(timespec="microseconds")
    d = db.Database(cfg["db_url"])
    d.init()
    stale_minutes = cfg.get("run_lock_stale_minutes", RUN_LOCK_STALE_MINUTES)
    run_id = d.start_run(
        trigger, now, config_mod.minutes_ago_kst_iso(stale_minutes))
    if run_id is None:
        d.close()
        return {"locked": True, "new_keywords": 0, "snapshotted": 0,
                "errors": [], "partial": False, "crawl_stopped": None}
    result = {"locked": False, "new_keywords": 0, "snapshotted": 0, "errors": [],
              "partial": False, "crawl_stopped": None, "retired": 0,
              "demand_updated": 0}
    try:
        # v3: 예산은 발굴·스냅샷·개별 호출 타임아웃까지 전 구간 적용
        discover(d, cfg, today, now, trigger, result, budget_seconds)
        client = client or NaverClient(cfg["client_id"], cfg["client_secret"])
        snapshot(d, cfg, client, today, now, started, budget_seconds, result)
        if trigger == "schedule":
            base = date.fromisoformat(today)
            result["demand_updated"] = update_demand(d, cfg, today, now)
            result["retired"] = retire(d, today, now)
            d.cleanup(
                (base - timedelta(days=STATS_RETENTION_DAYS)).isoformat(),
                (base - timedelta(days=TOP_RESULTS_RETENTION_DAYS)).isoformat(),
                (base - timedelta(days=LOG_RETENTION_DAYS)).isoformat(),
            )
        # v3: 상태 구분 — done(전량 성공) / partial(예산 종료·일부 오류·발굴 중단) / failed(전량 실패)
        if result["errors"] and result["snapshotted"] == 0:
            status = "failed"
        elif result["partial"] or result["errors"] or result["crawl_stopped"]:
            status = "partial"
        else:
            status = "done"
        d.finish_run(run_id, status, config_mod.now_kst_iso(), result)
    except Exception:
        d.finish_run(run_id, "failed", config_mod.now_kst_iso(), result)
        raise
    finally:
        d.close()
    return result


def main():
    cfg = config_mod.load_config()
    result = run_collection(cfg, trigger="schedule")
    if result.get("locked"):
        print("이미 수집이 실행 중입니다 — 종료")
        raise SystemExit(0)
    print(f"완료: 신규 {result['new_keywords']}개, 스냅샷 {result['snapshotted']}개, "
          f"수요갱신 {result['demand_updated']}개, 은퇴 {result['retired']}개, "
          f"오류 {len(result['errors'])}개"
          + (f" — 발굴 중단({result.get('crawl_stopped')})"
             if result.get("crawl_stopped") else ""))
    # v3: 자동완성 차단은 스냅샷 성공 여부와 무관하게 exit 1 — 차단을 조기에 인지해야
    # 대체 스케줄러(cron-job.org)로 전환할 수 있음 (스펙 §5)
    if result.get("crawl_stopped") == "blocked":
        raise SystemExit(1)
    # 전량 실패 시 exit 1 → GitHub Actions 실패 메일로 조기 인지 (스펙 §5)
    if result["errors"] and result["snapshotted"] == 0:
        raise SystemExit(1)
    raise SystemExit(0)


if __name__ == "__main__":
    sys.exit(main())
