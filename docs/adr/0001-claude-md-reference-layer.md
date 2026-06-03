# ADR-0001: CLAUDE.md Lazy-Loading Reference 구조 채택

- **상태**: 채택
- **날짜**: 2026-06-03
- **결정자**: /organize-claude-md (사용자 승인)

## 맥락

CLAUDE.md(41줄)가 평면 구조로, 코드(W1+W2 구현)가 늘면서 어댑터 패턴·DB 헬퍼·collect 게이트·테스트 규약 등 작업별 상세를 담을 곳이 없었다. CLAUDE.md는 매 세션 전체가 컨텍스트에 로드되므로 상세를 본문에 쌓으면 비대화된다. 단, 본 레포는 **단일 프로젝트(Python/FastAPI)** 로 monorepo가 아니다(빌드파일 1개, sub-project 0).

## 결정

1. **단일 프로젝트 lazy-loading 구조** 채택 — `.claude/docs/reference/`에 작업별 reference 분리, CLAUDE.md는 진입점(개요·Mermaid·금지형 규칙·인덱스)만 유지(≤120줄).
2. **reference 5종**(Small 등급): architecture · source-adapters · database · data-collection · testing.
3. **기존 `docs/00–08` 설계 스펙은 정본 SoT로 유지** — reference에서 링크만, 내용 복제 안 함. `TECH-DESIGN.md` 부재이므로 04/05/01이 정본.
4. monorepo 분할(sub-CLAUDE.md)은 **미적용** — 단일 프로젝트라 해당 없음.

## 대안

- (A) 모든 상세를 CLAUDE.md 본문에 → 비대화·compliance 저하. 기각.
- (B) monorepo 중첩 reference → 단일 프로젝트엔 과설계. 기각.
- (C) reference 없이 docs/만 → 코드 레벨 패턴(어댑터/테스트 규약)이 설계 스펙과 섞임. 기각.

## 결과

- CLAUDE.md ≤120줄 유지, 작업 맥락별 reference lazy load.
- 향후 W3(metrics/LLM/프론트) 추가 시 reference 증설(Medium 등급 전환 가능).
- 기존 정보 100% 보존(보안 규칙→Key Rules, docs 인덱스→Reference Docs, Harness 섹션 유지).
