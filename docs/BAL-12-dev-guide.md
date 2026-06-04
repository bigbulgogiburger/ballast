---
issue: BAL-12
title: validate 빈응답 가드 + 005930 적재 E2E
type: single
status: closed
week: W1
parent: null
persona: Python Expert
created: 2026-06-02
closed: 2026-06-04
---

# BAL-12 개발 가이드 — validate: 빈 응답 가드 + 005930 적재 E2E 증명

> 정본 우선순위: `TECH-DESIGN.md §15` > `docs/04-backend.md` > `docs/05-database.md`. seam 시그니처 정본 = `docs/BAL-1-m1a-orchestration.md §2 (v2 canonical)`.
> 본 가이드의 코드블록 시그니처는 위 정본과 정합 검증을 마쳤다. **그대로 사용**하고 임의 변형/발명하지 말 것.
> 범위: W1(M1a 데이터 스파이크)만. Wave W-3(순차) 담당.

---

## 1. 목표 & 배경 (W1 슬라이스 내 역할)

BAL-12는 BAL-1/M1a 수직 슬라이스의 **마지막 통합 증명(integration tracer)**이다. 두 가지를 책임진다.

1. **공통 가드(빈 응답 방지)** — `app/sources/__init__.py`에 `EmptyResponseError` / `retry` / `validate_response`를 정의. "조용한 실패(빈 CSV·0행)를 OK로 오인 금지"라는 SSoT §4 규칙(05 §1.8, 04 §7.1·§12)을 강제하는 단일 지점. **소유는 BAL-12지만 생성 시점은 W-2a**(BAL-11 `kr.py`가 import하므로 BAL-11보다 먼저 만든다 — orchestration §2.7·§3 순서 의존).
2. **005930 E2E 증명** — `KrSource().ohlcv/fundamentals('005930')` → `db.upsert_price/funda(frozen dataclass)` → `db.latest_price/funda(conn,'005930')`가 실수치 row를 돌려주는 것을 끝까지 관통 확인. 슬라이스 전체(BAL-8 db / BAL-9 tickers / BAL-10 calendar / BAL-11 kr)가 한 종목으로 실제로 맞물리는지 검증한다.

### 의존 (orchestration §1 DAG)
- **BAL-8** `app/db.py`: `connect` / `init_schema` / `latest_price` / `latest_funda` / `upsert_price` / `upsert_funda` (frozen dataclass 인자)
- **BAL-9** `app/tickers.py`: `to_source` 변환표 (E2E 가드테스트 + `tests/test_tickers.py`의 대상)
- **BAL-11** `app/sources/kr.py`: `KrSource.ohlcv` / `fundamentals` — 본체에서 W-2a 가드를 import해 사용
- **models.py 부분**: `OHLCV` / `Funda` frozen dataclass (orchestration §2.4, 04 §4.2)
- BAL-12 자신이 소유하는 W-2a 가드 (`sources/__init__.py`)

> 현재 레포 상태: 모든 모듈이 W0 스텁(`app/sources/__init__.py` 빈 파일, `app/db.py`·`app/models.py`·`app/sources/kr.py`는 docstring만). 따라서 BAL-12 E2E는 BAL-8/9/11/models 부분이 먼저 green이어야 통과한다. **W-2a 가드 단위테스트(아래 6.1)는 의존이 거의 없어 가장 먼저 작성·통과시킬 수 있다.**

### 왜 BAL-12가 "통합 그 자체"인가
orchestration §0: BAL-8~12는 격리 5-fanout이 아니라 단일 슬라이스. 최종 산출물(BAL-12)이 곧 통합. 따라서 BAL-12의 DoD = W1 통합 DoD(08 Week1, orchestration §5)와 동일하다.

---

## 2. 영향 파일

