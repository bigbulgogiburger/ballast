"""시장 거래일 캘린더 (BAL-10). canonical 04 §6.1 + decisions §1.3.

pandas_market_calendars 기본 휴장표(XKRX/XNYS)를 100% 신뢰한다(W1=임시공휴일 보정 안 함).
KOSPI/KOSDAQ은 동일 XKRX 캘린더를 공유하므로 market은 'KR'/'US'만 구분한다.
valid_days는 자정 UTC 라벨 → .date()가 거래소 현지 거래일과 일치(tz 변환 안 함).
"""
from datetime import date, timedelta
from typing import Literal

import pandas_market_calendars as mcal

_KR = mcal.get_calendar("XKRX")   # 한국거래소
_US = mcal.get_calendar("XNYS")   # NYSE


def _cal(market: Literal["KR", "US"]):
    return _KR if market == "KR" else _US


def is_trading_day(market: Literal["KR", "US"], d: date) -> bool:
    """d가 해당 시장의 거래일이면 True. 04 §6.1."""
    sessions = _cal(market).valid_days(start_date=d, end_date=d)
    return len(sessions) > 0


def prev_trading_day(market: Literal["KR", "US"], d: date) -> date:
    """d 직전 거래일. 14일 고정 윈도우(decisions: 0거래일이면 자연 IndexError)."""
    sessions = _cal(market).valid_days(
        start_date=d - timedelta(days=14), end_date=d - timedelta(days=1)
    )
    return sessions[-1].date()


def expected_trade_date(market: Literal["KR", "US"], today: date) -> date:
    """collect 기준 거래일. KR=오늘(휴장이면 직전), US=항상 직전(전일 마감분). decisions #9."""
    if market == "KR":
        return today if is_trading_day("KR", today) else prev_trading_day("KR", today)
    return prev_trading_day("US", today)
