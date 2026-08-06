# autocomplete.py
import time

import requests


class AutocompleteError(Exception):
    pass


def _first_string(node):
    if isinstance(node, str):
        return node.strip()
    if isinstance(node, list):
        for child in node:
            s = _first_string(child)
            if s:
                return s
    return ""


def parse_suggestions(payload):
    """비공식 엔드포인트의 구(list)/신(dict items) 포맷을 모두 수용하는 방어적 파싱.
    형태가 다르면 빈 리스트 — 크롤 자체는 계속되고 실측 스모크에서 잡는다."""
    if isinstance(payload, dict):
        items = payload.get("items", [])
    elif isinstance(payload, list) and len(payload) > 1:
        items = payload[1]
    else:
        return []
    if not isinstance(items, list):
        return []
    # {"items": [[[...], [...]]]} 처럼 리스트 묶음이 한 겹 더 있는 형태 언랩
    if len(items) == 1 and isinstance(items[0], list) and items[0] \
            and isinstance(items[0][0], list):
        items = items[0]
    out = []
    for it in items:
        s = _first_string(it)
        if s:
            out.append(s)
    return out


def fetch_suggestions(query, url, timeout=10, retries=3):
    last_err = None
    for attempt in range(retries):
        try:
            resp = requests.get(
                url,
                params={"q": query, "q_enc": "utf-8", "st": "100"},
                headers={"Referer": "https://www.naver.com/"},
                timeout=timeout,
            )
            if resp.status_code != 200:
                raise AutocompleteError(f"HTTP {resp.status_code}")
            return parse_suggestions(resp.json())
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(0.5 * (2 ** attempt))  # 지수 백오프 0.5 → 1.0
    raise AutocompleteError(str(last_err))


def expand_keywords(seeds, url, known=frozenset(), max_new=100, max_depth=2,
                    max_requests=300, delay=0.3, max_consecutive_failures=5,
                    budget_seconds=None, exclude=None):
    """BFS 확장. known(DB 기존 키워드)은 신규 상한에 계수하지 않되 경유지로 사용.
    반환: (신규 키워드, origins {키워드: 유래 키워드}, 중단 사유 None|'blocked'|'budget')
    v3: budget_seconds(수동 실행 잔여 예산) — 요청 전에 검사하고 잔여 예산 기반으로
    호출 타임아웃을 축소한다. 예산 소진은 'budget', 차단은 'blocked'로 구분 (스펙 §4.9).
    origins는 시드 분야 전파(1차 키워드 → 시드 category)의 전제.
    v14: exclude(판별 함수)가 True인 제안어는 신규 수집은 물론 다음 depth 경유지에서도
    제외 — 정제에서 버려질 노이즈(블랙리스트·브랜드 등)가 하위 제안어를 증폭시키던
    문제를 확장 단계에서 차단 (요청 낭비 + 노이즈 팬아웃 감소)."""
    known = set(known) | set(seeds)
    new_found, origins = [], {}
    visited = set(seeds)
    queue = list(seeds)
    requests_made = 0
    successes = 0
    consecutive_failures = 0
    stopped = None
    started = time.monotonic() if budget_seconds is not None else None
    for _ in range(max_depth):
        if stopped or not queue:
            break
        next_queue = []
        for kw in queue:
            if len(new_found) >= max_new or requests_made >= max_requests:
                break
            if budget_seconds is not None and time.monotonic() - started >= budget_seconds:
                stopped = "budget"
                break
            requests_made += 1
            timeout = 10
            if budget_seconds is not None:
                # 잔여 예산을 3회 재시도 최악에 나눠 호출 타임아웃 축소 (전 구간 예산 적용)
                remaining = budget_seconds - (time.monotonic() - started)
                timeout = max(1.0, min(10.0, remaining / 3))
            try:
                suggestions = fetch_suggestions(kw, url, timeout=timeout)
                successes += 1
                consecutive_failures = 0
            except AutocompleteError:
                consecutive_failures += 1
                if consecutive_failures >= max_consecutive_failures:
                    stopped = "blocked"
                    break
                continue
            finally:
                time.sleep(delay)
            for sug in suggestions:
                if sug in visited:
                    continue
                visited.add(sug)
                if exclude is not None and exclude(sug):
                    continue  # v14: 정제 대상 노이즈는 경유지·수집 모두 제외
                origins[sug] = kw
                next_queue.append(sug)
                if sug not in known and len(new_found) < max_new:
                    new_found.append(sug)
        queue = next_queue
    # v15: 중단 사유 보존 — 예산 소진('budget')으로 멈춘 실행이 성공 0건이라는 이유로
    # 'blocked'로 덮어써 차단으로 오보고되던 문제 (차단은 성공 0회 AND 예산 중단 아님)
    if stopped is None and requests_made > 0 and successes == 0:
        stopped = "blocked"  # 전면 실패도 차단으로 간주 (성공 0회)
    return new_found, origins, stopped
