# BAL-13 dev-guide — `app/sources/us.py` US 시세·펀더·뉴스 어댑터

> SSoT: `docs/04-backend.md`(최우선) → `docs/05-database.md` → `docs/01-product-spec.md`.
> 시그니처 정본: `docs/BAL-2-w2-orchestration.md §2.1` (이 표를 벗어난 새 시그니처 발명 금지).
> ⚠️ **`TECH-DESIGN.md`는 레포에 없음** — W1 dev-guide가 인용한 `§15.x`는 부재 파일이므로 **답습 금지**. 04/05/01만 인용한다. W1 구현 정본 시그니처는 `docs/BAL-1-m1a-orchestration.md §2(v2)` + `docs/BAL-1-m1a-decisions.md` 참조.
> 범위: W2 데이터 슬라이스. 하위작업 **BAL-49**(시세: Stooq→yfinance→Finnhub 폴백), **BAL-50**(펀더: FMP 5년 + 뉴스: Finnhub + 재무: SEC EDGAR). collect 통합·db upsert·metrics는 본 이슈 밖(§8).

---

## 1. 목표 & 배경

### 이슈 요약
`app/sources/us.py`는 현재 W1 스텁(1줄 docstring, `app/sources/us.py:1`)이다. BAL-13은 이를 **US 어댑터** `UsSource`(= `PriceSource` + `NewsSource` Protocol 구현, 04 §7.3)로 채운다. W1에서 완성된 `KrSource`(`app/sources/kr.py`)의 **동일 계약·동일 가드 구조를 US 소스로 미러링**한다.

3개 메서드(= 하위작업 2개로 분해):

1. **`ohlcv(ct)` → `OHLCV`** (BAL-49) — 1차 **Stooq**(`pandas_datareader`/`stooq`) → 2차 **yfinance** `auto_adjust=True` → 보조 **Finnhub `/quote`**(당일가). 조정 윈도우(200일+)를 fresh fetch 해 `close_raw`/`close_adj`/52주/sma200을 **그 자리에서 계산**. (04:475, 04:562-565)
2. **`fundamentals(ct)` → `Funda`** (BAL-50) — 1차 **FMP 무료**(5년 시계열, 250req/day)로 `per`/`pbr`/`div_yield` + `per_pctile_5y`/`pbr_pctile_5y` 계산, `report_date`는 **SEC EDGAR**(`edgartools`) 보조. ⚠️ **PER/PBR은 제공자 계산값만 캐시, 자체 가격×EPS 재계산 금지**(04:481, SSoT §5). (04:476-477)
3. **`headlines(ct, name)` → `list[Headline]`** (BAL-50) — **Finnhub 뉴스**. 빈응답=`[]`(정상), `validate_response` 미적용(04:478, decisions Q9 — KR `headlines`와 동일 규약).

### W2 슬라이스(BAL-2) 내 역할/의존
- BAL-13은 의존 DAG(orchestration §1)의 **W2-2 어댑터 4-way 병렬** 중 하나다(BAL-13 ∥ BAL-14 ∥ BAL-15 ∥ BAL-16). `app/sources/us.py`는 **다른 W2 이슈와 파일 비중복**이므로 충돌 없이 병렬 가능.
- 의존(읽기 전용): `app/sources/__init__.py`(가드 `retry`/`validate_response`/`EmptyResponseError`, W1) · `app/models.py`(`OHLCV`/`Funda`/`Headline`, W1) · `app/tickers.py`(`to_source`, W1) · `app/calendar.py`(`expected_trade_date`, W1).
- 하류: BAL-17(`app/collect.py`)의 `_collect_market("US", ...)`가 `UsSource().ohlcv/fundamentals/headlines`를 호출해 `db.upsert_*`로 적재한다(orchestration §2.5, 04:543-553). 즉 BAL-13은 **US 시장의 raw 데이터 인입 계층**이며 통합자의 의존물이다.
- 본 가이드 범위에서 `collect.py`·`db.py` upsert 헬퍼·`metrics`·`models.FxRate` 등은 건드리지 않는다(§8 Out of scope).

