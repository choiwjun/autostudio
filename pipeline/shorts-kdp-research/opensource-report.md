# 쇼츠 + KDP 파이프라인 오픈소스 도구 조사 보고서

> **작성**: 리서치팀 · **프로젝트**: autostudio · **작업 디렉토리**: `pipeline/shorts-kdp-research/`
> **작성일**: 2026-08-14 · **대상**: `docs/planning/14-shorts-pipeline.md` · `docs/planning/12-kdp-pipeline.md`
> **상위 문서**: `plan.md` · `trd.md` (기획/기술 요구사항)
> **조사 지시**: 쇼츠·KDP 파이프라인에 유용한 오픈소스 도구 발굴 — 유용성·기능개선 관점 (8개 주제)
> **방법론**: GitHub API 실측(별·활발도·라이선스) + 1차 출처(GitHub 저장소) 우선 + Firecrawl 보조 검증 (2026-08-14)

---

## 1. 요약 (TL;DR)

| 조사 주제 | 핵심 발견 | 기존 기획 대비 시사점 |
|---|---|---|
| 1. 쇼츠 자동화 | yt-dlp·moviepy·ffmpeg는 안정적. **Remotion은 "완전 오픈소스 아님"** (회사 규모별 라이선스, ⚠️ 오해 소지), **AI-Youtube-Shorts-Generator(⭐4.6k)** 가 Opus Clip류 대안으로 주목 | S-3 편집 자동화는 moviepy 기반 보조 수준 유지 권장, Remotion은 "회사 라이선스 필요" 명시 필요 |
| 2. 트렌드 발굴 | **pytrends ⚠️ 아카이브됨(2024-08 마지막 커밋)** — Google Trends 비공식 API, 깨질 수 있음. API v3 `mostPopular` + 공식 클라이언트가 최선 | S-1의 API v3 우선 원칙 **재확인** — pytrends는 보조·참고용으로만 |
| 3. TTS | **edge-tts 실제 라이선스 = LGPL-3.0** (대부분 파일) + MIT(srt_composer.py) — 비공식 API 리스크는 유지. **Kokoro 한국어 미지원** (9개 코드: 미영·영영·스페인·프랑스·힌디·이탈리아·일본·브라질포르투갈·중국어), **Piper 아카이브됨** → piper1-gpl(GPL-3.0) 계승, **MeloTTS(⭐7.6k, MIT) = 한국어 공식 지원 + 완전 오픈(MIT)인 경량 로컬 TTS** (edge-tts는 비공식 API·LGPL이라 대조적) | ⚠️ **S-4 TTS 게이트 재검토 필요**: 파일럿 전 Kokoro/Piper "한국어 미지원" 확인 → **MeloTTS를 대체 후보로 추가** 권장 |
| 4. 자막/캡션 | Whisper 한국어 WER 8~13% (Tier 2). faster-whisper·whisperX·auto-subtitle·**VideoLingo(⭐18k)** 유효 | S-3 자막 병행 강화 — whisper 기반 자막 생성은 "쇼츠 자막"과 "KDP 검증" 모두에 유효 |
| 5. KDP 전자책 | **⚠️ ebooklib 라이선스 = AGPL-3.0** — 기획이 "오픈소스·무료"로만 인지, **상업 배포 시 소스 공개 의무** (내부 사용 시 문제 없음). pypub(MIT)·pandoc(GPL-2.0)·calibre(GPL-3.0) | **K-3 의존성 검토**: ebooklib AGPL은 "내부 도구로만 사용"이면 무해, SaaS 배포 시 주의. pypub(MIT) 대안 후보 |
| 6. 표지/디자인 | Pillow(HPND·BSD류)·ImageMagick 유효. 3D-book-image-css-generator(⭐658, MIT) = 쇼츠용 3D 책 이미지 | K-3 표지 + S-5 쇼츠용 3D 책 이미지에 활용 가능 |
| 7. 책 홍보/메타 | 아마존 공개 API 여전히 없음(스크래퍼는 ToS 리스크). **OpenLibrary API·Google Books API·isbnlib(LGPL-3.0) = 무료 메타데이터 대안** | K-1 스냅샷 + K-4 모니터링 보강: ISBN/메타데이터는 무료 API로 대체 가능 |
| 8. 파이프라인 보강 | textstat(MIT)·sentence-transformers(Apache-2.0)·**LanguageTool(⭐14.8k, LGPL-2.1, ⚠️ 한국어 미지원)**·py-hanspell(MIT, 네이버 비공식 API) | K-2 QC 8항목 보강: 챕터 중복(임베딩)·가독성(textstat)·문법(한국어는 py-hanspell만) |

### ⚠️ 기획 문서 수정 필요 사항 (가장 중요한 발견 4건)

1. **edge-tts 라이선스 정정**: `trd.md`·`14-shorts.md`에 "오픈소스·무료"만 적혀 있으나 **실제 라이선스는 LGPL-3.0**(대부분 파일) — 상업 이용 시 **LGPL 준수(동적 링크·고지) 필요**, 비공식 API(MS 서버 활용) 리스크는 그대로
2. **ebooklib AGPL-3.0**: `12-kdp.md`·`trd.md`의 "오픈소스·무료" 표기 → **AGPL-3.0 = 상업 배포 시 파생 코드 공개 의무**. 내부 파이프라인으로만 쓰면 무해, 외부 서비스화 시 주의. 대안: **pypub(MIT, 간단 EPUB 생성)**
3. **Kokoro·Piper 한국어 미지원**: `14-shorts.md` §3.3 "Piper(한국어 모델 존재)·Kokoro" 표기는 **현 시점 부정확** — Piper 아카이브(2025-10), Kokoro 8개 언어 중 한국어 없음. **MeloTTS(MIT, 한국어 지원)** 를 대체 후보로 추가
4. **pytrends 아카이브**: Google Trends 비공식 API — "보조"로만 사용, 주 소스는 API v3 유지

---

## 2. 요약표 (전체 도구)

### 2.1 쇼츠 자동화 (주제 1)

| 도구 | GitHub 별 | 라이선스 | 활발도(마지막 커밋) | 한국어 | 기존 기획 대체/보강 | 적용 모듈 |
|---|---|---|---|---|---|---|
| **yt-dlp** | ⭐184,395 | Unlicense | 2026-08 (매우 활발) | ✅ | 보강 (S-1 보조·제한적) | S-1 |
| **youtube-transcript-api** | ⭐8,039 | MIT | 2026-05 | ✅ | 보강 (자막 수집) | S-1·S-3 |
| **moviepy** | ⭐14,848 | MIT | 2026-08 | — | 보강 (편집 자동화 참고) | S-3 |
| **FFmpeg** | ⭐63,295 | LGPL/GPL | 2026-08 | — | 보강 (핵심 미디어 처리) | S-3 |
| **Remotion** | ⭐56,297 | ⚠️ 회사 라이선스(2-tier) | 2026-08 | — | ⚠️ 완전 오픈 아님 — 회사 규모별 유료 | S-3 (검토만) |
| **Shotcut** | ⭐14,918 | GPL-3.0 | 2026-08 | ✅ | 보강 (수동 편집 GUI) | S-3 (사용자 도구) |
| **AI-Youtube-Shorts-Generator** | ⭐4,591 | ⚠️ 라이선스 없음 | 2026-07 | — | ⚠️ 참고 (Opus Clip 대안) | S-3 (벤치마크) |
| **autocut** | ⭐7,784 | Apache-2.0 | 2024-10 | ✅ | 보강 (텍스트 기반 컷) | S-3 (참고) |

