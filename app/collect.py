"""일배치 수집 통합자 (BAL-17). canonical 04 §8 + decisions §1.5/§3.4.

run_collect: auto 보유종목 → KR/US 시세·펀더·뉴스 + FX + 레짐 수집 → db 적재 + collect_run 게이트 기록.
- 종목 단위 try/except 격리(배치 비중단, 04:557/AC5).
- 날짜검사는 _collect_market 인라인(가드 본체 불변, decisions §3.4).
- _status_of 4분기 + OK_HOLIDAY 선분기(decisions §1.5 Q4). 외부 API rps는 TokenBucket.
하위: BAL-51(_collect_* + TokenBucket), BAL-52(_status_of + collect_run), BAL-53(백필).
"""
import json
import logging
import time
from datetime import date

from app import calendar, config, db
from app.sources import validate_response
from app.sources.fx import FxSource
from app.sources.kr import KrSource
from app.sources.regime import RegimeProvider
from app.sources.us import UsSource

log = logging.getLogger(__name__)

# 어댑터 인스턴스(무인자·lazy __init__ — decisions Q10). 테스트는 클래스 메서드 monkeypatch.
_KR = KrSource()
_US = UsSource()
_FX = FxSource()
_REGIME = RegimeProvider()

_RPS = {"KR": config.NAVER_RPS, "US": config.FMP_RPS}


class TokenBucket:
    """rps 페이싱(04 §8.6). 직전 호출과 최소 간격 1/rps 보장(monotonic). 과설계 금지."""

    def __init__(self, rps: float) -> None:
        self._min_interval = 1.0 / rps if rps > 0 else 0.0
        self._last = 0.0

    def acquire(self) -> None:
        wait = self._min_interval - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()


def run_collect(mode: str = "daily") -> None:
    """일배치 진입점. 04:517-524. KR/US 시세·펀더·뉴스 + FX + 레짐. 각 축 독립 격리."""
    today = date.today()
    conn = db.connect()
    try:
        holdings = db.auto_holdings(conn, 1)
        for market in ("KR", "US"):
            _collect_market(market, holdings, today, mode, conn)
        _collect_fx(today, mode, conn)
        _collect_regime(today, conn)
    finally:
        conn.close()


def _source_for(market: str):
    return _KR if market == "KR" else _US


def _collect_market(market: str, holdings: list, today: date, mode: str, conn) -> None:
    """시장별 수집 + collect_run 게이트 기록. 04 §8.2. 종목 단위 격리."""
    td = today.isoformat()
    if not calendar.is_trading_day(market, today):
        db.upsert_collect_run(conn, td, market, "OK_HOLIDAY", 0, 0, "[]")  # 정상 skip(04:542)
        return
    src = _source_for(market)
    expected = calendar.expected_trade_date(market, today).isoformat()
    bucket = TokenBucket(_RPS[market])
    n_ok = n_fail = 0
    missing: list[str] = []
    for h in [x for x in holdings if x["market"] == market]:
        ct = h["canonical_ticker"]
        try:
            bucket.acquire()
            ohlcv = src.ohlcv(ct)
            validate_response(rows=1, latest=ohlcv.trade_date, expected=expected)
            if ohlcv.trade_date != expected:  # 인라인 stale 검사(decisions §3.4)
                raise ValueError(f"stale {ct}: {ohlcv.trade_date} != {expected}")
            db.upsert_price(conn, ohlcv)
            db.upsert_funda(conn, src.fundamentals(ct))
            db.upsert_news(conn, src.headlines(ct, h["name"]), ct, ohlcv.trade_date)
            n_ok += 1
        except Exception as exc:  # noqa: BLE001 — 종목 격리(04:557)
            n_fail += 1
            missing.append(ct)
            log.warning("collect fail %s/%s: %s", market, ct, exc)
    status = _status_of(n_ok, n_fail, mode)
    db.upsert_collect_run(conn, td, market, status, n_ok, n_fail, json.dumps(missing))


def _collect_fx(today: date, mode: str, conn) -> None:
    """FX 수집. 실패 → collect_run(FX,FAIL) → USD 자산 보류(04:489, 05:162)."""
    td = today.isoformat()
    try:
        db.upsert_fx(conn, _FX.usdkrw())
        db.upsert_collect_run(conn, td, "FX", "OK", 1, 0, "[]")
    except Exception as exc:  # noqa: BLE001
        db.upsert_collect_run(conn, td, "FX", "FAIL", 0, 1, "[]")
        log.warning("fx collect fail: %s", exc)


def _collect_regime(today: date, conn) -> None:
    """레짐 수집. 이번 달 row 있으면 skip(04:528, U5). 실패=degrade(NULL 유지)."""
    as_of = today.replace(day=1).isoformat()
    exists = conn.execute(
        "SELECT 1 FROM market_regime WHERE trade_date = ?", (as_of,)
    ).fetchone()
    if exists:
        return
    try:
        db.upsert_market_regime(conn, _REGIME.regime())
    except Exception as exc:  # noqa: BLE001 — degrade(collect_run 미기록, 레짐은 게이트 비차단)
        log.warning("regime collect fail (degrade): %s", exc)


def _status_of(n_ok: int, n_fail: int, mode: str) -> str:
    """collect_run status 판정(순수함수). 04 §8.4. OK_HOLIDAY는 _collect_market 선분기."""
    if mode == "backfill":
        return "BACKFILL"
    if n_ok == 0:
        return "FAIL"
    if n_fail > 0:
        return "PARTIAL"
    return "OK"