---

## 2. 영향 파일

| 파일 | 동작 | 비고 |
|---|---|---|
| `app/sources/us.py` | **수정**(스텁→구현) | 본 이슈 본체. `UsSource.ohlcv/fundamentals/headlines` + 내부 폴백/percentile 헬퍼 |
| `tests/test_us.py` | **신규** | 본 가이드 §6 테스트. 외부 API **전량 모킹** |
| `app/sources/__init__.py` | **읽기 전용 의존** | `retry`/`validate_response`/`EmptyResponseError` import. 변경 불요(시그니처 불변, decisions §3.7) |
| `app/models.py` | **읽기 전용 의존** | `OHLCV`/`Funda`/`Headline` import. `OHLCV.week52_*`/`sma200`은 `float|None`(decisions §3.5) — US 신규편입 워밍업에서 None 경로 실제 발현. 변경 불요 |
| `app/tickers.py` | **읽기 전용 의존** | `to_source('stooq'/'yf'/'finnhub'/'fmp', ct, 'US')`. US 변환은 W1 완비(`tickers.py:31-36`). 변경 불요 |
| `app/config.py` | **읽기 전용 의존** | `FINNHUB_API_KEY`/`FMP_API_KEY`/`SEC_USER_AGENT` 참조(config.py:23-28, W1 선언). 변경 불요 — **사용 시점 fail-fast**는 본 이슈에서 비로소 구현(orchestration §4) |
| `requirements*.txt` | **수정(소규모)** | `pandas_datareader`, `yfinance`, `finnhub-python`(or `requests` 직접), `edgartools` 신규 추가(W2 신규 의존, orchestration §4) |

> 외부 네트워크/키를 만지는 어댑터이므로 §6 테스트는 **HTTP/라이브러리 경계를 전부 모킹**한다(실 API 호출 0).

---

## 3. 구현 단계

> 전제: KR 어댑터(`app/sources/kr.py`)가 정본 구조 템플릿이다. **동일한 상수·가드·percentile·`_pos_or_none` 패턴을 US로 미러링**하되 소스 라이브러리만 교체한다(Surgical — 새 추상화 발명 금지).

### 단계 0 — 모듈 골격 (kr.py 미러링)
`app/sources/kr.py:1-37`과 동일 구조로 import·상수·클래스 골격을 둔다.
- import: `logging`, `datetime`(date/timedelta), `pandas_datareader`(lazy import 권장 — 메서드 내부), `app.config`, `app.calendar.expected_trade_date`, `app.models.{Funda, Headline, OHLCV}`, `app.sources.{retry, validate_response}`, `app.tickers.to_source`.
- 상수: `_WEEK52_SESSIONS = 252`, `_SMA_SESSIONS = 200`, `_MIN_PCTILE_SAMPLE = 20`(kr.py:26-28 동일값 재사용). fetch 윈도우는 US 거래일 기준 200일+52주 동시 커버용 `_FETCH_WINDOW_DAYS = 420`(kr.py:25 동일).
- 클래스: `class UsSource:` — **`__init__` 무인자·무부작용(lazy)**. 네트워크/키 접근은 메서드 첫 호출 시(decisions Q10, kr.py:37 계약 동일).
- **검증 포인트**: `python3 -m py_compile app/sources/us.py` 통과. `UsSource()` 생성이 네트워크를 건드리지 않음(테스트로 보증).

### 단계 A — BAL-49: `ohlcv(ct)` 시세 폴백 체인 (04:475, 04:562-565)
`@retry(3)` 데코레이터(kr.py:39) 부착. 폴백 순서 = **Stooq(1차) → yfinance(2차) → Finnhub `/quote`(당일가 보조)**.

