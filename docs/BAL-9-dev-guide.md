# BAL-9 dev-guide — `app/tickers.py`: 변환표·코어 ETF 화이트리스트·분류

> SSoT 우선순위: `TECH-DESIGN.md §15`(Contract SoT) > `docs/05-database.md` / `docs/04-backend.md`.
> **시그니처 정본 = `docs/BAL-1-m1a-orchestration.md §2.2`** (seam 계약 표). 본 가이드는 그 표를 그대로 가져와 구체화한다.
> 범위: W1(BAL-1 슬라이스) 중 BAL-9 단일 이슈. 외부 네트워크 의존 0 → 순수 단위테스트로 완전 못박는다.

---

## 1. 목표 & 배경

**이슈 요약.** `app/tickers.py`는 BAL-1(M1a 데이터 스파이크) 수직 슬라이스의 **격리 foundation 3종**(BAL-8 db / BAL-9 tickers / BAL-10 calendar) 중 하나다. 책임은 세 가지로 자체 분해된다.

1. `to_source` — canonical 티커를 데이터 소스별 표기로 변환 (`005930`→`005930.KS`, `BRK.B`→`BRK-B` 등). 캐시 PK는 항상 canonical이고, 변환은 **소스 호출 직전에만** 쓰인다(05 §0 "캐시 PK는 항상 canonical_ticker 기준").
2. `CORE_ETF_WHITELIST` — G4 코어 ETF 화이트리스트(코드 상수 `frozenset`). 한도 오염 방지를 위해 광범위 지수 ETF만 포함(04 §5.2, 05 §1.1 G4 노트).
3. `classify_category` — 보유 종목을 `'core'`/`'satellite'`/`None`(확인 필요)으로 분류(G4).

**W1 슬라이스 내 역할/의존.**

- **의존: 없음**(BAL-9는 db/calendar와 파일 비중복, 충돌 0). orchestration §1 DAG 기준 BAL-8·9·10은 Wave-1에서 **진짜 3-way 병렬** 대상.
- **소비자: BAL-11 `app/sources/kr.py`**(Wave-2). `KrSource`가 내부에서 `tickers.to_source`를 호출해 pykrx/FDR 호출용 심볼을 만든다(orchestration §2.5 "내부: tickers.to_source, calendar.expected_trade_date 사용").
- **소비자: `POST /holdings` 저장 경로**(W1 범위 밖이지만 `classify_category`/`CORE_ETF_WHITELIST`의 최종 호출처. 04 §5.3 — 저장 직전 1회 판정 후 `holdings.category`에 영속화).

**왜 W1에서 강하게 못박나.** BAL-9는 외부 의존이 전혀 없는 순수 계산 모듈이라 단위테스트로 100% 결정적 검증이 가능하다. orchestration §3 Wave-1 게이트가 명시적으로 "tickers: to_source 변환표 테스트 green"을 산출 게이트로 요구한다(§5 DoD에도 `tests/test_tickers.py: to_source 변환표 전 케이스 통과`).

---

## 2. 영향 파일

| 파일 | 작업 | 내용 |
|---|---|---|
| `app/tickers.py` | **수정**(현재 W0 스텁: docstring 1줄) | `to_source`, `CORE_ETF_WHITELIST`, `classify_category` 구현 |
| `tests/test_tickers.py` | **신규** | 변환표 파라미터라이즈드 + 화이트리스트 + 분류 우선순위 단위테스트 |

> 다른 파일은 건드리지 않는다. `app/models.py`(HoldingInput)·`app/sources/kr.py`는 BAL-9 범위가 아니다. `classify_category` 입력 타입 결정에 따른 import 영향은 §8 미해결 질문 Q2 참조.

---

## 3. 구현 단계

> 각 단계는 외부 의존이 없으므로 **편집 → `python3 -m py_compile app/tickers.py` → 해당 단위테스트 green** 루프로 검증한다(orchestration §4 degraded-session: compile-check 수동 실행).

### 단계 1 — `to_source` 변환표

**핵심 로직.** canonical 티커를 소스 표기로 정규화한다. 변환 규칙의 정본 케이스(04 §5.1 표 + 05 §0)는 다음과 같다.

