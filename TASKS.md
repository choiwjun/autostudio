# TASKS — 알고리즘 감사 발견사항 수정 (2026-08-11)

> 근거: docs/VERIFICATION.md (전체 알고리즘 감사, minor 16건)
> 방법: TDD (테스트 먼저 → 구현 → 태스크 단위 커밋) · 실행: task-runner 스킬
> 검증: 각 태스크 관련 테스트 + 마지막에 전체 pytest

## T1 (R-1) adpost CSV 열 정확 매칭 — '클릭률' 오선택 방지
- [x] **수용 기준**: '클릭률,클릭' 헤더에서 clicks 열이 '클릭'(정확) 선택. 부분 문자열 폴백은 정확 매칭 실패 시에만
- [x] 파일: adpost.py `find()` / tests/test_adpost.py
- [x] 커밋: `fix: adpost CSV 열 매칭 정확 일치 우선 (클릭률 오선택 방지)`

## T2 (B-1) upcoming 프리셋 P50=0 폴백 우회 수정
- [x] **수용 기준**: opportunity P50=0이면 upcoming 프리셋이 절대값 폴백(20.0) 사용 — 0.0으로 전체 노출 금지
- [x] 파일: server.py list_keywords / tests/test_api.py
- [x] 커밋: `fix: upcoming 프리셋 P50=0 폴백 (전체 노출 차단)`

## T3 (E-1) 운세 qc_failed 콘텐츠 재시도 허용
- [x] **수용 기준**: status=qc_failed 행은 다음 실행에서 재생성 시도 (content 존재해도). generated만 멱등 스킵
- [x] 파일: db.py upsert_fortune_generation / tests/test_fortune_publish.py
- [x] 커밋: `fix: 운세 qc_failed 콘텐츠 재생성 허용`

## T4 (E-2) weekly/monthly/고정 콘텐츠 grounding 정합
- [x] **수용 기준**: weekly/monthly는 자체 builder grounding, 고정 콘텐츠는 고정 grounding 저장 — daily 그라운딩 오염 제거
- [x] 파일: collect.py fortune_generate_step / tests/test_collect.py
- [x] 커밋: `fix: 운세 콘텐츠별 grounding 메타데이터 정합`

## T5 (D-1) 재생성 피드백 보강 (body_length/first_paragraph 실측)
- [x] **수용 기준**: body_length·first_paragraph 실패 시 실측 길이/목표를 피드백에 주입
- [x] 파일: draft_pipeline.py generate_two_pass / tests/test_draft_pipeline.py
- [x] 커밋: `fix: 초안 재생성 피드백에 길이 실측 주입`

## T6 (D-2) 네이버 structure 검수 완화 (부분 일치)
- [x] **수용 기준**: 골격 소제목이 본문 한 줄에 부분 포함(공백 정규화)이면 매치 인정 — 정확 일치 요구 제거
- [x] 파일: draft_pipeline.py check_naver_subtitles / tests/test_draft_pipeline.py
- [x] 커밋: `fix: 네이버 소제목 검수 부분 일치 허용`

## T7 (R-2) URL 정규화 비대칭 수정
- [x] **수용 기준**: 초안 published_url 저장 시 rstrip('/') — CSV 매칭 정합
- [x] 파일: server.py /adpost/import 매칭 경로 확인 후 최소 수정 / tests/test_api.py
- [x] 커밋: `fix: AdPost URL 매칭 정규화 통일`

## T8 (R-3) /adpost/import 제목 매칭 status 가드
- [x] **수용 기준**: 제목 매칭 시 published 상태 초안만 대상 (미게시 초안 오매칭 방지)
- [x] 파일: server.py import_adpost_report / tests/test_api.py
- [x] 커밋: `fix: AdPost 임포트 제목 매칭 게시 상태 가드`

## T9 (R-4) revenue_insights 필터 통일
- [x] **수용 기준**: totals와 monthly 동일 기준 (revenue만 필터) 또는 3지표 통일 — 불일치 제거
- [x] 파일: db.py revenue_insights / tests/test_revenue_features.py
- [x] 커밋: `fix: 수익 인사이트 집계 필터 통일`

## T10 (R-5) /refresh 가드 (게시·성과 기준)
- [x] **수용 기준**: README 기준(게시 14일 이상·성과 50 미만) 적용 — 예외: refresh_of가 없는 신규? (플래너 추천과 정합)
- [x] 파일: server.py refresh_draft / tests/test_api.py
- [x] 커밋: `fix: 초안 리프레시 게시·성과 가드`

## T11 (R-6) 리프레시 boost 분배 확인·수정
- [x] **수용 기준**: 원본/신규 boost 의도 확인 (S5: 양쪽 +10) — 버그면 분배 수정, 의도면 테스트로 고정
- [x] 파일: server.py/db.py mark_draft_refreshed / tests
- [x] 커밋: `fix: 리프레시 boost 분배` 또는 `test: 리프레시 boost 의도 고정`

