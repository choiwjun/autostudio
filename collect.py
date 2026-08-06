# collect.py
import json
import logging
import sys
import time
from datetime import date, datetime, timedelta

import config as config_mod
import db
from analyzer import analyze_keyword
from autocomplete import expand_keywords
from datalab import DatalabError, fetch_demand_ratios
from naver_client import NaverAPIError, NaverClient
from refine import refine_keywords, reject_reason
from scoring import ai_citation_score, growth_rate, opportunity_score
from shopping_insight import fetch_click_ratios

RUN_LOCK_STALE_MINUTES = 60  # v3: GH Actions timeout-minutes(60)와 정합 (기본값, cfg로 조정)
MANUAL_DISCOVERY_MAX_NEW = 30       # 첫 실행(활성 0개)의 수동 발굴 축소 상한
MANUAL_DISCOVERY_MAX_REQUESTS = 40
RETIRE_MIN_AGE_DAYS = 14
RETIRE_WINDOW_DAYS = 7
# v14: 은퇴 기회점수 임계는 백분위(P25) 자가보정 — 고정 35.0는 실측 기회점수
# 최대(~24)보다 높아 "최근 기회 전부 < 35"가 항상 참이 되어 은퇴 판정이
# 쇼핑클릭 조건으로 퇴화하던 버그. 표본 부족 시 폴백 절대값.
RETIRE_OPPORTUNITY_LT_FALLBACK = 12.0
RETIRE_MIN_SAMPLES = 20        # 백분위 유효 최소 표본 (프리셋과 동일 원칙 — 스펙 §3.2)
RETIRE_CLICK_LT = 0.5          # v4: 쇼핑 클릭 지수(앵커 대비) 임계 — 상업성(NULL 상시) 대체
STATS_RETENTION_DAYS = 90
TOP_RESULTS_RETENTION_DAYS = 30
LOG_RETENTION_DAYS = 180
# v17: 데이터랩 갱신 슬롯 — 상위 고정 + 순환. 합계는 기존 200개/일과 동일하지만
# 순환 슬롯이 수요 갱신 오래된 키워드부터 채워 활성 전체(≤500)가 ~5일 주기로
# 골고루 갱신됨 (상위 200 밖 키워드의 영구 NULL 사각지대 해소 — 고도화 5).
DATALAB_PRIORITY_N = 100
DATALAB_ROTATE_N = 100
DATALAB_WINDOW_DAYS = 30
DATALAB_TIMEOUT = 10   # 수요·쇼핑 단계 기본 호출 타임아웃 (초)

logger = logging.getLogger("collect")


def compute_scores(d, keyword_id, day, stats):
    """점수 사전계산 (조회 시 재계산 금지 — 스펙 §4.5).
    v3: 증감률·기회점수는 전일(day-1) 스냅샷 대비만 산출 — 공백(2일 이상)이면
    NULL ("데이터 쌓는 중"). 최근 과거 스냅샷으로 며칠치 증가율을 하루치로 계산하지 않음.
    v4: 쇼핑 검색 API 종료로 상업성은 항상 NULL — 쇼핑 클릭 지수는 배치 단계에서 갱신.
    v6: ai_cite_idx는 키워드·카테고리·신선도 기반 프록시 — 스냅샷 시점에 사전계산 저장."""
    prev = d.get_prev_stats(keyword_id, day)
    growth = opportunity = None
    prev_day = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
    if prev and prev["day"] == prev_day:
        growth = growth_rate(prev["total_date"], stats["total_date"])
        opportunity = opportunity_score(
            stats["fresh_ratio"], growth, stats["total_sim"])
    ai_cite = ai_citation_score(stats["keyword"], stats["fresh_ratio"], stats.get("category", ""))
    return growth, opportunity, None, ai_cite


