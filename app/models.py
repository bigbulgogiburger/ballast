"""도메인 모델(dataclass) 정의 — W1/M1a 슬라이스(BAL-1).

W-1a 선커밋 범위(decisions §3.8): W1 코드가 참조하는 5종만 선정의한다.
  - HoldingInput (mutable) — 04 §4.1
  - OHLCV / Funda / Headline / RegimeRow (frozen) — 04 §4.2
FxRate·SecurityCard·BriefingDoc 등 W2+ DTO는 본 슬라이스 범위 밖.

SSoT: TECH-DESIGN §15.2 > docs/04-backend.md §4 > docs/05-database.md §1.
OHLCV.sma200/week52_* 는 04 §4.2의 non-Optional을 override하여 `float | None`로 둔다
(decisions §3.5 [충돌 #4]: 05 §1.3 REAL NULL 허용 + 04 §9 'NULL→degrade' 정합).
"""
from dataclasses import dataclass
from typing import Literal


@dataclass
class HoldingInput:
    """POST /holdings 폼 파싱용 (mutable: validation 단계에서 채움). 04 §4.1."""

    instrument: Literal["stock", "etf", "cash"]
    name: str
    canonical_ticker: str | None = None
    market: Literal["KR", "US"] | None = None
    quantity: float | None = None
    value_manual: float | None = None
    ccy: Literal["KRW", "USD"] | None = None
    avg_price: float | None = None
    category: Literal["core", "satellite"] | None = None  # 사용자 명시(선택)
    target_pct: float | None = None


@dataclass(frozen=True)
class OHLCV:
    """소스 시세 값 DTO. 04 §4.2 (week52/sma200은 decisions §3.5로 float|None 확장)."""

    canonical_ticker: str
    trade_date: str            # 소스 최신 거래일 (YYYY-MM-DD)
    close_raw: float           # 미조정 (현재 평가액용)
    close_adj: float           # 조정 (스냅샷 표시·감사용)
    ccy: Literal["KRW", "USD"]
    week52_high: float | None  # 조정가 기준 fresh 재계산. 윈도우<252 → None (decisions §3.5)
    week52_low: float | None
    sma200: float | None       # 윈도우<200 → None


@dataclass(frozen=True)
class Funda:
    """소스 펀더멘털 값 DTO. 04 §4.2."""

    canonical_ticker: str
    trade_date: str
    per: float | None              # 적자=None
    pbr: float | None
    div_yield: float | None
    per_pctile_5y: float | None    # NULL 허용(백필중/US 정밀도)
    pbr_pctile_5y: float | None
    report_date: str | None        # 재무 실제 기준일 (미확보 시 NULL — 배지 '워밍업')


@dataclass(frozen=True)
class Headline:
    """뉴스 헤드라인 DTO. 04 §4.2/§4.3."""

    title: str
    url: str
    source: str


@dataclass(frozen=True)
class RegimeRow:
    """market_regime 적재용(월단위) DTO. 04 §4.2.

    upsert 매핑: as_of→trade_date, us_cape→shiller_cape (05 §1.7).
    """

    as_of: str                 # 기준월 ('YYYY-MM-01')
    kospi_pbr: float | None    # KR — pykrx 지수 PBR
    us_cape: float | None      # US — Shiller CAPE (W1=None)
