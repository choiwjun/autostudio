# engine/calendar.py — v22.2(1.2): 만세력 계산 core (myunglab 최신 소스 포팅)
# temporal(율리우스일·KST 타임스탬프) + solar-terms(절기) + ganji(사주 4기둥)의
# 1:1 Python 이식. 결정적 계산 — myunglab golden-fixtures로 검증(1.4).
# 데이터는 engine/calendar_data.py(SQLite)에서 조회.
from datetime import datetime, timedelta, timezone

from engine.calendar_data import get_solar_terms

KST = timezone(timedelta(minutes=9 * 60))
SOURCE_TO_KST_OFFSET_HOURS = 1  # myunglab 소스 데이터의 UTC+1 보정 (동지 기준 등)

STEMS = ('甲', '乙', '丙', '丁', '戊', '己', '庚', '辛', '壬', '癸')
BRANCHES = ('子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥')
MONTH_BRANCH_START_INDEX = 2  # 인월 = 지지 3번째(0-based 2)

# 절(節) — 월주 경계가 되는 12절기 → 월 인덱스 (0 = 인월)
MAJOR_SOLAR_TERM_TO_MONTH_INDEX = {
    '소한': 11, '입춘': 0, '경칩': 1, '청명': 2, '입하': 3, '망종': 4,
    '소서': 5, '입추': 6, '백로': 7, '한로': 8, '입동': 9, '대설': 10,
}
JEOL_SOLAR_TERM_NAMES = tuple(MAJOR_SOLAR_TERM_TO_MONTH_INDEX.keys())

# 년간 → 인월(寅月) 천간 시작 인덱스 (둔간법)
TIGER_MONTH_STEM_START = {
    '甲': 2, '己': 2, '乙': 4, '庚': 4, '丙': 6, '辛': 6,
    '丁': 8, '壬': 8, '戊': 0, '癸': 0,
}


def timedelta_minutes(minutes):
    return timedelta(minutes=minutes)


def mod(value, divisor):
    return ((value % divisor) + divisor) % divisor


