# 14. 유튜브 쇼츠 파이프라인 (Phase S)

> 상태: 기획 고도화 (2026-08-14 — 리서치 수치 근거 반영) · 관련: `11-fortune-channel.md`(수익화 로드맵 §9 — 쇼츠 이연 해소), `12-kdp-pipeline.md`(Phase K — KDP↔쇼츠 시너지 §9)
> 핵심 차별점: **네이버 인기키워드가 아니라 유튜브 인기 주제·채널·키워드 기반 발굴**
> 리서치 근거: `pipeline/shorts-kdp-research/research-report.md` (R-1~R-7) · 리서치QA 승인 (조건부 — P1·P2·P4 반영)
> 수치 규칙: 출처 인라인 표기, 단일 출처/C등급은 ⚠️ 표시, 14·12·11 문서 간 수치 불일치 금지 (일 3권·쿼터 1만·로열티 35/70%)

## 1. 목적

autostudio의 키워드 발굴·초안 자동화 파이프라인을 **유튜브 쇼츠**에 확장.
"유튜브에서 뜨는 주제 = 쇼츠 소재" 공식으로 유입·수익원 추가. **수익 구조는 "쇼츠 광고(보조) + KDP/운세 유입(주)"** — 쇼츠를 단독 수익원으로 보지 않는다.

### 1.1 시장 근거 (왜 유튜브 쇼츠인가 — 출처 있는 수치)

