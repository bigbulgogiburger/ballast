"""W2-1 db.py 헬퍼 단위 테스트 (BAL-2 decisions §3.5). 순수 로컬 SQLite."""
import json

import pytest

from app import db
from app.models import FxRate, Headline, RegimeRow


@pytest.mark.unit
def test_upsert_fx_roundtrip(conn):
    db.upsert_fx(conn, FxRate(trade_date="2026-06-03", pair="USDKRW", rate=1380.5))
    row = db.latest_fx(conn)
    assert row["rate"] == 1380.5 and row["trade_date"] == "2026-06-03"


@pytest.mark.unit
def test_upsert_fx_conflict_updates_rate(conn):
    db.upsert_fx(conn, FxRate("2026-06-03", "USDKRW", 1380.5))
    db.upsert_fx(conn, FxRate("2026-06-03", "USDKRW", 1390.0))  # 동일 PK
    rows = conn.execute("SELECT rate FROM fx_snapshot").fetchall()
    assert len(rows) == 1 and rows[0][0] == 1390.0


@pytest.mark.unit
def test_upsert_news_dedup_by_url(conn):
    hs = [
        Headline(title="삼성 신고가", url="http://a", source="finnhub"),
        Headline(title="삼성 신고가(중복url)", url="http://a", source="finnhub"),
        Headline(title="배당 발표", url="http://b", source="finnhub"),
    ]
    db.upsert_news(conn, hs, "005930", "2026-06-03")
    rows = conn.execute("SELECT url, title FROM news_snapshot ORDER BY url").fetchall()
    assert len(rows) == 2  # url 중복 무시 (DO NOTHING)
    assert rows[0]["title"] == "삼성 신고가"  # 첫 삽입 보존


@pytest.mark.unit
def test_upsert_news_empty_list_noop(conn):
    db.upsert_news(conn, [], "005930", "2026-06-03")
    assert conn.execute("SELECT count(*) FROM news_snapshot").fetchone()[0] == 0


@pytest.mark.unit
def test_upsert_market_regime_mapping(conn):
    db.upsert_market_regime(conn, RegimeRow(as_of="2026-06-01", kospi_pbr=1.05, us_cape=33.2))
    row = conn.execute("SELECT trade_date, shiller_cape, kospi_pbr FROM market_regime").fetchone()
    assert row["trade_date"] == "2026-06-01"   # as_of → trade_date
    assert row["shiller_cape"] == 33.2          # us_cape → shiller_cape
    assert row["kospi_pbr"] == 1.05


@pytest.mark.unit
def test_upsert_market_regime_conflict_updates(conn):
    db.upsert_market_regime(conn, RegimeRow("2026-06-01", 1.0, None))
    db.upsert_market_regime(conn, RegimeRow("2026-06-01", 1.1, 34.0))  # 동일 trade_date
    rows = conn.execute("SELECT kospi_pbr, shiller_cape FROM market_regime").fetchall()
    assert len(rows) == 1 and rows[0]["kospi_pbr"] == 1.1 and rows[0]["shiller_cape"] == 34.0


@pytest.mark.unit
def test_upsert_collect_run_roundtrip(conn):
    missing = json.dumps(["AAPL", "005930"])
    db.upsert_collect_run(conn, "2026-06-03", "KR", "PARTIAL", 28, 2, missing)
    row = conn.execute("SELECT * FROM collect_run").fetchone()
    assert row["status"] == "PARTIAL" and row["n_ok"] == 28 and row["n_fail"] == 2
    assert json.loads(row["missing_tickers"]) == ["AAPL", "005930"]


@pytest.mark.unit
def test_upsert_collect_run_conflict_updates(conn):
    db.upsert_collect_run(conn, "2026-06-03", "KR", "FAIL", 0, 30, None)
    db.upsert_collect_run(conn, "2026-06-03", "KR", "OK", 30, 0, None)  # 동일 PK
    rows = conn.execute("SELECT status, n_ok FROM collect_run").fetchall()
    assert len(rows) == 1 and rows[0]["status"] == "OK" and rows[0]["n_ok"] == 30


@pytest.mark.unit
def test_upsert_collect_run_check_rejects_bad_status(conn):
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        db.upsert_collect_run(conn, "2026-06-03", "KR", "BOGUS", 1, 0, None)


@pytest.mark.unit
def test_auto_holdings_filters_auto_only(conn):
    conn.execute(
        "INSERT INTO holdings (asset_class, instrument, tracking, market, canonical_ticker, name, quantity) "
        "VALUES ('equity','stock','auto','KR','005930','삼성전자',10)"
    )
    conn.execute(
        "INSERT INTO holdings (asset_class, instrument, tracking, name, value_manual, ccy) "
        "VALUES ('cash','cash','manual','USD예금',1000,'USD')"
    )
    conn.commit()
    rows = db.auto_holdings(conn)
    assert len(rows) == 1
    assert rows[0]["market"] == "KR" and rows[0]["canonical_ticker"] == "005930"
    assert rows[0]["name"] == "삼성전자"
