# BAL-9 개발 가이드 — `app/tickers.py` (티커 변환표 · 코어 ETF 화이트리스트 · category 분류)

> 정본 우선순위: `TECH-DESIGN.md §15` > `docs/04-backend.md §5.1/§5.2/§5.3` > `docs/05-database.md §1.1`. seam 시그니처 정본 = `docs/BAL-1-m1a-orchestration.md §2.2(v2)`.
> 본 가이드의 "확정 시그니처"는 canonical 검증을 마친 정본이다. **그대로 사용**하라 — 시그니처 드리프트는 이미 해소됨(임의 변형/발명 금지).
> 범위: W1 (Wave-1), BAL-8/BAL-10과 **3-way 진짜 병렬**(파일 비중복, 충돌 0).

---

## 1. 목표 & 배경 (W1 슬라이스 내 역할 / 의존)

`app/tickers.py`는 W1 데이터 스파이크의 **3 격리 foundation 모듈** 중 하나다(나머지: `db.py`=BAL-8, `calendar.py`=BAL-10). 의존이 없어 BAL-8/10과 동시 착수 가능하며, W2의 consumer(`sources/kr.py`=BAL-11)가 이 모듈을 import 한다.

세 가지 책임:

1. **`to_source(source, ct, market)`** — `holdings.canonical_ticker`(예 `005930`, `VOO`, `BRK.B`)를 데이터 소스가 요구하는 표기로 변환. 모든 캐시 PK는 canonical 기준이라(`05 §0`·`§14`), 소스별 표기차(`005930.KS` vs `005930`)로 시계열이 갈라지지 않게 하는 **단일 변환 지점**. W2의 `KrSource.ohlcv/fundamentals`가 `to_source('pykrx'|'fdr', ct, 'KR')`로 호출한다(`BAL-1 §2.5`).
2. **`CORE_ETF_WHITELIST: frozenset[str]`** — G4 코어 ETF 화이트리스트(코드 상수). 광범위 지수 ETF만 `core`로 인정, 섹터·테마·레버리지·액티브 ETF는 제외해 satellite 한도 오염을 막는다(`04 §5.2`).
3. **`classify_category(h)`** — `HoldingInput`을 받아 `core`/`satellite`/`None`을 판정. `POST /holdings` 저장 직전 1회 호출되어 결과가 `holdings.category`에 영속화된다(`04 §5.3`·`05 §1.1` G4 — 매 계산 재판정 비용 회피).

> 현재 파일은 W0 스텁(docstring 1줄)이다: `/Users/pyeondohun/development/thinking/investbrief/app/tickers.py`.

### W1 슬라이스 내 위치 (`BAL-1 §1` DAG)
```
BAL-8  db.py       ─┐
BAL-9  tickers.py  ─┼─► BAL-11 sources/kr.py ─► BAL-12 validate + 005930 E2E
BAL-10 calendar.py ─┘
```

---

## 2. 영향 파일

| 파일 | 변경 | 비고 |
|---|---|---|
| `/Users/pyeondohun/development/thinking/investbrief/app/tickers.py` | **구현**(W0 스텁 → 본체) | 본 이슈 핵심 산출물 |
| `/Users/pyeondohun/development/thinking/investbrief/app/models.py` | **선행 의존** | `classify_category`가 `HoldingInput`을 받음 → `tickers.py`가 `from app.models import HoldingInput`. `models.py`는 W1 부분 기여로 `HoldingInput`(mutable) 정의 필요(`04 §4.1`, `BAL-1 §2.4`). 이미 정의돼 있지 않으면 **본 작업의 선행 조건**으로 최소 정의(아래 §3 단계 0 참조) |
| `/Users/pyeondohun/development/thinking/investbrief/tests/test_tickers.py` | **신규** | to_source 변환표 + whitelist + classify를 못박는 테스트 |

> `models.py` 전량(LLM/Card DTO 등)은 W3 범위다. W1은 `HoldingInput`만 필요. BAL-8(`db.py`)도 `OHLCV/Funda` 등 frozen DTO를 필요로 하므로, `models.py`는 W1에서 BAL-8·BAL-9가 함께 닿는 공유 파일이다 — **병렬 충돌 주의**(아래 §5 리스크).

---

## 3. 구현 단계 (하위작업 / 자체분해 단위 · 검증 포인트)

### 단계 0 — `models.HoldingInput` 존재 확인 (선행)
- `models.py`에 `HoldingInput`이 정의돼 있는지 확인. 없으면 `04 §4.1` 그대로 최소 정의(첫 필드 `instrument`, `category`는 마지막 직전, 전부 mutable `@dataclass`).
- **검증**: `python3 -c "from app.models import HoldingInput; print(HoldingInput(instrument='etf', name='x'))"` 동작.

