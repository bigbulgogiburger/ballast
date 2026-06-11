# Data Collection — 일배치 (`app/collect.py`)

> 참조 시점: collect 로직·게이트 status·백필 수정. SoT = `docs/04-backend.md §8`.

## 진입점

```python
run_collect(mode="daily" | "backfill") -> None
# db.connect() 1회 → auto_holdings → KR/US _collect_market → _collect_fx → _collect_regime
```

conn은 `run_collect`이 열어 격리 함수에 전달(전역 아님). 종목 단위 격리가 배치를 죽이지 않는다.

## _collect_market (04 §8.2)

1. 거래일 아님 → `collect_run(market, OK_HOLIDAY)` 기록 후 return (배너 오발동 방지, **선분기**).
2. auto 종목 loop, **종목 단위 try/except**:
   - `bucket.acquire()` (TokenBucket rps 페이싱)
   - `ohlcv = src.ohlcv(ct)` → `validate_response(rows=1, ...)`
   - **인라인 stale 검사**: `if ohlcv.trade_date != expected: raise`(decisions §3.4, 가드 본체 불변)
   - `upsert_price` / `upsert_funda` / `upsert_news(.., ct, ohlcv.trade_date)`
   - 실패 → `n_fail++`, `missing.append(ct)`, log.warning (배치 계속)
3. `_status_of(n_ok, n_fail, mode)` → `upsert_collect_run(.., json.dumps(missing))`.

## _status_of (순수함수, 04 §8.4)

```
mode==backfill → BACKFILL   (1순위)
n_ok==0        → FAIL
n_fail>0       → PARTIAL
else           → OK
```

`OK_HOLIDAY`는 `_collect_market` 선분기이지 `_status_of` 내부 아님(5번째 status).

## _collect_fx / _collect_regime

- **FX 실패** → `collect_run(FX, FAIL)` → 게이트가 USD 자산+현금 보류(04 §8, 05 §1.5).
- **regime** — 이번 달 `market_regime` row 있으면 skip(월단위, 04 §8). 실패=degrade(collect_run 미기록, 레짐은 게이트 비차단).

## TokenBucket (04 §8.6)

직전 호출과 최소 간격 `1/rps` 보장(monotonic). rps는 `config.{NAVER,FMP}_RPS`. 정밀 누적 버킷 불요(과설계 금지).

## NEVER

- **종목 예외가 배치를 중단시키지 말 것** — 종목 try/except 격리(AC5, 04:557). 다음 종목 계속.
- **missing_tickers를 헬퍼가 재직렬화 금지** — caller가 `json.dumps`한 문자열 전달.
- **collect가 db.py 본체를 수정 금지** — db 헬퍼 호출만.

## 게이트 의미 (collect_run status)

차단은 `FAIL`만: FX FAIL→US 전체 보류, US FAIL→US 종목만 제외+KR 정상, 전 시장 미갱신→생성 거부. `BACKFILL`/`OK_HOLIDAY`는 정상 진행+라벨.

## 운영 연동 (W6 — `operations.md` 상세)

- `scripts/run_collect.py` — `--backfill` 명시 또는 `is_backfill_complete` G9 핸드오프로 모드 자동 결정.
- 수집 FAIL → `notify.send_fail_alert` (backfill 모드는 스팸 방지 억제).
- launchd 08:00 스케줄 (`ops/com.ballast.collect.plist`).

## 미구현

FMP 250req/day 일일 한도 누적 추적(현재 rps blocking까지 — 백필 분할로 우회).
