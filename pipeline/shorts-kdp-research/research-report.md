# 쇼츠 + KDP 파이프라인 리서치 보고서

> **작성**: 리서치팀 · **프로젝트**: autostudio · **작업 디렉토리**: `pipeline/shorts-kdp-research/`
> **작성일**: 2026-08-14 · **대상**: `docs/planning/14-shorts-pipeline.md` · `docs/planning/12-kdp-pipeline.md` · `docs/planning/11-fortune-channel.md` §9
> **조사 지시**: requirements.md §11 (R-1~R-7) · **1차 출처 우선 원칙 적용** (YouTube 공식 문서, 아마존 KDP Help, 정부/공공 통계)

---

## 1. 요약 (TL;DR)

| 조사 주제 | 핵심 발견 | 기획 반영 시사점 |
|---|---|---|
| R-1 쇼츠 시장 | 유튜브 2025년 매출 **$600억+** (광고+구독, Alphabet 최초 공개), 쇼츠 일일 조회 **2,000억 회**, 쇼츠 RPM **$0.01~0.20** (니치 따라 10배 편차) | "쇼츠=조회수 폭발 + 수익은 보조" — **광고 수익 단독 의존은 위험**, KDP/운세 유입 경로가 실질 수익원 |
| R-2 알고리즘 | **시청 완료율·VVSA(Viewed vs Swiped Away)가 1순위 신호** — 좋아요/댓글은 상관 약함 (33억 뷰 연구), 상위권 80~90% 완주율, 60% 미만은 실패 | 기획의 "반응비" 지표는 **보조 지표로 격하** 필요, 완주율 기반 스크립트(30~45초) 설계 근거 확보 |
| R-3 API 정책 | Data API v3 기본 쿼터 **10,000 units/일** (2026년 개편: `search.list` 100회/일 별도 버킷), 무료. **yt-dlp·스크래핑은 ToS 위반** (2020 RIAA DMCA 선례) | API 우선 전략 **정당화**, 스크래핑은 "보조·제한적"으로 명시, 쿼터 예산 계산표 필요 |
| R-4 KDP 시장 | 미국 셀프퍼블리싱 시장 **$36억(2025)→$57억(2033, CAGR 5.7%)**, 전자책 로열티 35%/70%, **70% 구간 $2.99~$12.99로 확대 (2026-07-07 시행)**, 종이책 로열티 60%→50% 인하(2025) | 70% 로열티 구간 확대 = **가격 전략 폭 확대** — $9.99~$12.99 프리미엄 구간 가능 |
| R-5 KDP 정책 | 타이틀 생성 한도: 공식 Help **"포맷별 주 10권"**, 2023년 9월 AI 대응으로 **"일 3권"** 제한 도입 (가디언·KDP 포럼 확인) — **둘 다 실존** | "일 3권" 게이트 **유지 타당** (보수적 상한), AI 생성 콘텐츠 **의무 공개** (AI-assisted는 면제) |
| R-6 책 홍보 쇼츠 | BookTok/숏폼이 책 판매를 **600%까지 끌어올린 사례** (It Ends with Us), 캐나다 백리스트 20종 **1,047% 매출 증가**, 유럽 #BookTok **5천만 권 판매·€8억** (2025) | "챕터→쇼츠→아마존 링크" 시너지의 **수치 근거 확보**, 숏폼 = 논픽션/워크북에 특히 유효 |
| R-7 운세 쇼츠 | 한국 점술 시장 **1.4조 원**, MZ 91.6%가 운세 경험, 유튜브 운세 채널 **4,000개+** (플레이보드), 디지털 운세 플랫폼 연매출 수백억 | 운세 쇼츠는 **경쟁 치열하나 수요 폭발적** — 결정적 계산 엔진(차별점) + 시리즈 전략으로 승부 |

---

## 2. 방법론

### 2.1 조사 범위 및 접근

- **1차 출처 우선**: YouTube 공식 문서(Data API 쿼터, YPP 자격, ToS), 아마존 KDP Help(로열티·가격·콘텐츠 가이드라인·파일 형식), KDP 커뮤니티 공지, 정부/공공기관(방송통신광고비 조사, 한국미디어패널), Alphabet 실적 발표( Variety / Yahoo Finance 인용)
- **2차 출처 보조**: 신뢰성 있는 산업 분석(Statista류: Grand View Research, Demandsage, Influencer Marketing Hub, Shortimize), 언론(중앙일보·이투데이·조선일보·가디언·EFF)
- **교차 검증**: 핵심 수치는 2개 이상 출처로 교차 확인 (예: 쇼츠 일일 조회 2,000억 = Variety + Demandsage + TheWrap; KDP 일 3권 = 가디언 + KDP 포럼 + 레딧)

### 2.2 도구

- **Firecrawl API** (research-tools 스킬, .env 키) — 웹 검색 + 페이지 스크레이프 (JS 렌더링 대응)
- **직접 HTTP 스크레이프** — KDP Help 페이지 (정적 HTML 파싱)
- **GitHub API** — DMCA 기록 검증
- 웹 검색(Serper)은 **API 키 미설정으로 사용 불가** → research-tools의 fallback 체인으로 대체

### 2.3 한계

- 유튜브·아마존의 비공개 내부 데이터(실제 RPM, 판매량)는 추정치 기반 — **신뢰도 평가 섹션(§7)에 등급 명시**
- 한국 쇼츠 전용 시장 규모(원화) 공식 통계는 미존재 → **글로벌 수치 + 한국 MAU/이용률로 간접 추정**
- 아마존 검색량·판매량은 공개 API 부재 → 기획 단계에서 "경쟁도 스냅샷" 방식 유지

---

## 3. 주요 발견 (주제별 상세)

## R-1. 유튜브 쇼츠 시장 규모·성장률·광고 수익화 (한국·글로벌)

### 3.1 글로벌: 유튜브 플랫폼 규모