| 파일 | 변경 | 비고 |
|---|---|---|
| `app/sources/__init__.py` | **신규 구현(W-2a)** | 현재 빈 파일. `EmptyResponseError`/`retry`/`validate_response` 추가. BAL-11보다 먼저 |
| `tests/test_sources_guard.py` | **신규** | `validate_response` 빈응답 단위테스트(rows==0→raise, rows>0→pass) + `retry` 거동 |
| `tests/test_tickers.py` | **신규** | `to_source` 변환표 전 케이스(04 §5.1 표) green. (모듈은 BAL-9 소유, 테스트는 W1 DoD라 BAL-12 범위) |
| `tests/test_e2e_005930.py` | **신규** | 005930 fetch→upsert→latest_* 실수치 row E2E. KR 어댑터 네트워크는 **모킹** |
| `tests/conftest.py` | 픽스처 추가 | 인메모리 DB conn 픽스처(`connect(":memory:")` + `init_schema`) |

> **건드리지 않을 것**: `app/db.py`·`app/tickers.py`·`app/sources/kr.py`·`app/models.py` 본체(각각 BAL-8/9/11 소유). BAL-12는 그 시그니처를 **소비/검증**만 한다. 가드(`sources/__init__.py`)만 BAL-12가 작성.

---

## 3. 구현 단계 (하위작업 / 자체분해 단위 + 검증포인트)

### 단계 A — W-2a 공통 가드 생성 (`app/sources/__init__.py`)
가장 먼저. BAL-11이 import한다.
- A1. `EmptyResponseError(Exception)` 정의 → **검증**: `from app.sources import EmptyResponseError` import 성공
- A2. `validate_response(rows, latest, expected) -> None` — `rows == 0`이면 `EmptyResponseError` raise → **검증**: `validate_response(0, "x", "y")`가 raise, `validate_response(1, d, d)`가 None
- A3. `retry(times=3, backoff=1.5)` 데코레이터 — 지수 백오프, 마지막 실패는 raise → **검증**: 항상 실패하는 함수에 `@retry(2)`면 정확히 2회 호출 후 마지막 예외 raise
- A4. `python3 -m py_compile app/sources/__init__.py` 통과

### 단계 B — 가드 단위테스트 (`tests/test_sources_guard.py`)
- B1. `validate_response` 빈응답 동작(아래 6.1) → **검증**: `pytest tests/test_sources_guard.py -q` green
- B2. `retry` 횟수/마지막 raise 동작 → **검증**: 호출 카운트 assert

### 단계 C — to_source 변환표 테스트 (`tests/test_tickers.py`)
- C1. 04 §5.1 표 전 케이스(아래 6.2) → **검증**: `pytest tests/test_tickers.py -q` green (BAL-9 구현 완료 전제)

### 단계 D — 005930 E2E (`tests/test_e2e_005930.py`)
- D1. conftest에 인메모리 DB 픽스처 추가 → **검증**: `connect(":memory:")` + `init_schema(conn)` 후 9테이블 존재
- D2. `KrSource.ohlcv`/`fundamentals`의 네트워크 호출을 모킹해 결정적 `OHLCV`/`Funda` 반환 → **검증**: 반환 타입이 frozen dataclass
- D3. `db.upsert_price(conn, ohlcv)` / `db.upsert_funda(conn, funda)` → `db.latest_price(conn,'005930')` / `latest_funda` → **검증**: row가 `None`이 아니고 `close_raw`·`week52_high`·`sma200`·`per`가 실수치
- D4. (선택, DoD 스모크) `pytest -q` 전체 green + 편집 파일 `py_compile` 통과

> **자체분해 원칙**: A→B는 의존 없음(먼저 끝낼 수 있음). C는 BAL-9, D는 BAL-8+11+models 완료 후. degraded-session이라 편집마다 `python3 -m py_compile <file>` 수동 실행(orchestration §4).

---

## 4. 인터페이스 (확정 시그니처 구체화)

### 4.1 `app/sources/__init__.py` — 공통 가드 (정본 04 §7.1 / orchestration §2.7)

