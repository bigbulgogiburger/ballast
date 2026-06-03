"""시장 레짐 어댑터 (BAL-48 일부). canonical 04 §7.5 + decisions #10.

W1 = KR 절반만: kospi_pbr = pykrx 코스피 지수 PBR(코드 '1001'), us_cape = None(W2).
as_of = 당월 1일('YYYY-MM-01', upsert 매핑 as_of→trade_date).
"""
from datetime import date, timedelta

from pykrx import stock

from app.models import RegimeRow
from app.sources import retry

_KOSPI_INDEX = "1001"


class RegimeProvider:
    """RegimeSource Protocol. 실패 시 raise(collect가 W2에서 degrade)."""

    @retry(3)
    def regime(self) -> RegimeRow:
        today = date.today()
        fromdate = (today - timedelta(days=30)).strftime("%Y%m%d")
        df = stock.get_index_fundamental(fromdate, today.strftime("%Y%m%d"), _KOSPI_INDEX)
        kospi_pbr = float(df["PBR"].iloc[-1])
        return RegimeRow(
            as_of=today.replace(day=1).isoformat(),
            kospi_pbr=kospi_pbr,
            us_cape=None,
        )
