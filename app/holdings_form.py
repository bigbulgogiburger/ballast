"""보유자산 입력 폼 DTO·파싱·검증 — W5 M4 슬라이스(BAL-31).

03 §2.3(폼 DTO)·§2.4(검증 규칙)·e2e G4/G5/G6 정본.
폼 DTO는 dev-guide §2 결정에 따라 models.py가 아닌 본 모듈에 co-locate
(BAL-31 단일 소유 유지). 필드명·시맨틱은 03 §2.3 그대로.

검증은 서버가 SoT(F5): 실패 시 FieldError 리스트로 상태보존 재렌더(400).
통과 행은 HoldingRow로 정규화(asset_class/tracking 서버 자동,
category='' → CORE_ETF_WHITELIST 자동판정, 자동 target_pct는 None 유지).
"""
from dataclasses import dataclass

from starlette.requests import Request

from app.models import HoldingRow
from app.tickers import CORE_ETF_WHITELIST

# 목표비중 합 허용 오차(03 §2.4 "100%±0.5").
_TARGET_SUM_TOLERANCE: float = 0.5


@dataclass(frozen=True)
class HoldingForm:
    """POST /holdings 원본 입력(검증 전). 모든 값 str|None — 서버에서 타입 변환. 03 §2.3."""

    instrument: str            # 'stock'|'etf'|'cash'
    canonical_ticker: str | None
    market: str | None         # 'KR'|'US'
    quantity: str | None
    value_manual: str | None
    ccy: str | None
    avg_price: str | None
    category: str | None       # ''|'core'|'satellite'  ('' = 자동판정)
    target_pct: str | None


@dataclass(frozen=True)
class FieldError:
    """검증 실패 1건. 03 §2.3."""

    row_index: int             # -1 = 폼 전역 에러(합계 등)
    field: str | None          # None = 행 전역
    message: str               # 사용자 노출 한국어


@dataclass(frozen=True)
class HoldingsValidation:
    """validate_holdings 결과. 03 §2.3."""

    ok: bool
    rows: list[HoldingRow]              # 검증 통과 시 정규화된 행
    errors: list[FieldError]            # 실패 시 (ok=False)


