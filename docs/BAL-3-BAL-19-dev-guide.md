# [BAL-19] build_priced — 통화정규화·보류 처리 — slice dev-guide

> 부모: `docs/BAL-3-dev-guide.md` · Wave B (BAL-18 후) · 소유: `app/metrics/priced.py` (신규)

### 0. Touched Files
- **신규**: `app/metrics/priced.py`
- 읽기 전용: `app/models.py`(PricedHolding/HoldingRow), `app/db.py`(latest_price/latest_fx), 04 §9.1

### 1. 작업 범위
04 §9.1 `build_priced`를 그대로 구현 (스펙 코드가 정본):

```python
from app.models import PricedHolding, HoldingRow
from app import db

def _held(h: HoldingRow) -> PricedHolding:
    return PricedHolding(h, None, "fx_held")

def build_priced(conn, holdings: list[HoldingRow], fx_ok: bool, us_ok: bool) -> list[PricedHolding]:
    fx_rate = None
    if fx_ok:
        fx_row = db.latest_fx(conn, "USDKRW")
        fx_rate = fx_row["rate"] if fx_row is not None else None
        fx_ok = fx_rate is not None          # row 실종 → 게이트 일관 강등
    out: list[PricedHolding] = []
    for h in holdings:
        if h.tracking == "manual":           # 현금
            if h.ccy == "USD":
                if not fx_ok:
                    out.append(_held(h)); continue
                out.append(PricedHolding(h, h.value_manual * fx_rate, "ok")); continue
            out.append(PricedHolding(h, h.value_manual, "ok")); continue   # KRW 현금
        if h.market == "US" and not us_ok:
            out.append(PricedHolding(h, None, "data_pending")); continue
        price = db.latest_price(conn, h.canonical_ticker)
        if price is None:
            out.append(PricedHolding(h, None, "data_pending")); continue
        if h.market == "US" and not fx_ok:
            out.append(_held(h)); continue
        fx = fx_rate if h.market == "US" else 1.0
        out.append(PricedHolding(h, h.quantity * price["close_raw"] * fx, "ok"))
    return out
```

### 2. 인수조건 (★ CLAUDE.md NEVER 규칙)
- [ ] 보류 종목을 `status`로 표시하되 **분모에서 빼지 않음** (리스트에 항상 포함, value_base=None)
- [ ] **fx FAIL 시 KR만 100% 정규화 안 됨** — `fx`는 `market=='US'`에만 곱함 (전역 오염 금지)
- [ ] US collect FAIL(`us_ok=False`) → stale price여도 `data_pending` 강제 보류
- [ ] `fx_ok=True`인데 fx row 없음 → 모순이므로 `fx_held` 강등

### 3. 위험
- `value_base=None` 종목을 호출측이 sum에서 None 산입하지 않도록 — 본 슬라이스는 status만 책임, 합산은 portfolio(BAL-20).
- KRW 현금/USD 현금 분기 정확성 (G6).

### 4. 검증
`ruff check app/metrics/priced.py` + import 확인. 회귀 테스트는 BAL-23 ②.
