# tests/visual_check_v6.py
"""v6 대시보드 시각 검증 — 서버 기동 상태에서 Playwright로 렌더링 확인.
실행: .venv\Scripts\python tests/visual_check_v6.py
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8300"


def main():
    shots = Path(__file__).parent.parent / "docs" / "v6-screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1280, "height": 900})
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        page.goto(BASE, wait_until="networkidle")
        page.wait_for_selector("table", timeout=15000)
        page.wait_for_timeout(1500)
        page.screenshot(path=str(shots / "01-main.png"), full_page=True)
        print("[1] 메인 화면 캡처 완료")

        # KPI 카드 존재 확인
        for kpi in ["kpiKeywords", "kpiSeeds", "kpiLast", "kpiTop"]:
            el = page.locator(f"#{kpi}")
            print(f"  KPI {kpi}: '{el.inner_text()}'")

        # 프리셋 세그먼트 존재 확인
        seg_count = page.locator(".seg button").count()
        print(f"  프리셋 세그먼트 버튼: {seg_count}개")
        assert seg_count == 3, "프리셋 세그먼트 3개 필요"

        # 행이 있으면 상세 모달 열기 (데이터 있을 때)
        row_count = page.locator("tbody tr:not(.skel)").count()
        print(f"  테이블 행: {row_count}개")
        if row_count > 0:
            first_kw = page.locator("tbody tr .td-kw").first.inner_text()
            print(f"  첫 키워드: {first_kw}")
            page.locator("tbody tr").first.click()
            page.wait_for_selector("#detail[style*='flex']", timeout=8000)
            page.wait_for_timeout(1200)
            page.screenshot(path=str(shots / "02-detail.png"))
            print("[2] 상세 모달 캡처 완료")
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)

        # AI픽 프리셋 토글 확인 (전체 버튼 클릭 → 프리셋 해제)
        page.locator("#presetAll").click()
        page.wait_for_timeout(800)
        page.screenshot(path=str(shots / "03-all.png"), full_page=True)
        print("[3] 전체 보기 캡처 완료")

        # 모바일 뷰포트 반응형 확인
        page.set_viewport_size({"width": 390, "height": 844})
        page.reload(wait_until="networkidle")
        page.wait_for_selector("table", timeout=15000)
        page.wait_for_timeout(1200)
        page.screenshot(path=str(shots / "04-mobile.png"), full_page=True)
        print("[4] 모바일 뷰포트 캡처 완료")

        b.close()
        print("\n콘솔 에러:", errors if errors else "없음")
        if errors:
            sys.exit(1)
        print("v6 시각 검증 통과")


if __name__ == "__main__":
    main()