1. `expected = expected_trade_date("US", date.today())`.
2. **1차 Stooq**: `to_source('stooq', ct, 'US')`(예: `voo.us`, tickers.py:34-35) → `pandas_datareader.data.DataReader(sym, 'stooq', start, end)`. Stooq는 조정 컬럼을 직접 주지 않으므로(미조정 OHLCV) **`close_raw`는 Stooq Close**, `auto_adjust` 조정가는 2차 yfinance에서 확보 — degrade 시 `close_adj=close_raw`로 두고 `log.warning`(kr.py FDR 폴백 `fdr_fallback_adj_eq_raw`와 동일 정직성 규약, kr.py:79).
3. **빈 DF → 2차 yfinance**: `to_source('yf', ct, 'US')` → `yfinance` `history(period=...)` `auto_adjust=True`로 조정가 윈도우 확보 → `close_adj`(조정), `close_raw`는 `auto_adjust=False` 별도 1콜 또는 yfinance `Close`/`Adj Close` 분리(kr.py가 pykrx를 `adjusted=True/False` 2회 호출한 패턴 미러링, kr.py:46-49).
4. **2차도 빈 응답 → 보조 Finnhub `/quote`**: 당일가만 보강(시계열 없음 → 52주/sma200 계산 불가 → `None`). Finnhub `/quote`는 `c`(current) 단일값이므로 `close_raw=close_adj=c`, `week52_*`/`sma200`은 `None`(워밍업 경로, decisions §3.5).
5. `n = len(adj_close)`; `trade_date = <윈도우 최신 인덱스>.strftime("%Y-%m-%d")`.
6. **`validate_response(rows=n, latest=trade_date, expected=expected.isoformat())`** — 빈 응답이면 여기서 `EmptyResponseError`(04:457, kr.py:54).
7. `sma200 = float(adj_close.tail(200).mean()) if n >= _SMA_SESSIONS else None`(없으면 `log.warning`, kr.py:56-58). `w52 = adj_close.tail(252)` → `week52_high/low = float(w52.max()/min())` (윈도우<252면 None — decisions §3.5).
8. `return OHLCV(canonical_ticker=ct, trade_date=..., close_raw=..., close_adj=..., ccy="USD", week52_high=..., week52_low=..., sma200=...)`.

> 🔎 **조정가 fresh 재계산(04:562-565, SSoT §4 핵심)**: 매 호출 시 조정 윈도우(200일+)를 통째로 다시 받아 52주/SMA200을 그 자리 계산한다. 과거 `close_adj`를 누적 입력으로 쓰지 않는다(배당/분할 소급 흡수). 이 책임은 **어댑터(us.py)** 에 있고 collect는 호출만(orchestration §2.5).

- **검증 포인트**: (1) Stooq 정상 → close_raw·52주·sma200 채워진 `OHLCV`. (2) Stooq 빈 DF → yfinance 폴백 경로 진입. (3) 윈도우<200 종목 → `sma200=None`(+warning). (4) 빈 응답 전부 → `EmptyResponseError`.

### 단계 B — BAL-50-1: `fundamentals(ct)` FMP 5년 + EDGAR report_date (04:476-477, 04:481)
`@retry(3)` 부착. `_pos_or_none`/`_pctile` 헬퍼는 **kr.py:114-131을 그대로 미러링**(동일 로직, 재발명 금지).

1. `src = to_source('fmp', ct, 'US')`(예: `BRK.B`→`BRK-B`, tickers.py:32-33).
2. **FMP 무료 5년 시계열** 호출(`per`/`pbr`/`div_yield` + 분포). 키: `config.FMP_API_KEY` — **없으면 `raise KeyError`**(조용한 fallback 금지, 04 §2 / kr.py:138-139 패턴).
3. `trade_date = <시계열 최신 기준일>`; `validate_response(rows=len(series), latest=trade_date, expected=trade_date)`(kr.py:97과 동일하게 펀더는 자기 최신일=expected).
4. `per = _pos_or_none(latest_per)`, `pbr = _pos_or_none(latest_pbr)`, `div_yield = _pos_or_none(latest_div)` — **제공자 값 그대로, 가격×EPS 재계산 금지**(04:481).
5. `per_pctile_5y = _pctile(per_series, per, exclude_nonpos=True)`, `pbr_pctile_5y = _pctile(pbr_series, pbr, exclude_nonpos=False)`(kr.py:109-110 동일). 유효표본<20 → `None`(kr.py:129).
6. **`report_date`**: SEC EDGAR(`edgartools`)에서 최신 10-Q/10-K 기준일 보조 확보. 미확보·실패 시 `None`(배지 '워밍업', models.py:57). EDGAR 호출은 `config.SEC_USER_AGENT` 필요 — 없으면 `report_date=None`로 degrade(시세/펀더는 살리고 report_date만 NULL).
7. `return Funda(canonical_ticker=ct, trade_date=..., per=..., pbr=..., div_yield=..., per_pctile_5y=..., pbr_pctile_5y=..., report_date=...)`.