- KR 6자리 숫자 종목: 거래소 접미 부착이 필요한 소스(yf/finnhub/stooq)는 KOSPI=`​.KS`, KOSDAQ=`​.KQ`; pykrx는 6자리 **그대로**.
- US 일반: 대부분 소스는 그대로(`VOO`→`VOO`), stooq는 소문자+`.us`(`voo.us`).
- US 점(`.`) 포함 클래스주: yf/finnhub는 `.`→`-`(`BRK.B`→`BRK-B`), stooq는 `brk-b.us`.

**검증 포인트.**
- `to_source('005930', market='KR')`가 §2.2 케이스(`005930`→`005930.KS`)와 일치.
- `to_source('BRK.B', market='US')`가 §2.2 케이스(`BRK.B`→`BRK-B`)와 일치.
- ⚠️ **시그니처/표 구조 불일치(반드시 §8 Q1 확인 후 진행).** §2.2 정본 시그니처는 `to_source(canonical, market=None) -> str`로 **source 인자가 없다**. 그러나 04 §5.1의 변환표는 **소스별로 출력이 다르다**(yf `005930.KS` vs stooq `005930.KS` vs pykrx `005930`; `VOO` vs `voo.us`). 2-인자 시그니처로는 이 소스 분기를 표현할 수 없다 → 본문에서 임의로 source 인자를 추가하지 **않는다**. Q1 해소 전까지는 §2.2 시그니처(2-인자)를 정본으로 두고, 단위테스트는 §2.2가 명시한 케이스(KS 접미, BRK-B)만 못박는다(아래 §6 표의 "§2.2 확정" 행).

### 단계 2 — `CORE_ETF_WHITELIST`

**핵심 로직.** 04 §5.2 정본을 그대로 `frozenset[str]` 상수로 둔다(KR: `069500`, `360750`, `379800` / US: `VOO`, `SPY`, `VTI`, `IVV`, `ITOT`, `VT`). 섹터·테마·레버리지·액티브 ETF는 **포함 금지**(한도 오염 방지, 05 §1.1 G4 노트).

**검증 포인트.**
- 타입이 `frozenset`이고 불변(mutation `AttributeError`).
- 04 §5.2의 9개 심볼이 정확히 포함, 그 외 심볼(예: `QQQ`, `SOXL`)은 미포함.
- 멤버십 키는 canonical 표기(`VOO`, `069500`)와 일치 — `to_source` 변환 전 값으로 조회.

### 단계 3 — `classify_category`

**핵심 로직(우선순위, 04 §5.3 / 05 §1.1 G4 노트).**
1. 사용자 명시 category가 있으면 그 값 우선.
2. 개별주(stock) → `'satellite'`.
3. ETF → canonical이 `CORE_ETF_WHITELIST`에 있으면 `'core'`, 아니면 `None`(="확인 필요").
4. 그 외(cash 등) → `None`.

**검증 포인트.**
- 화이트리스트 ETF → `'core'`, 비화이트리스트 ETF → `None`.
- stock → `'satellite'`.
- ⚠️ **시그니처 불일치(§8 Q2).** §2.2 정본은 `classify_category(ticker: str, instrument: str) -> str | None`이다. 그러나 04 §5.3은 `classify_category(h: HoldingInput) -> ...`로 **사용자 명시 우선(`h.category`) 분기**를 포함한다. §2.2의 `(ticker, instrument)` 2-인자에는 사용자 override 입력 슬롯이 없다 → §2.2 시그니처를 정본으로 두면 우선순위 1(사용자 명시)을 이 함수가 직접 수행할 수 없다. 임의로 인자를 추가하거나 `HoldingInput`을 받도록 바꾸지 **않는다**. Q2 해소 전까지 §2.2 시그니처를 따르고, 우선순위 2~4(stock/ETF whitelist/그외)만 본 함수에서 구현하며 "사용자 명시 우선"은 호출측(POST /holdings) 책임으로 둔다(이 분기 위치는 Q2에서 확정).

---

## 4. 인터페이스

> **정본 = orchestration §2.2.** 아래는 §2.2를 그대로 옮기고 파라미터/반환/예외만 구체화한 것이다. 새 시그니처를 발명하지 않는다. §2.2와 04(§5.1/§5.3)의 불일치는 §8 미해결 질문으로 분리했다.

