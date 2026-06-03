"""US 시세·재무·뉴스 어댑터 (BAL-13). canonical 04 §7.3 + decisions §1.1/§3.3.

UsSource = PriceSource + NewsSource. 무료 소스 폴백 체인으로 30종목 US 인입 증명.
- ohlcv(BAL-49): Stooq 1차 → yfinance 2차 → Finnhub /quote 보조(당일가). 빈/무효=다음 소스.
- fundamentals(BAL-50): FMP 무료 5년 → per/pbr/div + percentile, report_date=SEC EDGAR period.
- headlines(BAL-50): Finnhub 뉴스, 빈응답=[].
외부 호출은 @retry(3). 키 부재=KeyError(fail-fast). 미설치 라이브러리(pandas_datareader 등)는
메서드 내부 lazy import — 테스트는 _fetch_* 경계 모킹. KrSource 미러(무인자 lazy __init__).
"""
import logging
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

import requests

from app import config
from app.calendar import expected_trade_date
from app.models import Funda, Headline, OHLCV
from app.sources import retry, validate_response
from app.tickers import to_source

log = logging.getLogger(__name__)

_FETCH_WINDOW_DAYS = 420
_WEEK52_SESSIONS = 252
_SMA_SESSIONS = 200
_MIN_PCTILE_SAMPLE = 20
_FMP_RATIOS_URL = "https://financialmodelingprep.com/api/v3/ratios/{sym}"
_FINNHUB_NEWS_URL = "https://finnhub.io/api/v1/company-news"
_FINNHUB_QUOTE_URL = "https://finnhub.io/api/v1/quote"


def _pos_or_none(v) -> float | None:
    if v is None or v != v or v <= 0:  # None / NaN / 비양수
        return None
    return float(v)


def _pctile(values: list, current: float | None, *, exclude_nonpos: bool) -> float | None:
    """5년 분포 대비 현재값 백분위. 유효표본<20 → None (kr.py 미러)."""
    if current is None:
        return None
    dist = [x for x in values if x is not None and x == x]
    if exclude_nonpos:
        dist = [x for x in dist if x > 0]
    if len(dist) < _MIN_PCTILE_SAMPLE:
        return None
    return float(sum(1 for x in dist if x <= current) / len(dist) * 100)


