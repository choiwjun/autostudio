# shorts_topic.py — v31: 쇼츠 파이프라인 S-2 주제 판정·틈새 스코어
# (docs/planning/14-shorts-pipeline.md §3.2 — 리서치 R-2 개정 지표)
#
# 개정 판정 지표 (API 수집 가능 대상, 가중 합 100점):
#   ① 조회 급상승(24~48h) 35점 — 탐색→활용 전환 신호 (1순위)
#   ② 조회/구독 비율        25점 — 소형 채널 폭발 = 디스커버리 성공 대리 지표
#   ③ 반응비(좋아요·댓글)   15점 — 보조·만족도 참고 (33억 뷰 연구: 상관 약함)
#   ④ 틈새(경쟁 적음+수요)  25점 — 동일 주제 영상 수 적을수록, 평균 조회 높을수록
#   ⑤ 공유율 — 채널 소유 시에만 API 제공(조건부) → 판정 제외, evidence에만 기록
#
# 주제 클러스터: youtube_raw.tags(창작자 태그) 기반 결정적 클러스터링.
# LLM 클러스터링(스펙 대안)은 S-2 범위 밖 — tags가 없는 영상은 후보에서 제외.
import json
import logging
from datetime import datetime, timedelta, timezone

import config as config_mod

logger = logging.getLogger("shorts_topic")

KST = timezone(timedelta(hours=9))

# 정규화 상수 — 실측 분포 재보정 전 임계(스펙 §3.2 근거치 기반)
RECENT_WINDOW_HOURS = 48      # ① 급상승 판정 창 (24~48h 중 상단)
VELOCITY_NORM = 200_000.0     # ① 일평균 조회 포화점 (views/day)
VIEWS_PER_SUB_NORM = 10.0     # ② 조회/구독 10배 = 폭발 포화점
LIKE_RATE_NORM = 0.05         # ③ 좋아요율 5% 포화점
COMMENT_RATE_NORM = 0.005     # ③ 댓글율 0.5% 포화점
NICHE_VIDEOS_NORM = 10        # ④ 동일 주제 영상 10개 = 경쟁 포화점
NICHE_DEMAND_VIEWS = 200_000  # ④ 클러스터 평균 조회 포화점
MIN_CLUSTER_VIDEOS = 2        # 단일 영상 태그는 주제로 성립 안 함
TOP_K = 10                    # 산출 상한
CORPUS_DAYS = 7               # 스코어 대상 최근 수집 분량

WEIGHTS = {"velocity": 35.0, "small_channel": 25.0,
           "reaction": 15.0, "niche": 25.0}


def _parse_age_days(published_at, now):
    """published_at(ISO 8601, Z/오프셋) → 경과 일수. 파싱 실패는 None."""
    if not published_at:
        return None
    try:
        text = published_at.strip().replace("Z", "+00:00")
        published = datetime.fromisoformat(text)
        if published.tzinfo is None:
            published = published.replace(tzinfo=KST)
        return max(0.0, (now - published).total_seconds() / 86400.0)
    except ValueError:
        return None


def _clamp01(v):
    return max(0.0, min(1.0, v))


def _topic_labels(video):
    """태그 JSON → 정규화 라벨 집합. 태그는 창작자 선별 주제어라 클러스터 키로 유효."""
    try:
        tags = json.loads(video.get("tags") or "[]")
    except (TypeError, ValueError):
        return set()
    if not isinstance(tags, list):
        return set()
    out = set()
    for t in tags:
        label = str(t or "").strip().lower()
        if label:
            out.add(label)
    return out


def _velocity(videos, now):
    """① 최근 48h 게시 영상의 최고 일평균 조회 — '지금 뜨는' 신호."""
    best = 0.0
    for v in videos:
        age = _parse_age_days(v.get("published_at"), now)
        if age is None or age * 24 > RECENT_WINDOW_HOURS:
            continue
        vpd = v.get("view_count", 0) / max(age, 0.5)  # 최소 0.5일 — 0나누기·과대 방지
        best = max(best, vpd)
    return _clamp01(best / VELOCITY_NORM)


def _small_channel(videos):
    """② max(조회/구독) — 소형 채널이 조회를 폭발시켰으면 디스커버리 성공.
    구독자수 미수집(rows NULL) 채널은 0 기여 — evidence에 결측 비율 기록."""
    best = 0.0
    known = 0
    for v in videos:
        subs = v.get("subscriber_count")
        if not subs:
            continue
        known += 1
        best = max(best, v.get("view_count", 0) / subs)
    return _clamp01(best / VIEWS_PER_SUB_NORM), known


