"""BAL-17 app/collect.py 단위/통합 테스트. 어댑터·캘린더 모킹, in-memory DB."""
import time
from datetime import date

import pytest

from app import collect
from app.collect import TokenBucket, _status_of
from app.models import Funda, FxRate, Headline, OHLCV, RegimeRow

_TODAY = date(2026, 6, 3)
_EXPECTED = date(2026, 6, 2)
_EXP_ISO = _EXPECTED.isoformat()


def _ohlcv(ct, td=_EXP_ISO):
    return OHLCV(canonical_ticker=ct, trade_date=td, close_raw=100.0, close_adj=99.0,
                 ccy="USD", week52_high=120.0, week52_low=80.0, sma200=95.0)


def _funda(ct):
    return Funda(canonical_ticker=ct, trade_date=_EXP_ISO, per=12.0, pbr=1.1,
                 div_yield=2.0, per_pctile_5y=40.0, pbr_pctile_5y=35.0, report_date=None)


@pytest.fixture
def trading(monkeypatch):
    monkeypatch.setattr(collect.calendar, "is_trading_day", lambda m, d: True)
    monkeypatch.setattr(collect.calendar, "expected_trade_date", lambda m, d: _EXPECTED)


# ── _status_of (순수함수) ──
@pytest.mark.unit
@pytest.mark.parametrize("n_ok,n_fail,mode,expected", [
    (5, 0, "daily", "OK"),
    (4, 1, "daily", "PARTIAL"),
    (0, 3, "daily", "FAIL"),
    (3, 0, "backfill", "BACKFILL"),
    (0, 0, "backfill", "BACKFILL"),
])
def test_status_of(n_ok, n_fail, mode, expected):
    assert _status_of(n_ok, n_fail, mode) == expected


# ── TokenBucket ──
@pytest.mark.unit
def test_token_bucket_paces():
    tb = TokenBucket(rps=50)  # interval 0.02s
    tb.acquire()
    t0 = time.monotonic()
    tb.acquire()
    assert time.monotonic() - t0 >= 0.018  # 2번째 호출이 간격만큼 대기


@pytest.mark.unit
def test_token_bucket_zero_rps_noop():
    TokenBucket(rps=0).acquire()  # 예외 없음


# ── _collect_market ──
@pytest.mark.unit
def test_collect_market_holiday_skips(conn, monkeypatch):
    monkeypatch.setattr(collect.calendar, "is_trading_day", lambda m, d: False)
    collect._collect_market("US", [], _TODAY, "daily", conn)
    row = conn.execute("SELECT status FROM collect_run WHERE market='US'").fetchone()
    assert row["status"] == "OK_HOLIDAY"


@pytest.mark.unit
def test_collect_market_all_ok(conn, trading, monkeypatch):
    monkeypatch.setattr(collect.UsSource, "ohlcv", lambda self, ct: _ohlcv(ct))
    monkeypatch.setattr(collect.UsSource, "fundamentals", lambda self, ct: _funda(ct))
    monkeypatch.setattr(collect.UsSource, "headlines", lambda self, ct, name: [
        Headline(title="t", url="http://u", source="finnhub")])
    holdings = [{"market": "US", "canonical_ticker": "AAPL", "name": "Apple"},
                {"market": "US", "canonical_ticker": "MSFT", "name": "Microsoft"}]
    collect._collect_market("US", holdings, _TODAY, "daily", conn)
    cr = conn.execute("SELECT status, n_ok, n_fail FROM collect_run WHERE market='US'").fetchone()
    assert cr["status"] == "OK" and cr["n_ok"] == 2 and cr["n_fail"] == 0
    assert conn.execute("SELECT count(*) FROM price_snapshot").fetchone()[0] == 2
    assert conn.execute("SELECT count(*) FROM news_snapshot").fetchone()[0] == 2


@pytest.mark.unit
def test_collect_market_partial(conn, trading, monkeypatch):
    def ohlcv(self, ct):
        if ct == "BADCO":
            raise RuntimeError("no data")
        return _ohlcv(ct)
    monkeypatch.setattr(collect.UsSource, "ohlcv", ohlcv)
    monkeypatch.setattr(collect.UsSource, "fundamentals", lambda self, ct: _funda(ct))
    monkeypatch.setattr(collect.UsSource, "headlines", lambda self, ct, name: [])
    holdings = [{"market": "US", "canonical_ticker": "AAPL", "name": "Apple"},
                {"market": "US", "canonical_ticker": "BADCO", "name": "Bad"}]
    collect._collect_market("US", holdings, _TODAY, "daily", conn)
    import json
    cr = conn.execute("SELECT status, n_ok, n_fail, missing_tickers FROM collect_run WHERE market='US'").fetchone()
    assert cr["status"] == "PARTIAL" and cr["n_ok"] == 1 and cr["n_fail"] == 1
    assert json.loads(cr["missing_tickers"]) == ["BADCO"]