```python
"""sources 공통 안정성 가드 (04 §7.1, SSoT §4·§5).

조용한 실패(빈 CSV·0행)를 OK로 오인하지 않기 위한 단일 지점.
BAL-11(kr.py)이 import하므로 W-2a(BAL-11 앞)에 먼저 생성한다.
"""
import functools
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


class EmptyResponseError(Exception):
    """응답 행수 0 — '조용한 실패'를 OK로 오인 방지 (SSoT §4 OK=데이터 실재)."""


def validate_response(rows: int, latest: str, expected: str) -> None:
    """응답 유효성: 행수>0 (04 §7.1, 05 §1.8).

    rows == 0 → EmptyResponseError. (Stooq 빈 CSV 등 조용한 실패 차단.)
    latest/expected는 '최신일자 vs 기대거래일' 대조용 인자(향후 W2 collect에서 활용).
    W1에서는 rows==0 가드가 핵심이며 날짜 불일치는 호출측 책임으로 둔다.
    """
    if rows == 0:
        raise EmptyResponseError("행수 0 — 조용한 실패")


def retry(times: int = 3, backoff: float = 1.5) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """@retry(3) — 지수 백오프. 마지막 실패는 raise (collect가 종목 단위로 격리)."""

    def deco(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def wrapper(*args: object, **kwargs: object) -> T:
            last: Exception | None = None
            for attempt in range(times):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:  # noqa: BLE001 — 마지막 시도면 재raise
                    last = e
                    if attempt < times - 1:
                        time.sleep(backoff ** attempt)
            assert last is not None
            raise last

        return wrapper

    return deco
```

| 심볼 | 파라미터 | 반환 | 예외 |
|---|---|---|---|
| `EmptyResponseError` | — | — | Exception 서브클래스 |
| `validate_response` | `rows: int, latest: str, expected: str` | `None` | `rows==0` → `EmptyResponseError` |
| `retry` | `times: int = 3, backoff: float = 1.5` | 데코레이터 | 마지막 시도 실패 시 원 예외 re-raise |

> **시그니처 고정**: `validate_response`는 `(rows:int, latest:str, expected:str)`. `df_or_obj`/`context`/키워드전용 형태 **아님**(orchestration §2.7이 v1을 정정). 변형 금지.
> `retry`의 `time.sleep`은 테스트에서 `monkeypatch`로 무력화(6.1 B2)해 느려지지 않게 한다.

### 4.2 BAL-12가 소비하는 의존 시그니처 (정의는 타 이슈 소유 — 호출만)

```python
# BAL-8 (db.py) — 인메모리/파일 SQLite
def connect(db_path: str = "data/ballast.db") -> sqlite3.Connection   # row_factory=Row, PRAGMA FK/WAL/busy_timeout (05 §0)
def init_schema(conn) -> None                                          # 9테이블 + 인덱스 ②④ + settings seed (05 §1, §15.5)
def upsert_price(conn, row: OHLCV) -> None   # frozen dataclass → 내부 asdict→named bind (05 §4.1 ON CONFLICT)
def upsert_funda(conn, row: Funda) -> None
def latest_price(conn, ct: str) -> sqlite3.Row | None    # 05 §3.1 MAX(trade_date)
def latest_funda(conn, ct: str) -> sqlite3.Row | None    # 05 §3.2

# BAL-11 (sources/kr.py)
class KrSource:
    def ohlcv(self, ct: str) -> OHLCV          # close_raw/close_adj/week52_high/week52_low/sma200 실수치
    def fundamentals(self, ct: str) -> Funda   # per/pbr/div_yield/per_pctile_5y

# models.py (orchestration §2.4, 04 §4.2) — 첫 필드 canonical_ticker
@dataclass(frozen=True) class OHLCV: canonical_ticker; trade_date; close_raw; close_adj; ccy; week52_high; week52_low; sma200
@dataclass(frozen=True) class Funda: canonical_ticker; trade_date; per; pbr; div_yield; per_pctile_5y; pbr_pctile_5y; report_date
```

> **upsert 인자형**: frozen dataclass(`OHLCV`/`Funda`)를 그대로 넘긴다. caller(BAL-12 E2E)가 dict로 변환하지 않는다(orchestration §2.1 결정).
> `latest_*`는 `sqlite3.Row`라 컬럼 접근은 `row["close_raw"]`처럼 키 인덱싱.

---

## 5. 엣지 & 리스크

