# 11. 운세 채널 — 만세력 엔진 이식 + 자체 블로그 계획

> 상태: 계획 확정 (2026-08-10) · 관련 저장소: `autostudio`(콘텐츠 공장), `myunglab`(만세력 엔진)
> 쇼츠 공장(구 Phase 4)은 네이버 블로그 + 외부 블로그 안정화 이후 별도 검토 — 본 계획에서 제외

## 1. 배경과 목적

- **autostudio** — 네이버 애드포스트 키워드 발굴·초안 자동화 (Python/FastAPI, Vercel+Supabase). 발굴·생성은 자동이지만 게시는 수동이라 초안 34개 적체, 요리 키워드 42%(CPC 0.5) 병목.
- **myunglab (命 MYEONG)** — 만세력 엔진 기반 사주/궁합/운세 상용화 수준 구현 (TypeScript, Next.js + Tauri 데스크톱 설치형). 12종 계산(사주·궁합·토정·자미·기문·대육임·구성·홍연·매화·하락·대정·작명), 골든 픽스처·외부 제공자 비교·전문가 검증 프로세스 보유. 도메인 `myeong.kr` 확보, 웹 배포는 미실시.
- **목적**: 운세 콘텐츠(반복 검색 수요)를 자동화해 초기 트래픽을 잡고, myunglab(데스크톱 판매/추후 웹) 홍보·전환 채널로 활용.

### 검증된 판단
- 운세는 CPC가 낮아 **광고 수익원으로는 부적합**하나, **플랫폼 전환(홍보) 채널로는 반복 검색 수요(오늘의/주간/월간 운세)가 강력**.
- AI 환상 운세는 저품질·중복 판정 위험이나, **만세력 엔진 실계산 + AI 해석**은 차별화와 E-E-A-T 확보 가능.
- 엔진은 순수 TypeScript(플랫폼 독립) — 데스크톱 WebView 브리지(`globalThis.MyeongEngine`)로만 노출됨. autostudio(Python)와 통합하려면 **Python 포팅**이 필요.

## 2. 최종 구조

```
autostudio (Vercel + Supabase) — 콘텐츠 공장 + 외부 블로그
├── engine/                  만세력 Python 포팅 (Phase 1)
│   ├── calendar.py          간지·절기·음양력·한국시간 규정
│   ├── fortune.py           daily-fortune(일운)·monthly-rhythm(월운)
│   └── data/                lunar-solar·solar-terms (SQLite 테이블 권장)
├── /blog                    자체 블로그 (Phase 2)
│   ├── blog_posts 테이블 + 목록/상세 페이지
│   └── sitemap.xml · RSS · OG · JSON-LD
├── daily-collect            발굴 → 초안 → /blog 자동 발행 (2.4)
└── 운세 채널 (Phase 3)       엔진 직접 호출 → 운세 글 매일 재생성·발행 + CTA

myunglab (기존, 변경 없음) — 데스크톱 설치형 판매 + myeong.kr 랜딩
```

### 의존 순서
```
Phase 1(엔진 포팅) → Phase 3(운세 자동화)
Phase 2(/blog)는 Phase 1과 병행 가능
쇼츠 공장: 네이버 블로그 + 외부 블로그 안정화 후 별도 계획 (본 문서 제외)
```

## 3. Phase 1 — 만세력 엔진 Python 포팅

| # | 작업 | 산출물 | 비고 |
|---|---|---|---|
| 1.1 | 데이터 변환 | `lunar-solar.generated.json`(4MB)·`solar-terms.generated.json`(1.1MB) → **SQLite 테이블** | 인덱스·조회·캐시 용이, autostudio DB 인프라 재활용 |
| 1.2 | core 포팅 | `ganji`(간지)·`solar-terms`(절기)·`lunar-solar`(음양력)·`korean-legal-time`(한국 시간 규정)·`manseryeok-engine` → Python | 결정적 계산이라 1:1 이식 |
| 1.3 | 운세 문구 포팅 | `daily-fortune`(305줄)·`monthly-rhythm`(232줄) → Python | 규칙 기반·결정적·금지어 가드(반드시/무조건/100%) 유지 |
| 1.4 | 정확성 검증 | myunglab golden-fixtures를 Python 테스트로 재사용 | 상용화 정확도 이식 보장 — 외부 제공자 비교 벤치마크 데이터도 활용 |
| 1.5 | 사주 4기둥(2단계) | `saju/calculator` + 십신·신살·용신·대운 | 심화 콘텐츠용 (이번 범위 밖) |

