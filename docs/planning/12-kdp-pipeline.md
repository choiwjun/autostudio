# 12. KDP 자동 출간 파이프라인 (Phase K)

> 상태: 설계 확정 + **개선점 8건 전부 반영** (2026-08-14) · 관련: `11-fortune-channel.md`(수익화 로드맵), `14-shorts-pipeline.md`(Phase S — KDP↔쇼츠 시너지)
> 리서치 근거: `pipeline/shorts-kdp-research/research-report.md` (R-4~R-6) · 리서치QA 승인 (조건부 — P1·P2·P4 반영)
> 수치 규칙: 출처 인라인 표기, 단일 출처/C등급은 ⚠️ 표시, 14·12·11 문서 간 수치 불일치 금지 (일 3권·쿼터 1만·로열티 35/70%)

## 1. 목적

autostudio의 키워드 발굴·초안 파이프라인을 **아마존 KDP 전자책 출간**에 확장. "뜨는 키워드 = 책 주제" 공식으로 롱테일 수익원 추가 (애드포스트·쇼핑커넥트와 병행).

### 1.1 시장 근거 (출처 있는 수치)

| 항목 | 수치 | 출처 |
|---|---|---|
| 미국 셀프퍼블리싱 시장 | **$36억(2025) → $57억(2033), CAGR 5.7%** | [Grand View Research](https://www.grandviewresearch.com/industry-analysis/us-self-publishing-market-report) |
| 셀프퍼블리싱 작가 채널 | **98%가 전자책, 83%가 아마존 주 플랫폼** | [ISBNdb](https://isbndb.com/blog/self-publishing-is-changing-the-book-industry/) |
| 구조화 비소설 검증 | 셀프헬프/워크북 = Amazon 베스트셀러 카테고리 수요 지속, 자동화·AI 적합성 최고 (소설은 품질·정책 리스크) | [Amazon Best Sellers Self-Help](https://www.amazon.com/Best-Sellers-Self-Help/zgbs/books/4736), [Grand View Research](https://www.grandviewresearch.com/industry-analysis/us-self-publishing-market-report) |

### 1.2 수익 모델: 로열티 35%/70% + 손익분기 (개선점 #7 반영 — [KDP eBook Royalties](https://kdp.amazon.com/help/topic/G200644210))

| 옵션 | 로열티 | 조건 | 예시 |
|---|---|---|---|
| **35%** | 리스트 가격의 35% (VAT 제외) | 최소 $0.99 (파일 크기별 $1.99/$2.99) | $0.99 × 35% = **$0.35** |
| **70%** | 리스트 가격의 70% − 전송비(평균 **$0.06/권**) | **$2.99~$12.99** (2026-07-07 확대) | $9.99 × 70% − $0.06 = **$6.93** |

> ⚠️ **2026-07-07 변경 — 70% 로열티 가격 구간 $2.99~$12.99로 확대** (종전 $2.99~$9.99, [KDP 공식](https://kdp.amazon.com/help/topic/G200634560)) — **$11.99~$12.99 프리미엄 구간 가능** (14·12·11 공통 수치: 로열티 35/70%).

**손익분기 계산 (전자책, 70% 로열티, 전송비 $0.06)**:

| 가격 | 로열티/권 | 손익분기 (월 $1,000) | 손익분기 (월 $100) |
|---|---|---|---|
| $2.99 | $2.03 | 493권/월 | 49권/월 |
| $4.99 | $3.43 | 292권/월 | 29권/월 |
| $9.99 | $6.93 | 144권/월 | 14권/월 |
| $12.99 | $9.03 | 111권/월 | 11권/월 |

- 전자책 제작 비용은 사실상 0 (오픈소스 도구) — **한계이익률 ~100%**
- ⚠️ **현실 벤치마크 (C등급 — 참고치)**: KDP 책 1권당 평균 판매는 수십~수백 권 수준 (레딧/Quora 보고, [r/KDP](https://www.reddit.com/r/KDP/comments/1jvlesb/do_i_get_in_trouble_publishing_multiple_book)) — **단권 수익은 작고, "100권 시리즈 × 권당 3권/일 = 월 $2.5만" 볼륨 전략이 현실적** ([Medium KDP Files](https://medium.com/the-kdp-files-steal-my-notes/100-books-selling-3-copies-a-day-pays-25-470-pe) ⚠️ 미검증 — 기획 수익 산정의 근거로 사용하지 않음, 참고치 한정)
- 종이책 (참고): 로열티 50% 또는 60% − 인쇄비, 2025년 6월 저가 종이책 로열티 60%→50% 인하 → **전자책 중심 전략 유지** ([KDP Print](https://kdp.amazon.com/help/topic/G8BKPU9AGVZSF9QF), [ISBNdb](https://isbndb.com/blog/self-publishing-is-changing-the-book-industry/))

### 1.3 시장 검증 (2026-08-10 실측)
- Kindle 전자책 베스트셀러는 로맨스/스릴러/리터지 소설이 압도적 (Top 30의 ~90%)
- KDP 수익 공식: **시리즈 확장**(Dungeon Crawler Carl 1~6권 전부 Top 30) + **저가 볼륨**(Freida McFadden ~$1 스릴러)
- 자동화 궁합: 구조화 비소설(워크북/가이드)이 성공 확률·AI 적합성 최고, 소설은 품질·정책 리스크

## 2. 파이프라인 단계별 오픈소스 배치 (개선점 #2 반영 — 의존성 명시)

| 단계 | 배치 오픈소스 | 자체 구현/기존 자산 | 비고 |
|---|---|---|---|
| 1. 주제 선정 | — (아마존 공개 API 없음) | autostudio v20 '곧 뜰' 프리셋 + 아마존 검색 경쟁도 스냅샷 | `kdp_research.py` |
| 2. 책 아웃라인 | 구조 참고: `auto-ebook-generator` | pass1 골격 생성 재사용 — 챕터 목록·불릿 | `kdp_book.py` |
| 3. 챕터 작성 | 구조 참고: `auto-ebook-generator` | draft_pipeline 2패스 + 챕터 일관성 보정 패스 | 핵심은 기존 자산 |
| 4. 품질 검수 | — | QC 8항목 + KDP 특화(챕터 길이 ±20%·AI 표기 문구) | 자체 |
| 5. 표지 생성 | **Pillow** | `image_gen` 확장 — 6×9 비율 + 텍스트 오버레이 | 기존 생성기 + Pillow |
| 6. EPUB 조립 | **ebooklib** | `ebook_builder.py` — 목차·챕터·메타 조립 | 핵심 채택 |
| 7. 검증/변환 | **calibre**(`ebook-convert`) + **epubcheck** | GH Actions 배치 단계 | 업로드 전 필수 |
| 8. 출간 | — (자동 업로드 도구는 계정 제재 리스크) | 수동 업로드 + 출간 큐(**일 3권 게이트** — 개선점 #1) | 반자동 유지 |
| 9. 출간 후 모니터링 | — | **48h 확인 게이트 (신규 — 개선점 #3)** | 책 상태·가격·미러 확인 |
| 10. 성과 추적 | — | 대시보드 탭 확장 (판매·리뷰 입력) | autostudio 패턴 |

### 2.1 의존성 명세 (개선점 #2 — requirements-dev.txt·워크플로우)

**Python 의존성 (requirements-dev.txt 추가)**:
```
ebooklib>=0.18        # EPUB 조립 (K-3)
Pillow>=10.0          # 표지 6×9 텍스트 오버레이 (K-3)
# epubcheck·calibre는 시스템/워크플로우 도구 (아래)
```

**GH Actions 러너 (K-3 검증 단계 — calibre 설치 추가)**:
```yaml
- name: Install calibre + epubcheck
  run: |
    sudo apt-get update && sudo apt-get install -y calibre   # ebook-convert
    # epubcheck: java -jar epubcheck.jar (릴리스 다운로드)
- name: EPUB 검증
  run: |
    ebook-convert out.epub /tmp/check.mobi --debug-pipeline=2 2>&1 | tee epub-convert.log
    java -jar epubcheck.jar out.epub   # 에러 0 확인
```

> 리서치 근거: ebooklib+calibre+epubcheck 조합은 KDP 공식 지원 형식(EPUB)에 유효 — MOBI는 2025.3부터 fixed-layout 전용으로 수용 중단, reflowable EPUB 중심 ([KDP 파일 형식](https://kdp.amazon.com/help/topic/G200634390), [KPG](https://kdp.amazon.com/help/topic/GU72M65VRFPH43L6)).

### 배치 요약
```
[기존 자산 재활용]   [오픈소스 배치]       [자체 신규]
주제선정·챕터생성    ebooklib (EPUB 조립)   kdp_research.py
QC·대시보드·배치     calibre (검증·변환)    kdp_book.py
image_gen (이미지)   Pillow (표지 처리)     ebook_builder.py
                    (선택) pandoc (DOCX)   출간 큐·성과 추적·48h 모니터링
```

## 3. 데이터 모델

```
kdp_books     id · title · description · keywords(JSON) · category · status
              (draft/assembling/ready/published/monitoring) · created_at · updated_at
kdp_chapters  id · book_id(FK) · seq · title · body_md · word_count · status
kdp_covers    id · book_id(FK) · image_url · size(6×9) · created_at
kdp_publish   id · book_id(FK) · publish_date · price · royalty_rate · expected_royalty
              · status(pending/published/verified/failed) · verified_at   [개선점 #3 모니터링]
```

- 기존 SQLite/Postgres 이중 SQL 패턴 재사용 (`db.py` 확장)
- 엔진 메타는 `drafts`와 분리 (KDP 전용 테이블)
- `kdp_publish` 추가: 48h 확인 게이트 기록 (출간일·가격·검증 시각)

## 4. 모듈 설계

### kdp_research.py — 주제 선정 (~3h)
- 입력: v20 '곧 뜰' 프리셋 상위 키워드 + 카테고리(고CPC 우선)
- **키워드→주제 변환 단계 (개선점 #4)**: ① 한국어 키워드 → 영어 현지화 (번역 + 아마존 검색어 관례 검토) ② **아마존 검색량 검증** (검색 결과 수·상위권 책 존재 여부 — 공개 API 부재로 스냅샷 방식, 12 §7 참조) ③ 수요/경쟁 판정
- 아마존 검색 경쟁도 스냅샷: 상위권 권수·평점·가격대 → **틈새 판정** (경쟁 적음 + 수요 있음)
- **한국어 전자책 병행 옵션**: 영어 현지화가 어려운 키워드는 한국어 전자책(KDP KR)으로 병행 명시 — 파일럿에서 판단
- 산출: 책 주제 후보(제목·설명·키워드·카테고리) → kdp_books

### kdp_book.py — 책 생성 (~5h)
- 책 아웃라인: pass1 골격 생성 재사용 (챕터 6~12개 + 불릿)
- 챕터별 생성: draft_pipeline 2패스 (플랫폼=brand 포맷 재활용 — 마크다운)
- 일관성 보정 패스: 챕터 간 어조·용어·시점 통일 (LLM 1회 추가 호출)
- 예산: 챕터당 하드 예산 300초 (content_batch 패턴), 책 1권 = 여러 날 배치로 분산

### ebook_builder.py — EPUB 조립 (~3h)
- ebooklib: 목차(챕터 시퀀스)·메타(제목/저자/키워드)·챕터 HTML 조립
- 표지: image_gen(6×9) + Pillow 텍스트 오버레이(제목·부제)
- 검증: calibre ebook-convert (에러·경고 0) + epubcheck (GH Actions — §2.1)
- **서버리스 제약**: 조립·검증은 GH Actions 배치 전용 (Vercel 60초 한도 밖), 대시보드는 다운로드만

### QC 8항목 정의 (개선점 #5 — 4단계 품질 검수 기준)

| # | 항목 | 기준 | 근거 |
|---|---|---|---|
| 1 | 표절 유사성 | 타 도서·공개 콘텐츠 유사 문장 검출 (LLM 재작성·패러프레이즈 확인) | KDP 표절·중복 콘텐츠 금지 ([KDP Content Guidelines](https://kdp.amazon.com/help/topic/G200672390)) |
| 2 | 금지어 | 광고성 과장·의료/투자 확정 표현·Amazon 정책 위반어 | KDP 콘텐츠 가이드라인 |
| 3 | 사실성 | 수치·주장 출처 검증 (추정은 "추정" 명시) | 허위 정보 금지 |
| 4 | 챕터 간 중복 | 의미 중복 문단 검출 (embedding 유사도 ≥ 0.8 재작성) | 독자 경험·품질 |
| 5 | 길이 | 챕터별 목표 ±20% (워크북 800~1,200단어/챕터), 책 6~12챕터 | 구조화 비소설 표준 |
| 6 | **AI 표기** | **AI-generated vs AI-assisted 구분 판정 + 출간 시 공개 문구** (아래 상세) | KDP 의무 ([KDP Content Guidelines](https://kdp.amazon.com/help/topic/G200672390)) |
| 7 | 마크다운 정합 | 코드블록·링크·테이블 파싱 오류 0, EPUB 변환 경고 0 | K-3 게이트 |
| 8 | 메타데이터 | 제목·부제·설명·키워드(7개)·카테고리 2개·저자(펜네임) 검수 | KDP 검색 노출 |

**AI 표기 상세 (QC #6)**:
- **AI-generated** = "AI 도구가 실제 콘텐츠 생성 (이후 대폭 수정해도)" — 파이프라인 초안 LLM 생성물은 **AI-generated에 해당** → 출간 시 KDP에 **의무 공개** ([KDP Content Guidelines](https://kdp.amazon.com/help/topic/G200672390), [Authors Guild](https://authorsguild.org/news/amazons-new-disclosure-policy-for-ai-generated-book-content-/))
- **AI-assisted = 공개 불필요** = "본인이 만들고 AI로 편집·교정·개선" 또는 "AI 브레인스토밍 후 직접 작성"
- 출간 체크리스트에 "AI 생성 콘텐츠 공개" 항목 필수 포함

## 5. KDP 정책 게이트 (출간 시) — 개선점 #1·#5 반영

공식 정책 기준 (kdp.amazon.com Help, 2026-08-14 리서치QA 교차 검증 완료):

- **타이틀 생성 한도 — "둘 다 실존" 명시**:
  - 현행 공식 Help: **포맷별 주 10권** ([KDP Create a Book](https://kdp.amazon.com/help/topic/G202172740), [파일 형식](https://kdp.amazon.com/help/topic/G200634390))
  - 2023.9.18 AI 콘텐츠 대응으로 **일 3권** 제한 도입 ([KDP 커뮤니티](https://www.kdpcommunity.com/s/article/Update-on-KDP-Title-Creation-Limits?language=en_US), [가디언](https://www.theguardian.com/books/2023/sep/20/amazon-restricts-authors-from-self-publishing-more-than-three-books-a-day-after-ai-concerns))
  - **운영 상한: 일 3권으로 통일** (보수적 상한, 14·12·11 공통 수치) — 출간 큐 게이트 `일 3권` 유지
- **개인(individual) 가입 가능** — Business type에서 개인/법인 선택. 법적 이름으로 계정, 책에는 펜네임 사용 가능
- **EPUB 업로드 지원** ✓ — Kindle Publishing Guidelines 준수 시 (ebooklib 설계 유효, 업로드 전 Kindle Previewer 검증 권장)
- **AI 생성 콘텐츠 공개 표기 의무** — 출간 시 체크리스트 포함 (QC #6)
- **업로드 수동** — 자동 업로드 오픈소스(kdp-api류)는 브라우저 자동화로 계정 제재 리스크 → 미사용
- 표절·중복 콘텐츠 금지 — 챕터 QC에 유사성 점검 (QC #1)

## 6. 대시보드 (KDP 출간 탭)

- 책 목록(상태 배지 — **monitoring 포함**) · 챕터 진행률 바 · EPUB 다운로드 버튼 · 출간 체크리스트(표기·가격·키워드) · **48h 모니터링 리스트 (출간 후 미검증 책 표시 — 개선점 #3)**
- 기존 v18 탭 패턴 재사용

## 7. 실행 순서

1. **K-1** DB 스키마 + kdp_research.py (주제 선정 — 키워드→주제 변환·영어 현지화 포함) — ~3h
2. **K-2** kdp_book.py (챕터 생성 + 일관성 패스) — ~5h
3. **K-3** ebook_builder.py (ebooklib 조립 + calibre/epubcheck 검증 — 의존성 §2.1) — ~3h
4. **K-4** 배치 모드 + 대시보드 탭 + EPUB 다운로드 + **출간 큐(일 3권)+48h 모니터링** — ~3h
5. **파일럿**: "52주 절약 챌린지 워크북" 1권 → 반응 확인 → 시리즈 확장

### 파일럿 주제 선정 (개선점 #6 — 리서치 기반 재검증)

**"52주 절약 챌린지 워크북" 유지 (OQ-3 결정) + 아마존 경쟁도 스냅샷 검증 추가**:

| 검증 항목 | 결과 | 근거 |
|---|---|---|
| 시장 수요 | 금융/개인재무 셀프헬프 수요 지속, Amazon 셀프헬프 베스트셀러 카테고리 ✅ | [Amazon Best Sellers Self-Help](https://www.amazon.com/Best-Sellers-Self-Help/zgbs/books/4736) |
| 수익 모델 | 70% 로열티 $9.99 → 권당 **$6.93**, 손익분기 14권/월($100) ✅ | §1.2 손익분기표 |
| 자동화 궁합 | 구조화 워크북 = AI 파이프라인 최적 ✅ | §1.1 |
| 시리즈 확장 | "52주" → 월/분기/연간 변형 가능 ✅ | 시리즈 공식 |
| 경쟁도 | 절약/재무 워크북 경쟁 심함 — **K-1 스냅샷 검증 필요** ⚠️ | 상위 20권 가격·평점·권수 조사 |

**파일럿 실행 전 게이트**: 아마존 검색 "52 week money saving challenge" 상위 20권 스냅샷 → 경쟁도 판정 후 확정. '곧 뜰' 키워드와 교차 확인 (개선점 #4·#6 반영).

### 시리즈 확장 공식
- 검증된 주제 → 시리즈화 (52주 → 100일·분기·연간 변형, 난이도별 2~3권)
- **엔진 자산 연계 (v22.5)**: 일주 분석(60일주) 문구 세트 → "60일주 성격 해석 가이드" 시리즈 — 결정적 계산 기반 = AI 환상 아님 (차별화, 11-fortune §1.5 연계)

## 8. 리스크

| 리스크 | 완화 |
|---|---|
| AI 생성 콘텐츠 제한 (일 3권·공개 표기) | 출간 게이트 체크리스트로 강제 (QC #6) |
| 전자책 시장 경쟁 | '곧 뜰' 키워드 기반 틈새 주제 + 시리즈 전략 + 경쟁도 스냅샷 |
| 품질 (AI 소설 반감) | 구조화 워크북/가이드 파일럿 → 검증 후 장르 확장 |
| 아마존 정책 변경 | 반자동(수동 업로드) 유지 + **48h 모니터링 게이트**로 정책·가격 변동 감지 |
| 의존성 설치 누락 | requirements-dev.txt + GH Actions calibre/epubcheck 설치 단계 명시 (§2.1) |
| 출간 후 미러/가격 오류 | 48h 확인 게이트 (책 상태·가격·미러) — 대시보드 monitoring 상태 |

## 9. KDP ↔ 쇼츠 시너지 (개선점 #8 — 14-shorts-pipeline.md §6과 상호 참조)

```
KDP 책 챕터 (영어권 워크북/가이드)
  → 챕터 핵심 팁 1개 = 30~45초 쇼츠 대본 (14-shorts §3.3)
  → 쇼츠 CTA: "Full chapter in my book on Amazon" + 링크
  → 시청자 → 아마존 책 상세페이지 → 구매 (KDP 수익)
  → 책 리뷰 → 다음 쇼츠 소재 (선순환)
```

**수치 근거 (출처)**:
| 사례 | 수치 | 출처 |
|---|---|---|
| BookTok 노출 도서 | 평균 판매 **+600%** | [A2Z Publishing](https://a2zpublishing.com/how-booktok-can-transform-your-book-sales-a-data-driven-guide-wi) |
| It Ends with Us | 2021년 판매 **650% 급증** (190만 권, NPD BookScan) | [A2Z](https://a2zpublishing.com/how-booktok-can-transform-your-book-sales-a-data-driven-guide-wi), [BookNet Canada](https://www.booknetcanada.ca/blog/research/2022/9/29/the-real-impact-of-booktok-on-book-sales) |
| 캐나다 백리스트 20종 | BookTok 트렌드 후 매출 **+1,047%** (중앙값 +2,255%) | [BookNet Canada (SalesData)](https://www.booknetcanada.ca/blog/research/2022/9/29/the-real-impact-of-booktok-on-book-sales) |
| 유럽 #BookTok | **5,000만 권 판매·€8억 (2025)** | [TikTok Newsroom](https://newsroom.tiktok.com/booktok-community-50-million-books?lang=en-150) |
| 미국 | BookTok이 2024년 종이책 판매 **5,900만 권** 유발 (12권 중 1권) | [A2Z](https://a2zpublishing.com/how-booktok-can-transform-your-book-sales-a-data-driven-guide-wi) |
| TikTok 사용자 | **45%가 플랫폼에서 본 책 구매**, #BookTok 3,700억 뷰 | [A2Z](https://a2zpublishing.com/how-booktok-can-transform-your-book-sales-a-data-driven-guide-wi) |

**모범 사례 원칙** (리서치 R-6):
1. 감정·경험 기반 콘텐츠가 리뷰보다 강력 (반응형 숏폼)
2. 알고리즘은 팔로워 수 무관 추천 — 신인 작가도 소규모 팔로워로 대규모 도달 가능
3. 숏폼은 논픽션·교육 콘텐츠에 유효 ([Reedsy](https://reedsy.com/blog/book-marketing-ideas/))
4. 10~30초 "바이브 트레일러" — 책의 감성·분위기 전달
5. 네이티브 업로드 + 플랫폼별 재가공
6. 시리즈 전략: 검증된 주제 → 시리즈화

**채널 구분 (OQ-5 결정과 정합)**: KDP 쇼츠는 **영어권 채널 전용** — 한국어 운세 쇼츠 채널과 분리 (14-shorts §5 채널 전략). 쇼츠 CTA 링크는 아마존 책 상세페이지(딥링크)로.

## 10. KDP 개선점 8건 → 반영 위치 매핑표 (NFR-4 추적성)

| # | 구분 | 개선점 | 반영 위치 |
|---|---|---|---|
| 1 | 🔴 수정 | 주간 10권/일 3권 한도 혼용 → **일 3권 통일** | §5 (정책 게이트) — "둘 다 실존" 명시 + 일 3권 운영 상한 |
| 2 | 🔴 수정 | 의존성 미기재 (ebooklib·Pillow·calibre) | §2.1 (requirements-dev.txt + GH Actions calibre/epubcheck 설치) |
| 3 | 🟡 보강 | 출간 후 모니터링 게이트 부재 | §2 (단계 9·10), §3 (kdp_publish), §6 (대시보드 monitoring), §8 (리스크) |
| 4 | 🟡 보강 | '곧 뜰' 키워드 → 책 주제 변환 단절 | §4 (kdp_research.py — 영어 현지화 + 아마존 검색량 검증 + 한국어 병행) |
| 5 | 🟡 보강 | QC 8항목 미정의 | §4 (QC 8항목 표 — 표절·금지어·사실성·중복·길이·AI 표기·마크다운·메타) |
| 6 | 🟡 보강 | 파일럿 주제 선정 근거 부족 | §7 (파일럿 재검증 표 + 경쟁도 스냅샷 게이트) |
| 7 | 🟡 보강 | 수익성/비용 모델 부재 | §1.2 (로열티 35/70%·가격 구간 확대·손익분기표) |
| 8 | 🟢 연계 | KDP↔쇼츠 시너지 미정의 | §9 (시너지 흐름 + 수치 근거 + 채널 구분) |

---

*작성: 기획팀 · 상태: 개선점 8건 전부 반영 (2026-08-14) · 상호 참조: 14-shorts-pipeline.md §6(시너지)·11-fortune-channel.md §9(운세·KDP 쇼츠)*