def _categorize_by_rules(keyword, rules):
    """키워드 패턴 규칙으로 카테고리 결정 (첫 매치 우선). 매치 없으면 빈 문자열.
    v17: 부분문자열·대소문자 오탐 수정 — 기존 'token in keyword'는 '암사동'이
    '암'(의료)에, '운동화'가 '운동'(건강)에 매치되고 'isa'는 'ISA'를 놓쳤다.
    오탐은 CPC 등급 왜곡(수익 직결)이라 정밀도를 재현율보다 우선:
    - 기본은 단어 단위 매치 (공백 분리 토큰 완전 일치, 대소문자 무시)
    - 복합어 부분 매치가 필요한 토큰만 규칙에서 (토큰, 카테고리, "contains")로 명시"""
    k = (keyword or "").lower()
    words = set(k.split())
    for rule in rules:
        token, category = rule[0], rule[1]
        mode = rule[2] if len(rule) > 2 else "word"
        t = token.lower()
        if mode == "contains":
            if t in k:
                return category
        elif t in words:
            return category
    return ""


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def discover(d, cfg, today, now, trigger, result, budget_seconds=None):
    seeds = d.list_seeds()
    if not seeds:
        # v6: 시드 없으면 집중 기본 시드로 자동 초기화 (애드포스트 1차 목표 기준)
        for kw, cat in cfg.get("default_focus_seeds", []):
            d.add_seed(kw, cat)
            d.log_collection(kw, "seed", "집중 시드 자동 초기화", now)
        seeds = d.list_seeds()
    if not seeds:
        return
    if trigger == "manual" and d.count_active() > 0:
        return  # 수동 수집은 스냅샷 갱신 전용 — 발굴은 스케줄러 몫 (첫 실행만 예외)
    max_requests = cfg["autocomplete_max_requests"]
    cap_room = cfg["active_keyword_cap"] - d.count_active()
    daily_cap = cfg["daily_new_keyword_cap"]
    if daily_cap > 0:
        remaining = min(daily_cap - d.count_new_keywords_today(today), cap_room)
    else:
        # 0 disables the daily cap; ACTIVE_KEYWORD_CAP remains the hard safety bound.
        remaining = cap_room
    if trigger == "manual":
        remaining = min(remaining, MANUAL_DISCOVERY_MAX_NEW)
        max_requests = min(max_requests, MANUAL_DISCOVERY_MAX_REQUESTS)
    if remaining <= 0:
        reason = "총량 상한 도달" if daily_cap <= 0 else "일일/총량 상한 도달"
        d.log_collection("(seed)", "skip", reason, now)
        return
    try:
        # v3: 예산을 발굴에도 적용(잔여 예산 기반 타임아웃·중단), 유래 키워드(origins) 추적
        # v14: exclude — 정제에서 버려질 노이즈는 BFS 경유지에서도 제외 (팬아웃 차단)
        found, origins, stopped = expand_keywords(
            [s["keyword"] for s in seeds], url=cfg["autocomplete_url"],
            known=d.all_keyword_names(), max_new=remaining,
            max_depth=cfg["autocomplete_max_depth"], max_requests=max_requests,
            budget_seconds=budget_seconds,
            exclude=lambda w: reject_reason(w) is not None)
    except Exception as e:
        d.log_collection("(seed)", "error", f"autocomplete: {e}", now)
        # v17: 예상치 못한 예외는 'blocked'(연속 실패 차단)과 구분 — 원인 혼동 방지
        result["crawl_stopped"] = "error"
        return
    result["crawl_stopped"] = stopped
    if stopped == "blocked":
        d.log_collection("(seed)", "blocked", "자동완성 연속 실패로 중단", now)
    elif stopped == "budget":
        d.log_collection("(seed)", "blocked", "시간 예산 초과로 발굴 중단", now)
    # v3: 시드에서 직접 파생된 1차 키워드는 시드 분야 상속 (v4: 쇼핑 카테고리 소실로 시드 분야가 유일 소스)
    # v8: 시드 상속 실패(무카테고리 시드 유래) 시 키워드 패턴 규칙으로 분류 — 에어프라이어류 다수 발굴 이슈
    seed_cat = {s["keyword"]: s["category"] for s in seeds}
    rules = cfg.get("keyword_category_rules", [])
    kept, rejected = refine_keywords(found)
    # v14 §1.2: 거부율 지표 원료 — 발굴 후보 수·거부 수를 result로 올려 note에 기록
    result["found_raw"] = len(found)
    result["rejected"] = len(rejected)
    for kw, reason in rejected:
        d.log_collection(kw, "reject", reason, now)  # v3: 사유 기록 (substring/token/...)
    for kw in kept[:remaining]:
        cat = seed_cat.get(origins.get(kw, ""), "")
        if not cat:
            cat = _categorize_by_rules(kw, rules)
        if not cat:
            cat = cfg.get("fallback_category", config_mod.FALLBACK_CATEGORY)  # v14 §2
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
            # v3: 키워드당 최악 호출(blog 2종, v4)이 잔여 예산을 넘지 않도록
            # 호출 타임아웃 축소 — 루프 사이 체크만으로는 오버슛이 가능했음 (스펙 §4.9)
            remaining = budget_seconds - (time.monotonic() - started)
            client.timeout = max(
                1.0, min(getattr(client, "timeout", 10.0) or 10.0, remaining / 2))
        try:
            stats = analyze_keyword(client, kw["keyword"], base_date)
            # v6: ai_citation_score가 키워드·카테고리를 참조하므로 stats에 주입
            stats["keyword"] = kw["keyword"]
            stats["category"] = kw.get("category", "")
            growth, opportunity, commercial, ai_cite = compute_scores(
                d, kw["id"], today, stats)
            stats.update({"growth": growth, "opportunity": opportunity,
                          "commercial": commercial, "ai_cite_idx": ai_cite})
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


