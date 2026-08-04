# 네이버 블로그 콘텐츠 자동화 화면 목록

> 작성일: 2026-08-04 · 버전: v1
> 이 파일은 /screen-spec의 입력이다. 화면 ID·경로·컴포넌트가 정확해야 한다.

## 화면 1: 키워드 대시보드 (기존 + 글 생성 버튼)

- ID: screen-01
- 경로: `/` (기존 대시보드)
- 기능: 키워드 목록 조회 (기존), 각 키워드 행에 **"글 생성" 버튼 추가**
- 컴포넌트: 키워드 테이블, 정렬/프리셋 컨트롤, 우선순위 게이지, **글 생성 버튼 (신규)**
- 비고: 기존 v6 화면 그대로 유지, 행 액션에 버튼 1개 추가

## 화면 2: 초안 보기

- ID: screen-02
- 경로: 모달/오버레이 (별도 라우트 없음 — `draft-modal`)
- 기능: 초안(제목·첫문단·본문) 표시, 이미지 생성/미리보기, 복사
- 컴포넌트: 초안 제목(H1), 첫문단 블록, 본문 블록(질문형 소제목 포함), 이미지 미리보기, **이미지 생성 버튼**, **복사 버튼**, 생성 상태 표시(skeleton/spinner)
- 데이터 요구: drafts (title, first_paragraph, body, image_url, status)

## 화면 3: 상위글 골격 확인 (모달)

- ID: screen-03
- 경로: 모달/오버레이 (`outline-modal`)
- 기능: 해당 키워드 상위글의 구조 미리보기(질문형 소제목·비교·수치), "초안 생성" 트리거
- 컴포넌트: 골격 구조 목록(소제목/비교/수치 태그), **초안 생성 버튼**, 닫기 버튼
- 데이터 요구: outlines (structure, day, source)

## 화면 간 이동

```
screen-01 (대시보드) --글 생성 클릭--> screen-03 (골격 모달)
screen-03 --초안 생성 클릭--> screen-02 (초안 보기)
screen-02 --복사--> 외부 (네이버 블로그 편집기)
screen-03 --닫기--> screen-01
```

## Loop Metadata

- Upstream documents referenced: 01-prd.md, 03-user-flow.md
- Downstream documents affected: /screen-spec (specs/screens/*.yaml), 06-tasks.md
- Open questions: 없음
- Assumptions: 초안 보기와 골격 확인은 모달로 구현 (별도 페이지 없음)
- Validation criteria: 3개 화면의 데이터 요구가 resources.yaml과 정합
- Risks: 모달 중첩(골격 모달 → 초안 모달) 시 닫기 동작 혼선 — 순차 전환으로 해결
