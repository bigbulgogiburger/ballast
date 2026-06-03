"""시장 레짐 어댑터. canonical 04 §7.5 + decisions #10(W1) / BAL-15 §1.3(W2).

kospi_pbr = pykrx 코스피 지수 PBR(코드 '1001', W1). us_cape = Shiller CAPE(W2-BAL-15):
Yale ie_data.xls 1차 → multpl 스크레이프 2차. 한쪽만 실패 → 그 필드만 NULL.
as_of = 당월 1일('YYYY-MM-01', upsert 매핑 as_of→trade_date).
"""
import logging
from datetime import date, timedelta

import requests
from pykrx import stock

from app.models import RegimeRow
from app.sources import retry

log = logging.getLogger(__name__)

_KOSPI_INDEX = "1001"
_YALE_CAPE_URL = "http://www.econ.yale.edu/~shiller/data/ie_data.xls"
_MULTPL_CAPE_URL = "https://www.multpl.com/shiller-pe"


class RegimeProvider:
    """RegimeSource Protocol. kospi_pbr 실패 시 raise(degrade), us_cape 실패는 NULL."""

    @retry(3)
    def regime(self) -> RegimeRow:
        today = date.today()
        fromdate = (today - timedelta(days=30)).strftime("%Y%m%d")
        df = stock.get_index_fundamental(fromdate, today.strftime("%Y%m%d"), _KOSPI_INDEX)
        kospi_pbr = float(df["PBR"].iloc[-1])
        try:
            us_cape = _fetch_us_cape()  # BAL-15: us_cape만 실패해도 메서드 성공(NULL)
        except Exception as exc:  # noqa: BLE001 — 한쪽 실패 격리(decisions §1.3 Q3)
            log.warning("us_cape fetch failed → NULL: %s", exc)
            us_cape = None
        return RegimeRow(
            as_of=today.replace(day=1).isoformat(),
            kospi_pbr=kospi_pbr,
            us_cape=us_cape,
        )


def _fetch_us_cape() -> float:
    """Shiller CAPE: Yale ie_data.xls(1차) → multpl(2차). 둘 다 실패 시 raise(decisions §3.2)."""
    try:
        return _cape_from_yale()
    except Exception as exc:  # noqa: BLE001 — 2차 폴백 유도
        log.warning("yale CAPE failed, fallback multpl: %s", exc)
        return _cape_from_multpl()


def _cape_from_yale() -> float:
    """Yale ie_data.xls 'Data' 시트 최신 비결측 CAPE. (xls 엔진 미설치 시 lazy-import 실패→폴백)."""
    import pandas as pd
    df = pd.read_excel(_YALE_CAPE_URL, sheet_name="Data", skiprows=7)
    cape_col = [c for c in df.columns if "CAPE" in str(c).upper()][0]
    series = df[cape_col].dropna()
    if series.empty:
        raise ValueError("yale CAPE 전부 결측")
    return float(series.iloc[-1])


def _cape_from_multpl() -> float:
    """multpl Shiller PE 현재값 스크레이프."""
    from bs4 import BeautifulSoup
    r = requests.get(_MULTPL_CAPE_URL, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    el = soup.find(id="current")
    text = (el.get_text() if el else "").replace("\n", " ")
    import re
    m = re.search(r"(\d+\.\d+)", text)
    if not m:
        raise ValueError("multpl CAPE 파싱 실패")
    return float(m.group(1))
