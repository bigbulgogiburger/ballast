"""validate_holdings 단위 테스트 — 03 §2.4 검증 규칙 8종 (BAL-31).

규칙: auto 필수(stock/etf)·manual 필수(cash)·ccy 일관·ticker 형식·
category 값·target 배타(G5)·target 합 100%±0.5·중복 ticker.
정규화(HoldingRow 변환)도 함께 확인.
"""
import pytest

from app.holdings_form import (
    FieldError,
    HoldingForm,
    HoldingsValidation,
    validate_holdings,
)
from app.tickers import CORE_ETF_WHITELIST


def _form(
    *,
    instrument: str = "stock",
    canonical_ticker: str | None = "005930",
    market: str | None = "KR",
    quantity: str | None = "10",
    value_manual: str | None = None,
    ccy: str | None = "KRW",
    avg_price: str | None = None,
    category: str | None = "",
    target_pct: str | None = None,
) -> HoldingForm:
    """HoldingForm 빌더 — 유효한 stock 기본값, 필요한 필드만 override."""
    return HoldingForm(
        instrument=instrument,
        canonical_ticker=canonical_ticker,
        market=market,
        quantity=quantity,
        value_manual=value_manual,
        ccy=ccy,
        avg_price=avg_price,
        category=category,
        target_pct=target_pct,
    )


def _has_error(result: HoldingsValidation, *, row_index: int, field: str | None) -> bool:
    """주어진 (row_index, field) 조합의 FieldError 존재 여부."""
    return any(
        e.row_index == row_index and e.field == field for e in result.errors
    )


@pytest.mark.unit
def test_valid_single_stock_passes_and_normalizes() -> None:
    """기본 유효 stock 1행 → ok=True, HoldingRow 1건 정규화(equity/auto)."""
    result = validate_holdings([_form()])
    assert result.ok is True
    assert result.errors == []
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.asset_class == "equity"
    assert row.tracking == "auto"
    assert row.canonical_ticker == "005930"


@pytest.mark.unit
def test_auto_required_missing_quantity_rejected() -> None:
    """규칙1 auto 필수 — stock 수량 누락 시 행 전역(None) 에러."""
    result = validate_holdings([_form(quantity=None)])
    assert result.ok is False
    assert _has_error(result, row_index=0, field=None)


@pytest.mark.unit
def test_auto_required_nonpositive_quantity_rejected() -> None:
    """규칙1 auto 필수 — 수량<=0 거부."""
    result = validate_holdings([_form(quantity="0")])
    assert result.ok is False
    assert _has_error(result, row_index=0, field=None)


@pytest.mark.unit
def test_manual_required_cash_needs_value() -> None:
    """규칙2 manual 필수 — cash는 value_manual>0 필수."""
    bad = validate_holdings(
        [_form(instrument="cash", canonical_ticker=None, market=None,
               quantity=None, value_manual=None, ccy="USD")]
    )
    assert bad.ok is False
    assert _has_error(bad, row_index=0, field="value_manual")

    good = validate_holdings(
        [_form(instrument="cash", canonical_ticker=None, market=None,
               quantity=None, value_manual="1000", ccy="USD")]
    )
    assert good.ok is True
    assert good.rows[0].asset_class == "cash"
    assert good.rows[0].tracking == "manual"
    assert good.rows[0].ccy == "USD"


@pytest.mark.unit
def test_ccy_consistency_us_market_must_be_usd() -> None:
    """규칙3 ccy 일관 — US 시장 종목 통화가 USD가 아니면 ccy 에러."""
    result = validate_holdings(
        [_form(canonical_ticker="AAPL", market="US", ccy="KRW")]
    )
    assert result.ok is False
    assert _has_error(result, row_index=0, field="ccy")


@pytest.mark.unit
def test_ccy_cash_must_be_usd() -> None:
    """규칙3 ccy 일관 — cash 통화는 USD만 허용."""
    result = validate_holdings(
        [_form(instrument="cash", canonical_ticker=None, market=None,
               quantity=None, value_manual="1000", ccy="KRW")]
    )
    assert result.ok is False
    assert _has_error(result, row_index=0, field="ccy")


