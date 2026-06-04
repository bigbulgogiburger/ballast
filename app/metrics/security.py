"""개별 종목 밸류에이션·추세·레짐 라벨 계산 (BAL-21, 04 §9.2).

핵심 불변식(CLAUDE.md NEVER):
  - 제공자 PER/PBR 재계산 금지 — Funda 값을 그대로 노출(캐시값만).
  - per_pctile_5y NULL → '워밍업 중'(절대 PER만), 음수/적자 PER는 판정 제외.
  - sqlite Row(shiller_cape)·RegimeRow(us_cape) 둘 다 None-safe 접근.

회귀(④⑤)는 BAL-23. metrics는 수치/라벨만 산출(LLM이 문장 톤 덧입힘).
"""
from dataclasses import dataclass

from app.models import OHLCV, Funda

# ③ valuation pctile 임계 (양면 라벨)
_PCTILE_LOW = 0.3
_PCTILE_HIGH = 0.7


@dataclass(frozen=True)
class ValuationLabel:
    """③ 양면 밸류에이션 라벨. per_pctile_5y NULL → '워밍업 중'."""

    label: str                 # '저평가'|'고평가'|'중립'|'워밍업 중'
    pctile: float | None       # per_pctile_5y (NULL→warmup)
    per: float | None
    pbr: float | None
    div_yield: float | None


@dataclass(frozen=True)
class TrendLabel:
    """④ 맥락용 추세 지표(None-safe)."""

    week52_pos: float | None    # 52주 내 위치 0~1
    sma200_gap: float | None    # 200일선 이격도 (close_adj vs sma200)


def change_pct(ohlcv: OHLCV, prev_close: float | None) -> float | None:
    """전일 대비 등락률(%). prev_close None/0 → None (MVP nullable)."""
    if prev_close is None or prev_close == 0:
        return None
    return (ohlcv.close_raw - prev_close) / prev_close * 100


def valuation(funda: Funda) -> ValuationLabel:
    """③ per_pctile_5y NULL → '워밍업 중'. 음수/적자 PER 판정 제외(중립).

    PER/PBR/div_yield는 Funda 값 그대로 노출(재계산 금지 — CLAUDE.md).
    """
    pctile = funda.per_pctile_5y
    if pctile is None:
        label = "워밍업 중"
        pctile = None
    elif funda.per is None or funda.per < 0:
        # 음수/적자 PER → pctile 기반 판정 스킵, 중립 처리
        label = "중립"
    elif pctile < _PCTILE_LOW:
        label = "저평가"
    elif pctile > _PCTILE_HIGH:
        label = "고평가"
    else:
        label = "중립"
    return ValuationLabel(
        label=label,
        pctile=pctile,
        per=funda.per,
        pbr=funda.pbr,
        div_yield=funda.div_yield,
    )


def trend(ohlcv: OHLCV) -> TrendLabel:
    """④ 52주 내 위치·200일선 이격도(None-safe).

    week52_pos = (close_adj - low) / (high - low); high==low → None.
    sma200_gap = (close_adj - sma200) / sma200; sma200 None/0 → None.
    """
    high = ohlcv.week52_high
    low = ohlcv.week52_low
    if high is None or low is None or high == low:
        week52_pos = None
    else:
        week52_pos = (ohlcv.close_adj - low) / (high - low)

    sma200 = ohlcv.sma200
    if sma200 is None or sma200 == 0:
        sma200_gap = None
    else:
        sma200_gap = (ohlcv.close_adj - sma200) / sma200

    return TrendLabel(week52_pos=week52_pos, sma200_gap=sma200_gap)


def regime(market_regime_row) -> str:
    """⑤ CAPE(US)·KOSPI PBR 한 줄. 둘 다 None → '레짐 데이터 미확보'.

    RegimeRow(us_cape) / sqlite Row(shiller_cape) 둘 다 안전 접근.
    """
    if market_regime_row is None:
        return "레짐 데이터 미확보"
    kospi_pbr = _get(market_regime_row, "kospi_pbr")
    us_cape = _get(market_regime_row, "us_cape")
    if us_cape is None:
        us_cape = _get(market_regime_row, "shiller_cape")
    if kospi_pbr is None and us_cape is None:
        return "레짐 데이터 미확보"

    parts: list[str] = []
    if kospi_pbr is not None:
        parts.append(f"KOSPI PBR {kospi_pbr:.2f}")
    if us_cape is not None:
        parts.append(f"US CAPE {us_cape:.1f}")
    return " · ".join(parts)


def _get(row, key: str):
    """RegimeRow(attr)·sqlite Row(key) 양쪽 None-safe 접근."""
    try:
        return row[key]
    except (TypeError, KeyError, IndexError):
        return getattr(row, key, None)
