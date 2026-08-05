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


class DraftIn(BaseModel):
    keyword_id: int


def create_app(cfg):
    env = cfg.get("env", "development")
    # v3: fail-closed — 프로덕션에서 토큰 미설정 시 기동 거부 (스펙 §7).
    # v2는 토큰이 비면 인증을 생략해 설정 실수가 무인증 쓰기 API로 이어졌음.
    # 로컬 개발(ENV 미설정/development)만 인증 생략 허용
    if env == "production" and not cfg.get("dashboard_token", ""):
        raise RuntimeError("DASHBOARD_TOKEN required in production (fail-closed)")
    app = FastAPI()

    @app.middleware("http")
    async def strip_api_prefix(request, call_next):
        # Vercel: api/index.py는 /api/* 에만 매핑되고 최신 런타임은 rewrite된
        # destination path(/api)로 라우팅한다. /api 프리픽스를 제거해 라우트와
        # 매칭시킨다. 프리픽스 없는 요청(로컬)은 그대로 통과시킨다.
        path = request.url.path
        if path == "/api":
            request.scope["path"] = "/"
            request.scope["raw_path"] = b"/"
        elif path.startswith("/api/"):
            new_path = path[4:]
            request.scope["path"] = new_path
            request.scope["raw_path"] = new_path.encode()
        return await call_next(request)

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
        # v6: 로컬 개발(development)은 토큰이 설정돼 있어도 인증 생략 — README
        # "로컬 개발만 인증 생략"과 일치. .env.local에 DASHBOARD_TOKEN이 있어도
        # 개발 편의를 위해 쓰기 API가 401을 내지 않도록 한다 (프로덕션만 강제).
        if env == "development":
            return
        token = cfg.get("dashboard_token", "")
        if token and not hmac.compare_digest(authorization, f"Bearer {token}"):
            raise HTTPException(status_code=401, detail="invalid token")

    @app.get("/keywords")
    def list_keywords(sort: str = "priority", sort_dir: str = "desc",
                      category: str = "", commercial_min: float = 0,
                      click_min: float = 0, q: str = "",
                      discovered_within: int = 0,
                      preset: str = "ai_pick", show_inactive: int = 0,
                      page: int = 1, page_size: int = 50):
        page = max(page, 1)
        page_size = min(max(page_size, 1), 200)
        discovered_since = ""
        if discovered_within > 0:
            discovered_since = (
                config_mod.today_kst() - timedelta(days=discovered_within)
            ).isoformat()
        # v4: 유망 프리셋 — 기회≥70 & 쇼핑클릭≥0.5 & 수요지수≥0.01 (쇼핑 검색 API 종료 대체)
        # v6: 기본 프리셋 'ai_pick' — AI 인용 가능성 + 수요(조회수 프록시) 기반,
        #     애드포스트 1차 목표에 맞는 '지금 써야 할 키워드' 상위 20개 중심
        opportunity_min, demand_min, ai_cite_min = 0.0, 0.0, 0.0
        if preset == "promising":
            opportunity_min, click_min, demand_min = 70.0, 0.5, 0.01
        elif preset == "ai_pick":
            # v6: demand_idx는 데이터랩 앵커('냉장고') 대비 상대 비율 — 실측 0~0.01 분포.
            #     0.2 임계는 전 키워드 탈락을 유발해 0.001(앵커의 0.1%)로 현실화 (임계는 절대값이 아닌 상대값)
            ai_cite_min, demand_min = 0.6, 0.001
        filters = dict(category=category, commercial_min=commercial_min, q=q,
                       discovered_since=discovered_since,
                       active=None if show_inactive else 1,
                       opportunity_min=opportunity_min, demand_min=demand_min,
                       click_min=click_min, ai_cite_min=ai_cite_min)
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

    @app.get("/outlines/{keyword_id}")
    def get_outline(keyword_id: int):
        outline = run_db(lambda d: d.get_outline(keyword_id))
        if not outline:
            raise HTTPException(status_code=404, detail="outline not found")
        return outline

    @app.post("/outlines/{keyword_id}", dependencies=[Depends(require_token)])
    def analyze_outline(keyword_id: int):
        # v7: 상위글 골격 분석 — 블로그 검색 API description 캡처 → structure JSON 저장
        kw = run_db(lambda d: d.get_keyword(keyword_id))
        if not kw:
            raise HTTPException(status_code=404, detail="not found")
        import analyzer
        import outline as outline_mod
        from naver_client import NaverClient
        client = NaverClient(cfg.get("client_id", ""), cfg.get("client_secret", ""))
        snap = analyzer.analyze_keyword(client, kw["keyword"], config_mod.today_kst())
        structure = outline_mod.build_outline_structure(snap["top_descriptions"])
        day = config_mod.today_kst().isoformat()
        run_db(lambda d: d.upsert_outline(keyword_id, day, structure))
        return run_db(lambda d: d.get_outline(keyword_id))

    @app.post("/drafts", dependencies=[Depends(require_token)])
    def create_draft(body: DraftIn):
        # v7: 글 초안 생성 — 골격 기반 opencode CLI 실행 (deepseek-v4-flash)
        import draft_generator
        kw = run_db(lambda d: d.get_keyword(body.keyword_id))
        if not kw:
            raise HTTPException(status_code=404, detail="not found")
        outline = run_db(lambda d: d.get_outline(body.keyword_id))
        structure = (outline["structure"] if outline
                     else '{"questions": [], "comparisons": [], "facts": []}')
        draft = draft_generator.generate_draft(kw["keyword"], structure)
        created_at = config_mod.now_kst_iso()
        draft_id = run_db(lambda d: d.insert_draft(
            body.keyword_id, draft["title"], draft["first_paragraph"],
            draft["body"], created_at=created_at))
        return run_db(lambda d: d.get_draft(draft_id))

    @app.get("/drafts/{draft_id}")
    def get_draft(draft_id: int):
        draft = run_db(lambda d: d.get_draft(draft_id))
        if not draft:
            raise HTTPException(status_code=404, detail="not found")
        return draft

    @app.post("/drafts/{draft_id}/image", dependencies=[Depends(require_token)])
    def generate_draft_image(draft_id: int):
        # v7: 블로그 이미지 생성 — 키 미발급 시 503(명확한 안내), 텍스트 초안은 유지
        import image_gen
        draft = run_db(lambda d: d.get_draft(draft_id))
        if not draft:
            raise HTTPException(status_code=404, detail="not found")
        try:
            url = image_gen.generate_image(
                run_db(lambda d: d.get_keyword(draft["keyword_id"]))["keyword"],
                draft["title"])
        except image_gen.ImageGenerationError as e:
            raise HTTPException(status_code=503, detail=str(e))
        run_db(lambda d: d.update_draft_image(
            draft_id, url, config_mod.now_kst_iso()))
        return run_db(lambda d: d.get_draft(draft_id))

    @app.get("/")
    def index():
        return FileResponse(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "static", "index.html"))

    return app


app = create_app(config_mod.load_config())
