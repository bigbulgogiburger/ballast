"""BAL-10 app/calendar.py 테스트. 04 §6.1 + decisions §1.3 (모킹 8 + 실 mcal 통합 1)."""
from datetime import date

import pandas as pd
import pytest

from app import calendar as cal


def _sessions(*dates):
    """fake valid_days 반환값(tz-aware UTC DatetimeIndex)."""
    return pd.DatetimeIndex([pd.Timestamp(d, tz="UTC") for d in dates])


# ── 모킹 단위 테스트 (monkeypatch valid_days) ──────────────────────────────

@pytest.mark.unit
def test_is_trading_day_true(monkeypatch):
    monkeypatch.setattr(cal._KR, "valid_days", lambda start_date, end_date: _sessions("2024-01-02"))
    assert cal.is_trading_day("KR", date(2024, 1, 2)) is True


@pytest.mark.unit
def test_is_trading_day_false(monkeypatch):
    monkeypatch.setattr(cal._KR, "valid_days", lambda start_date, end_date: _sessions())
    assert cal.is_trading_day("KR", date(2024, 1, 1)) is False


@pytest.mark.unit
def test_is_trading_day_us_weekday(monkeypatch):
    monkeypatch.setattr(cal._US, "valid_days", lambda start_date, end_date: _sessions("2024-03-15"))
    assert cal.is_trading_day("US", date(2024, 3, 15)) is True


@pytest.mark.unit
def test_prev_trading_day_returns_last(monkeypatch):
    monkeypatch.setattr(
        cal._US, "valid_days",
        lambda start_date, end_date: _sessions("2023-12-28", "2023-12-29"),
    )
    assert cal.prev_trading_day("US", date(2024, 1, 2)) == date(2023, 12, 29)


@pytest.mark.unit
def test_prev_trading_day_empty_window_raises(monkeypatch):
    monkeypatch.setattr(cal._KR, "valid_days", lambda start_date, end_date: _sessions())
    with pytest.raises(IndexError):
        cal.prev_trading_day("KR", date(2024, 1, 1))


@pytest.mark.unit
def test_expected_kr_today_when_trading(monkeypatch):
    monkeypatch.setattr(cal._KR, "valid_days", lambda start_date, end_date: _sessions("2024-01-02"))
    assert cal.expected_trade_date("KR", date(2024, 1, 2)) == date(2024, 1, 2)


@pytest.mark.unit
def test_expected_kr_prev_when_holiday(monkeypatch):
    calls = {"n": 0}

    def fake(start_date, end_date):
        calls["n"] += 1
        # 1st call = is_trading_day(today) → 휴장(빈), 2nd = prev window
        return _sessions() if calls["n"] == 1 else _sessions("2023-12-29")

    monkeypatch.setattr(cal._KR, "valid_days", fake)
    assert cal.expected_trade_date("KR", date(2024, 1, 1)) == date(2023, 12, 29)


@pytest.mark.unit
def test_expected_us_always_prev(monkeypatch):
    monkeypatch.setattr(
        cal._US, "valid_days", lambda start_date, end_date: _sessions("2023-12-29"),
    )
    # today가 거래일이어도 US는 직전 거래일
    assert cal.expected_trade_date("US", date(2024, 1, 2)) == date(2023, 12, 29)


@pytest.mark.unit
def test_valid_days_label_uses_date_not_tz_shift(monkeypatch):
    monkeypatch.setattr(cal._KR, "valid_days", lambda start_date, end_date: _sessions("2024-03-15"))
    # UTC 자정 라벨 → .date() 그대로 (tz 변환 없음)
    assert cal.prev_trading_day("KR", date(2024, 3, 18)) == date(2024, 3, 15)


# ── 실 mcal 통합 테스트 (decisions §1.3 row 5) ─────────────────────────────

@pytest.mark.integration
def test_real_calendar_expected_trade_date():
    assert cal.expected_trade_date("KR", date(2024, 1, 2)) == date(2024, 1, 2)
    assert cal.expected_trade_date("US", date(2024, 1, 2)) == date(2023, 12, 29)
    # KR 신정(2024-01-01)은 휴장 → 직전 거래일(2023-12-28; 12-29는 연말 휴장)
    assert cal.expected_trade_date("KR", date(2024, 1, 1)) != date(2024, 1, 1)
    assert not cal.is_trading_day("KR", date(2024, 1, 1))
