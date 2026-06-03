"""BAL-9 app/tickers.py 단위 테스트. 04 §5 변환표 + decisions §3.1~§3.3."""
import pytest

from app.models import HoldingInput
from app.tickers import CORE_ETF_WHITELIST, classify_category, to_source


@pytest.mark.unit
@pytest.mark.parametrize(
    "source,ct,market,expected",
    [
        ("yf", "005930", "KR", "005930.KS"),
        ("finnhub", "005930", "KR", "005930.KS"),
        ("stooq", "005930", "KR", "005930.KS"),
        ("pykrx", "005930", "KR", "005930"),
        ("yf", "VOO", "US", "VOO"),
        ("finnhub", "VOO", "US", "VOO"),
        ("stooq", "VOO", "US", "voo.us"),
        ("yf", "BRK.B", "US", "BRK-B"),
        ("finnhub", "BRK.B", "US", "BRK-B"),
        ("stooq", "BRK.B", "US", "brk-b.us"),
    ],
)
def test_to_source_table(source, ct, market, expected):
    assert to_source(source, ct, market) == expected


@pytest.mark.unit
def test_to_source_fdr_fmp_dart():
    assert to_source("fdr", "005930", "KR") == "005930"   # KR bare
    assert to_source("dart", "005930", "KR") == "005930"
    assert to_source("fmp", "BRK.B", "US") == "BRK-B"      # decisions §3.2 정규화


@pytest.mark.unit
def test_to_source_unknown_market_raises():
    with pytest.raises(ValueError):
        to_source("yf", "005930", "JP")


@pytest.mark.unit
def test_to_source_impossible_combo_raises():
    with pytest.raises(ValueError):
        to_source("pykrx", "VOO", "US")   # pykrx는 KR 전용
    with pytest.raises(ValueError):
        to_source("fmp", "005930", "KR")  # fmp는 US 전용


@pytest.mark.unit
def test_classify_user_override():
    h = HoldingInput(instrument="stock", name="t", category="core")
    assert classify_category(h) == "core"


@pytest.mark.unit
def test_classify_stock_satellite():
    h = HoldingInput(instrument="stock", name="삼성전자")
    assert classify_category(h) == "satellite"


@pytest.mark.unit
def test_classify_etf_whitelist_core():
    h = HoldingInput(instrument="etf", name="VOO", canonical_ticker="VOO")
    assert classify_category(h) == "core"
    assert "VOO" in CORE_ETF_WHITELIST


@pytest.mark.unit
def test_classify_etf_non_whitelist_none():
    h = HoldingInput(instrument="etf", name="ARKK", canonical_ticker="ARKK")
    assert classify_category(h) is None


@pytest.mark.unit
def test_classify_cash_none():
    h = HoldingInput(instrument="cash", name="USD예금")
    assert classify_category(h) is None