> 🔎 **degrade 규칙(04:481)**: FMP 한도가 빠듯하면 percentile을 "현재 PER vs 자기 5년 평균"으로 낮춤. `per_pctile_5y` **NULL 허용** → metrics가 "워밍업 중" 라벨(W3). 본 어댑터는 **NULL 반환까지** 책임지고 라벨링은 W3(orchestration §2.1 degrade 주석).

- **검증 포인트**: (1) FMP 정상 → per/pbr/div_yield + percentile 채워진 `Funda`. (2) 적자(PER≤0) → `per=None`(+percentile None). (3) 표본<20 → percentile `None`. (4) EDGAR 미확보 → `report_date=None`(나머지 필드 정상). (5) `FMP_API_KEY` 미설정 → `KeyError`.

### 단계 C — BAL-50-2: `headlines(ct, name)` Finnhub 뉴스 (04:478, decisions Q9)
`@retry(3)` 부착. **kr.py:133-155의 네이버 → Finnhub 치환** 미러링.

1. 키: `config.FINNHUB_API_KEY` — 없으면 `raise KeyError`(조용한 fallback 금지, kr.py:138-139).
2. Finnhub `company-news`(또는 `news`) 호출 → 헤드라인 목록.
3. **`validate_response` 미적용** — 빈 리스트=정상(decisions Q9, kr.py:135). `list[Headline]`이 비어도 예외 아님.
4. 각 항목 → `Headline(title=..., url=..., source="finnhub")`(models.py:60-66). `title`은 필요 시 HTML/공백 정리.
5. `return [...]`.

- **검증 포인트**: (1) Finnhub 정상 → `list[Headline]`(source="finnhub"). (2) 빈 응답 → `[]`(예외 없음). (3) `FINNHUB_API_KEY` 미설정 → `KeyError`.

### 단계 D — `py_compile` + 단위 테스트 그린
편집 후 `python3 -m py_compile app/sources/us.py`(degraded-session 수동 대체, orchestration §4) → `pytest -q tests/test_us.py`.
- **검증 포인트**: §7 DoD 체크리스트 전 항목 통과 + 외부 호출 0(모킹 보증).

---

## 4. 인터페이스 (정본 = orchestration §2.1, 그대로 구체화)

> 새 시그니처 발명 금지. 아래는 orchestration §2.1(canonical 04 §7.3) 시그니처를 파라미터/반환형/예외 수준으로만 구체화한 것이며, §2.1 텍스트와 1:1 대응한다.

```python
from app.models import OHLCV, Funda, Headline

class UsSource:   # PriceSource + NewsSource Protocol (04 §4.3/§7.2 구조 동일, KrSource 미러)
    # __init__ 무인자·무부작용(lazy) — 네트워크/키 접근은 메서드 첫 호출 시 (decisions Q10)

    @retry(3)
    def ohlcv(self, ct: str) -> OHLCV: ...
    #   BAL-49: 1차 Stooq(pandas_datareader/stooq) → 2차 yfinance auto_adjust=True
    #           → Finnhub /quote(당일가 보조). 조정 윈도우(200일+) fresh fetch
    #           → close_raw/close_adj/52주/sma200 그 자리 계산 (04:475, 04:562-565)
    #   ccy="USD". week52_*/sma200은 윈도우 부족 시 None (decisions §3.5)
    #   빈 응답 전부 → validate_response가 EmptyResponseError (04:457)

    @retry(3)
    def fundamentals(self, ct: str) -> Funda: ...
    #   BAL-50: FMP 무료 5년 시계열(250req/day) → per/pbr/div_yield + per_pctile_5y/pbr_pctile_5y
    #           report_date = SEC EDGAR(edgartools) 보조 (04:476-477)
    #   ⚠️ PER/PBR은 제공자 계산값만 캐시, 자체 가격×EPS 재계산 금지 (04:481)
    #   적자/표본부족/한도 → 해당 필드 None (degrade, NULL까지 책임)

    @retry(3)
    def headlines(self, ct: str, name: str) -> list[Headline]: ...
    #   BAL-50: Finnhub 뉴스. 빈응답=[] (validate_response 미적용 — 04:478, decisions Q9)
```

