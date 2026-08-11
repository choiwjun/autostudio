# tests/test_draft_generator.py
import pytest

from draft_generator import DraftGenerationError, parse_draft

# v15: v8 단일패스 generate_draft는 프로덕션 미사용 사어 코드라 제거됨 —
# 초안 생성 진입점은 draft_pipeline.generate_two_pass 유일.


def test_parse_draft_json():
    d = parse_draft('{"title": "t", "first_paragraph": "p", "body": "b"}')
    assert d == {"title": "t", "first_paragraph": "p", "body": "b", "tags": [],
                 "thumbnail_ideas": []}


def test_parse_draft_thumbnail_ideas():
    # v19: 썸네일 아이디어 — 2개 상한, 빈 값 제거
    d = parse_draft('{"title": "t", "first_paragraph": "p", "body": "b", '
                    '"thumbnail_ideas": ["아이디어1", "아이디어2", "아이디어3", ""]}')
    assert d["thumbnail_ideas"] == ["아이디어1", "아이디어2"]


def test_parse_draft_strips_codeblock():
    raw = '```json\n{"title": "t", "first_paragraph": "p", "body": "b"}\n```'
    assert parse_draft(raw)["title"] == "t"


def test_parse_draft_strips_uppercase_codeblock():
    # v15: 공용 펜스 제거 — 대문자 ```JSON도 처리 (기존 소문자 전용 매칭 누락)
    raw = '```JSON\n{"title": "t", "first_paragraph": "p", "body": "b"}\n```'
    assert parse_draft(raw)["title"] == "t"
    raw2 = '```\n{"title": "t2", "first_paragraph": "p", "body": "b"}\n```'
    assert parse_draft(raw2)["title"] == "t2"


def test_parse_draft_missing_field():
    with pytest.raises(DraftGenerationError):
        parse_draft('{"title": "t"}')


def test_parse_draft_not_json():
    with pytest.raises(DraftGenerationError):
        parse_draft("그냥 텍스트")


def test_faq_appended_when_missing():
    # v8: AEO — 모델이 FAQ를 놓치면 골격 질문으로 보정
    from draft_generator import _append_faq_if_missing
    draft = {"title": "t", "first_paragraph": "p", "body": "## 본문\n내용"}
    out = _append_faq_if_missing(draft, {"questions": ["어떤 게 좋을까?", "가격은?"]})
    assert "자주 묻는 질문" in out["body"]
    assert "어떤 게 좋을까" in out["body"]


def test_faq_not_duplicated_when_present():
    from draft_generator import _append_faq_if_missing
    draft = {"title": "t", "first_paragraph": "p", "body": "## 자주 묻는 질문\n이미 있음"}
    out = _append_faq_if_missing(draft, {"questions": ["어떤 걸?"]})
    assert out["body"].count("자주 묻는 질문") == 1


def test_faq_skipped_without_questions():
    from draft_generator import _append_faq_if_missing
    draft = {"title": "t", "first_paragraph": "p", "body": "본문"}
    out = _append_faq_if_missing(draft, {"questions": []})
    assert out["body"] == "본문"


# ---------- v17.2: 태그 정규화 ----------

def test_parse_draft_normalizes_tags():
    # # 제거·공백 정리·중복 제거·순서 유지
    raw = ('{"title": "t", "first_paragraph": "p", "body": "b", '
           '"tags": ["#여름휴가", " 여름 휴가 추천 ", "여름휴가", "", "부산 여행"]}')
    assert parse_draft(raw)["tags"] == ["여름휴가", "여름 휴가 추천", "부산 여행"]


def test_parse_draft_tags_missing_or_malformed():
    assert parse_draft('{"title": "t", "first_paragraph": "p", "body": "b"}')["tags"] == []
    # 리스트가 아니면 빈 리스트로 정규화 (모델이 문자열로 돌려주는 경우 대비)
    raw = ('{"title": "t", "first_paragraph": "p", "body": "b", '
           '"tags": "여름휴가"}')
    assert parse_draft(raw)["tags"] == []


def test_parse_draft_tags_capped():
    from draft_generator import TAGS_MAX_COUNT
    tags = [f"태그{i}" for i in range(15)]
    import json as json_mod
    raw = json_mod.dumps({"title": "t", "first_paragraph": "p",
                          "body": "b", "tags": tags}, ensure_ascii=False)
    assert len(parse_draft(raw)["tags"]) == TAGS_MAX_COUNT


# ---------- v23: 초안 LLM 프로바이더 (OpenCode Go 우선, Bailian 폴백) ----------

