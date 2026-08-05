import requests

DATALAB_URL = "https://openapi.naver.com/v1/datalab/search"


class DatalabError(Exception):
    pass


def fetch_demand_ratios(client_id, client_secret, keywords, anchor,
                        start_date, end_date, timeout=10):
    """앵커 + 후보(최대 4개)를 한 요청으로 비교.
    반환: {keyword: 수요지수(앵커 평균 ratio 대비)}.
    데이터랩 ratio는 요청 내 상대값이므로 앵커로 나눠야 요청 간 비교 가능.
    v3: 네트워크 오류·타임아웃·잘못된 JSON도 전부 DatalabError로 변환 —
    update_demand가 잡을 수 있는 예외 종류를 하나로 정규화 (graceful degradation, 스펙 §4.4)."""
    groups = [{"groupName": anchor, "keywords": [anchor]}] + [
        {"groupName": kw, "keywords": [kw]} for kw in keywords[:4]
    ]
    try:
        resp = requests.post(
            DATALAB_URL,
            json={
                "startDate": start_date, "endDate": end_date,
                "timeUnit": "date", "keywordGroups": groups,
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
        raise DatalabError(f"datalab 요청 실패: {e}") from e
    means = {}
    for group in data.get("results", []):
        vals = [p.get("ratio", 0.0) for p in group.get("data", [])]
        means[group.get("title", "")] = (sum(vals) / len(vals)) if vals else 0.0
    anchor_mean = means.get(anchor, 0.0)
    if anchor_mean <= 0:
        raise DatalabError(f"앵커 '{anchor}' ratio가 0 — 앵커 교체 필요")
    return {kw: round(means.get(kw, 0.0) / anchor_mean, 4) for kw in keywords[:4]}
