# Metrics — 지표 엔진 (`app/metrics/`)

> 참조 시점: 지표 계산·게이트·보류 판정 수정. SoT = `docs/04-backend.md §9·§10.2`.

## priced.py — 통화정규화 (04 §9.1)

`build_priced(conn, holdings, fx_ok, us_ok) -> list[PricedHolding]` — base=KRW.
- `value_base` = quantity×close_raw×(fx if US else 1); USD현금 = value_manual×fx.
- status enum(§15.4): `ok | data_pending | fx_held | warmup | failed`.
- **NEVER**: fx 결측 시 분모 제외/0 위장 금지 — USD 자산은 `fx_held`로 산출 거부.

## portfolio.py — 포트폴리오 지표

| 함수 | 산출 |
|------|------|
| `auto_targets(holdings)` | target_pct 미지정 종목 자동목표(평가액 비의존, G5) |
| `drift(priced, targets, band_abs, band_rel, micro_floor)` | ① 자산군 5/25 드리프트 `DriftResult(per_group, flags, rebalance_needed)` |
| `core_sat(priced, limit_pct)` | ② 코어/새틀 30% 한도 `CoreSatResult(core_pct, satellite_pct, over_limit)` |
| `asset_alloc(priced, usd_held, threshold)` | 1층 배분 `AllocResult(equity_pct, cash_pct, alloc_held)` |
| `dca(priced, drift, valuations, monthly)` | ⑥ 적립 후보 `DcaResult(allocations, note_key)` |

## security.py — 종목 지표

- `valuation(Funda) -> ValuationLabel(label, pctile, per, pbr, div_yield)` — ③ 양면 라벨. percentile NULL → "워밍업 중" degrade.
- `trend(OHLCV) -> TrendLabel(week52_pos, sma200_gap)` — ④ 52주 위치(0~1)·SMA200 이격(비율). 윈도우 부족 → None.
- `regime(row) -> str` — ⑤ KOSPI PBR + Shiller CAPE 라벨.

## gate.py — 신선도 게이트 (04 §10.2)

- `collect_complete_today(conn)` — 08:00→08:30 핸드오프 선검사.
- `evaluate_gate(conn) -> GateResult(blocked, fx_ok, us_ok, banner)` — collect_run 기준. 차단은 `FAIL`만.
- 신선도 배지는 `briefing.build_freshness_badge`(G10) — 시세/환율 경과일 최악값으로 `fresh(≤1)/stale(≤4)/warn`, 데이터 결측 → 999 안전 degrade.

## change_pct (Level 1, briefing.py 소유)

`briefing._change_pct(conn, ct)` — `db.last_two_closes` 최신 2거래일 close_adj. SecurityMetric에 주입되어
슬롯 `{change_pct}`·카드 등락 배지·why_needed 판정(≥3% + 헤드라인)에 사용.

## NEVER

- **0/NULL 위장 금지** — 산출 불가는 None + 보류 status로 정직하게.
- **current_pct 분모** = 산출가능 equity 합 — 보류 종목은 0%(분모 제외 아님).
- **수치 표기는 `_fmt`**(None → '—', signed 옵션) — 슬롯 문자열 일관성.