def _reaction(videos):
    """③ 평균 반응비(좋아요율·댓글율 각 정규화 후 평균) — 만족도 보조 신호."""
    rates = []
    for v in videos:
        views = v.get("view_count", 0)
        if views <= 0:
            continue
        like_r = (v.get("like_count", 0) or 0) / views
        comment_r = (v.get("comment_count", 0) or 0) / views
        rates.append((_clamp01(like_r / LIKE_RATE_NORM)
                      + _clamp01(comment_r / COMMENT_RATE_NORM)) / 2.0)
    return sum(rates) / len(rates) if rates else 0.0


def _niche(videos):
    """④ (1 - 경쟁 포화) × 수요 포화 — 영상 적고 조회 높은 주제가 틈새."""
    competition = _clamp01(len(videos) / NICHE_VIDEOS_NORM)
    mean_views = sum(v.get("view_count", 0) for v in videos) / len(videos)
    demand = _clamp01(mean_views / NICHE_DEMAND_VIEWS)
    return (1.0 - competition) * demand


def _share_summary(videos):
    """⑤ 공유율 — 채널 소유 시에만 수집되는 조건부 지표. 판정 제외, 관측치만 기록.
    truthiness 가드 — 레거시 행의 ""(빈 문자열)도 미수집으로 취급."""
    shares = [v for v in videos if v.get("share_count")]
    if not shares:
        return None
    rates = [v["share_count"] / v["view_count"] for v in shares
             if v.get("view_count")]
    return {"observed": len(shares), "mean_rate": round(sum(rates) / len(rates), 5)
            if rates else None}


def score_topics(videos, now=None):
    """youtube_raw 행 목록 → 주제별 스코어 리스트 (score 내림차순).
    반환: [{label, score, evidence}] — evidence는 지표 분해 + 표본 영상."""
    now = now or datetime.now(KST)
    clusters = {}
    for v in videos:
        for label in _topic_labels(v):
            clusters.setdefault(label, []).append(v)
    results = []
    for label, group in clusters.items():
        if len(group) < MIN_CLUSTER_VIDEOS:
            continue
        velocity = _velocity(group, now)
        small_channel, subs_known = _small_channel(group)
        reaction = _reaction(group)
        niche = _niche(group)
        score = round(
            WEIGHTS["velocity"] * velocity
            + WEIGHTS["small_channel"] * small_channel
            + WEIGHTS["reaction"] * reaction
            + WEIGHTS["niche"] * niche, 1)
        results.append({
            "label": label,
            "score": score,
            "evidence": {
                "videos": len(group),
                "channels": len({v.get("channel_id") for v in group}),
                "velocity": round(velocity, 3),
                "small_channel": round(small_channel, 3),
                "reaction": round(reaction, 3),
                "niche": round(niche, 3),
                "subscriber_known": subs_known,
                "share": _share_summary(group),   # ⑤ 조건부 — 참고 기록
                "sample_video_ids": [v.get("video_id") for v in group[:5]],
            },
        })
    results.sort(key=lambda r: (-r["score"], r["label"]))
    return results


def refresh_topics(d, now=None, top_k=TOP_K):
    """S-2 배치 진입점 — 최근 CORPUS_DAYS일 youtube_raw에서 주제 스코어 산출·저장.
    반환: 저장된 후보 목록. 수집 데이터가 없으면 빈 리스트 (조용한 no-op)."""
    now = now or datetime.now(KST)
    since = (now - timedelta(days=CORPUS_DAYS)).strftime("%Y-%m-%d")
    rows = d._qd(
        "SELECT * FROM youtube_raw WHERE fetched_at >= ? ORDER BY id DESC",
        (since,), fetch=True)
    if not rows:
        return []
    created_at = config_mod.now_kst_iso()
    saved = []
    for topic in score_topics(rows, now=now)[:top_k]:
        d.upsert_shorts_topic(
            topic["label"], topic["score"],
            json.dumps(topic["evidence"], ensure_ascii=False),
            "candidate", created_at)
        saved.append(topic)
    logger.info("S-2 주제 스코어 갱신: %d건 (후보 %d)",
                len(rows), len(saved))
    return saved


if __name__ == "__main__":
    import db
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    cfg = config_mod.load_config()
    conn = db.Database(cfg["db_url"])
    conn.init()
    for t in refresh_topics(conn):
        logger.info("  %.1f  %s", t["score"], t["label"])
    conn.close()