import llm_client


def test_draft_provider_prefers_opencode_go(monkeypatch):
    monkeypatch.setenv("OPENCODE_GO_API_KEY", "og-key")
    monkeypatch.delenv("OPENCODE_GO_BASE_URL", raising=False)
    provider, base_url, model = llm_client.resolve_draft_provider()
    assert provider == "opencode-go"
    assert base_url == "https://opencode.ai/zen/go/v1"
    assert model == "deepseek-v4-flash"
    assert llm_client.resolve_draft_api_key() == "og-key"


def test_draft_provider_bailian_fallback(monkeypatch):
    monkeypatch.delenv("OPENCODE_GO_API_KEY", raising=False)
    monkeypatch.setenv("BAILIAN_TOKEN_PLAN_API_KEY", "b-key")
    provider, base_url, model = llm_client.resolve_draft_provider()
    assert provider == "bailian"
    assert base_url == "https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"
    assert model == "deepseek-v4-flash-0731"


def test_draft_provider_custom_base_url_scoped_per_provider(monkeypatch):
    # OpenCode Go 키가 있으면 OpenCode 커스텀 base만 적용, Bailian 커스텀은 무시
    monkeypatch.setenv("OPENCODE_GO_API_KEY", "og-key")
    monkeypatch.setenv("OPENCODE_GO_BASE_URL", "https://og.example/v1")
    monkeypatch.setenv("BAILIAN_TOKEN_PLAN_BASE_URL", "https://bailian-custom/v1")
    provider, base_url, _ = llm_client.resolve_draft_provider()
    assert (provider, base_url) == ("opencode-go", "https://og.example/v1")
    # Bailian 폴백 시에는 Bailian 커스텀 base 사용
    monkeypatch.delenv("OPENCODE_GO_API_KEY", raising=False)
    provider, base_url, _ = llm_client.resolve_draft_provider()
    assert (provider, base_url) == ("bailian", "https://bailian-custom/v1")


def test_draft_provider_falls_back_to_dashscope(monkeypatch):
    monkeypatch.delenv("OPENCODE_GO_API_KEY", raising=False)
    monkeypatch.delenv("BAILIAN_TOKEN_PLAN_API_KEY", raising=False)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "ds-key")
    assert llm_client.resolve_draft_api_key() == "ds-key"


def test_run_llm_opencode_go_payload(monkeypatch):
    # OpenCode Go — zen/go 엔드포인트 + deepseek-v4-flash + thinking 비활성
    import draft_generator
    captured = {}

    def fake_post(url, payload, api_key, timeout, error_cls, err_prefix):
        captured.update(url=url, payload=payload, api_key=api_key,
                        timeout=timeout, error_cls=error_cls)
        return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setenv("OPENCODE_GO_API_KEY", "og-key")
    monkeypatch.setattr(llm_client, "post_json", fake_post)
    assert draft_generator._run_llm("프롬프트") == "ok"
    assert captured["url"] == "https://opencode.ai/zen/go/v1/chat/completions"
    assert captured["payload"]["model"] == "deepseek-v4-flash"
    assert captured["payload"]["thinking"] == {"type": "disabled"}
    assert "enable_thinking" not in captured["payload"]
    assert captured["api_key"] == "og-key"
    assert captured["error_cls"] is DraftGenerationError


def test_run_llm_bailian_fallback_payload(monkeypatch):
    # Bailian 폴백 — 기존 Token Plan 동작 유지
    import draft_generator
    captured = {}

    def fake_post(url, payload, api_key, timeout, error_cls, err_prefix):
        captured.update(url=url, payload=payload, api_key=api_key)
        return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.delenv("OPENCODE_GO_API_KEY", raising=False)
    monkeypatch.setenv("BAILIAN_TOKEN_PLAN_API_KEY", "b-key")
    monkeypatch.setattr(llm_client, "post_json", fake_post)
    assert draft_generator._run_llm("프롬프트") == "ok"
    assert captured["url"].endswith("/chat/completions")
    assert captured["payload"]["model"] == "deepseek-v4-flash-0731"
    assert captured["payload"]["enable_thinking"] is False
    assert "thinking" not in captured["payload"]
    assert captured["api_key"] == "b-key"


def test_run_llm_no_key_raises(monkeypatch):
    import draft_generator
    monkeypatch.delenv("OPENCODE_GO_API_KEY", raising=False)
    monkeypatch.delenv("BAILIAN_TOKEN_PLAN_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    with pytest.raises(DraftGenerationError):
        draft_generator._run_llm("프롬프트")