### 단계 1 — `to_source` 구현
- 시그니처(§4.1)대로 `source` 리터럴 분기 + `market` 분기로 변환표(§4.1 표)를 구현.
- KR(`market=='KR'`): `yf/finnhub/stooq`는 `{ct}.KS` 접미(KOSPI 가정), `pykrx`는 `ct` 그대로(6자리).
- US(`market=='US'`): `yf/finnhub`는 점→하이픈 정규화 후 대문자(`BRK.B`→`BRK-B`, `VOO`→`VOO`), `stooq`는 소문자 + `.us` 접미 + 점→하이픈(`VOO`→`voo.us`, `BRK.B`→`brk-b.us`).
- `fdr`(KR)·`fmp`(US)·`dart`(KR)는 정본 표에 명시 케이스가 없으나 시그니처 리터럴에 포함됨 → **§미해결 질문 1** 참조(현재 결정: `fdr`=pykrx와 동일(6자리 그대로), `dart`=6자리, `fmp`=canonical 그대로 대문자 — 보수적 기본값).
- **검증**: `python3 -m py_compile app/tickers.py` + 단계 1 테스트(아래 §6) green.

### 단계 2 — `CORE_ETF_WHITELIST` 상수
- `04 §5.2` 9개 티커를 `frozenset[str]`으로 정의(069500/360750/379800/VOO/SPY/VTI/IVV/ITOT/VT). 주석으로 "섹터·테마·레버리지·액티브 제외" 명시.
- **검증**: 멤버십 테스트(`"069500" in CORE_ETF_WHITELIST`, `"TQQQ" not in ...`) green.

### 단계 3 — `classify_category` 구현
- 우선순위(§4.3): ① `h.category is not None` → 그대로 반환 ② `instrument=="stock"` → `"satellite"` ③ `instrument=="etf"` → whitelist 매칭 시 `"core"` 아니면 `None` ④ 그 외(cash 등) → `None`.
- **검증**: 4분기 + 우선순위 충돌(사용자가 satellite ETF를 core로 명시) 테스트 green.

### 단계 4 — 통합 검증
- `pytest -q tests/test_tickers.py` green, `python3 -m py_compile app/tickers.py` 통과, black/isort/ruff clean.

---

## 4. 인터페이스 (확정 시그니처 구체화)

### 4.1 `to_source`
```python
from typing import Literal

def to_source(
    source: Literal["yf", "finnhub", "stooq", "pykrx", "fdr", "fmp", "dart"],
    ct: str,
    market: str,
) -> str:
    ...
```
- **파라미터**: `source` = 데이터 소스 키(7종 리터럴). `ct` = canonical ticker(`005930`/`VOO`/`BRK.B`). `market` = `"KR"` 또는 `"US"`(현재 `str` 정본; 04/seam이 `str`로 둠 — Literal 좁히지 말 것).
- **반환**: 소스별 표기 문자열.
- **변환표(검증 가능 — test_tickers.py가 못박음)**:

| canonical (market) | yf | finnhub | stooq | pykrx |
|---|---|---|---|---|
| `005930` (KR) | `005930.KS` | `005930.KS` | `005930.KS` | `005930` |
| `VOO` (US) | `VOO` | `VOO` | `voo.us` | — |
| `BRK.B` (US) | `BRK-B` | `BRK-B` | `brk-b.us` | — |

> seam v2(`BAL-1 §2.2`) 예시 `to_source('stooq','VOO','US')->'voo.us'`, `to_source('finnhub','BRK.B','US')->'BRK-B'`, `to_source('yf','005930','KR')->'005930.KS'`와 일치. (TECH-DESIGN §189의 2-arg narrative 표기는 서술용 약식 — 정본 시그니처는 04 §5.1/seam §2.2의 3-arg. 이 드리프트는 이미 해소됨.)
- **예외/엣지**: KR은 `005930=KOSPI(.KS)`로 진행. KOSDAQ(`.KQ`) 서브마켓은 `market='KR'`만으로 구분 불가 → **W2로 유보(known limitation)**, 본 이슈에서 `.KQ` 분기 구현하지 않음. 미지원 `source`/`market` 조합 처리 정책은 **§미해결 질문 2**.

