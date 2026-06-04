# [BAL-4] W4 · M3 AI 브리핑 — 통합 개발 가이드 (부모)

> 생성일: 2026-06-04 · 스택: Python/FastAPI · 페르소나: Python Expert
> 실행: 에픽 1 + 5 자식 슬라이스 (단일 worktree `feat/BAL-4` + Workflow)

## 1. 요구사항 (에픽 DoD §11)
LLM은 **문장·라벨만** 생성, **숫자는 코드가 박는다**. 환각·금지어·종목 누락 0 증명.
- [ ] 실제 브리핑 1건: 금지어 0건(BANNED) + 면책 문자열 포함 + **LLM 출력 raw 숫자 0개**(RAW_NUMBER 린터)
- [ ] ct join(G2): LLM 누락/중복/변형 시 failed 카드 + holds_excluded (정상 종목 영향 0)
- [ ] 보류 종목(hold_status != 'ok')은 **LLM 미호출** + status 카드
- [ ] total_cost_usd 로깅

## 2. 슬라이스 DAG
```
BAL-24 [app/llm.py ClaudeCLIClient]   ┐
BAL-25 [app/prompts/briefing.md]      ├─> BAL-27+28 [app/briefing.py 전체] ─ (config.disclaimer)
BAL-26 [app/schemas.py]               ┘
```
- **Wave1 (병렬)**: BAL-24 ‖ BAL-25 ‖ BAL-26 — disjoint 파일.
- **Wave2 (단독)**: BAL-27(run_securities/run_portfolio) + BAL-28(assemble_briefing/run_briefing) → **둘 다 `app/briefing.py`라 한 에이전트가 함께 구현**(파일 공유 = 순차 불가피 → 통합).
- **Wave3**: tests/test_briefing.py (DoD 검증).

## 3. 파일 소유권 (충돌 0)
| 슬라이스 | 소유 파일 | 의존(읽기) |
|----------|-----------|------------|
| BAL-24 | `app/llm.py` (신규: ClaudeCLIClient, LLMError) | `models.LLMClient` Protocol(BAL-3 완료) |
| BAL-25 | `app/prompts/briefing.md` (신규, 코드 아님) | 06 §6 |
| BAL-26 | `app/schemas.py` (신규: SECURITY_SCHEMA, PORTFOLIO_SCHEMA) | 06 §2, models §15.2 |
| BAL-27+28 | `app/briefing.py` (전체 구현) + `app/config.py`(disclaimer) | llm.py·schemas.py·prompts·models·metrics·db·gate |
| (DoD) | `tests/test_briefing.py` (신규) + conftest | 전체 |

## 4. Cross-cutting 결정 (★ 환각 차단 핵심)
1. **숫자는 코드가 박는다(SSoT §7)**: LLM은 `{key}` placeholder만. `inject()`가 S5 계산값으로 단방향 치환. echo-reject 루프 없음.
2. **RAW_NUMBER 린터**: 슬롯 밖 raw 숫자(`12%`·`3000원`) 발견 시 reject → 배치 1회 재호출, 재실패 시 failed 카드.
3. **BANNED 린터**: 권유·단정어(매수하세요/반드시/보장…) reject.
4. **ct join(G2)**: LLM `canonical_ticker` echo를 holdings에 left-join. 미매칭/중복/누락 → `HoldExcluded(reason='llm_unmatched'|'llm_duplicate')` + failed 카드. 정상 종목 영향 0.
5. **보류 종목 LLM 미호출**: `hold_status != 'ok'`(data_pending/fx_held/warmup)은 run_securities `live` 필터에서 제외 → status 카드만.
6. **면책은 코드 상수**: `BriefingDoc.disclaimer` = `config.DISCLAIMER`. LLM 생성 금지.
7. **수치 슬롯 분리 경계**: 06(run_securities)=텍스트 전용 SecurityLLMOut + failed 반환. 04(assemble_briefing)=수치 코드 주입 → 최종 SecurityCard. (BAL-3 models.py에 DTO 존재)

## 5. 위험 요소
| 위험 | 영향 | 대응 |
|------|------|------|
| 테스트가 실제 `claude` CLI 호출 | 높음 | **FakeLLMClient**(canned structured_output) 주입. subprocess 절대 안 탐 |
| `run_all_metrics`(§10.1) 미존재 — W3은 개별 metric만 | 높음 | BAL-28에서 metrics 통합 어댑터 필요 여부 확인. 없으면 최소 통합 함수 작성 or 범위 명시 |
| db.insert_briefing/headlines_map/holdings 헬퍼 미존재 | 중간 | BAL-28에서 필요 헬퍼 확인·추가(named param) |
| ANTHROPIC_API_KEY 노출 | 중간 | `.env` 환경변수만, 로그/예외에 키 금지 |

## 6. 슬라이스 진입점
| 슬라이스 | dev-guide |
|----------|-----------|
| BAL-24 | `docs/BAL-4-BAL-24-dev-guide.md` |
| BAL-25 | `docs/BAL-4-BAL-25-dev-guide.md` |
| BAL-26 | `docs/BAL-4-BAL-26-dev-guide.md` |
| BAL-27 | `docs/BAL-4-BAL-27-dev-guide.md` (하위 BAL-54/55 포함) |
| BAL-28 | `docs/BAL-4-BAL-28-dev-guide.md` |

## 7. 검증
- 각 슬라이스: `ruff check` + import.
- 통합: `pytest tests/test_briefing.py` — 금지어 0·면책 포함·raw 숫자 0·ct join 3케이스(누락/중복/변형)·보류 LLM 미호출. + `pytest -q` 전체 무손상.