## T12 (B-2) README·문서 드리프트 갱신
- [x] **수용 기준**: ① 일 5%→15% ② 표본 3건→MEASURED_TIER_MIN_POSTS 실제 적용 후 문서 정합 ③ 은퇴 3개 스냅샷 가드 ④ demand 0.02
- [x] 파일: README.md / docs/planning 스펙
- [x] 커밋: `docs: 알고리즘 문서 드리프트 갱신`

## T13 (B-3) 정합 테스트 실측 CPC 경로 추가
- [x] **수용 기준**: category_cpc_stats 존재 시 PRIORITY_SQL 동작 테스트 (v6_priority는 레거시로 문서화)
- [x] 파일: tests/test_db.py
- [x] 커밋: `test: priority 정합 테스트 실측 CPC 경로 커버`

## T14 (B-4) MEASURED_TIER_MIN_POSTS 실제 적용
- [x] **수용 기준**: posts<3 카테고리는 measured_tier NULL (정적 폴백) — README '표본 3건 이상'과 정합
- [x] 파일: db.py refresh_category_cpc_stats / tests/test_revenue_features.py
- [x] 커밋: `fix: 실측 CPC 표본 3건 미만 폴백 적용`

## T15 (C-1) refine '작업 대출' 띄어쓰기 우회 차단
- [x] **수용 기준**: 토큰 {'작업','대출'} 동시 존재 시 차단
- [x] 파일: refine.py / tests/test_refine.py
- [x] 커밋: `fix: 불법 대출 키워드 띄어쓰기 변형 차단`

## T16 (E-4/E-5) 약화된 테스트 보강
- [x] **수용 기준**: 항진 단언(`is None or True`) 제거, test_ganji_known_pillars 실제 기대값 단언 (engine.db 실측으로 고정)
- [x] 파일: tests/test_engine_data.py, tests/test_engine_calendar.py
- [x] 커밋: `test: 엔진 테스트 항진 단언 제거·기대값 고정`

## T17 (E-3, N-1~N-3) 사어 코드·stale 주석 정리
- [x] **수용 기준**: FIXED_CONTENT_NAMES 미사용 시 제거, GROWTH_NORM_MAX 0.05 주석, 맛집 주석, commercial 사어 주석
- [x] 파일: engine/fortune_content.py, db.py, scoring.py
- [x] 커밋: `chore: 사어 코드·stale 주석 정리`

## 최종
- [x] 전체 pytest 실행 (기존 358 + 신규 테스트 전부 통과)
- [x] VERIFICATION.md 갱신 (수정 내역 반영)
- [x] 릴리즈 노트 요약 (releaser)


# ===== Phase 2: 블로그 프롬프트 개선 (2026-08-11, 리서치 기반 — docs/RESEARCH.md) =====

## T18 (P1-1) SYSTEM_PROMPT 안전성 — '실제 경험 기반' → 검증 가능 정보 + 창작 금지
- [x] **수용 기준**: SYSTEM_PROMPT에 '경험·출처·기관명·통계 창작 금지' + AI 브리핑 인용 구조 명시. '실제 경험 기반' 표현 제거
- [x] 파일: draft_generator.py / tests/test_draft_generator.py
- [x] 커밋: `fix: 초안 SYSTEM_PROMPT 창작 금지 강화 — 허위 경험·출처 방지 (P1-1)`

## T19 (P1-2) 허위 출처 표현 검수 추가
- [x] **수용 기준**: '조사에 따르면'류 패턴 감지 시 검수 실패 + 재생성 피드백
- [x] 파일: draft_pipeline.py (check_no_fake_sources, validate_draft, generate_two_pass) / tests/test_draft_pipeline.py
- [x] 커밋: `feat: 허위 출처('조사에 따르면'류) 검수·재생성 피드백 추가 (P1-2)`

## T20 (P2-1) AI 브리핑 인용 구조 지시 (pass1/pass2)
- [x] **수용 기준**: pass1·pass2 프롬프트에 'AI 브리핑이 인용하기 좋은 구조' 지시 포함
- [x] 파일: draft_pipeline.py / tests/test_draft_pipeline.py
- [x] 커밋: `feat: 프롬프트에 AI 브리핑 인용 구조 지시 추가 (P2-1)`

## T21 (P2-2) non-commodity 지시 (정보형 템플릿)
- [x] **수용 기준**: intent 정보형 템플릿에 '일반 상식 나열 금지·구체적 기준/숫자/비교/함정 중심' 포함
- [x] 파일: intent.py / tests/test_intent.py
- [x] 커밋: `feat: 정보형 템플릿 non-commodity 지시 추가 (P2-2)`

## T22 (P3) 제목 지시 보강 (연도·정보성)
- [x] **수용 기준**: pass2 제목 요구사항에 연도·정보성·핵심요약 지시 포함
- [x] 파일: draft_pipeline.py / tests/test_draft_pipeline.py
- [x] 커밋: `feat: 제목 지시 보강 — 연도·정보성·핵심 요약 (P3)`

## 최종 (Phase 2)
- [x] 전체 pytest 통과
- [x] README·VERIFICATION.md 갱신 + 수동 배포 (vercel --prod)