- **유튜브 2025년 연간 매출 $600억+** — 광고+구독 합산, Alphabet이 최초로 유튜브 총매출을 공개 ([Variety, 2026-02-04](https://variety.com/2026/digital/news/youtube-2025-total-revenue-ads-subscriptions-alphabet-earnings-1236652260/), [Yahoo Finance/Marketing Dive, 2026-02-05](https://finance.yahoo.com/news/youtube-annual-revenue-tops-60b-103200622.html))
  - 넷플릭스($451.8억)보다 큼, 디즈니($957억) 다음
  - **Q4 2025 광고 매출 $113.8억, 전년比 +8.7%** ([Variety](https://variety.com/2026/digital/news/youtube-2025-total-revenue-ads-subscriptions-alphabet-earnings-1236652260/))
  - Alphabet 총매출 $4,030억 (2025, 사상 최초 $4,000억 돌파)
- **유튜브 쇼츠 일일 조회 2,000억 회 (200 billion)** — 닐 모한 CEO 발표 ([TheWrap](https://www.thewrap.com/youtube-shorts-200-billion-daily-views/), [Demandsage](https://www.demandsage.com/youtube-shorts-statistics/), [Variety](https://variety.com/2026/digital/news/youtube-2025-total-revenue-ads-subscriptions-alphabet-earnings-1236652260/))
  - 2024년 초 700억 회 → 2025년 중반 2,000억 회 (약 3배 성장, 1년 반)
- **쇼츠 월간 활성 이용자 20억+** ([Demandsage](https://www.demandsage.com/youtube-shorts-statistics/), [Loopex](https://www.loopexdigital.com/blog/youtube-shorts-statistics))
- **쇼츠 광고가 유튜브 전체 광고 매출의 약 22%** (2025, shno 검색 스니펫 — 단일 출처, 신뢰도 ⚠️)

### 3.2 쇼츠 광고 수익화 (RPM/CPM)

| 항목 | 수치 | 출처 |
|---|---|---|
| 쇼츠 RPM (크리에이터 실수익) | **$0.01~$0.07/1,000뷰** (일반), **$0.05~$0.20** (보고 범위) | [Resourcera via Loopex](https://www.loopexdigital.com/blog/youtube-shorts-statistics), [Demandsage](https://www.demandsage.com/youtube-shorts-statistics), [Influencer Marketing Hub](https://influencermarketinghub.com/youtube-shorts-rpm/) |
| "높은" 쇼츠 RPM | ~$0.15 (강한 니치), 일부 $5+ 보고 (이례적) | [Influencer Marketing Hub](https://influencermarketinghub.com/youtube-shorts-rpm/) |
| 수익 분배 | 크리에이터 **45%**, 유튜브 55% (롱폼과 역전) — 음악 라이선스 비용 때문 | [The Verge via Stack Influence](https://www.theverge.com/2024/3/28/24114031/youtube-shorts-partner-program-ad-sharing-revenue), [Stack Influence](https://stackinfluence.com/blog/youtube-shorts-monetization) |
| 수익 풀링 구조 | 쇼츠 피드 광고를 **전체 풀링 → 조회 기여도 배분 → 45%** | [Stack Influence](https://stackinfluence.com/blog/youtube-shorts-monetization) |
| 니치별 편차 | **금융/투자/비즈니스 쇼츠 RPM이 코미디/라이프스타일보다 10배** | [Influencer Marketing Hub](https://influencermarketinghub.com/youtube-shorts-rpm/) |
| YPP 자격 | 구독자 1,000 + (최근 12개월 시청 4,000시간 **또는** 최근 90일 쇼츠 조회 1,000만) | [YouTube 공식](https://support.google.com/youtube/answer/72851) |
| 광고 수익만으로 $100 | RPM $0.03 기준 **330만 뷰 필요** | [Demandsage](https://www.demandsage.com/youtube-shorts-statistics/) |

> **⚠️ 핵심 해석**: 쇼츠 광고 단독으로는 수익성이 낮다. 광고 외 수익화(브랜드·제휴·상품·**책 판매 유입**)가 주수익원. 크리에이터의 **8%만 광고를 주수입원**으로 삼음 ([Loopex](https://www.loopexdigital.com/blog/youtube-shorts-statistics)).

### 3.3 한국: 유튜브 이용 현황

- **한국 유튜브 MAU 4,848만 명 (2025년 11월)** — 한국 SNS 1위, 전년比 +3.1% ([조선일보/IGAWorks MobileIndex, 2025-12-28](https://www.chosun.com/economy/tech_it/2025/12/28/2SEJEXGW7RAN7EBRJJJ4R2NCYY/))
  - 2024년 10월 4,623만 → 2025년 10월 4,862만 (**+238만 명**, [이투데이](https://www.etoday.co.kr/news/view/2526454))
  - 카카오톡(4,646만)·인스타그램(2,468만)보다 많음
- **OTT 1순위 이용 서비스: 유튜브 71.4%** (2025 한국미디어패널조사, 8,411명) ([KISDI](https://blog.naver.com/PostView.naver?blogId=kisdi_stat&logNo=224198717604))
- **한국인 평균 유튜브 이용시간 61분/일**, 쇼츠 일평균 4.3회·1회 12.8개 시청 ([오픈서베이, 2025-10](https://blog.opensurvey.co.kr/article/socialmedia-2025-2/))
- **쇼츠가 신규 이용자 유입 장벽을 낮춤** — 짧은 영상 → 롱폼 전환 → 체류시간 증가 ([이투데이](https://www.etoday.co.kr/news/view/2526454))
- 한국인 유튜버 '김프로(KIMPRO)'가 2025년 글로벌 연간 조회수 1위 (775억 회, 구독자 1억+) — 쇼츠 중심 전략의 실증 사례 ([네이버 블로그 집계](https://blog.naver.com/PostView.naver?blogId=skyu0021&logNo=224149769875), ⚠️ 2차 출처)

### 3.4 한국 광고 시장 (쇼츠 광고 지출 배경)

- **2024년 국내 방송통신광고비 17.1조 원**, 온라인 광고비 **10.1조 원 (59%)** — 방송(3.2조, 18.8%) 추월 ([방송미디어통신위원회·KOBACO '2025년 방송통신광고비 조사' via 한국기자협회](https://www.journalist.or.kr/news/article.html?no=60072))
- 2025년 온라인 광고비 전망 **10.7조 원 (+6.1%)**
- 모바일 광고비 7.8조 원 (전체 온라인의 77%)

---

## R-2. 유튜브 쇼츠 알고리즘·트렌드 판정 지표 근거

### 3.5 알고리즘 동작 원리 (2단계 테스트)

쇼츠는 **"탐색(Explore) → 활용(Exploit)" 2단계**로 동작 ([Shortimize](https://www.shortimize.com/blog/how-does-youtube-shorts-algorithm-work)):

1. **탐색**: 업로드 직후 수백~수천 명의 소규모 테스트 관객에게 노출 → 시청 반응 측정
2. **활용**: 반응이 좋으면 더 큰 관객 풀로 확대. 나쁘면 조회 정체

> **구독자 수·업로드 시간은 1순위 신호가 아님.** 구독자 0 채널도 알고리즘 추천으로 대박 가능 — 쇼츠는 "디스커버리 머신".

### 3.6 판정 지표 근거 (기획의 조회/구독·성장률·반응비 검증)

**① 시청 완료율·시청 지속 시간 (1순위 — "This Is Everything")** ([Shortimize](https://www.shortimize.com/blog/how-does-youtube-shorts-algorithm-work), [Shortsninja](https://shortsninja.com/blog/top-5-metrics-for-youtube-shorts-growth/))

- 완주율이 원시 시청 시간보다 중요: 30초 영상 25초 시청(83%) = 최상, 60초 영상 20초(33%) = 실패
- **상위권 쇼츠 평균 완주율 80~90%**, 50% 미만이면 "스킵 대상" 취급
- 리플레이(반복 시청)·루프 시청도 강한 신호

**② VVSA (Viewed vs Swiped Away, 본 vs 스와이프)** ([Medium 33억 뷰 연구](https://medium.com/@antoinelacombled/cracking-the-youtube-shorts-algorithm-a-study-of-3-3-billion-views-4711fdf7931b), [Conbersa](https://www.conbersa.ai/learn/youtube-shorts-analytics-guide), [Shortimize](https://www.shortimize.com/blog/how-does-youtube-shorts-algorithm-work))

- **60% 미만 = 성과 나쁨, 70~90% = 좋은 성과** (33억 뷰 데이터)
- 첫 1~2초에서 결정 — **후킹의 중요성 입증**
- Tubular 2025 리포트: 스와이프 30% 미만 쇼츠가 50% 초과 쇼츠보다 **지속 배포 4배** ([Conbersa](https://www.conbersa.ai/learn/youtube-shorts-analytics-guide))

**③ 반응 지표 (좋아요/댓글/공유) — ⚠️ 기획의 "반응비"는 보조 지표로 격하 필요**

- **33억 뷰 연구: 좋아요·공유·댓글과 성과의 강한 상관관계 없음** ([Medium](https://medium.com/@antoinelacombled/cracking-the-youtube-shorts-algorithm-a-study-of-3-3-billion-views-4711fdf7931b))
  - "이 지표들은 YouTube 만족도 스코어링에 여전히 쓰일 수 있으나 추가 검증 필요"
- 공유율은 예외: 공유/조회 0.5% 이상이면 바이럴 상관 높음 ([Conbersa](https://www.conbersa.ai/learn/youtube-shorts-analytics-guide))
- 댓글/조회수는 깊은 관여의 신호로 참고 가능 ([Conbersa](https://www.conbersa.ai/learn/youtube-shorts-analytics-guide))

**④ 구독 전환 (기획의 "구독·성장률" 근거)** ([Medium](https://medium.com/@antoinelacombled/cracking-the-youtube-shorts-algorithm-a-study-of-3-3-billion-views-4711fdf7931b), [Conbersa](https://www.conbersa.ai/learn/youtube-shorts-analytics-guide))

- 롱폼이 1만 뷰당 구독 전환은 높으나, **구독자 100만+ 채널은 쇼츠 전환이 더 좋음** (CTA 품질 때문)
- "쇼츠에서 구독자 500k 뷰로 1,000명 vs 같은 뷰로 200명" — **구독 전환율이 단순 조회수보다 중요한 KPI**
- 리턴 뷰어(재방문) 비율 상승 = 실제 구독 성장 신호

**⑤ 업로드 빈도·콘텐츠 길이** ([Loopex](https://www.loopexdigital.com/blog/youtube-shorts-statistics), [Medium](https://medium.com/@antoinelacombled/cracking-the-youtube-shorts-algorithm-a-study-of-3-3-billion-views-4711fdf7931b))

- 평균 크리에이터 월 7개, 상위권은 월 18~22개
- 6개월 꾸준한 업로드 → 채널 성장 +44%
- 50~60초 쇼츠가 시청 완주율 76%로 최고 (단, 20~40초가 가장 흔함) — **기획의 30~45초는 유효 범위 내**

### 3.7 기획 지표 설계 권고

| 기획 지표 (14-shorts 초안) | 판정 | 근거 |
|---|---|---|
| 조회수/구독자 수 (소형 채널 폭발) | ✅ 유효 | 알고리즘은 구독자 무관 추천 — 소형 채널의 조회 폭발 = 디스커버리 성공 |
| 최근 24~48h 조회 급상승 (성장률) | ✅ 유효 | 테스트 단계 → 활용 단계 전환 신호 |
| 좋아요/조회수, 댓글/조회수 (반응비) | ⚠️ **보조로 격하** | 33억 뷰 연구에서 상관 약함 — "만족도 스코어" 정도로만 |
| 시청 완료율 프록시 | ⚠️ **API로 직접 측정 불가** — 완주율은 YouTube Studio 전용 | 대안: 조회수 대비 급상승 + 공유율 + (가능 시) 채널 소유 시 Studio 데이터 |
| **공유율 (추가 권장)** | ✅ 추가 | 공유/조회 0.5%+ = 바이럴 상관 ([Conbersa](https://www.conbersa.ai/learn/youtube-shorts-analytics-guide)) |

> **결론**: API로 수집 가능한 지표(조회·좋아요·댓글·공유·채널 통계) 중에서 **조회 급상승 + 공유율 + 조회/구독 비율**이 알고리즘 추천 확률을 가장 잘 대리한다. 완주율은 API로 못 얻으므로 **스크립트 길이(30~45초)와 후킹 품질로 간접 통제**.

---

## R-3. YouTube Data API v3 쿼터·엔드포인트·비용·대안 정책

### 3.8 공식 쿼터 체계 (2026-06 기준, [공식 문서](https://developers.google.com/youtube/v3/determine_quota_cost))

**기본 할당 (일일, 태평양 시간 자정 리셋):**

| 항목 | 쿼터 | 비고 |
|---|---|---|
| **전체 기본 쿼터** | **10,000 units/일** | 모든 엔드포인트 합산 |
| `search.list` | **100회/일** (별도 버킷, 1회 = 1 unit) | ⚠️ 2026년 개편 — **기존 "100 units/회" 아님** |
| `videos.insert` | 100회/일 (별도 버킷) | 업로드 전용 |

**주요 엔드포인트 쿼터 비용 ([공식 테이블](https://developers.google.com/youtube/v3/determine_quota_cost)):**

| 엔드포인트 | 비용 (units) | 기획 사용처 |
|---|---|---|
| `videos.list` | 1 | 인기 동영상·통계 |
| `channels.list` | 1 | 채널 구독자·총조회수 |
| `commentThreads.list` | 1 | 댓글 수집 |
| `search.list` | 1 (100회/일 한도) | 키워드 검색 |
| `playlistItems.list` | 1 | 플레이리스트 수집 |
| `captions.list` | 50 | 자막 (미사용 권장) |

> **중요**: 모든 요청은 **실패해도 최소 1 unit** 소모. 페이지네이션도 페이지당 비용 발생.

### 3.9 비용

- **무료** (기본 할당 내). 초과 시 다음 날 자정 리셋
- 유료 확장: 추가 할당은 Google Cloud 프로젝트 승인 필요 (보통 개인 사용엔 불필요)
- **기획 예산 시뮬레이션** (일일):
  - 인기 동영상 50개 (`videos.list` × 50) = 50 units
  - 채널 통계 20개 (`channels.list` × 20) = 20 units
  - 검색 10회 (`search.list` × 10) = 10 units
  - 댓글 20개 영상 (`commentThreads.list` × 20) = 20 units
  - **합계 ≈ 100 units/일** → 10,000 units 대비 **1%만 사용** — 여유 충분

### 3.10 대안 정책·리스크 (yt-dlp·스크래핑)

**⚠️ YouTube ToS (공식, [링크](https://www.youtube.com/static?template=terms)):**

> "03. access the Service using any automated means (such as robots, botnets or scrapers) except (a) in the case of public search engines, in accordance with YouTube's robots.txt file; or (b) with YouTube's prior written permission"

- **자동화 수단(스크래퍼) 접근은 명시적 금지** — 사전 서면 허가 없이는 위반
- 즉, **HTML 스크래핑·yt-dlp 무분별 사용은 ToS 위반** 리스크

**yt-dlp 법적 이력:**

- 2020년 10월 **RIAA DMCA 테이크다운**으로 youtube-dl GitHub 레포 삭제 → EFF 개입으로 11월 복원 ([Wikipedia](https://en.wikipedia.org/wiki/Youtube-dl), [EFF](https://www.eff.org/deeplinks/2020/11/github-reinstates-youtube-dl-after-riaas-abuse-dmca))
- 복원 후에도 "Section 1201 안티서큠벤션" 논란 지속 — **도구 사용 자체가 합법이어도 YouTube ToS 위반은 별개**
- GitHub의 dmca 레포에서 yt-dlp 관련 신규 테이크다운(2024~2026)은 확인되지 않음 (GitHub API 실측) — 다만 **리포/포크가 항상 노출 리스크**

**권고 (기획 반영):**

1. **API v3를 유일한 정식 데이터 소스로** — 무료·공식·안정
2. yt-dlp/스크래핑은 **파일럿 보조·제한적 사용**으로만, ToS 위반 리스크를 문서에 명시
3. 스크래핑 시 **개인·비상업적·저빈도** 원칙, robots.txt 준수
4. 트렌딩 페이지 스크래핑 대신 **`videos?chart=mostPopular&regionCode=KR` API 사용** (1 unit) — 기획 초안에 이미 있음 ✅

---

## R-4. KDP 전자책 시장: 규모·카테고리 성과·수익 모델

### 3.11 시장 규모

- **미국 셀프퍼블리싱 시장 $36억 (2025) → $57억 (2033), CAGR 5.7%** ([Grand View Research](https://www.grandviewresearch.com/industry-analysis/us-self-publishing-market-report))
- 미국 ISBN 발행 도서 2025년 +32.5% (Bowker), **셀프퍼블리싱 350만+ 종/년 (2024)** ([ISBNdb](https://isbndb.com/blog/self-publishing-is-changing-the-book-industry/))
- 글로벌 셀프퍼블리싱 시장 $18.5억(2024) → $61.6억(2033) 전망 ([ISBNdb 인용](https://isbndb.com/blog/self-publishing-is-changing-the-book-industry/))
- **미국 전자책 시장 = 글로벌 $506억 전자책 시장의 약 33%** (2025) ([Fortune Business Insights via ISBNdb](https://isbndb.com/blog/self-publishing-is-changing-the-book-industry/))
- 셀프퍼블리싱 작가의 **98%가 전자책, 83%가 아마존을 주 플랫폼**으로 사용 ([ISBNdb](https://isbndb.com/blog/self-publishing-is-changing-the-book-industry/))

### 3.12 카테고리 성과 (기획의 "구조화 비소설" 검증)

- 미국 셀프퍼블리싱에서 **픽션이 매출 1위** (로맨스·판타지·스릴러·SF) ([Grand View Research](https://www.grandviewresearch.com/industry-analysis/us-self-publishing-market-report))
- 그러나 **자동화 궁합·AI 적합성은 논픽션(워크북/가이드)이 최고** — 기존 KDP 문서(2026-08-10 실측: Kindle 베스트셀러의 소설 편중)와 일치
- 셀프헬프/워크북은 Amazon 베스트셀러 카테고리로 수요 지속 ([Amazon Best Sellers Self-Help](https://www.amazon.com/Best-Sellers-Self-Help/zgbs/books/4736))

### 3.13 수익 모델: 로열티 35%/70% (공식, [KDP eBook Royalties](https://kdp.amazon.com/help/topic/G200644210))

| 옵션 | 로열티 | 조건 | 예시 |
|---|---|---|---|
| **35%** | 리스트 가격의 35% (VAT 제외) | 최소 $0.99 (파일 크기별 $1.99/$2.99) | $0.99 × 35% = **$0.35** |
| **70%** | 리스트 가격의 70% − 전송비(평균 $0.06/권) | **$2.99~$12.99** (2026-07-07 확대, 기존 $2.99~$9.99) | $9.99 × 70% − $0.06 = **$6.93** |

**⚠️ 2026년 7월 7일 변경 — 70% 로열티 가격 구간 $2.99~$12.99로 확대** ([KDP 공식](https://kdp.amazon.com/help/topic/G200634560))

- 종전 $9.99 상한 → $12.99까지 70% 적용 가능
- **프리미엄 가격 전략의 여지 확대** (워크북 $11.99~$12.99 가능)

**손익분기 계산 (전자책, 70% 로열티 기준):**

| 가격 | 로열티/권 | 손익분기 (월 $1,000) | 손익분기 (월 $100) |
|---|---|---|---|
| $2.99 | $2.03 | 493권/월 | 49권/월 |
| $4.99 | $3.43 | 292권/월 | 29권/월 |
| $9.99 | $6.93 | 144권/월 | 14권/월 |
| $12.99 | $9.03 | 111권/월 | 11권/월 |

- 전자책 제작 비용은 사실상 0 (오픈소스 도구) — **한계이익률 ~100%**
- **현실적 벤치마크**: KDP 책 1권당 평균 판매는 수십~수백 권 수준 (레딧 보고) — **단권 수익은 작고, "100권 시리즈 × 권당 3권/일 = 월 $2.5만" 같은 볼륨 전략이 현실적** ([Medium KDP Files](https://medium.com/the-kdp-files-steal-my-notes/100-books-selling-3-copies-a-day-pays-25-470-pe))

**종이책 (참고):** 로열티 50% 또는 60% (리스트 가격·마켓플레이스별) − 인쇄비 ([KDP Print Book Pricing](https://kdp.amazon.com/help/topic/G8BKPU9AGVZSF9QF))

- 예: $9.99 300p 흑백 페이퍼백 → (0.60 × $9.99) − $4.60 = **$1.39/권**
- 2025년 6월 저가 종이책 로열티 60%→50% 인하 (ISBNdb 보도) — **전자책 중심 전략이 유리**

---

## R-5. KDP 정책: 타이틀 한도·AI 콘텐츠 표기·EPUB 요구사항 (1차 출처)

### 3.14 타이틀 생성 한도 — "일 3권 vs 주 10권" 해명 (⚠️ 기획의 핵심 확인 사항)

**결론: 둘 다 실존하는 정책. "일 3권"이 더 보수적인 운영 상한으로 타당.**

1. **현행 공식 Help: "포맷별 주 10권"** ([KDP Create a Book](https://kdp.amazon.com/help/topic/G202172740), [KDP 파일 형식 페이지](https://kdp.amazon.com/help/topic/G200634390))
   > "we limit the number of titles you can create at the same time to **10 per book format each week**"
2. **2023년 9월 18일: AI 콘텐츠 대응으로 "일 3권" 제한 도입** ([KDP 커뮤니티 공지](https://www.kdpcommunity.com/s/article/Update-on-KDP-Title-Creation-Limits?language=en_US), [가디언](https://www.theguardian.com/books/2023/sep/20/amazon-restricts-authors-from-self-publishing-more-than-three-books-a-day-after-ai-concerns))
   - "생성형 AI의 급속한 진화를 모니터링하며, 남용 방지를 위해 신규 타이틀 생성 볼륨 한도를 낮춘다"
   - 아마존이 가디언에 **"일 3권"** 확인, 예외 신청 가능
3. 레딧 실측: 2023년 9월 이후 다수 저자가 "일 3권" 제한 경험 보고 ([r/KDP](https://www.reddit.com/r/KDP/comments/1jvlesb/do_i_get_in_trouble_publishing_multiple_book))

**기획 반영**: requirements.md의 "일 3권 통일" 결정을 **유지** — 공식 Help의 주 10권보다 보수적이고, AI 생성 콘텐츠 시대의 실질 운영 한도에 부합. 다만 문서에는 "현행 Help: 주 10권 / 실질 운영 한도: 일 3권 (2023.9 이후)" 둘 다 명시해 혼동 방지.

### 3.15 AI 생성 콘텐츠 표기 (공식, [KDP Content Guidelines](https://kdp.amazon.com/help/topic/G200672390))

- **의무 공개**: AI 생성 콘텐츠(텍스트·이미지·번역)는 신규 출간·재출간 시 KDP에 **공개 필수**
- **AI-generated 정의**: "AI 도구가 실제 콘텐츠를 생성 (이후 대폭 수정해도 AI-generated)"
  - 이미지(표지·내부 삽화) 포함
- **AI-assisted는 공개 불필요**: "본인이 만들고 AI로 편집·교정·개선" 또는 "AI로 아이디어 브레인스토밍 후 직접 작성" → 면제
- 표절·중복 콘텐츠 금지, AI 콘텐츠도 모든 콘텐츠 가이드라인 준수 필요
- **Authors Guild 배경**: 2023년 9월 7일 발표, AI 생성 도서 급증 대응 ([Authors Guild](https://authorsguild.org/news/amazons-new-disclosure-policy-for-ai-generated-book-content-/))

**기획 반영**: QC 8항목에 "AI 표기 문구" 포함 (이미 계획됨 ✅) + **"AI-assisted vs AI-generated 구분 가이드" 추가** — 파이프라인이 초안을 LLM으로 생성하면 **법적으로 AI-generated에 해당**하므로 반드시 출간 시 공개 필요.

### 3.16 EPUB 요구사항 (공식, [KDP 파일 형식](https://kdp.amazon.com/help/topic/G200634390), [Kindle Publishing Guidelines](https://kdp.amazon.com/help/topic/GU72M65VRFPH43L6))

- **EPUB 지원**: KPG(Kindle Publishing Guidelines) 준수 시 업로드 가능
- **권장**: 업로드 전 Kindle Previewer로 검증
- 지원 형식: DOC/DOCX, KPF(Kindle Create), **EPUB**, HTML(ZIP), RTF, TXT, PDF(영어 등 9개 언어 한정)
- **MOBI: 2025년 3월부터 fixed-layout 전용으로만 수용 중단** (reflowable EPUB 중심으로 전환)
- **ebooklib + calibre + epubcheck 조합은 유효** (기획 K-3 설계 정당화)

---

## R-6. 책 홍보 쇼츠(KDP↔쇼츠) 모범 사례

### 3.17 숏폼이 책 판매를 바꾼 사례 (수치)

| 사례 | 수치 | 출처 |
|---|---|---|
| **It Ends with Us (Colleen Hoover)** | 2021년 판매 **650% 급증** (190만 권, NPD BookScan) → NYT 베스트셀러 29주 연속 | [A2Z Publishing](https://a2zpublishing.com/how-booktok-can-transform-your-book-sales-a-data-driven-guide-wi), [BookNet Canada](https://www.booknetcanada.ca/blog/research/2022/9/29/the-real-impact-of-booktok-on-book-sales) |
| BookTok 노출 도서 | **평균 판매 +600%** | [A2Z Publishing](https://a2zpublishing.com/how-booktok-can-transform-your-book-sales-a-data-driven-guide-wi) |
| 캐나다 백리스트 20종 | BookTok 트렌드 후 **매출 +1,047%** (중앙값 +2,255%) | [BookNet Canada (SalesData 실측)](https://www.booknetcanada.ca/blog/research/2022/9/29/the-real-impact-of-booktok-on-book-sales) |
| 유럽 #BookTok | **5,000만 권 판매, €8억 매출 (2025)** — NielsenIQ BookData·Media Control 분석 | [TikTok Newsroom](https://newsroom.tiktok.com/booktok-community-50-million-books?lang=en-150) |
| 미국 | BookTok이 2024년 종이책 판매 **5,900만 권** 유발, 12권 중 1권 | [A2Z Publishing](https://a2zpublishing.com/how-booktok-can-transform-your-book-sales-a-data-driven-guide-wi) |
| TikTok 사용자 | **45%가 플랫폼에서 본 책을 구매**, #BookTok 3,700억 뷰 (2024) | [A2Z Publishing](https://a2zpublishing.com/how-booktok-can-transform-your-book-sales-a-data-driven-guide-wi) |

### 3.18 모범 사례 원칙 (KDP↔쇼츠 시너지 설계 근거)

1. **감정·경험 기반 콘텐츠가 리뷰보다 강력** — "이 책을 읽고 울었다" 같은 반응형 숏폼 (BookTok 사례 공통)
2. **알고리즘은 팔로워 수 무관 추천** — 신인 작가도 100명 팔로워로 수백만 도달 가능 ([A2Z](https://a2zpublishing.com/how-booktok-can-transform-your-book-sales-a-data-driven-guide-wi))
3. **숏폼은 논픽션·교육 콘텐츠에 유효** — YouTube는 "교육/어드바이스" 크리에이터에 적합 ([Reedsy](https://reedsy.com/blog/book-marketing-ideas/))
4. **10~30초 "바이브 트레일러"** — 책의 감성·분위기 전달 숏폼 ([Reedsy](https://reedsy.com/blog/book-marketing-ideas/))
5. **네이티브 업로드 + 플랫폼별 재가공** — 같은 영상도 플랫폼 로직에 맞게 ([Reedsy](https://reedsy.com/blog/book-marketing-ideas/))
6. **시리즈 전략**: 검증된 주제 → 시리즈화 (KDP 문서의 "시리즈 확장 공식"과 일치)

### 3.19 KDP↔쇼츠 시너지 설계 (기획 반영안)

```
KDP 책 챕터 (영어권 워크북/가이드)
  → 챕터 핵심 팁 1개 = 30~45초 쇼츠 대본
  → 쇼츠 CTA: "Full chapter in my book on Amazon" + 링크
  → 시청자 → 아마존 책 상세페이지 → 구매 (KDP 수익)
  → 책 리뷰 → 다음 쇼츠 소재 (선순환)
```

- **수치 근거**: 숏폼 노출 도서 평균 +600% 판매, 유럽 5천만 권 — "쇼츠→책" 전환은 검증된 경로
- **한국어 운세 쇼츠와의 차별**: KDP 쇼츠는 영어권 대상, 운세 쇼츠는 한국어 대상 — 채널 분리 권장

---

## R-7. 한국어 운세/사주 쇼츠 사례·성과·규제

### 3.20 한국 운세 시장 규모·성과

- **한국 점술 시장 1.4조 원** (집계 제외 매출 고려 시 더 큼) ([크리스천헤럴드](https://www.cheraldus.com/bbs/board.php?bo_table=korean_news&wr_id=109))
- **MZ세대 91.6%가 사주·타로·별자리 경험** (537명 설문) ([브릿지경제](https://www.viva100.com/article/20250227501106))
- 네이버 엑스퍼트: 운세·사주·타로가 인기 분야 1·2위, **월 상담 건수·거래액 전년比 +30%**, 이용자 20~30대 80% ([크리스천헤럴드](https://www.cheraldus.com/bbs/board.php?bo_table=korean_news&wr_id=109))
- **유튜브 운세 채널 4,000개+** (플레이보드 통계) — 수십~수백만 뷰 영상 다수 ([중앙일보](https://www.joongang.co.kr/article/25329791))
- **디지털 운세 플랫폼 성과**: 포스텔러·점신 MAU 50~100만·누적 가입 860만/1,700만, 홍카페 매출 68억(2019)→300억(2023), 사주나루·사주천궁 각 200억+ ([브릿지경제](https://www.viva100.com/article/20250227501106))
- **운세 앱 트래픽은 자정(운세 갱신 시점) 폭주** — "밤 12시 되면 트래픽 폭주" ([중앙일보](https://www.joongang.co.kr/article/25329791))
- 글로벌 점성술 앱 시장 $322억(2023) → $2,387억(2032) 전망 ([Business Research Insights via 브릿지경제](https://www.viva100.com/article/20250227501106))
- MZ 운세 소비 이유: 마음의 위안(76.9%)·긍정 에너지(58.6%)·불확실성 해소(38%) (엠브레인) ([브릿지경제](https://www.viva100.com/article/20250227501106))

### 3.21 운세 쇼츠 사례 (실측)

- 유튜브 해시태그 `#운세쇼츠`·`#데일리운세`·`#띠별운세`·`#오늘의운세` 활성 — 쇼츠 전용 콘텐츠 생태계 형성 ([YouTube 해시태그](https://www.youtube.com/hashtag/%EC%9A%B4%EC%84%B8%EC%87%BC%EC%B8%A0))
- "오늘의 운세" 쇼츠 채널·플레이리스트 다수 (일일 갱신형)
- **일본 사례**: AI 새해 운세 유튜브로 수익화 (해외 쇼츠 수익화 사례) ([YouTube](https://www.youtube.com/watch?v=0Fdas9bLYWs))
- **AI 운세 쇼츠 자동 제작 도구·튜토리얼 확산** — n8n + AI로 쇼츠 자동 제작 ([YouTube](https://www.youtube.com/watch?v=8nML6B7poHM), [Reddit r/n8n](https://www.reddit.com/r/n8n/comments/1i66chs/i_used_ai_and_n8n_to_automate_youtube_shorts/?tl=))
- 카카오톡 '사주' 검색 시 오픈채팅방 수백 개, 구독자 11만+ 채널 존재 ([크리스천헤럴드](https://www.cheraldus.com/bbs/board.php?bo_table=korean_news&wr_id=109))

### 3.22 규제·리스크 (⚠️ 기획 반영 필수)

- **허위·과장 광고 규제**: 운세/사주 콘텐츠의 "적중률 보장" 류 표현은 공정거래법상 과장 광고 소지 — **"오락·참고용" 프레이밍 필요**
- **의료·투자·취업 결정 유도 금지**: 운세로 건강·금전·중요 결정을 유도하면 규제 리스크
- **선거·정치 이용 제한**: 공직선거법상 운세를 이용한 특정 후보 지지·비방 금지
- **민감정보**: 생년월일·시간(사주 4기둥) 수집 시 개인정보보호법 주의 — **날짜만 입력(띠·별자리) 방식이 안전**
- 유튜브 커뮤니티 가이드라인: 미신·사기성 콘텐츠 신고 대상 가능성 — "결정적 계산 기반"임을 명시해 **AI 환상 콘텐츠 아님을 문서화** (11-fortune 문서의 기존 원칙 유지)
- **차별화 포인트**: 대부분의 운세 쇼츠가 LLM 생성(환상 위험)인 반면, **autostudio는 결정적 엔진(60일주 계산) 기반** — 정확성·재현 가능성에서 차별화. 이 점을 홍보 문구로 활용.

---

## 4. 파일럿 주제 선정 근거 (리서치 기반)

### 4.1 쇼츠 파일럿 (10개 소재 → 5개 쇼츠)

| 후보 | 근거 (리서치) | 우선순위 |
|---|---|---|
| **오늘의 운세 (띠·별자리 카드)** | 한국 점술 시장 1.4조 원, MZ 91.6% 경험, 유튜브 운세 채널 4,000개+ (수요 검증), 결정적 엔진 차별화, 일일 갱신 = 업로드 리듬 확보 | 🥇 |
| **KDP 책 챕터 홍보 (영어권)** | 숏폼→책 판매 +600% 사례, 유럽 5천만 권, 시리즈 확장성 | 🥈 |
| 금융/절약 꿀팁 (KDP 워크북 연계) | 금융 쇼츠 RPM = 타 니치 10배, "52주 절약 챌린지" 워크북과 시너지 | 🥉 |
| 일반 트렌드/잡지식 (한국어) | 쇼츠 디스커버리 특성, 50~60초 완주율 76% | 4 |
| 교훈/동기부여 (AI 3분 지혜류) | 쇼츠 상위권 콘텐츠 유형 (네이버 집계) | 5 |

**파일럿 선정 기준 (제안)**: ① 수요 검증(검색·채널 존재) ② 자동화 궁합(스크립트화 용이) ③ 수익 경로 존재(광고/책/유입) ④ 업로드 리듬 지속 가능성 ⑤ 차별화(경쟁 대비)

### 4.2 KDP 파일럿 (기존 "52주 절약 챌린지 워크북" 재검증)

| 검증 항목 | 결과 |
|---|---|
| 시장 수요 | 금융/개인재무 셀프헬프 수요 지속, 아마존 셀프헬프 베스트셀러 카테고리 ✅ |
| 수익 모델 | 70% 로열티 $9.99 → 권당 $6.93, 손익분기 14권/월($100) ✅ |
| 자동화 궁합 | 구조화 워크북 = AI 파이프라인 최적 ✅ |
| 시리즈 확장 | "52주" 시리즈 → 월/분기/연간 변형 가능 ✅ |
| 경쟁도 | 절약/재무 워크북 경쟁 심함 (스냅샷 검증 필요) ⚠️ |

**권고**: "52주 절약 챌린지" 유지 + **아마존 검색 경쟁도 스냅샷(상위 20권 가격·평점·권수) 검증 추가** — "곧 뜰" 키워드와 교차 확인 (KDP 개선점 #4·#6 반영)

---

## 5. 기획 문서 반영 권고 (KDP 개선점 8건 매핑)

| # | 개선점 | 리서치 근거 (이 보고서) |
|---|---|---|
| 1 | 일 3권 통일 | §3.14 — 공식 Help 주 10권 + 2023.9 일 3권 실존. 일 3권 유지 타당 |
| 2 | 의존성 명시 | §3.16 — ebooklib·calibre·epubcheck 조합 유효 (공식 지원 형식) |
| 3 | 출간 후 모니터링 | §3.14~3.15 — 정책 변경 빈번(2026 가격 구간·AI 표기), 48h 확인 게이트 근거 |
| 4 | 키워드→주제 변환 | §3.11~3.12 — 시장 규모·카테고리 데이터로 영어 현지화 검증 근거 |
| 5 | QC 8항목 | §3.15 — AI 표기(AI-generated vs assisted 구분)가 핵심 항목 |
| 6 | 파일럿 근거 | §4.2 — 시장·수익·자동화 궁합 검증 |
| 7 | 수익성 모델 | §3.13 — 로열티 35/70%·가격 구간 확대·손익분기표 |
| 8 | KDP↔쇼츠 시너지 | §3.17~3.19 — 숏폼→책 +600% 사례 |

---

## 6. 오픈 질문 (기획팀 검토 필요)

1. **OQ-1 (수집 빈도)**: 쇼츠 수집 빈도 — API 쿼터 1%만 사용해도 충분하므로 **매일 1회 무난** (검증: 일일 100 units 예산)
2. **OQ-2 (주제 비중)**: 운세/KDP/일반 트렌드 비중 — 파일럿은 **운세 4 + KDP 3 + 일반 3** 권장 (수익 경로별 균형)
3. **OQ-3 (KDP 파일럿 주제)**: "52주 절약 챌린지" 유지 + 아마존 경쟁도 스냅샷 검증 추가 권장
4. **OQ-4 (TTS)**: edge-tts 무료·오픈소스 — 운세 카드 쇼츠(자막+간단 음성)에 적합. 다만 한국어 TTS 품질·저작권(목소리) 확인 필요
5. **신규 OQ-5**: 쇼츠 채널 전략 — 운세(한국어)와 KDP(영어) **채널 분리** 여부 (알고리즘 주제 일관성 측면에서 분리 권장)

---

## 7. 신뢰도 평가

| 등급 | 의미 | 적용 항목 |
|---|---|---|
| **A (높음)** | 1차 출처·공식 문서 | YouTube Data API 쿼터 문서, KDP Help 전부(로열티·가격·콘텐츠·파일·타이틀), YouTube ToS, YPP 자격, Alphabet 실적(Variety/Yahoo), KOBACO 방송통신광고비, KISDI 미디어패널, 가디언(KDP 일 3권), TikTok Newsroom |
| **B (중간)** | 신뢰성 있는 2차 분석 | Grand View Research, Demandsage, Influencer Marketing Hub, Shortimize, BookNet Canada(SalesData 실측), 중앙일보·이투데이·조선일보·브릿지경제, A2Z Publishing |
| **C (낮음)** | 단일 출처·추정·커뮤니티 | 쇼츠 광고 점유율 22%(shno 스니펫), 김프로 수익(네이버 블로그), KDP 평균 판매량(레딧/Medium), 일부 RPM 상한($5+), 운세 쇼츠 규제 해석 |

**주의 사항**:
- 쇼츠 RPM은 **크리에이터·지역·시기별 편차 극심** — 기획 시 "범위"로만 사용
- 한국 쇼츠 광고 단가 원화 환산 수치는 2차 출처 추정 — 기획 수익 모델에 넣지 말 것
- KDP 평균 판매량은 공식 통계 부재 — **시리즈 볼륨 전략의 참고치로만**
- 운세 쇼츠 "규제"는 법령 조항이 아닌 일반 원칙 해석 — **기획 단계에서 법률 검토 권장** (특히 공직선거법 연관)

---

## 8. 참고: 원천 데이터 (crawled/)

- `pipeline/shorts-kdp-research/crawled/raw/` — KDP Help·YouTube 공식 문서 HTML 원본 (9개)
- `pipeline/shorts-kdp-research/crawled/extracted/` — 텍스트 추출본 (9개)
- `pipeline/shorts-kdp-research/crawled/markdown/` — 기사·분석 마크다운 (37개)
- `pipeline/shorts-kdp-research/crawled/search-results.json` — 검색 결과 전체 (23+건)
- `pipeline/shorts-kdp-research/crawled/source-inventory.json` — 출처 인벤토리 (45개)

---

## 9. 출처 목록 (URL 전체)

### R-1 유튜브 쇼츠 시장
1. Variety — YouTube 2025 매출 $60B (2026-02-04): https://variety.com/2026/digital/news/youtube-2025-total-revenue-ads-subscriptions-alphabet-earnings-1236652260/
2. Yahoo Finance/Marketing Dive — YouTube 연매출 $60B (2026-02-05): https://finance.yahoo.com/news/youtube-annual-revenue-tops-60b-103200622.html
3. TheWrap — 쇼츠 일일 2,000억 뷰: https://www.thewrap.com/youtube-shorts-200-billion-daily-views/
4. Demandsage — 쇼츠 통계 2026: https://www.demandsage.com/youtube-shorts-statistics/
5. Loopex Digital — 쇼츠 통계 2026: https://www.loopexdigital.com/blog/youtube-shorts-statistics
6. Influencer Marketing Hub — 쇼츠 RPM 벤치마크: https://influencermarketinghub.com/youtube-shorts-rpm/
7. YouTube Help — YPP 자격: https://support.google.com/youtube/answer/72851
8. 이투데이 — 한국 유튜브 MAU 4,862만: https://www.etoday.co.kr/news/view/2526454
9. 조선일보 — 2025 한국 SNS MAU 순위: https://www.chosun.com/economy/tech_it/2025/12/28/2SEJEXGW7RAN7EBRJJJ4R2NCYY/
10. 한국기자협회 — 2025 방송통신광고비 조사: https://www.journalist.or.kr/news/article.html?no=60072
11. 오픈서베이 — 2025 소셜미디어 트렌드: https://blog.opensurvey.co.kr/article/socialmedia-2025-2/
12. KISDI — 2025 한국미디어패널조사: https://blog.naver.com/PostView.naver?blogId=kisdi_stat&logNo=224198717604
13. 네이버 블로그 — 유튜브 수익·쇼츠 집계 (2차): https://blog.naver.com/PostView.naver?blogId=skyu0021&logNo=224149769875

### R-2 알고리즘
14. Shortimize — 쇼츠 알고리즘 2025: https://www.shortimize.com/blog/how-does-youtube-shorts-algorithm-work
15. Medium — 33억 뷰 알고리즘 연구: https://medium.com/@antoinelacombled/cracking-the-youtube-shorts-algorithm-a-study-of-3-3-billion-views-4711fdf7931b
16. Conbersa — 쇼츠 분석 지표: https://www.conbersa.ai/learn/youtube-shorts-analytics-guide
17. Shorts Ninja — 쇼츠 성장 지표 5선: https://shortsninja.com/blog/top-5-metrics-for-youtube-shorts-growth/
18. Versa Creative — 쇼츠 알고리즘 2025: https://versacreative.com/blog/how-the-youtube-shorts-algorithm-works-in-2025/

### R-3 API 정책
19. YouTube Data API — 쿼터 계산기: https://developers.google.com/youtube/v3/determine_quota_cost
20. YouTube Data API — 시작하기: https://developers.google.com/youtube/v3/getting-started
21. YouTube ToS: https://www.youtube.com/static?template=terms
22. yt-dlp GitHub: https://github.com/yt-dlp/yt-dlp
23. Wikipedia — youtube-dl/yt-dlp 법적 이력: https://en.wikipedia.org/wiki/Youtube-dl
24. EFF — youtube-dl 복원: https://www.eff.org/deeplinks/2020/11/github-reinstates-youtube-dl-after-riaas-abuse-dmca

### R-4 KDP 시장
25. KDP Help — eBook 로열티: https://kdp.amazon.com/help/topic/G200644210
26. KDP Help — eBook 가격 요건 (70% 구간 확대): https://kdp.amazon.com/help/topic/G200634560
27. KDP Help — 종이책 가격·로열티: https://kdp.amazon.com/help/topic/G8BKPU9AGVZSF9QF
28. Grand View Research — 미국 셀프퍼블리싱 시장: https://www.grandviewresearch.com/industry-analysis/us-self-publishing-market-report
29. ISBNdb — 셀프퍼블리싱 데이터: https://isbndb.com/blog/self-publishing-is-changing-the-book-industry/

### R-5 KDP 정책
30. KDP Help — 콘텐츠 가이드라인 (AI 표기): https://kdp.amazon.com/help/topic/G200672390
31. KDP Help — 지원 파일 형식 (주 10권): https://kdp.amazon.com/help/topic/G200634390
32. KDP Help — 책 만들기 (타이틀 한도): https://kdp.amazon.com/help/topic/G202172740
33. KDP Help — Kindle Publishing Guidelines: https://kdp.amazon.com/help/topic/GU72M65VRFPH43L6
34. 가디언 — KDP 일 3권 제한 (2023-09-20): https://www.theguardian.com/books/2023/sep/20/amazon-restricts-authors-from-self-publishing-more-than-three-books-a-day-after-ai-concerns
35. KDP 커뮤니티 — 타이틀 생성 한도 업데이트: https://www.kdpcommunity.com/s/article/Update-on-KDP-Title-Creation-Limits?language=en_US
36. Authors Guild — AI 공개 정책: https://authorsguild.org/news/amazons-new-disclosure-policy-for-ai-generated-book-content-/

### R-6 책 홍보 쇼츠
37. A2Z Publishing — BookTok 데이터 가이드: https://a2zpublishing.com/how-booktok-can-transform-your-book-sales-a-data-driven-guide-wi
38. BookNet Canada — BookTok 매출 영향 (SalesData): https://www.booknetcanada.ca/blog/research/2022/9/29/the-real-impact-of-booktok-on-book-sales
39. TikTok Newsroom — 유럽 #BookTok 5,000만 권: https://newsroom.tiktok.com/booktok-community-50-million-books?lang=en-150
40. Reedsy — 책 마케팅 아이디어 96: https://reedsy.com/blog/book-marketing-ideas/
41. IBPA PubSpot — BookTok 케이스스터디: https://pubspot.ibpa-online.org/article/tapping-into-booktok-a-case-study-part-i

### R-7 운세 쇼츠
42. 크리스천헤럴드 — 한국 점술 시장 1.4조·MZ 운세: https://www.cheraldus.com/bbs/board.php?bo_table=korean_news&wr_id=109
43. 중앙일보 — MZ 운세 트래픽·유튜브 채널 4,000개: https://www.joongang.co.kr/article/25329791
44. 브릿지경제 — 디지털 운세 산업 (홍카페 300억 등): https://www.viva100.com/article/20250227501106
45. YouTube — #운세쇼츠 해시태그: https://www.youtube.com/hashtag/%EC%9A%B4%EC%84%B8%EC%87%BC%EC%B8%A0

---

*작성: 리서치팀 · 상태: R-1~R-7 조사 완료 · 다음 단계: 리서치QA 검증 → 기획팀 문서 개정*
