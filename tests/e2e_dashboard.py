# tests/e2e_dashboard.py
# 실행: .venv\Scripts\pip install playwright && .venv\Scripts\playwright install chromium
#       (서버 기동 후) .venv\Scripts\python tests/e2e_dashboard.py
import sys

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8000"


def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page()
        page.goto(BASE)
        page.wait_for_selector("table")
        # v6: KPI 카드 + 프리셋 세그먼트 렌더링 확인
        page.wait_for_selector(".kpi, .empty, .gauge", timeout=10_000)
        assert page.locator(".kpi").count() == 4
        assert page.locator(".seg button").count() == 3
        # 빈 상태(전체 0건)면 CTA 버튼 2개 확인 — 온보딩 카피와 함께
        if page.locator("text=아직 데이터가 없습니다").count():
            assert page.locator("button:has-text('시드 추가')").count() == 1
            assert page.locator("button:has-text('지금 수집 실행')").count() == 1
        # v6: Priority가 기본 활성(descending) — 첫 클릭 → 오름차순, 재클릭 → 내림차순 (UX §6)
        th = page.locator("th.sortable", has_text="Priority")
        assert page.locator("th[aria-sort='descending']").count() == 1
        th.click()
        page.wait_for_timeout(200)
        assert page.locator("th[aria-sort='ascending']").count() == 1
        th.click()
        page.wait_for_timeout(200)
        assert page.locator("th[aria-sort='descending']").count() == 1
        # v7: 글 생성 버튼 + 모달 마크업 존재 확인 (데이터 없으면 버튼 미노출 — 셀렉터 존재만 검증)
        assert page.locator("th:has-text('글')").count() == 1
        b.close()


if __name__ == "__main__":
    sys.exit(main())
