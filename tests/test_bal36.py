"""is_backfill_complete 분기 전수 검증 (BAL-36 / M5 무인운영 G9 핸드오프).

데이터 완성도 게이트: 미설정(0홀딩)·미적재(price/funda 결측)·KR percentile 미해제는 False.
모든 auto 종목 price+funda row 존재 + KR 종목 per_pctile_5y NOT NULL → True.
US는 FMP degrade로 per_pctile_5y NULL 영구 허용(04 §8.5) → percentile 미요구.
collect_run.status는 보지 않는다(순환 회피). in-memory DB는 conftest.py conn fixture 재사용.
"""

from app import db


def _add_auto(conn, ct: str, market: str = "KR") -> None:
    """tracking='auto' 종목 1건 삽입(스키마 CHECK 충족 최소 필드)."""
    conn.execute(
        "INSERT INTO holdings "
        "(user_id, asset_class, instrument, tracking, market, canonical_ticker, "
        "name, quantity, ccy) "
        "VALUES (1, 'equity', 'stock', 'auto', ?, ?, ?, 10.0, ?)",
        (market, ct, ct, "KRW" if market == "KR" else "USD"),
    )
    conn.commit()


def _add_price(conn, ct: str) -> None:
    conn.execute(
        "INSERT INTO price_snapshot "
        "(canonical_ticker, trade_date, close_adj, close_raw, ccy) "
        "VALUES (?, '2026-06-04', 100.0, 100.0, 'KRW')",
        (ct,),
    )
    conn.commit()


def _add_funda(conn, ct: str, per_pctile_5y=None, trade_date: str = "2026-06-04") -> None:
    conn.execute(
        "INSERT INTO fundamentals_snapshot "
        "(canonical_ticker, trade_date, per, pbr, per_pctile_5y) "
        "VALUES (?, ?, 10.0, 1.0, ?)",
        (ct, trade_date, per_pctile_5y),
    )
    conn.commit()


def test_no_holdings_returns_false(conn):
    """auto 종목 0건 → 미설정을 완료로 오인하지 않음(False)."""
    assert db.is_backfill_complete(conn) is False


def test_missing_price_returns_false(conn):
    """funda만 있고 price 없는 종목 → False."""
    _add_auto(conn, "005930")
    _add_funda(conn, "005930", per_pctile_5y=0.5)
    assert db.is_backfill_complete(conn) is False


def test_missing_funda_returns_false(conn):
    """price만 있고 funda 없는 종목 → False."""
    _add_auto(conn, "005930")
    _add_price(conn, "005930")
    assert db.is_backfill_complete(conn) is False


def test_kr_percentile_null_returns_false(conn):
    """KR 종목 price+funda 있으나 per_pctile_5y NULL(백필 진행중) → False."""
    _add_auto(conn, "005930")
    _add_price(conn, "005930")
    _add_funda(conn, "005930", per_pctile_5y=None)
    assert db.is_backfill_complete(conn) is False


def test_kr_percentile_set_returns_true(conn):
    """KR 종목 price+funda + per_pctile_5y NOT NULL → True(percentile 해제)."""
    _add_auto(conn, "005930")
    _add_price(conn, "005930")
    _add_funda(conn, "005930", per_pctile_5y=0.42)
    assert db.is_backfill_complete(conn) is True


def test_us_percentile_null_allowed_true(conn):
    """US 종목은 per_pctile_5y NULL(FMP degrade)이어도 price+funda 있으면 완료 허용 → True."""
    _add_auto(conn, "AAPL", market="US")
    _add_price(conn, "AAPL")
    _add_funda(conn, "AAPL", per_pctile_5y=None)
    assert db.is_backfill_complete(conn) is True


def test_latest_funda_row_used(conn):
    """funda가 여러 행이면 최신 trade_date 행의 per_pctile_5y로 판정 — 과거 NULL은 무관."""
    _add_auto(conn, "005930")
    _add_price(conn, "005930")
    _add_funda(conn, "005930", per_pctile_5y=None, trade_date="2026-06-01")  # 과거 NULL
    _add_funda(conn, "005930", per_pctile_5y=0.30, trade_date="2026-06-04")  # 최신 해제
    assert db.is_backfill_complete(conn) is True


def test_status_backfill_ignored(conn):
    """collect_run.status=BACKFILL이어도 데이터 완성도가 충족되면 True(status 무관 — 순환 회피)."""
    _add_auto(conn, "005930")
    _add_price(conn, "005930")
    _add_funda(conn, "005930", per_pctile_5y=0.5)
    db.upsert_collect_run(conn, "2026-06-04", "KR", "BACKFILL", 1, 0, "[]")
    assert db.is_backfill_complete(conn) is True


def test_partial_holdings_returns_false(conn):
    """auto 2종목 중 1종목만 price+funda → False(전수 충족 아님)."""
    _add_auto(conn, "005930")
    _add_auto(conn, "AAPL", market="US")
    _add_price(conn, "005930")
    _add_funda(conn, "005930", per_pctile_5y=0.5)
    # AAPL은 price/funda 미적재
    assert db.is_backfill_complete(conn) is False


def test_mixed_kr_us_complete_true(conn):
    """KR(percentile 해제) + US(percentile NULL 허용) 혼합 모두 적재 → True."""
    _add_auto(conn, "005930")
    _add_auto(conn, "AAPL", market="US")
    _add_price(conn, "005930")
    _add_funda(conn, "005930", per_pctile_5y=0.5)
    _add_price(conn, "AAPL")
    _add_funda(conn, "AAPL", per_pctile_5y=None)
    assert db.is_backfill_complete(conn) is True
