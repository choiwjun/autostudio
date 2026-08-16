# v31: 쇼츠 파이프라인 S-3 — 스크립트 생성·검수 회귀 테스트
# (docs/planning/14-shorts-pipeline.md §3.3: 30~45초 80~120자·후킹 3초·CTA·금지어)
import json

import db
import shorts_script as ss
from fastapi.testclient import TestClient
from server import create_app

HOOK = "이 차이, 알고 계셨나요?"           # 13자 — 후킹 규칙 통과
CTA = "다음 편도 구독해서 확인하세요."      # '구독' 마커 포함
HASHTAGS = ["#쇼츠", "#꿀팁", "#실용"]


def _body(fill=6):
    # 기본: 총 94자(hook 13 + 구분 4 + 본문 60 + CTA 17) — 80~120 밴드 안
    return "본문 문장입니다. " * fill


def make_db(tmp_path):
    d = db.Database(f"sqlite:///{tmp_path / 't.db'}")
    d.init()
    return d


def _seed_topic(d, label="꿀팁", with_videos=False):
    ref_ids = []
    if with_videos:
        for i in range(2):
            d.upsert_youtube_video({
                "video_id": f"vid{i}", "title": f"{label} 참고영상 {i}",
                "region": "KR",
                "fetched_at": "2026-08-16T09:00:00+09:00"})
        ref_ids = ["vid0", "vid1"]
    d.upsert_shorts_topic(
        label, 55.0,
        json.dumps({"videos": 3, "sample_video_ids": ref_ids}),
        "candidate", "2026-08-16T09:00:00+09:00")
    return ref_ids


def _ok_runner(prompt, timeout=60):
    assert "80~120자" in prompt            # 규칙이 프롬프트에 명시됐는지
    assert "후킹" in prompt
    return json.dumps({"hook": HOOK, "script": _body(),
                       "cta": CTA, "hashtags": HASHTAGS})


# ---------- 검수 5종 ----------

def test_validate_pass():
    script_md = ss._compose(HOOK, _body(), CTA)
    assert 80 <= len(script_md) <= 120      # 전제 확인
    ok, failed = ss.validate_script(HOOK, script_md, CTA, HASHTAGS)
    assert ok and failed == []


def test_validate_length_band():
    short = ss._compose(HOOK, _body(1), CTA)   # 과소
    long_ = ss._compose(HOOK, _body(60), CTA)  # 과대
    for md in (short, long_):
        assert "length" in ss.validate_script(HOOK, md, CTA, HASHTAGS)[1]


def test_validate_hook_and_cta():
    md = ss._compose(HOOK, _body(), CTA)
    _, f1 = ss.validate_script("", md, CTA, HASHTAGS)
    assert "hook" in f1
    _, f2 = ss.validate_script("후" * 50, md, CTA, HASHTAGS)  # 40자 초과
    assert "hook" in f2
    _, f3 = ss.validate_script(HOOK, md, "그럼 이만", HASHTAGS)  # 마커 없음
    assert "cta" in f3


def test_validate_banned_and_factual():
    bad_body = "이 방법은 100% 효과가 보장합니다. " * 3
    md = ss._compose(HOOK, bad_body, CTA)
    _, failed = ss.validate_script(HOOK, md, CTA, HASHTAGS)
    assert "banned_words" in failed
    md2 = ss._compose(HOOK, "검증된 통계에 따르면 좋습니다. " * 3, CTA)
    _, f2 = ss.validate_script(HOOK, md2, CTA, HASHTAGS)
    assert "factual_claims" in f2


def test_validate_hashtags_count():
    md = ss._compose(HOOK, _body(), CTA)
    _, f1 = ss.validate_script(HOOK, md, CTA, ["#a"])
    assert "hashtags" in f1
    _, f2 = ss.validate_script(HOOK, md, CTA,
                               ["#a", "#b", "#c", "#d", "#e", "#f"])
    assert "hashtags" in f2


def test_normalize_hashtags_dedup_and_prefix():
    assert ss._normalize_hashtags(["a", "#a", " b ", ""]) == ["#a", "#b"]


# ---------- 생성 파이프라인 ----------

def test_generate_script_happy_path_persists_ready(tmp_path):
    d = make_db(tmp_path)
    _seed_topic(d, with_videos=True)
    res = ss.generate_script(d, "꿀팁", runner=_ok_runner)
    assert res["status"] == ss.STATUS_READY and res["failed"] == []
    row = d.get_shorts_script(res["script_id"])
    assert row["topic"] == "꿀팁"
    assert row["hook"] == HOOK and "구독" in row["script_md"]
    assert json.loads(row["hashtags"]) == HASHTAGS
    assert json.loads(row["ref_video_ids"]) == ["vid0", "vid1"]  # 근거 연결
    d.close()


def test_generate_script_retry_with_feedback_then_pass(tmp_path):
    d = make_db(tmp_path)
    _seed_topic(d)
    calls = []

    def runner(prompt, timeout=60):
        calls.append(prompt)
        if len(calls) == 1:
            # 1회차 — 길이 초과 (피드백 주입 확인용)
            return json.dumps({"hook": HOOK, "script": _body(50),
                               "cta": CTA, "hashtags": HASHTAGS})
        assert "80~120자" in prompt and "자로 허용 범위" in prompt  # 실측 피드백
        return json.dumps({"hook": HOOK, "script": _body(),
                           "cta": CTA, "hashtags": HASHTAGS})

    res = ss.generate_script(d, "꿀팁", runner=runner)
    assert res["status"] == ss.STATUS_READY
    assert len(calls) == 2                    # 정확히 1회 재시도
    d.close()