def _budget_exhausted(budget_seconds, started):
    # v17: started=None 가드 — 미전달 시 TypeError 대신 예산 검사 생략
    return (budget_seconds is not None and started is not None
            and time.monotonic() - started >= budget_seconds)


def _budget_timeout(budget_seconds, started, default):
    if budget_seconds is None or started is None:
        return default
    remaining = budget_seconds - (time.monotonic() - started)
    return max(2.0, min(default, remaining / 2))


def update_demand(d, cfg, today, now, budget_seconds=None, started=None):
    if not cfg.get("datalab_enabled", True):
        return 0
    start = (date.fromisoformat(today)
             - timedelta(days=DATALAB_WINDOW_DAYS)).isoformat()
    updated = 0
    # v17: 상위 고정 슬롯 + 순환 슬롯 — 기존 상위 200개만 갱신되던 커버리지 한계
    targets = d.datalab_targets(today, DATALAB_PRIORITY_N, DATALAB_ROTATE_N)
    for batch in _chunks(targets, 4):
        if _budget_exhausted(budget_seconds, started):
            d.log_collection("(datalab)", "partial", "시간 예산 초과로 수요 단계 중단", now)
            break
        # v15: 잔여 예산 기반 호출 타임아웃 축소 — 스냅샷 단계만 적용되던 오버슛
        # 가드가 수요 단계에도 적용 (요청 자체는 재시도 복원력 보유)
        timeout = _budget_timeout(budget_seconds, started, DATALAB_TIMEOUT)
        try:
            ratios = fetch_demand_ratios(
                cfg["client_id"], cfg["client_secret"],
                [b["keyword"] for b in batch], cfg["datalab_anchor"], start, today,
                timeout=timeout)
        except DatalabError as e:
            d.log_collection("(datalab)", "error", str(e), now)
            break  # 수요 단계만 중단 — 나머지 파이프라인은 정상 (스펙 §4.4)
        for b in batch:
            if b["keyword"] in ratios:
                # v9: ratios[kw] = {"ratio":, "growth":} — demand_idx + 시계열 기울기 저장
                val = ratios[b["keyword"]]
                d.update_demand_idx(b["id"], today, val["ratio"])
                d.update_demand_growth(b["id"], today, val["growth"])
                updated += 1
        time.sleep(0.2)
    return updated


