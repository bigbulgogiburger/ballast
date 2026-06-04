# [BAL-20] metrics.portfolio — auto_targets·drift·core_sat·dca — slice dev-guide

> 부모: `docs/BAL-3-dev-guide.md` · Wave C (BAL-19 후, 21/22와 동시) · 소유: `app/metrics/portfolio.py`

### 0. Touched Files
- **수정**: `app/metrics/portfolio.py` (현재 스텁)
- 읽기 전용: `app/models.py`(PricedHolding/HoldingRow), 04 §9.2
- ⚠️ `__init__.py` 만지지 말 것 (리드 통합)

### 1. 작업 범위 (04 §9.2 시그니처 고정)
결과 타입은 **본 모듈에 frozen dataclass로 로컬 정의** (§15.2 아님):

```python
@dataclass(frozen=True)
class DriftResult:
    per_group: dict[str, float]          # 자산군별 현재-목표 격차(%p)
    flags: dict[str, bool]               # 자산군별 리밸런스 트리거
    rebalance_needed: bool

@dataclass(frozen=True)
class CoreSatResult:
    core_pct: float; satellite_pct: float; over_limit: bool

@dataclass(frozen=True)
class AllocResult:
    equity_pct: float; cash_pct: float; alloc_held: bool

@dataclass(frozen=True)
class DcaResult:
    allocations: dict[str, float]; note_key: str

def auto_targets(holdings_without_value: list[HoldingRow]) -> dict[str, float]:
    # G5 순환차단: 평가액 타입 안 받음. 그룹목표 → 그룹내 균등 분배.

def drift(priced: list[PricedHolding], targets: dict[str, float],
          band_abs: float, band_rel: float, micro_floor: float) -> DriftResult:
    # ① 자산군(코어/새틀) 집계 후 5/25 "작은 쪽" 플래그. micro_floor 미만 억제.

def core_sat(priced: list[PricedHolding], limit_pct: float) -> CoreSatResult:
    # ② category 코어/새틀 합계 + 30% 한도 초과.

def asset_alloc(priced: list[PricedHolding], usd_held: bool, threshold_pct: float) -> AllocResult:
    # 1층 equity vs cash. G6: usd_held & USD비중>=threshold → alloc_held=True.

def dca(priced, drift_result: DriftResult, valuation_results, monthly: float) -> DcaResult:
    # ⑥ 드리프트 음수 우선, 저평가는 펀더 게이트 통과분만 보조.
```

### 2. 핵심 로직 — ① 5/25 "작은 쪽"
자산군 g의 현재비중 `cur`, 목표 `tgt`에 대해:
- 절대 트리거: `abs(cur - tgt) >= band_abs` (예: 5%p)
- 상대 트리거: `abs(cur - tgt) >= tgt * band_rel` (예: 25%)
- **작은 쪽 먼저**: `min` 임계 = 둘 중 먼저 닿는 것 → 둘 중 하나라도 초과면 flag. `micro_floor`(예: 최소 금액/비중) 미만 격차는 억제.

### 3. 인수조건
- [ ] 5/25 작은 쪽(절대 5%p vs 상대 25%) 먼저 트리거
- [ ] 자동목표 순환차단 — `auto_targets`가 평가액 인자 없이 그룹 균등
- [ ] **분모**: 보류(value_base=None) 종목은 비중 계산 분모에서 제외하지 않되 placeholder (CLAUDE.md). 분모 = 산출가능 종목 value_base 합. (보류는 "비중 미산출", 분모 오염 아님 — value_base=None은 sum에서 0 취급이 아니라 별도 placeholder)
- [ ] 소수종목(<2)·엣지 → flag 억제

### 4. 검증
`ruff check app/metrics/portfolio.py`. 회귀 ①③은 BAL-23.
