# AI Briefing — LLM 파이프라인 (`app/briefing.py`·`llm.py`·`schemas.py`)

> 참조 시점: 브리핑 생성 로직·프롬프트·스키마·린트 수정. SoT = `docs/06-ai-agent.md` / `docs/04-backend.md §10`.

## 파이프라인 (`run_briefing`, 04 §10.1)

```
collect_complete_today 선검사 → evaluate_gate (차단 시 배너 doc 저장)
  → build_priced (통화정규화, 보류 분리)
  → _build_metrics (5종 지표 + change_pct)
  → build_security_inputs (슬롯·헤드라인·why_needed) / build_portfolio_input
  → run_securities (BATCH=10 분할) / run_portfolio (1회)
  → assemble_briefing (코드가 수치 주입) → db.insert_briefing
```

## 책임 경계

- **06 소유**: 슬롯주입(`inject`)·린트(`lint`)·ct 조인(G2)·배치호출 → 텍스트 전용 `SecurityLLMOut`.
- **04 소유**: 수치를 코드가 직접 박아 `SecurityCard`/`BriefingDoc` 조립.

## 안전장치 (NEVER — CLAUDE.md Key Rules와 연동)

| 장치 | 동작 |
|------|------|
| `RAW_NUMBER` 린트 | LLM 원문(placeholder 보존 상태)에서 슬롯 밖 raw 숫자 검출 → `LintError`. **주입 후 검사 금지**(정상 수치 오탐) |
| `BANNED` 린트 | "매수하세요·반드시·보장" 등 단정 매매지시 금지어 |
| ct echo join (G2) | 미매칭→`HoldExcluded('llm_unmatched')`, 응답 누락→`'failed'`, 중복→첫 건만+경고로그 |
| 배치 1회 재호출 | 린트/슬롯/LLM 실패 시 동일 배치 재호출, 재실패 → 배치 전 종목 failed 카드 |
| hold_status 게이트 | `!= 'ok'` 또는 현금(ct=None)은 LLM 미호출 (G3/G6) |
| 면책 | `config.DISCLAIMER` 코드 상수 — LLM 생성 금지 |
| 헤드라인 sanitize | 프롬프트 직렬화 시 개행 제거 + title 100자/source 40자 절단(인젝션 표면 축소) |

## 슬롯 (코드 계산값만)

`_security_slots`: per·pbr·div_yield·valuation_band·pos_52w·sma200_gap·change_pct·current_pct·target_pct·drift.
포트폴리오: core_pct·satellite_pct·equity_pct·cash_pct. `inject`는 미정의 키 → `LLMError`.

## 변동 귀인 why_note (Level 1)

- `_change_pct(conn, ct)` — 최신 2거래일 `close_adj` 기준 등락률. 2건 미만/0분모 → None(0 위장 금지).
- `why_needed` = `|change_pct| ≥ WHY_MOVE_THRESHOLD(3.0)` **and** 헤드라인 보유 — **코드가 판정**, 프롬프트에 귀인 지시 주입.
- why_note도 린트+슬롯주입 동일 경로. `SecurityCard.why_note` 기본값 `""`(구버전 content_json 역직렬화 호환).

## ClaudeCLIClient (`app/llm.py`)

`claude -p --bare --model claude-sonnet-4-5 --output-format json --json-schema` subprocess.
envelope `is_error`/exit≠0 → `LLMError`(stderr 200자 절단, 시크릿 비노출). 시스템 프롬프트 = `app/prompts/briefing.md`(고정).

## 스키마 (`app/schemas.py`)

`SECURITY_SCHEMA`(securities[]: canonical_ticker echo + comment + trend_note + investment_points + why_note),
`PORTFOLIO_SCHEMA`(rebalance_note·dca_note·weight_note). **숫자형 필드 0개** — 수치는 슬롯주입이 1차 방어선.

## 테스트 패턴

`FakeLLMClient`(canned structured_output, `calls` 누적) — 실 claude CLI 절대 호출 금지. `tests/test_briefing.py` 참조.