def update_shop_clicks(d, cfg, today, now, budget_seconds=None, started=None):
    """v4: 쇼핑 클릭 지수 — 쇼핑인사이트 검색 클릭 추이를 수요지수와 동일한
    앵커 정규화로 배치 산출 (쇼핑 검색 API 종료 대체, 스펙 §4.4).
    v17: 분야 미매칭(None)은 NULL 유지 — 진짜 저클릭과 구분 (은퇴 판정 정합)."""
    if not cfg.get("datalab_enabled", True):
        return 0
    start = (date.fromisoformat(today)
             - timedelta(days=DATALAB_WINDOW_DAYS)).isoformat()
    category = cfg.get("shopping_insight_category", "50000000")
    updated = 0
    # v17: 수요 단계와 동일한 대상 목록 — 지표 간 커버리지 정합
    targets = d.datalab_targets(today, DATALAB_PRIORITY_N, DATALAB_ROTATE_N)
    for batch in _chunks(targets, 4):
        if _budget_exhausted(budget_seconds, started):
            d.log_collection("(shopping)", "partial",
                             "시간 예산 초과로 쇼핑 클릭 단계 중단", now)
            break
        timeout = _budget_timeout(budget_seconds, started, DATALAB_TIMEOUT)
        try:
            ratios = fetch_click_ratios(
                cfg["client_id"], cfg["client_secret"],
                [b["keyword"] for b in batch], cfg["datalab_anchor"],
                category, start, today, timeout=timeout)
        except DatalabError as e:
            d.log_collection("(shopping)", "error", str(e), now)
            break  # 쇼핑 클릭 단계만 중단 — 나머지 파이프라인은 정상 (스펙 §4.4)
        for b in batch:
            val = ratios.get(b["keyword"])
            if val is not None:  # None = 분야 미매칭 → NULL 유지 (v17)
                d.update_shop_click_idx(b["id"], today, val)
                updated += 1
        time.sleep(0.2)
    return updated


