---
issue: BAL-18
title: §15.2 DTO 전량 + Protocol
type: slice
status: closed
week: W3
parent: BAL-3
persona: Python Expert
created: 2026-06-04
closed: 2026-06-04
---

# [BAL-18] §15.2 DTO 전량 + Protocol — slice dev-guide

> 부모: `docs/BAL-3-dev-guide.md` · Wave A (토대, 최우선) · 소유: `app/models.py`

### 0. Touched Files
- **수정**: `app/models.py` (DTO 추가 — 기존 6종 보존, 절대 재정의 금지)
- 읽기 전용: `docs/04-backend.md` §4.1/§4.4/§9.1, §15.2

### 1. 작업 범위
`app/models.py`에 **frozen dataclass**로 추가 (기존 OHLCV/Funda/Headline/RegimeRow/FxRate/HoldingInput 유지):

```python
@dataclass(frozen=True)
class HoldingRow:           # 04 §4.1 — holdings 영속 형태
    id: int | None; user_id: int
    asset_class: Literal["equity", "cash"]
    instrument: Literal["stock", "etf", "cash"]
    tracking: Literal["auto", "manual"]
    market: Literal["KR", "US"] | None
    canonical_ticker: str | None; name: str
    quantity: float | None; value_manual: float | None
    ccy: Literal["KRW", "USD"] | None; avg_price: float | None
    category: Literal["core", "satellite"] | None; target_pct: float | None

@dataclass(frozen=True)
class PricedHolding:        # 04 §9.1 — 통화정규화 완료(base=KRW)
    holding: HoldingRow
    value_base: float | None
    status: str             # §15.4 enum

@dataclass(frozen=True)
class SecurityLLMOut:       # 06 §1.3 — LLM 텍스트 전용
    canonical_ticker: str; comment: str; trend_note: str
    investment_points: list[str]

@dataclass(frozen=True)
class SecurityCard:         # 04 §4.4 / §15.2 — 직렬화 정본 (필드 전량, §4.4 그대로)
    canonical_ticker: str; name: str; instrument: str; asset_class: str
    category: str | None
    change_pct: float | None; current_pct: float; target_pct: float | None
    drift: float | None; rebalance_flag: bool
    per: float | None; pbr: float | None; div_yield: float | None
    valuation_pctile: float | None; valuation_label: str
    week52_pos: float | None; sma200_gap: float | None
    status: str
    comment: str; trend_note: str; investment_points: list[str]

@dataclass(frozen=True)
class HoldExcluded:         # §15.2 — G2 전용
    canonical_ticker: str; reason: str

@dataclass(frozen=True)
class FreshnessBadge:       # 04 §6.3 / §15.2
    price_age_days: int; funda_label: str; fx_age_days: int
    worst_level: str; consecutive_fallback: bool

@dataclass(frozen=True)
class BriefingDoc:          # §15.2 — content_json 정본
    briefing_date: str; model: str; created_at: str
    banner: str | None; regime_label: str
    as_of: dict; asset_allocation: dict
    securities: list[SecurityCard]; holds_excluded: list[HoldExcluded]
    dca: dict; portfolio_comment: dict; disclaimer: str
    def to_json(self) -> str: ...
    @classmethod
    def from_json(cls, s: str) -> "BriefingDoc": ...
```
Protocol (`PriceSource/NewsSource/FxSource/RegimeSource/LLMClient`)는 04 §4.3 그대로. **이미 sources/에 동등 Protocol이 있으면** 재정의 말고 models에 누락분만.

### 2. 인수조건
- [ ] §15.2 DTO 전부 정의, **frozen 검증** (`dataclasses.fields`/`FrozenInstanceError` 테스트는 BAL-23)
- [ ] `BriefingDoc.to_json/from_json` 라운드트립 가능 (json.dumps + asdict)

### 3. 구현 노트
- `to_json`: `json.dumps(asdict(self), ensure_ascii=False)`. `from_json`: 중첩 `SecurityCard`/`HoldExcluded` 재구성.
- `import` 추가: `from typing import Literal, Protocol`, `from dataclasses import dataclass, field, asdict`, `import json`.

### 4. 검증
`python -c "from app.models import SecurityCard, BriefingDoc, PricedHolding, HoldingRow, SecurityLLMOut, HoldExcluded, FreshnessBadge"` + `ruff check app/models.py`.
