# ADR-0002: 마일스톤 에픽은 단일트리 의존순서 wave로 실행 (N-worktree 팬아웃 기각)

- **상태**: 채택
- **날짜**: 2026-06-04
- **결정자**: /harness-workflow (BAL-3·4·5 실행, 사용자 승인)

## 맥락

BAL 의 W-마일스톤은 **1 에픽 + N개 형제 `작업`** 구조다(예: BAL-3=W3 지표엔진의 자식 BAL-18~23, BAL-5=W5 프론트엔드의 자식 BAL-29~33). 형제 작업들은 `subtasks` 필드가 비어 있어 `--subtasks` 플래그가 no-op이다.

여러 형제 키를 `/harness-workflow` 에 나열하면 `parallel-fanout.md` 결정트리가 "다중 부모"로 인식해 **N개 worktree + Tier-1 Agent Teams + N회 개별 jira-complete/머지**를 시도한다. 그러나 BAL 마일스톤의 형제 작업들은 같은 `app/<pkg>/` 또는 단일 파일(`app/main.py`, `tokens.css`)을 공유·상호 의존하는 **수직 슬라이스**다. 특히 W5 프론트엔드(BAL-5)는 `main.py`(BAL-31·32 공유)·`tokens.css`(BAL-29·33 공유)·템플릿 상호의존으로 worktree 격리 전제(`parallel-fanout §0-2`: 코드 영역 충돌 없음)가 거짓이었다.

`ADR-070`(Agent Teams 패턴)은 harness 스킬이 차용한 **다른 프로젝트의 ADR**로 본 레포에 실재하지 않는다(과거 dev-guide의 유령 참조 — 본 ADR이 대체).

## 결정

1. **마일스톤 에픽은 단일 worktree `feat/BAL-N` + 의존 DAG wave로 실행.** N-worktree Tier-1 팬아웃은 코드 영역이 진짜 disjoint일 때만 고려(BAL 마일스톤은 해당 없음).
2. **wave 내부 병렬화는 Workflow 툴**(`parallel`/`pipeline`)로 수행 — Agent Teams spawn보다 안정적(Agent team이 internal error로 zombie 멤버를 남긴 사례 다수).
3. **충돌은 단일 파일 소유권으로 0 제거** — 슬라이스마다 disjoint한 파일 집합을 소유하고, wave 경계의 import 시그니처를 dev-guide에 고정.
4. **closure는 에픽 1회** — N회 개별 머지 대신 `feat/BAL-N` → main `--no-ff` 1회, 자식들은 SHA 인용 댓글로 일괄 완료 전이.

## 대안

- (A) `parallel-fanout.md` N-worktree 팬아웃 → 공유 파일(main.py·tokens.css) 머지 충돌 폭증 + 토큰 5~12×. 기각.
- (B) 슬라이스를 순수 순차 구현 → wave 내 독립 슬라이스의 병렬성 손실. 기각.
- (C) Agent Teams Tier-2 (단일 worktree 내 team) → zombie 멤버·팀 컨텍스트 점유 리스크. Workflow 툴로 대체.

## 결과

- BAL-3(6 슬라이스)·BAL-4(5)·BAL-5(5) 모두 본 패턴으로 완료, 충돌 0·전체 테스트 그린(BAL-5 기준 pytest 252).
- 충돌 매트릭스를 먼저 그려 wave를 결정하는 것이 진입 전 필수 단계.
- 밀결합 프론트엔드(BAL-5)일수록 단일트리+소유권 분할의 이점이 크다.
- 과거 dev-guide의 `ADR-070` 참조는 본 ADR(0002)로 교체.