- **가드 생성 순서**: `sources/__init__.py`를 BAL-11보다 먼저 만들지 않으면 `kr.py`의 `from app.sources import retry, validate_response, EmptyResponseError`가 ImportError. → 단계 A를 최우선(orchestration §3 W-2a).
- **`validate_response`의 latest/expected 미사용**: W1 본체는 `rows==0`만 강제한다. 날짜 일치 검사(±허용)는 04 §7.1이 명시하나 W2 collect의 `validate_response(rows=1, latest=ohlcv.trade_date, expected=...)` 호출지점에서 의미를 가진다. W1에서 날짜 로직을 넣으면 거래일 모킹 부담이 생기므로 **rows 가드만** 구현(과설계 금지). → 미해결 질문 1.
- **E2E 네트워크 비결정성**: pykrx/FDR/네이버 실호출은 테스트에서 금지(스타일 규칙). `KrSource.ohlcv`/`fundamentals` 내부의 데이터 fetch 경계를 `monkeypatch`로 모킹해 결정적 `OHLCV`/`Funda`를 반환시킨다. 실제 네트워크 스모크는 DoD의 `python -c "..."` 수동 1회(아래 7)로 별도 수행.
- **인메모리 DB와 WAL**: `connect(":memory:")`에서 `PRAGMA journal_mode=WAL`은 무시되거나 memory 모드로 동작 — 단위테스트엔 영향 없음. E2E는 인메모리로 충분.
- **frozen dataclass upsert**: `db.upsert_*`가 `dataclasses.asdict` 후 named-bind한다는 전제. dataclass 필드명 ↔ 테이블 컬럼명이 1:1이어야 한다(`OHLCV.close_raw`→`price_snapshot.close_raw`). 불일치는 BAL-8 책임이나 E2E가 실패로 잡아낸다(통합 증명의 목적).
- **`retry` 마지막 시도 백오프**: 마지막 시도 후엔 sleep하지 않는다(불필요 지연). 위 구현은 `attempt < times-1`로 처리.
- **빈 응답을 `[]`로 받는 headlines와 혼동 금지**: `validate_response`는 시세/펀더(0행=실패)에만 적용. 뉴스 빈응답은 정상(`[]`)이라 가드 미적용(orchestration §2.5). BAL-12 가드테스트는 headlines를 다루지 않는다.

---

## 6. 테스트 계획 (pytest, 어댑터 = 모킹)

> 마커: `@pytest.mark.unit`(가드·tickers) / `@pytest.mark.integration`(E2E). 네트워크 전부 모킹. `time.sleep`은 monkeypatch.

### 6.1 `tests/test_sources_guard.py` — 가드 단위 (단계 B, 의존 최소)

```python
import pytest
from app.sources import EmptyResponseError, retry, validate_response


@pytest.mark.unit
def test_validate_response_raises_on_empty() -> None:
    # rows == 0 → EmptyResponseError (05 §1.8 OK=데이터 실재)
    with pytest.raises(EmptyResponseError):
        validate_response(rows=0, latest="2026-06-01", expected="2026-06-01")


@pytest.mark.unit
def test_validate_response_passes_on_nonempty() -> None:
    # rows > 0 → None (예외 없음)
    assert validate_response(rows=1, latest="2026-06-01", expected="2026-06-01") is None


@pytest.mark.unit
def test_retry_reraises_after_exhausting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.sources.time.sleep", lambda *_: None)  # 백오프 즉시
    calls = {"n": 0}

    @retry(times=3)
    def always_fail() -> None:
        calls["n"] += 1
        raise ValueError("boom")

    with pytest.raises(ValueError):
        always_fail()
    assert calls["n"] == 3  # 정확히 times회 시도


@pytest.mark.unit
def test_retry_succeeds_after_transient(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.sources.time.sleep", lambda *_: None)
    calls = {"n": 0}

    @retry(times=3)
    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 2:
            raise ValueError("transient")
        return "ok"

    assert flaky() == "ok"
    assert calls["n"] == 2
```

### 6.2 `tests/test_tickers.py` — to_source 변환표 (단계 C, 04 §5.1 표)

