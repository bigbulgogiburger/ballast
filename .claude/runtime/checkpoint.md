# Harness Checkpoint — BAL-1 / M1a 슬라이스

- **Epic**: BAL-1 ([W1] M1a 데이터 스파이크) · **Parents**: BAL-8~12 (전부 진행 중)
- **Branch**: feat/bal-1-m1a-spike (base 7a0a815)
- **Stage**: planning (Phase 3) — dev-guide fan-out 진행/완료
- **Mode**: wave-3-1-1 (orchestration §3)
- **Session**: degraded (thinking/ 루트) — 풀 자동화는 `cd investbrief && claude` 후 `/harness-resume`

## 완료
- Phase 1 start: 에픽 + BAL-8~12 In Progress, 브랜치 생성
- Phase 3 plan: orchestration 문서 + seam 계약 **v2(canonical 정합)**, dev-guide 5종(docs/BAL-{8..12}-dev-guide.md), Sprint Contract(BAL-1), state
- 정합성 정정: seam v1 드리프트(to_source/calendar/headlines/validate/regime/9테이블) → canonical로 수정. W-2a 공통가드 선행.
- 미해결 질문 **전건 해소**: `docs/BAL-1-m1a-decisions.md` (유보 0건, needs_user 0건). 교차충돌 4건 단일화.

## 다음
- **Phase 4 사용자 승인 대기** (슬라이스 계획) → Phase 5 구현은 Wave W-1(BAL-8/9/10)부터
- 구현은 사용자 green-light 후(가능하면 investbrief 정상 세션 `cd investbrief && claude` + `/harness-resume`)

## 복원: /harness-resume (state=.claude/runtime/workflow-state.json)