**orchestration §2.1과의 정합 확인**:
- `UsSource.ohlcv/fundamentals/headlines` — 3개 모두 §2.1 시그니처와 자모 단위 일치(파라미터명·반환형). `ct: str` / `name: str` / 반환 `OHLCV`·`Funda`·`list[Headline]`.
- `__init__` 무인자·lazy 계약은 §2.1 주석("KrSource와 동일하게 __init__ 무인자·무부작용") 구체화 — KR(`kr.py:37`)과 동일.
- 폴백 체인·degrade·`report_date` EDGAR 보조는 §2.1 인라인 주석의 구체화이며 **시그니처 불변, 내부 구현만 채움**.
- `validate_response`/`retry`/`EmptyResponseError`는 W1 가드(`app/sources/__init__.py`) **그대로 사용** — 본 이슈에서 시그니처/본체 변경 없음(날짜검사 본체 성장은 BAL-17 소관, orchestration §2.7/U2).

---

## 5. 엣지 & 리스크

| # | 상황 | 영향 | 대응 (본 모듈) |
|---|---|---|---|
| E1 | **Stooq 빈 CSV / 조용한 실패** | 빈 응답이 OK처럼 보임 | 1차 빈 DF → yfinance 폴백 진입(단계 A-3). 전부 빈 응답 시 `validate_response(rows=0)`→`EmptyResponseError`(04:457). "예외 안 남"≠OK(04:576) |
| E2 | **US 신규편입·워밍업(윈도우<200/<252)** | sma200/52주 계산 불가 | `sma200=None`(윈도우<200), `week52_*=None`(윈도우<252) + `log.warning`(decisions §3.5, models.py:41-43). `OHLCV`가 None을 정직하게 담음 |
| E3 | **Finnhub `/quote` 당일가만(시계열 없음)** | 52주/sma200 산출 불가 | 보조 경로에서 `week52_*/sma200=None`, `close_raw=close_adj=c`. 워밍업 라벨은 metrics(W3) |
| E4 | **Stooq 조정 컬럼 부재** | close_adj 미확보 | yfinance `auto_adjust=True`로 조정가 확보가 정본. yfinance도 실패 시 `close_adj=close_raw` + warning(kr.py FDR 폴백 정직성 규약 미러, kr.py:79) |
| E5 | **FMP 한도(250req/day) 소진** | percentile 미산출 | `per_pctile_5y/pbr_pctile_5y=None` degrade(04:481). 백필 분할은 BAL-17 TokenBucket 책임 — 어댑터는 NULL 반환까지. metrics가 "워밍업" 라벨(W3) |
| E6 | **자체 PER 재계산 유혹**(가격×EPS) | SSoT §5 위반(이중 진실) | **금지**(04:481). 제공자(FMP) 계산값만 캐시. 가격으로 PER 재산출하는 코드 작성 금지 |
| E7 | **적자/음수 PER·PBR·DIV** | 잘못된 percentile | `_pos_or_none`로 음수/0/NaN→None(kr.py:114-119 미러). percentile 분포도 `exclude_nonpos`로 정제(kr.py:122-131) |
| E8 | **EDGAR(report_date) 실패·SEC_USER_AGENT 미설정** | report_date 미확보 | `report_date=None` degrade(시세/펀더는 살림). NULL=배지 '워밍업'(models.py:57). EDGAR 실패가 fundamentals 전체를 죽이지 않음 |
| E9 | **API 키 미설정**(FMP/Finnhub) | 조용한 빈 결과 위험 | `raise KeyError`(조용한 fallback 금지, 04 §2 / kr.py:138-139). collect가 종목 격리로 `missing_tickers` 기록(04:557) |
| E10 | **단일 종목 raise가 배치 죽임** | 전체 수집 중단 | 어댑터는 raise까지만(`@retry(3)` 후 최종 실패 raise). **격리는 collect(BAL-17) 책임**(04:446/557) — 어댑터는 종목별 순수 함수 |
| E11 | **티커 변환 오류**(예: `BRK.B`) | 소스가 못 찾음 | `to_source('fmp'/'finnhub','BRK.B','US')`→`BRK-B`, `('stooq',...)`→`brk-b.us`(tickers.py:32-35, W1 완비). 미지원 조합은 `ValueError` fail-fast |
| E12 | **테스트가 실 API 호출** | 비결정·키 누출·rate limit | §6 모킹 전량 강제 — `pandas_datareader`/`yfinance`/`requests`/`edgartools` 경계 mock. 실 네트워크 0 |

