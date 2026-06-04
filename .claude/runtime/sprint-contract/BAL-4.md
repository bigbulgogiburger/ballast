# BAL-4 Sprint Contract

> 원본: docs/BAL-4-dev-guide.md (+ slice 5장) · /harness-plan · 2026-06-04
> 실행: 에픽 1 + 5 자식 (Workflow, 단일 worktree feat/BAL-4)

## 통합 DoD (에픽 §11)
- [ ] 브리핑 1건(FakeLLMClient): 금지어 0건(BANNED) + 면책 포함 + LLM raw 숫자 0개(RAW_NUMBER)
- [ ] ct join(G2): 누락/중복/변형 → failed 카드 + holds_excluded, 정상 종목 영향 0
- [ ] 보류 종목(hold_status != 'ok') LLM 미호출 + status 카드
- [ ] total_cost_usd 로깅
- [ ] `pytest -q` 전체 GREEN (기존 195 무손상) · `ruff check app/ tests/` clean
- [ ] CLAUDE.md NEVER 무위반 (시크릿 로그 금지·SQL named param·print 금지)

## Slice 별 DoD
| Slice | DoD | 소유 파일 |
|-------|-----|-----------|
| BAL-24 | ClaudeCLIClient subprocess + structured_output 파싱 + exit≠0/is_error→LLMError, 키 비노출 | `app/llm.py` |
| BAL-25 | 프롬프트 하드규칙(숫자 placeholder·ct echo·금지어)·양면라벨·good/bad | `app/prompts/briefing.md` |
| BAL-26 | SECURITY/PORTFOLIO_SCHEMA §15.2 정합, 숫자필드 0, json 직렬화 | `app/schemas.py` |
| BAL-27(+54/55) | run_securities/run_portfolio: 배치10·ct join G2·BANNED/RAW_NUMBER 린트·슬롯주입·보류 제외 | `app/briefing.py` |
| BAL-28 | assemble_briefing(수치 코드주입)+run_briefing 파이프라인+disclaimer 상수, blocked banner | `app/briefing.py`+`app/config.py`(+db) |
| (DoD test) | FakeLLMClient + 인메모리 conn, DoD 5항목 검증 | `tests/test_briefing.py` |

## Files to Change
| Path | 변경 | Risk |
|------|------|------|
| `app/llm.py` | 신규 | Medium — subprocess, 키 비노출 |
| `app/prompts/briefing.md` | 신규 | Low |
| `app/schemas.py` | 신규 | Low |
| `app/briefing.py` | 수정(스텁→전체) | **High** — 환각 차단 핵심(린터·ct join·슬롯주입·assemble) |
| `app/config.py` | 수정(DISCLAIMER) | Low |
| `app/db.py` | 수정 가능(insert_briefing 등 부재 시) | Medium — named param |
| `tests/test_briefing.py` | 신규 | Medium |

## Verify Targets
- `bal-security-reviewer` — 키 노출·subprocess 안전·SQL 바인딩·환각 차단(raw 숫자/금지어 reject 실효)
- `bal-test-writer` — DoD 5항목 + ct join 3케이스(누락/중복/변형) + 보류 LLM 미호출 진검증, FakeLLMClient 사용 확인
- `pytest -q` 전체 GREEN · `ruff check`

## Phase 분할 (= wave)
- Phase 1 (Wave1 병렬): BAL-24 ‖ BAL-25 ‖ BAL-26
- Phase 2 (Wave2): BAL-27 + BAL-28 (briefing.py 통합 구현, 한 에이전트)
- Phase 3 (Wave3): tests/test_briefing.py (DoD 검증)

## Out of Scope
- 실제 `claude` CLI 라이브 호출 (테스트는 FakeLLMClient) — 라이브 1건은 수동/후속
- FastAPI 라우트·Jinja2 렌더 (W5)
- 메트릭 로직 변경 (W3 완료분 — 읽기만)
- W3 외 신규 metric

## Context Handoff
- Reference: docs/06-ai-agent.md §1~§6, docs/04-backend.md §10.1·§10.3, models.py(SecurityLLMOut/SecurityCard/BriefingDoc/HoldExcluded from BAL-3)
- Memory: bal-milestone-execution-pattern, bal-repo-jira-facts
