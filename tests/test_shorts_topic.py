# v31: 쇼츠 파이프라인 S-2 — 주제 판정·틈새 스코어 회귀 테스트
# (docs/planning/14-shorts-pipeline.md §3.2 개정 지표 기준)
import json
from datetime import datetime, timedelta

import db
import shorts_topic as st
from fastapi.testclient import TestClient
from server import create_app

NOW = datetime(2026, 8, 16, 12, 0, 0,
               tzinfo=st.KST)


def make_db(tmp_path):
    d = db.Database(f"sqlite:///{tmp_path / 't.db'}")
    d.init()
    return d


def _video(vid, tag, views=100_000, likes=5_000, comments=500, subs=None,
           published_hours_ago=24.0, channel="ch1"):
    published = (NOW - timedelta(hours=published_hours_ago)
                 ).strftime("%Y-%m-%dT%H:%M:%S+09:00")
    return {
        "video_id": vid, "title": f"{vid} 제목",
        "tags": json.dumps([tag]), "description": "",
        "channel_id": channel, "channel_title": channel,
        "published_at": published, "view_count": views,
        "like_count": likes, "comment_count": comments,
        "share_count": None, "subscriber_count": subs,
        "region": "KR", "fetched_at": NOW.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
    }


def test_recent_high_velocity_topic_scores_higher_than_stale():
    recent = [_video("r1", "운명", views=400_000, published_hours_ago=24.0),
              _video("r2", "운명", views=300_000, published_hours_ago=30.0)]
    stale = [_video("s1", "여행", views=400_000, published_hours_ago=24 * 20),
             _video("s2", "여행", views=300_000, published_hours_ago=24 * 25)]
    results = {r["label"]: r for r in st.score_topics(recent + stale, now=NOW)}
    assert results["운명"]["score"] > results["여행"]["score"]  # ① 급상승 우선
    assert results["운명"]["evidence"]["velocity"] > 0
    assert results["여행"]["evidence"]["velocity"] == 0  # 48h 창 밖


def test_small_channel_explosion_contributes():
    small = [_video("a1", "소형", views=500_000, subs=10_000,
                    published_hours_ago=24),
             _video("a2", "소형", views=400_000, subs=20_000,
                    published_hours_ago=30)]
    big = [_video("b1", "대형", views=500_000, subs=5_000_000,
                  published_hours_ago=24),
           _video("b2", "대형", views=400_000, subs=8_000_000,
                  published_hours_ago=30)]
    results = {r["label"]: r for r in st.score_topics(small + big, now=NOW)}
    assert results["소형"]["evidence"]["small_channel"] == 1.0  # 50배 → 포화
    assert results["소형"]["score"] > results["대형"]["score"]


def test_niche_fewer_videos_beats_saturated_cluster():
    niche = [_video("n1", "틈새", views=300_000, published_hours_ago=24),
             _video("n2", "틈새", views=280_000, published_hours_ago=36)]
    crowded = [_video(f"c{i}", "포화", views=300_000, published_hours_ago=24)
               for i in range(10)]
    results = {r["label"]: r for r in st.score_topics(niche + crowded, now=NOW)}
    assert results["틈새"]["evidence"]["niche"] > 0
    assert results["포화"]["evidence"]["niche"] == 0  # 10개 = 경쟁 포화
    assert results["틈새"]["score"] > results["포화"]["score"]


def test_single_video_tag_not_a_topic():
    solo = [_video("x1", "외톨이"), _video("x2", "다른주제")]
    assert st.score_topics(solo, now=NOW) == []  # MIN_CLUSTER_VIDEOS=2


def test_missing_subscribers_zero_contribution_not_crash():
    rows = [_video("m1", "결측", subs=None), _video("m2", "결측", subs=None)]
    results = st.score_topics(rows, now=NOW)
    assert len(results) == 1
    assert results[0]["evidence"]["small_channel"] == 0.0
    assert results[0]["evidence"]["subscriber_known"] == 0


def test_reaction_and_weights_sum():
    rows = [_video("v1", "반응", views=100_000, likes=5_000, comments=500),
            _video("v2", "반응", views=100_000, likes=5_000, comments=500)]
    results = st.score_topics(rows, now=NOW)
    ev = results[0]["evidence"]
    # 구성요소 정합: velocity 0.5(10만뷰/1일 ÷ 20만 정규화)·reaction 1.0·
    # niche 0.4((1-2/10)×0.5) — 가중 합 = 17.5+15+10 = 42.5
    assert ev["reaction"] == 1.0 and ev["velocity"] == 0.5 and ev["niche"] == 0.4
    assert results[0]["score"] == 42.5
    assert sum(st.WEIGHTS.values()) == 100.0


def test_refresh_topics_persists_and_preserves_status(tmp_path):
    d = make_db(tmp_path)
    d.upsert_youtube_video(_video("p1", "저장", views=250_000))
    d.upsert_youtube_video(_video("p2", "저장", views=200_000))
    saved = st.refresh_topics(d, now=NOW)
    assert len(saved) == 1 and saved[0]["label"] == "저장"
    rows = d.list_shorts_topics()
    assert len(rows) == 1 and rows[0]["status"] == "candidate"
    ev = json.loads(rows[0]["evidence"])
    assert ev["videos"] == 2 and ev["sample_video_ids"]
    # S-3/S-4가 상태를 진행시킨 뒤 재산출해도 status 유지
    d._qd("UPDATE shorts_topics SET status = 'scripted'", ())
    st.refresh_topics(d, now=NOW)
    assert d.list_shorts_topics()[0]["status"] == "scripted"
    d.close()