### 2.2 트렌드/주제 발굴 (주제 2)

| 도구 | GitHub 별 | 라이선스 | 활발도 | 한국어 | 대체/보강 | 적용 모듈 |
|---|---|---|---|---|---|---|
| **google-api-python-client** | ⭐8,900 | Apache-2.0 | 2026-07 | — | 보강 (공식 클라이언트) | S-1 |
| **pytrends** | ⭐3,731 | Apache-2.0 | ⚠️ **2024-08 (아카이브)** | ✅ | ⚠️ 보조만 (비공식 API) | S-1 (보조) |
| **Trending-YouTube-Scraper** | ⭐369 | BSD-2-Clause | 2020-05 | — | ❌ 구식 — 미사용 권장 | — |
| **Invidious API** | ⭐22,630 | AGPL-3.0 | 2026-08 | — | 참고 (대체 프론트엔드) | S-1 (참고) |

### 2.3 TTS/음성 (주제 3)

| 도구 | GitHub 별 | 라이선스 | 활발도 | 한국어 | 대체/보강 | 적용 모듈 |
|---|---|---|---|---|---|---|
| **edge-tts** | ⭐11,725 | ⚠️ **LGPL-3.0**(대부분) | 2026-03 | ✅ (ko-KR 10+ 목소리) | ⚠️ 현행 채택 — LGPL 준수 필요 | S-3 |
| **MeloTTS** | ⭐7,579 | MIT | 2024-12 | ✅ **한국어 지원** | 🆕 **대체 후보 추가 권장** | S-3 |
| **Piper** | ⭐11,278 | MIT | ⚠️ **2025-10 아카이브** | ⚠️ 커뮤니티 모델만 | ⚠️ 기획 표기 부정확 — piper1-gpl 계승 | S-3 |
| **piper1-gpl** | ⭐5,121 | GPL-3.0 | 2026-08 | ⚠️ 커뮤니티 모델 | 🆕 후속 확인 | S-3 |
| **Kokoro** | ⭐8,414 | Apache-2.0 | 2025-08 | ❌ **한국어 미지원** (8개 언어) | ⚠️ 기획 표기 부정확 | S-3 |
| **Coqui TTS** | ⭐45,896 | MPL-2.0 | 2024-08 (사실상 중단) | ✅ (XTTS) | ⚠️ 회사 해체 — idiap fork로 계승 | S-3 |
| **gTTS** | ⭐2,626 | MIT | 2026-04 | ✅ | 보강 (edge-tts와 동일 비공식 성격) | S-3 |
| **OpenVoice** | ⭐37,144 | MIT | 2025-04 | ⚠️ | 참고 (음성 복제 — 필요 시) | S-3 |
| **bark** | ⭐39,238 | MIT | 2024-08 | ❌ | 참고 (생성형 오디오) | S-3 |
| **F5-TTS** | ⭐15,119 | MIT(코드)/CC-BY-NC(모델) | 2026-07 | ❌ 공식 미지원 | 참고 (제로샷 음성 복제) | S-3 |
| **Fish-Speech** | ⭐32,186 | ⚠️ 비상업(연구용) | 2026-08 | ✅ | ❌ 상업 사용 제한 | S-3 |
| **ChatTTS** | ⭐39,772 | AGPL-3.0 | 2026-04 | ❌ (중·영) | ❌ | — |

### 2.4 자막/캡션 (주제 4)

| 도구 | GitHub 별 | 라이선스 | 활발도 | 한국어 | 대체/보강 | 적용 모듈 |
|---|---|---|---|---|---|---|
| **openai-whisper** | ⭐107,250 | MIT | 2026-07 | ✅ WER 8~13% | 보강 (자막 생성) | S-3·K-2 |
| **faster-whisper** | ⭐24,900 | MIT | 2025-11 | ✅ | 보강 (CTranslate2 가속) | S-3 |
| **whisperX** | ⭐23,569 | BSD-2-Clause | 2026-07 | ✅ | 보강 (단어 타임스탬프·화자분리) | S-3 |
| **auto-subtitle** | ⭐2,275 | MIT | 2024-07 | — | 보강 (자막 오버레이) | S-3 |
| **VideoLingo** | ⭐18,149 | Apache-2.0 | 2026-07 | ✅ | 보강 (자막 절단·번역·더빙) | S-3 |
| **VideoCaptioner** | ⭐15,628 | GPL-3.0 | 2026-07 | ✅ | 보강 (LLM 자막) | S-3 |
| **pysubs2** | ⭐436 | MIT | 2026-07 | — | 보강 (SRT/VTT 파싱) | S-3·K-3 |

### 2.5 KDP 전자책 생성 (주제 5)

| 도구 | GitHub 별 | 라이선스 | 활발도 | 한국어 | 대체/보강 | 적용 모듈 |
|---|---|---|---|---|---|---|
| **ebooklib** | ⭐1,801 | ⚠️ **AGPL-3.0** | 2026-07 | — | ⚠️ 현행 채택 — AGPL 주의 | K-3 |
| **pypub** | ⭐285 | MIT | 2023-07 | — | 🆕 대안 (간단 EPUB, MIT) | K-3 |
| **pandoc** | ⭐45,863 | GPL-2.0 | 2026-08 | — | 보강 (MD→EPUB/DOCX) | K-3 |
| **calibre** | ⭐25,634 | GPL-3.0 | 2026-08 | ✅ | 현행 채택 (ebook-convert) | K-3 |
| **epubcheck** | ⭐1,946 | BSD-3-Clause | 2026-03 (v5.3.0) | — | 현행 채택 | K-3 |
| **Sigil** | ⭐6,925 | GPL-3.0 | 2026-08 | — | 참고 (GUI 에디터) | K-3 |
| **auto-ebook-generator** | ⭐6 | ⚠️ 라이선스 없음 | 2026-08 | — | ⚠️ 기획 참고 — 라이선스 없어 채택 곤란 | K-2 |
| **storycraftr** | ⭐156 | MIT | 2026-03 | — | 참고 (AI 책 CLI) | K-2 |
| **mdBook** | ⭐22,071 | MPL-2.0 | 2026-08 | — | 참고 (웹 책 — EPUB 아님) | — |

### 2.6 표지/디자인 (주제 6)

| 도구 | GitHub 별 | 라이선스 | 활발도 | 한국어 | 대체/보강 | 적용 모듈 |
|---|---|---|---|---|---|---|
| **Pillow** | ⭐13,752 | HPND(BSD류) | 2026-08 | — | 현행 채택 유지 | K-3 |
| **ImageMagick** | ⭐17,163 | ImageMagick 라이선스 | 2026-08 | — | 보강 (CLI 이미지 처리) | K-3 |
| **3d-book-image-css-generator** | ⭐658 | MIT | 2023-04 | — | 🆕 쇼츠용 3D 책 이미지 | S-5·K-3 |

### 2.7 책 홍보/메타데이터 (주제 7)