```python
def to_source(canonical: str, market: str | None = None) -> str:
    """canonical 티커를 데이터 소스 표기로 변환. (orchestration §2.2 / 04 §5.1)

    예(§2.2 정본 케이스):
      to_source('005930', 'KR') -> '005930.KS'
      to_source('BRK.B', 'US')  -> 'BRK-B'
    """

CORE_ETF_WHITELIST: frozenset[str]
    # G4 코어 ETF 화이트리스트 (04 §5.2 정본 9종). 광범위 지수 ETF만.

def classify_category(ticker: str, instrument: str) -> str | None:
    """보유 종목 카테고리 분류. (orchestration §2.2 / 04 §5.3)
       반환: 'core' | 'satellite' | None('확인 필요')
    """
```

**파라미터/반환/예외 명세.**

| 시그니처 | 파라미터 | 반환 | 예외/엣지 |
|---|---|---|---|
| `to_source(canonical, market=None)` | `canonical: str`(정규 티커), `market: str \| None`(`'KR'`/`'US'`, KR 접미 분기에 필요) | `str`(소스 표기) | KR 종목인데 `market=None`이면 접미 분기 판단 불가 → Q1·Q3 참조. 본문에 임의 예외 정책 주입 금지 |
| `CORE_ETF_WHITELIST` | — | `frozenset[str]` | 불변. 멤버십 조회는 canonical 표기 기준 |
| `classify_category(ticker, instrument)` | `ticker: str`(canonical), `instrument: str`(`'stock'`/`'etf'`/`'cash'`) | `'core'` \| `'satellite'` \| `None` | 알 수 없는 `instrument` 처리 정책 미정 → Q4 |

> 반환 타입 표기: §2.2는 `classify_category -> str | None`, 04 §5.3은 `Literal['core','satellite'] | None`. 본 가이드는 §2.2 표기(`str | None`)를 정본으로 채택하되, 구현은 `'core'`/`'satellite'`/`None`만 반환한다(§15에 tickers DTO 정의 없음 → §2 우선).

---

## 5. 엣지 & 리스크

| 엣지/리스크 | 영향 | 대응 |
|---|---|---|
| **KOSDAQ vs KOSPI 접미 구분** (`.KQ` vs `.KS`) | 04 §5.1 노트: "KOSDAQ은 `.KQ` 접미(yf/stooq)". 6자리 숫자만으로는 시장 구분 불가 | 접미 결정 입력(시장 구분)이 §2.2 시그니처에 없음 → Q3. 본문에 임의 룩업/추론 주입 금지 |
| **source별 출력 분기 불가** | 04 §5.1 표는 소스별로 다른 출력. §2.2는 source 인자 없음 | Q1. 단위테스트는 §2.2 확정 케이스만 강제, 소스별 케이스는 Q1 해소 후 추가 |
| **`classify_category` 사용자 override 누락** | 04 §5.3 우선순위 1(사용자 명시)을 §2.2 시그니처가 표현 못함 | Q2. override는 호출측 책임으로 임시 분리 |
| **빈/None canonical 입력** | `to_source('')` 또는 `classify_category(None, ...)` 동작 미정 | 입력 검증 정책 미정 → Q4. 임의 방어코드 추가 금지(§15/§2에 검증 계약 없음) |
| **알 수 없는 instrument** | `classify_category('X','bond')` 등 | G4 분류표에 없음 → `None` 반환이 자연스럽되 명시 안 됨 → Q4 |
| **빈 DF / 백필 / 휴장 / NULL percentile / 조정가 stale** | **BAL-9 무관**(이들은 sources/collect/metrics 레이어 — orchestration §2.5·§7, 05 §1.3/§1.8). tickers.py는 순수 문자열 변환·상수·분기로 외부 응답을 다루지 않음 | 본 모듈 책임 아님 → §7 Out of scope. (요청 항목이지만 BAL-9 범위에 해당 없음을 명시) |

---

## 6. 테스트 계획

**파일: `tests/test_tickers.py`** (신규). 외부 의존 0 → 전부 `@pytest.mark.unit`. 모킹 불필요(어댑터 없음). 기존 `tests/conftest.py`/`pytest.ini`(`markers: unit`) 그대로 사용.

### 6.1 `to_source` 변환표 (파라미터라이즈드) — DoD 핵심

> orchestration §5 / §3 Wave-1 게이트가 명시 요구: "to_source 변환표 전 케이스 통과".

**§2.2 확정 케이스(무조건 green이어야 함):**

| 입력 `(canonical, market)` | 기대 출력 | 근거 |
|---|---|---|
| `('005930', 'KR')` | `'005930.KS'` | §2.2 명시 케이스 |
| `('BRK.B', 'US')` | `'BRK-B'` | §2.2 명시 케이스 |

