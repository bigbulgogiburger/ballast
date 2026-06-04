"""도메인 모델(dataclass) 정의 — W1/M1a 슬라이스(BAL-1).

W-1a 선커밋 범위(decisions §3.8): W1 코드가 참조하는 5종만 선정의한다.
  - HoldingInput (mutable) — 04 §4.1
  - OHLCV / Funda / Headline / RegimeRow (frozen) — 04 §4.2
FxRate·SecurityCard·BriefingDoc 등 W2+ DTO는 본 슬라이스 범위 밖.

SSoT: TECH-DESIGN §15.2 > docs/04-backend.md §4 > docs/05-database.md §1.
OHLCV.sma200/week52_* 는 04 §4.2의 non-Optional을 override하여 `float | None`로 둔다
(decisions §3.5 [충돌 #4]: 05 §1.3 REAL NULL 허용 + 04 §9 'NULL→degrade' 정합).
"""
import json
from dataclasses import asdict, dataclass
from typing import Literal, Protocol


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


@dataclass(frozen=True)
class FxRate:
    """환율 DTO (W2 — BAL-14). 05 §1.5 fx_snapshot 컬럼 1:1 (asdict 키 = 전체명).

    W1 decisions §3.8에서 W2로 유보됐던 DTO. 본 슬라이스가 유보 해제.
    """

    trade_date: str   # 'YYYY-MM-DD'
    pair: str         # 'USDKRW'
    rate: float       # USD 1단위 = KRW (decisions §1.2 Q5)


# ─────────────────────────────────────────────────────────────────────────
# W3/M2 슬라이스(BAL-18) — §15.2 DTO 전량 + Protocol.
# 정본: TECH-DESIGN §15.2 > docs/04-backend.md §4.1·§4.3·§4.4·§9.1·§6.3.
# 기존 6종(HoldingInput/OHLCV/Funda/Headline/RegimeRow/FxRate)은 위에 정의됨 — 재정의 금지.
# ─────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class HoldingRow:
    """holdings 테이블 영속 형태(검증·자동판정 후). 04 §4.1."""

    id: int | None
    user_id: int
    asset_class: Literal["equity", "cash"]
    instrument: Literal["stock", "etf", "cash"]
    tracking: Literal["auto", "manual"]
    market: Literal["KR", "US"] | None
    canonical_ticker: str | None
    name: str
    quantity: float | None
    value_manual: float | None
    ccy: Literal["KRW", "USD"] | None
    avg_price: float | None
    category: Literal["core", "satellite"] | None
    target_pct: float | None


@dataclass(frozen=True)
class PricedHolding:
    """통화정규화 완료(base=KRW). 04 §9.1. status=§15.4 enum."""

    holding: HoldingRow
    value_base: float | None   # quantity*close_raw*(fx if US else 1); USD현금=value_manual*fx
    status: str                # 'ok'|'data_pending'|'fx_held'|'warmup'|'failed'


@dataclass(frozen=True)
class SecurityLLMOut:
    """LLM 텍스트 전용 출력. 06 §1.3 — 코드가 수치를 슬롯주입해 SecurityCard로 머지."""

    canonical_ticker: str
    comment: str
    trend_note: str
    investment_points: list[str]


@dataclass(frozen=True)
class SecurityCard:
    """코드가 슬롯주입한 최종형 = 대시보드/JSON 직렬화 정본. 04 §4.4 / §15.2."""

    canonical_ticker: str
    name: str
    instrument: str
    asset_class: str
    category: str | None
    change_pct: float | None
    current_pct: float
    target_pct: float | None
    drift: float | None
    rebalance_flag: bool
    per: float | None
    pbr: float | None
    div_yield: float | None
    valuation_pctile: float | None
    valuation_label: str
    week52_pos: float | None
    sma200_gap: float | None
    status: str                # §15.4 enum
    comment: str               # ↓ LLM(SecurityLLMOut) 머지
    trend_note: str
    investment_points: list[str]


@dataclass(frozen=True)
class HoldExcluded:
    """G2 전용(LLM 미매칭/중복 처리실패). 04 §4.4 / §15.2."""

    canonical_ticker: str
    reason: str


@dataclass(frozen=True)
class FreshnessBadge:
    """신선도 배지(G10 — 입력 일원화). 04 §6.3 / §15.2."""

    price_age_days: int
    funda_label: str
    fx_age_days: int
    worst_level: str           # 'fresh'|'stale'|'warn'
    consecutive_fallback: bool


@dataclass(frozen=True)
class BriefingDoc:
    """briefing.content_json 직렬화 정본. 04 §4.4 / §15.2."""

    briefing_date: str
    model: str
    created_at: str
    banner: str | None                      # 게이트 차단/부분보류 안내(정상시 None)
    regime_label: str                        # ⑤ top-level 1개
    as_of: dict                              # {'price','funda','fx'} 3키 고정
    asset_allocation: dict                   # 1층 + 2층
    securities: list[SecurityCard]
    holds_excluded: list[HoldExcluded]       # G2만. 보류는 securities[].status 단일경로
    dca: dict
    portfolio_comment: dict                  # {'rebalance_note','dca_note','weight_note'}
    disclaimer: str                          # 고정 면책(코드 상수)

    def to_json(self) -> str:
        """asdict 직렬화(중첩 dataclass 포함). ensure_ascii=False로 한글 보존."""
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, s: str) -> "BriefingDoc":
        d = json.loads(s)
        return cls(
            briefing_date=d["briefing_date"],
            model=d["model"],
            created_at=d["created_at"],
            banner=d["banner"],
            regime_label=d["regime_label"],
            as_of=d["as_of"],
            asset_allocation=d["asset_allocation"],
            securities=[SecurityCard(**c) for c in d["securities"]],
            holds_excluded=[HoldExcluded(**h) for h in d["holds_excluded"]],
            dca=d["dca"],
            portfolio_comment=d["portfolio_comment"],
            disclaimer=d["disclaimer"],
        )


# Protocol (SSoT §5 / 04 §4.3) — 어댑터 계약. 구현체는 sources/·06-ai-agent.
class PriceSource(Protocol):
    def ohlcv(self, ct: str) -> OHLCV: ...
    def fundamentals(self, ct: str) -> Funda: ...


class NewsSource(Protocol):
    def headlines(self, ct: str, name: str) -> list[Headline]: ...


class FxSource(Protocol):
    def usdkrw(self) -> FxRate: ...


class RegimeSource(Protocol):
    def regime(self) -> RegimeRow: ...


class LLMClient(Protocol):
    def generate(self, prompt: str, schema: dict) -> dict: ...