@pytest.mark.unit
def test_ticker_format_invalid_rejected() -> None:
    """규칙4 ticker 형식 — 영숫자·'.' 외 문자 거부."""
    result = validate_holdings([_form(canonical_ticker="00 59*30")])
    assert result.ok is False
    assert _has_error(result, row_index=0, field="canonical_ticker")


@pytest.mark.unit
def test_category_value_invalid_rejected() -> None:
    """규칙5 category 값 — ''|core|satellite 외 거부."""
    result = validate_holdings([_form(category="growth")])
    assert result.ok is False
    assert _has_error(result, row_index=0, field="category")


@pytest.mark.unit
def test_target_exclusive_partial_rejected() -> None:
    """규칙6 target 배타(G5) — 일부 행만 target 입력 시 전역 에러."""
    forms = [
        _form(canonical_ticker="005930", target_pct="60"),
        _form(canonical_ticker="000660", target_pct=None),
    ]
    result = validate_holdings(forms)
    assert result.ok is False
    assert _has_error(result, row_index=-1, field=None)


@pytest.mark.unit
def test_target_sum_must_be_100_within_tolerance() -> None:
    """규칙7 target 합 — 전부 수동이면 100%±0.5. 합 99는 거부, 100은 통과."""
    bad = validate_holdings(
        [
            _form(canonical_ticker="005930", target_pct="60"),
            _form(canonical_ticker="000660", target_pct="39"),
        ]
    )
    assert bad.ok is False
    assert _has_error(bad, row_index=-1, field=None)

    good = validate_holdings(
        [
            _form(canonical_ticker="005930", target_pct="60"),
            _form(canonical_ticker="000660", target_pct="40"),
        ]
    )
    assert good.ok is True
    # 전부 수동 → target_pct 영속
    assert {r.target_pct for r in good.rows} == {60.0, 40.0}


@pytest.mark.unit
def test_target_sum_tolerance_boundary_passes() -> None:
    """규칙7 경계 — 합 100.5(허용 오차 끝)는 통과."""
    result = validate_holdings(
        [
            _form(canonical_ticker="005930", target_pct="60"),
            _form(canonical_ticker="000660", target_pct="40.5"),
        ]
    )
    assert result.ok is True


@pytest.mark.unit
def test_duplicate_ticker_rejected() -> None:
    """규칙8 중복 ticker — 동일 종목코드 2회 입력 시 두번째 행에 에러."""
    forms = [
        _form(canonical_ticker="005930"),
        _form(canonical_ticker="005930"),
    ]
    result = validate_holdings(forms)
    assert result.ok is False
    assert _has_error(result, row_index=1, field="canonical_ticker")


@pytest.mark.unit
def test_auto_target_not_persisted_when_all_blank() -> None:
    """target 전부 비움 → 정규화 시 target_pct None 유지(자동 저장 안 함)."""
    result = validate_holdings(
        [
            _form(canonical_ticker="005930", target_pct=None),
            _form(canonical_ticker="000660", target_pct=None),
        ]
    )
    assert result.ok is True
    assert all(r.target_pct is None for r in result.rows)


@pytest.mark.unit
def test_category_autoclassify_etf_whitelist() -> None:
    """category='' 자동판정 — 화이트리스트 ETF는 core, stock은 satellite."""
    whitelist_ticker = next(iter(CORE_ETF_WHITELIST))
    result = validate_holdings(
        [
            _form(instrument="etf", canonical_ticker=whitelist_ticker,
                  market="US", ccy="USD", category=""),
            _form(instrument="stock", canonical_ticker="005930",
                  market="KR", ccy="KRW", category=""),
        ]
    )
    assert result.ok is True
    by_ticker = {r.canonical_ticker: r for r in result.rows}
    assert by_ticker[whitelist_ticker].category == "core"
    assert by_ticker["005930"].category == "satellite"


@pytest.mark.unit
def test_field_error_dataclass_shape() -> None:
    """FieldError 형태 — 회귀 방지(row_index/field/message)."""
    e = FieldError(row_index=3, field="ccy", message="msg")
    assert (e.row_index, e.field, e.message) == (3, "ccy", "msg")
