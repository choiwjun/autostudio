# v30.3: 쇼츠 S-1 유튜브 수집 (shorts_research) — AC-S1-1~4
import json

import db
import shorts_research as sr


def make_db(tmp_path):
    d = db.Database(f"sqlite:///{tmp_path / 't.db'}")
    d.init()
    return d


# ---- 스키마/멱등 (AC-S1-1) ----
def test_youtube_raw_schema_and_upsert(tmp_path):
    d = make_db(tmp_path)
    v1 = {"video_id": "abc123", "title": "테스트 영상", "tags": json.dumps(["재테크", "주식"], ensure_ascii=False),
          "description": "설명", "channel_id": "ch1", "channel_title": "채널A",
          "published_at": "2026-08-01T00:00:00Z", "view_count": 1000,
          "like_count": 50, "comment_count": 3, "share_count": None,
          "region": "KR", "fetched_at": "2026-08-16T00:00:00+09:00"}
    d.upsert_youtube_video(v1)
    assert d.count_youtube_videos() == 1

    # 재수집(같은 video_id) — UPSERT 멱등 (행 수 동일, 값 갱신)
    v1b = dict(v1, view_count=2000, like_count=80)
    d.upsert_youtube_video(v1b)
    assert d.count_youtube_videos() == 1
    rows = d.list_youtube_videos()
    assert rows[0]["view_count"] == 2000
    assert rows[0]["like_count"] == 80
    assert json.loads(rows[0]["tags"]) == ["재테크", "주식"]  # JSON 문자열 저장


def test_youtube_video_list_region_filter(tmp_path):
    d = make_db(tmp_path)
    for i in range(5):
        d.upsert_youtube_video({"video_id": f"v{i}", "title": f"영상{i}",
                                "region": "KR", "fetched_at": "2026-08-16T00:00:00+09:00"})
    d.upsert_youtube_video({"video_id": "us1", "title": "US", "region": "US",
                            "fetched_at": "2026-08-16T00:00:00+09:00"})
    assert d.count_youtube_videos() == 6
    assert d.count_youtube_videos(region="KR") == 5
    rows = d.list_youtube_videos(region="KR", limit=3)
    assert len(rows) == 3


# ---- 쿼터 로그 (AC-S1-1③, AC-S1-4③) ----
def test_quota_log_and_usage(tmp_path):
    d = make_db(tmp_path)
    d.log_youtube_quota("2026-08-16T07:00:00+09:00", "videos.list", 1)
    d.log_youtube_quota("2026-08-16T07:01:00+09:00", "videos.list", 1)
    d.log_youtube_quota("2026-08-16T07:02:00+09:00", "search.list", 1)
    usage, total = d.youtube_quota_usage("2026-08-16")
    assert usage["videos.list"] == 2
    assert usage["search.list"] == 1
    assert total == 3


# ---- API 응답 → 내부 레코드 변환 (AC-S1-1) ----
def test_parse_video_item():
    item = {
        "id": "vid1",
        "snippet": {
            "title": "제목", "description": "설명",
            "channelId": "ch1", "channelTitle": "채널A",
            "publishedAt": "2026-08-01T00:00:00Z",
            "tags": ["태그1", "태그2"],
        },
        "statistics": {"viewCount": "1234", "likeCount": "56",
                       "commentCount": "7"},
    }
    rec = sr._parse_video_item(item, region="KR", fetched_at="2026-08-16T00:00:00+09:00")
    assert rec["video_id"] == "vid1"
    assert rec["title"] == "제목"
    assert rec["view_count"] == 1234
    assert rec["like_count"] == 56
    assert rec["comment_count"] == 7
    assert rec["region"] == "KR"
    assert json.loads(rec["tags"]) == ["태그1", "태그2"]


# ---- 인기 동영상 수집 (AC-S1-1①) ----
def test_fetch_popular_videos_stores_rows(tmp_path, monkeypatch):
    d = make_db(tmp_path)

    class FakeResp:
        def execute(self):
            return {"items": [
                {"id": "p1",
                 "snippet": {"title": "인기1", "description": "d",
                             "channelId": "c1", "channelTitle": "채널1",
                             "publishedAt": "2026-08-10T00:00:00Z", "tags": ["a"]},
                 "statistics": {"viewCount": "1000", "likeCount": "10",
                                "commentCount": "1"}},
                {"id": "p2",
                 "snippet": {"title": "인기2", "description": "d",
                             "channelId": "c2", "channelTitle": "채널2",
                             "publishedAt": "2026-08-11T00:00:00Z"},
                 "statistics": {"viewCount": "2000", "likeCount": "20",
                                "commentCount": "2"}},
            ]}

    class FakeVideos:
        def list(self, **kwargs):
            assert kwargs["chart"] == "mostPopular"
            assert kwargs["regionCode"] == "KR"
            assert kwargs["maxResults"] == 50
            return FakeResp()

    class FakeYT:
        def videos(self):
            return FakeVideos()

    calls = []
    monkeypatch.setattr(sr, "_build_client", lambda key_path=None: FakeYT())
    result = sr.fetch_popular_videos(d, client=None, region="KR",
                                     max_results=50, fetched_at="2026-08-16T00:00:00+09:00")
    assert d.count_youtube_videos(region="KR") == 2
    assert result["fetched"] == 2
    assert result["quota_units"] == 1  # videos.list 1회 = 1 unit
    # 쿼터 로그 기록 확인
    usage, total = d.youtube_quota_usage("2026-08-16")
    assert usage.get("videos.list") == 1


# ---- 예산/한도 (AC-S1-4) ----
def test_quota_budget_guard(tmp_path):
    # 쿼터 예산 계산 로직 검증
    budget = sr.QUOTA_BUDGET_DAILY  # 100
    used = 60
    remaining = sr.quota_remaining(used, budget)
    assert remaining == 40
    assert sr.quota_exceeded(used, budget) is False
    assert sr.quota_exceeded(101, budget) is True
