---
issue: BAL-21
title: metrics.security change_pct·valuation·trend
type: slice
status: closed
week: W3
parent: BAL-3
persona: Python Expert
created: 2026-06-04
closed: 2026-06-04
---

# [BAL-21] metrics.security — change_pct·valuation·trend·regime — slice dev-guide

> 부모: `docs/BAL-3-dev-guide.md` · Wave C (BAL-19 후, 20/22와 동시) · 소유: `app/metrics/security.py`

### 0. Touched Files
- **수정**: `app/metrics/security.py` (현재 스텁)
- 읽기 전용: `app/models.py`(OHLCV/Funda), 04 §9.2
- ⚠️ `__init__.py` 만지지 말 것 (리드 통합)

### 1. 작업 범위 (04 §9.2)
결과 라벨 타입은 **본 모듈 로컬 frozen dataclass**:

```python
@dataclass(frozen=True)
class ValuationLabel:
    label: str                 # ③ 양면 라벨 ('저평가'/'고평가'/'중립'/'워밍업 중')
    pctile: float | None       # per_pctile_5y (NULL→warmup)
    per: float | None; pbr: float | None; div_yield: float | None

@dataclass(frozen=True)
class TrendLabel:
    week52_pos: float | None    # ④ 52주 내 위치 0~1
    sma200_gap: float | None    # 이격도 (close vs sma200)

def change_pct(ohlcv: OHLCV, prev_close: float | None) -> float | None:
    # 전일 대비 등락. prev_close 없으면 None (MVP nullable).
    if prev_close is None or prev_close == 0:
        return None
    return (ohlcv.close_raw - prev_close) / prev_close * 100

def valuation(funda: Funda) -> ValuationLabel:
    # ③ per_pctile_5y NULL → "워밍업 중(절대 PER만)". 음수/None PER 제외.
def trend(ohlcv: OHLCV) -> TrendLabel:    # ④ 52주위치·sma200 gap, week52_*/sma200 None → None
def regime(market_regime_row) -> str:      # ⑤ CAPE(US)·KOSPI PBR 한 줄. 둘 다 NULL → "레짐 데이터 미확보"
```

### 2. 핵심 로직 — ③ valuation
- `funda.per_pctile_5y is None` → `label="워밍업 중"`, pctile=None (절대 PER만 노출, **재계산 금지** — CLAUDE.md).
- `funda.per is None or funda.per < 0` → **음수/적자 PER 제외** (pctile 기반 판정 스킵, label 중립 처리).
- pctile 존재 시 양면: 낮으면 저평가 / 높으면 고평가 (임계는 settings 또는 상수).

### 3. 인수조건
- [ ] per_pctile NULL → warmup 라벨
- [ ] 음수 PER 제외 (판정에서 빠짐)
- [ ] week52_high/low/sma200 None → trend None-safe
- [ ] **제공자 PER/PBR 재계산 금지** (Funda 값 그대로)

### 4. 검증
`ruff check app/metrics/security.py`. 회귀 ④⑤는 BAL-23.
