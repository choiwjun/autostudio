# engine/fortune_content.py — v22.2(3.1~3.2): 운세 콘텐츠 생성
# "엔진 = 데이터, LLM = 통역사" 원칙 구현:
#   1. build_daily_grounding()  — 오늘 일진 기반 결정적 그라운딩 데이터 조립
#   2. generate_sns_summary()   — 프롬프트 A (SNS 요약본, 500자 이내)
#   3. generate_blog_detail()   — 프롬프트 B (블로그 상세본, 2,500~3,500자)
#   4. 검수                     — 금지어·전문용어·기준일·SNS 길이
# 발행(Phase 2 발행 API)은 별도 — 생성물은 fortune_generations 큐에 저장.
import json
import re

import config as config_mod
import llm_client
from engine.calendar import get_daily_fortune, get_ganji, get_monthly_rhythm
from engine.day_pillar import day_pillar_profile, to_hangul_pillar
from engine.fortune_extra import field_fortunes, lucky_elements

BANNED_WORDS = ("반드시", "무조건", "100%")
# 블로그 상세본 전용: 일반 독자가 모르는 전문용어 — 포함 시 재생성 지시
EXPERT_TERMS = ("일간", "간지", "십신", "지지", "천간", "육친", "대운", "세운",
                "월주", "년주", "시주", "일주", "용신", "격국", "오행", "편재",
                "정재", "편관", "정관", "식신", "상관", "비견", "겁재", "편인",
                "정인", "갑목", "을목", "병화", "정화", "무토", "기토", "경금",
                "신금", "임수", "계수", "자시", "축시")
SNS_MAX_LEN = 500


def _gan_hangul(ganji_day):
    """한자 일주('丁巳') → 한글 일간('정')."""
    hangul = to_hangul_pillar(ganji_day)
    return hangul[0] if len(hangul) == 2 else '갑'


def build_daily_grounding(today=None):
    """오늘 일진 기반 그라운딩 데이터 (결정적 조립 — 3.1).
    반환: dict — 프롬프트 A·B의 그라운딩 블록 원료."""
    today = today or config_mod.today_kst()
    date_key = today.isoformat()
    # 정오 기준 4기둥 (자시 경계 회피)
    ganji = get_ganji(today.year, today.month, today.day, 12, 0)
    day_gan = _gan_hangul(ganji["day"]["ganji"])
    fortune = get_daily_fortune(day_gan, today.year, today.month, today.day)
    fields = field_fortunes(day_gan, today.year, today.month, today.day)
    lucky = lucky_elements(day_gan)
    keyword, summary = day_pillar_profile(ganji["day"]["ganji"])
    month_rhythm = get_monthly_rhythm(day_gan, today.year, today.month)
    return {
        "reference_date": date_key,
        "day_gan": day_gan,
        "day_pillar": to_hangul_pillar(ganji["day"]["ganji"]),
        "day_pillar_keyword": keyword,
        "day_pillar_summary": summary,
        "energy": fortune["energy"],
        "fortune_text": fortune["text"],
        "fields": fields,
        "lucky": lucky,
        "month_rhythm_summary": month_rhythm["summary"],
        "month_rhythm_energy": month_rhythm["energy"],
        "month_rhythm_recommendation": month_rhythm["recommendation"],
    }


def _grounding_block(g):
    """그라운딩 dict → 프롬프트 주입용 텍스트 블록."""
    fields = "\n".join(f"- {k}: {v}" for k, v in g["fields"].items() if v)
    lucky = " · ".join(f"{k} {v}" for k, v in g["lucky"].items())
    return (
        f"## 엔진 데이터 (변형 금지 — 의미 방향 유지)\n"
        f"- 기준일: {g['reference_date']}\n"
        f"- 일간 에너지: {g['energy']}\n"
        f"- 핵심 문구: {g['fortune_text']}\n"
        f"- 분야별:\n{fields}\n"
        f"- 행운 요소: {lucky}\n"
        f"- 월간 흐름: {g['month_rhythm_summary']} ({g['month_rhythm_energy']})\n"
    )


_SNS_SYSTEM = (
    "당신은 운세 콘텐츠 작가입니다. 아래 엔진 데이터를 그대로 사용해 "
    "일반인이 읽는 SNS 운세 카드 문구를 작성합니다."
)

_SNS_RULES = (
    "1. 후킹 한 문장으로 시작한다 (예: \"오늘은 ___ 하기 좋은 날\")\n"
    "2. 엔진 핵심 문구의 의미를 일상어로 풀어 3~5문장 작성한다\n"
    "3. 분야별(재물/애정/건강/일)을 각 한 줄씩 담는다\n"
    "4. 행운 요소(색·숫자·방위)를 한 줄로 담는다\n"
    "5. 마지막에 CTA: \"더 자세한 오늘의 운세는 블로그에서 확인하세요\"\n"
    "6. 총 길이 500자 이내\n"
    "7. 금지: 반드시/무조건/100% 표현, 간지·십신 등 전문용어\n"
    "8. 기준일({ref})이 명확히 드러나야 한다\n"
)


