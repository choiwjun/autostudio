# 쇼츠 + KDP 파이프라인 — 기술 요구사항 (trd.md)

> 작성: 기획팀 · 프로젝트: autostudio · 작업 디렉토리: `pipeline/shorts-kdp-research/`
> 작성일: 2026-08-14 · 모드: standard · 상위: `plan.md` · 근거: `research-report.md` R-3(API)·R-5(EPUB)·R-2(지표)

## 1. 기술 스택·아키텍처 제약

### 1.1 스택 (기존 autostudio 자산 재사용 원칙)

| 계층 | 기술 | 비고 |
|---|---|---|
| 백엔드 | Python 3.x / FastAPI | 기존 server.py 확장 |
| 데이터 | SQLite + Postgres 이중 SQL 패턴 (`db.py` 확장) | 기존 패턴 재사용 |
| 배치 | GitHub Actions (daily-collect.yml 패턴) | S-1 매일 1회, K-3 EPUB 검증 |
| 서버리스 | Vercel (60초 한도) | 조립·검증은 배치 전용, 대시보드는 다운로드만 |
| 외부 API | YouTube Data API v3 | 무료 티어 10,000 units/일 |
| LLM | 기존 draft_pipeline (OpenCode Go 우선, Bailian 폴백) | 스크립트·챕터 생성 |
| TTS | edge-tts (**LGPL-3.0 대부분 + MIT srt_composer**) + **MeloTTS**(MIT·한국어 지원) 대체 검토 | OQ-4 결정 — 자막 병행, ⚠️ 비공식 API — 파일럿 전 라이선스 검증 (S-4). ~~Piper~~(아카이브 2025-10·한국어 모델 없음)·~~Kokoro~~(한국어 미지원) 제외, piper1-gpl(GPL-3.0) 계승 명시 (오픈소스 조사 P1-1·P1-3) |
| EPUB | ebooklib(**AGPL-3.0**) + calibre(ebook-polish --check) + epubcheck(Java 필요) | K-3 — 의존성 명시 (개선점 #2), Java 미설치 시 ebook-polish 폴백 (K-1). ⚠️ AGPL-3.0: 내부 사용 OK, 외부 SaaS 서비스화 시 파생 공개 의무 — 대안 pypub(MIT) (오픈소스 조사 P1-2) |
| 표지 | Pillow + image_gen 확장 | 6×9 텍스트 오버레이 |

### 1.2 아키텍처 제약

- **Vercel 서버리스 60초 한도**: 쇼츠 수집·주제 판정은 GH Actions 배치로 (API 호출+LLM은 60초 초과 가능). 대시보드 API는 경량(조회·다운로드)만
- **SQLite/Postgres 이중 SQL**: 모든 신규 쿼리는 두 엔진 모두에서 동작 (기존 `db.py` 헬퍼 패턴)
- **GH Actions 배치 패턴 재사용**: daily-collect.yml의 스케줄·시크릿·런너 구조 복제
- **자동 업로드 금지**: 아마존·유튜브 모두 수동 — 파이프라인은 산출물(스크립트/EPUB/체크리스트) 제공까지만

## 2. 성능 요건

| 항목 | 요구사항 | 근거 |
|---|---|---|
| 쇼츠 수집 (S-1) | 매일 1회, **≤ 2분** (API 80회+ 저장) | GH Actions 배치 타임아웃 내 |
| 쿼터 예산 | **≤ 100 units/일** (10,000 대비 1%) | 리서치 R-3 시뮬레이션 — 여유 확보 |
| 주제 판정 (S-2) | 10개+ 후보 산출 ≤ 1분 (LLM 제외) | 지표 계산은 로컬 |
| 스크립트 생성 (S-3) | 1건당 ≤ 90초 (LLM 호출 2회+검수) | content_batch 하드 예산 패턴 |
| 책 생성 (K-2) | 챕터당 하드 예산 **300초**, 책 1권 = 여러 날 배치 분산 | 기존 content_batch 패턴 |
| EPUB 조립·검증 (K-3) | 1권 ≤ 3분 (GH Actions) | calibre 변환 + epubcheck |
| 대시보드 API | P95 < 500ms (조회·다운로드) | Vercel 서버리스 |

## 3. 보안 요건

| 항목 | 요구사항 |
|---|---|
| API 키 | `YOUTUBE_API_KEY`는 `.env.local`/GH Actions 시크릿 — 소스 커밋 금지 (기존 패턴) |
| LLM 호출 | 기존 프롬프트·예산 패턴 (외부 키 없음 — 기존 자산) |
| 발행 API | autoblog 발행 API 토큰 인증 재사용 (운세 쇼츠 아님 — 콘텐츠 생성만) |
| 민감정보 | 운세 쇼츠는 **날짜만 입력** (띠·별자리) — 생년월일·시간(사주 4기둥) 미수집 (개인정보보호법, 11-fortune §9) |
| 아마존·유튜브 | 자동 업로드 도구(kdp-api류·yt-dlp 업로드) 미사용 — 계정 제재 리스크 회피 |
| ToS 준수 | 유튜브 스크래핑 금지 원칙 (API v3 우선) — 14-shorts §2.2 |

## 4. 외부 시스템/API 연동 요구사항

### 4.1 YouTube Data API v3 (S-1)

| 항목 | 요구사항 | 출처 |
|---|---|---|
| 기본 쿼터 | 10,000 units/일 (태평양 자정 리셋) | [공식 문서](https://developers.google.com/youtube/v3/determine_quota_cost) |
| `search.list` | **100회/일 별도 버킷** (1회 = 1 unit, 2026 개편) | [공식 문서](https://developers.google.com/youtube/v3/determine_quota_cost) |
| 사용 엔드포인트 | videos.list(1)·channels.list(1)·commentThreads.list(1)·search.list(1)·playlistItems.list(1) | 공식 쿼터 표 |
| 실패 정책 | 실패 요청도 최소 1 unit 소모 — 재시도는 지수 백오프, 4xx는 재시도 금지 | [공식 문서](https://developers.google.com/youtube/v3/determine_quota_cost) |
| 페이지네이션 | 페이지당 비용 발생 — 1페이지만 수집 (상위 50개) | 공식 |

### 4.2 아마존 KDP (K-1~K-4)

| 항목 | 요구사항 | 출처 |
|---|---|---|
| 공개 API | **없음** — 검색 경쟁도 스냅샷 방식 유지 (상위 20권 가격·평점·권수) | 리서치 §2.3 한계 |
| 한국어 병행 | KDP KR 한국어 전자책 — 영어 전환율 30% 미만 시 병행 확대 | K-2 (파일럿 게이트) |
| EPUB | Kindle Publishing Guidelines 준수, 업로드 전 Kindle Previewer 검증 권장 | [KDP 파일 형식](https://kdp.amazon.com/help/topic/G200634390) |
| 로열티 | 35%/$0.99~ / 70%/$2.99~$12.99 (2026-07-07 확대) | [KDP Help](https://kdp.amazon.com/help/topic/G200644210) |
| 타이틀 한도 | 공식 주 10권(포맷별) + 실질 일 3권 (2023.9) — **일 3권 게이트** | [KDP Help](https://kdp.amazon.com/help/topic/G202172740)·[가디언](https://www.theguardian.com/books/2023/sep/20/amazon-restricts-authors-from-self-publishing-more-than-three-books-a-day-after-ai-concerns) |
| AI 표기 | AI-generated 공개 의무 / AI-assisted 면제 — **본문+표지(이미지) 모두** | [KDP Content Guidelines](https://kdp.amazon.com/help/topic/G200672390) — K-3 |

### 4.3 기타

| 항목 | 요구사항 |
|---|---|
| edge-tts | **LGPL-3.0(대부분 파일)+MIT(srt_composer)** — ⚠️ **비공식 API(상업 이용 약관 위반 소지)** 한국어 품질·목소리 저작권·대체재(**MeloTTS**·MIT·한국어 공식 지원 — 1순위, piper1-gpl·GPL-3.0) 파일럿 전 검증 (S-4). ~~Piper~~ 아카이브 2025-10·공식 한국어 모델 없음, ~~Kokoro~~ 한국어 미지원 (9개 언어 중 한국어 없음) (오픈소스 조사 P1-1·P1-3) |
| 문법 검사 (P2-3) | 영어: **LanguageTool**(HTTP API) · 한국어: **py-hanspell** — K-2 QC·S-3 검수에서 언어별 병행 |
| 네이버 '곧 뜰' 프리셋 | K-1 입력 재사용 (기존 자산) |
| 운세 엔진 | `engine/` Python 모듈 재사용 (60일주·별자리·띠) — 결정적 계산 |

## 5. 데이터 요구사항

### 5.1 쇼츠 데이터 모델 (14-shorts §4 확정)

```sql
youtube_raw       id · video_id(UNIQUE) · title · tags(JSON) · description · channel_id ·
                  channel_title · published_at · view_count · like_count · comment_count ·
                  share_count? · region · fetched_at
shorts_topics     id · label · score · evidence(JSON) · status · created_at
shorts_scripts    id · topic · hook · script_md · hashtags(JSON) · ref_video_ids(JSON) ·
                  status(draft/ready/published) · created_at · updated_at
```

- `share_count`: API statistics의 shareCount는 채널 소유 시에만 — **수집 불가 시 공유율 대체 지표**(조회급상승+반응비) 사용, 파일럿에서 검증
- 멱등성: `video_id UNIQUE` UPSERT (재수집 안전)

### 5.2 KDP 데이터 모델 (12-kdp §3 확정)

```sql
kdp_books     id · title · description · keywords(JSON) · category · status
              (draft/assembling/ready/published/monitoring) · created_at · updated_at
kdp_chapters  id · book_id(FK) · seq · title · body_md · word_count · status
kdp_covers    id · book_id(FK) · image_url · size(6×9) · created_at
kdp_publish   id · book_id(FK) · publish_date · price · royalty_rate · expected_royalty
              · status(pending/published/verified/failed) · verified_at   [48h 모니터링]
```

- `kdp_publish`는 개선점 #3(출간 후 모니터링)의 기록 저장소

### 5.3 데이터 정합 규칙 (NFR-3)

- **공통 상수**: 일 3권(출간 게이트) · 쿼터 10,000 units/일 · 로열티 35%/70% · 70% 구간 $2.99~$12.99 · 손익분기($9.99→$6.93/권, 월$100=14권) — 14·12·11 문서와 동일 값, config 상수로 단일화 권장
- **지표 상수 (S-1)**: 공유율(공유/조회 ≥ 0.5%)은 **채널 소유 시에만** 수집·판정 — `share_count` 컬럼은 예약, 비소유 시 NULL (14-shorts §4·§5.1과 동일)

## 6. 확장성 요건

| 항목 | 요구사항 |
|---|---|
| 쇼츠 수집 확장 | regionCode 파라미터로 국가 확장 (KR → US·JP), 쿼터 예산 내 자동 조절 |
| KDP 볼륨 | 일 3권 게이트로 상한 — DB·배치는 100권 시리즈 수용 (테이블 인덱스 필수) |
| 시리즈 확장 | 검증된 주제 → 시리즈화 (52주 → 100일·분기·연간) — 생성 파라미터 재사용 |
| 채널 분리 | 운세(한국어)·KDP(영어)·일반(한국어) — 태그·설명 템플릿 분리 (OQ-5) |

## 7. ADR (아키텍처 결정 기록)

| ADR | 결정 | 대안 | 근거 |
|---|---|---|---|
| ADR-1 | YouTube API v3 유일 정식 소스 | yt-dlp·스크래핑 | ToS 위반 리스크 (2020 RIAA DMCA 선례), 공식·무료·안정 |
| ADR-2 | EPUB=ebooklib+calibre+epubcheck | pandoc DOCX·Kindle Create | 공식 지원 형식, 검증 자동화 (KDP 파일 형식) |
| ADR-3 | 배치는 GH Actions (Vercel 밖) | Vercel cron | 60초 한도 — EPUB 조립·LLM 생성은 배치 전용 |
| ADR-4 | edge-tts (OQ-4) — 라이선스: LGPL-3.0 대부분+MIT srt_composer, ⚠️ 비공식 API | 유료 TTS·자막만·**MeloTTS**(MIT·한국어 지원) | 무료·오픈소스, 운세 카드에 적합 — 비공식 API 리스크 시 MeloTTS 대체, 자막 폴백 유지 (오픈소스 조사 P1-1·P1-3) |
| ADR-5 | 채널 분리 (OQ-5) | 단일 채널 | 알고리즘 주제 일관성 — 파일럿 최소 2채널(한국어/영어) |
| ADR-6 | 일 3권 게이트 (OQ-3 관련) | 주 10권 | 보수적 상한, AI 콘텐츠 시대 실질 한도 (가디언·KDP 커뮤니티) |

## 8. 구현 시 주의사항 (개발팀 인계)

1. **search.list 별도 버킷** (100회/일) — 쿼터 계산 로직에 반영, `videos.list`와 혼동 금지
2. **shareCount 비공개 (채널 소유 시에만)** — 공유율은 조건부 지표, 비소유 시 조회급상승·조회/구독·반응비로 판정 (S-1)
3. **calibre·epubcheck 설치** — GH Actions 러너에 **calibre + openjdk(epubcheck Java 필수)** 명시 (12-kdp §2.1), Java 불필요 폴백: ebook-polish --check (K-1)
4. **AI 표기 QC** — AI-generated 판정 로직 + 출간 체크리스트 (12-kdp QC #6)
5. **엔진 데이터는 결정적** — 운세 카드 쇼츠는 LLM 환상 콘텐츠 금지 (11-fortune §8-1 원칙)
6. **수동 업로드 UX** — 스크립트/EPUB/체크리스트 다운로드 중심, 자동 업로드 API 미구현
7. **TTS 라이선스 상수** — edge-tts=LGPL-3.0(대부분)+MIT(srt_composer)·비공식 API, MeloTTS=MIT·한국어 지원(대체 1순위), piper1-gpl=GPL-3.0 — 파이프라인 config에 라이선스·대체 후보 명시 (S-4 게이트, 오픈소스 조사 P1-1·P1-3)
8. **ebooklib AGPL-3.0** — 내부 파이프라인 OK, **외부 SaaS 서비스화 시 파생 코드 공개 의무** — 서비스화 시 pypub(MIT) 대체 검토 (P1-2·P3-4)
9. **pytrends 참고용 한정** — 아카이브(2024-08)·비공식 API — 주 소스 API v3 유지, pytrends 단독 의존 금지 (P1-4)

---

*작성: 기획팀 · 상태: 기획 문서 패키지 2/5 (오픈소스 조사 P1·P2 반영) · 상위: plan.md · 근거: research-report.md R-3·R-5, opensource-report.md §4 (P1·P2)*