def test_generate_script_final_fail_stored_qc_failed(tmp_path):
    d = make_db(tmp_path)
    _seed_topic(d)
    res = ss.generate_script(
        d, "꿀팁",
        runner=lambda p, timeout=60: json.dumps(
            {"hook": HOOK, "script": _body(1), "cta": CTA,
             "hashtags": HASHTAGS}))
    assert res["status"] == ss.STATUS_QC_FAILED
    assert "length" in res["failed"]
    row = d.get_shorts_script(res["script_id"])
    assert json.loads(row["qc_detail"]) == ["length"]
    d.close()


def test_generate_script_recovers_first_parse_on_second_failure(tmp_path):
    """v31 패턴 — 2회차 파싱 실패 시 1회차 유효 스크립트 폐기하지 않음."""
    d = make_db(tmp_path)
    _seed_topic(d)
    calls = []

    def runner(prompt, timeout=60):
        calls.append(1)
        if len(calls) == 1:
            return json.dumps({"hook": HOOK, "script": _body(),
                               "cta": CTA, "hashtags": HASHTAGS})
        return "not json"                     # 2회차 하드 실패

    res = ss.generate_script(d, "꿀팁", runner=runner)
    assert res["status"] == ss.STATUS_READY   # 1회차분 회수
    d.close()


def test_generate_script_all_parse_fail_raises(tmp_path):
    d = make_db(tmp_path)
    _seed_topic(d)
    try:
        ss.generate_script(d, "꿀팁",
                           runner=lambda p, timeout=60: "not json")
    except ss.ScriptGenerationError:
        d.close()
        return
    raise AssertionError("전체 파싱 실패 시 ScriptGenerationError여야 함")


def test_generate_script_unknown_topic_returns_none(tmp_path):
    d = make_db(tmp_path)
    assert ss.generate_script(d, "없는주제", runner=_ok_runner) is None
    d.close()


# ---------- S-4 배치 (run_batch) ----------

def test_run_batch_generates_missing_topics_only(tmp_path):
    d = make_db(tmp_path)
    for i, label in enumerate(("주제A", "주제B", "주제C")):
        d.upsert_shorts_topic(label, 90.0 - i, "{}", "candidate",
                              "2026-08-16T09:00:00+09:00")
    # 주제A는 이미 ready 스크립트 보유 → 재생성 대상 제외 (멱등)
    now = "2026-08-16T10:00:00+09:00"
    d.insert_shorts_script("주제A", HOOK, ss._compose(HOOK, _body(), CTA),
                           json.dumps(HASHTAGS), "[]", ss.STATUS_READY,
                           "[]", now, now)
    res = ss.run_batch(d, limit=2, runner=_ok_runner)
    assert [r["topic"] for r in res] == ["주제B", "주제C"]   # 상위 스코어 순
    assert all(r["status"] == ss.STATUS_READY for r in res)
    # A는 여전히 1건 (재생성 안 함)
    a_rows = [s for s in d.list_shorts_scripts() if s["topic"] == "주제A"]
    assert len(a_rows) == 1
    d.close()


def test_run_batch_empty_noop(tmp_path):
    d = make_db(tmp_path)
    assert ss.run_batch(d, limit=3, runner=_ok_runner) == []
    d.close()


def test_run_batch_error_isolated_per_topic(tmp_path):
    d = make_db(tmp_path)
    d.upsert_shorts_topic("주제X", 50.0, "{}", "candidate",
                          "2026-08-16T09:00:00+09:00")
    res = ss.run_batch(d, limit=1, runner=lambda p, timeout=60: "not json")
    assert res[0]["status"] == "error" and res[0]["failed"]
    d.close()


# ---------- API 엔드포인트 ----------

def test_shorts_script_endpoints(tmp_path, monkeypatch):
    d = make_db(tmp_path)
    _seed_topic(d, "운세")
    d.close()

    def fake_generate(conn, topic, runner=None, topic_row=None):
        if not any(r["label"] == topic for r in conn.list_shorts_topics()):
            return None  # 실제 구현 동작 — 미지정 주제
        sid = conn.insert_shorts_script(
            topic=topic, hook=HOOK,
            script_md=ss._compose(HOOK, _body(), CTA),
            hashtags_json=json.dumps(HASHTAGS),
            ref_video_ids_json="[]", status=ss.STATUS_READY,
            qc_detail_json="[]",
            created_at="2026-08-16T10:00:00+09:00",
            updated_at="2026-08-16T10:00:00+09:00")
        return {"script_id": sid, "topic": topic,
                "status": ss.STATUS_READY, "failed": []}

    monkeypatch.setattr(ss, "generate_script", fake_generate)
    app = create_app({"db_url": f"sqlite:///{tmp_path / 't.db'}",
                      "dashboard_token": "sekret", "env": "development"})
    client = TestClient(app)
    resp = client.post("/shorts/scripts", json={"topic": "운세"})
    assert resp.status_code == 200
    sid = resp.json()["script_id"]
    # 목록 — hashtags/qc_detail 파싱 노출
    body = client.get("/shorts/scripts?status=ready").json()
    item = next(it for it in body["items"] if it["id"] == sid)
    assert isinstance(item["hashtags"], list) and item["hashtags"][0].startswith("#")
    assert item["qc_detail"] == []
    # 없는 주제 404
    assert client.post("/shorts/scripts", json={"topic": "없음"}).status_code == 404