| 도구 | GitHub 별 | 라이선스 | 활발도 | 한국어 | 대체/보강 | 적용 모듈 |
|---|---|---|---|---|---|---|
| **OpenLibrary API** | ⭐6,603 (openlibrary) | AGPL-3.0(서버) | 2026-08 | ✅ | 🆕 무료 메타데이터 API | K-1·K-4 |
| **Google Books API** | — (구글 서비스) | 무료 API | 상시 | ✅ | 🆕 무료 메타데이터 API | K-1·K-4 |
| **isbnlib** | ⭐279 | LGPL-3.0 | 2024-08 | — | 🆕 ISBN 검증·변환 | K-1·K-4 |
| **amazon-scraper-python** | ⭐878 | MIT | 2020-10 | — | ⚠️ 구식 — 아마존 ToS 리스크 | K-1 (참고만) |
| **tiktok-scraper** | ⭐5,166 | 없음 | 2023-05 | — | ⚠️ ToS 리스크 | S-1 (참고만) |

### 2.8 파이프라인 보강 (주제 8)

| 도구 | GitHub 별 | 라이선스 | 활발도 | 한국어 | 대체/보강 | 적용 모듈 |
|---|---|---|---|---|---|---|
| **textstat** | ⭐1,377 | MIT | 2026-02 | — | 🆕 가독성 지표 (QC 보강) | K-2 |
| **sentence-transformers** | ⭐19,002 | Apache-2.0 | 2026-08 | ✅ | 🆕 챕터 중복 검출 (임베딩) | K-2 |
| **LanguageTool** | ⭐14,796 | LGPL-2.1 | 2026-08 | ❌ 한국어 미지원 | 🆕 영어 문법 검사 | K-2 |
| **language-tool-python** | ⭐529 | GPL-3.0 | 2026-08 | ❌ | 🆕 LT 파이썬 래퍼 | K-2 |
| **py-hanspell** | ⭐360 | MIT | 2024-04 | ✅ | 🆕 한국어 맞춤법 (네이버 비공식 API) | K-2·S-3 |
| **PySceneDetect** | ⭐5,098 | BSD-3-Clause | 2026-08 | — | 🆕 장면 전환 감지 (쇼츠 컷) | S-3 |
| **Prefect** | ⭐23,619 | Apache-2.0 | 2026-08 | — | 🆕 배치 오케스트레이션 | S-4·K-4 |
| **n8n** | ⭐200,593 | ⚠️ Sustainable Use(fair-code) | 2026-08 | — | ⚠️ OSI 아님 — 무료 사용은 가능 | S-4 (참고) |
| **Dify** | ⭐152,430 | ⚠️ Dify 라이선스(fair-code) | 2026-08 | ✅ | ⚠️ 참고 | — |
| **Apache Airflow** | ⭐46,477 | Apache-2.0 | 2026-08 | — | 참고 (과함) | — |
| **Huginn** | ⭐49,789 | MIT | 2026-08 | — | 참고 (에이전트 자동화) | — |

---

## 3. 도구별 상세 (8개 주제)

### 주제 1. 유튜브 쇼츠 자동화

#### 1.1 yt-dlp (⭐184,395 · Unlicense · 활발)
- **기능**: 유튜브·4,000+ 사이트 오디오/비디오 다운로더. 자막·메타데이터·재생목록 지원
- **라이선스**: Unlicense (퍼블릭 도메인) — 상업 사용 무제한
- **활발도**: ⭐184k, 2026-08 커밋, 포크 15.9k — **가장 활발한 다운로더**
- **한국어**: 해당 없음 (다운로더)
- **기존 기획 대비**: `14-shorts.md` §2.2는 yt-dlp를 "ToS 위반 리스크"로 제한적 사용만 명시 — **유지 타당** (2020 RIAA DMCA 선례). 단, 파일럿에서 **참고 영상 다운로드(소재 분석용)** 용도로는 제한적 사용 가능
- **적용 모듈**: S-1 (보조·제한적), S-3 (참고 영상 확보 시)

#### 1.2 youtube-transcript-api (⭐8,039 · MIT · 2026-05)
- **기능**: 유튜브 자막/트랜스크립트를 API로 가져옴 (자동 생성 자막 포함). 비공식 API지만 널리 사용
- **라이선스**: MIT — 상업 사용 가능
- **활발도**: 2026-05 커밋, 이슈 30건 — **활발**
- **기존 기획 대비**: `14-shorts.md` §2.1은 `captions.list`(API v3, 50 units) "미사용 권장" — **이 도구로 자막 수집 시 쿼터 절약 + 자막 기반 소재 발굴 가능** (검색 대신 자막 키워드 집계)
- **적용 모듈**: S-1 (자막 수집), S-3 (스크립트 참고)

#### 1.3 moviepy (⭐14,848 · MIT · 2026-08)
- **기능**: Python 비디오 편집 — 클립 자르기·합치기·텍스트 오버레이·오디오 믹싱
- **라이선스**: MIT — 상업 사용 가능
- **활발도**: 2026-08 커밋 — 활발 (moviepy2로 이전 중, 기존 1.x 유지보수)
- **기존 기획 대비**: 기획은 "영상 편집(Shotcut/CapCut)은 사용자 수동" — **moviepy를 활용한 자동 편집은 정책 리스크 없이 가능** (업로드만 수동). 예: 자막 오버레이 영상 자동 생성 → 사용자가 Shotcut으로 최종 편집
- **적용 모듈**: S-3 (자동 편집 보조), S-5 (3D 책 이미지 영상화)

#### 1.4 FFmpeg (⭐63,295 · LGPL/GPL 이중 · 2026-08)
- **기능**: 미디어 처리 표준 — 트랜스코딩·컷·자막 합성·오디오 추출
- **라이선스**: LGPL(대부분 빌드) / GPL(일부 빌드) — 상업 사용 가능 (LGPL 준수 시)
- **활발도**: 2026-08 커밋 — **표준 유지**
- **적용 모듈**: S-3 (moviepy 백엔드), K-3 (표지 리사이즈 등)

#### 1.5 Remotion (⭐56,297 · ⚠️ 회사 라이선스 · 2026-08)
- **기능**: React로 비디오를 코드로 제작 — 프로그래매틱 모션 그래픽·애니메이션
- **라이선스**: ⚠️ **완전 오픈소스 아님** — 개인/소규모 회사는 무료, **일정 규모 이상 회사는 유료 라이선스 필요** (2-tier)
- **활발도**: 2026-08 커밋 — 활발
- **기존 기획 대비**: ⚠️ **기획 문서에서 "오픈소스"로 오인하지 않도록 주의** — 쇼츠 자동화에 Remotion 채택 시 라이선스 비용 검토 필요. **파일럿 단계에서는 불필요** (간단 카드형 쇼츠는 moviepy/자막으로 충분)
- **적용 모듈**: S-3 (검토만 — 고급 애니메이션 필요 시)

#### 1.6 Shotcut (⭐14,918 · GPL-3.0 · 2026-08)
- **기능**: 크로스플랫폼 GUI 영상 편집기 (Qt)
- **라이선스**: GPL-3.0 — 상업 사용 가능 (배포 시 GPL 준수)
- **활발도**: 2026-08 커밋 — 활발
- **기존 기획 대비**: 기획의 "사용자 수동 편집 도구"로 **현행 유지** — CLI 자동화는 제한적 (프로젝트 파일 XML 기반)
- **적용 모듈**: S-3 (사용자 도구)

