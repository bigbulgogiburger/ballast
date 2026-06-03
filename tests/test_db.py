"""BAL-8 app/db.py 단위 테스트 (순수 로컬 SQLite, 네트워크 없음)."""
import sqlite3

import pytest

from app import db
from app.models import Funda, FxRate, OHLCV

_TABLES = {
    "holdings", "settings", "price_snapshot", "fundamentals_snapshot",
    "fx_snapshot", "news_snapshot", "market_regime", "collect_run", "briefing",
}


def _ohlcv(ct="005930", td="2024-01-02", raw=70000.0, adj=70000.0):
    return OHLCV(
        canonical_ticker=ct, trade_date=td, close_raw=raw, close_adj=adj,
        ccy="KRW", week52_high=80000.0, week52_low=60000.0, sma200=68000.0,
    )


def _funda(ct="005930", td="2024-01-02", per=12.5, pctile=None):
    return Funda(
        canonical_ticker=ct, trade_date=td, per=per, pbr=1.2, div_yield=2.5,
        per_pctile_5y=pctile, pbr_pctile_5y=pctile, report_date=None,
    )


@pytest.mark.unit
def test_connect_pragmas():
    c = db.connect(":memory:")
    assert c.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert c.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    assert c.row_factory is sqlite3.Row
    c.close()


@pytest.mark.unit
def test_connect_wal_on_file_db(tmp_path):
    c = db.connect(str(tmp_path / "t.db"))
    assert c.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    c.close()


@pytest.mark.unit
def test_init_schema_creates_9_tables(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    assert {r[0] for r in rows} == _TABLES


@pytest.mark.unit
def test_init_schema_indexes(conn):
    idx = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }
    assert {"ix_briefing_user_date", "ix_holdings_user_tracking", "ux_holdings_user_ct"} <= idx


@pytest.mark.unit
def test_init_schema_idempotent(conn):
    db.init_schema(conn)  # 2회차
    tables = conn.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchone()[0]
    assert tables == 9
    assert conn.execute("SELECT count(*) FROM settings").fetchone()[0] == 7


@pytest.mark.unit
def test_settings_seed(conn):
    rows = conn.execute("SELECT key, value FROM settings WHERE user_id=1").fetchall()
    d = {r[0]: r[1] for r in rows}
    assert len(d) == 7
    assert all(isinstance(v, str) for v in d.values())
    assert d["monthly_contribution"] == "0"
    assert d["micro_weight_floor"] == "1.0"
    assert d["base_currency"] == "KRW"


@pytest.mark.unit
def test_settings_seed_source_is_dataclass(conn):
    import dataclasses

    from app.config import SETTINGS_DEFAULTS
    assert not isinstance(SETTINGS_DEFAULTS, dict)
    db_keys = {r[0] for r in conn.execute("SELECT key FROM settings").fetchall()}
    assert db_keys == set(dataclasses.asdict(SETTINGS_DEFAULTS).keys())


@pytest.mark.unit
def test_settings_seed_no_override(conn):
    conn.execute("UPDATE settings SET value='USD' WHERE key='base_currency'")
    conn.commit()
    db.init_schema(conn)  # 재호출 → DO NOTHING
    assert conn.execute(
        "SELECT value FROM settings WHERE key='base_currency'"
    ).fetchone()[0] == "USD"


@pytest.mark.unit
def test_connect_wal_memory_db_does_not_raise():
    c = db.connect(":memory:")  # :memory:는 WAL 불가 → 'memory' 강등(예외 없음)
    assert c.execute("PRAGMA journal_mode").fetchone()[0] in {"wal", "memory"}
    c.close()


@pytest.mark.unit
def test_settings_seed_all_values(conn):
    d = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM settings WHERE user_id=1")}
    assert d == {
        "base_currency": "KRW",
        "monthly_contribution": "0",
        "satellite_limit_pct": "30",
        "rebalance_band_abs": "5",
        "rebalance_band_rel": "25",
        "micro_weight_floor": "1.0",
        "usd_cash_gate_threshold": "5.0",
    }


@pytest.mark.unit
def test_holdings_check_auto_keys(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO holdings (asset_class, instrument, tracking, name) "
            "VALUES ('equity','stock','auto','t')"  # ct/market/qty 누락
        )


@pytest.mark.unit
def test_holdings_check_ccy_enum(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO holdings (asset_class, instrument, tracking, name, value_manual, ccy) "
            "VALUES ('cash','cash','manual','t', 100, 'JPY')"
        )


@pytest.mark.unit
def test_holdings_check_manual_keys(conn):
    with pytest.raises(sqlite3.IntegrityError):  # value_manual 누락
        conn.execute(
            "INSERT INTO holdings (asset_class, instrument, tracking, name, ccy) "
            "VALUES ('cash','cash','manual','t','KRW')"
        )
    with pytest.raises(sqlite3.IntegrityError):  # quantity 있으면 위반
        conn.execute(
            "INSERT INTO holdings (asset_class, instrument, tracking, name, ccy, value_manual, quantity) "
            "VALUES ('cash','cash','manual','t','KRW',100,5)"
        )