---

## 6. 테스트 계획

**파일: `tests/test_us.py`** (pytest, `@pytest.mark.unit`). ⚠️ **외부 API 전량 모킹** — 실 네트워크 호출 0. 모킹 경계:
- Stooq: `pandas_datareader.data.DataReader`(또는 us.py가 import한 심볼)
- yfinance: `yfinance.Ticker`/`download`(us.py 사용형에 맞춰)
- Finnhub: `requests.get`(또는 `finnhub` 클라이언트 메서드)
- EDGAR: `edgartools` 진입점

권장 패턴: `monkeypatch.setattr` 또는 `unittest.mock.patch`로 모듈 경계 함수를 가짜 DataFrame/dict 반환으로 치환. `config.FMP_API_KEY`/`FINNHUB_API_KEY`/`SEC_USER_AGENT`는 `monkeypatch.setattr(config, ...)`로 주입(실 키 미사용).

| 테스트명 | 검증 대상 | 핵심 단언 |
|---|---|---|
| `test_init_no_network` | lazy `__init__` (단계 0) | `UsSource()` 생성 시 모킹된 네트워크 함수 호출 0회 |
| `test_ohlcv_stooq_primary` | ohlcv 1차 (단계 A) | Stooq mock 정상 → `OHLCV.close_raw`/`week52_high`/`sma200` 실수치, `ccy=="USD"`, `trade_date` 포맷 |
| `test_ohlcv_yfinance_fallback` | ohlcv 2차 (E1) | Stooq 빈 DF → yfinance mock 경로 진입(yfinance mock 호출됨) → 조정가 `OHLCV` 반환 |
| `test_ohlcv_finnhub_quote_aux` | ohlcv 보조 (E3) | Stooq·yfinance 빈 → Finnhub `/quote` mock → `close_raw==close_adj`, `week52_*/sma200 is None` |
| `test_ohlcv_short_window_none` | 워밍업 (E2) | 윈도우<200 mock → `sma200 is None`; 윈도우<252 → `week52_* is None` (+warning) |
| `test_ohlcv_all_empty_raises` | 빈응답 가드 (E1) | 모든 소스 빈 응답 → `EmptyResponseError` |
| `test_fundamentals_fmp_ok` | fundamentals (단계 B) | FMP mock 정상 → `per`/`pbr`/`div_yield`/`per_pctile_5y` 실수치 `Funda` |
| `test_fundamentals_negative_per_none` | 적자 (E7) | PER≤0 mock → `per is None` 및 `per_pctile_5y is None` |
| `test_fundamentals_small_sample_pctile_none` | 표본부족 (E5/E7) | 분포 표본<20 → `per_pctile_5y is None` |
| `test_fundamentals_no_recalc_per` | 재계산 금지 (E6) | 제공자 PER 값이 그대로 반환됨(가격×EPS 재산출 흔적 없음 — 제공자값==반환값) |
| `test_fundamentals_edgar_fail_report_date_none` | EDGAR degrade (E8) | EDGAR mock 예외/빈 → `report_date is None`, 나머지 필드 정상 |
| `test_fundamentals_missing_fmp_key_raises` | 키 가드 (E9) | `FMP_API_KEY=None` → `KeyError` |
| `test_headlines_finnhub_ok` | headlines (단계 C) | Finnhub mock → `list[Headline]`, 각 `source=="finnhub"` |
| `test_headlines_empty_is_ok` | 빈응답=정상 | 빈 응답 → `[]`(예외 없음, validate_response 미호출) |
| `test_headlines_missing_finnhub_key_raises` | 키 가드 (E9) | `FINNHUB_API_KEY=None` → `KeyError` |
| `test_to_source_us_mapping` | 티커 변환 (E11) | (간접) `BRK.B` US 종목 mock에서 소스 심볼이 `BRK-B`/`brk-b.us`로 전달됨 |

