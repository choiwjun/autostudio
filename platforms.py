# platforms.py — v19: 플랫폼별 블로그 콘텐츠 규칙 (단일 소스)
# 네이버(플레인 텍스트) / 티스토리(구글 SEO) / 애드센스(수익 최적화) / 브랜드(신뢰 구축).
# 프롬프트·검수·태그·내보내기·이미지가 모두 이 모듈의 규칙을 참조한다.
# (외부 블로그 작성 프롬프트 설계서의 플랫폼별 포맷 규칙을 파이프라인 구조에 병합)

PLATFORMS = ("naver", "tistory", "adsense", "brand")
DEFAULT_PLATFORM = "naver"
PLATFORM_LABELS = {
    "naver": "네이버 블로그",
    "tistory": "티스토리",
    "adsense": "애드센스",
    "brand": "브랜드 블로그",
}
# 내보내기 파일명 접두어
PLATFORM_FILENAME = {
    "naver": "blog-naver", "tistory": "blog-tistory",
    "adsense": "blog-adsense", "brand": "blog-brand",
}

# 태그 구분 — 네이버/애드센스/브랜드는 #+공백, 티스토리는 쉼표(# 없음)
_TAG_STYLE_HASH = ("naver", "adsense", "brand")


def format_tags(tags, platform):
    """초안의 태그 리스트 → 플랫폼별 표기 문자열."""
    tags = [t for t in (tags or []) if str(t).strip()]
    if not tags:
        return ""
    if platform in _TAG_STYLE_HASH:
        return "#" + " #".join(tags)
    return ", ".join(tags)


# ---------- 검수 규칙 ----------

# 마크다운 블로그(티스토리/애드센스/브랜드) 전용: 표(테이블) 요구
TABLE_REQUIRED_PLATFORMS = ("tistory", "adsense", "brand")


def table_required(platform):
    return platform in TABLE_REQUIRED_PLATFORMS


# 네이버 전용: 플레인 텍스트 — 마크다운 기호 사용 시 검수 실패
NAVER_BANNED_MARKDOWN = (
    ("##", "H2 마크다운"), ("#", "# 제목 기호"), ("**", "굵게 기호"),
    ("|", "표 기호"), ("```", "코드블록"),
)
NAVER_BANNED_LINE_STARTS = ("- ", "* ", "---")


def naver_markdown_violations(text):
    """네이버 플레인 텍스트 위반 감지 — (기호, 설명) 리스트. 없으면 빈 리스트."""
    violations = []
    for line in (text or "").splitlines():
        for marker in NAVER_BANNED_LINE_STARTS:
            if line.strip().startswith(marker):
                violations.append((marker, f"줄 시작 마크다운 {marker.strip()}"))
                break
    for symbol, label in NAVER_BANNED_MARKDOWN:
        if symbol in (text or ""):
            violations.append((symbol, label))
    return violations


# ---------- 프롬프트 규칙 (pass1 골격 / pass2 확장) ----------

PASS1_RULES = {
    "naver": (
        "- 소제목은 플레인 텍스트 한 줄로 설계한다 (마크다운 기호 없음).\n"
        "- 친근한 대화체, 공감 유도. 네이버 검색 30~50대 정보 검색 독자 대상.\n"),
    "tistory": (
        "- 소제목에 번호를 붙인다 (## 1. 소제목 형식, 하위 소제목 ### 1-1.).\n"
        "- 전문적·분석적 어조, 구글 검색(Featured Snippet) 최적화 구조.\n"),
    "adsense": (
        "- 소제목에 번호를 붙인다 (## 1. 소제목 형식, 하위 소제목 ### 1-1.).\n"
        "- 실용적·문제 해결 중심 어조, 광고 친화적 충분한 길이.\n"),
    "brand": (
        "- 소제목에 번호를 붙인다 (## 1. 소제목 형식, 하위 소제목 ### 1-1.).\n"
        "- 전문적·신뢰감 있는 어조, 업계 인사이트 중심.\n"),
}

PASS2_RULES = {
    "naver": (
        "## 플랫폼 포맷: 네이버 블로그 (플레인 텍스트 전용)\n"
        "- 마크다운 기호(#, ##, ###, **, *, -, |, ---, ```)를 어떤 상황에서도 사용 금지.\n"
        "- 소제목은 기호 없이 한 줄 텍스트로, 문단 사이에 빈 줄을 둔다.\n"
        "- 표(테이블) 대신 '1) 2) 3)' 넘버링 또는 자연스러운 문단 나열로 구조화한다.\n"
        "- 친근한 대화체, 공감 유도, 30~50대 정보 검색 독자 대상.\n"
        "- 마지막 섹션 순서: '자주 묻는 질문'(Q./A. 플레인 텍스트) → '마무리'(핵심 요약 3~5개).\n"),
    "tistory": (
        "## 플랫폼 포맷: 티스토리 (마크다운 + 구글 SEO)\n"
        "- H2 소제목에 번호 서식 필수 (## 1. 소제목), 하위 소제목은 ### 1-1. 형식.\n"
        "- 첫문단은 150~160자 내외 구글 메타 디스크립션 역할의 즉답 요약.\n"
        "- 표(markdown table)를 1~2개 이상 적극 활용. 전문적·분석적 어조.\n"
        "- 마지막 섹션: '## N. 자주 묻는 질문 (FAQ)' — > 인용문 형식 Q/A 3~5개.\n"
        "- 마무리 섹션에 핵심 정리 불릿과 공감·댓글 CTA 문구 포함.\n"),
    "adsense": (
        "## 플랫폼 포맷: 구글 애드센스 블로그 (마크다운 + 수익 최적화)\n"
        "- H2 소제목에 번호 서식 필수 (## 1. 소제목), 하위 소제목은 ### 1-1. 형식.\n"
        "- 첫문단 직후 '이 글에서 다루는 내용' 불릿 요약 리스트를 삽입한다.\n"
        "- 표(markdown table)를 1~2개 이상 적극 활용. 실용적·문제 해결 중심.\n"
        "- 클릭 유도·과장 광고 문구 금지 (애드센스 정책 준수).\n"
        "- 마지막 섹션: '## 자주 묻는 질문' — ### 질문 + 간결 답변 3~5개.\n"),
    "brand": (
        "## 플랫폼 포맷: 브랜드 블로그 (마크다운 + 신뢰 구축)\n"
        "- H2 소제목에 번호 서식 필수 (## 1. 소제목), 하위 소제목은 ### 1-1. 형식.\n"
        "- 표(markdown table)를 필요시 활용. 전문적이면서 친근한 어조.\n"
        "- 자사 홍보는 배제하고 객관적 정보·업계 인사이트 중심.\n"
        "- 마무리 섹션에 '더 자세한 내용은 관련 서비스/제품 페이지를 확인하세요' 같은 부드러운 간접 CTA 포함.\n"),
}

# 태그·썸네일 아이디어 공통 지시 (모든 플랫폼)
PASS2_COMMON_TAIL = (
    "8. 태그 {TAGS_PROMPT_MIN}~{TAGS_PROMPT_MAX}개: 주제 키워드를 첫 태그로, "
    "이어서 변형·연관어(지역·계절·용도·대상 등). # 기호 없이 낱개만\n"
    "9. 썸네일 아이디어 2개: 클릭률을 높이는 구체적인 비주얼 콘셉트 "
    "(색상, 구도, 텍스트 배치, 이미지 구성을 각 1~2문장으로)\n"
)
