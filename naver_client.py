# naver_client.py — 네이버 검색 API 클라이언트
# v15: 429/5xx·네트워크 오류 지수 백오프 재시도(3회) — 기존 1회성 호출은 429 한 번에
# 스냅샷 단계 전체가 오류로 밀리던 문제. 비정상 JSON 본문도 NaverAPIError로 정규화.
import time

import requests


class NaverAPIError(Exception):
    pass


BASE_URL = "https://openapi.naver.com/v1/search"
RETRY_STATUSES = (429, 500, 502, 503, 504)
RETRIES = 3


class NaverClient:
    def __init__(self, client_id, client_secret, timeout=10):
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout

    def _get(self, path, params):
        last_msg = ""
        for attempt in range(RETRIES):
            try:
                resp = requests.get(
                    f"{BASE_URL}/{path}",
                    params=params,
                    headers={
                        "X-Naver-Client-Id": self.client_id,
                        "X-Naver-Client-Secret": self.client_secret,
                    },
                    timeout=self.timeout,
                )
            except requests.RequestException as e:
                last_msg = f"network: {e}"
                if attempt < RETRIES - 1:
                    time.sleep(0.5 * (2 ** attempt))
                    continue
                raise NaverAPIError(last_msg) from e
            if resp.status_code in RETRY_STATUSES and attempt < RETRIES - 1:
                last_msg = f"HTTP {resp.status_code}"
                time.sleep(0.5 * (2 ** attempt))
                continue
            if resp.status_code != 200:
                try:
                    body = resp.json()
                    msg = body.get("errorMessage", resp.text)
                except ValueError:
                    msg = resp.text
                raise NaverAPIError(f"HTTP {resp.status_code}: {msg}")
            try:
                return resp.json()
            except ValueError as e:
                raise NaverAPIError(
                    f"bad json: {resp.text[:200]}") from e
        raise NaverAPIError(f"retry exhausted: {last_msg}")

    def search_blog(self, query, sort="sim", display=100, start=1):
        return self._get("blog.json", {
            "query": query, "sort": sort,
            "display": display, "start": start,
        })
