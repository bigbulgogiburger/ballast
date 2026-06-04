"""포트폴리오 비중·드리프트·리밸런싱 지표 (BAL-20). 04 §9.2.

핵심 불변식(CLAUDE.md NEVER):
  - 비중 분모 = value_base 산출 종목(status='ok') 합. 보류(value_base=None)는
    분모에서 0 취급/드롭이 아니라 '비중 미산출' — sum에 끼지 않을 뿐 별도 처리.
  - 제공자 PER/PBR 등 제공자 계산값을 재계산하지 않는다 (이 모듈은 비중·드리프트만).
  - 자동목표(auto_targets)는 평가액 타입을 아예 받지 않는다 — 런타임 순환 차단(G5).
  - 5/25 '작은 쪽': 절대 band_abs(%p)와 상대 tgt*band_rel(%) 중 먼저 닿는 쪽 트리거.
"""
from dataclasses import dataclass

from app.models import HoldingRow, PricedHolding


@dataclass(frozen=True)
class DriftResult:
    per_group: dict[str, float]   # 자산군별 현재-목표 격차(%p, 현재 - 목표)
    flags: dict[str, bool]        # 자산군별 리밸런스 트리거
    rebalance_needed: bool


@dataclass(frozen=True)
class CoreSatResult:
    core_pct: float
    satellite_pct: float
    over_limit: bool


@dataclass(frozen=True)
class AllocResult:
    equity_pct: float
    cash_pct: float
    alloc_held: bool


@dataclass(frozen=True)
class DcaResult:
    allocations: dict[str, float]  # canonical_ticker → 배분 금액(base ccy)
    note_key: str


def _priced_base(priced: list[PricedHolding]) -> list[PricedHolding]:
    """비중 분모에 들어가는 산출가능 종목(value_base 실재)만."""
    return [p for p in priced if p.value_base is not None]


def auto_targets(holdings_without_value: list[HoldingRow]) -> dict[str, float]:
    """G5 자동 목표비중 — 평가액 없이 그룹균등 → 그룹내 균등 (합 100%).

    - equity 자산만 대상(cash는 1층 배분 소관, 목표비중 분배에서 제외).
    - 그룹 = category(core/satellite). 미지정(None)은 자체 그룹으로 분리.
    - 산출 가능한 그룹에 100%를 균등 배분 → 각 그룹 내 종목에 다시 균등 배분.
    """
    equity = [
        h
        for h in holdings_without_value
        if h.asset_class == "equity" and h.canonical_ticker is not None
    ]
    if not equity:
        return {}

    groups: dict[str | None, list[str]] = {}
    for h in equity:
        groups.setdefault(h.category, []).append(h.canonical_ticker)

    group_share = 100.0 / len(groups)
    out: dict[str, float] = {}
    for tickers in groups.values():
        per_ticker = group_share / len(tickers)
        for ct in tickers:
            out[ct] = per_ticker
    return out


def _group_current_pct(priced_base: list[PricedHolding]) -> dict[str, float]:
    """category(core/satellite) 자산군별 현재 비중(%). 분모 = equity value_base 합."""
    equity = [p for p in priced_base if p.holding.asset_class == "equity"]
    total = sum(p.value_base for p in equity)  # type: ignore[misc]
    if total <= 0:
        return {}
    cur: dict[str, float] = {}
    for p in equity:
        g = p.holding.category if p.holding.category is not None else "uncategorized"
        cur[g] = cur.get(g, 0.0) + (p.value_base / total) * 100.0  # type: ignore[operator]
    return cur


def _target_group_pct(targets: dict[str, float], priced_base: list[PricedHolding]) -> dict[str, float]:
    """종목 단위 target → category 자산군 단위 목표 비중으로 집계."""
    cat_by_ticker: dict[str, str] = {}
    for p in priced_base:
        ct = p.holding.canonical_ticker
        if ct is not None:
            cat_by_ticker[ct] = (
                p.holding.category if p.holding.category is not None else "uncategorized"
            )
    tgt: dict[str, float] = {}
    for ct, pct in targets.items():
        g = cat_by_ticker.get(ct)
        if g is None:
            continue
        tgt[g] = tgt.get(g, 0.0) + pct
    return tgt


def drift(
    priced: list[PricedHolding],
    targets: dict[str, float],
    band_abs: float,
    band_rel: float,
    micro_floor: float,
) -> DriftResult:
    """① 자산군(코어/새틀) 5/25 '작은 쪽' 드리프트 플래그.

    - band_abs: 절대 밴드(%p, 예 5). band_rel: 상대 밴드(비율, 예 0.25).
    - 트리거: |gap| >= band_abs 또는 |gap| >= tgt*band_rel 중 '먼저 닿는 쪽'.
    - micro_floor(%p) 미만 격차는 거짓신호로 억제.
    - 소수종목(equity 산출가능 < 2) → 전 플래그 억제.
    """
    priced_base = _priced_base(priced)
    cur = _group_current_pct(priced_base)
    tgt = _target_group_pct(targets, priced_base)

    groups = set(cur) | set(tgt)
    per_group: dict[str, float] = {}
    flags: dict[str, bool] = {}

    equity_n = sum(
        1 for p in priced_base if p.holding.asset_class == "equity"
    )
    suppress = equity_n < 2

    for g in groups:
        c = cur.get(g, 0.0)
        t = tgt.get(g, 0.0)
        gap = c - t
        per_group[g] = gap
        abs_gap = abs(gap)
        if suppress or abs_gap < micro_floor:
            flags[g] = False
            continue
        thresholds = [band_abs]
        if t > 0:
            thresholds.append(t * band_rel)
        trigger = min(thresholds)  # 작은 쪽 = 먼저 닿는 임계
        flags[g] = abs_gap >= trigger

    return DriftResult(
        per_group=per_group,
        flags=flags,
        rebalance_needed=any(flags.values()),
    )