@pytest.mark.unit
def test_collect_market_stale_date_fails_ticker(conn, trading, monkeypatch):
    monkeypatch.setattr(collect.UsSource, "ohlcv", lambda self, ct: _ohlcv(ct, td="2026-05-30"))  # stale
    monkeypatch.setattr(collect.UsSource, "fundamentals", lambda self, ct: _funda(ct))
    monkeypatch.setattr(collect.UsSource, "headlines", lambda self, ct, name: [])
    collect._collect_market("US", [{"market": "US", "canonical_ticker": "AAPL", "name": "Apple"}],
                            _TODAY, "daily", conn)
    cr = conn.execute("SELECT status, n_fail FROM collect_run WHERE market='US'").fetchone()
    assert cr["status"] == "FAIL" and cr["n_fail"] == 1  # 날짜검사 인라인(decisions §3.4)


@pytest.mark.unit
def test_collect_market_all_fail(conn, trading, monkeypatch):
    monkeypatch.setattr(collect.UsSource, "ohlcv",
                        lambda self, ct: (_ for _ in ()).throw(RuntimeError("net")))
    collect._collect_market("US", [{"market": "US", "canonical_ticker": "AAPL", "name": "Apple"}],
                            _TODAY, "daily", conn)
    cr = conn.execute("SELECT status, n_ok, n_fail FROM collect_run WHERE market='US'").fetchone()
    assert cr["status"] == "FAIL" and cr["n_ok"] == 0 and cr["n_fail"] == 1


@pytest.mark.unit
def test_collect_market_backfill_status(conn, trading, monkeypatch):
    monkeypatch.setattr(collect.UsSource, "ohlcv", lambda self, ct: _ohlcv(ct))
    monkeypatch.setattr(collect.UsSource, "fundamentals", lambda self, ct: _funda(ct))
    monkeypatch.setattr(collect.UsSource, "headlines", lambda self, ct, name: [])
    collect._collect_market("US", [{"market": "US", "canonical_ticker": "AAPL", "name": "Apple"}],
                            _TODAY, "backfill", conn)
    assert conn.execute("SELECT status FROM collect_run WHERE market='US'").fetchone()["status"] == "BACKFILL"


@pytest.mark.unit
def test_collect_market_news_uses_ohlcv_trade_date(conn, trading, monkeypatch):
    monkeypatch.setattr(collect.UsSource, "ohlcv", lambda self, ct: _ohlcv(ct, td=_EXP_ISO))
    monkeypatch.setattr(collect.UsSource, "fundamentals", lambda self, ct: _funda(ct))
    monkeypatch.setattr(collect.UsSource, "headlines", lambda self, ct, name: [
        Headline(title="t", url="http://u", source="finnhub")])
    collect._collect_market("US", [{"market": "US", "canonical_ticker": "AAPL", "name": "Apple"}],
                            _TODAY, "daily", conn)
    row = conn.execute("SELECT trade_date FROM news_snapshot WHERE canonical_ticker='AAPL'").fetchone()
    assert row["trade_date"] == _EXP_ISO  # today가 아니라 ohlcv.trade_date


@pytest.mark.unit
def test_collect_market_isolation_continues(conn, trading, monkeypatch):
    def ohlcv(self, ct):
        if ct == "BADCO":
            raise RuntimeError("mid-loop")
        return _ohlcv(ct)
    monkeypatch.setattr(collect.UsSource, "ohlcv", ohlcv)
    monkeypatch.setattr(collect.UsSource, "fundamentals", lambda self, ct: _funda(ct))
    monkeypatch.setattr(collect.UsSource, "headlines", lambda self, ct, name: [])
    holdings = [{"market": "US", "canonical_ticker": "AAPL", "name": "Apple"},
                {"market": "US", "canonical_ticker": "BADCO", "name": "Bad"},
                {"market": "US", "canonical_ticker": "MSFT", "name": "Microsoft"}]
    collect._collect_market("US", holdings, _TODAY, "daily", conn)
    cr = conn.execute("SELECT n_ok, n_fail FROM collect_run WHERE market='US'").fetchone()
    assert cr["n_ok"] == 2 and cr["n_fail"] == 1
    got = {r[0] for r in conn.execute("SELECT canonical_ticker FROM price_snapshot")}
    assert "MSFT" in got  # 2번째 실패 후에도 3번째 수집됨(04:557 격리 연속성)