def to_julian_day(year, month, day):
    """양력 날짜 → 율리우스일 (temporal.toJulianDay 1:1 이식)."""
    a = (14 - month) // 12
    y = year + 4800 - a
    m = month + 12 * a - 3
    return (day + (153 * m + 2) // 5 + 365 * y
            + y // 4 - y // 100 + y // 400 - 32045 - 0.5)


def to_kst_timestamp(parts):
    """KST 벽시계 부품 → UTC 타임스탬프 (temporal.toKstTimestamp 1:1)."""
    dt = datetime(parts['year'], parts['month'], parts['day'],
                  parts.get('hour', 0), parts.get('minute', 0),
                  parts.get('second', 0), tzinfo=timezone(timedelta_minutes(9 * 60)))
    return dt.timestamp()


def _normalize_to_kst(term):
    """solar-terms 소스 데이터 → KST 벽시계 보정 (+1h, julianDay +1/24).
    hour=23인 절기는 +1h로 다음 날 0시가 됨 — datetime 자동 정규화."""
    shifted = (datetime(term['year'], term['month'], term['day'],
                        term['hour'], term['minute'], term['second'],
                        tzinfo=timezone.utc)
               + timedelta(hours=SOURCE_TO_KST_OFFSET_HOURS))
    return {
        'source_name': term['source_name'],
        'korean_name': term['korean_name'],
        'year': shifted.year,
        'month': shifted.month,
        'day': shifted.day,
        'hour': shifted.hour,
        'minute': shifted.minute,
        'second': shifted.second,
        'julian_day': term['julian_day'] + SOURCE_TO_KST_OFFSET_HOURS / 24,
    }


def list_solar_terms_for_year(year, db_path=None):
    """연도별 24절기 (KST 보정 후) — SQLite 데이터를 1회 보정해 반환."""
    return [_normalize_to_kst(t) for t in get_solar_terms(year, db_path=db_path)]


def get_latest_major_solar_term(date_parts, db_path=None):
    """기준 시각 이전 가장 최근 절(節)기 — 월주 경계 판정.
    date_parts: {'year','month','day','hour','minute','second'} (KST 벽시계)"""
    effective_ts = to_kst_timestamp(date_parts)
    candidates = []
    for year in (date_parts['year'] - 1, date_parts['year']):
        candidates += [t for t in list_solar_terms_for_year(year, db_path)
                       if t['korean_name'] in MAJOR_SOLAR_TERM_TO_MONTH_INDEX]
    best = None
    for term in candidates:
        term_ts = to_kst_timestamp(term)
        if term_ts <= effective_ts and (best is None
                                        or term_ts > to_kst_timestamp(best)):
            best = term
    if best is None:
        raise ValueError(f"No major solar term found for {date_parts}")
    return best


def get_ipchun(year, db_path=None):
    terms = [t for t in list_solar_terms_for_year(year, db_path)
             if t['korean_name'] == '입춘']
    if not terms:
        raise ValueError(f"No 입춘 data for {year}")
    return terms[0]


def _create_pillar(sexagenary_index):
    normalized = mod(sexagenary_index, 60)
    gan = STEMS[normalized % 10]
    ji = BRANCHES[normalized % 12]
    return {'gan': gan, 'ji': ji, 'ganji': f'{gan}{ji}'}


def _get_day_index(year, month, day):
    return mod(int(to_julian_day(year, month, day) + 49.5), 60)


def get_ganji(year, month, day, hour=0, minute=0, second=0,
              sect=2, db_path=None):
    """사주 4기둥 (ganji.getGanji 1:1 이식 — 최신 소스 기준).
    sect: 1=자시 일주 바꿈(야자시), 2=안 바꿈. hour=23 처리 포함.
    반환: {'year':{'gan','ji','ganji'}, 'month':..., 'day':..., 'hour':...}
    dayHourDateTimeSchoolApplied: 학교 적용 여부 (False 기본 — 23시 shift)"""
    base = {'year': year, 'month': month, 'day': day,
            'hour': hour, 'minute': minute, 'second': second}
    # 년주: 입춘 경계
    ipchun = get_ipchun(base['year'], db_path)
    effective_ts = to_kst_timestamp(base)
    effective_year = base['year'] if effective_ts >= to_kst_timestamp(ipchun) \
        else base['year'] - 1
    year_pillar = _create_pillar(effective_year - 1984)  # 1984 = 갑자년

    # 월주: 가장 최근 절(節)기 기준
    latest = get_latest_major_solar_term(base, db_path)
    month_index = MAJOR_SOLAR_TERM_TO_MONTH_INDEX[latest['korean_name']]
    stem_start = TIGER_MONTH_STEM_START[year_pillar['gan']]
    stem = STEMS[mod(stem_start + month_index, 10)]
    branch = BRANCHES[mod(MONTH_BRANCH_START_INDEX + month_index, 12)]
    month_pillar = {'gan': stem, 'ji': branch, 'ganji': f'{stem}{branch}'}

    # 일주: sect=1 & 23시 & 미적용이면 +24h shift
    if sect == 1 and hour == 23:
        base_date = _shift_utc(base, 24 * 60)
    else:
        base_date = base
    day_pillar = _create_pillar(_get_day_index(
        base_date['year'], base_date['month'], base_date['day']))

    # 시주: 자시(23시) shift + 시간 천간 (둔간법)
    hour_branch_index = 0 if (hour == 23 or hour == 0) else (hour + 1) // 2
    hour_base = _shift_utc(base, 24 * 60) if hour == 23 else base
    hour_base_pillar = _create_pillar(_get_day_index(
        hour_base['year'], hour_base['month'], hour_base['day']))
    day_stem_index = STEMS.index(hour_base_pillar['gan'])
    offsets = (0, 2, 4, 6, 8)
    hour_stem_index = mod(offsets[day_stem_index % 5] + hour_branch_index, 10)
    hour_pillar = {'gan': STEMS[hour_stem_index],
                   'ji': BRANCHES[hour_branch_index],
                   'ganji': f'{STEMS[hour_stem_index]}{BRANCHES[hour_branch_index]}'}

    return {
        'year': year_pillar, 'month': month_pillar,
        'day': day_pillar, 'hour': hour_pillar,
    }


def _shift_utc(parts, minutes):
    """벽시계를 UTC로 해석해 minutes만큼 이동 (temporal.shiftDateTimeUtc 1:1)."""
    dt = datetime(parts['year'], parts['month'], parts['day'],
                  parts['hour'], parts['minute'], parts['second'],
                  tzinfo=timezone.utc) + timedelta_minutes(minutes)
    return {'year': dt.year, 'month': dt.month, 'day': dt.day,
            'hour': dt.hour, 'minute': dt.minute, 'second': dt.second}


# ---------- v22.2(1.3): 운세 문구 (daily-fortune·monthly-rhythm 포팅) ----------

DAY_GAN_ENERGY = {
    '갑': '목(木)', '을': '목(木)', '병': '화(火)', '정': '화(火)',
    '무': '토(土)', '기': '토(土)', '경': '금(金)', '신': '금(金)',
    '임': '수(水)', '계': '수(水)',
}

FORTUNE_PHRASES = [
    # 목(木) 계열 — 성장, 시작, 추진
    '새로운 아이디어가 자연스럽게 떠오르기 좋은 흐름입니다.',
    '오늘은 작은 행동 하나가 큰 방향을 만들어줄 수 있습니다.',
    '한 걸음 앞으로 내딛기에 좋은 에너지가 흐릅니다.',
    '오래 미뤄온 일을 다시 꺼내보기에 좋은 날입니다.',
    '계획을 구체적인 행동으로 옮기는 데 좋은 흐름입니다.',
    '주변의 변화를 유연하게 받아들이는 것이 도움이 됩니다.',
    '오늘은 자신이 원하는 방향을 조용히 되새겨보는 시간이 유익할 수 있습니다.',
    '작게 시작해도 괜찮습니다. 움직임 자체가 오늘의 에너지입니다.',
    '새로운 연결이 예상치 못한 곳에서 생길 가능성이 있습니다.',
    '자신의 직관을 조금 더 믿어보는 것이 좋습니다.',
    # 화(火) 계열 — 열정, 표현, 집중
    '오늘은 자신의 생각을 솔직하게 표현할 좋은 기회가 있을 수 있습니다.',
    '열정적으로 집중하되, 잠시 쉬는 시간도 균형을 위해 중요합니다.',
    '상대방에게 먼저 다가가보는 것이 예상보다 좋은 결과를 가져올 수 있습니다.',
    '오늘의 에너지는 창의적인 작업과 잘 맞는 편입니다.',
    '말보다 행동으로 보여줄 기회가 생길 수 있습니다.',
    '감정을 표현하고 싶다면, 오늘은 그 타이밍이 좋을 수 있습니다.',
    '자신의 페이스를 지키면서 앞으로 나아가는 것이 효과적입니다.',
    '오늘은 에너지를 한 곳에 집중할 때 더 좋은 흐름이 만들어집니다.',
    '주변 사람들과의 소통에서 새로운 가능성이 열릴 수 있습니다.',
    '조용히 혼자 집중하는 시간이 오늘의 흐름과 잘 맞을 수 있습니다.',
    # 토(土) 계열 — 안정, 신뢰, 인내
    '안정적인 흐름 속에서 꾸준함이 빛을 발하는 날입니다.',
    '오늘은 익숙한 환경에서 묵묵히 쌓아가는 것이 효과적입니다.',
    '신뢰할 수 있는 사람과 대화를 나눠보는 것이 도움이 될 수 있습니다.',
    '천천히 검토하는 것이 빠른 결정보다 나을 수 있는 날입니다.',
    '주변을 돌아보며 감사할 것들을 찾아보는 것이 기분에 도움이 됩니다.',
    '한 가지에 집중하면 오늘의 에너지를 더 효과적으로 쓸 수 있습니다.',
    '변화보다 지금 있는 자리를 단단히 다지는 것이 좋을 수 있습니다.',
    '오늘의 작은 노력이 나중에 의미 있는 결과로 이어질 가능성이 있습니다.',
    '관계에서 여유를 갖고 상대의 이야기를 들어보는 것이 좋습니다.',
    '오늘은 처음 계획한 방향대로 차분하게 진행하는 것이 효과적입니다.',
    # 금(金) 계열 — 결단, 정리, 집중
    '오늘은 불필요한 것을 정리하기에 좋은 흐름이 있습니다.',
    '중요한 결정을 앞두고 있다면, 오늘 조용히 정리해보는 것도 좋습니다.',
    '명확한 기준을 세우는 것이 오늘 특히 도움이 될 수 있습니다.',
    '복잡하게 얽힌 것을 단순하게 정리할 에너지가 있는 날입니다.',
    '오늘은 솔직한 피드백이 오히려 관계에 도움이 될 수 있습니다.',
    '마무리하지 못한 일을 끝내는 데 좋은 흐름이 있습니다.',
    '자신의 기준을 지키면서 움직이는 것이 오늘의 좋은 흐름입니다.',
    '집중력이 필요한 작업을 오늘 처리하면 좋은 결과를 얻을 수 있습니다.',
    '효율적으로 움직이는 것이 오늘의 에너지와 잘 맞습니다.',
    '오늘은 핵심에 집중하고 주변 소음은 잠시 내려놓는 것이 좋습니다.',
    # 수(水) 계열 — 통찰, 흐름, 내면
    '오늘은 내면의 직관을 따라가보는 것이 좋은 흐름입니다.',
    '관찰하며 기다리는 것이 오늘 더 좋은 선택일 수 있습니다.',
    '조용한 시간 속에서 좋은 아이디어가 떠오를 가능성이 있습니다.',
    '상황의 흐름을 읽으며 유연하게 대응하는 것이 오늘과 잘 맞습니다.',
    '전략적으로 생각하기에 좋은 에너지가 흐르는 날입니다.',
    '오늘은 감정보다 상황을 객관적으로 바라보는 것이 도움이 됩니다.',
    '충분히 생각한 후에 움직여도 늦지 않은 날입니다.',
    '주변의 변화를 예민하게 감지할 수 있는 날입니다.',
    '신뢰할 수 있는 소수와 깊은 대화를 나눠보는 것이 좋습니다.',
    '오늘은 혼자만의 사색 시간이 내일의 방향을 잡아줄 수 있습니다.',
    # 범용 — 관계, 균형, 건강, 기회
    '관계에서 한 발짝 물러나 관찰하는 것이 도움이 됩니다.',
    '예상치 못한 작은 기회에 주의를 기울여보는 것이 좋습니다.',
    '몸의 신호에 귀를 기울이고, 충분한 휴식을 취하는 것이 좋습니다.',
    '오늘은 일보다 사람에게 집중해보는 것이 좋은 흐름입니다.',
    '자신에게 솔직해지는 것이 오늘의 좋은 출발점입니다.',
    '작은 감사의 마음이 오늘의 에너지를 높여줄 수 있습니다.',
    '오늘 하루를 무리하지 않고 자신의 속도로 채워가는 것이 좋습니다.',
    '새로운 정보를 받아들이기 좋은 흐름이 있는 날입니다.',
    '잠시 걷거나 가볍게 움직이는 것이 오늘의 에너지에 도움이 됩니다.',
    '오늘은 대화에서 먼저 듣는 자세가 좋은 인상을 줄 수 있습니다.',
    '창의적인 생각이 잘 떠오르는 흐름입니다.',
    '무언가를 배우거나 탐구하기에 좋은 에너지가 있습니다.',
    '과거의 결정을 너무 돌아보기보다, 오늘 할 수 있는 것에 집중하는 것이 좋습니다.',
    '오늘은 완벽함보다 완성에 초점을 맞추는 것이 효과적입니다.',
    '주변 사람에게 작은 친절을 베풀면 예상치 못한 좋은 흐름이 만들어질 수 있습니다.',
    '걱정보다 지금 이 순간에 집중하는 것이 오늘의 좋은 선택입니다.',
    '자신을 돌보는 시간을 조금 더 확보하는 것이 오늘에 잘 맞습니다.',
    '오늘은 결과보다 과정에서 배움을 찾는 것이 의미 있습니다.',
    '기대보다 조금 유연하게 상황을 받아들이면 더 좋은 흐름이 생길 수 있습니다.',
    '오늘은 자신이 잘하는 것에 집중하면 자연스럽게 에너지가 높아집니다.',
    '소소한 일상에서 즐거움을 찾는 것이 오늘의 좋은 흐름입니다.',
    '약속이 있다면 조금 여유롭게 준비하는 것이 좋습니다.',
    '직감이 말하는 것을 무시하지 않는 것이 좋은 날입니다.',
    '오늘은 혼자 생각하는 시간과 사람들과 함께하는 시간의 균형이 좋습니다.',
    '정리되지 않은 감정이 있다면, 오늘 조용히 들여다보는 것이 도움이 됩니다.',
    '밀린 연락을 하기에 좋은 에너지가 흐르는 날입니다.',
    '오늘은 남의 시선보다 자신의 기준을 따르는 것이 좋은 흐름입니다.',
    '작은 목표를 하나 정하고 그것을 완수하는 것이 오늘의 좋은 리듬입니다.',
    '새로운 시각으로 같은 상황을 바라보면 해결책이 보일 수 있습니다.',
    '오늘은 마음을 가볍게 하는 것이 생산성에도 도움이 됩니다.',
    '좋아하는 음악이나 책과 함께 시간을 보내는 것이 오늘과 잘 맞습니다.',
    '자신의 페이스를 잃지 않는 것이 오늘 특히 중요합니다.',
    '오늘은 감사 일기를 써보면 기분이 한결 나아질 수 있습니다.',
    '주변 환경을 조금 정리하는 것이 마음의 여유를 만들어줍니다.',
    '오늘은 한 번에 여러 일을 처리하기보다 하나씩 집중하는 것이 효과적입니다.',
    '좋은 흐름은 서두른다고 빨리 오지 않습니다. 오늘은 차분히 기다려보세요.',
    '오늘 만나는 사람 한 명 한 명이 모두 의미 있는 연결일 수 있습니다.',
    '에너지가 낮다면, 억지로 채우기보다 회복을 선택하는 것이 좋습니다.',
    '오늘은 계획에 없던 일이 생겨도 유연하게 대처할 수 있는 날입니다.',
    '가볍게 시작한 일이 의외로 좋은 결과를 가져올 수 있는 날입니다.',
    '자신이 원하는 것을 명확하게 말하는 것이 오늘의 좋은 전략입니다.',
    '오늘은 익숙하지 않은 방법을 시도해보는 것이 흥미로운 결과를 줄 수 있습니다.',
    '상대방의 입장을 먼저 들어보는 것이 오늘의 소통에 도움이 됩니다.',
    '완벽한 준비보다 시작하는 용기가 오늘 더 중요할 수 있습니다.',
    '오늘 하루, 자신에게 작은 선물을 해보는 것도 좋습니다.',
    '걱정하던 일이 생각보다 쉽게 해결될 가능성이 있는 날입니다.',
    '좋은 결과는 오늘 심은 씨앗에서 나중에 나오는 경우가 많습니다.',
    '오늘은 경쟁보다 협력에서 더 좋은 에너지가 나옵니다.',
    '자신의 감정을 판단하지 않고 그냥 느껴보는 것이 오늘의 좋은 연습입니다.',
    '오늘은 작은 성취에도 충분히 기뻐하는 것이 좋습니다.',
    # 계절/자연 감성
    '오늘의 에너지는 조용히 흐르는 물처럼 부드럽게 나아갑니다.',
    '아침의 맑은 공기처럼 새로운 가능성이 오늘을 채울 수 있습니다.',
    '뿌리가 깊은 나무처럼 흔들리지 않는 하루를 보낼 수 있습니다.',
    '바람이 방향을 바꾸듯, 오늘은 유연한 적응이 강점이 됩니다.',
    '이슬처럼 섬세한 감각이 오늘 빛을 발할 수 있습니다.',
    '불꽃처럼 집중하면 오늘 하고자 하는 것을 이룰 가능성이 높습니다.',
    '대지처럼 묵묵히 버티는 것이 오늘의 좋은 전략입니다.',
    '가을의 수확처럼 그동안의 노력이 결실을 맺기 시작할 수 있습니다.',
    '봄비처럼 조용히 스며드는 변화가 오늘 일어날 수 있습니다.',
    '달빛처럼 은은하게 빛나는 것이 오늘의 좋은 에너지입니다.',
    # 마음/내면
    '마음이 편안한 상태에서 내린 결정이 오늘 더 좋은 결과를 가져옵니다.',
    '잠시 숨을 고르고 현재에 집중하는 것이 오늘의 좋은 출발입니다.',
    '자신을 너무 몰아붙이지 않아도 됩니다. 오늘은 자신에게 여유를 주세요.',
    '내면의 목소리를 조용히 들어보는 것이 오늘 의미 있는 시간이 될 수 있습니다.',
    '오늘은 자신이 통제할 수 있는 것에만 에너지를 쏟는 것이 현명합니다.',
    '남과 비교하지 않고 자신의 성장에 집중하는 것이 오늘의 좋은 흐름입니다.',
    '기대를 내려놓으면 오늘 더 많은 것이 보일 수 있습니다.',
    '오늘은 이유 없이 기분이 좋아지는 순간이 있을 수 있습니다.',
    '작은 것에서 아름다움을 발견하는 것이 오늘을 풍요롭게 합니다.',
    '혼자이고 싶을 때는 혼자여도 괜찮습니다. 오늘은 그런 날일 수 있습니다.',
    # 일/성취
    '오늘 진행 중인 일이 예상보다 순조롭게 흘러갈 가능성이 있습니다.',
    '도움을 요청하는 것이 오늘 더 좋은 결과를 만들 수 있습니다.',
    '오늘은 작은 진전이 큰 의미를 가집니다.',
    '집중력이 높은 시간대를 활용하면 오늘 효율적인 하루가 됩니다.',
    '새로운 방식을 시도하면 예상치 못한 좋은 결과가 나올 수 있습니다.',
    '실수가 있어도 그것이 오늘의 배움이 됩니다.',
    '오늘은 완성하지 못하더라도, 시작한 것이 이미 좋은 흐름입니다.',
    '협력하는 관계에서 오늘 더 좋은 에너지가 나옵니다.',
    '오늘은 자신의 강점을 활용할 기회가 생길 수 있습니다.',
    '결과에 집착하기보다 과정을 즐기는 것이 오늘 더 좋은 에너지입니다.',
    # 관계/소통
    '솔직한 대화가 오늘의 관계를 더 단단하게 해줄 수 있습니다.',
    '상대의 좋은 면을 발견하는 것이 오늘의 좋은 연습입니다.',
    '기대하지 않았던 사람에게서 도움을 받을 수 있는 날입니다.',
    '오래 연락하지 못한 사람에게 먼저 손을 내밀어 보는 것이 좋습니다.',
    '관계에서 여유를 갖고 상대방의 속도를 존중하는 것이 오늘 좋습니다.',
    '오늘은 말보다 들음으로써 더 많은 것을 얻을 수 있습니다.',
    '진심이 담긴 말 한마디가 오늘 누군가에게 큰 힘이 될 수 있습니다.',
    '공감하려는 노력이 오늘의 관계를 더 따뜻하게 만들어줍니다.',
    '오늘 만나는 사람과의 대화에서 새로운 관점을 얻을 가능성이 있습니다.',
    '관계를 맺을 때 진정성을 갖는 것이 오늘 특히 중요합니다.',
    # 건강/회복
    '몸이 보내는 신호에 민감하게 반응하는 것이 오늘 좋습니다.',
    '충분한 수면이 오늘의 에너지를 결정하는 가장 중요한 요소입니다.',
    '작은 스트레칭이나 산책이 오늘의 흐름을 좋게 바꿔줄 수 있습니다.',
    '영양이 풍부한 음식을 먹는 것이 오늘의 에너지에 도움이 됩니다.',
    '오늘은 무리하지 않는 것이 장기적으로 더 좋은 선택입니다.',
    '자연을 가까이하는 것이 오늘의 에너지 회복에 도움이 됩니다.',
    '충분한 물을 마시는 작은 습관이 오늘을 더 편안하게 합니다.',
    '좋아하는 사람과 함께하는 시간이 오늘의 에너지를 채워줍니다.',
    '긴장을 풀고 천천히 호흡하는 것이 오늘 도움이 됩니다.',
    '지금 이 순간이 충분히 소중하다는 것을 느끼는 것이 오늘의 선물입니다.',
    # 추가 문구 (151~200)
    '오늘은 자신을 과소평가하지 않는 것이 중요합니다.',
    '한 번 더 시도해볼 용기가 오늘의 에너지와 잘 맞습니다.',
    '오늘은 작은 변화가 큰 차이를 만들 수 있는 날입니다.',
    '자신이 가진 것에 집중하면 오늘 더 좋은 흐름이 생깁니다.',
    '오늘은 지금 이 순간에 충실하는 것이 가장 좋은 전략입니다.',
    '새로운 가능성이 예상치 못한 방향에서 다가올 수 있습니다.',
    '오늘은 누군가에게 진심 어린 칭찬을 건네보는 것이 좋습니다.',
    '복잡한 것을 단순하게 볼 수 있는 안목이 오늘 빛을 발합니다.',
    '자신만의 속도로 걸어가는 것이 오늘의 좋은 선택입니다.',
    '오늘은 결과보다 태도가 더 중요한 날입니다.',
    '가볍게 웃는 것이 오늘의 에너지를 높여줍니다.',
    '오늘은 타인의 평가보다 자신의 만족을 우선에 두는 것이 좋습니다.',
    '불확실한 상황에서도 한 걸음씩 나아가는 것이 오늘의 흐름입니다.',
    '오늘은 감사한 사람에게 그 마음을 전해보는 것이 좋습니다.',
    '자신의 직관과 논리가 균형을 이루는 날입니다.',
    '오늘은 여유로운 마음이 더 좋은 결과를 불러옵니다.',
    '실패를 두려워하지 않는 마음이 오늘의 강점이 됩니다.',
    '오늘은 즉흥적인 결정이 오히려 좋은 흐름을 만들 수 있습니다.',
    '가까운 사람과 솔직한 대화를 나눠보는 것이 오늘 도움이 됩니다.',
    '오늘은 자신의 장점을 다시 한번 확인해보는 것이 좋습니다.',
    '집중해야 할 일이 있다면, 오늘 그것에 몰입해보세요.',
    '오늘은 주변에서 좋은 에너지를 발견하기 좋은 날입니다.',
    '편안한 환경을 만드는 것이 오늘의 생산성에 도움이 됩니다.',
    '오늘은 한 가지 좋은 습관을 실천하는 것이 의미 있습니다.',
    '주변의 지지를 받아들이는 것도 능력입니다. 오늘 그것을 연습해보세요.',
    '오늘은 큰 그림을 그리기보다 눈앞의 한 가지에 집중하는 것이 좋습니다.',
    '포기했던 것을 다시 시작해보기에 좋은 에너지가 있습니다.',
    '오늘은 자신에게 너그러운 하루를 허락해보세요.',
    '기분 좋은 음악을 듣는 것이 오늘의 흐름에 도움이 됩니다.',
    '오늘은 계획보다 조금 더 유연하게 움직이는 것이 좋습니다.',
    '자신이 원하는 것을 글로 적어보는 것이 오늘 효과적입니다.',
    '오늘은 지금 하고 있는 일이 의미 있다는 것을 기억하세요.',
    '예상보다 빠르게 좋은 흐름이 올 수 있는 날입니다.',
    '오늘은 한 발 물러서서 전체를 바라보는 것이 도움이 됩니다.',
    '작은 감사의 순간들이 오늘을 충만하게 채워줍니다.',
    '오늘은 자신이 좋아하는 일을 조금이라도 해보는 것이 좋습니다.',
    '의심하기보다 믿어보는 것이 오늘의 좋은 선택입니다.',
    '오늘은 무언가를 배우는 시간을 따로 갖는 것이 의미 있습니다.',
    '작은 성공 경험이 오늘의 자신감을 높여줄 수 있습니다.',
    '오늘은 자신이 통제할 수 없는 것에 에너지를 낭비하지 않는 것이 현명합니다.',
    '호기심을 갖고 새로운 것을 탐구하기에 좋은 에너지가 있습니다.',
    '오늘은 부드러운 말 한마디가 관계를 더 따뜻하게 합니다.',
    '자신이 원하는 방향으로 조금씩 다가가는 오늘이 됩니다.',
    '오늘은 결정을 미루기보다 작은 한 걸음을 내딛는 것이 좋습니다.',
    '주변의 아름다움에 눈을 돌리면 오늘이 더 풍요로워집니다.',
    '오늘은 자신의 감정을 솔직하게 인정하는 것이 도움이 됩니다.',
    '힘든 순간도 지나가고, 오늘의 흐름은 내일을 위한 준비입니다.',
    '오늘은 천천히, 그리고 충실하게 하루를 보내는 것이 좋습니다.',
    '자신을 믿는 것이 오늘의 가장 좋은 출발점입니다.',
]


def get_daily_fortune(day_gan, year, month, day):
    """일운 (daily-fortune.getDailyFortune 1:1) — 같은 날+일간 → 같은 문구."""
    gans = ('갑', '을', '병', '정', '무', '기', '경', '신', '임', '계')
    gan_idx = gans.index(day_gan) if day_gan in gans else 0
    date_num = year * 10000 + month * 100 + day
    hash_idx = (date_num * 31 + gan_idx * 7) % len(FORTUNE_PHRASES)
    return {
        'text': FORTUNE_PHRASES[hash_idx],
        'energy': DAY_GAN_ENERGY.get(day_gan, '목(木)'),
    }


MONTH_THEMES = {
    1: {'element': '토', 'keyword': '준비'},
    2: {'element': '목', 'keyword': '시작'},
    3: {'element': '목', 'keyword': '성장'},
    4: {'element': '토', 'keyword': '전환'},
    5: {'element': '화', 'keyword': '확장'},
    6: {'element': '화', 'keyword': '표현'},
    7: {'element': '토', 'keyword': '안정'},
    8: {'element': '금', 'keyword': '정리'},
    9: {'element': '금', 'keyword': '수확'},
    10: {'element': '토', 'keyword': '전환'},
    11: {'element': '수', 'keyword': '성찰'},
    12: {'element': '수', 'keyword': '마무리'},
}

GAN_ELEMENT = {g: e for g, e in (
    ('갑', '목'), ('을', '목'), ('병', '화'), ('정', '화'), ('무', '토'),
    ('기', '토'), ('경', '금'), ('신', '금'), ('임', '수'), ('계', '수'))}

_SHENG = {'목': '화', '화': '토', '토': '금', '금': '수', '수': '목'}
_KE = {'목': '토', '화': '금', '토': '수', '금': '목', '수': '화'}


def _get_relation(day_element, month_element):
    """오행 관계 (monthly-rhythm.getRelation 1:1): 비화/생아/아생/극아/아극."""
    if day_element == month_element:
        return '비화'
    if _SHENG[day_element] == month_element:
        return '아생'
    if _SHENG[month_element] == day_element:
        return '생아'
    if _KE[day_element] == month_element:
        return '아극'
    if _KE[month_element] == day_element:
        return '극아'
    return '비화'


RELATION_PROFILES = {
    '비화': {
        'energy_keywords': ['조화', '균형', '안정', '일관성'],
        'summaries': [
            '자신의 페이스를 유지하기 좋은 흐름입니다.',
            '내면의 균형이 잡히며 안정감을 느낄 수 있습니다.',
            '자기다움을 지키는 것이 가장 좋은 전략인 시기입니다.',
        ],
        'recommendations': [
            '평소 하던 루틴을 꾸준히 이어가는 것이 좋습니다.',
            '변화를 억지로 만들기보다 자연스러운 흐름을 따라가 보세요.',
            '내가 잘하는 일에 집중하면 좋은 결과가 따라올 수 있습니다.',
        ],
    },
    '생아': {
        'energy_keywords': ['충전', '지원', '회복', '풍요'],
        'summaries': [
            '에너지가 자연스럽게 채워지는 시기입니다.',
            '주변의 도움이 예상치 못한 곳에서 올 수 있습니다.',
            '마음과 몸이 회복되는 흐름 속에 있습니다.',
        ],
        'recommendations': [
            '새로운 것을 배우거나 경험하기에 좋은 타이밍입니다.',
            '긍정적인 에너지를 활용해 평소 미뤄둔 일을 시작해 보세요.',
            '주변 사람들의 지지를 적극적으로 받아들이는 것이 도움이 됩니다.',
        ],
    },
    '아생': {
        'energy_keywords': ['나눔', '소진', '기여', '관계'],
        'summaries': [
            '에너지를 주변에 나누게 되는 시기입니다.',
            '타인을 돕거나 기여하는 역할이 자연스럽게 주어질 수 있습니다.',
            '소비되는 에너지가 많으니 자기 관리가 중요합니다.',
        ],
        'recommendations': [
            '자신의 에너지를 점검하며 과도한 소모를 주의하세요.',
            '남을 돕되, 내 컨디션도 챙기는 균형이 필요합니다.',
            '쉬는 시간을 의식적으로 확보하는 것이 좋습니다.',
        ],
    },
    '극아': {
        'energy_keywords': ['도전', '긴장', '성장통', '변화'],
        'summaries': [
            '외부 압력이 느껴질 수 있지만 성장의 기회이기도 합니다.',
            '불편한 상황이 결국 더 단단하게 만드는 시기입니다.',
            '예상치 못한 변화에 유연하게 대처하는 것이 중요합니다.',
        ],
        'recommendations': [
            '큰 결정보다 작은 실행에 집중하면 부담이 줄어듭니다.',
            '무리하지 않는 선에서 도전을 받아들여 보세요.',
            '건강과 수면에 더 신경 쓰는 것이 이 시기의 좋은 전략입니다.',
        ],
    },
    '아극': {
        'energy_keywords': ['추진', '통제', '결단', '목표'],
        'summaries': [
            '주도적으로 움직이기 좋은 에너지가 있습니다.',
            '목표를 향해 밀고 나가는 힘이 강한 시기입니다.',
            '결단력이 필요한 일을 처리하기에 적합합니다.',
        ],
        'recommendations': [
            '목표를 구체적으로 세우고 실행에 옮기는 것이 효과적입니다.',
            '너무 강하게 밀어붙이기보다 부드러운 조율도 필요합니다.',
            '성과를 내기 좋은 타이밍이니 중요한 일을 이 시기에 배치해 보세요.',
        ],
    },
}


def _deterministic_index(year, month, gan_idx, pool_size):
    seed = year * 1000 + month * 100 + gan_idx * 7
    return abs(seed) % pool_size


def get_monthly_rhythm(day_gan, year, month):
    """월운 (monthly-rhythm.getMonthlyRhythm 1:1) — 일간×월 오행 관계 기반."""
    gans = ('갑', '을', '병', '정', '무', '기', '경', '신', '임', '계')
    gan_idx = gans.index(day_gan) if day_gan in gans else 0
    safe_gan = gans[gan_idx]
    safe_month = max(1, min(12, month))
    day_element = GAN_ELEMENT[safe_gan]
    month_theme = MONTH_THEMES[safe_month]
    relation = _get_relation(day_element, month_theme['element'])
    profile = RELATION_PROFILES[relation]
    summary_idx = _deterministic_index(year, safe_month, gan_idx,
                                       len(profile['summaries']))
    reco_idx = _deterministic_index(year + 1, safe_month, gan_idx,
                                    len(profile['recommendations']))
    energy_idx = _deterministic_index(year, safe_month + 13, gan_idx,
                                      len(profile['energy_keywords']))
    return {
        'year': year,
        'month': safe_month,
        'summary': profile['summaries'][summary_idx],
        'energy': f"{month_theme['keyword']} + {profile['energy_keywords'][energy_idx]}",
        'recommendation': profile['recommendations'][reco_idx],
    }


def get_yearly_rhythm(day_gan, year):
    """특정 일간의 12개월 리듬 (monthly-rhythm.getYearlyRhythm 1:1)."""
    return [get_monthly_rhythm(day_gan, year, m) for m in range(1, 13)]
