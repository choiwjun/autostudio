# 네이버 블로그 콘텐츠 자동화 디자인 시스템

> 작성일: 2026-08-04 · 버전: v1
> 기존 대시보드(static/index.html)의 디자인 언어를 그대로 확장한다. 신규 요소는 글 생성 모달·초안 보기 화면·상위글 골격 모달.

## 1. 색상 팔레트

- Primary: `#03C75A` (네이버 그린 — 기존 대시보드 강조색 유지)
- Secondary: `#191F28` (진한 남회색 — 텍스트·버튼)
- Background: `#F9FAFB` (밝은 배경) / 카드 `#FFFFFF`
- Border: `#E5E8EB`
- Text: `#333D4B` (본문) / `#8B95A1` (보조) / `#FFFFFF` (Primary 위)
- Danger: `#F04452` (오류·차단 메시지)
- Warning: `#F79009` (키 미발급 등 경고)

## 2. 타이포그래피

- 제목(H1): 20px / 700 (초안 제목)
- 소제목(H2): 16px / 700 (질문형 소제목 표시)
- 본문(Body): 14px / 400 (초안 본문)
- 캡션(Caption): 12px / 400 (생성 상태·안내)
- 모노(코드/API): 13px / `SFMono-Regular, Consolas` (복사용 텍스트 블록)

## 3. 컴포넌트

### Button
- Primary(글 생성): 초록 배경 + 흰 글자, hover 시 진한 초록
- Secondary(이미지 생성): 흰 배경 + 회색 보더
- Ghost(복사): 텍스트 버튼 + 아이콘, 클릭 시 "복사됨!" 피드백
- Disabled: 회색 배경 + 비활성 (스냅샷 없는 키워드)

### Modal (글 생성 / 상위글 골격)
- 배경: 50% 검정 오버레이
- 카드: 480px 최대 너비, 16px 라운드, 24px 패딩
- 닫기: 우측 상단 X 버튼

### TextBlock (초안 본문)
- 흰 배경 카드, 1px 보더, 12px 패딩
- 제목/첫문단/본문을 섹션으로 구분
- 복사 버튼 포함

### ImagePreview (이미지 미리보기)
- 생성 전: 회색 플레이스홀더 + "생성 중..." 스피너
- 생성 후: 이미지 썸네일 + URL 표시

### Skeleton (로딩)
- 기존 대시보드 스켈레톤 패턴 재사용 (생성 중 상태)

## 4. 간격 시스템

- xs: 4px / sm: 8px / md: 16px / lg: 24px / xl: 32px (기존 유지)

## 5. 반응형

- Mobile: < 768px (모달이 전체 화면으로 확장, 이미지 썸네일 100% 너비)
- Tablet: 768px ~ 1024px
- Desktop: > 1024px (모달 480px 고정)

## Loop Metadata

- Upstream documents referenced: 06-screens.md (신규 화면 2개 + 모달)
- Downstream documents affected: 06-tasks.md (프론트 태스크)
- Open questions: 없음
- Assumptions: 기존 대시보드 디자인 언어(네이버 그린)를 확장 — 별도 디자인 툴 없음
- Validation criteria: 신규 컴포넌트가 기존 대시보드와 시각적으로 일관됨
- Risks: 모달 반응형에서 모바일 가로폭 초과 — 100% 확장 규칙 적용
