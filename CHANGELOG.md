# CHANGELOG

이 프로젝트의 버전 이력. 버전 규칙: 기능 단위로 커밋 메시지에 표기 (비공식 SemVer).

## v25 — 2026-08-11 (키워드 대시보드 UX 개선)

### 변경
- **기본 프리셋 전체 표시** — 대시보드 첫 로드·필터 초기화가 전체 키워드(활성 전체) 기준으로
  변경 (UX-1/UX-2, 기존 ai_pick 기본 → 명시적 선택). 페이지네이션에 `N건 (프리셋명)` 라벨 표시
- **쇼핑클릭 필터 옵션 통합** — 0.001+/0.01+ 중복 옵션을 '클릭 수집됨 (값 있음만)' 하나로 통합,
  전체 라벨을 '쇼핑클릭 전체 (미수집 포함)'로 명확화 (UX-3)
- **프리셋 툴팁** — AI픽/유망/상승/곧 뜰 버튼에 기준(백분위) 설명 title 추가 (UX-4)

### 테스트
- `tests/test_api.py` 기본 preset 기대값 2건 갱신 — 전체 pytest 377 passed

### 문서
- `docs/KEYWORD-UIUX.md` — UX-1~UX-5 해결 상태 반영 (분석 보고서 갱신, 커밋 a3b94ba)
- **배포 확인**: 프로덕션(autostudio-eight.vercel.app) 실측 — 기본 호출 전체(203건) vs ai_pick(59건),
  HTML 마커(UX-2/3/4) 반영 확인 완료

## v24 — 2026-08-11 (프롬프트 개선 · 리서치 반영)

### 추가
- **AI 브리핑·AI 탭 인용 구조 지시** (pass1/pass2) — 질문-답변·리스트·단계·표 구조로
  AI가 답변 근거로 인용하기 쉽게 작성 (P2-1)
- **허위 출처 검수** — '조사에 따르면'류 11종 패턴 감지 → 검수 실패 + 재생성 피드백 (P1-2)
- **정보형 템플릿 non-commodity** — 일반 상식 나열 금지, 구체적 기준·숫자·비교·함정 중심 (P2-2)
- **제목 지시 보강** — 연도·정보성·핵심 요약("N가지 방법") (P3)

### 변경
- SYSTEM_PROMPT: "실제 경험 기반" → "검증 가능한 정보" + 경험·출처·통계 창작 금지 (P1-1)

### 문서
- `docs/RESEARCH.md` — 블로그 프롬프트 개선 리서치 (5개 출처, 갭 분석)

## v23.1 — 2026-08-11 (할당량 폴백)

### 추가
- opencode-go 호출이 할당량(429)/서버 오류(5xx)로 실패하면 **Bailian 자동 폴백** —
  쿼터 소진 시 초안 생성 마비 방지 (테스트 3건)

## v23 — 2026-08-11 (초안 LLM 프로바이더 전환)

### 변경
- 초안 생성 LLM: Bailian(Token Plan) → **OpenCode Go (zen/go, deepseek-v4-flash)** 우선
  - `OPENCODE_GO_API_KEY` 설정 시 사용, 미설정 시 Bailian 폴백
  - deepseek-v4-flash는 reasoning 모델 — `thinking: {"type": "disabled"}`로 추론 OFF
  - 브라우저 UA 추가 (zen/go Cloudflare 앞단 차단 대응)
- 이미지 생성은 Bailian 유지 (변경 없음)

### 환경변수
- `OPENCODE_GO_API_KEY` 추가 (GitHub Secrets / Vercel Env / .env.local)

## v22.3.2 — 2026-08-11 (마지막 v22)

- daily-collect에 autoblog 발행 env 추가 — 운세 자동 발행 활성화
- product_recommend f-string syntax error 수정

## v22.3 — 2026-08-10 (운세 채널 자동화)

- 운세 콘텐츠 자동 생성·발행 (daily/weekly/monthly/일주·별자리·띠 고정 콘텐츠)
- `engine/` 만세력 엔진 포팅 (calendar/day_pillar/fortune_content/fortune_extra)
- 별도 블로그(autoblog) 발행 클라이언트 + 게시 API

## v22.2 — 2026-08-09 (만세력 엔진)

- myunglab 만세력 데이터 → SQLite 변환 (`engine/data/engine.db` 커밋)
- 한국 법정 시간(표준/일광절약) 포팅, 60일주 문구 세트

## v22.1 — 2026-08-07

- 운세 채널 기획 확정 (11-fortune-channel), B2B/B2C 분리

## v21 — 2026-08-06 (출구 뚫기 + 카테고리 리밸런싱)

- 카테고리 비중 가드 (시드/발굴), '곧 뜰'(upcoming) 프리셋 — 초안 우선순위 연결

## v20 — 2026-08-05 (변별력 회복)

- GROWTH_NORM_MAX 0.05 → 0.15, demand 정규화 0.01 → 0.02, 카테고리별 fresh window
- 은퇴 스냅샷 3개 가드, 실측 CPC 베이지안 스무딩(prior=3)

## v19 — 2026-08-05 (멀티 플랫폼)

- 네이버(플레인)/티스토리/애드센스/브랜드 플랫폼 분기 (platforms.py 단일 소스)
- 썸네일 아이디어, 배치 플랫폼 지정

## v18 — 2026-08-04 (수익 최적화)

- AdPost 리포트 임포트, 카테고리 실측 CPC/RPM, 게시 플래너, 리프레시, 수익 인사이트

## v17 — 2026-08-04 (콘텐츠 배치)

- 스케줄 수집의 초안·이미지 배치 (시간 제약 없는 GH Actions), 이미지 증분 생성
- 하드 예산 55초 + 호출 타임아웃 클램프, outline facts/comparisons 그라운딩

## v16 — 2026-08-03

- 발행 기준일 공유 (temporal_relevance), v15 인증 fail-closed 강화

## v15 — 2026-08-03

- llm_client 공용 레이어 (펜스 제거·오류 정규화), ENV 소문자 정규화, 읽기 API 인증

## v14 — 2026-08-03 (자가보정 임계)

- 백분위 기반 임계 (P50/P75/P25), priority 가중치 30/25/15/30, 성장 신호 반영
- 정제 규칙 개선 (len/noise/brand), BFS 팬아웃 차단

## v13 — 2026-08-02

- 배지/프리셋 임계 재보정

## v12 — 2026-08-01 (수요 정규화)

- demand_idx 앵커 정규화 ('냉장고'), priority demand 항 복원

## v11 — 2026-08-01

- 본문 길이·H2 개수 검수, 밀도 공백 무시 보정, 재생성 시간 예산

## v10 — 2026-07-31 (2패스 + 검수 8항목)

- 1패스(H2 골격) → 2패스(섹션 확장) + 검수 8항목 + 1회 재생성
- 의도 분류 (정보/비교/구매)