| 항목 | 수치 | 출처 |
|---|---|---|
| 유튜브 연간 매출 | **$600억+(2025, 광고+구독)** — 넷플릭스($451.8억)보다 큼 | [Variety 2026-02-04](https://variety.com/2026/digital/news/youtube-2025-total-revenue-ads-subscriptions-alphabet-earnings-1236652260/), [Yahoo Finance](https://finance.yahoo.com/news/youtube-annual-revenue-tops-60b-103200622.html) |
| 쇼츠 일일 조회 | **2,000억 회 (200B)** — 2024년 초 700억→2025년 중반 2,000억 (약 3배, 1년 반) | [TheWrap](https://www.thewrap.com/youtube-shorts-200-billion-daily-views/), [Demandsage](https://www.demandsage.com/youtube-shorts-statistics/), [Variety](https://variety.com/2026/digital/news/youtube-2025-total-revenue-ads-subscriptions-alphabet-earnings-1236652260/) |
| 쇼츠 월간 활성 이용자 | **20억+** | [Demandsage](https://www.demandsage.com/youtube-shorts-statistics/) |
| 한국 유튜브 MAU | **4,848만 명 (2025.11, 전년比 +3.1%)** — 한국 SNS 1위 | [조선일보/IGAWorks](https://www.chosun.com/economy/tech_it/2025/12/28/2SEJEXGW7RAN7EBRJJJ4R2NCYY/), [이투데이](https://www.etoday.co.kr/news/view/2526454) |
| 한국인 유튜브 이용 | **평균 61분/일, 쇼츠 일평균 4.3회·1회 12.8개 시청** | [오픈서베이 2025-10](https://blog.opensurvey.co.kr/article/socialmedia-2025-2/) |
| 한국 OTT 1순위 | 유튜브 **71.4%** (한국미디어패널 8,411명) | [KISDI](https://blog.naver.com/PostView.naver?blogId=kisdi_stat&logNo=224198717604) |

### 1.2 수익 모델 (쇼츠 — 광고/유입)

| 항목 | 수치 | 출처 |
|---|---|---|
| 쇼츠 RPM (크리에이터 실수익) | **$0.01~$0.07/1,000뷰** (일반), **$0.05~$0.20** (보고 범위) | [Loopex/Resourcera](https://www.loopexdigital.com/blog/youtube-shorts-statistics), [Demandsage](https://www.demandsage.com/youtube-shorts-statistics/), [Influencer Marketing Hub](https://influencermarketinghub.com/youtube-shorts-rpm/) |
| 니치별 편차 | **금융/투자/비즈니스 쇼츠 RPM = 코미디/라이프스타일의 약 10배** | [Influencer Marketing Hub](https://influencermarketinghub.com/youtube-shorts-rpm/) |
| 수익 분배 | 크리에이터 **45%** / 유튜브 55% (음악 라이선스 비용 — 롱폼과 역전) | [Stack Influence](https://stackinfluence.com/blog/youtube-shorts-monetization), [The Verge](https://www.theverge.com/2024/3/28/24114031/youtube-shorts-partner-program-ad-sharing-revenue) |
| YPP 자격 | 구독자 1,000 + (최근 12개월 4,000시간 **또는** 최근 90일 쇼츠 조회 1,000만) | [YouTube 공식](https://support.google.com/youtube/answer/72851) |
| 광고 수익 한계 | RPM $0.03 기준 월 $100 = **약 333만 뷰** 필요 (330만은 반올림 근사). 크리에이터의 **8%만 광고를 주수입원**으로 삼음 | [Demandsage](https://www.demandsage.com/youtube-shorts-statistics/), [Loopex](https://www.loopexdigital.com/blog/youtube-shorts-statistics) |

> ⚠️ **핵심 해석**: 쇼츠 광고 단독 수익성은 낮다(RPM $0.01~0.07, 45% 배분). **광고는 보조 수익** — KDP 책 유입(숏폼 노출 도서 평균 +600% 판매, [A2Z](https://a2zpublishing.com/how-booktok-can-transform-your-book-sales-a-data-driven-guide-wi))·운세 채널 유입이 실질 수익원 (R-4 수익 모델과 연계, 12-kdp §9 참조).

### 1.3 기존 문서와의 차이 (왜 유튜브 데이터인가)
- 11-fortune §9는 쇼츠를 "B2C 웹 출시 후"로 이연만 했으나, **2026-08-14 개정으로 이연 해소** — 한국어 운세 쇼츠·영어권 KDP 쇼츠 모두 이 기획 범위에 포함 (11-fortune §9 개정본 참조)
- 네이버 인기키워드(블로그 검색)는 **쇼츠 소재와 궁합이 낮음** — 쇼츠는 조회·시청 완료율이 지표이고, 주제는 유튜브 트렌드에서 나옴
- 따라서 **유튜브 인기 주제·채널·키워드 수집 → 쇼츠 소재 후보 판정** 파이프라인이 선행 필요

## 2. 데이터 소스 (유튜브)

### 2.1 YouTube Data API v3 (정식 데이터 소스 — 유일한 공식 경로)
- **무료 쿼터: 하루 10,000 units** (모든 엔드포인트 합산, 태평양 시간 자정 리셋) — [공식 쿼터 문서](https://developers.google.com/youtube/v3/determine_quota_cost)
- ⚠️ **2026년 개편**: `search.list`는 **100회/일 별도 버킷** (1회 = 1 unit) — 기존 "100 units/회" 아님
- 사용 엔드포인트:

  | 목적 | 엔드포인트 | 쿼터(units) |
  |---|---|---|
  | 인기 동영상 (국가별) | `videos?chart=mostPopular&regionCode=KR` | 1 |
  | 트렌딩 키워드 | `videos?chart=mostPopular` + 제목/태그 집계 | 1 |
  | 검색 (주제 후보·시드 확장) | `search?q={키워드}&type=video` | 1 (**100회/일 버킷**) |
  | 채널 통계 | `channels?part=statistics` | 1 |
  | 동영상 상세 | `videos?part=statistics,contentDetails` | 1 |
  | 댓글 (반응 수집) | `commentThreads?part=snippet` | 1 |
  | 자막 | `captions.list` | 50 (미사용 권장) |

- **쿼터 예산 시뮬레이션 (OQ-1: 매일 1회 기준)** — 실패 요청도 최소 1 unit 소모, 페이지네이션도 페이지당 비용 발생:
  - 인기 동영상 50개 (`videos.list` × 50) = 50 · 채널 통계 20개 = 20 · 검색 10회 = 10 · 댓글 20개 영상 = 20 → **합계 ≈ 100 units/일 = 10,000 대비 1%** (여유 충분)
- **비용**: 무료 (기본 할당 내). 초과 시 다음날 리셋 — 유료 확장 불필요 (개인용)
- **필요**: Google Cloud Console에서 YouTube Data API v3 활성화 + API 키 발급 (사용자 작업)

### 2.2 스크래핑·yt-dlp (보조·제한적 — ⚠️ ToS 리스크 명시)
- **YouTube ToS**: 자동화 수단(스크래퍼) 접근은 명시적 금지 — 사전 서면 허가 없이는 위반 ([ToS](https://www.youtube.com/static?template=terms))
- **yt-dlp 법적 이력**: 2020년 RIAA DMCA 테이크다운 → EFF 개입으로 복원 ([Wikipedia](https://en.wikipedia.org/wiki/Youtube-dl), [EFF](https://www.eff.org/deeplinks/2020/11/github-reinstates-youtube-dl-after-riaas-abuse-dmca)) — 도구 사용이 합법이어도 ToS 위반은 별개
- **운영 원칙**: ① API v3를 유일한 정식 소스로 ② yt-dlp/스크래핑은 **파일럿 보조·제한적 사용**만 (개인·비상업적·저빈도, robots.txt 준수) ③ 트렌딩 페이지 스크래핑 대신 `videos?chart=mostPopular&regionCode=KR` API 사용 (기획 초안 유지 ✅)

### 2.3 선택: 네이버 데이터 재활용 (보조)
- 기존 네이버 '곧 뜰' 키워드를 유튜브 검색 쿼리로 변환 — 교차 검증용 (유튜브 검색 결과량·채널 수)
- KDP 개선점 #4(키워드→책 주제 변환)와 동일한 '곧 뜰' 자산 공유 — 12-kdp §4 참조

## 3. 쇼츠 소재 발굴 로직

### 3.1 수집 (shorts_research.py — ~3h)
```
유튜브 인기 동영상 (KR)      → 제목·태그·설명 수집
  + 채널 통계 (구독자·총조회수)
  + 검색 (시드 키워드 확장 — 네이버 '곧 뜰' 교차)
      ↓
원본 데이터 DB 저장 (youtube_raw)   [매일 1회 배치 — OQ-1 결정]
```

### 3.2 주제 후보 판정 (shorts_topic.py — ~2h) — ⚠️ 지표 개정 (리서치 R-2 반영)

알고리즘은 **"탐색(Explore) → 활용(Exploit)" 2단계**로 동작 ([Shortimize](https://www.shortimize.com/blog/how-does-youtube-shorts-algorithm-work)) — 업로드 직후 소규모 테스트 관객 → 반응 좋으면 확대. **구독자 수·업로드 시간은 1순위 신호가 아님** (구독자 0 채널도 추천 대박 가능 = 디스커버리 머신).

| 기획 지표 (초안) | 판정 | 근거 |
|---|---|---|
| 조회수/구독자 수 (소형 채널 폭발) | ✅ 유효 | 알고리즘은 구독자 무관 추천 — 소형 채널 조회 폭발 = 디스커버리 성공 ([Shortimize](https://www.shortimize.com/blog/how-does-youtube-shorts-algorithm-work)) |
| 최근 24~48h 조회 급상승 (성장률) | ✅ 유효 | 탐색→활용 전환 신호 — 완주율/VVSA의 API 대리 지표 ([Shortimize](https://www.shortimize.com/blog/how-does-youtube-shorts-algorithm-work)) |
| 좋아요/조회수·댓글/조회수 (반응비) | ⚠️ **보조 지표로 격하** | 33억 뷰 연구: 좋아요·공유·댓글과 성과의 **강한 상관 없음** ([Medium](https://medium.com/@antoinelacombled/cracking-the-youtube-shorts-algorithm-a-study-of-3-3-billion-views-4711fdf7931b)) — "만족도 스코어" 정도로만 |
| 시청 완료율 프록시 | ⚠️ **API로 직접 측정 불가** | 완주율은 YouTube Studio 전용 — 스크립트 길이(30~45초)·후킹 품질로 간접 통제 |
| **공유율 (신규 추가)** | ⚠️ **조건부 (채널 소유 시)** | 공유/조회 **0.5%+ = 바이럴 상관** ([Conbersa](https://www.conbersa.ai/learn/youtube-shorts-analytics-guide)) — 단, API `statistics.shareCount`는 **채널 소유 시에만 제공** → 파일럿에서 채널 소유 전제 충족 시에만 핵심 지표로 승격, 그 전엔 참고 지표 |

**개정된 판정 지표 (API 수집 가능 지표 중심 — S-1 모순 해소)**: ① **조회 급상승(24~48h)** — 탐색→활용 전환 신호 (1순위) ② **조회/구독 비율(소형 채널 폭발)** — 디스커버리 성공 대리 지표 ③ **반응비(좋아요·댓글)** — 보조·만족도 참고용 (33억 뷰 연구: 상관 약함) ④ **틈새(경쟁 적음 + 수요 있음)** ⑤ **공유율(공유/조회 ≥ 0.5%)** — ⚠️ **조건부 지표: 채널 소유 시에만 API로 수집 가능** → 파일럿에서 채널 소유 전제가 확인되면 핵심 지표로 승격, 그 전엔 판정에서 제외(참고용). **완주율·VVSA는 API 미제공** — 스크립트 길이(30~45초)·후킹 품질로 간접 통제.

**스크립트 길이 근거 (리서치 R-2)**: 상위권 쇼츠 평균 완주율 **80~90%**, 50% 미만은 스킵 대상 ([Shortimize](https://www.shortimize.com/blog/how-does-youtube-shorts-algorithm-work)); VVSA 60% 미만 = 성과 나쁨, 70~90% = 좋음, **첫 1~2초에서 결정** ([Medium 33억 뷰](https://medium.com/@antoinelacombled/cracking-the-youtube-shorts-algorithm-a-study-of-3-3-billion-views-4711fdf7931b)); 50~60초 쇼츠 완주율 76%로 최고이나 20~40초가 가장 흔함 ([Loopex](https://www.loopexdigital.com/blog/youtube-shorts-statistics)) → **기획의 30~45초는 유효 범위 내 유지**.

**업로드 리듬 근거**: 평균 크리에이터 월 7개·상위권 월 18~22개, 6개월 꾸준한 업로드 → 채널 성장 +44% ([Loopex](https://www.loopexdigital.com/blog/youtube-shorts-statistics)) → 파일럿 이후 주 3~5회 목표.

- **주제 추출**: 제목·태그 TF-IDF / LLM 클러스터링 → 주제 클러스터
- **틈새 판정**: 경쟁(기존 영상 수·채널 수) 적음 + 수요(조회) 있음
- **산출**: 쇼츠 소재 후보(주제·스크립트·해시태그·참고 영상) → `shorts_scripts`

### 3.3 쇼츠 스크립트 생성 (shorts_script.py — ~3h)
- 기존 draft_pipeline 2패스 재활용 (플랫폼=shorts 포맷)
- 쇼츠 특화: 30~45초 (한국어 80~120자), **후킹 3초** (VVSA 첫 1~2초 결정 근거), CTA(구독/시리즈)
- 검수: 금지어·허위 주장·길이·후킹 존재
- **음성/자막**: **edge-tts 채택 (OQ-4 결정)** — 오픈소스·무료, 운세 카드 쇼츠(자막+간단 음성)에 적합. 자막 텍스트만 산출(수동 녹음)도 지원
  - ⚠️ **S-4 라이선스 주의**: edge-tts는 **비공식 API(Microsoft Edge 서버 활용)** — 상업 쇼츠 음성 사용 시 MS 약관 위반 소지 있음. **파일럿 전 검토 항목**: ① 상업 이용 가능성 확인 ② 대체재 검토 — **Piper**(오픈소스·로컬 추론, 한국어 모델 존재), **Kokoro**(오픈소스 TTS), 기타 오픈소스 TTS(Coqui 등) ③ 목소리 저작권·품질 비교 후 edge-tts 유지/교체 결정
  - 파일럿 전 게이트: **TTS 라이선스·품질 검증 통과 후 edge-tts 확정** (실패 시 Piper/Kokoro 폴백)

## 4. 데이터 모델

```sql
youtube_raw       id · video_id · title · tags(JSON) · description · channel_id ·
                  channel_title · published_at · view_count · like_count · comment_count ·
                  share_count? · region · fetched_at · UNIQUE(video_id)
shorts_scripts    id · topic · hook · script_md · hashtags(JSON) · ref_video_ids(JSON) ·
                  status(draft/ready/published) · created_at · updated_at
shorts_topics     id · label · score · evidence(JSON) · status · created_at
```

- 기존 SQLite/Postgres 이중 SQL 패턴 재사용 (`db.py` 확장)
- `youtube_raw`는 수집 원본(재수집 멱등 — video_id UNIQUE), `shorts_*`는 산출물
- **공유율 산출 (조건부)**: `youtube_raw`에 `share_count` 컬럼 **예약** — API `statistics.shareCount`는 **채널 소유 시에만 제공**되므로, 파일럿 전 채널 소유 전제가 충족될 때만 수집·판정에 사용. 비소유 시 컬럼은 NULL 유지(수집 생략) — 공유율은 **조건부 지표**로만 동작 (S-1)

## 5. 배치/발행

| 단계 | 방식 |
|---|---|
| 수집 | GH Actions 배치 (**매일 1회 — OQ-1 결정**, 쿼터 1% ≈ 100 units, 10,000 내) |
| 스크립트 생성 | GH Actions 또는 사용자 트리거 (LLM 호출) |
| **쇼츠 제작·업로드** | **수동** — 자동 업로드는 정책 리스크 (KDP와 동일 원칙). 스크립트+해시태그+참고영상 제공, 영상 편집(Shotcut/CapCut)은 사용자 |
| 성과 추적 | 대시보드 탭 (조회·구독·완주율·수익 입력 — 수동, 측정 경로 §5.1) |

### 5.1 성과 측정 경로 (S-2 — 채널 소유 전제 명시)

| 지표 | 측정 경로 | 파일럿 전(비소유) | 파일럿 후(채널 소유 시) |
|---|---|---|---|
| 조회수·구독자·좋아요·댓글 | **API v3** (`videos.list`·`channels.list`) | ✅ 수집 가능 | ✅ |
| 공유 수 | **API v3** (`statistics.shareCount`) | ❌ **채널 소유 시에만** — 수집 생략, 참고 지표 | ✅ 핵심 지표로 승격 |
| 완주율·VVSA(본/스와이프) | **YouTube Studio 전용** | ❌ 미측정 — 스크립트 길이·후킹으로 간접 통제 | ✅ Studio 수동 입력 |
| 수익(RPM·광고) | **YouTube Studio** (YPP 가입 후) | ❌ 수동 추정 | ✅ Studio 수동 입력 |
| KDP 전환(아마존 유입·판매) | 아마존 KDP 리포트 (수동 입력) | ✅ 수동 | ✅ |

> **파일럿 전 게이트**: 채널 소유 여부 확인 → 소유 시 공유율·완주율·수익 지표를 성과 평가에 포함, 비소유 시엔 **조회·구독·반응비(API 지표) + 수동 KDP 전환**만으로 판정 (S-2).

### 채널 전략 (OQ-5 결정: 분리 권장)
| 채널 | 대상 | 주제 | 비고 |
|---|---|---|---|
| 운세 쇼츠 채널 (한국어) | 한국어 시청자 | 오늘의 운세 카드(띠·별자리)·일주 | 결정적 엔진 기반 — AI 환상 아님 명시 (11-fortune §9 연계) |
| KDP 쇼츠 채널 (영어권) | 영어권 독자 | 책 챕터→쇼츠→아마존 링크 | 12-kdp §9 시너지 (숏폼 노출 도서 평균 +600% 판매 근거) |
| 일반 트렌드 채널 (한국어) | 한국어 시청자 | 트렌드·잡지식 | 파일럿에서 검증 후 병합/분리 판단 |

> 알고리즘 **주제 일관성** 관점에서 채널 분리 권장 — 단, 파일럿 단계(운세4+KDP3+일반3)에서는 운영 부담 고려해 최소 2채널(한국어/영어)로 시작, 성과 후 세분화.

## 6. 실행 순서

1. **S-1** DB 스키마 + `shorts_research.py` (유튜브 수집 — API 연동, 매일 1회 배치) — ~3h
2. **S-2** `shorts_topic.py` (주제 판정·틈새 스코어 — 개정 지표: 조회급상승·조회/구독·반응비(보조)·틈새, 공유율은 채널 소유 시 조건부) — ~2h
3. **S-3** `shorts_script.py` (스크립트 생성 + 검수 + edge-tts 음성) — ~3h
4. **S-4** 배치 + 대시보드 탭 (소재 목록·스크립트 보기/복사) — ~3h
5. **파일럿**: 소재 후보 10개 → 5개 쇼츠 제작 → 반응 확인

### 파일럿 주제 (OQ-2 결정 — 리서치 R-1·R-6·R-7 반영, 10개 소재)

| 후보 | 근거 (리서치) | 우선순위 |
|---|---|---|
| **오늘의 운세 (띠·별자리 카드)** — 4개 | 한국 점술 시장 **1.4조 원**, MZ **91.6%** 경험, 유튜브 운세 채널 **4,000개+** (수요 검증), 결정적 엔진 차별화, 일일 갱신 = 업로드 리듬 확보 ([크리스천헤럴드](https://www.cheraldus.com/bbs/board.php?bo_table=korean_news&wr_id=109), [브릿지경제](https://www.viva100.com/article/20250227501106), [중앙일보](https://www.joongang.co.kr/article/25329791)) | 🥇 |
| **KDP 책 챕터 홍보 (영어권)** — 3개 | 숏폼→책 판매 **+600%** 사례, 유럽 #BookTok **5,000만 권·€8억**, 시리즈 확장성 ([A2Z](https://a2zpublishing.com/how-booktok-can-transform-your-book-sales-a-data-driven-guide-wi), [TikTok Newsroom](https://newsroom.tiktok.com/booktok-community-50-million-books?lang=en-150)) | 🥈 |
| **일반 트렌드/잡지식 (한국어)** — 3개 | 쇼츠 디스커버리 특성, 50~60초 완주율 76%, 금융 니치 RPM 10배 ([Loopex](https://www.loopexdigital.com/blog/youtube-shorts-statistics), [Influencer Marketing Hub](https://influencermarketinghub.com/youtube-shorts-rpm/)) | 3 |

**파일럿 선정 기준 (리서치 반영)**: ① 수요 검증(검색·채널 존재) ② 자동화 궁합(스크립트화 용이) ③ 수익 경로 존재(광고/책/유입) ④ 업로드 리듬 지속 가능성 ⑤ 차별화(경쟁 대비).

### 파일럿 성공/실패 기준 (S-3 — exit criteria)

**쇼츠 파일럿 (5개 쇼츠, 30일 평가)**: 리서치 수치(완주율 80~90% 상위권·VVSA 70~90% 좋음) 기반

| 기준 | 성공 | 실패 | 측정 경로 |
|---|---|---|---|
| 30일 누적 조회 | **1만+** | < 3,000 | API v3 |
| 평균 완주율 (채널 소유 시) | **70%+** | < 50% (스킵 대상 수준) | Studio (S-2 §5.1) |
| 평균 VVSA (채널 소유 시) | **70~90%** | < 60% | Studio |
| 구독 전환 | 5개 쇼츠 후 구독자 +50 이상 | +10 미만 | API v3 |
| 공유율 (채널 소유 시) | ≥ 0.5% 쇼츠 2개+ | 0건 | API v3/Studio |

> **판정**: 30일 후 상기 기준으로 **성공 → 시리즈 확장**(검증 주제 2~3개) / **부분 성공 → 지표별 원인 분석 후 재파일럿** / **실패 → 주제·포맷 재선정** (OQ-2 비중 재조정).

**KDP 파일럿 (52주 워크북 1권, 90일 평가)**: 손익분기(§1.2 — 월 $100 = 14권, 90일 = 42권) 기반

| 기준 | 성공 | 실패 | 측정 경로 |
|---|---|---|---|
| 90일 누적 판매 | **50권+** | < 15권 | KDP 리포트 (수동 입력) |
| 월 판매 추세 | 상승·유지 (2개월 연속) | 2개월 연속 하락 | KDP 리포트 |
| 리뷰 | 5개+ (평균 4.0+) | 리뷰 0건 + 판매 저조 | KDP |
| KDP↔쇼츠 유입 | 시너지 쇼츠 노출 후 방문·판매 추적 | 유입 0 | 아마존 리포트 |

> **판정**: 90일 후 **성공 → 시리즈 확장**(100일·분기 변형) / **실패 → 주제 재선정**(K-1 스냅샷 재실행) — 12-kdp §7 파일럿 게이트와 연동.

### 시리즈 전략 (KDP와 동일 원칙)
- 검증된 주제 → 시리즈화 (KDP 시리즈 확장 공식 재활용, 12-kdp §7 참조)
- 운세 엔진 자산 연계: "오늘의 운세 쇼츠" (별자리·띠별 30초 카드) — 11-fortune §9 한국어 운세 쇼츠와 연결
- KDP 연계: 책 챕터 핵심 팁 1개 = 쇼츠 대본 → CTA "Full chapter in my book on Amazon" → 아마존 링크 (12-kdp §9)

## 7. 리스크

| 리스크 | 완화 |
|---|---|
| YouTube API 쿼터 소진 | 하루 1만 쿼터 — 매일 1회 배치 ≈ 100 units (1%), 여유 충분. `search.list` 100회/일 버킷 별도 관리 |
| API 키 비용/한도 | 무료 티어 1만/일 — 초과 시 다음날 자연 리셋 |
| HTML 스크래핑 ToS 위반 | **API v3 우선 원칙** — 스크래핑은 파일럿 보조·제한적 (개인·비상업적·저빈도, robots.txt 준수) |
| 자동 업로드 정책 | 수동 업로드 유지 (KDP 원칙 공유) |
| 주제 판정 품질 | 개정 지표(조회급상승·조회/구독·틈새 — API 수집 가능) + 반응비 보조 이중 판정. 공유율은 **채널 소유 시에만** 조건부 승격 (리서치 R-2·S-1) |
| 쇼츠 광고 수익 미미 | 광고=보조 인식 — KDP/운세 유입을 실질 수익원으로 (수익 모델 §1.2) |
| 운세 콘텐츠 규제 | "오락·참고용" 프레이밍, 적중률 보장 표현 금지, 결정적 엔진 명시 (11-fortune §9 참조) |
| 완주율 직접 측정 불가 | 스크립트 길이(30~45초)+후킹 품질로 간접 통제 — 채널 소유 시 Studio 데이터로 보정 |
| edge-tts 상업 이용 라이선스 (비공식 API) | 파일럿 전 대체재 검토(Piper·Kokoro) — 실패 시 교체, 자막 텍스트만으로도 운영 가능 (S-4) |

## 8. 사용자 필요 조치

1. **Google Cloud Console에서 YouTube Data API v3 활성화 + API 키 발급** → `.env.local`에 `YOUTUBE_API_KEY` 추가
2. **채널 구분 결정**: 운세(한국어) / KDP(영어) 채널 분리 시 신규 채널 생성 (파일럿 전)
3. (선택) 쇼츠 제작 도구 — Shotcut/CapCut 등 (자동화 아님)
4. (파일럿 전) **TTS 검증**: edge-tts 한국어 음성 품질 청취 + **상업 이용 라이선스 확인** (비공식 API — 대체재 Piper/Kokoro 검토, S-4)

---

*작성: 기획팀 · 상태: 리서치 반영 고도화 (2026-08-14) — 승인 후 S-1~S-4 진행 · 상호 참조: 12-kdp-pipeline.md §9(시너지)·11-fortune-channel.md §9(운세 쇼츠 이연 해소)*