# ── _collect_fx ──
@pytest.mark.unit
def test_collect_fx_ok(conn, monkeypatch):
    monkeypatch.setattr(collect.FxSource, "usdkrw", lambda self: FxRate("2026-06-03", "USDKRW", 1380.0))
    collect._collect_fx(_TODAY, "daily", conn)
    assert conn.execute("SELECT status FROM collect_run WHERE market='FX'").fetchone()["status"] == "OK"
    assert conn.execute("SELECT rate FROM fx_snapshot").fetchone()["rate"] == 1380.0


@pytest.mark.unit
def test_collect_fx_fail(conn, monkeypatch):
    monkeypatch.setattr(collect.FxSource, "usdkrw",
                        lambda self: (_ for _ in ()).throw(RuntimeError("fx down")))
    collect._collect_fx(_TODAY, "daily", conn)
    assert conn.execute("SELECT status FROM collect_run WHERE market='FX'").fetchone()["status"] == "FAIL"


# ── _collect_regime ──
@pytest.mark.unit
def test_collect_regime_upserts(conn, monkeypatch):
    monkeypatch.setattr(collect.RegimeProvider, "regime",
                        lambda self: RegimeRow(as_of="2026-06-01", kospi_pbr=1.05, us_cape=33.0))
    collect._collect_regime(_TODAY, conn)
    row = conn.execute("SELECT shiller_cape, kospi_pbr FROM market_regime").fetchone()
    assert row["shiller_cape"] == 33.0 and row["kospi_pbr"] == 1.05


@pytest.mark.unit
def test_collect_regime_skips_when_month_exists(conn, monkeypatch):
    db_calls = {"n": 0}

    def regime(self):
        db_calls["n"] += 1
        return RegimeRow("2026-06-01", 1.0, 30.0)

    monkeypatch.setattr(collect.RegimeProvider, "regime", regime)
    collect._collect_regime(_TODAY, conn)   # 1번째: upsert
    collect._collect_regime(_TODAY, conn)   # 2번째: 이번 달 row 존재 → skip
    assert db_calls["n"] == 1


@pytest.mark.unit
def test_collect_regime_degrade_on_failure(conn, monkeypatch):
    monkeypatch.setattr(collect.RegimeProvider, "regime",
                        lambda self: (_ for _ in ()).throw(RuntimeError("regime down")))
    collect._collect_regime(_TODAY, conn)  # 예외 삼킴(degrade)
    assert conn.execute("SELECT count(*) FROM market_regime").fetchone()[0] == 0


# ── run_collect 통합 ──
@pytest.mark.integration
def test_run_collect_end_to_end(conn, trading, monkeypatch):
    class _NoClose:  # run_collect finally가 fixture conn을 닫지 않도록 위임 프록시
        def __getattr__(self, n):
            return getattr(conn, n)

        def close(self):
            pass

    monkeypatch.setattr(collect.db, "connect", lambda *a, **k: _NoClose())
    conn.execute(
        "INSERT INTO holdings (asset_class, instrument, tracking, market, canonical_ticker, name, quantity) "
        "VALUES ('equity','stock','auto','US','AAPL','Apple',10)"
    )
    conn.commit()
    monkeypatch.setattr(collect.UsSource, "ohlcv", lambda self, ct: _ohlcv(ct))
    monkeypatch.setattr(collect.UsSource, "fundamentals", lambda self, ct: _funda(ct))
    monkeypatch.setattr(collect.UsSource, "headlines", lambda self, ct, name: [])
    monkeypatch.setattr(collect.KrSource, "ohlcv", lambda self, ct: _ohlcv(ct))
    monkeypatch.setattr(collect.KrSource, "fundamentals", lambda self, ct: _funda(ct))
    monkeypatch.setattr(collect.KrSource, "headlines", lambda self, ct, name: [])
    monkeypatch.setattr(collect.FxSource, "usdkrw", lambda self: FxRate("2026-06-03", "USDKRW", 1380.0))
    monkeypatch.setattr(collect.RegimeProvider, "regime", lambda self: RegimeRow("2026-06-01", 1.05, 33.0))
    collect.run_collect("daily")
    # US OK(1종목), KR OK_HOLIDAY 아님(trading mock True라 OK·0종목→FAIL), FX OK, regime upsert
    assert conn.execute("SELECT status FROM collect_run WHERE market='US'").fetchone()["status"] == "OK"
    assert conn.execute("SELECT status FROM collect_run WHERE market='FX'").fetchone()["status"] == "OK"
    assert conn.execute("SELECT rate FROM fx_snapshot").fetchone()["rate"] == 1380.0