```python
import pytest
from app.tickers import to_source


@pytest.mark.unit
@pytest.mark.parametrize(
    "source, ct, market, expected",
    [
        ("yf", "005930", "KR", "005930.KS"),
        ("finnhub", "005930", "KR", "005930.KS"),
        ("stooq", "005930", "KR", "005930.KS"),
        ("pykrx", "005930", "KR", "005930"),
        ("yf", "VOO", "US", "VOO"),
        ("finnhub", "VOO", "US", "VOO"),
        ("stooq", "VOO", "US", "voo.us"),
        ("yf", "BRK.B", "US", "BRK-B"),
        ("finnhub", "BRK.B", "US", "BRK-B"),
        ("stooq", "BRK.B", "US", "brk-b.us"),
    ],
)
def test_to_source_table(source: str, ct: str, market: str, expected: str) -> None:
    assert to_source(source, ct, market) == expected
```

> 표 출처 = 04 §5.1(`005930.KS`/`voo.us`/`BRK-B`/`brk-b.us`)·orchestration §2.2. `fdr`/`fmp`/`dart` 케이스는 04 §5.1 표에 명시값이 없어 W1 변환표 테스트에서 제외(추측 금지). KOSDAQ `.KQ`는 W2(다종목)로 유보(orchestration §2.2 known limitation).

### 6.3 `tests/conftest.py` — 인메모리 DB 픽스처 (단계 D1)

```python
import pytest
from app import db


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.init_schema(c)
    yield c
    c.close()
```

### 6.4 `tests/test_e2e_005930.py` — 적재 E2E (단계 D, 어댑터 모킹)

```python
import pytest
from app.db import latest_funda, latest_price, upsert_funda, upsert_price
from app.models import Funda, OHLCV
from app.sources.kr import KrSource


@pytest.fixture
def fake_ohlcv() -> OHLCV:
    return OHLCV(
        canonical_ticker="005930", trade_date="2026-06-01",
        close_raw=81000.0, close_adj=81000.0, ccy="KRW",
        week52_high=88000.0, week52_low=68000.0, sma200=75000.0,
    )


@pytest.fixture
def fake_funda() -> Funda:
    return Funda(
        canonical_ticker="005930", trade_date="2026-06-01",
        per=14.2, pbr=1.3, div_yield=2.1,
        per_pctile_5y=42.0, pbr_pctile_5y=38.0, report_date="2026-03-31",
    )


@pytest.mark.integration
def test_005930_ohlcv_load_roundtrip(conn, monkeypatch, fake_ohlcv: OHLCV) -> None:
    # 어댑터 네트워크 경계 모킹 → 결정적 OHLCV (실호출 금지)
    monkeypatch.setattr(KrSource, "ohlcv", lambda self, ct: fake_ohlcv)

    ohlcv = KrSource().ohlcv("005930")          # frozen dataclass
    upsert_price(conn, ohlcv)                    # frozen dataclass 인자
    row = latest_price(conn, "005930")           # sqlite3.Row | None

    assert row is not None
    assert row["close_raw"] == 81000.0
    assert isinstance(row["week52_high"], float)
    assert isinstance(row["sma200"], float)


@pytest.mark.integration
def test_005930_funda_load_roundtrip(conn, monkeypatch, fake_funda: Funda) -> None:
    monkeypatch.setattr(KrSource, "fundamentals", lambda self, ct: fake_funda)

    funda = KrSource().fundamentals("005930")
    upsert_funda(conn, funda)
    row = latest_funda(conn, "005930")

    assert row is not None
    assert isinstance(row["per"], float)
    assert row["per_pctile_5y"] == 42.0
```

> 모킹은 `KrSource.ohlcv`/`fundamentals` **메서드 경계**에서. 어댑터 내부 pykrx/FDR 함수를 모킹하고 싶다면 BAL-11 구현의 실제 fetch 경계명에 맞춰 `monkeypatch.setattr`을 조정한다(이름은 BAL-11 소유라 본 가이드는 메서드 경계 모킹을 기본으로 둠). 실제 네트워크 검증은 DoD 수동 스모크(7)로 분리.

