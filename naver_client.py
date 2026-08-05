# naver_client.py
import requests


class NaverAPIError(Exception):
    pass


BASE_URL = "https://openapi.naver.com/v1/search"


class NaverClient:
    def __init__(self, client_id, client_secret, timeout=10):
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout

    def _get(self, path, params):
        resp = requests.get(
            f"{BASE_URL}/{path}",
            params=params,
            headers={
                "X-Naver-Client-Id": self.client_id,
                "X-Naver-Client-Secret": self.client_secret,
            },
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            try:
                body = resp.json()
                msg = body.get("errorMessage", resp.text)
            except ValueError:
                msg = resp.text
            raise NaverAPIError(f"HTTP {resp.status_code}: {msg}")
        return resp.json()

    def search_blog(self, query, sort="sim", display=100, start=1):
        return self._get("blog.json", {
            "query": query, "sort": sort,
            "display": display, "start": start,
        })

    def search_shop(self, query, display=10, start=1):
        return self._get("shop.json", {
            "query": query, "display": display, "start": start,
        })
