import hmac
import os
import threading
from datetime import timedelta

import config as config_mod
import db
from fastapi import Body, Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel


class SeedIn(BaseModel):
    keyword: str
    category: str = ""


class KeywordPatch(BaseModel):
    active: bool


class CollectIn(BaseModel):
    trigger: str = "manual"  # "schedule" = cron-job.org 대체 스케줄러 (전 구간, v3)


def create_app(cfg):
    env = cfg.get("env", "development")
    # v3: fail-closed — 프로덕션에서 토큰 미설정 시 기동 거부 (스펙 §7).
    # v2는 토큰이 비면 인증을 생략해 설정 실수가 무인증 쓰기 API로 이어졌음.
    # 로컬 개발(ENV 미설정/development)만 인증 생략 허용
    if env == "production" and not cfg.get("dashboard_token", ""):
        raise RuntimeError("DASHBOARD_TOKEN required in production (fail-closed)")
    app = FastAPI()
    state = {"db": None}
    lock = threading.Lock()

    def get_db():
        if state["db"] is None:
            state["db"] = db.Database(cfg["db_url"])
            state["db"].init()
        return state["db"]

    def run_db(fn):
        # 서버리스에서 유휴 종료된 커넥션 대비: 연결 오류 1회 재연결 후 재시도 (스펙 §3)
        with lock:
            try:
                return fn(get_db())
            except db.CONNECTION_ERRORS:
                state["db"] = None
                return fn(get_db())

    def require_token(authorization: str = Header(default="")):
        token = cfg.get("dashboard_token", "")
        if token and not hmac.compare_digest(authorization, f"Bearer {token}"):
            raise HTTPException(status_code=401, detail="invalid token")

    @app.get("/keywords")
    def list_keywords(sort: str = "opportunity", sort_dir: str = "desc",
                      category: str = "", commercial_min: float = 0,
                      q: str = "", discovered_within: int = 0,
                      preset: str = "", show_inactive: int = 0,
                      page: int = 1, page_size: int = 50):
        page = max(page, 1)
        page_size = min(max(page_size, 1), 200)
        discovered_since = ""
        if discovered_within > 0:
            discovered_since = (
                config_mod.today_kst() - timedelta(days=discovered_within)
            ).isoformat()
        # v3: 유망 프리셋 — UX §8 "유망" 버튼 (기회≥70 & 상업성≥60 & 수요지수≥0.01)
        opportunity_min, demand_min = 0.0, 0.0
        if preset == "promising":
            opportunity_min, commercial_min, demand_min = 70.0, 60.0, 0.01
        filters = dict(category=category, commercial_min=commercial_min, q=q,
                       discovered_since=discovered_since,
                       active=None if show_inactive else 1,
                       opportunity_min=opportunity_min, demand_min=demand_min)
        items = run_db(lambda d: d.query_keywords(
            sort=sort, sort_dir=sort_dir, limit=page_size,
            offset=(page - 1) * page_size, **filters))
        total = run_db(lambda d: d.count_keywords(**filters))
        return {"items": items, "count": total, "page": page, "page_size": page_size}

    @app.get("/keywords/{keyword_id}")
    def keyword_detail(keyword_id: int):
        kw = run_db(lambda d: d.get_keyword(keyword_id))
        if not kw:
            raise HTTPException(status_code=404, detail="not found")
        history = run_db(lambda d: d.get_history(keyword_id))
        return {"keyword": kw["keyword"], "active": kw["active"], "history": history}

    @app.patch("/keywords/{keyword_id}", dependencies=[Depends(require_token)])
    def patch_keyword(keyword_id: int, body: KeywordPatch):
        kw = run_db(lambda d: d.get_keyword(keyword_id))
        if not kw:
            raise HTTPException(status_code=404, detail="not found")
        run_db(lambda d: d.set_active(keyword_id, 1 if body.active else 0))
        return {"ok": True}

    @app.get("/seeds")
    def list_seeds():
        return run_db(lambda d: d.list_seeds())

    @app.post("/seeds", dependencies=[Depends(require_token)])
    def add_seed(seed: SeedIn):
        run_db(lambda d: d.add_seed(seed.keyword, seed.category))
        return {"ok": True}

    @app.delete("/seeds/{seed_id}", dependencies=[Depends(require_token)])
    def delete_seed(seed_id: int):
        run_db(lambda d: d.delete_seed(seed_id))
        return {"ok": True}

    @app.post("/collect", dependencies=[Depends(require_token)])
    def trigger_collect(body: CollectIn = Body(default_factory=CollectIn)):
        import collect
        if body.trigger == "schedule":
            # v3: cron-job.org 대체 경로 — 전체 파이프라인(발굴·수요·은퇴·보존).
            # Vercel 60초 한도 내라 예산(45초)을 걸어 전 구간 예산 적용 + 잔여는 다음 실행이 순환
            return collect.run_collection(
                cfg, trigger="schedule",
                budget_seconds=cfg.get("manual_budget_seconds", 45))
        return collect.run_collection(
            cfg, trigger="manual",
            budget_seconds=cfg.get("manual_budget_seconds", 45))

    @app.get("/status")
    def status():
        runs = run_db(lambda d: d.get_last_runs(5))
        # v3: partial/failed는 성공 수집으로 집계하지 않음 (UX §5.2 경고 기준)
        last_success = next((r for r in runs if r["status"] == "done"), None)
        return {
            "keyword_count": run_db(lambda d: d.count_active()),
            "seed_count": len(run_db(lambda d: d.list_seeds())),
            "today": config_mod.today_kst().isoformat(),
            "last_run": runs[0] if runs else None,
            "last_success": last_success,
        }

    @app.get("/categories")
    def categories():
        return run_db(lambda d: d.list_categories())

    @app.get("/")
    def index():
        return FileResponse(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "static", "index.html"))

    return app


app = create_app(config_mod.load_config())