### 4.2 `CORE_ETF_WHITELIST`
```python
CORE_ETF_WHITELIST: frozenset[str] = frozenset({
    "069500",  # KODEX 200
    "360750",  # TIGER 미국S&P500
    "379800",  # KODEX 미국S&P500TR
    "VOO", "SPY", "VTI", "IVV", "ITOT", "VT",
})
# 섹터·테마·레버리지·액티브 ETF 포함 금지 (한도 오염 방지, 04 §5.2 / SSoT §6).
```
- **타입**: `frozenset[str]`(immutable 상수). canonical ticker(KR=6자리, US=심볼) 그대로.

### 4.3 `classify_category`
```python
from app.models import HoldingInput

def classify_category(h: HoldingInput) -> Literal["core", "satellite"] | None:
    if h.category is not None:        # 1) 사용자 명시 우선
        return h.category
    if h.instrument == "stock":       # 2) 개별주 → satellite
        return "satellite"
    if h.instrument == "etf":         # 3) ETF: 화이트리스트 매칭만 core, 아니면 None(="확인 필요")
        return "core" if h.canonical_ticker in CORE_ETF_WHITELIST else None
    return None                       # 4) cash 등 → None
```
- **파라미터**: `h: HoldingInput`(`models.py §4.1`, **mutable** dataclass). 읽는 필드 = `h.category`, `h.instrument`, `h.canonical_ticker`.
- **반환**: `"core"` | `"satellite"` | `None`(`None`="확인 필요", `holdings.category` NULL로 영속).
- **예외**: 없음(순수 함수, 분기로 전체 입력 커버). `h.canonical_ticker is None`(cash 등 등록 ETF가 아닌 행)이어도 ① `etf` 분기는 `None in frozenset` → `False` → `None` 반환으로 안전. instrument enum 외 값은 어느 분기에도 안 걸려 `None` 반환(방어적) — **§미해결 질문 3**.

---

## 5. 엣지 & 리스크

| # | 엣지/리스크 | 처리 |
|---|---|---|
| E1 | KOSPI/KOSDAQ 구분 불가(`market='KR'`만으로 `.KS`/`.KQ` 결정 불가) | `005930=KOSPI(.KS)`로 진행. KOSDAQ 서브마켓 해소는 **W2 유보(known limitation)** — `BAL-1 §2.2` 결정 그대로 |
| E2 | `BRK.B`류 점-포함 티커 | yf/finnhub=점→하이픈(`BRK-B`), stooq=소문자+하이픈+`.us`(`brk-b.us`). 변환표 정본 |
| E3 | 정본 표 미명시 source(`fdr`/`fmp`/`dart`) | 보수적 기본값(§3 단계 1). 실제 적재는 W2(BAL-11) — `fdr`/`pykrx`만 KR 어댑터가 사용(`BAL-1 §2.5`). `dart`/`fmp` 미사용 케이스는 **§미해결 질문 1** |
| E4 | satellite ETF를 사용자가 `category='core'`로 명시 | 우선순위 ①이 사용자값을 신뢰(반환 `core`) — 의도된 동작(`04 §5.3` "사용자 명시 우선") |
| **R1** | **`models.py` 병렬 충돌**: BAL-8(db.py)도 `OHLCV/Funda` 등 DTO를 `models.py`에 추가 → 같은 파일 동시 편집 | W1 3-way 병렬에서 `models.py`만 공유. **권장**: `models.py`의 `HoldingInput`만 먼저 단독 커밋하거나, BAL-9는 `HoldingInput` 블록만 편집(다른 DTO 영역 비접촉)해 머지 충돌 최소화. `BAL-1 §2.4`가 W1 기여 DTO 목록을 명시 |
| R2 | `from app.models import HoldingInput`가 순환 import 유발? | `models.py`는 `tickers.py`를 import 하지 않음(단방향) → 순환 없음. 안전 |
| R3 | `market` 대소문자 변형(`'kr'`) | 정본은 `"KR"`/`"US"` 대문자 입력 가정(holdings CHECK가 `'KR','US'`만 허용, `05 §1.1`). 소문자 정규화는 범위 밖 |

---

## 6. 테스트 계획 (`tests/test_tickers.py` · pytest, 어댑터=모킹)

- **외부 네트워크 없음**: `tickers.py`는 순수 변환 로직이라 모킹 불필요(W1 foundation의 장점). 어댑터 모킹은 W2(BAL-11)에서 적용.
- `pytest.mark.unit` 마커 사용(`pytest.ini`에 등록됨). black/isort/ruff 통과.