### 실행
```bash
python3 -m py_compile app/sources/__init__.py
pytest tests/test_sources_guard.py tests/test_tickers.py tests/test_e2e_005930.py -q
```

---

## 7. DoD (로드맵 08 Week1 + orchestration §5 인용)

orchestration §5(W1 통합 DoD) 그대로:
- [ ] `python -c "from app.sources.kr import KrSource; print(KrSource().ohlcv('005930'))"` → close_raw·52주·sma200 **실수치** (수동 네트워크 스모크 1회)
- [ ] `fundamentals('005930')` → PER/PBR/배당 + `per_pctile_5y`(5년 백필)
- [ ] `db.upsert_*` 적재 후 `latest_price(conn,'005930')` row 반환 → **6.4 E2E로 자동화**
- [ ] `tests/test_tickers.py`: to_source 변환표 전 케이스 통과 → **6.2**
- [ ] `validate_response`가 빈 응답을 `EmptyResponseError`로 올림 → **6.1**
- [ ] `pytest -q` green, 편집 파일 `py_compile` 통과

08 Week1 DoD 추가 정합(중복 항목 제외):
- [ ] `validate_response`가 빈 CSV를 OK로 오인 안 함(05 §1.8) — 6.1 `test_validate_response_raises_on_empty`로 증명

> BAL-12의 DoD = W1 슬라이스 통합 DoD(orchestration §0: 최종 산출물이 곧 통합). 따라서 BAL-8/9/11 DoD가 선행 green이어야 6.4 E2E가 통과한다.

---

## 8. Out of scope (W1 아님 — 끌려가지 말 것)

orchestration §6 + 본 이슈 경계:
- **가드 본체(소유는 BAL-12지만 import는 BAL-11)** 외의 어댑터 로직 — `KrSource.ohlcv`/`fundamentals` 구현은 BAL-11 소유. BAL-12는 모킹해 소비만.
- `validate_response`의 **날짜 일치(latest vs expected ±허용) 검사** — W2 collect 호출지점에서 의미. W1은 rows 가드만.
- **headlines/regime 가드** — 뉴스 빈응답=`[]` 정상(가드 미적용), regime은 별도 `sources/regime.py`(BAL-48). BAL-12 범위 밖.
- US/FX 어댑터·`upsert_fx`·collect 배치·백필·metrics 계산·LLM/Card DTO·프론트 — 전부 W2+ (orchestration §6).
- `db.py`/`tickers.py`/`kr.py`/`models.py` **본체 구현·리팩토링** — 각각 BAL-8/9/11 소유. BAL-12는 시그니처 소비/검증만.

---

## 부록 — 정합성 노트 (정본 교차검증 결과)
- `validate_response(rows, latest, expected) -> None` / `rows==0→EmptyResponseError`: 04 §7.1(L454-459)·05 §1.8(L209)·orchestration §2.7 일치. ✅
- `retry(times=3, backoff=1.5)`: 04 §7.1(L451)·orchestration §2.7 일치. ✅
- `upsert_price/funda(conn, row: OHLCV/Funda)` frozen dataclass 인자: orchestration §2.1 결정(L57-63). 04 §8.2는 `db.upsert_price(ohlcv)` 호출형으로 정합. ✅
- `latest_price/funda(conn, ct) -> sqlite3.Row | None`: 04 §3.2(L175-180)·05 §3.1-3.2·orchestration §2.1 일치. ✅
- `OHLCV`/`Funda` 첫 필드 `canonical_ticker`: 04 §4.2(L242,253)·§15.2·orchestration §2.4 일치(v1 `OHLCV.ct` 오류 정정됨). ✅
- to_source 표(`005930.KS`/`voo.us`/`BRK-B`/`brk-b.us`): 04 §5.1(L362-368)·orchestration §2.2 일치. ✅
- §15(TECH-DESIGN)와 모순 없음: §15.2 DTO·§15.4 status·§15.5 settings 모두 04/05와 정합. ✅

---
> 📌 본 가이드의 "미해결 질문"은 **전건 해소됨** → `docs/BAL-1-m1a-decisions.md` (유보 0건). 시그니처 정본 = orchestration §2 v2.
