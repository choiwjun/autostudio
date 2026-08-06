# shopping_insight.py
# v4: 네이버 쇼핑인사이트(검색 클릭 추이) — 쇼핑 검색 API 종료(2026-07-31) 대체 상업 신호.
# 수요지수(datalab.py)와 동일한 앵커 정규화 패턴: 요청당 앵커 1 + 후보 4 키워드,
# 후보 평균 ratio ÷ 앵커 평균 ratio = 쇼핑 클릭 지수.
# docs: developers.naver.com/docs/serviceapi/datalab/shopping/shopping.md
import requests

SHOPPING_INSIGHT_URL = "https://openapi.naver.com/v1/datalab/shopping/category/keywords"

# 오류 정규화 + 재시도 재사용 — graceful degradation (수요 단계와 동일 복원력)
from datalab import DatalabError, post_with_retry  # noqa: E402


def fetch_click_ratios(client_id, client_secret, keywords, anchor, category,
                       start_date, end_date, timeout=10):
    """쇼핑인사이트 키워드별 클릭 추이를 앵커로 정규화.
    반환: {keyword: 쇼핑 클릭 지수(앵커 평균 ratio 대비) 또는 None}.
    v17: 분야 미매칭(빈 시계열)은 None — 기존 0.0은 '진짜 저클릭'과 구별 불가해
    은퇴·우선순위 판정을 왜곡했다. None은 호출 측에서 NULL 유지로 이어지고,
    은퇴 판정은 기회점수 단독 경로로 처리 (db.find_retire_candidates v17).
    ratio는 요청 내 키워드별 상대값(자기 최대=100)이므로 앵커로 나눠야 요청 간 비교 가능.
    v4: 네트워크·타임아웃·JSON 오류도 전부 DatalabError로 정규화 (스펙 §4.4)."""
    groups = [{"name": anchor, "param": [anchor]}] + [
        {"name": kw, "param": [kw]} for kw in keywords[:4]
    ]
    try:
        resp = post_with_retry(
            SHOPPING_INSIGHT_URL,
            {
                "startDate": start_date, "endDate": end_date,
                "timeUnit": "date", "category": category,
                "keyword": groups,
                "device": "", "gender": "", "ages": [],
            },
            {
                "X-Naver-Client-Id": client_id,
                "X-Naver-Client-Secret": client_secret,
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )
        if resp.status_code != 200:
            raise DatalabError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
    except DatalabError:
        raise
    except Exception as e:
        raise DatalabError(f"쇼핑인사이트 요청 실패: {e}") from e
    means = {}
    for group in data.get("results", []):
        vals = [p.get("ratio", 0.0) for p in group.get("data", [])]
        if vals:  # 빈 시계열 = 분야 미매칭 — 0.0으로 집계하지 않음 (v17)
            means[group.get("title", "")] = sum(vals) / len(vals)
    anchor_mean = means.get(anchor, 0.0)
    if anchor_mean <= 0:
        raise DatalabError(f"앵커 '{anchor}' 클릭 ratio가 0 — 앵커 교체 필요")
    return {kw: (round(means[kw] / anchor_mean, 4) if kw in means else None)
            for kw in keywords[:4]}