class UsSource:
    """US 어댑터. __init__ 무인자·무부작용(decisions Q10)."""

    @retry(3)
    def ohlcv(self, ct: str) -> OHLCV:
        today = date.today()
        expected = expected_trade_date("US", today)
        start = today - timedelta(days=_FETCH_WINDOW_DAYS)

        df = self._ohlcv_stooq(ct, start, today)
        if df is None or df.empty:
            df = self._ohlcv_yf(ct, start, today)
        if df is None or df.empty:
            return self._ohlcv_finnhub_quote(ct, expected)  # 보조: 당일가만

        adj = df["close_adj"]
        n = len(adj)
        trade_date = df.index[-1].strftime("%Y-%m-%d")
        validate_response(rows=n, latest=trade_date, expected=expected.isoformat())
        sma200 = float(adj.tail(_SMA_SESSIONS).mean()) if n >= _SMA_SESSIONS else None
        w52 = adj.tail(_WEEK52_SESSIONS)
        return OHLCV(
            canonical_ticker=ct, trade_date=trade_date,
            close_raw=float(df["close_raw"].iloc[-1]), close_adj=float(adj.iloc[-1]), ccy="USD",
            week52_high=float(w52.max()) if n >= _WEEK52_SESSIONS else None,
            week52_low=float(w52.min()) if n >= _WEEK52_SESSIONS else None,
            sma200=sma200,
        )

    def _ohlcv_stooq(self, ct: str, start: date, end: date):
        """1차 Stooq. 단일 Close → raw=adj. 미설치/실패 시 None(폴백 유도)."""
        try:
            import pandas_datareader.data as web
            s = web.DataReader(to_source("stooq", ct, "US"), "stooq", start, end)
        except Exception as exc:  # noqa: BLE001
            log.warning("stooq fetch failed for %s: %s", ct, exc)
            return None
        if s.empty:
            return None
        s = s.sort_index().rename(columns={"Close": "close_raw"})
        s["close_adj"] = s["close_raw"]  # stooq 단일 종가 (decisions §1.1 Q2)
        return s[["close_raw", "close_adj"]]

    def _ohlcv_yf(self, ct: str, start: date, end: date):
        """2차 yfinance. Close=raw, Adj Close=adj 분리."""
        try:
            import yfinance as yf
            h = yf.Ticker(to_source("yf", ct, "US")).history(
                start=start, end=end, auto_adjust=False
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("yfinance fetch failed for %s: %s", ct, exc)
            return None
        if h.empty:
            return None
        h = h.sort_index().rename(columns={"Close": "close_raw", "Adj Close": "close_adj"})
        if "close_adj" not in h:
            h["close_adj"] = h["close_raw"]
        return h[["close_raw", "close_adj"]]

    def _ohlcv_finnhub_quote(self, ct: str, expected: date) -> OHLCV:
        """보조: Finnhub /quote 당일가만(week52/sma200=None). 전 소스 빈 시 마지막 수단."""
        key = config.FINNHUB_API_KEY
        if not key:
            raise KeyError("FINNHUB_API_KEY 미설정")
        q = requests.get(
            _FINNHUB_QUOTE_URL,
            params={"symbol": to_source("finnhub", ct, "US")},
            headers={"X-Finnhub-Token": key},  # 키는 헤더로(URL 노출 차단, S-1)
            timeout=10,
        )
        q.raise_for_status()
        data = q.json()
        price = data.get("c")
        ts = data.get("t")
        validate_response(rows=1 if price else 0, latest="quote", expected=expected.isoformat())
        td = (
            datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
            if ts else expected.isoformat()
        )
        return OHLCV(
            canonical_ticker=ct, trade_date=td, close_raw=float(price), close_adj=float(price),
            ccy="USD", week52_high=None, week52_low=None, sma200=None,
        )

    @retry(3)
    def fundamentals(self, ct: str) -> Funda:
        key = config.FMP_API_KEY
        if not key:
            raise KeyError("FMP_API_KEY 미설정")
        rows = self._fmp_ratios(ct, key)  # 최신순 list[dict]
        validate_response(rows=len(rows), latest="fmp", expected="fmp")
        latest = rows[0]
        per = _pos_or_none(latest.get("priceEarningsRatio"))
        pbr = _pos_or_none(latest.get("priceToBookRatio"))
        div_yield = _pos_or_none(latest.get("dividendYield"))
        return Funda(
            canonical_ticker=ct, trade_date=str(latest.get("date", "")),
            per=per, pbr=pbr, div_yield=div_yield,
            per_pctile_5y=_pctile([r.get("priceEarningsRatio") for r in rows], per, exclude_nonpos=True),
            pbr_pctile_5y=_pctile([r.get("priceToBookRatio") for r in rows], pbr, exclude_nonpos=False),
            report_date=self._edgar_report_date(ct),  # 실패/미설정 시 None (degrade)
        )

    def _fmp_ratios(self, ct: str, key: str) -> list:
        # sym을 URL path에 넣기 전 인코딩 — path traversal 차단(S-2). FMP는 apikey 헤더 미지원→query.
        sym = quote(to_source("fmp", ct, "US"), safe="")
        r = requests.get(
            _FMP_RATIOS_URL.format(sym=sym),
            params={"period": "annual", "limit": 5, "apikey": key}, timeout=10,
        )
        # raise_for_status()는 예외 메시지에 apikey 포함 URL을 노출(S-1) → status만 담아 재포장.
        if r.status_code != 200:
            raise RuntimeError(f"FMP HTTP {r.status_code} for {ct}")
        data = r.json()
        return data if isinstance(data, list) else []

    def _edgar_report_date(self, ct: str) -> str | None:
        """SEC EDGAR period-of-report(재무 실제 기준일, decisions Q4). PoC=미확보 None degrade."""
        if not config.SEC_USER_AGENT:
            return None
        return None  # CIK 매핑/제출 조회는 구현자 보강 — 현재 degrade(None)

    @retry(3)
    def headlines(self, ct: str, name: str) -> list[Headline]:
        """Finnhub 뉴스. 빈응답=[](validate_response 미적용, decisions Q9)."""
        key = config.FINNHUB_API_KEY
        if not key:
            raise KeyError("FINNHUB_API_KEY 미설정")
        today = date.today()
        r = requests.get(
            _FINNHUB_NEWS_URL,
            params={
                "symbol": to_source("finnhub", ct, "US"),
                "from": (today - timedelta(days=7)).isoformat(),
                "to": today.isoformat(),
            },
            headers={"X-Finnhub-Token": key},  # 키는 헤더로(S-1)
            timeout=10,
        )
        r.raise_for_status()
        items = r.json() if isinstance(r.json(), list) else []
        return [
            Headline(title=it.get("headline", ""), url=it.get("url", ""), source="finnhub")
            for it in items if it.get("headline")
        ]
