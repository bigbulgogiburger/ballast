"""BAL-11 app/sources/kr.py 단위 테스트. 외부 소스(pykrx/FDR/네이버) 전량 모킹."""
import pandas as pd
import pytest

import app.sources as sources_pkg
from app.sources import EmptyResponseError, kr
from app.sources.kr import KrSource


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(sources_pkg.time, "sleep", lambda *a, **k: None)


def _ohlcv_df(values, col="종가", periods=300):
    idx = pd.date_range("2023-01-01", periods=periods, freq="D")
    return pd.DataFrame({col: [float(v) for v in values]}, index=idx)


@pytest.mark.unit
def test_ohlcv_returns_realistic_dto(monkeypatch):
    adj = _ohlcv_df([70000.0 + i for i in range(300)])
    raw = _ohlcv_df([71000.0 + i for i in range(300)])

    def fake(fromdate, todate, ticker, adjusted=True):
        return adj if adjusted else raw

    monkeypatch.setattr(kr.stock, "get_market_ohlcv", fake)
    o = KrSource().ohlcv("005930")
    assert o.canonical_ticker == "005930" and o.ccy == "KRW"
    assert isinstance(o.close_raw, float) and isinstance(o.close_adj, float)
    assert isinstance(o.sma200, float)
    assert o.week52_high >= o.week52_low
    assert len(o.trade_date) == 10  # YYYY-MM-DD
    assert o.close_raw != o.close_adj  # raw/adj 분리


@pytest.mark.unit
def test_ohlcv_short_window_sma_none(monkeypatch):
    adj = _ohlcv_df([1000.0 + i for i in range(50)], periods=50)  # <200거래일
    monkeypatch.setattr(
        kr.stock, "get_market_ohlcv",
        lambda f, t, ct, adjusted=True: adj,
    )
    o = KrSource().ohlcv("005930")
    assert o.sma200 is None  # 윈도우<200 → None (decisions #1)
    assert isinstance(o.week52_high, float)  # 가용분 max


@pytest.mark.unit
def test_ohlcv_empty_df_raises_empty_response(monkeypatch):
    import FinanceDataReader
    monkeypatch.setattr(kr.stock, "get_market_ohlcv", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(FinanceDataReader, "DataReader", lambda *a, **k: pd.DataFrame())
    with pytest.raises(EmptyResponseError):  # pykrx 빈 → FDR 폴백 빈 → 승격
        KrSource().ohlcv("005930")


@pytest.mark.unit
def test_ohlcv_pykrx_empty_falls_back_to_fdr(monkeypatch):
    import FinanceDataReader
    monkeypatch.setattr(kr.stock, "get_market_ohlcv", lambda *a, **k: pd.DataFrame())
    fdr_df = _ohlcv_df([5000.0 + i for i in range(250)], col="Close", periods=250)
    monkeypatch.setattr(FinanceDataReader, "DataReader", lambda *a, **k: fdr_df)
    o = KrSource().ohlcv("005930")
    assert o.close_raw == o.close_adj  # FDR 단일 Close


def _funda_df(per_list):
    idx = pd.date_range("2019-06-30", periods=len(per_list), freq="D")
    return pd.DataFrame(
        {
            "BPS": [50000.0] * len(per_list),
            "PER": [float(p) for p in per_list],
            "PBR": [1.0 + i * 0.01 for i in range(len(per_list))],
            "EPS": [5000.0] * len(per_list),
            "DIV": [2.5] * len(per_list),
            "DPS": [1000.0] * len(per_list),
        },
        index=idx,
    )


@pytest.mark.unit
def test_fundamentals_computes_percentile(monkeypatch):
    df = _funda_df(list(range(1, 41)))  # 40 표본, 최신 PER=40
    monkeypatch.setattr(kr.stock, "get_market_fundamental", lambda *a, **k: df)
    f = KrSource().fundamentals("005930")
    assert f.per == 40.0 and isinstance(f.pbr, float)
    assert f.div_yield == 2.5  # 제공자 값 그대로
    assert 0.0 <= f.per_pctile_5y <= 100.0
    assert f.report_date is None  # W1


@pytest.mark.unit
def test_fundamentals_negative_per_is_none(monkeypatch):
    df = _funda_df([10, 12, -5])  # 최신 적자
    monkeypatch.setattr(kr.stock, "get_market_fundamental", lambda *a, **k: df)
    f = KrSource().fundamentals("005930")
    assert f.per is None and f.per_pctile_5y is None  # 적자 → None


@pytest.mark.unit
def test_fundamentals_small_sample_pctile_none(monkeypatch):
    df = _funda_df([10, 12, 14])  # 표본<20
    monkeypatch.setattr(kr.stock, "get_market_fundamental", lambda *a, **k: df)
    f = KrSource().fundamentals("005930")
    assert f.per == 14.0 and f.per_pctile_5y is None


class _FakeResp:
    def __init__(self, items):
        self._items = items

    def raise_for_status(self):
        pass

    def json(self):
        return {"items": self._items}


@pytest.mark.unit
def test_headlines_strips_html_tags(monkeypatch):
    monkeypatch.setattr(kr.config, "NAVER_CLIENT_ID", "id")
    monkeypatch.setattr(kr.config, "NAVER_CLIENT_SECRET", "sec")
    monkeypatch.setattr(
        kr.requests, "get",
        lambda *a, **k: _FakeResp([
            {"title": "<b>삼성</b>전자 &amp; 신고가", "originallink": "http://x", "link": "http://y"}
        ]),
    )
    hl = KrSource().headlines("005930", "삼성전자")
    assert hl[0].title == "삼성전자 & 신고가" and hl[0].url == "http://x" and hl[0].source == "naver"


@pytest.mark.unit
def test_headlines_empty_returns_list_not_raise(monkeypatch):
    monkeypatch.setattr(kr.config, "NAVER_CLIENT_ID", "id")
    monkeypatch.setattr(kr.config, "NAVER_CLIENT_SECRET", "sec")
    monkeypatch.setattr(kr.requests, "get", lambda *a, **k: _FakeResp([]))
    assert KrSource().headlines("005930", "삼성전자") == []  # 뉴스 0건=정상


@pytest.mark.unit
def test_headlines_missing_keys_raises(monkeypatch):
    monkeypatch.setattr(kr.config, "NAVER_CLIENT_ID", None)
    monkeypatch.setattr(kr.config, "NAVER_CLIENT_SECRET", None)
    with pytest.raises(KeyError):  # 조용한 fallback 금지
        KrSource().headlines("005930", "삼성전자")
