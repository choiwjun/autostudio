# scripts/replace_seeds.py
"""프로덕션 시드 교체 — v6: 기존 22개 트렌드 시드 삭제 + 집중 시드 추가.

사용: DASHBOARD_TOKEN=<토큰> BASE_URL=<vercel-url> python scripts/replace_seeds.py
  BASE_URL 예: https://autostudio-eight.vercel.app

주의: 프로덕션 쓰기 API이므로 실행 전 대시보드 상태 확인 필수.
"""
import os
import sys

import requests

BASE = os.getenv("BASE_URL", "https://autostudio-eight.vercel.app").rstrip("/")
TOKEN = os.getenv("DASHBOARD_TOKEN", "")
if not TOKEN:
    sys.exit("DASHBOARD_TOKEN 환경변수 필요 (fail-closed: 프로덕션은 토큰 필수)")

HEADERS = {"Authorization": f"Bearer {TOKEN}"}

# v6: 집중 발굴 시드 — config.py DEFAULT_FOCUS_SEEDS와 동일
# v8: 카테고리 확장 — config.py와 동기화 (11개 카테고리)
FOCUS_SEEDS = [
    ("보험 비교 방법", "보험"),
    ("실비보험 추천", "보험"),
    ("암보험 가입 전 확인", "보험"),
    ("재테크 방법", "금융"),
    ("연말정산 환급 방법", "금융"),
    ("주식 초보 시작 방법", "재테크"),
    ("ISA 계좌 개설 조건", "재테크"),
    ("청약 당첨 후 절차", "부동산"),
    ("전세 계약 시 확인 사항", "부동산"),
    ("상속세 신고 방법", "법률"),
    ("양도소득세 계산 방법", "법률"),
    ("건강 관리 방법", "건강"),
    ("다이어트 식단 추천", "건강"),
    ("건강검진 항목 추천", "의료"),
    ("실손의료보험 청구 방법", "의료"),
    ("노트북 추천 비교", "IT"),
    ("AI 활용 방법", "IT"),
    ("생성형 AI 도구 추천", "디지털"),
    ("홈페이지 제작 방법", "디지털"),
    ("자격증 준비 방법", "교육"),
    ("공부법 추천", "교육"),
    ("정보처리기사 준비 기간", "자격증"),
    ("요양보호사 자격증 조건", "자격증"),
]


def main():
    r = requests.get(f"{BASE}/seeds", timeout=15)
    r.raise_for_status()
    seeds = r.json()
    print(f"기존 시드 {len(seeds)}개 발견")
    for s in seeds:
        resp = requests.delete(f"{BASE}/seeds/{s['id']}", headers=HEADERS, timeout=15)
        resp.raise_for_status()
        print(f"  삭제: {s['keyword']}")
    for kw, cat in FOCUS_SEEDS:
        resp = requests.post(f"{BASE}/seeds", headers=HEADERS,
                             json={"keyword": kw, "category": cat}, timeout=15)
        resp.raise_for_status()
        print(f"  추가: [{cat}] {kw}")
    r = requests.get(f"{BASE}/seeds", timeout=15)
    r.raise_for_status()
    print(f"완료: 시드 {len(r.json())}개 (집중 카테고리 {len(FOCUS_SEEDS)}개)")


if __name__ == "__main__":
    main()
