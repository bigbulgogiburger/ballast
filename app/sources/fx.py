"""FX(USDKRW) 어댑터 (BAL-14). canonical 04 §7.4 + decisions §1.2/§3.1.

FxSource.usdkrw() -> FxRate. 1차 ECB(ECOS 보조) → 2차 yfinance 'KRW=X'.
무효 응답(rate<=0/NaN/None)=그 소스 실패 → 다음 폴백. 전부 실패 → raise(0/NULL 위장 금지).
rate = USD 1단위 = KRW. 외부 호출은 @retry(3). 미설치 라이브러리는 lazy import.
"""
import logging
from datetime import date

import requests

from app import config
from app.models import FxRate
from app.sources import EmptyResponseError, retry

log = logging.getLogger(__name__)

_PAIR = "USDKRW"


def _valid_rate(v) -> float | None:
    if v is None or v != v or v <= 0:
        return None
    return float(v)


class FxSource:
    """FX 어댑터. __init__ 무인자·무부작용."""

    @retry(3)
    def usdkrw(self) -> FxRate:
        for fetch in (self._from_ecb, self._from_ecos, self._from_yf):
            try:
                rate = fetch()
            except Exception as exc:  # noqa: BLE001 — 폴백 유도
                log.warning("fx source %s failed: %s", fetch.__name__, exc)
                rate = None
            if rate is not None:
                return FxRate(trade_date=date.today().isoformat(), pair=_PAIR, rate=rate)
        raise EmptyResponseError("USDKRW: 전 소스 무효 — fx 산출 거부(05 §1.5)")

    def _from_ecb(self) -> float | None:
        """ECB SDW는 EUR 기준 → USDKRW = (KRW/EUR) / (USD/EUR) 합성. 결측 시 None."""
        krw_eur = self._ecb_rate("KRW")
        usd_eur = self._ecb_rate("USD")
        if krw_eur is None or usd_eur is None or usd_eur == 0:
            return None
        return _valid_rate(krw_eur / usd_eur)

    def _ecb_rate(self, ccy: str) -> float | None:
        url = f"https://data-api.ecb.europa.eu/service/data/EXR/D.{ccy}.EUR.SP00.A"
        r = requests.get(url, params={"lastNObservations": 1, "format": "jsondata"}, timeout=10)
        r.raise_for_status()
        obs = r.json()["dataSets"][0]["series"]["0:0:0:0:0"]["observations"]
        return _valid_rate(next(iter(obs.values()))[0])

    def _from_ecos(self) -> float | None:
        """한국은행 ECOS 보조. ECOS_API_KEY 없으면 skip(에러 아님 — 선택 키)."""
        if not config.ECOS_API_KEY:
            return None
        return None  # ECOS 통계코드 매핑은 구현자 보강 — 현재 보조 경로 미사용

    def _from_yf(self) -> float | None:
        """2차 yfinance 'KRW=X' 최신 종가."""
        import yfinance as yf
        h = yf.Ticker("KRW=X").history(period="5d")
        if h.empty:
            return None
        return _valid_rate(float(h["Close"].dropna().iloc[-1]))
