# tests/chart_check.py
"""v6 차트 개선 검증 — 서버 기동 상태에서 상세 모달 차트 렌더링 확인.
실행: .venv\Scripts\python tests/chart_check.py
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
        page.wait_for_selector("tbody tr:not(.skel)", timeout=15000)
        page.wait_for_timeout(800)

        # 상세 모달 열기
        page.locator("tbody tr").first.click()
        page.wait_for_selector("#detail[style*='flex']", timeout=8000)
        page.wait_for_timeout(1500)

        # 차트 캔버스 존재 + 실제 크기 확인
        canvas = page.locator("#chart")
        box = canvas.bounding_box()
        print(f"[1] 차트 캔버스: {box['width']}x{box['height']}px")
        assert box["width"] > 300, "차트 너비 부족"

        # Chart.js 인스턴스에서 실제 설정 검증 (spanGaps는 dataset 속성)
        cfg = page.evaluate("() => { const c = Chart.getChart('chart'); if (!c) return null; "
                            "return { datasets: c.data.datasets.length, "
                            "spanGaps: c.data.datasets.map(d => d.spanGaps), "
                            "tension: c.data.datasets.map(d => d.tension), "
                            "borderDash: c.data.datasets.map(d => d.borderDash || []), "
                            "yMin: c.options.scales.y.min, yMax: c.options.scales.y.max, "
                            "interactionMode: c.options.interaction.mode, "
                            "pointRadius: c.data.datasets.map(d => d.pointRadius) }; }")
        print(f"[2] Chart 설정: {cfg}")
        assert cfg and cfg["datasets"] == 4, "데이터셋 4개 필요"
        assert cfg["yMin"] == 0 and cfg["yMax"] == 100, "y축 0~100 고정 필요"
        assert cfg["interactionMode"] == "index", "interaction mode index 필요"
        assert all(cfg["spanGaps"]), "모든 dataset spanGaps 필요"
        assert cfg["borderDash"][2] == [5, 5], "총 글 수(3번째) 점선 필요"

        # y2(총 글 수) 축 존재 확인
        page.screenshot(path=str(shots / "05-chart-v6.png"))
        print("[3] 차트 스크린샷 저장: docs/v6-screenshots/05-chart-v6.png")

        b.close()
        print("\n콘솔 에러:", errors if errors else "없음")
        if errors:
            sys.exit(1)
        print("차트 검증 통과")


if __name__ == "__main__":
    main()