### 기술 결정
- **경로 1(Python 포팅) 채택** — 서버리스(Vercel Python 함수)와 GH Actions 배치가 같은 엔진 코드를 공유. Node 런타임 실행(경로 2)은 Vercel에서 불가해 비채택.
- **데이터는 SQLite 테이블** — 4MB JSON을 메모리 로드하지 않고 조회·캐시.
- **검증은 픽스처 재사용** — myunglab의 golden-fixtures가 곧 Python 테스트의 golden standard.

## 4. Phase 2 — autostudio /blog (자체 블로그)

| # | 작업 | 산출물 |
|---|---|---|
| 2.1 | `blog_posts` 테이블 | slug(유니크)·제목·본문(markdown)·태그·플랫폼·발행일·엔진 메타(운세 유형·기준일) |
| 2.2 | 블로그 페이지 | 목록(카드 그리드)·상세(마크다운→HTML 렌더링)·카테고리 필터 — `/blog` 서브패스, 대시보드(`/`) 불변 |
| 2.3 | SEO | sitemap.xml 동적 생성·RSS·OG 태그·JSON-LD |
| 2.4 | 자동 발행 | content_batch 확장 — 초안 → /blog 자동 게시 (네이버 수동 발행과 분리) |

### 설계 원칙
- Next.js 도입 없이 기존 FastAPI + static 구조 유지 (별도 빌드 파이프라인 없음).
- 블로그는 공개(인증 없음), 대시보드와 URL 격리.

## 5. Phase 3 — 운세 채널 자동화

| # | 작업 | 산출물 |
|---|---|---|
| 3.1 | 운세 콘텐츠 타입 | 오늘의 운세(일간 기준)·주간/월간 운세(월운)·띠별·별자리 — 시드/발굴 로직 재활용 |
| 3.2 | 엔진 기반 글 생성 | Python 엔진 직접 호출(외부 API 없음) → v19 플랫폼 파이프라인으로 초안화 |
| 3.3 | 매일 재생성·발행 | daily-collect에 운세 모드 — "오늘의 운세"는 기준일마다 재생성·재발행 (구글 신선도 신호) |
| 3.4 | CTA 블록 | 글 하단 → `myeong.kr` (데스크톱 판매/추후 웹 전환) — 플랫폼명은 설정값으로 |

### 콘텐츠 전략 주의
- 네이버 블로그에는 운세 반복 포스팅 금지(패턴 감지·저품질 리스크) — **운세는 자체 블로그(/blog) 전용**.
- 네이버 블로그는 기존 애드포스트 파이프라인(고CPC) 전용으로 유지 — 도메인 파워 혼재 방지.

## 6. 향후 과제 (보류 — 안정화 후 검토)

네이버 블로그 + 외부 블로그가 안정화된 이후 별도 계획으로 검토합니다:

| 항목 | 내용 |
|---|---|
| 유튜브 쇼츠 공장 | 세로형(1080×1920) 운세 카드 이미지 생성(image_gen 확장) → 매일 쇼츠 큐 → (추후) 실사 배경 영상 API |
| 사주 4기둥 확장 | Phase 1.5 — 사주 기반 심화 콘텐츠 |

## 7. 리스크

| 리스크 | 완화 |
|---|---|
| 포팅 정확성 (음양력·절기 테이블 오차) | myunglab 골든 픽스처·외부 제공자 벤치마크를 Python 테스트로 재사용 (1.4) |
| 엔진 이중 유지보수 (TS/Python 분기) | 운세 문구·규칙은 결정적 — 픽스처 공유로 분기 감지, myunglab 변경 시 재동기 프로세스 |
| 신규 도메인 검색 노출 지연 | /blog는 autostudio 기존 Vercel 도메인(또는 myeong.kr) — 운세 콘텐츠를 미리 축적 |
| 자동 발행 품질 | v19 플랫폼 QC 재활용 + 운세는 결정적 계산이라 문구 품질은 픽스처로 보장 |
| 네이버 정책 | 운세 콘텐츠를 네이버에 게시하지 않음 (자체 블로그 전용) |

## 8. 실행 순서 (다음 액션)

1. **1.1 데이터 변환** — myunglab 생성 JSON → autostudio SQLite 테이블 스키마 설계
2. **1.2~1.3 core·문구 포팅** — engine/ Python 모듈 작성
3. **1.4 검증** — golden-fixtures Python 테스트 (완료 기준: myunglab 대비 동일 출력)
4. **2.1~2.4 /blog** — 병행 가능
5. **3.1~3.4 운세 자동화** — 첫 자동 발행 데모
