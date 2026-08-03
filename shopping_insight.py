# shopping_insight.py
# v4: 네이버 쇼핑인사이트(검색 클릭 추이) — 쇼핑 검색 API 종료(2026-07-31) 대체 상업 신호.
# 수요지수(datalab.py)와 동일한 앵커 정규화 패턴: 요청당 앵커 1 + 후보 4 키워드,
# 후보 평균 ratio ÷ 앵커 평균 ratio = 쇼핑 클릭 지수.
# docs: developers.naver.com/docs/serviceapi/datalab/shopping/shopping.md
import requests

SHOPPING_INSIGHT_URL = "https://openapi.naver.com/v1/datalab/shopping/category/keywords"

from datalab import DatalabError  # noqa: E402  (오류 정규화 재사용 — graceful degradation)


def fetch_click_ratios(client_id, client_secret, keywords, anchor, category,
                       start_date, end_date, timeout=10):
    """쇼핑인사이트 키워드별 클릭 추이를 앵커로 정규화.
    반환: {keyword: 쇼핑 클릭 지수(앵커 평균 ratio 대비)} — 분야 미매칭(빈 응답) 키워드는 0.0.
    ratio는 요청 내 키워드별 상대값(자기 최대=100)이므로 앵커로 나눠야 요청 간 비교 가능.
    v4: 네트워크·타임아웃·JSON 오류도 전부 DatalabError로 정규화 (스펙 §4.4)."""
    groups = [{"name": anchor, "param": [anchor]}] + [
        {"name": kw, "param": [kw]} for kw in keywords[:4]
    ]
    try:
        resp = requests.post(
            SHOPPING_INSIGHT_URL,
            json={
                "startDate": start_date, "endDate": end_date,
                "timeUnit": "date", "category": category,
                "keyword": groups,
                "device": "", "gender": "", "ages": [],
            },
            headers={
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
        means[group.get("title", "")] = (sum(vals) / len(vals)) if vals else 0.0
    anchor_mean = means.get(anchor, 0.0)
    if anchor_mean <= 0:
        raise DatalabError(f"앵커 '{anchor}' 클릭 ratio가 0 — 앵커 교체 필요")
    return {kw: round(means.get(kw, 0.0) / anchor_mean, 4) for kw in keywords[:4]}