#### 1.7 AI-Youtube-Shorts-Generator (⭐4,591 · ⚠️ 라이선스 없음 · 2026-07)
- **기능**: 롱폼 영상 → 9:16 쇼츠 자동 변환 (LLM 하이라이트 검출 + Whisper 자막 + 자동 세로 크롭). Opus Clip/Vidyo.ai 대안
- **라이선스**: ⚠️ **라이선스 파일 없음** — 상업 사용 법적 불명확
- **활발도**: 2026-07 커밋 — 활발
- **기존 기획 대비**: 기획은 "스크립트 생성까지 자동화, 편집 수동" — 이 도구는 **편집까지 자동화**하는 참고 사례. 단, 라이선스 불명확으로 **직접 채택보다 아키텍처 참고** 권장
- **적용 모듈**: S-3 (벤치마크·아키텍처 참고)

#### 1.8 autocut (⭐7,784 · Apache-2.0 · 2024-10)
- **기능**: 텍스트 편집기처럼 영상 자르기 — 자막 기반 컷·제거 (중국어 중심, 한국어 자막 지원)
- **라이선스**: Apache-2.0 — 상업 사용 가능
- **활발도**: 2024-10 — 개발 소강
- **적용 모듈**: S-3 (참고 — 자막 기반 컷 자동화)

---

### 주제 2. 유튜브 트렌드/인기 주제 발굴

#### 2.1 google-api-python-client (⭐8,900 · Apache-2.0 · 2026-07)
- **기능**: Google 공식 API 클라이언트 (YouTube Data API v3 포함)
- **라이선스**: Apache-2.0 — 상업 사용 가능
- **활발도**: 2026-07 커밋 — 활발
- **기존 기획 대비**: `trd.md` §4.1 YouTube API 연동 시 **공식 클라이언트 사용 권장** (자체 HTTP 구현 대신) — 쿼터·에러·백오프 처리 표준화
- **적용 모듈**: S-1 (핵심)

#### 2.2 pytrends (⭐3,731 · Apache-2.0 · ⚠️ 2024-08 아카이브)
- **기능**: Google Trends 비공식 API (키워드 트렌드·인기 검색어)
- **라이선스**: Apache-2.0
- **활발도**: ⚠️ **2024-08 마지막 커밋, 아카이브됨** — Google HTML 구조 변경 시 깨질 수 있음
- **한국어**: 지원 (지역 필터)
- **기존 기획 대비**: 기획은 "네이버 '곧 뜰' + 유튜브 API"만 사용 — **pytrends 추가는 선택적**. 아카이브 상태라 **주 소스로 부적합**, 보조·교차 검증용으로만
- **적용 모듈**: S-1 (보조·참고)

#### 2.3 Invidious (⭐22,630 · AGPL-3.0 · 2026-08)
- **기능**: 유튜브 대체 프론트엔드 + 공개 API (트렌딩·검색·영상 메타)
- **라이선스**: AGPL-3.0 — 서비스 배포 시 소스 공개
- **활발도**: 2026-08 — 활발
- **기존 기획 대비**: API v3 쿼터 절약 대안이지만 **ToS 리스크·AGPL 조건** — 기획의 "API v3 우선" 원칙 유지, 참고만
- **적용 모듈**: S-1 (참고)

---

### 주제 3. TTS/음성 (⚠️ 기획 S-4 게이트 재검토 필요)

#### 3.1 edge-tts (⭐11,725 · ⚠️ LGPL-3.0 · 2026-03)
- **기능**: Microsoft Edge 온라인 TTS 서비스 비공식 API — **한국어 10+ 목소리** (ko-KR-SunHiNeural, InJoonNeural, HyunsuNeural 등)
- **라이선스**: ⚠️ **실측 결과 — 대부분 파일 LGPL-3.0, srt_composer.py만 MIT** (기존 기획의 "오픈소스·무료" 표기는 부정확). 비공식 API(MS 서버 활용) 특성은 그대로 — **상업 쇼츠 음성 사용 시 MS 약관 위반 소지 유지**
- **활발도**: 2026-03 커밋, 이슈 3건 — 유지보수 소강
- **기존 기획 대비**: ⚠️ **`trd.md`·`14-shorts.md` 라이선스 표기 수정 필요** — "LGPL-3.0 (srt_composer는 MIT)" 명시. 파일럿 전 게이트에서 **LGPL 준수(고지·동적 링크) + 상업성 재검토** 필요
- **적용 모듈**: S-3 (현행), S-4 (게이트 재검토)

#### 3.2 MeloTTS (⭐7,579 · MIT · 2024-12) — 🆕 대체 후보 추가 권장
- **기능**: 다국어 TTS — **영어·스페인어·프랑스어·중국어·일본어·한국어 지원** (MyShell.ai)
- **라이선스**: **MIT** — 상업 사용 무제한
- **활발도**: 2024-12 마지막 커밋 — 소강 (하지만 라이선스·한국어 지원으로 가치)
- **한국어**: ✅ **공식 지원** (음성 샘플 제공)
- **기존 기획 대비**: 🆕 **`14-shorts.md` §3.3의 대체재 검토 목록에 MeloTTS 추가 강력 권장** — Kokoro/Piper가 한국어 미지원/아카이브인 상황에서 **한국어 지원 + MIT 라이선스**를 갖춘 유일한 경량 오픈 TTS. CPU 실시간 추론 가능
- **적용 모듈**: S-3 (대체 후보), S-4 (게이트)

#### 3.3 Piper (⭐11,278 · MIT · ⚠️ 2025-10 아카이브) / piper1-gpl (⭐5,121 · GPL-3.0 · 2026-08)
- **기능**: 로컬 신경망 TTS (경량, 오프라인)
- **라이선스**: Piper = MIT (아카이브), piper1-gpl = **GPL-3.0** (계승)
- **활발도**: ⚠️ **Piper는 2025-10 아카이브** — 공식 유지보수 중단, **piper1-gpl로 계승** (별도 그룹)
- **한국어**: ⚠️ **공식 모델 없음** — 커뮤니티 모델(neurlang/piper-onnx-kss-korean 등)만 존재, 품질·지원 보장 없음
- **기존 기획 대비**: ⚠️ **`14-shorts.md` §3.3 "Piper(한국어 모델 존재)" 표기 부정확** — 공식 한국어 모델은 없고 커뮤니티 모델만. 계승자인 piper1-gpl은 GPL-3.0이라 상업 파이프라인 내장 시 주의
- **적용 모듈**: S-3 (대체 후보 — 커뮤니티 모델 검증 시)

