# BAL-3 Sprint Contract

> 보충 문서 — 원본: docs/BAL-3-dev-guide.md (+ slice 6장)
> 생성: /harness-plan · 일시: 2026-06-04
> 실행 형태: 에픽 1 + 6 자식 슬라이스 (Agent Teams, 단일 worktree feat/BAL-3)

## 통합 Definition of Done (에픽)
- [ ] `pytest tests/test_metrics.py --cov=app/metrics` 커버리지 **≥ 85%**
- [ ] 회귀 5종 전부 PASS: ① 5/25 작은쪽 · ② fx FAIL 전역오염 방지 · ③ 자동목표 순환차단 · ④ warmup · ⑤ 음수 PER 제외
- [ ] `pytest -q` 전체 GREEN (기존 138 테스트 + 신규 회귀 무손상)
- [ ] `ruff check app/ tests/` 0 violations
- [ ] CLAUDE.md NEVER 규칙 무위반: fx 결측 시 분모 제외 금지 · 제공자 PER/PBR 재계산 금지 · 빈 응답 OK 금지 · SQL 문자열연결 금지

## Slice 별 DoD
| Slice | DoD (검증 가능 행동) | 소유 파일 |
|-------|----------------------|-----------|
| **BAL-18** | §15.2 DTO 7종 frozen 정의 + import 성공 + BriefingDoc to_json/from_json 라운드트립 | `app/models.py` |
| **BAL-19** | build_priced: 보류=status·분모유지 / fx FAIL 시 KR만 정규화 / US us_ok=False 보류 / fx row 실종 강등 | `app/metrics/priced.py` |
| **BAL-20** | auto_targets 평가액 무인자 / drift 5·25 작은쪽 / core_sat 30% / asset_alloc G6 / dca 드리프트우선 | `app/metrics/portfolio.py` |
| **BAL-21** | change_pct None-safe / valuation warmup·음수PER 제외 / trend None-safe / regime degrade | `app/metrics/security.py` |
| **BAL-22** | evaluate_gate 분기(blocked/fx_ok/us_ok) / collect_complete_today 오판정 방지 / db 헬퍼 2종 | `app/metrics/gate.py`, `app/db.py` |
| **BAL-23** | 회귀 5종 + 분기 커버 → ≥85% | `tests/test_metrics.py` |

## Files to Change (산출물 계약)
| Path | 변경 | Risk |
|------|------|------|
| `app/models.py` | 수정 (DTO 7종 추가) | Medium — 기존 6종 보존 |
| `app/metrics/priced.py` | 신규 | High — fx 전역오염 함정 |
| `app/metrics/portfolio.py` | 수정 (스텁→구현) | High — 5/25 로직 |
| `app/metrics/security.py` | 수정 (스텁→구현) | Medium — NULL/음수 분기 |
| `app/metrics/gate.py` | 신규 | Medium — 게이트 분기 |
| `app/db.py` | 수정 (헬퍼 2종) | Medium — named param only |
| `app/metrics/__init__.py` | 수정 (export, **리드 통합**) | Low |
| `tests/test_metrics.py` | 신규 | Medium — 커버리지 게이트 |

## Verify Targets (Evaluator)
> 프로젝트에 verify-* 스킬 없음 → harness-review fan-out (bal-* 에이전트) + 표준 게이트로 검증:
- `bal-security-reviewer` — 시크릿/주입/금융 산출 안전 (fx 분모 오염, SQL 바인딩)
- `bal-test-writer` — 회귀 5종 + 엣지 커버 충분성
- `pytest --cov` ≥85% (정량 게이트)
- `ruff check` (정적)

## Phase 분할 (= wave)
- **Phase 1 (Wave A)**: BAL-18 — DTO 봉인
- **Phase 2 (Wave B)**: BAL-19 — build_priced 봉인
- **Phase 3 (Wave C)**: BAL-20 ‖ BAL-21 ‖ BAL-22 — 3-way 동시 (disjoint 파일)
- **Phase 4 (Wave D)**: BAL-23 — 회귀 + 커버리지 게이트

## Out of Scope (스코프 드리프트 방지)
- briefing.py 조립(`assemble_briefing`/`run_briefing`) — W4(BAL-4+)
- LLM 어댑터 실제 구현 — 06-ai-agent, W4
- FastAPI 라우트/Jinja2 렌더 — W5
- `build_freshness_badge` 실구현 (DTO만 BAL-18) — 소비자 W5
- collect 어댑터 수정 — W2 완료분, 건드리지 않음

## Context Handoff
- Reference: docs/04-backend.md §4.4·§9·§10.2, docs/08-dev-roadmap.md Week 3, .claude/docs/reference/{database,testing}.md
- Memory: ~/.claude/projects/-Users-pyeondohun-development-thinking-investbrief/memory/MEMORY.md
