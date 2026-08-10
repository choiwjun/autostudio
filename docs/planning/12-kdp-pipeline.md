# 12. KDP 자동 출간 파이프라인 (Phase K)

> 상태: 설계 확정 (2026-08-10) · 관련: `11-fortune-channel.md`(수익화 로드맵), autostudio 기존 자산 재활용

## 1. 목적

autostudio의 키워드 발굴·초안 파이프라인을 **아마존 KDP 전자책 출간**에 확장. "뜨는 키워드 = 책 주제" 공식으로 롱테일 수익원 추가 (애드포스트·쇼핑커넥트와 병행).

### 시장 검증 (2026-08-10 실측)
- Kindle 전자책 베스트셀러는 로맨스/스릴러/리터지 소설이 압도적 (Top 30의 ~90%)
- KDP 수익 공식: **시리즈 확장**(Dungeon Crawler Carl 1~6권 전부 Top 30) + **저가 볼륨**(Freida McFadden ~$1 스릴러)
- 자동화 궁합: 구조화 비소설(워크북/가이드)이 성공 확률·AI 적합성 최고, 소설은 품질·정책 리스크

## 2. 파이프라인 단계별 오픈소스 배치

| 단계 | 배치 오픈소스 | 자체 구현/기존 자산 | 비고 |
|---|---|---|---|
| 1. 주제 선정 | — (아마존 공개 API 없음) | autostudio v20 '곧 뜰' 프리셋 + 아마존 검색 경쟁도 스냅샷 | `kdp_research.py` |
| 2. 책 아웃라인 | 구조 참고: `auto-ebook-generator` | pass1 골격 생성 재사용 — 챕터 목록·불릿 | `kdp_book.py` |
| 3. 챕터 작성 | 구조 참고: `auto-ebook-generator` | draft_pipeline 2패스 + 챕터 일관성 보정 패스 | 핵심은 기존 자산 |
| 4. 품질 검수 | — | QC 8항목 + KDP 특화(챕터 길이 ±20%·AI 표기 문구) | 자체 |
| 5. 표지 생성 | **Pillow** | `image_gen` 확장 — 6×9 비율 + 텍스트 오버레이 | 기존 생성기 + Pillow |
| 6. EPUB 조립 | **ebooklib** ✅ | `ebook_builder.py` — 목차·챕터·메타 조립 | 핵심 채택 |
| 7. 검증/변환 | **calibre**(`ebook-convert`) ✅ + epubcheck | GH Actions 배치 단계 | 업로드 전 필수 |
| 8. 출간 | — (자동 업로드 도구는 계정 제재 리스크) | 수동 업로드 + 출간 큐(일 3권 게이트) | 반자동 유지 |
| 9. 성과 추적 | — | 대시보드 탭 확장 (판매·리뷰 입력) | autostudio 패턴 |

### 배치 요약
```
[기존 자산 재활용]   [오픈소스 배치]       [자체 신규]
주제선정·챕터생성    ebooklib (EPUB 조립)   kdp_research.py
QC·대시보드·배치     calibre (검증·변환)    kdp_book.py
image_gen (이미지)   Pillow (표지 처리)     ebook_builder.py
                    (선택) pandoc (DOCX)   출간 큐·성과 추적
```

## 3. 데이터 모델

```
kdp_books     id · title · description · keywords(JSON) · category · status
              (draft/assembling/ready/published) · created_at · updated_at
kdp_chapters  id · book_id(FK) · seq · title · body_md · word_count · status
kdp_covers    id · book_id(FK) · image_url · size(6×9) · created_at
```

- 기존 SQLite/Postgres 이중 SQL 패턴 재사용 (`db.py` 확장)
- 엔진 메타는 `drafts`와 분리 (KDP 전용 테이블)

## 4. 모듈 설계

### kdp_research.py — 주제 선정 (~3h)
- 입력: v20 '곧 뜰' 프리셋 상위 키워드 + 카테고리(고CPC 우선)
- 아마존 검색 경쟁도 스냅샷: 상위권 권수·평점·가격대 → **틈새 판정** (경쟁 적음 + 수요 있음)
- 산출: 책 주제 후보(제목·설명·키워드·카테고리) → kdp_books

### kdp_book.py — 책 생성 (~5h)
- 책 아웃라인: pass1 골격 생성 재사용 (챕터 6~12개 + 불릿)
- 챕터별 생성: draft_pipeline 2패스 (플랫폼=brand 포맷 재활용 — 마크다운)
- 일관성 보정 패스: 챕터 간 어조·용어·시점 통일 (LLM 1회 추가 호출)
- 예산: 챕터당 하드 예산 300초 (content_batch 패턴), 책 1권 = 여러 날 배치로 분산

### ebook_builder.py — EPUB 조립 (~3h)
- ebooklib: 목차(챕터 시퀀스)·메타(제목/저자/키워드)·챕터 HTML 조립
- 표지: image_gen(6×9) + Pillow 텍스트 오버레이(제목·부제)
- 검증: calibre ebook-convert (에러·경고 0) + epubcheck
- **서버리스 제약**: 조립·검증은 GH Actions 배치 전용 (Vercel 60초 한도 밖), 대시보드는 다운로드만

## 5. KDP 정책 게이트 (출간 시)

공식 정책 기준 (kdp.amazon.com Help, 2026-08-10 확인):

- **개인(individual) 가입 가능** — Business type에서 개인/법인 선택. 법적 이름으로 계정, 책에는 펜네임 사용 가능
- **EPUB 업로드 지원** ✓ — Kindle Publishing Guidelines 준수 시 (ebooklib 설계 유효, 업로드 전 Kindle Previewer 검증 권장)
- **제목 생성 상한: 포맷별 주당 10권** (공식) — 출간 큐를 주 단위 게이트로
- **AI 생성 콘텐츠 공개 표기 의무** (아마존 정책) — 출간 시 체크리스트에 포함
- **업로드 수동** — 자동 업로드 오픈소스(kdp-api류)는 브라우저 자동화로 계정 제재 리스크 → 미사용
- 표절·중복 콘텐츠 금지 — 챕터 QC에 유사성 점검

## 6. 대시보드 (KDP 출간 탭)

- 책 목록(상태 배지) · 챕터 진행률 바 · EPUB 다운로드 버튼 · 출간 체크리스트(표기·가격·키워드)
- 기존 v18 탭 패턴 재사용

## 7. 실행 순서

1. **K-1** DB 스키마 + kdp_research.py (주제 선정) — ~3h
2. **K-2** kdp_book.py (챕터 생성 + 일관성 패스) — ~5h
3. **K-3** ebook_builder.py (ebooklib 조립 + calibre 검증) — ~3h
4. **K-4** 배치 모드 + 대시보드 탭 + EPUB 다운로드 — ~3h
5. **파일럿**: "52주 절약 챌린지 워크북" 1권 → 반응 확인 → 시리즈 확장

## 8. 리스크

| 리스크 | 완화 |
|---|---|
| AI 생성 콘텐츠 제한 (일 3권·공개 표기) | 출간 게이트 체크리스트로 강제 |
| 전자책 시장 경쟁 | '곧 뜰' 키워드 기반 틈새 주제 + 시리즈 전략 |
| 품질 (AI 소설 반감) | 구조화 워크북/가이드 파일럿 → 검증 후 장르 확장 |
| 아마존 정책 변경 | 반자동(수동 업로드) 유지로 계정 리스크 최소화 |