@pytest.mark.unit
def test_upsert_price_insert_then_update(conn):
    db.upsert_price(conn, _ohlcv(raw=70000.0))
    db.upsert_price(conn, _ohlcv(raw=71000.0))  # 동일 PK 갱신
    rows = conn.execute("SELECT close_raw FROM price_snapshot").fetchall()
    assert len(rows) == 1 and rows[0][0] == 71000.0


@pytest.mark.unit
def test_upsert_price_new_date_appends(conn):
    db.upsert_price(conn, _ohlcv(td="2024-01-02"))
    db.upsert_price(conn, _ohlcv(td="2024-01-03"))
    assert conn.execute("SELECT count(*) FROM price_snapshot").fetchone()[0] == 2


@pytest.mark.unit
def test_upsert_funda_null_pctile(conn):
    db.upsert_funda(conn, _funda(pctile=None))
    row = db.latest_funda(conn, "005930")
    assert row["per_pctile_5y"] is None and row["per"] == 12.5


@pytest.mark.unit
def test_upsert_fx_default_pair(conn):
    db.upsert_fx(conn, FxRate(trade_date="2024-01-02", pair="USDKRW", rate=1300.0))
    row = db.latest_fx(conn)
    assert row["pair"] == "USDKRW" and row["rate"] == 1300.0


@pytest.mark.unit
def test_latest_price_returns_max_date(conn):
    db.upsert_price(conn, _ohlcv(td="2024-01-02"))
    db.upsert_price(conn, _ohlcv(td="2024-01-03"))
    assert db.latest_price(conn, "005930")["trade_date"] == "2024-01-03"


@pytest.mark.unit
def test_latest_price_none_when_empty(conn):
    assert db.latest_price(conn, "999999") is None


@pytest.mark.unit
def test_upsert_funda_insert_then_update(conn):
    db.upsert_funda(conn, _funda(per=12.5))
    db.upsert_funda(conn, _funda(per=15.0))  # 동일 PK 갱신
    rows = conn.execute("SELECT per FROM fundamentals_snapshot").fetchall()
    assert len(rows) == 1 and rows[0][0] == 15.0


@pytest.mark.unit
def test_latest_funda_returns_max_date(conn):
    db.upsert_funda(conn, _funda(td="2024-01-02", per=10.0))
    db.upsert_funda(conn, _funda(td="2024-01-03", per=11.0))
    row = db.latest_funda(conn, "005930")
    assert row["trade_date"] == "2024-01-03" and row["per"] == 11.0


@pytest.mark.unit
def test_latest_fx_returns_max_date(conn):
    db.upsert_fx(conn, FxRate(trade_date="2024-01-02", pair="USDKRW", rate=1300.0))
    db.upsert_fx(conn, FxRate(trade_date="2024-01-03", pair="USDKRW", rate=1310.0))
    row = db.latest_fx(conn)
    assert row["trade_date"] == "2024-01-03" and row["rate"] == 1310.0


@pytest.mark.unit
def test_latest_funda_none_when_empty(conn):
    assert db.latest_funda(conn, "999999") is None


@pytest.mark.unit
def test_latest_fx_none_for_unknown_pair(conn):
    assert db.latest_fx(conn, "EURKRW") is None


@pytest.mark.unit
def test_e2e_upsert_then_latest(conn):
    """슬라이스 E2E 축소판: upsert → latest 전필드 라운드트립(키명 정합 증명, decisions §3.4)."""
    o = _ohlcv(raw=70000.0, adj=69500.0)
    db.upsert_price(conn, o)
    pr = db.latest_price(conn, "005930")
    assert pr["canonical_ticker"] == o.canonical_ticker
    assert pr["trade_date"] == o.trade_date
    assert pr["close_raw"] == o.close_raw
    assert pr["close_adj"] == o.close_adj
    assert pr["ccy"] == o.ccy
    assert pr["week52_high"] == o.week52_high
    assert pr["week52_low"] == o.week52_low
    assert pr["sma200"] == o.sma200

    f = _funda(per=12.5, pctile=33.0)
    db.upsert_funda(conn, f)
    fr = db.latest_funda(conn, "005930")
    assert fr["canonical_ticker"] == f.canonical_ticker
    assert fr["trade_date"] == f.trade_date
    assert fr["per"] == f.per and fr["pbr"] == f.pbr and fr["div_yield"] == f.div_yield
    assert fr["per_pctile_5y"] == f.per_pctile_5y and fr["pbr_pctile_5y"] == f.pbr_pctile_5y
    assert fr["report_date"] == f.report_date