#### 3.4 Kokoro (⭐8,414 · Apache-2.0 · 2025-08)
- **기능**: 경량(82M) 고품질 TTS — Apache-2.0 라이선스 가중치
- **라이선스**: Apache-2.0 — 상업 사용 가능
- **활발도**: 2025-08 마지막 커밋 — 개발 소강
- **한국어**: ❌ **미지원** — 공식 9개 코드 (미영·영영·스페인·프랑스·힌디·이탈리아·일본·브라질포르투갈·중국어) — **한국어 없음** (실측 확인)
- **기존 기획 대비**: ⚠️ **`14-shorts.md` §3.3 "Kokoro(오픈소스 TTS)" 표기 부정확** — 한국어 쇼츠에는 **부적합** (영어 KDP 쇼츠에는 유효)
- **적용 모듈**: S-3 (영어 KDP 쇼츠용 대체 후보), S-4 (게이트)

#### 3.5 Coqui TTS (⭐45,896 · MPL-2.0 · 2024-08)
- **기능**: 딥러닝 TTS 툴킷 — XTTS 다국어 음성 복제 포함
- **라이선스**: MPL-2.0 (파일 수준 카피레프트) — 상업 사용 가능 (수정 파일 공개 조건)
- **활발도**: ⚠️ 2024-08 마지막 커밋 — **Coqui 회사 해체** (2024), 커뮤니티 fork(idiap/coqui-ai-TTS, ⭐2.3k)로 계승
- **한국어**: ✅ XTTS v2 한국어 지원
- **적용 모듈**: S-3 (참고 — 음성 복제 필요 시)

#### 3.6 gTTS (⭐2,626 · MIT · 2026-04)
- **기능**: Google Translate TTS 비공식 API
- **라이선스**: MIT
- **한국어**: ✅
- **기존 기획 대비**: edge-tts와 동일하게 **비공식 API 특성** — 대체 후보로는 MeloTTS가 우선
- **적용 모듈**: S-3 (참고)

#### 3.7 기타 TTS (참고)
| 도구 | 별 | 라이선스 | 한국어 | 비고 |
|---|---|---|---|---|
| OpenVoice | ⭐37,144 | MIT | ⚠️ | 음성 복제 (MyShell) |
| bark | ⭐39,238 | MIT | ❌ | 생성형 오디오 — 한국어 미지원 |
| F5-TTS | ⭐15,119 | MIT(코드)/CC-BY-NC(모델) | ❌ | 제로샷 복제 — **모델 비상업** |
| Fish-Speech | ⭐32,186 | ⚠️ 비상업 | ✅ | S2 모델 연구용 — **상업 제한** |
| ChatTTS | ⭐39,772 | AGPL-3.0 | ❌ | 중·영 — 한국어 미지원 |

---

### 주제 4. 자막/캡션 자동화

#### 4.1 openai-whisper (⭐107,250 · MIT · 2026-07)
- **기능**: 음성 인식(STT) — 99개 언어, 한국어 WER 8~13% (Tier 2 수준)
- **라이선스**: MIT — 상업 사용 가능
- **활발도**: ⭐107k, 2026-07 커밋 — 매우 활발
- **한국어**: ✅ (WER 8~13%, 일본어·중국어와 유사 Tier 2)
- **기존 기획 대비**: 기획은 자막을 "스크립트에서 생성"만 — **Whisper로 쇼츠 자막 자동 생성** 추가 시 TTS 음성과 정합 가능. 또한 **K-2 QC(챕터 내용 검증)** 에도 활용 가능
- **적용 모듈**: S-3 (자막 생성), K-2 (참고)

#### 4.2 faster-whisper (⭐24,900 · MIT · 2025-11)
- **기능**: CTranslate2 기반 Whisper 가속 — GPU/CPU 모두 4배+ 빠름, 메모리 절약
- **라이선스**: MIT
- **한국어**: ✅ (Whisper 모델 재사용)
- **적용 모듈**: S-3 (자막 생성 — 배치/서버리스에 적합)

#### 4.3 whisperX (⭐23,569 · BSD-2-Clause · 2026-07)
- **기능**: Whisper + 단어 타임스탬프 + 화자 분리(디아라이제이션)
- **라이선스**: BSD-2-Clause
- **한국어**: ✅
- **적용 모듈**: S-3 (단어 단위 자막 스타일링)

#### 4.4 auto-subtitle (⭐2,275 · MIT · 2024-07)
- **기능**: 영상에 자막 자동 생성·오버레이 (Whisper + ffmpeg)
- **라이선스**: MIT
- **적용 모듈**: S-3 (자막 오버레이)

#### 4.5 VideoLingo (⭐18,149 · Apache-2.0 · 2026-07)
- **기능**: 자막 절단·번역·정렬·더빙까지 원스톱 (넷플릭스급)
- **라이선스**: Apache-2.0
- **한국어**: ✅ (번역 대상 지원)
- **적용 모듈**: S-3 (자막 번역 — 한국어↔영어 시너지)

#### 4.6 VideoCaptioner (⭐15,628 · GPL-3.0 · 2026-07)
- **기능**: LLM 기반 자막 생성·교정·번역 (중국 개발, 다국어)
- **라이선스**: GPL-3.0 — 상업 사용 시 파생 배포 조건
- **적용 모듈**: S-3 (참고)

#### 4.7 pysubs2 (⭐436 · MIT · 2026-07)
- **기능**: SRT/VTT/ASS 자막 파싱·생성·변환
- **라이선스**: MIT
- **적용 모듈**: S-3 (자막 파일 처리), K-3 (자막형 전자책 검증)

---

### 주제 5. KDP 전자책 생성 (⚠️ 라이선스 재검토 필요)

#### 5.1 ebooklib (⭐1,801 · ⚠️ AGPL-3.0 · 2026-07)
- **기능**: EPUB2/EPUB3 생성·조작 파이썬 라이브러리
- **라이선스**: ⚠️ **AGPL-3.0** — **상업 배포(특히 SaaS) 시 파생 코드 전체 공개 의무**
- **활발도**: 2026-07 커밋 — 유지보수 중
- **기존 기획 대비**: ⚠️ **`12-kdp.md` §2.1·`trd.md` §1.1의 "오픈소스·무료" 표기 보완 필요** — 내부 파이프라인(개인 사용)으로만 쓰면 AGPL 조건 무해, **Vercel 서버리스에 올려 서비스화하면 AGPL 이슈 발생 가능**. `ebook_builder.py`가 **자체 실행 스크립트로만 동작**하면 문제 없음 — 단, 라이선스 인지·문서 명시 권장
- **대안**: **pypub**(⭐285, MIT) — 간단한 EPUB 생성에 충분. pandoc(GPL-2.0)도 MD→EPUB 지원
- **적용 모듈**: K-3 (현행), 대안 검토 시 K-3

#### 5.2 pypub (⭐285 · MIT · 2023-07) — 🆕 대안 후보
- **기능**: 파이썬으로 EPUB 생성 (간단·가벼움)
- **라이선스**: MIT — 상업 사용 무제한
- **활발도**: 2023-07 — 개발 소강 (하지만 MIT + 단순성으로 충분)
- **적용 모듈**: K-3 (ebooklib AGPL 우려 시 대체)

#### 5.3 pandoc (⭐45,863 · GPL-2.0 · 2026-08)
- **기능**: 범용 마크업 변환기 — MD→EPUB/DOCX/PDF 등
- **라이선스**: GPL-2.0 — CLI 도구로 호출 시 파생 아님 (임베딩 시 주의)
- **적용 모듈**: K-3 (보강 — DOCX 변환), 12-kdp §2.1 "(선택) pandoc (DOCX)" 현행 유지

