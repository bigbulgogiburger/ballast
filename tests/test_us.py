"""BAL-13 app/sources/us.py 단위 테스트. 외부 소스(Stooq/yfinance/Finnhub/FMP) 전량 모킹."""
import pandas as pd
import pytest

import app.sources as sources_pkg
from app.sources import us
from app.sources.us import UsSource


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(sources_pkg.time, "sleep", lambda *a, **k: None)


def _win(raw0=100.0, adj0=98.0, periods=300):
    idx = pd.date_range("2025-01-01", periods=periods)
    return pd.DataFrame(
        {"close_raw": [raw0 + i for i in range(periods)],
         "close_adj": [adj0 + i for i in range(periods)]},
        index=idx,
    )


@pytest.mark.unit
def test_ohlcv_stooq_primary(monkeypatch):
    monkeypatch.setattr(UsSource, "_ohlcv_stooq", lambda self, ct, s, e: _win())
    o = UsSource().ohlcv("AAPL")
    assert o.canonical_ticker == "AAPL" and o.ccy == "USD"
    assert isinstance(o.close_raw, float) and isinstance(o.sma200, float)
    assert o.close_raw != o.close_adj  # raw/adj 분리


@pytest.mark.unit
def test_ohlcv_yf_fallback_when_stooq_empty(monkeypatch):
    monkeypatch.setattr(UsSource, "_ohlcv_stooq", lambda self, ct, s, e: None)
    monkeypatch.setattr(UsSource, "_ohlcv_yf", lambda self, ct, s, e: _win(periods=260))
    o = UsSource().ohlcv("AAPL")
    assert isinstance(o.week52_high, float) and isinstance(o.sma200, float)


@pytest.mark.unit
def test_ohlcv_short_window_none(monkeypatch):
    monkeypatch.setattr(UsSource, "_ohlcv_stooq", lambda self, ct, s, e: _win(periods=50))
    o = UsSource().ohlcv("NEWCO")
    assert o.sma200 is None and o.week52_high is None  # 윈도우 부족


@pytest.mark.unit
def test_ohlcv_finnhub_quote_last_resort(monkeypatch):
    monkeypatch.setattr(UsSource, "_ohlcv_stooq", lambda self, ct, s, e: None)
    monkeypatch.setattr(UsSource, "_ohlcv_yf", lambda self, ct, s, e: None)
    monkeypatch.setattr(us.config, "FINNHUB_API_KEY", "k")

    class R:
        def raise_for_status(self): pass
        def json(self): return {"c": 191.5, "t": 1717400000}

    monkeypatch.setattr(us.requests, "get", lambda *a, **k: R())
    o = UsSource().ohlcv("AAPL")
    assert o.close_raw == 191.5 and o.week52_high is None and o.sma200 is None


@pytest.mark.unit
def test_ohlcv_all_empty_raises(monkeypatch):
    from app.sources import EmptyResponseError
    monkeypatch.setattr(UsSource, "_ohlcv_stooq", lambda self, ct, s, e: None)
    monkeypatch.setattr(UsSource, "_ohlcv_yf", lambda self, ct, s, e: None)
    monkeypatch.setattr(us.config, "FINNHUB_API_KEY", "k")

    class R:
        def raise_for_status(self): pass
        def json(self): return {"c": None, "t": None}

    monkeypatch.setattr(us.requests, "get", lambda *a, **k: R())
    with pytest.raises(EmptyResponseError):
        UsSource().ohlcv("AAPL")


def _ratios(per_list):
    return [
        {"date": f"202{i%5}-12-31", "priceEarningsRatio": p,
         "priceToBookRatio": 3.0, "dividendYield": 0.015}
        for i, p in enumerate(per_list)
    ]


@pytest.mark.unit
def test_fundamentals_fmp_percentile(monkeypatch):
    monkeypatch.setattr(us.config, "FMP_API_KEY", "k")
    monkeypatch.setattr(UsSource, "_fmp_ratios", lambda self, ct, key: _ratios(list(range(1, 41))))
    f = UsSource().fundamentals("AAPL")
    assert f.per == 1.0 and f.pbr == 3.0
    assert 0.0 <= f.per_pctile_5y <= 100.0
    assert f.report_date is None  # EDGAR PoC degrade


@pytest.mark.unit
def test_fundamentals_negative_per_none(monkeypatch):
    monkeypatch.setattr(us.config, "FMP_API_KEY", "k")
    monkeypatch.setattr(UsSource, "_fmp_ratios", lambda self, ct, key: _ratios([-3, 12, 10]))
    f = UsSource().fundamentals("AAPL")  # rows[0]=최신=적자
    assert f.per is None and f.per_pctile_5y is None


@pytest.mark.unit
def test_fundamentals_missing_key_raises(monkeypatch):
    monkeypatch.setattr(us.config, "FMP_API_KEY", None)
    with pytest.raises(KeyError):
        UsSource().fundamentals("AAPL")


@pytest.mark.unit
def test_headlines_finnhub(monkeypatch):
    monkeypatch.setattr(us.config, "FINNHUB_API_KEY", "k")

    class R:
        def raise_for_status(self): pass
        def json(self): return [
            {"headline": "Apple beats", "url": "http://a"},
            {"headline": "", "url": "http://skip"},  # 빈 headline 제외
        ]

    monkeypatch.setattr(us.requests, "get", lambda *a, **k: R())
    hl = UsSource().headlines("AAPL", "Apple")
    assert len(hl) == 1 and hl[0].source == "finnhub" and hl[0].title == "Apple beats"


@pytest.mark.unit
def test_headlines_empty_returns_list(monkeypatch):
    monkeypatch.setattr(us.config, "FINNHUB_API_KEY", "k")

    class R:
        def raise_for_status(self): pass
        def json(self): return []

    monkeypatch.setattr(us.requests, "get", lambda *a, **k: R())
    assert UsSource().headlines("AAPL", "Apple") == []


@pytest.mark.unit
def test_headlines_missing_key_raises(monkeypatch):
    monkeypatch.setattr(us.config, "FINNHUB_API_KEY", None)
    with pytest.raises(KeyError):
        UsSource().headlines("AAPL", "Apple")
