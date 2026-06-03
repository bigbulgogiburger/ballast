"""KR 시세·재무·뉴스 어댑터 (BAL-11). canonical 04 §4.3/§7.2 + decisions §1.4.

KrSource = PriceSource + NewsSource Protocol 구현. 005930 무료데이터 인입 증명이 목표.
- ohlcv(BAL-46): pykrx adjusted=True/False 2회 → close_adj/raw 분리, 소진 시 FDR 폴백.
- fundamentals(BAL-47): pykrx 5년 월말 PER/PBR/DIV + 어댑터 percentile 계산.
- headlines(BAL-48): 네이버 검색 API, 빈응답=[] (validate_response 미적용).
모든 외부 호출은 @retry(3). report_date=None(W1), KOSDAQ=W2(005930=KOSPI).
"""
import html
import logging
import re
from datetime import date, timedelta

import requests
from pykrx import stock

from app import config
from app.calendar import expected_trade_date
from app.models import Funda, Headline, OHLCV
from app.sources import EmptyResponseError, retry, validate_response
from app.tickers import to_source

log = logging.getLogger(__name__)

_FETCH_WINDOW_DAYS = 420   # 주말·공휴일 손실 가정 시 ≈290거래일 > 252·200 동시 커버 (decisions #4)
_WEEK52_SESSIONS = 252
_SMA_SESSIONS = 200
_MIN_PCTILE_SAMPLE = 20
_NAVER_NEWS_URL = "https://openapi.naver.com/v1/search/news.json"


def _fmt(d: date) -> str:
    return d.strftime("%Y%m%d")


class KrSource:
    """KR 어댑터. __init__ 무인자·무부작용(lazy) — 네트워크/키 접근은 메서드 첫 호출 시(decisions Q10)."""

    @retry(3)
    def ohlcv(self, ct: str) -> OHLCV:
        today = date.today()
        expected = expected_trade_date("KR", today)
        src = to_source("pykrx", ct, "KR")  # KR=6자리 그대로
        fromdate, todate = _fmt(today - timedelta(days=_FETCH_WINDOW_DAYS)), _fmt(today)

        df_adj = stock.get_market_ohlcv(fromdate, todate, src, adjusted=True)
        if df_adj.empty:
            return self._ohlcv_fdr(ct, expected)  # pykrx 빈응답 → FDR 폴백 (decisions #3)
        df_raw = stock.get_market_ohlcv(fromdate, todate, src, adjusted=False)

        adj_close = df_adj["종가"]
        n = len(adj_close)
        trade_date = df_adj.index[-1].strftime("%Y-%m-%d")
        validate_response(rows=n, latest=trade_date, expected=expected.isoformat())

        sma200 = float(adj_close.tail(_SMA_SESSIONS).mean()) if n >= _SMA_SESSIONS else None
        if sma200 is None:
            log.warning("sma200 window<200 (%s sessions) for %s → None", n, ct)
        w52 = adj_close.tail(_WEEK52_SESSIONS)
        return OHLCV(
            canonical_ticker=ct,
            trade_date=trade_date,
            close_raw=float(df_raw["종가"].iloc[-1]),
            close_adj=float(adj_close.iloc[-1]),
            ccy="KRW",
            week52_high=float(w52.max()),
            week52_low=float(w52.min()),
            sma200=sma200,
        )

    def _ohlcv_fdr(self, ct: str, expected: date) -> OHLCV:
        """FDR 폴백: 단일 Close 컬럼이라 close_raw=close_adj(동일값) + warning."""
        import FinanceDataReader as fdr

        today = date.today()
        df = fdr.DataReader(to_source("fdr", ct, "KR"), today - timedelta(days=_FETCH_WINDOW_DAYS), today)
        trade_date = df.index[-1].strftime("%Y-%m-%d") if not df.empty else ""
        validate_response(rows=len(df), latest=trade_date, expected=expected.isoformat())
        log.warning("fdr_fallback_adj_eq_raw for %s (FDR Close 단일 컬럼)", ct)
        close = df["Close"]
        n = len(close)
        sma200 = float(close.tail(_SMA_SESSIONS).mean()) if n >= _SMA_SESSIONS else None
        w52 = close.tail(_WEEK52_SESSIONS)
        return OHLCV(
            canonical_ticker=ct, trade_date=trade_date,
            close_raw=float(close.iloc[-1]), close_adj=float(close.iloc[-1]), ccy="KRW",
            week52_high=float(w52.max()), week52_low=float(w52.min()), sma200=sma200,
        )

    @retry(3)
    def fundamentals(self, ct: str) -> Funda:
        today = date.today()
        src = to_source("pykrx", ct, "KR")
        fromdate = _fmt(today - timedelta(days=5 * 365))
        df = stock.get_market_fundamental(fromdate, _fmt(today), src, freq="m")
        trade_date = df.index[-1].strftime("%Y-%m-%d") if not df.empty else ""
        validate_response(rows=len(df), latest=trade_date, expected=trade_date)

        latest = df.iloc[-1]
        per = self._pos_or_none(latest["PER"])
        pbr = self._pos_or_none(latest["PBR"])
        div_yield = self._pos_or_none(latest["DIV"])  # 제공자 값 그대로(%), 재계산 금지
        return Funda(
            canonical_ticker=ct,
            trade_date=trade_date,
            per=per,
            pbr=pbr,
            div_yield=div_yield,
            per_pctile_5y=self._pctile(df["PER"], per, exclude_nonpos=True),
            pbr_pctile_5y=self._pctile(df["PBR"], pbr, exclude_nonpos=False),
            report_date=None,  # pykrx 시세 기준일은 재무 기준일 아님 → W1 None (decisions #9)
        )

    @staticmethod
    def _pos_or_none(v: float) -> float | None:
        """음수/0/NaN → None(적자·데이터부재). pandas NaN은 v != v."""
        if v is None or v != v or v <= 0:
            return None
        return float(v)

    @staticmethod
    def _pctile(series, current: float | None, *, exclude_nonpos: bool) -> float | None:
        """5년 분포 대비 현재값 백분위. 유효표본<20 → None (decisions #5)."""
        if current is None:
            return None
        dist = series.dropna()
        if exclude_nonpos:
            dist = dist[dist > 0]
        if len(dist) < _MIN_PCTILE_SAMPLE:
            return None
        return float((dist <= current).mean() * 100)

    @retry(3)
    def headlines(self, ct: str, name: str) -> list[Headline]:
        """네이버 검색 API. 빈응답=[](정상), validate_response 미적용 (decisions #11)."""
        cid = config.NAVER_CLIENT_ID
        secret = config.NAVER_CLIENT_SECRET
        if not cid or not secret:
            raise KeyError("NAVER_CLIENT_ID/SECRET 미설정")  # 조용한 fallback 금지 (04 §2)
        resp = requests.get(
            _NAVER_NEWS_URL,
            headers={"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": secret},
            params={"query": name, "display": 10, "sort": "date"},
            timeout=10,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        return [
            Headline(
                title=self._strip_html(it.get("title", "")),
                url=it.get("originallink") or it.get("link", ""),
                source="naver",
            )
            for it in items
        ]

    @staticmethod
    def _strip_html(s: str) -> str:
        return html.unescape(re.sub(r"<[^>]+>", "", s))