def _run_llm(prompt, timeout=90):
    """Token Plan LLM 호출 (draft_generator와 동일 패턴) — JSON 응답."""
    if not llm_client.has_api_key():
        raise RuntimeError("Token Plan API 키가 필요합니다 (BAILIAN_TOKEN_PLAN_API_KEY)")
    base_url = llm_client.resolve_base_url(
        "https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1")
    data = llm_client.post_json(
        f"{base_url}/chat/completions",
        {
            "model": "deepseek-v4-flash-0731",
            "messages": [
                {"role": "system", "content": _SNS_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 3000,
            "enable_thinking": False,
        },
        llm_client.resolve_api_key(), timeout, RuntimeError, "fortune API",
    )
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"fortune API bad response: {str(data)[:200]}") from e


def _parse_json_output(raw):
    text = llm_client.strip_code_fence(raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"fortune not json: {text[:200]}") from e
    return data


# ---------- 검수 ----------

def check_banned_words(text):
    return [w for w in BANNED_WORDS if w in (text or "")]


def check_expert_terms(text):
    return [t for t in EXPERT_TERMS if t in (text or "")]


def check_reference_date(text, ref_date):
    return ref_date in (text or "")


def check_sns_length(text):
    return len(text or "") <= SNS_MAX_LEN


# ---------- 프롬프트 A·B ----------

def build_sns_prompt(g):
    return (
        f"{_grounding_block(g)}\n"
        f"## SNS 카드 문구 규칙\n{_SNS_RULES.format(ref=g['reference_date'])}\n"
        "## 출력 형식 (JSON만)\n"
        '{"text": "...", "hashtags": ["운세", "오늘의운세", "..."]}\n'
    )


def generate_sns_summary(g, runner=None):
    """프롬프트 A — SNS 요약본 (500자 이내). runner 주입 시 결정적 테스트 가능."""
    run = runner or _run_llm
    raw = run(build_sns_prompt(g))
    data = _parse_json_output(raw)
    text = str(data.get("text", "")).strip()
    hashtags = data.get("hashtags", []) if isinstance(data.get("hashtags"), list) else []
    return {"text": text, "hashtags": [str(h) for h in hashtags]}


def build_blog_prompt(g):
    return (
        f"{_grounding_block(g)}\n"
        "## 블로그 상세 글 규칙\n"
        "1. 제목(날짜+핵심 키워드) → 한줄 요약 → 총평 → 분야별 상세(재물/애정/"
        "건강/일 각 5~8문장) → 행운 아이템 → 실천 가이드 → 마무리\n"
        "2. 총 2,500~3,500자 — 일반인이 읽는 친근한 존댓말\n"
        "3. 엔진 데이터의 의미 방향(긍정/부정/특성)은 유지하되 일상 언어로 풀어쓴다\n"
        "4. 금지: 반드시/무조건/100% 표현, 전문용어(일간/간지/십신/오행 등)\n"
        f"5. 기준일 {g['reference_date']}이 제목·본문에 명확히 드러나야 한다\n"
        "6. 마무리에 \"더 정확한 사주 분석이 궁금하면 다른 운세 글도 확인해보세요\" "
        "같은 블로그 내 유도 CTA를 넣는다\n"
        "## 출력 형식 (JSON만)\n"
        '{"title": "...", "summary": "...", "body": "..."}\n'
    )


def generate_blog_detail(g, runner=None):
    """프롬프트 B — 블로그 상세본. runner 주입 시 결정적 테스트 가능."""
    run = runner or _run_llm
    raw = run(build_blog_prompt(g))
    data = _parse_json_output(raw)
    return {
        "title": str(data.get("title", "")).strip(),
        "summary": str(data.get("summary", "")).strip(),
        "body": str(data.get("body", "")).strip(),
    }


def validate_content(content, ref_date, content_type):
    """검수 — 위반 시 (통과 False, 사유 리스트). SNS본은 길이도 검사."""
    text = content.get("text", "") if content_type == "sns" \
        else f"{content.get('title', '')}\n{content.get('body', '')}"
    checks = []
    banned = check_banned_words(text)
    if banned:
        checks.append(f"금지어: {', '.join(banned)}")
    expert = check_expert_terms(text)
    if expert:
        checks.append(f"전문용어: {', '.join(expert[:4])}")
    if not check_reference_date(text, ref_date):
        checks.append("기준일 미포함")
    if content_type == "sns" and not check_sns_length(text):
        checks.append(f"SNS 길이 초과({len(text)}자 > {SNS_MAX_LEN})")
    return (not checks), checks
