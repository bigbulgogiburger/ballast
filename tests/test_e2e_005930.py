"""BAL-12 W-3 통합 증명: 005930 fetch → db.upsert → db.latest 라운드트립.

KR 어댑터 네트워크는 메서드 경계(KrSource.ohlcv/fundamentals)에서 모킹(decisions Q4).
슬라이스 전체(BAL-8 db / BAL-9 tickers / BAL-10 calendar / BAL-11 kr / models)가
한 종목으로 실제 맞물리는지 검증한다. 실 네트워크 검증은 DoD 수동 스모크로 분리.
"""
import pytest

from app.db import latest_funda, latest_price, upsert_funda, upsert_price
from app.models import Funda, OHLCV
from app.sources.kr import KrSource


@pytest.fixture
def fake_ohlcv() -> OHLCV:
    return OHLCV(
        canonical_ticker="005930", trade_date="2026-06-01",
        close_raw=81000.0, close_adj=81000.0, ccy="KRW",
        week52_high=88000.0, week52_low=68000.0, sma200=75000.0,
    )


@pytest.fixture
def fake_funda() -> Funda:
    return Funda(
        canonical_ticker="005930", trade_date="2026-06-01",
        per=14.2, pbr=1.3, div_yield=2.1,
        per_pctile_5y=42.0, pbr_pctile_5y=38.0, report_date="2026-03-31",
    )


@pytest.mark.integration
def test_005930_ohlcv_load_roundtrip(conn, monkeypatch, fake_ohlcv):
    monkeypatch.setattr(KrSource, "ohlcv", lambda self, ct: fake_ohlcv)

    ohlcv = KrSource().ohlcv("005930")   # frozen dataclass
    upsert_price(conn, ohlcv)            # frozen dataclass 인자
    row = latest_price(conn, "005930")   # sqlite3.Row | None

    assert row is not None
    assert row["trade_date"] == "2026-06-01"
    assert row["close_raw"] == 81000.0
    assert row["close_adj"] == 81000.0
    assert row["ccy"] == "KRW"
    assert row["week52_high"] == 88000.0
    assert row["sma200"] == 75000.0


@pytest.mark.integration
def test_005930_funda_load_roundtrip(conn, monkeypatch, fake_funda):
    monkeypatch.setattr(KrSource, "fundamentals", lambda self, ct: fake_funda)

    funda = KrSource().fundamentals("005930")
    upsert_funda(conn, funda)
    row = latest_funda(conn, "005930")

    assert row is not None
    assert row["trade_date"] == "2026-06-01"
    assert row["per"] == 14.2 and row["pbr"] == 1.3 and row["div_yield"] == 2.1
    assert row["per_pctile_5y"] == 42.0 and row["pbr_pctile_5y"] == 38.0
    assert row["report_date"] == "2026-03-31"