def _clean(value: str | None) -> str | None:
    """폼 문자열 정리: 공백 trim, 빈 문자열은 None으로 정규화."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


async def parse_holdings_form(request: Request) -> list[HoldingForm]:
    """async form → HoldingForm 리스트. name=rows[{i}][field] 파싱(03 §2.1).

    instrument가 빈 행은 신규/미입력으로 보고 건너뛴다(고정 N행 + 빈 행 = 신규).
    """
    data = await request.form()
    rows: dict[int, dict[str, str | None]] = {}
    for key in data.keys():
        if not key.startswith("rows[") or "][" not in key:
            continue
        # rows[{i}][{field}]
        idx_str, _, rest = key[len("rows[") :].partition("]")
        if not idx_str.isdigit():
            continue
        field = rest.lstrip("[").rstrip("]")
        value = data.get(key)
        rows.setdefault(int(idx_str), {})[field] = (
            value if isinstance(value, str) else None
        )

    forms: list[HoldingForm] = []
    for idx in sorted(rows):
        row = rows[idx]
        instrument = _clean(row.get("instrument"))
        if instrument is None:          # 빈 행 = 미입력 → 스킵
            continue
        forms.append(
            HoldingForm(
                instrument=instrument,
                canonical_ticker=_clean(row.get("canonical_ticker")),
                market=_clean(row.get("market")),
                quantity=_clean(row.get("quantity")),
                value_manual=_clean(row.get("value_manual")),
                ccy=_clean(row.get("ccy")),
                avg_price=_clean(row.get("avg_price")),
                category=row.get("category"),   # ''(자동) 보존
                target_pct=_clean(row.get("target_pct")),
            )
        )
    return forms


def _parse_float(value: str | None) -> float | None:
    """문자열 → float. 변환 불가/None이면 None."""
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _is_valid_ticker(ticker: str) -> bool:
    """ticker 형식: 영숫자·'.'만(정규화는 tickers.py 책임, 폼은 형식만). 03 §2.4."""
    return all(c.isalnum() or c == "." for c in ticker) and bool(ticker)


def _classify_category(
    instrument: str, canonical_ticker: str | None, explicit: str | None
) -> str | None:
    """category 자동판정(G4, 03 §2.4). 사용자 명시값 우선, ''이면 화이트리스트 판정."""
    if explicit:                        # core/satellite 명시
        return explicit
    if instrument == "stock":
        return "satellite"
    if instrument == "etf":
        return "core" if canonical_ticker in CORE_ETF_WHITELIST else None
    return None


def validate_holdings(forms: list[HoldingForm]) -> HoldingsValidation:
    """03 §2.4 규칙 전량 검증 → 통과 시 HoldingRow 정규화.

    규칙: auto 필수(stock/etf)·manual 필수(cash)·ccy 일관·ticker 형식·
    category 값·target 배타(G5)·target 합 100%±0.5·중복 ticker.
    실패는 FieldError 리스트, 통과는 정규화된 HoldingRow 리스트.
    """
    errors: list[FieldError] = []
    rows: list[HoldingRow] = []
    seen_tickers: dict[str, int] = {}
    # G5 배타 판정: stock/etf 행 중 target 입력/미입력 집계.
    target_filled: list[bool] = []
    target_values: list[float] = []

    for i, f in enumerate(forms):
        instrument = f.instrument

        # category 값 검증(''|core|satellite만)
        category_raw = f.category if f.category is not None else ""
        if category_raw not in ("", "core", "satellite"):
            errors.append(FieldError(i, "category", "구분 값이 올바르지 않습니다"))

        # ticker 형식(stock/etf만 해당, 값이 있을 때)
        if instrument in ("stock", "etf") and f.canonical_ticker is not None:
            if not _is_valid_ticker(f.canonical_ticker):
                errors.append(
                    FieldError(i, "canonical_ticker", "종목코드 형식이 올바르지 않습니다")
                )

        quantity = _parse_float(f.quantity)
        value_manual = _parse_float(f.value_manual)

        if instrument in ("stock", "etf"):
            # auto 필수: ticker·market·quantity>0
            if (
                f.canonical_ticker is None
                or f.market is None
                or quantity is None
                or quantity <= 0
            ):
                errors.append(
                    FieldError(i, None, "종목코드·시장·수량은 필수입니다")
                )
            # ccy 일관: US → USD 권장
            if f.market == "US" and f.ccy is not None and f.ccy != "USD":
                errors.append(
                    FieldError(i, "ccy", "미국 시장 종목의 통화는 USD를 권장합니다")
                )
            # 중복 ticker
            if f.canonical_ticker is not None:
                if f.canonical_ticker in seen_tickers:
                    errors.append(
                        FieldError(
                            i,
                            "canonical_ticker",
                            f"중복된 종목코드: {f.canonical_ticker}",
                        )
                    )
                else:
                    seen_tickers[f.canonical_ticker] = i

        elif instrument == "cash":
            # manual 필수: value_manual>0·ccy
            if value_manual is None or value_manual <= 0:
                errors.append(
                    FieldError(i, "value_manual", "달러예금은 평가액을 입력하세요")
                )
            # cash → ccy=USD
            if f.ccy is not None and f.ccy != "USD":
                errors.append(
                    FieldError(i, "ccy", "달러예금의 통화는 USD입니다")
                )
        else:
            errors.append(FieldError(i, "instrument", "자산 유형이 올바르지 않습니다"))

        # target 배타(G5) 집계 — stock/etf만(cash도 §2.1상 선택 가능하나 비중 대상은 전 행)
        target_pct = _parse_float(f.target_pct)
        target_filled.append(target_pct is not None)
        if target_pct is not None:
            target_values.append(target_pct)

    # target 배타: 일부만 채움 → reject(전부 입력 or 전부 비움)
    if target_filled and any(target_filled) and not all(target_filled):
        errors.append(
            FieldError(-1, None, "목표비중은 전부 입력하거나 전부 비워두세요")
        )
    # target 합계: 전부 수동이면 합 100%±0.5
    elif target_filled and all(target_filled):
        total = sum(target_values)
        if abs(total - 100.0) > _TARGET_SUM_TOLERANCE:
            errors.append(
                FieldError(
                    -1,
                    None,
                    f"수동 목표비중 합이 100%가 아닙니다 (현재 {total:g}%)",
                )
            )

    if errors:
        return HoldingsValidation(ok=False, rows=[], errors=errors)

    # 검증 통과 → HoldingRow 정규화
    all_manual_target = bool(target_filled) and all(target_filled)
    for f in forms:
        instrument = f.instrument
        if instrument == "cash":
            asset_class = "cash"
            tracking = "manual"
        else:
            asset_class = "equity"
            tracking = "auto"

        category = _classify_category(instrument, f.canonical_ticker, f.category)
        # 자동 target_pct는 None 유지(저장 안 함). 전부 수동일 때만 값 영속.
        target_pct = _parse_float(f.target_pct) if all_manual_target else None

        rows.append(
            HoldingRow(
                id=None,
                user_id=1,
                asset_class=asset_class,
                instrument=instrument,
                tracking=tracking,
                market=f.market,
                canonical_ticker=f.canonical_ticker,
                name=f.canonical_ticker or "달러예금",
                quantity=_parse_float(f.quantity),
                value_manual=_parse_float(f.value_manual),
                ccy=f.ccy if f.ccy else ("USD" if instrument == "cash" else None),
                avg_price=_parse_float(f.avg_price),
                category=category,
                target_pct=target_pct,
            )
        )

    return HoldingsValidation(ok=True, rows=rows, errors=[])