#### 5.4 calibre (⭐25,634 · GPL-3.0 · 2026-08)
- **기능**: 전자책 관리·변환 (ebook-convert, ebook-polish, ebook-meta)
- **라이선스**: GPL-3.0 — CLI 호출은 파생 아님
- **적용 모듈**: K-3 (현행 — ebook-convert·ebook-polish --check)

#### 5.5 epubcheck (⭐1,946 · BSD-3-Clause · 2026-03)
- **기능**: W3C EPUB 적합성 검사기 (v5.3.0, 2025-09)
- **라이선스**: BSD-3-Clause — 상업 사용 무제한
- **적용 모듈**: K-3 (현행 — Java 필요, 12-kdp §2.1)

#### 5.6 auto-ebook-generator (⭐6 · ⚠️ 라이선스 없음 · 2026-08)
- **기능**: AI 책 생성기 — 아웃라인→드래프트→EPUB/PDF/DOCX
- **라이선스**: ⚠️ **라이선스 파일 없음** — 상업 채택 부적합
- **기존 기획 대비**: ⚠️ **`12-kdp.md` §2 "구조 참고: auto-ebook-generator"는 "구조 참고"로만 유지** — 코드 직접 사용은 라이선스 불명확으로 곤란. **아키텍처(아웃라인→챕터→조립)는 기획과 동일** — 기획의 자체 구현 방향이 타당
- **적용 모듈**: K-2 (구조 참고만)

#### 5.7 storycraftr (⭐156 · MIT · 2026-03)
- **기능**: AI 책 작성 CLI (아웃라인·챕터·워드빌딩)
- **라이선스**: MIT
- **적용 모듈**: K-2 (참고 — 자체 파이프라인 대체 불필요)

---

### 주제 6. KDP 표지/디자인

#### 6.1 Pillow (⭐13,752 · HPND(BSD류) · 2026-08)
- **기능**: 파이썬 이미지 처리 — 6×9 표지 텍스트 오버레이 (기획 현행)
- **라이선스**: HPND (BSD 계열) — 상업 사용 무제한
- **적용 모듈**: K-3 (현행 유지)

#### 6.2 ImageMagick (⭐17,163 · ImageMagick 라이선스 · 2026-08)
- **기능**: CLI 이미지 처리 — 리사이즈·합성·필터
- **라이선스**: ImageMagick 라이선스 (허용적)
- **적용 모듈**: K-3 (보강 — 서버리스 제약 시 CLI 폴백)

#### 6.3 3d-book-image-css-generator (⭐658 · MIT · 2023-04) — 🆕 추가 후보
- **기능**: 책 표지 이미지에서 3D 책 이미지 생성 (HTML/CSS) — 쇼츠·소셜용
- **라이선스**: MIT
- **기존 기획 대비**: 🆕 **KDP↔쇼츠 시너지(12-kdp §9)에 활용** — 책 챕터 쇼츠에서 3D 책 표지로 시각적 매력 ↑
- **적용 모듈**: S-5 (신규 — 쇼츠용 3D 책 이미지), K-3 (보강)

---

### 주제 7. 책 홍보/메타데이터

#### 7.1 OpenLibrary API (⭐6,603 · AGPL-3.0(서버) · 2026-08)
- **기능**: 무료 도서 메타데이터 API (ISBN·제목·저자·표지) — 인터넷 아카이브
- **라이선스**: 서버 AGPL-3.0, **API 사용은 무료** (API 클라이언트는 파생 아님)
- **한국어**: ✅ (한국 서적 메타 일부)
- **적용 모듈**: K-1 (주제 검증), K-4 (48h 모니터링 — 표지·메타 확인)

#### 7.2 Google Books API (무료 · 상시)
- **기능**: 도서 메타데이터·검색 API (ISBN 조회)
- **라이선스**: 무료 API (사용량 제한)
- **한국어**: ✅
- **적용 모듈**: K-1 (주제 검증 — 아마존 스냅샷 대안), K-4 (모니터링)

#### 7.3 isbnlib (⭐279 · LGPL-3.0 · 2024-08)
- **기능**: ISBN 검증·정규화·변환·메타데이터 조회 (여러 소스: OpenLibrary·Google Books 등)
- **라이선스**: LGPL-3.0 — 동적 링크 시 상업 사용 가능
- **적용 모듈**: K-1 (ISBN 처리), K-4 (출간 후 ISBN 확인)

#### 7.4 아마존 스크래퍼류 (amazon-scraper-python ⭐878 · MIT · 2020-10 / tiktok-scraper ⭐5,166)
- **기능**: 아마존/틱톡 제품·콘텐츠 스크래핑
- **라이선스**: MIT (amazon-scraper-python), 라이선스 없음 (tiktok-scraper)
- ⚠️ **리스크**: 아마존·틱톡 ToS 위반 가능 — 기획의 "스냅샷 방식 유지(제한적)" 원칙 유지, 스크래퍼 직접 채택 비권장
- **적용 모듈**: K-1 (참고만)

#### 7.5 BookTok 분석 (공개 데이터)
- **기능**: 오픈소스 BookTok 분석 도구는 사실상 미성숙 (검색 결과 대부분 저품질·중단)
- **기존 기획 대비**: **BookTok 트렌드는 수동 리서치(12-kdp §9)로 유지** — 별도 오픈소스 발굴 불필요
- **적용 모듈**: S-5 (수동)

---

### 주제 8. 파이프라인 보강 (autostudio 패턴 적용)

