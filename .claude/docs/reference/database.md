# Database — SQLite 스키마 & 헬퍼 (`app/db.py`)

> 참조 시점: 테이블/쿼리/upsert 추가, 캐시 조회. SoT = `docs/05-database.md`.

## 연결 (05 §0)

```python
connect(db_path="data/ballast.db") -> sqlite3.Connection
# row_factory=Row, PRAGMA foreign_keys=ON, journal_mode=WAL, busy_timeout=5000
```

- PRAGMA는 연결마다 적용. `:memory:`는 WAL→'memory' 자동 강등(정상).

## 스키마 (`init_schema`, 9테이블, 멱등)

`holdings · settings · price_snapshot · fundamentals_snapshot · fx_snapshot · news_snapshot · market_regime · collect_run · briefing` + 인덱스 ②④(`ix_briefing_user_date`, `ix_holdings_user_tracking`) + `ux_holdings_user_ct`. settings 7키 seed(`asdict(SETTINGS_DEFAULTS)`, ON CONFLICT DO NOTHING).

## 헬퍼

| 함수 | 비고 |
|------|------|
| `latest_price/funda/fx(conn, ct\|pair)` | `MAX(trade_date)` 1행, 0건→None (휴장/미적재 자동 흡수) |
| `upsert_price(conn, OHLCV)` / `upsert_funda(conn, Funda)` | frozen dataclass → `asdict` named-bind, ON CONFLICT DO UPDATE |
| `upsert_fx(conn, FxRate)` | W2에서 dict-surface→FxRate 전환 |
| `upsert_news(conn, list[Headline], ct, trade_date)` | PK(ct,trade_date,url) → DO NOTHING(url dedup) |
| `upsert_market_regime(conn, RegimeRow)` | as_of→trade_date, us_cape→shiller_cape 매핑 |
| `upsert_collect_run(conn, td, market, status, n_ok, n_fail, missing_tickers)` | PK(td,market), missing=caller가 json.dumps |
| `auto_holdings(conn, user_id=1)` | tracking='auto' 행(sqlite3.Row, 키 접근 `row["market"]`) |

## NEVER

- **f-string/문자열 연결로 SQL 작성 금지** — 전부 `?`/named param 바인딩.
- **upsert named param은 컬럼 전체명** — 05 §4.1 약어(`:ct/:td`)는 예시일 뿐, `asdict` 키와 1:1 정합 필요(decisions §3.4). 불일치 시 `ProgrammingError`.
- **조회 0건을 예외로 만들지 말 것** — `latest_*`는 None 반환, 보류 판정은 metrics(W3).
- **self-commit** — W1 upsert 헬퍼는 내부 `conn.commit()`(W2 배치는 종목 격리와 정합). 배치 단일 트랜잭션은 W2 PoC 범위 밖.

## 조정/미조정 (절대 혼동 금지)

- **현재 평가액** = `close_raw`(미조정).
- **52주/SMA200/percentile** = `close_adj`(조정) — 매 수집 시 윈도우 통째 fresh 재계산(캐시 누적 금지, stale 방지).

## 미구현 (W2+ 범위)

`upsert_holdings/settings/briefing`, 신선도 배지 집계 쿼리(05 §3.3), 게이트 판정 쿼리(05 §3.5), users 테이블(PoC 미생성).