**04 §5.1 확장 케이스(Q1 해소 = source 인자 확정 후 활성화. 그 전에는 `@pytest.mark.skip(reason="Q1: source 인자 미확정")`):**

| canonical | market | yf | finnhub | stooq | pykrx |
|---|---|---|---|---|---|
| `005930` | KR | `005930.KS` | `005930.KS` | `005930.KS` | `005930` |
| `VOO` | US | `VOO` | `VOO` | `voo.us` | — |
| `BRK.B` | US | `BRK-B` | `BRK-B` | `brk-b.us` | — |

테스트 함수명:
- `test_to_source_kr_kospi_suffix` — `('005930','KR') == '005930.KS'`
- `test_to_source_us_dot_to_dash` — `('BRK.B','US') == 'BRK-B'`
- `test_to_source_table_per_source`(파라미터라이즈드, skip until Q1) — 04 §5.1 4-소스 표

### 6.2 `CORE_ETF_WHITELIST`

- `test_whitelist_is_frozenset` — `isinstance(CORE_ETF_WHITELIST, frozenset)`
- `test_whitelist_contains_core_members` — 04 §5.2의 9종 전부 포함
- `test_whitelist_excludes_non_core` — `'QQQ'`, `'SOXL'`, `'005930'`(개별주 코드 아님 확인용) 미포함
- `test_whitelist_immutable` — `add` 호출 시 `AttributeError`

### 6.3 `classify_category` (우선순위)

- `test_classify_stock_is_satellite` — `('005930','stock') == 'satellite'`
- `test_classify_core_etf` — `('VOO','etf') == 'core'`
- `test_classify_unknown_etf_is_none` — `('QQQ','etf') is None`
- `test_classify_cash_is_none` — `('','cash') is None`
- `test_classify_user_override`(Q2 해소 후) — 사용자 명시 우선 분기 위치 확정 시 추가

### 6.4 검증 명령

```bash
python3 -m py_compile app/tickers.py
pytest tests/test_tickers.py -q -m unit
```

---

## 7. DoD (Definition of Done)

> 로드맵 08 Week1 + orchestration §5 인용. BAL-9 관련 항목만 발췌.

- [ ] **(orchestration §5)** `tests/test_tickers.py`: to_source 변환표 전 케이스 통과 (§2.2 확정 케이스 = 무조건; 04 §5.1 확장 케이스 = Q1 해소 시).
- [ ] **(orchestration §3 Wave-1 게이트)** "tickers: to_source 변환표 테스트 green".
- [ ] **(orchestration §5)** `pytest -q` green, 편집 파일 `py_compile` 통과.
- [ ] `to_source` 시그니처가 §2.2 정본(`to_source(canonical, market=None) -> str`)과 일치.
- [ ] `classify_category` 시그니처가 §2.2 정본(`classify_category(ticker, instrument) -> str | None`)과 일치.
- [ ] `CORE_ETF_WHITELIST`가 04 §5.2 정본 9종과 정확히 일치하는 `frozenset[str]`.
- [ ] PEP8 + 타입주석 + (해당 시) frozen dataclass 스타일 준수, `print()` 미사용.
- [ ] §8 미해결 질문이 코드 머지 전까지 해소 또는 명시적으로 deferred 처리(임의 가정 주입 0).

---

## 8. Out of scope (W1 아님 — 끌려가지 말 것)

- **US/FX/regime 어댑터의 티커 변환 케이스 실호출** — `sources/us.py`(Stooq `.us`)·`fx.py`·`regime.py`는 W2. BAL-9는 변환 **규칙**만 제공, 어댑터가 실제로 호출하는 건 W2(orchestration §6).
- **`POST /holdings` validation·category 영속화** — `classify_category` 결과를 `holdings.category`에 저장하는 경로(04 §1.4/§5.3)는 W1 슬라이스 밖(main.py 라우트). BAL-9는 순수 분류 함수만.
- **빈 DF/백필/휴장/NULL percentile/조정가 stale 처리** — sources(BAL-11)·collect.py(W2)·metrics(W3)·calendar(BAL-10) 책임. tickers.py는 외부 응답을 다루지 않음.
- **`models.py` LLM/Card DTO** — W3.
- **프론트엔드** — W5.
- **ETF 구성종목(PDF) 변환** — `sources/etf.py`(W2 이후).