```python
import pytest
from app.models import HoldingInput
from app.tickers import to_source, classify_category, CORE_ETF_WHITELIST


# --- to_source 변환표 (못박기) ---
@pytest.mark.unit
@pytest.mark.parametrize("source,ct,market,expected", [
    # KR (005930 = KOSPI .KS)
    ("yf",      "005930", "KR", "005930.KS"),
    ("finnhub", "005930", "KR", "005930.KS"),
    ("stooq",   "005930", "KR", "005930.KS"),
    ("pykrx",   "005930", "KR", "005930"),
    # US — VOO
    ("yf",      "VOO", "US", "VOO"),
    ("finnhub", "VOO", "US", "VOO"),
    ("stooq",   "VOO", "US", "voo.us"),
    # US — BRK.B (점 포함)
    ("finnhub", "BRK.B", "US", "BRK-B"),
    ("yf",      "BRK.B", "US", "BRK-B"),
    ("stooq",   "BRK.B", "US", "brk-b.us"),
])
def test_to_source_conversion_table(source, ct, market, expected):
    assert to_source(source, ct, market) == expected


# --- CORE_ETF_WHITELIST ---
@pytest.mark.unit
def test_whitelist_members():
    assert CORE_ETF_WHITELIST == frozenset({
        "069500", "360750", "379800", "VOO", "SPY", "VTI", "IVV", "ITOT", "VT",
    })

@pytest.mark.unit
def test_whitelist_excludes_sector_leverage():
    for t in ("TQQQ", "SOXL", "ARKK", "KODEX2X"):
        assert t not in CORE_ETF_WHITELIST


# --- classify_category 4분기 + 우선순위 ---
def _h(**kw):
    base = dict(instrument="etf", name="x", canonical_ticker=None, category=None)
    base.update(kw)
    return HoldingInput(**base)

@pytest.mark.unit
def test_classify_user_override_wins():
    # satellite ETF지만 사용자가 core 명시 → core
    assert classify_category(_h(instrument="etf", canonical_ticker="TQQQ", category="core")) == "core"

@pytest.mark.unit
def test_classify_stock_is_satellite():
    assert classify_category(_h(instrument="stock", canonical_ticker="005930")) == "satellite"

@pytest.mark.unit
def test_classify_etf_whitelist_is_core():
    assert classify_category(_h(instrument="etf", canonical_ticker="VOO")) == "core"

@pytest.mark.unit
def test_classify_etf_not_whitelist_is_none():
    assert classify_category(_h(instrument="etf", canonical_ticker="TQQQ")) is None

@pytest.mark.unit
def test_classify_cash_is_none():
    assert classify_category(_h(instrument="cash", canonical_ticker=None)) is None
```

> `_h` 헬퍼의 `HoldingInput(**base)` 키워드는 `04 §4.1` 필드명과 일치해야 함(`instrument`/`name`/`canonical_ticker`/`category`). 다른 필수 필드가 default 없으면 헬퍼에 추가.

---

## 7. DoD (로드맵 08 Week1 + `BAL-1 §5`)

`docs/BAL-1-m1a-orchestration.md §5` 인용 — 본 이슈가 닿는 항목:
- [ ] **`tests/test_tickers.py`: to_source 변환표 전 케이스 통과** (`§5` 4번째 게이트 / `§3` W-1 게이트 "tickers: to_source 변환표 테스트 green")
- [ ] `pytest -q` green, 편집 파일 `py_compile` 통과 (`§5` 마지막 게이트)

본 이슈 자체 DoD:
- [ ] `to_source` 변환표 9 케이스(KR 4 + US 5) green
- [ ] `CORE_ETF_WHITELIST` = 정확히 9개 멤버(`04 §5.2` 정본), 섹터/레버리지 제외 검증 green
- [ ] `classify_category` 4분기 + 우선순위 충돌 케이스 green
- [ ] `from app.models import HoldingInput` 동작(순환 import 없음)
- [ ] black/isort/ruff clean, 전 함수 시그니처 타입주석

---

## 8. Out of scope (W1 아님 — 끌려가지 말 것)

- **KOSDAQ `.KQ` 서브마켓 분기**(W2 유보, known limitation — `BAL-1 §2.2`).
- **`fdr`/`fmp`/`dart` 소스의 실제 변환 검증** — 본 이슈는 정본 표(yf/finnhub/stooq/pykrx) 4종만 못박는다. US 어댑터(`fmp`)·DART는 W2+.
- **다종목 입력·실데이터 적재**(`KrSource.ohlcv` 등 = BAL-11/W2).
- **`category`의 DB 영속화 SQL**(`POST /holdings` upsert = `04 §1.4`/`main.py`, W3+). 본 이슈는 판정 함수만 제공.
- `models.py`의 LLM/Card DTO·FxRate(W2+), metrics·collect·frontend(W2~W5).
