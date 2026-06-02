# Sprint Contract — BAL-1 / M1a 데이터 스파이크 (BAL-8~12)

> harness-plan 보충. dev-guide(`docs/BAL-{8..12}-dev-guide.md`) + 오케스트레이션(`docs/BAL-1-m1a-orchestration.md`) 위의 DoD/Verify/Out-of-Scope 정본.
> 브랜치 `feat/bal-1-m1a-spike` · 모드 wave-3-1-1 · HARNESS_MODE=auto(세션 degraded → 수동 게이트).

## 한 줄 성공 기준
> **삼성전자(005930)의 무료 시세·재무가 실제로 SQLite에 적재되고 `latest_*`로 조회된다** (로드맵 08 §Week1).

## Phase = Wave

### Wave W-1 — foundation (BAL-8 ∥ BAL-9 ∥ BAL-10)
**DoD**
- **W-1a 먼저(공유파일 충돌 제거)**: `app/models.py`에 W1 DTO 5종(HoldingInput mutable + OHLCV/Funda/Headline/RegimeRow frozen, 첫필드 `canonical_ticker`) 단독 정의·커밋 → 이후 BAL-8/9/11이 import만.
- BAL-8: `connect()` PRAGMA(FK/WAL/busy_timeout) 적용 + `init_schema()`가 05 §1 **9테이블** + 인덱스 ②④ + `ux_holdings_user_ct` 생성 + settings §15.5 seed(`dataclasses.asdict(SETTINGS_DEFAULTS)`, `str()` 변환, ON CONFLICT DO NOTHING). `latest_price/funda/fx` + 최소 `upsert_*`(frozen dataclass 인자) 동작.
- BAL-9: `to_source(source, ct, market)` 변환표(canonical 04 §5.1), `CORE_ETF_WHITELIST` frozenset, `classify_category(HoldingInput)`.
- BAL-10: `is_trading_day(market,d)/prev_trading_day(market,d)/expected_trade_date(market,today)` (XKRX/XNYS, US=직전거래일). ⚠️ 인자순서 `(market, d)`.

**Verify Targets**
- `python3 -c "import app.db as d; c=d.connect(':memory:'); d.init_schema(c); print(len([r[0] for r in c.execute(\"select name from sqlite_master where type='table' and name not like 'sqlite_%'\")]))"` → 9
- `pytest tests/test_tickers.py -q` → green (to_source 변환표)
- `python3 -c "from app.calendar import expected_trade_date; from datetime import date; print(expected_trade_date('KR', date.today()))"` → 거래일 1개
- 편집한 `.py` 전부 `python3 -m py_compile` 통과

### Wave W-2 — consumer (BAL-11 + regime KR, Tier-2: BAL-46/47/48)
**DoD**
- **W-2a 먼저**: `app/sources/__init__.py` 공통 가드 — `retry`/`validate_response(rows,latest,expected)`/`EmptyResponseError`(canonical 04 §7.1). BAL-11이 import.
- `KrSource().ohlcv('005930')` → close_raw·close_adj·week52·sma200 실수치(조정 윈도우 fresh 재계산).
- `fundamentals('005930')` → PER/PBR/div + `per_pctile_5y`(어댑터가 계산, 04 §7.2).
- `headlines('005930', name)` → `list[Headline]`(빈응답=[]). regime KR = `sources/regime.py RegimeProvider.regime()`→`RegimeRow(kospi_pbr=.., us_cape=None)`.
- 반환형 = `models.OHLCV/Funda/Headline/RegimeRow`(W1 부분 기여). `tickers.to_source`/`calendar` 사용. `@retry(3)`+`validate_response`.

**Verify Targets**
- `python3 -c "from app.sources.kr import KrSource; print(KrSource().ohlcv('005930'))"` → 실수치
- `pytest tests/test_kr*.py -q` (네트워크 모킹) → green

### Wave W-3 — integration proof (BAL-12)
**DoD**
- `EmptyResponseError` + `validate_response`: 빈 응답을 OK로 오인하지 않고 예외.
- E2E: 005930 fetch → `db.upsert_*` 적재 → `latest_price/funda` 실수치 row 반환.

**Verify Targets**
- `pytest -q` 전체 green
- 수동 스모크: 005930 적재 후 `latest_price` row 확인 로그

## Aggregate 게이트 (커밋 전)
- 각 wave 종료 시 변경분 리뷰(`bal-*` 지침 주입한 general 에이전트) → verdict PASS 필요.
- 세션 degraded이므로 `review-gate` hook 대신 오케스트레이터가 verdict 수동 확인 후 커밋.

## Out of Scope (W1 아님)
US/FX/regime 어댑터 · `collect.py` 배치/백필 · `metrics/` 계산 · `models.py`의 SecurityCard/BriefingDoc 등 LLM·렌더 DTO · 프론트(W5) · 손익/수익률(G8) · `briefing.py`.

## Verdict
- [ ] W-1 PASS
- [ ] W-2 PASS
- [ ] W-3 PASS → 슬라이스 통합 DoD(orchestration §5) 전건 → BAL-8~12 QA 전이