def retire(d, today, now):
    base = date.fromisoformat(today)
    # v14: 기회점수 임계는 활성 키워드 최신 스냅샷의 P25 — 데이터 분포를 따라가
    # 재보정 커밋 없이도 실측 스케일과 정합 (표본 < 20 또는 P50=0이면 폴백).
    n, pct = d.percentiles("opportunity")
    if n >= RETIRE_MIN_SAMPLES and pct.get(0.5, 0) > 0:
        opp_lt = pct[0.25]
    else:
        opp_lt = RETIRE_OPPORTUNITY_LT_FALLBACK
    victims = d.find_retire_candidates(
        (base - timedelta(days=RETIRE_MIN_AGE_DAYS)).isoformat(),
        (base - timedelta(days=RETIRE_WINDOW_DAYS)).isoformat(),
        opp_lt, RETIRE_CLICK_LT)
    for v in victims:
        # v17: 클릭 데이터가 구조적으로 없는 키워드는 기회점수 단독 판정 — 사유 구분 기록
        note = ("저성과 자동 비활성 (쇼핑클릭 미수집·기회점수 단독 판정)"
                if v.get("clickless") else "저성과 자동 비활성")
        d.set_active(v["id"], 0)
        d.log_collection(v["keyword"], "retire", note, now)
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
              "demand_updated": 0, "shop_clicks_updated": 0,
              "drafts_created": 0, "draft_images_created": 0}
    try:
        # v3: 예산은 발굴·스냅샷·개별 호출 타임아웃까지 전 구간 적용
        discover(d, cfg, today, now, trigger, result, budget_seconds)
        client = client or NaverClient(cfg["client_id"], cfg["client_secret"])
        snapshot(d, cfg, client, today, now, started, budget_seconds, result)
        if trigger == "schedule":
            base = date.fromisoformat(today)
            result["demand_updated"] = update_demand(
                d, cfg, today, now, budget_seconds, started)
            # v4: 쇼핑 클릭 지수 (쇼핑인사이트) — 수요 단계와 동일 패턴
            result["shop_clicks_updated"] = update_shop_clicks(
                d, cfg, today, now, budget_seconds, started)
            result["retired"] = retire(d, today, now)
            d.cleanup(
                (base - timedelta(days=STATS_RETENTION_DAYS)).isoformat(),
                (base - timedelta(days=TOP_RESULTS_RETENTION_DAYS)).isoformat(),
                (base - timedelta(days=LOG_RETENTION_DAYS)).isoformat(),
            )
            # v17: 콘텐츠 배치 — 시간 제약 없는 스케줄 실행(GH Actions)에서만.
            # budget_seconds가 설정된 실행(Vercel /collect 45초)은 이미지 1장도
            # 못 끝내므로 건너뛴다. 실패해도 수집 성과는 보존 (오류만 기록).
            if budget_seconds is None and cfg.get("content_batch_enabled", True):
                try:
                    import content_batch
                    batch = content_batch.run_content_batch(
                        d, cfg, today, now, client)
                    result["drafts_created"] = batch.get("drafts_created", 0)
                    result["draft_images_created"] = batch.get(
                        "draft_images_created", 0)
                except Exception as e:
                    logger.warning("content batch failed: %s", e)
                    d.log_collection("(content)", "error", str(e), now)
                    result["errors"].append(f"content_batch: {e}")
        # v3: 상태 구분 — done(전량 성공) / partial(예산 종료·일부 오류·발굴 중단) / failed(전량 실패)
        if result["errors"] and result["snapshotted"] == 0:
            status = "failed"
        elif result["partial"] or result["errors"] or result["crawl_stopped"]:
            status = "partial"
        else:
            status = "done"
        # v14 §1.2: 노이즈 유입률(거부율) — 발굴이 있었던 실행만 note에 JSON 기록
        # (대시보드는 collection_runs.note 파싱으로 노출 — 스펙 §5)
        note = ""
        if result.get("found_raw"):
            note = json.dumps({
                "found_raw": result["found_raw"],
                "rejected": result.get("rejected", 0),
                "reject_rate": round(result.get("rejected", 0) / result["found_raw"], 4),
            }, ensure_ascii=False)
        d.finish_run(run_id, status, config_mod.now_kst_iso(), result, note)
    except Exception:
        d.finish_run(run_id, "failed", config_mod.now_kst_iso(), result)
        raise
    finally:
        d.close()
    return result


def main():
    # v15: print → 구조화 로그 (관측성 공백 해소 시작점)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    cfg = config_mod.load_config()
    result = run_collection(cfg, trigger="schedule")
    if result.get("locked"):
        logger.info("이미 수집이 실행 중입니다 — 종료")
        raise SystemExit(0)
    logger.info(
        "완료: 신규 %d개, 스냅샷 %d개, 수요갱신 %d개, 쇼핑클릭 %d개, 은퇴 %d개, "
        "초안 %d개, 이미지 %d개, 오류 %d개%s",
        result["new_keywords"], result["snapshotted"], result["demand_updated"],
        result["shop_clicks_updated"], result["retired"],
        result.get("drafts_created", 0), result.get("draft_images_created", 0),
        len(result["errors"]),
        f" — 발굴 중단({result.get('crawl_stopped')})"
        if result.get("crawl_stopped") else "")
    # v3: 자동완성 차단은 스냅샷 성공 여부와 무관하게 exit 1 — 차단을 조기에 인지해야
    # 대체 스케줄러(cron-job.org)로 전환할 수 있음 (스펙 §5)
    # v17: 'error'(예상치 못한 예외)도 동일하게 조기 인지 대상
    if result.get("crawl_stopped") in ("blocked", "error"):
        raise SystemExit(1)
    # 전량 실패 시 exit 1 → GitHub Actions 실패 메일로 조기 인지 (스펙 §5)
    if result["errors"] and result["snapshotted"] == 0:
        raise SystemExit(1)
    raise SystemExit(0)


if __name__ == "__main__":
    sys.exit(main())
