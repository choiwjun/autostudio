# 네이버 블로그 콘텐츠 자동화 코딩 컨벤션

> 작성일: 2026-08-04 · 버전: v1
> 기존 프로젝트 컨벤션(파이썬 3.11 + FastAPI + 단일 HTML)을 그대로 따른다.

## 1. 파일 구조

```
autostudio/
├── config.py               # 설정 로드 + KST 헬퍼 (기존)
├── db.py                   # DB 레이어 (기존 + drafts/outlines 메서드 추가)
├── analyzer.py             # 키워드당 스냅샷 (기존 + description 캡처 확장)
├── outline.py              # [신규] 상위글 골격 추출 모듈 (description → structure)
├── draft_generator.py      # [신규] 초안 생성 (opencode CLI 실행 + 프롬프트 빌드)
├── image_gen.py            # [신규] 이미지 생성 (bl CLI / Bailian API)
├── server.py               # FastAPI 앱 (기존 + /drafts, /outlines 엔드포인트 추가)
├── static/index.html       # 대시보드 (기존 + 글 생성 UI 추가)
├── tests/
│   ├── test_analyzer.py    # 기존 + description 캡처 테스트
│   ├── test_outline.py     # [신규]
│   ├── test_draft_generator.py  # [신규]
│   ├── test_image_gen.py   # [신규]
│   └── test_api.py         # 기존 + drafts API 테스트
└── .github/workflows/
    └── daily-collect.yml   # 기존 (변경 없음, 초안 생성은 사용자 트리거)
```

## 2. 네이밍 규칙

- 변수/함수: snake_case (기존 유지)
- 클래스: PascalCase
- 상수: UPPER_SNAKE_CASE
- API 라우트: `/drafts`, `/outlines`, `/drafts/{id}/image` (복수형 리소스)
- JSON 필드: snake_case 그대로 (기존 API와 동일)

## 3. 주석 규칙

- 모듈 상단: 한 줄 설명 (`# module.py — 설명`)
- 함수: docstring 없이 1~2줄 주석 (기존 스타일 유지 — 기존 코드가 주석 위주)
- 변경 지점: `# v7:` 접두어로 버전 표기 (기존 `# v3:`, `# v6:` 패턴 계승)
- 테스트 함수명: `test_동작_조건` 형태 (기존 유지)

## 4. Lint/Formatter

- flake8 + black 기본 설정 (기존 유지)
- 라인 길이 88자 (black 기본)

## 5. Git 커밋 메시지

- feat: 새 기능 (예: `feat: draft generation endpoint`)
- fix: 버그 수정
- docs: 문서 수정
- refactor: 리팩토링
- test: 테스트 추가/수정
- 기존 커밋 히스토리 패턴 확인: `feat(v6):`, `fix(server):` 형태 — 태그(스코프) 병기 유지

## Loop Metadata

- Upstream documents referenced: 02-trd.md (스택), 04-database-design.md (스키마)
- Downstream documents affected: 06-tasks.md
- Open questions: 없음
- Assumptions: 신규 모듈 3개(outline/draft_generator/image_gen)는 기존 패턴을 따름
- Validation criteria: flake8 통과, 기존 84개 테스트 유지
- Risks: 이미지 생성 CLI 호출이 파이썬 표준 라이브러리만으로 안 되면 subprocess 래퍼 필요
