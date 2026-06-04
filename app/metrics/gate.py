"""신선도 게이트 (BAL-22). canonical 04 §10.2 · SSoT §7 · S4 · G6.

수집 사이클 완료 여부(collect_complete_today)와 시장별 데이터 생존 판정(evaluate_gate)을
collect_run 테이블 기준으로 산출한다. BACKFILL/OK_HOLIDAY는 차단 아님 — FAIL만 차단.
fx_ok=False(USD 자산 보류)는 플래그만 세우고 실제 분모 제외는 build_priced(BAL-19) 책임.
"""
from dataclasses import dataclass
from datetime import date
from typing import Literal
import sqlite3

from app import calendar, db

_ALIVE = {"OK", "PARTIAL", "BACKFILL", "OK_HOLIDAY"}


@dataclass(frozen=True)
class GateResult:
    blocked: bool      # KR·US 모두 미갱신 → 생성 거부
    fx_ok: bool        # FX FAIL → False (USD 자산 전체 보류)
    us_ok: bool        # US FAIL → US 종목 제외
    banner: str | None


def collect_complete_today(conn: sqlite3.Connection) -> bool:
    """보유 시장별로 '오늘 기대 거래일' collect_run row가 모두 존재하면 True.

    row 없음(아직 수집 미완) 또는 trade_date 불일치(전날값) → False(브리핑 보류).
    """
    today = date.today()
    for m in db.markets_in_use(conn):
        run = db.latest_collect_run(conn, m)
        market: Literal["KR", "US"] = m  # type: ignore[assignment]
        expected = calendar.expected_trade_date(market, today).isoformat()
        if run is None or run["trade_date"] != expected:
            return False
    return True


def evaluate_gate(conn: sqlite3.Connection) -> GateResult:
    """시장별 최신 collect_run status로 차단/보류 플래그 산출. 04 §10.2."""
    kr = db.latest_collect_run(conn, "KR")
    us = db.latest_collect_run(conn, "US")
    fx = db.latest_collect_run(conn, "FX")

    def alive(r: sqlite3.Row | None) -> bool:
        return r is not None and r["status"] in _ALIVE

    if not (alive(kr) or alive(us)):
        return GateResult(True, False, False, "데이터 미갱신 — 브리핑 보류")
    return GateResult(
        blocked=False,
        fx_ok=alive(fx),
        us_ok=alive(us),
        banner=None if alive(fx) and alive(us) else "일부 시장 데이터 보류",
    )
