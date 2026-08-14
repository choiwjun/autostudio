# v27: 테스트 격리 픽스처 — 사용자 Windows 환경변수에 GEMINI_API_KEY가 실제로
# 설정되어 있어(Windows venv pytest가 이를 상속), GEMINI 미설정 시나리오를 전제로
# 하는 기존 v26 테스트(나노바나나 미도입 시절)가 나노바나나 경로로 새는 것을 방지한다.
# 신규 v27 테스트는 테스트 본문에서 monkeypatch.setenv("GEMINI_API_KEY", ...)로
# 명시 설정 — autouse 픽스처가 먼저 삭제한 뒤 테스트 본문이 다시 설정하는 순서.
# (기존 테스트 파일 수정 금지 규칙에 따라 conftest에서 일괄 격리)
import pytest


@pytest.fixture(autouse=True)
def _clear_gemini_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