#### 8.1 textstat (⭐1,377 · MIT · 2026-02) — 🆕 QC 보강
- **기능**: 가독성 지표 (Flesch-Kincaid 등) — 영어 텍스트 품질
- **라이선스**: MIT
- **기존 기획 대비**: 🆕 **K-2 QC 8항목 보강** — 챕터 길이(±20%)에 **가독성 스코어** 추가 (영어 워크북 대상)
- **적용 모듈**: K-2 (QC #5 길이 보강)

#### 8.2 sentence-transformers (⭐19,002 · Apache-2.0 · 2026-08) — 🆕 QC 보강
- **기능**: 문장 임베딩 — 의미 유사도 (paraphrase-multilingual-MiniLM = 50+ 언어)
- **라이선스**: Apache-2.0
- **한국어**: ✅ (다국어 모델)
- **기존 기획 대비**: 🆕 **K-2 QC #4(챕터 간 중복)의 embedding 유사도 구현에 직접 활용** — 기획이 "embedding 유사도 ≥ 0.8"을 명시했으나 구체 도구 미지정 → **sentence-transformers 채택 권장**
- **적용 모듈**: K-2 (QC #4)

#### 8.3 LanguageTool (⭐14,796 · LGPL-2.1 · 2026-08) — 🆕 영어 QC
- **기능**: 25+ 언어 문법·스타일 검사 (Java 서버 + 파이썬 래퍼)
- **라이선스**: LGPL-2.1 — 상업 사용 가능 (동적 링크)
- **한국어**: ❌ **미지원** (실측 확인 — 지원 언어 목록에 없음)
- **적용 모듈**: K-2 (영어 챕터 문법 검사), S-3 (영어 스크립트 검수)

#### 8.4 language-tool-python (⭐529 · GPL-3.0 · 2026-08)
- **기능**: LanguageTool 파이썬 래퍼 (jxmorris12)
- **라이선스**: ⚠️ GPL-3.0 — 파이썬 코드 임베딩 시 GPL 조건
- **적용 모듈**: K-2 (참고 — GPL 주의, HTTP API 호출 방식이면 무해)

#### 8.5 py-hanspell (⭐360 · MIT · 2024-04) — 🆕 한국어 QC
- **기능**: 파이썬 한글 맞춤법 검사 (네이버 맞춤법 검사기 비공식 API)
- **라이선스**: MIT
- **한국어**: ✅ (한국어 전용)
- ⚠️ **주의**: 네이버 비공식 API — 부하 주의·변경 시 깨질 수 있음
- **적용 모듈**: K-2 (한국어 책 QC), S-3 (한국어 스크립트 검수)

#### 8.6 PySceneDetect (⭐5,098 · BSD-3-Clause · 2026-08) — 🆕 쇼츠 편집
- **기능**: 영상 장면 전환 감지 — 쇼츠 컷 포인트 자동화
- **라이선스**: BSD-3-Clause
- **적용 모듈**: S-3 (편집 보조 — 자동 컷 포인트)

#### 8.7 워크플로우 오케스트레이션
| 도구 | 별 | 라이선스 | 비고 | 적용 |
|---|---|---|---|---|
| **Prefect** | ⭐23,619 | Apache-2.0 | 파이썬 배치 오케스트레이션 — GH Actions보다 유연 | S-4·K-4 (선택) |
| **Apache Airflow** | ⭐46,477 | Apache-2.0 | 과함 — 오버엔지니어링 | — |
| **n8n** | ⭐200,593 | ⚠️ Sustainable Use | OSI 아님 — 무료 사용 가능, 상업 SaaS 시 제한 | S-4 (참고) |
| **Dify** | ⭐152,430 | ⚠️ Dify 라이선스 | AI 워크플로우 — fair-code | — |
| **Huginn** | ⭐49,789 | MIT | 에이전트 자동화 — 모니터링 | S-4 (참고) |

> **기존 기획 대비**: 기획은 GH Actions 배치 + Vercel 서버리스(60초) 구조 — **Prefect는 추가 의존성 없이 유지보수 단순화**에만 유효. 파이프라인 규모(매일 1회)에선 **기존 GH Actions 유지가 최선** (Prefect는 참고만)

---

## 4. 기존 기획 대비 개선 제안 (우선순위별)

### 🥇 P1 — 기획 문서 수정 필요 (오류·부정확 정정)

| # | 제안 | 대상 문서 | 근거 (실측) |
|---|---|---|---|
| P1-1 | **edge-tts 라이선스 표기 수정**: "오픈소스·무료" → **"LGPL-3.0(대부분)+MIT(srt), 비공식 API — 상업 쇼츠 사용 시 MS 약관 위반 소지"** | 14-shorts §3.3·§8, trd.md §1.1·§4.3 | GitHub LICENSE 실측: LGPL-3.0 + srt_composer MIT |
| P1-2 | **ebooklib 라이선스 표기 보완**: "오픈소스·무료" → **"AGPL-3.0 — 내부 파이프라인 사용 OK, 외부 SaaS 서비스화 시 파생 공개 의무"** | 12-kdp §2.1, trd.md §1.1 | GitHub 실측: AGPL-3.0 |
| P1-3 | **TTS 대체재 목록 갱신**: Piper(아카이브·공식 한국어 모델 없음)·Kokoro(한국어 미지원) → **MeloTTS(MIT·한국어 지원) 추가, piper1-gpl(GPL-3.0) 명시** | 14-shorts §3.3·§7, trd.md §4.3 | GitHub 실측 + Kokoro README 언어 목록 |
| P1-4 | **pytrends 상태 명시**: 아카이브(2024-08) → "보조·참고용으로만, 주 소스는 API v3" | 14-shorts §2 (선택) | GitHub 실측: archived=True |

### 🥈 P2 — 기능 보강 (기존 모듈 확장)

| # | 제안 | 적용 모듈 | 도구 | 근거 |
|---|---|---|---|---|
| P2-1 | **QC #4 챕터 중복 검출 구현체 확정**: sentence-transformers(paraphrase-multilingual-MiniLM) 사용 | K-2 (QC #4) | sentence-transformers | 기획이 "embedding ≥ 0.8"만 명시 — 구체 도구 미지정 |
| P2-2 | **QC #5 길이 + 가독성**: textstat(Flesch-Kincaid) 추가 | K-2 (QC #5) | textstat | 영어 워크북 품질 게이트 강화 |
| P2-3 | **영어 챕터 문법 검사**: LanguageTool(HTTP API) 추가 — 한국어는 py-hanspell | K-2 (QC), S-3 | LanguageTool·py-hanspell | 한국어는 LanguageTool 미지원 → 병행 |
| P2-4 | **쇼츠 자막 자동 생성**: faster-whisper로 음성→자막 (edge-tts 음성과 정합) | S-3 | faster-whisper | 한국어 WER 8~13% — 자막 병행 강화 |
| P2-5 | **3D 책 이미지**: 3d-book-image-css-generator로 쇼츠용 표지 이미지 | S-5 (신규) | 3d-book-image-css-generator | KDP↔쇼츠 시너지 시각화 |

### 🥉 P3 — 참고·선택 (파일럿 후 검토)

| # | 제안 | 적용 | 도구 | 비고 |
|---|---|---|---|---|
| P3-1 | youtube-transcript-api로 자막 기반 소재 발굴 (쿼터 절약) | S-1 | youtube-transcript-api | captions.list(50 units) 대신 비공식 API — ToS 검토 필요 |
| P3-2 | google-api-python-client 공식 클라이언트 채택 | S-1 | google-api-python-client | 쿼터·에러 처리 표준화 |
| P3-3 | Remotion 검토 (고급 애니메이션 쇼츠) — 단, 회사 라이선스 비용 확인 | S-3 | Remotion | 파일럿 이후 |
| P3-4 | ebooklib → pypub 대체 검토 (AGPL 회피) | K-3 | pypub | 간단 EPUB 생성에 충분 |
| P3-5 | Prefect 도입 검토 (배치 단순화) | S-4·K-4 | Prefect | 현행 GH Actions 유지가 우선 |
| P3-6 | Invidious API 참고 (쿼터 절약) — AGPL·ToS 주의 | S-1 | Invidious | 참고만 |

---

## 5. 라이선스 종합 리스크 매트릭스

| 도구 | 라이선스 | 상업 사용 | 배포 시 의무 | 비고 |
|---|---|---|---|---|
| yt-dlp | Unlicense | ✅ 무제한 | 없음 | — |
| youtube-transcript-api | MIT | ✅ | 없음 | 비공식 API — ToS 주의 |
| moviepy | MIT | ✅ | 없음 | — |
| FFmpeg | LGPL/GPL | ✅ | LGPL 준수 (빌드별 상이) | — |
| Remotion | 회사 라이선스 | ⚠️ 조건부 (규모별 유료) | 회사 규모 확인 | 완전 오픈 아님 |
| pytrends | Apache-2.0 | ✅ | 없음 | 아카이브 — 비공식 API |
| **edge-tts** | **LGPL-3.0** | ⚠️ LGPL 준수 + 비공식 API | 고지·동적 링크 | **기획 표기 수정 필요** |
| MeloTTS | MIT | ✅ 무제한 | 없음 | **한국어 지원 대체 후보** |
| Piper | MIT | ✅ | 없음 | 아카이브 — 한국어 공식 모델 없음 |
| Kokoro | Apache-2.0 | ✅ | 없음 | 한국어 미지원 |
| Coqui TTS | MPL-2.0 | ✅ | 수정 파일 공개 | 회사 해체 — fork 계승 |
| whisper | MIT | ✅ | 없음 | — |
| faster-whisper | MIT | ✅ | 없음 | — |
| whisperX | BSD-2-Clause | ✅ | 없음 | — |
| **ebooklib** | **AGPL-3.0** | ⚠️ 내부 OK / SaaS 배포 시 파생 공개 | 서비스 시 소스 공개 | **기획 표기 보완 필요** |
| pypub | MIT | ✅ | 없음 | 대안 |
| pandoc | GPL-2.0 | ✅ (CLI 호출) | 임베딩 시 주의 | — |
| calibre | GPL-3.0 | ✅ (CLI 호출) | 임베딩 시 주의 | — |
| epubcheck | BSD-3-Clause | ✅ | 없음 | — |
| Pillow | HPND(BSD류) | ✅ | 없음 | — |
| OpenLibrary API | API 무료 | ✅ | 없음 | 서버 AGPL은 API 사용과 무관 |
| Google Books API | 무료 API | ✅ | 사용량 제한 | — |
| isbnlib | LGPL-3.0 | ✅ | 동적 링크 | — |
| LanguageTool | LGPL-2.1 | ✅ | 동적 링크 | **한국어 미지원** |
| py-hanspell | MIT | ✅ | 없음 | 네이버 비공식 API |
| sentence-transformers | Apache-2.0 | ✅ | 없음 | — |
| textstat | MIT | ✅ | 없음 | — |
| PySceneDetect | BSD-3-Clause | ✅ | 없음 | — |
| Prefect | Apache-2.0 | ✅ | 없음 | — |
| n8n | Sustainable Use | ⚠️ 내부 OK / 상업 SaaS 제한 | OSI 아님 | fair-code |
| Dify | Dify 라이선스 | ⚠️ 참고 | OSI 아님 | — |

---

## 6. 방법론·한계

### 6.1 방법
- **GitHub API 실측** (2026-08-14): 58개 저장소의 별·포크·라이선스(SPDX)·마지막 커밋·아카이브 여부
- **1차 출처 우선**: GitHub 저장소 LICENSE 파일·README 직접 확인 (edge-tts LGPL, ebooklib AGPL, Kokoro 언어 목록, pytrends 아카이브, Piper 아카이브 등)
- **Firecrawl 보조 검증**: 웹 검색·페이지 스크레이프 (한국어 지원 여부, 커뮤니티 모델 존재 등)
- **HuggingFace API**: Kokoro-82M 모델 카드, 파이퍼 커뮤니티 모델 확인

### 6.2 한계
- 별 수·커밋 시점은 2026-08-14 시점 스냅샷 — 이후 변동 가능
- "한국어 지원"은 공식 문서·모델 카드 기준 — 커뮤니티 파생 모델 품질은 별도 검증 필요
- 라이선스 해석은 일반 원칙 수준 — 법률 검토 대체 불가 (특히 edge-tts 비공식 API 상업성, ebooklib AGPL SaaS 배포)
- 아마존·틱톡 스크래핑의 ToS 리스크는 기획 원칙(스냅샷 방식·제한적 사용) 유지

---

## 7. 출처 목록 (실측 기준)

### GitHub API 실측 (별·라이선스·커밋)
- yt-dlp/yt-dlp · jdepoix/youtube-transcript-api · Zulko/moviepy · FFmpeg/FFmpeg · remotion-dev/remotion · mltframework/shotcut
- GeneralMills/pytrends · googleapis/google-api-python-client · iv-org/invidious · mitchelljy/Trending-YouTube-Scraper
- rany2/edge-tts · rhasspy/piper · OHF-Voice/piper1-gpl · hexgrad/kokoro · coqui-ai/TTS · pndurette/gTTS · myshell-ai/MeloTTS · myshell-ai/OpenVoice · suno-ai/bark · SWivid/F5-TTS · fishaudio/fish-speech · 2noise/ChatTTS
- openai/whisper · SYSTRAN/faster-whisper · m-bain/whisperX · m1guelpf/auto-subtitle · Huanshere/VideoLingo · WEIFENG2333/VideoCaptioner · tkarabela/pysubs2 · Breakthrough/PySceneDetect
- aerkalov/ebooklib · wcember/pypub · jgm/pandoc · kovidgoyal/calibre · w3c/epubcheck · Sigil-Ebook/Sigil · Montgomery66/auto-ebook-generator · raestrada/storycraftr
- python-pillow/Pillow · ImageMagick/ImageMagick · scastiel/3d-book-image-css-generator
- internetarchive/openlibrary · xlcnd/isbnlib · tducret/amazon-scraper-python · drawrowfly/tiktok-scraper
- textstat/textstat · UKPLab/sentence-transformers · languagetool-org/languagetool · jxmorris12/language_tool_python · ssut/py-hanspell · prefecthq/prefect · n8n-io/n8n · langgenius/dify · apache/airflow · huginn/huginn

### 라이선스·한국어 지원 실측 (LICENSE 파일·README)
- [edge-tts LICENSE (LGPL-3.0 + MIT)](https://github.com/rany2/edge-tts/blob/master/LICENSE)
- [ebooklib (AGPL-3.0)](https://github.com/aerkalov/ebooklib)
- [Kokoro README — 언어 목록](https://github.com/hexgrad/kokoro) (한국어 없음 실측)
- [MeloTTS README — 한국어 음성 샘플](https://github.com/myshell-ai/MeloTTS)
- [Piper 아카이브 공지](https://github.com/rhasspy/piper) · [piper1-gpl](https://github.com/OHF-Voice/piper1-gpl)
- [pytrends 아카이브](https://github.com/GeneralMills/pytrends)
- [Azure 한국어 TTS 목소리 (ko-KR 10종)](https://json2video.com/ai-voices/azure/languages/korean/)
- [Piper 커뮤니티 한국어 모델 (neurlang)](https://huggingface.co/neurlang/piper-onnx-kss-korean)
- [Whisper 한국어 WER (8~13%)](https://vexascribe.com/how-accurate-is-whisper)
- [LanguageTool 지원 언어 (한국어 없음)](https://dev.languagetool.org/languages)
- [n8n Sustainable Use License](https://github.com/n8n-io/n8n/blob/master/LICENSE.md)
- [OpenLibrary API](https://openlibrary.org/developers/api) · [Google Books API](https://developers.google.com/books)
- [epubcheck v5.3.0 릴리스](https://github.com/w3c/epubcheck/releases)

---

*작성: 리서치팀 · 상태: 오픈소스 도구 조사 완료 (2026-08-14) · 상위: plan.md·trd.md · 대상: docs/planning/14-shorts-pipeline.md · 12-kdp-pipeline.md*
