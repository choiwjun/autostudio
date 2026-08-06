import time

import requests

DATALAB_URL = "https://openapi.naver.com/v1/datalab/search"
RETRY_STATUSES = (429, 500, 502, 503, 504)
RETRIES = 3


class DatalabError(Exception):
    pass


def post_with_retry(url, payload, headers, timeout=10):
    """v15: 429/5xx·네트워크 오류는 지수 백오프로 재시도 — 기존 1회성 호출은
    429 한 번에 수요/쇼핑 단계 전체가 중단됐음. 반환: Response 또는 DatalabError."""
    last_msg = ""
    for attempt in range(RETRIES):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
        except requests.RequestException as e:
            last_msg = f"network: {e}"
            if attempt < RETRIES - 1:
                time.sleep(0.5 * (2 ** attempt))
                continue
            raise DatalabError(f"네트워크 오류: {e}") from e
        if resp.status_code in RETRY_STATUSES and attempt < RETRIES - 1:
            last_msg = f"HTTP {resp.status_code}"
            time.sleep(0.5 * (2 ** attempt))
            continue
        return resp
    raise DatalabError(f"재시도 소진: {last_msg}")


def fetch_demand_ratios(client_id, client_secret, keywords, anchor,
                        start_date, end_date, timeout=10):
    """앵커 + 후보(최대 4개)를 한 요청으로 비교.
    반환: {keyword: {"ratio": 수요지수, "growth": 기울기}}.
    ratio = 앵커 평균 ratio 대비 (요청 간 비교 가능하도록 정규화).
    growth = (최근 7일 평균 ratio - 이전 23일 평균 ratio) / 이전 23일 평균 —
    실제 "뜨는 키워드" 신호 (30일 시계열을 평균만 쓰고 버리지 않음).
    v3: 네트워크 오류·타임아웃·잘못된 JSON도 전부 DatalabError로 변환 —
    update_demand가 잡을 수 있는 예외 종류를 하나로 정규화 (graceful degradation, 스펙 §4.4).
    v9: 반환 구조가 {kw: float} → {kw: {"ratio":, "growth":}} 로 확장됨."""
    groups = [{"groupName": anchor, "keywords": [anchor]}] + [
        {"groupName": kw, "keywords": [kw]} for kw in keywords[:4]
    ]
    try:
        resp = post_with_retry(
            DATALAB_URL,
            {
                "startDate": start_date, "endDate": end_date,
                "timeUnit": "date", "keywordGroups": groups,
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
        raise DatalabError(f"datalab 요청 실패: {e}") from e
    # 데이터랙 응답은 오름차순(오래된→최근) 일별 ratio. 30일이면 최근 7일 vs 이전 23일
    series = {}
    for group in data.get("results", []):
        vals = [p.get("ratio", 0.0) for p in group.get("data", [])]
        series[group.get("title", "")] = vals
    anchor_series = series.get(anchor, [])
    anchor_mean = (sum(anchor_series) / len(anchor_series)) if anchor_series else 0.0
    if anchor_mean <= 0:
        raise DatalabError(f"앵커 '{anchor}' ratio가 0 — 앵커 교체 필요")

    def _ratio_growth(vals):
        if not vals:
            return {"ratio": 0.0, "growth": 0.0}
        mean = sum(vals) / len(vals)
        recent = vals[-7:]
        prev = vals[:-7]
        prev_mean = (sum(prev) / len(prev)) if prev else 0.0
        recent_mean = sum(recent) / len(recent)
        if prev_mean > 0:
            growth = (recent_mean - prev_mean) / prev_mean
        elif prev and recent_mean > 0:
            # v14: 콜드스타트 사각지대 수정 — 이전 기간(23일) 검색량이 0이다가 최근
            # 상승한 키워드(진짜 '뜨는 키워드')가 growth 0으로 묻히던 문제. 비율 계산이
            # 불가능하므로 최대 신호(1.0) 부여 — 소비 측(성장 정규화)에서 클램프됨.
            # 단, 시계열 자체가 8일 미만(prev 없음)이면 자료 부족 → 중립 0.
            growth = 1.0
        else:
            growth = 0.0
        return {"ratio": round(mean / anchor_mean, 4), "growth": round(growth, 4)}

    return {kw: _ratio_growth(series.get(kw, [])) for kw in keywords[:4]}