def core_sat(priced: list[PricedHolding], limit_pct: float) -> CoreSatResult:
    """② category 코어/새틀 합계 + 새틀 한도 초과 판정.

    분모 = equity 산출가능 value_base 합. 한도는 satellite 비중에 적용.
    """
    cur = _group_current_pct(_priced_base(priced))
    core_pct = cur.get("core", 0.0)
    satellite_pct = cur.get("satellite", 0.0)
    return CoreSatResult(
        core_pct=core_pct,
        satellite_pct=satellite_pct,
        over_limit=satellite_pct > limit_pct,
    )


def asset_alloc(
    priced: list[PricedHolding],
    usd_held: bool,
    threshold_pct: float,
) -> AllocResult:
    """1층 equity vs cash 배분.

    G6: USD 자산이 보류(usd_held=True)이고 USD 비중 >= threshold_pct면
    1층 배분 전체를 보류(alloc_held=True). 분모 = 산출가능 value_base 합.
    """
    priced_base = _priced_base(priced)
    total = sum(p.value_base for p in priced_base)  # type: ignore[misc]
    if total <= 0:
        return AllocResult(equity_pct=0.0, cash_pct=0.0, alloc_held=usd_held)

    equity_v = sum(
        p.value_base for p in priced_base if p.holding.asset_class == "equity"  # type: ignore[misc]
    )
    cash_v = sum(
        p.value_base for p in priced_base if p.holding.asset_class == "cash"  # type: ignore[misc]
    )
    equity_pct = (equity_v / total) * 100.0
    cash_pct = (cash_v / total) * 100.0

    usd_pct = (
        sum(
            p.value_base  # type: ignore[misc]
            for p in priced_base
            if p.holding.ccy == "USD"
        )
        / total
    ) * 100.0
    alloc_held = usd_held and usd_pct >= threshold_pct

    return AllocResult(
        equity_pct=equity_pct,
        cash_pct=cash_pct,
        alloc_held=alloc_held,
    )


def dca(
    priced: list[PricedHolding],
    drift_result: DriftResult,
    valuation_results,
    monthly: float,
) -> DcaResult:
    """⑥ 월 적립금 배분 — 드리프트 음수(미달) 자산군 우선, 저평가 보조.

    - 1순위: per_group < 0 (목표 미달) 자산군의 종목에 부족분 비례 배분.
    - 보조: valuation_results에서 펀더 게이트 통과(저평가) 종목 가중.
    - monthly<=0 또는 미달 자산군 없음 → 빈 배분 + note_key로 사유 전달.
    """
    if monthly <= 0:
        return DcaResult(allocations={}, note_key="dca_no_contribution")

    priced_base = _priced_base(priced)

    under_groups = {g: -gap for g, gap in drift_result.per_group.items() if gap < 0}
    if not under_groups:
        return DcaResult(allocations={}, note_key="dca_balanced")

    undervalued = _undervalued_tickers(valuation_results)

    weights: dict[str, float] = {}
    for p in priced_base:
        if p.holding.asset_class != "equity":
            continue
        ct = p.holding.canonical_ticker
        if ct is None:
            continue
        g = p.holding.category if p.holding.category is not None else "uncategorized"
        deficit = under_groups.get(g)
        if deficit is None:
            continue
        w = deficit
        if ct in undervalued:
            w *= 2.0  # 펀더 게이트 통과분 보조 가중
        weights[ct] = weights.get(ct, 0.0) + w

    total_w = sum(weights.values())
    if total_w <= 0:
        return DcaResult(allocations={}, note_key="dca_balanced")

    allocations = {ct: monthly * (w / total_w) for ct, w in weights.items()}
    return DcaResult(allocations=allocations, note_key="dca_drift_priority")


def _undervalued_tickers(valuation_results) -> set[str]:
    """valuation_results(매핑/이터러블)에서 저평가(게이트 통과) 종목 집합 추출.

    보수적 덕타이핑 — 형태 미확정(BAL-21/22 ValuationLabel)이라
    'undervalued'/저평가 라벨만 통과로 본다. 미해석 형태는 빈 집합.
    """
    if valuation_results is None:
        return set()
    items = (
        valuation_results.items()
        if hasattr(valuation_results, "items")
        else valuation_results
    )
    out: set[str] = set()
    for entry in items:
        ct = label = None
        if isinstance(entry, tuple) and len(entry) == 2:
            ct, label = entry
        else:
            ct = getattr(entry, "canonical_ticker", None)
            label = getattr(entry, "label", None)
        if ct is None or label is None:
            continue
        if str(label).lower() in {"undervalued", "저평가"}:
            out.add(ct)
    return out