> 네트워크 의존(Stooq/yfinance/Finnhub/EDGAR)은 **전부 모킹** — 어댑터 계약 단위 테스트만. 실제 라이브 인입 증명(30종목)은 BAL-17 collect 통합 게이트(orchestration §5).

---

## 7. DoD (Definition of Done)

로드맵 08 §Week2 + orchestration §5에서 **us.py 어댑터에 해당하는 항목만** 인용:

- [ ] (orchestration §5 W2-2 게이트) `UsSource().ohlcv(<US종목>)` → `close_raw`·52주·sma200 채워진 `OHLCV`(ccy="USD"). 폴백 체인 Stooq→yfinance→Finnhub `/quote` 동작.
- [ ] (orchestration §5 W2-2) `UsSource().fundamentals(<US종목>)` → `per`/`pbr`/`div_yield` + `per_pctile_5y`/`pbr_pctile_5y` 산출. report_date는 EDGAR 보조(미확보 시 None).
- [ ] (orchestration §5 W2-2) `UsSource().headlines(<US종목>, name)` → `list[Headline]`(source="finnhub"), 빈응답=`[]`(예외 없음).
- [ ] **PER/PBR 재계산 금지**(04:481): 제공자 계산값만 캐시, 가격×EPS 자체 재산출 코드 없음.
- [ ] **조정가 fresh 재계산**(04:562-565): `ohlcv()` 매 호출 200일+ 윈도우 통째 fetch → 52주/sma200 그 자리 계산.
- [ ] **degrade 경로**: 워밍업(윈도우<200/<252)·적자·표본부족·EDGAR 실패 시 해당 필드 `None` 반환(예외 아님, decisions §3.5 / 04:481).
- [ ] **키 fail-fast**: `FMP_API_KEY`/`FINNHUB_API_KEY` 미설정 → `KeyError`(조용한 fallback 금지, 04 §2).
- [ ] **빈응답 가드**: 시세 전 소스 빈 응답 → `EmptyResponseError`(04:457). headlines는 빈=정상.
- [ ] (orchestration §5) `pytest -q tests/test_us.py` green, 편집 파일 `py_compile` 통과(degraded-session 수동 대체, §4). **외부 API 호출 0**(모킹).
- [ ] 코딩 규칙 준수: PEP8 + 전 함수 타입주석 + frozen DTO(`OHLCV`/`Funda`/`Headline` 재사용). `print()` 미사용(logging).
- [ ] (orchestration §4) W2 신규 라이브러리(`pandas_datareader`/`yfinance`/`edgartools` 등) `requirements` 추가 + `.venv` 설치 수동 검증.

> ⚠️ **종목 격리·`missing_tickers`·`collect_run` status·30종목 라이브 수집**은 **BAL-17(collect.py) DoD**(orchestration §5) — us.py DoD 아님. 어댑터는 종목별 raise까지만 책임.

---

## 8. Out of scope (W2 / BAL-13 아님)

