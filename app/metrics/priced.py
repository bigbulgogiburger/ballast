"""build_priced — 통화정규화(base=KRW) + 보류 처리. 04 §9.1 (BAL-19).

핵심 불변식(CLAUDE.md NEVER):
  - fx 결측 시 USD 자산은 '산출 거부'(status 보류, value_base=None) — 분모에서 빼지 않음.
  - fx는 market=='US'에만 곱한다 — KR 자산까지 미정규화되는 전역오염 금지.
  - US collect FAIL(us_ok=False) → stale price여도 data_pending 강제 보류(게이트 일관).
"""
from app import db
from app.models import HoldingRow, PricedHolding


def _held(h: HoldingRow) -> PricedHolding:
    """fx 결측으로 USD 자산 보류. §15.4 'fx_held'."""
    return PricedHolding(h, None, "fx_held")


def build_priced(
    conn, holdings: list[HoldingRow], fx_ok: bool, us_ok: bool
) -> list[PricedHolding]:
    fx_rate = None
    if fx_ok:
        fx_row = db.latest_fx(conn, "USDKRW")
        fx_rate = fx_row["rate"] if fx_row is not None else None
        fx_ok = fx_rate is not None  # row 실종 시 게이트와 일관되게 보류로 강등
    out: list[PricedHolding] = []
    for h in holdings:
        if h.tracking == "manual":  # 현금
            if h.ccy == "USD":
                if not fx_ok:  # G6: USD 현금도 fx 의존
                    out.append(_held(h))
                    continue
                out.append(PricedHolding(h, h.value_manual * fx_rate, "ok"))
                continue
            out.append(PricedHolding(h, h.value_manual, "ok"))  # KRW 현금
            continue
        if h.market == "US" and not us_ok:  # US collect FAIL → 강제 보류
            out.append(PricedHolding(h, None, "data_pending"))
            continue
        price = db.latest_price(conn, h.canonical_ticker)
        if price is None:  # G3: row 0건 → 데이터 준비중 보류
            out.append(PricedHolding(h, None, "data_pending"))
            continue
        if h.market == "US" and not fx_ok:  # fx FAIL → US 평가액 산출 거부 (SSoT §4)
            out.append(_held(h))
            continue
        fx = fx_rate if h.market == "US" else 1.0
        out.append(PricedHolding(h, h.quantity * price["close_raw"] * fx, "ok"))
    return out