def test_refresh_topics_empty_corpus_noop(tmp_path):
    d = make_db(tmp_path)
    assert st.refresh_topics(d, now=NOW) == []
    d.close()


# ---------- S-1 연계: 채널 구독자 병합 + 수집 후 스코어 ----------

class _FakeYouTube:
    def __init__(self):
        self.calls = []

    def videos(self):
        self.calls.append("videos.list")
        return self

    def channels(self):
        self.calls.append("channels.list")
        return self

    def list(self, **kw):
        self._last = kw
        return self

    def execute(self):
        if self._last.get("chart") == "mostPopular":
            return {"items": [
                {"id": f"vid{i}",
                 "snippet": {"title": f"t{i}", "tags": ["공통"],
                             "channelId": f"ch{i % 2}", "channelTitle": "",
                             "publishedAt": "2026-08-15T12:00:00Z",
                             "description": ""},
                 "statistics": {"viewCount": "100000", "likeCount": "5000",
                                "commentCount": "500"}}
                for i in range(4)]}
        stats = {"ch0": "10000", "ch1": "20000"}
        ids = self._last.get("id", "").split(",")
        return {"items": [
            {"id": cid, "statistics": {"subscriberCount": stats.get(cid, "1")}}
            for cid in ids if cid in stats]}


def test_run_collection_merges_subs_and_refreshes_topics(tmp_path):
    import shorts_research as sr
    d = make_db(tmp_path)
    res = sr.run_collection(d, {}, client=_FakeYouTube())
    assert res["fetched"] == 4 and not res["errors"]
    assert res["topics"] >= 1  # "공통" 태그 클러스터 → S-2 저장
    rows = d.list_youtube_videos()
    assert all(r["subscriber_count"] in (10_000, 20_000) for r in rows)
    topic = d.list_shorts_topics()[0]
    assert topic["label"] == "공통"
    assert json.loads(topic["evidence"])["subscriber_known"] == 4
    d.close()


def test_shorts_topics_endpoint(tmp_path):
    d = make_db(tmp_path)
    d.upsert_shorts_topic("라벨", 42.0, '{"videos": 2}', "candidate",
                          "2026-08-16T00:00:00+09:00")
    d.close()
    app = create_app({"db_url": f"sqlite:///{tmp_path / 't.db'}",
                      "dashboard_token": "sekret", "env": "development"})
    client = TestClient(app)
    body = client.get("/shorts/topics").json()
    assert body["items"][0]["label"] == "라벨"
    assert body["items"][0]["evidence"] == {"videos": 2}  # JSON 파싱 노출


# ---------- KDP consistency_pass 실제 반영 ----------

def test_consistency_pass_filters_short_hallucination():
    import kdp_book as kb
    chapters = [
        {"seq": 1, "title": "챕터1", "body_md": "본문 " * 100},
        {"seq": 2, "title": "챕터2", "body_md": "본문 " * 100},
    ]

    def runner(prompt, timeout=120):
        # seq1은 유효 재구성(기존 대비 50% 이상), seq2는 환각성 초단본문 → 폴백
        if "챕터1" in prompt:
            return '{"body": "' + "통일된 재구성 본문입니다. " * 60 + '"}'
        return '{"body": "짧"}'

    res = kb.consistency_pass(chapters, runner=runner)
    assert res["updated"] == 1
    assert "통일된" in res["bodies"][1]
    assert 2 not in res["bodies"]  # 50% 미만 → 원본 유지


def test_consistency_pass_bad_json_keeps_original():
    import kdp_book as kb
    chapters = [{"seq": 1, "title": "챕터1", "body_md": "원본 본문"}]
    res = kb.consistency_pass(
        chapters, runner=lambda p, timeout=120: "not json")
    assert res["updated"] == 0 and res["bodies"] == {}


def test_generate_book_persists_consistent_bodies(tmp_path):
    import kdp_book as kb
    from unittest import mock
    d = make_db(tmp_path)
    bid = d.insert_kdp_book(
        title="일관성 책", status="assembling", lang="ko",
        source_keyword="절약", created_at="2026-08-14",
        keywords_json='["절약","워크북","가이드","초보","실습","독학","문제집"]',
        category="재테크,교육", pen_name="펜", description="설명")
    bodies = {"1회": [], "2회": []}
    state = {"n": 0}

    def runner(prompt, timeout=120):
        state["n"] += 1
        i = state["n"]
        body = f"chapter{i} consistent body. " + f"token{i} " * 100
        return json.dumps({"title": "C", "first_paragraph": "요약",
                           "body": body, "tags": ["절약"]})

    with mock.patch.object(
            kb, "generate_outline",
            lambda *a, **k: [{"title": f"챕터 {i}", "bullets": ["a"]}
                             for i in range(1, 7)]):
        kb.generate_book(d, {}, bid, runner=runner, qc_enabled=False)
    # 일관성 패스 재구성 본문이 DB에 반영됐는지 (6챕터 생성 + 6 재구성 호출)
    rows = d.list_kdp_chapters(bid)
    assert len(rows) == 6
    assert all("consistent body" in (r["body_md"] or "") for r in rows)
    d.close()
