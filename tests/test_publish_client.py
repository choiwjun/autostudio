# tests/test_publish_client.py — v22.3(2.x): 별도 블로그(autoblog) 발행 클라이언트
import json

import db
import publish_client
import pytest
import requests


def _open(tmp_path):
    d = db.Database(f"sqlite:///{tmp_path / 't.db'}")
    d.init()
    return d


def _cfg(tmp_path, enabled=True):
    return {"blog_api_url": "https://blog.example.com",
            "blog_token": "tok", "blog_publish_enabled": enabled,
            "db_url": f"sqlite:///{tmp_path / 't.db'}"}


def _draft(d, keyword_id):
    return d.insert_draft(keyword_id, "제목", "첫문단", "## 섹션\n본문",
                          tags=json.dumps(["태그1", "태그2"], ensure_ascii=False))


def _keyword(d):
    return d.upsert_keyword("보험 비교 방법", category="보험", day="2026-08-10")


# ---------- slug 규칙 ----------

def test_blog_slug_rules():
    assert publish_client.blog_slug("보험 비교 방법") == "k-" + __import__(
        "hashlib").sha1("보험 비교 방법".encode()).hexdigest()[:8]
    assert publish_client.blog_slug("fortune", fortune_ref_date="2026-08-10") \
        == "fortune-2026-08-10"
    kebab = publish_client.blog_slug("AI Tools Guide 2026")
    assert kebab.startswith("k-") and "-" in kebab and kebab.isascii()


# ---------- 발행 성공 → 게시 로그 ----------

def test_publish_draft_success(monkeypatch, tmp_path):
    posted = {}

    def fake_post(url, json, headers, timeout):
        posted["url"] = url
        posted["payload"] = json
        posted["headers"] = headers
        return _Resp(200, {"op": "created", "slug": json["slug"]})

    monkeypatch.setattr(publish_client.requests, "post", fake_post)
    d = _open(tmp_path)
    kid = _keyword(d)
    did = _draft(d, kid)
    draft = d.get_draft(did)
    url = publish_client.publish_draft(_cfg(tmp_path), d, draft, d.get_keyword(kid))
    assert url == "https://blog.example.com/k-" + __import__(
        "hashlib").sha1("보험 비교 방법".encode()).hexdigest()[:8]
    # 요청: 토큰 인증 + 마크다운 + 메타
    assert posted["headers"]["Authorization"] == "Bearer tok"
    p = posted["payload"]
    assert p["title"] == "제목" and "## 섹션" in p["body"]
    assert p["tags"] == ["태그1", "태그2"] and p["category"] == "보험"
    assert p["status"] == "published"
    # 게시 로그 갱신
    row = d.get_draft(did)
    assert row["published_url"] == url and row["status"] == "published"
    d.close()


# ---------- 재시도 (429 → 성공) ----------

class _Resp:
    def __init__(self, status, text):
        self.status_code = status
        self.text = text if isinstance(text, str) else json.dumps(text)
        self._json = text if isinstance(text, dict) else None

    def json(self):
        return self._json


def test_publish_retries_then_succeeds(monkeypatch, tmp_path):
    calls = []

    def flaky(url, json, headers, timeout):
        calls.append(1)
        if len(calls) == 1:
            return _Resp(429, "rate limited")
        return _Resp(200, {"op": "updated"})

    monkeypatch.setattr(publish_client.requests, "post", flaky)
    monkeypatch.setattr(publish_client.time, "sleep", lambda s: None)
    d = _open(tmp_path)
    kid = _keyword(d)
    did = _draft(d, kid)
    publish_client.publish_draft(_cfg(tmp_path), d, d.get_draft(did),
                                 d.get_keyword(kid))
    assert len(calls) == 2
    d.close()


def test_publish_retries_exhausted_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(publish_client.requests, "post",
                        lambda *a, **kw: _Resp(503, "boom"))
    monkeypatch.setattr(publish_client.time, "sleep", lambda s: None)
    d = _open(tmp_path)
    kid = _keyword(d)
    did = _draft(d, kid)
    with pytest.raises(publish_client.BlogPublishError):
        publish_client.publish_draft(_cfg(tmp_path), d, d.get_draft(did),
                                     d.get_keyword(kid))
    # 실패 시 게시 로그 미갱신
    assert d.get_draft(did)["published_url"] == ""
    d.close()


def test_publish_400_no_retry(monkeypatch, tmp_path):
    calls = []

    def bad(url, json, headers, timeout):
        calls.append(1)
        return _Resp(400, "slug must be")

    monkeypatch.setattr(publish_client.requests, "post", bad)
    d = _open(tmp_path)
    kid = _keyword(d)
    did = _draft(d, kid)
    with pytest.raises(publish_client.BlogPublishError):
        publish_client.publish_draft(_cfg(tmp_path), d, d.get_draft(did),
                                     d.get_keyword(kid))
    assert len(calls) == 1  # 재시도 안 함
    d.close()


def test_publish_requires_config(tmp_path):
    d = _open(tmp_path)
    kid = _keyword(d)
    did = _draft(d, kid)
    with pytest.raises(publish_client.BlogPublishError):
        publish_client.publish_draft({}, d, d.get_draft(did))
    d.close()


# ---------- db: 미발행 초안 조회 ----------

def test_list_drafts_unpublished(tmp_path):
    d = _open(tmp_path)
    kid = _keyword(d)
    a = _draft(d, kid)
    b = _draft(d, kid)
    assert {x["id"] for x in d.list_drafts_unpublished(10)} == {a, b}
    d.set_draft_published_url(a, "https://blog.example.com/x")
    assert [x["id"] for x in d.list_drafts_unpublished(10)] == [b]
    d.close()


# ---------- v28: BlogPublishError.status_code (401/429 힌트 판별용) ----------

def test_blog_publish_error_carries_status_code(monkeypatch, tmp_path):
    # OQ-2: status_code 속성 — 401 즉시 실패 / 429·5xx 재시도 후 최종 실패 /
    # 네트워크 None. 메시지 포맷 "HTTP {status}: ..."은 기존과 불변.
    monkeypatch.setattr(publish_client.time, "sleep", lambda s: None)

    def publish_with(resp_factory):
        d = _open(tmp_path)
        kid = _keyword(d)
        did = _draft(d, kid)
        monkeypatch.setattr(publish_client.requests, "post", resp_factory)
        with pytest.raises(publish_client.BlogPublishError) as ei:
            publish_client.publish_draft(_cfg(tmp_path), d, d.get_draft(did),
                                         d.get_keyword(kid))
        return ei.value

    e401 = publish_with(lambda *a, **kw: _Resp(401, "bad token"))
    assert e401.status_code == 401
    assert str(e401).startswith("HTTP 401:")
    e429 = publish_with(lambda *a, **kw: _Resp(429, "quota"))
    assert e429.status_code == 429
    assert str(e429).startswith("HTTP 429:")
    e503 = publish_with(lambda *a, **kw: _Resp(503, "boom"))
    assert e503.status_code == 503
    assert str(e503).startswith("HTTP 503:")

    def net_error(url, json, headers, timeout):
        raise requests.RequestException("boom")

    d = _open(tmp_path)
    kid = _keyword(d)
    did = _draft(d, kid)
    monkeypatch.setattr(publish_client.requests, "post", net_error)
    with pytest.raises(publish_client.BlogPublishError) as ei:
        publish_client.publish_draft(_cfg(tmp_path), d, d.get_draft(did),
                                     d.get_keyword(kid))
    assert ei.value.status_code is None
    assert str(ei.value).startswith("network error:")
