---
issue: BAL-22
title: gate evaluate_gate + collect_complete_today
type: slice
status: closed
week: W3
parent: BAL-3
persona: Python Expert
created: 2026-06-04
closed: 2026-06-04
---

# [BAL-22] gate — evaluate_gate + collect_complete_today — slice dev-guide

> 부모: `docs/BAL-3-dev-guide.md` · Wave C (20/21과 동시) · 소유: `app/metrics/gate.py`(신규) + `app/db.py`

### 0. Touched Files
- **신규**: `app/metrics/gate.py`
- **수정**: `app/db.py` (헬퍼 추가: `latest_collect_run`, `markets_in_use`), `app/calendar.py` (`expected_trade_date` 부재 시 추가)
- 읽기 전용: 04 §10.2, `app/models.py`
- ⚠️ db.py는 **본 슬라이스 단독 touch** (다른 슬라이스와 충돌 없음)

### 1. 작업 범위 (04 §10.2 — 스펙 코드 정본)
`app/metrics/gate.py`:
```python
from datetime import date
from dataclasses import dataclass
from app import db, calendar

@dataclass(frozen=True)
class GateResult:
    blocked: bool; fx_ok: bool; us_ok: bool; banner: str | None

def collect_complete_today(conn) -> bool:
    today = date.today()
    for m in db.markets_in_use(conn):
        run = db.latest_collect_run(conn, m)
        expected = calendar.expected_trade_date(m, today).isoformat()
        if run is None or run["trade_date"] != expected:
            return False
    return True

def evaluate_gate(conn) -> GateResult:
    kr = db.latest_collect_run(conn, "KR")
    us = db.latest_collect_run(conn, "US")
    fx = db.latest_collect_run(conn, "FX")
    def alive(r): return r is not None and r["status"] in {"OK","PARTIAL","BACKFILL","OK_HOLIDAY"}
    if not (alive(kr) or alive(us)):
        return GateResult(True, False, False, "데이터 미갱신 — 브리핑 보류")
    return GateResult(False, alive(fx), alive(us),
                      None if alive(fx) and alive(us) else "일부 시장 데이터 보류")
```

### 2. db.py 헬퍼 추가 (named param 바인딩 — 문자열 연결 금지)
```python
def latest_collect_run(conn, market: str) -> sqlite3.Row | None:
    # collect_run에서 market의 MAX(trade_date) row 1건 (status·trade_date 포함)
def markets_in_use(conn, user_id: int = 1) -> list[str]:
    # 보유 종목이 있는 시장 집합 (holdings.market DISTINCT, cash 제외)
```
> `upsert_collect_run`(db.py:271)으로 collect_run 테이블 존재 확인됨. 컬럼명은 05 §1 스키마 따름.

### 3. 인수조건
- [ ] 게이트 분기 정확: `BACKFILL`/`OK_HOLIDAY`=차단 아님, `FAIL`만 차단. KR·US 모두 죽으면 blocked.
- [ ] collect 미완 시 전날값 오판정 방지 (`collect_complete_today` False → 보류)
- [ ] fx_ok=False → USD 자산 보류는 build_priced(BAL-19) 책임, gate는 플래그만

### 4. 검증
`ruff check app/metrics/gate.py app/db.py`. 게이트 분기 테스트는 BAL-23.