- **`collect.py`** 전체(`run_collect`/`_collect_market`/`_collect_fx`/`_collect_regime`/`_status_of`/`TokenBucket`/백필) — **BAL-17**(orchestration §2.5). us.py는 어댑터 메서드만, 호출·격리·status 판정·rate limiting은 BAL-17.
- **db upsert 헬퍼**(`upsert_price`/`upsert_funda`/`upsert_news` 등) — W1(BAL-8) + W2-1 선커밋(orchestration §2.6). us.py는 DTO 반환까지, 적재는 caller.
- **`models.FxRate`** 정의 — **BAL-14**(W2-1 선커밋, orchestration §2.2). us.py와 무관.
- **`fx.py`/`regime.py`/`etf.py`** 어댑터 — BAL-14/15/16(orchestration §2.2~2.4). 본 이슈는 `us.py` 단독.
- **`validate_response` 날짜검사 본체 성장**(`if latest != expected: raise`) — BAL-17 collect 경로(orchestration §2.7/U2). us.py는 W1 가드 그대로 사용(시그니처/본체 불변).
- **metrics 계산**(percentile→라벨, drift/valuation/trend, 04 §9) — W3. 어댑터는 raw 값·NULL까지, 라벨링은 W3.
- **룩스루 ETF 비중 분해**(F-19, 01:248 R2) — 정확도 확장, R1 PoC 밖.
- **LLM/브리핑·프론트·손익(G8)** — orchestration §6.

---

## 미해결 질문
(아래는 04/05/01 및 orchestration §2.1 간 명시되지 않은 구현 세부 — 본문에 임의 가정을 주입하지 않고 모았다.)

1. **`ohlcv` 1차/2차 조정가 책임 분담**: orchestration §2.1은 "1차 Stooq → 2차 yfinance `auto_adjust=True`"라 적었으나 **Stooq가 조정 컬럼을 직접 안 주는 경우** `close_adj`를 (a) 항상 yfinance에서 별도 확보할지, (b) Stooq Close를 `close_adj=close_raw`로 두고 degrade할지 명시 없음. 본 가이드 기본안 = Stooq 정상 시 close_raw 확보 + 조정가는 yfinance 우선, 둘 다 실패 시 `close_adj=close_raw`+warning(kr.py FDR 폴백 정직성 규약 미러, kr.py:79). 폴백 단계별 조정가 정확도 기대치 확인 필요.
2. **`close_raw` vs `close_adj` 소스 일관성**: KR은 pykrx를 `adjusted=True/False` **2회** 호출해 둘을 분리(kr.py:46-49). US에서 동일하게 yfinance를 `auto_adjust=True/False` 2회 호출할지, 1콜에서 `Close`/`Adj Close` 두 컬럼을 쓸지(라이브러리 버전별 컬럼명 차이) — 구현자(BAL-13)가 yfinance 버전 확인 후 1택 고정 필요. 계약(`OHLCV.close_raw`/`close_adj` 분리)은 불변.
3. **Finnhub `/quote` 보조의 trade_date**: 당일가만 주므로 `trade_date`를 (a) `date.today()` (b) Finnhub 응답의 `t`(timestamp) 변환 중 무엇으로 채울지 명시 없음. `validate_response`의 `latest==expected` 비교(W2 collect 경로, U2)와 정합하려면 응답 timestamp 사용이 안전 — 확인 필요.
4. **EDGAR `report_date` 매핑 단위**: `edgartools`가 주는 filing date vs period-of-report(재무 기준일) 중 `Funda.report_date`(models.py:57 "재무 실제 기준일")에 무엇을 넣을지. 신선도 배지 의미(05 §3.3 report_date)와 정합하려면 **period-of-report**가 정본일 가능성이 높으나 04/05에 US EDGAR 매핑 명시 없음 — 사용자/구현자 확인 필요.

> 📌 W1 dev-guide의 미해결 질문이 `docs/BAL-1-m1a-decisions.md`로 전건 해소된 것과 동일하게, 본 가이드의 위 4건은 **BAL-2/W2 decisions(작성 시)** 또는 구현 직전 확정으로 해소한다. 시그니처 정본 = orchestration §2.1(canonical 04 §7.3) — 위 질문은 모두 **시그니처 불변, 내부 구현 세부**에 한정된다.
