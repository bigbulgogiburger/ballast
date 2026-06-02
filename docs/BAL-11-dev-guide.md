# BAL-11 개발 가이드 — `app/sources/kr.py` (KR 어댑터: 시세·재무·뉴스) + regime KR

> **정본 우선순위**: `TECH-DESIGN.md §15` > `docs/04-backend.md` > `docs/05-database.md`. seam 시그니처 정본 = `docs/BAL-1-m1a-orchestration.md §2`(v2, canonical 정합).
> **이 가이드의 시그니처는 canonical 검증 완료된 정본이다. 그대로 사용 — 변형/발명 금지.**
> 모듈: `app/sources/kr.py` + `app/sources/regime.py`(KR 절반). 현재 W0 스텁: `app/sources/kr.py`(docstring 1줄), `app/sources/regime.py`(미생성).

---

## 1. 목표 & 배경 (W1 슬라이스 내 역할/의존)

### 1.1 목표
**"삼성전자(005930) 시세·재무·뉴스가 무료 소스에서 진짜로 긁혀 DTO로 나온다"를 끝까지 증명**(08 §Week1 목표). M1a 데이터 스파이크의 핵심 소비자 모듈로, 무료 데이터 가정의 검증 지점이다. 여기서 막히면 설계를 튼다.

### 1.2 W1 수직 슬라이스 내 위치 (DAG)
`BAL-11`은 foundation 3종(BAL-8 db, BAL-9 tickers, BAL-10 calendar) 위에 얹히는 **consumer**다(`BAL-1-m1a-orchestration.md §1`).

```
BAL-8  app/db.py        ─┐
BAL-9  app/tickers.py   ─┼─► BAL-11 app/sources/kr.py ─► BAL-12 validate + 005930 E2E
BAL-10 app/calendar.py  ─┘     (+ app/sources/regime.py)
```

- **상류 의존(반드시 먼저 존재)**: `tickers.to_source()`(BAL-9), `calendar.expected_trade_date()`(BAL-10), `models.py`의 DTO(BAL-11 자신이 W1 부분 정의), 그리고 **공통 가드 `app/sources/__init__.py`**(retry/validate_response/EmptyResponseError — `BAL-1-m1a §2.7`, **W-2a에서 kr.py보다 먼저 생성**).
- **하류 소비(BAL-11이 만든 걸 쓰는 쪽)**: BAL-12(빈응답 동작 테스트 + `db.upsert_*` 적재 → `latest_price` row 증명 E2E), W2의 `collect.py`(`_collect_market`이 `ohlcv/fundamentals/headlines` 호출, 04 §8.2).

### 1.3 실행 파동
- **Wave W-2b**(`BAL-1-m1a §3`). 선행: W-1(8·9·10 커밋) + W-2a(`sources/__init__.py` 가드). kr.py 내부 3개 메서드는 Tier-2 병렬 가능(ohlcv ∥ fundamentals ∥ headlines)이나 1인 작업이면 순차로 충분.
- regime KR(`regime.py`)도 같은 W-2b. **BAL-48("headlines + regime KR")은 두 파일에 걸친다**: headlines→kr.py, regime→regime.py(`BAL-1-m1a §2.6`).

### 1.4 BAL-11 하위작업 매핑
| 하위 | 범위 | 파일 |
|---|---|---|
| BAL-46 | `ohlcv()` 조정 윈도우 fresh fetch | kr.py |
| BAL-47 | `fundamentals()` 5년 PER/PBR/배당 + percentile | kr.py |
| BAL-48(일부) | `headlines()` 네이버 + `regime()` KR | kr.py + regime.py |

---

## 2. 영향 파일

| 파일 | 작업 | 근거 |
|---|---|---|
| `app/sources/kr.py` | **신규 구현**(W0 스텁 대체): `class KrSource`의 `ohlcv`/`fundamentals`/`headlines` | 04 §4.3/§7.2, BAL-1-m1a §2.5 |
| `app/sources/regime.py` | **신규 생성**: `class RegimeProvider`의 `regime()`(KR 절반) | 04 §7.5, BAL-1-m1a §2.6 |
| `app/models.py` | **W1 부분 기여**: `OHLCV`/`Funda`/`Headline`/`RegimeRow` frozen dataclass 선정의(없으면 추가) | 04 §4.2, §15.2, BAL-1-m1a §2.4 |
| `app/sources/__init__.py` | **읽기 전용 import**(W-2a가 이미 생성): `retry`, `validate_response`, `EmptyResponseError` | 04 §7.1, BAL-1-m1a §2.7 |
| `app/tickers.py` | **읽기 전용 import**: `to_source` | 04 §5.1 (BAL-9) |
| `app/calendar.py` | **읽기 전용 import**: `expected_trade_date` | 04 §6.1 (BAL-10) |
| `app/config.py` | **읽기 전용 import**: `load()` → 네이버 키(`naver_client_id/secret`, `naver_rps`) | 04 §2 |
| `tests/test_kr.py`, `tests/test_regime.py` | **신규**: 모킹 단위 테스트 | testing 규칙 |

> ⚠️ 모델 DTO는 BAL-11이 만들지만 **W1에 필요한 것만**(`OHLCV/Funda/Headline/RegimeRow` + `HoldingInput`). `FxRate`·`SecurityCard`·`BriefingDoc` 등은 W2+/W3+ (BAL-1-m1a §2.4 — 끌려가지 말 것). 이미 BAL-8/9/10 작업에서 일부 DTO가 추가됐다면 중복 정의 금지, 시그니처만 대조.

---

## 3. 구현 단계 (하위작업 분해 · 검증 포인트)

### 단계 0 — 선행 확인 (블로킹)
- `app/sources/__init__.py`에 `retry`/`validate_response`/`EmptyResponseError`가 **존재하는지 확인**. 없으면 W-2a 미완 → kr.py 작성 보류(이 가드는 BAL-11이 만들지 않음).
- `app/tickers.py:to_source`, `app/calendar.py:expected_trade_date` import 가능 확인.
- **검증**: `python3 -c "from app.sources import retry, validate_response, EmptyResponseError; from app.tickers import to_source; from app.calendar import expected_trade_date"`

### 단계 1 — models.py DTO 선정의 (BAL-11 기여분)
`OHLCV`/`Funda`/`Headline`/`RegimeRow`를 04 §4.2 **첫 필드 순서 그대로** 추가(§4 인터페이스 절 코드블록 사용). 이미 있으면 시그니처만 대조(드리프트 금지).
- **검증**: `python3 -m py_compile app/models.py` + `python3 -c "from app.models import OHLCV, Funda, Headline, RegimeRow"`

### 단계 2 — `ohlcv()` (BAL-46)
1. `src_ct = to_source("fdr", ct, "KR")` 또는 `to_source("pykrx", ct, "KR")`(둘 다 KR은 6자리 그대로 → `"005930"`).
2. `today = date.today()` → `expected = calendar.expected_trade_date("KR", today)`.
3. **조정 윈도우 fresh fetch**: 최소 200거래일 + 52주(약 252거래일) 커버하도록 시작일을 **today 기준 약 400캘린더일 전**으로 잡아 FDR/pykrx에서 OHLCV DataFrame을 통째로 받는다(05 §1.3 stale 방지 — 캐시 누적 금지).
4. DataFrame에서 계산:
   - `close_raw` = 최신 거래일 **미조정** 종가(현재 평가액용).
   - `close_adj` = 최신 거래일 **조정** 종가(표시·감사용).
   - `week52_high/low` = **조정가** 윈도우 최근 252거래일 max/min.
   - `sma200` = **조정가** 최근 200거래일 단순이동평균.
   - `trade_date` = DataFrame 마지막 인덱스 날짜(`YYYY-MM-DD`).
   - `ccy = "KRW"`.
5. `validate_response(rows=len(df), latest=trade_date, expected=expected.isoformat())` → 빈 DF면 `EmptyResponseError`.
6. `OHLCV(canonical_ticker=ct, ...)` 반환(**`ct`는 canonical 원본**, 소스 변환 키 아님 — PK는 canonical 기준, 05 §0).
- **검증**: `python3 -c "from app.sources.kr import KrSource; print(KrSource().ohlcv('005930'))"` → `close_raw`·`week52_*`·`sma200` **실수치**(08 §Week1 DoD).

### 단계 3 — `fundamentals()` (BAL-47)
1. pykrx `get_market_fundamental`로 **5년 시계열**(PER/PBR/DIV) fetch(`to_source("pykrx", ct, "KR")`).
2. 최신 row → `per`/`pbr`/`div_yield`(제공자 계산값 그대로, **자체 가격×EPS 재계산 금지** 04 §7.3 / 05 §1.4).
3. **percentile은 어댑터가 계산**(04 §7.2): `per_pctile_5y` = 5년 PER 분포 중 현재 PER의 백분위, `pbr_pctile_5y` 동일.
4. 음수/NaN PER(적자) → 해당 필드 `None`(판정은 metrics 레이어, DB는 NULL/원값 저장; 05 §1.4).
5. percentile 계산 불가(데이터 부족) → `per_pctile_5y=None`(NULL 허용, degrade 경로는 W3 metrics가 처리).
6. `report_date`: pykrx 시계열엔 재무 기준일이 명확치 않음 → W1은 **`None` 허용**(DART 확보는 보조·W2, 04 §7.2 "(보조)"; 05 §1.4 NULL 허용).
7. `Funda(canonical_ticker=ct, ...)` 반환.
- **검증**: `python3 -c "from app.sources.kr import KrSource; print(KrSource().fundamentals('005930'))"` → PER/PBR/배당 + `per_pctile_5y`(5년 백필 OK).

### 단계 4 — `headlines()` (BAL-48 일부)
1. 네이버 검색 API(`config.load()`의 `naver_client_id/secret`) 호출, 검색어 = `name`(예 "삼성전자").
2. 응답 items → `Headline(title=, url=, source=)` 리스트. 제목 HTML 태그(`<b>` 등) 제거.
3. **빈 응답은 `[]` 반환**(뉴스 0건은 정상, `validate_response` **미적용** — BAL-1-m1a §2.5). 그 외 네트워크 오류는 `@retry`가 흡수.
4. `@retry(3)` 적용, 토큰버킷 rate-limit은 **W1 범위 밖**(collect.py가 W2에서 TokenBucket 소유 — 04 §8.6). W1은 단일 종목 수동 호출이라 페이싱 불필요.
- **검증**: `python3 -c "from app.sources.kr import KrSource; print(KrSource().headlines('005930', '삼성전자'))"` → list[Headline] 또는 `[]`.

### 단계 5 — `regime.py:RegimeProvider.regime()` (BAL-48 일부)
1. pykrx 지수 PBR(KOSPI)로 `kospi_pbr` 산출.
2. `us_cape = None`(**W1은 KR 절반만**, US CAPE는 W2 — BAL-1-m1a §6 Out of scope).
3. `as_of` = 기준월(`YYYY-MM-01` 등, 04 §4.2 upsert 매핑 `as_of→trade_date`).
4. `RegimeRow(as_of=, kospi_pbr=, us_cape=None)` 반환. 실패 시 raise(collect가 degrade 처리 — W2).
- **검증**: `python3 -c "from app.sources.regime import RegimeProvider; print(RegimeProvider().regime())"` → `kospi_pbr` 실수치, `us_cape=None`.

### 단계 6 — 컴파일 + 테스트
- `python3 -m py_compile app/sources/kr.py app/sources/regime.py app/models.py`(degraded-session 수동 compile-check, BAL-1-m1a §4).
- `pytest -q tests/test_kr.py tests/test_regime.py` green.

---

## 4. 인터페이스 (확정 시그니처 구체화: 파라미터/반환형/예외)

### 4.1 `app/models.py` — DTO (04 §4.2, 첫 필드 `canonical_ticker`)
```python
from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True)
class OHLCV:
    canonical_ticker: str
    trade_date: str            # 소스 최신 거래일 'YYYY-MM-DD'
    close_raw: float           # 미조정 (현재 평가액용)
    close_adj: float           # 조정 (스냅샷 표시·감사용)
    ccy: Literal["KRW", "USD"]
    week52_high: float         # 조정가 기준, fresh 재계산
    week52_low: float
    sma200: float

@dataclass(frozen=True)
class Funda:
    canonical_ticker: str
    trade_date: str
    per: float | None          # 적자=None
    pbr: float | None
    div_yield: float | None
    per_pctile_5y: float | None    # NULL 허용(백필중/정밀도)
    pbr_pctile_5y: float | None
    report_date: str | None        # US 워밍업/DART 미확보 시 NULL

@dataclass(frozen=True)
class Headline:
    title: str
    url: str
    source: str

@dataclass(frozen=True)
class RegimeRow:
    as_of: str                 # 기준월 → 테이블 PK trade_date로 매핑 (05 §1.7)
    kospi_pbr: float | None    # KR — pykrx 지수 PBR
    us_cape: float | None      # US — Shiller CAPE (W1=None)
    # upsert 매핑: as_of→trade_date, us_cape→shiller_cape
```

### 4.2 `app/sources/kr.py` — KrSource (04 §4.3 PriceSource + NewsSource)
```python
class KrSource:   # PriceSource + NewsSource Protocol (04 §4.3)
    def ohlcv(self, ct: str) -> OHLCV:
        # BAL-46: FDR/pykrx 조정 윈도우 fresh fetch → close_raw/close_adj/week52/sma200.
        # 내부: tickers.to_source("fdr"/"pykrx", ct, "KR") + calendar.expected_trade_date("KR", today).
        # @retry(3) + validate_response(rows, latest=trade_date, expected).
        # 반환 OHLCV.canonical_ticker = ct (canonical 원본).
        # 예외: 빈 DF → EmptyResponseError(validate_response 경유). 재시도 소진 → 마지막 예외 raise.

    def fundamentals(self, ct: str) -> Funda:
        # BAL-47: pykrx get_market_fundamental 5년 PER/PBR/배당.
        # percentile(per_pctile_5y/pbr_pctile_5y)은 어댑터가 5년 분포로 직접 계산 (04 §7.2).
        # 적자(음수/NaN PER) → per=None. percentile 불가 → None. report_date → None(W1).
        # @retry(3) + validate_response. 예외: 빈 응답 → EmptyResponseError.

    def headlines(self, ct: str, name: str) -> list[Headline]:
        # BAL-48 일부: 네이버 검색 API(name으로 질의). 헤드라인+링크만.
        # 빈 응답 = [] 반환 (뉴스 0건은 정상, validate_response 미적용).
        # @retry(3). 예외: 네트워크/인증 실패만 raise(빈 결과는 예외 아님).
```

### 4.3 `app/sources/regime.py` — RegimeProvider (04 §7.5 RegimeSource)
```python
class RegimeProvider:   # RegimeSource Protocol
    def regime(self) -> RegimeRow:
        # W1 = KR 절반만: kospi_pbr = pykrx 지수 PBR(KOSPI), us_cape = None.
        # 예외: pykrx 실패 시 raise(collect가 degrade — W2). W1 수동 검증은 성공 경로만.
```

### 4.4 의존 시그니처 (읽기 전용, 이미 정본)
```python
# app/tickers.py (BAL-9)
to_source(source, ct, market) -> str          # to_source("pykrx","005930","KR") -> "005930"
# app/calendar.py (BAL-10)
expected_trade_date(market, today) -> date    # ("KR", today) -> 오늘(거래일)
# app/sources/__init__.py (W-2a)
@retry(times=3, backoff=1.5)
validate_response(rows: int, latest: str, expected: str) -> None   # rows==0 → EmptyResponseError
class EmptyResponseError(Exception): ...
```

---

## 5. 엣지 & 리스크

| 케이스 | 처리 | 근거 |
|---|---|---|
| pykrx/FDR 특정 종목·기간 빈 DF | `@retry(3)` → 재시도 소진 시 `validate_response`가 `EmptyResponseError` | 08 §Week1 리스크, 04 §7.1 |
| **SMA200 윈도우 < 200거래일**(신규 상장 등) | 005930은 충분하므로 W1 정상 경로 영향 無. **정책 미확정** → 미해결 질문 참조 | — |
| 5년 percentile 산출 불가(시계열 부족) | `per_pctile_5y=None`(NULL 허용) → W3 metrics가 "절대 PER만" degrade 라벨 | 05 §1.4, 08 §Week1 |
| 음수/NaN PER(적자) | 해당 필드 `None`, percentile 밴드 제외는 metrics(W3) 책임 | 05 §1.4 |
| 뉴스 0건 | `[]` 반환(정상), `validate_response` **미적용** | BAL-1-m1a §2.5 |
| 조정가 stale | **매 호출 조정 윈도우 통째 재fetch**, 캐시 누적 금지 | 05 §1.3 |
| KOSDAQ(.KQ) | W1은 005930=KOSPI만. KOSDAQ 서브마켓은 W2 유보(known limitation) | BAL-1-m1a §2.2 |
| 네이버 API 키 누락 | `config.load()`가 `KeyError`로 즉시 실패(조용한 fallback 금지) | 04 §2 |
| 외부 네트워크 | **테스트에서 전량 모킹**(pykrx/FDR/requests) | 스타일 규칙 |

---

## 6. 테스트 계획 (pytest, 어댑터=모킹)

> 외부 네트워크(pykrx/FDR/네이버)는 **전량 모킹**. 실 API 호출 테스트 금지(범위·결정성).

### `tests/test_kr.py`
```python
import pytest

@pytest.mark.unit
def test_ohlcv_returns_realistic_dto(monkeypatch):
    # FDR/pykrx fetch를 200일+ 조정 DataFrame fixture로 모킹
    # → OHLCV.close_raw/close_adj/week52_high/week52_low/sma200 모두 float
    # → canonical_ticker == "005930", ccy == "KRW", trade_date 형식 'YYYY-MM-DD'

@pytest.mark.unit
def test_ohlcv_empty_df_raises_empty_response(monkeypatch):
    # 빈 DataFrame 모킹 → EmptyResponseError

@pytest.mark.unit
def test_fundamentals_computes_percentile(monkeypatch):
    # 5년 PER 시계열 모킹 → per_pctile_5y가 분포상 올바른 백분위(예: 중앙값이면 ~50)

@pytest.mark.unit
def test_fundamentals_negative_per_is_none(monkeypatch):
    # 음수 PER 최신 row → per=None

@pytest.mark.unit
def test_headlines_empty_returns_list_not_raise(monkeypatch):
    # 네이버 빈 응답 모킹 → [] 반환(예외 X)

@pytest.mark.unit
def test_headlines_strips_html_tags(monkeypatch):
    # 제목의 <b>·</b> 제거 확인
```

### `tests/test_regime.py`
```python
@pytest.mark.unit
def test_regime_kr_only(monkeypatch):
    # pykrx 지수 PBR 모킹 → RegimeRow.kospi_pbr float, us_cape is None
```

- **회귀 연결**: BAL-12가 `validate_response` 빈응답 동작 + 005930 fetch→`db.upsert_*`→`latest_price` E2E를 담당(이 가이드 범위 밖). W1 단위 테스트는 어댑터 격리에 집중.
- 커버리지: `pytest --cov=app/sources --cov-report=term-missing`(testing 규칙).

---

## 7. DoD (Definition of Done)

### 로드맵 08 §Week1 DoD (BAL-11 해당분)
- [ ] `python -c "from app.sources.kr import KrSource; print(KrSource().ohlcv('005930'))"` → `close_raw`·52주·`sma200`이 **실수치**로 출력.
- [ ] `fundamentals('005930')` → PER/PBR/배당 + `per_pctile_5y`(5년 백필 OK).
- [ ] `headlines('005930','삼성전자')` → list[Headline](또는 정상 `[]`).
- [ ] `RegimeProvider().regime()` → `kospi_pbr` 실수치, `us_cape=None`.

### BAL-1-m1a §5 검증 게이트 (인용, BAL-11 해당분)
- [ ] `KrSource().ohlcv('005930')` close_raw·52주·sma200 실수치 (§5).
- [ ] `fundamentals` PER·PBR·`per_pctile_5y` (§5).
- [ ] headlines 정상 (§5).
- [ ] `RegimeProvider().regime()` kospi_pbr (§5).
- [ ] `validate_response`가 빈 응답을 `EmptyResponseError`로 올림(단위 테스트로 증명; E2E 동작 검증 자체는 BAL-12).
- [ ] `pytest -q` green, 편집 파일 `py_compile` 통과 (§5).

> **경계**: `db.upsert_*` 적재 → `latest_price` row 반환(§5 3번째 항목)은 **BAL-12(W-3) E2E** 소유. BAL-11은 어댑터가 올바른 DTO를 반환하는 것까지.

---

## 8. Out of Scope (W1 아님 — 끌려가지 말 것)

- **US/FX 어댑터**(`sources/us.py`, `sources/fx.py`) — W2.
- **regime US 절반(Shiller CAPE)** — W2(`us_cape`는 W1에서 `None` 고정).
- **`collect.py` 배치·`_collect_market`·`TokenBucket` rate limiter·`collect_run` 적재** — W2(04 §8). kr.py는 어댑터만, 페이싱·격리·게이트는 collect 책임.
- **`db.upsert_*` 호출 / E2E 적재 증명** — BAL-12(W-3).
- **metrics 계산**(`valuation`/`trend`/percentile degrade 라벨링) — W3(04 §9, §6). 어댑터는 `per_pctile_5y` 수치만 산출, 라벨은 metrics.
- **DART(OpenDartReader) `report_date` 정밀 확보** — W2 보조(W1은 `None` 허용).
- **`sources/etf.py`(ETF 구성)** — W2.
- **`FxRate` DTO·`SecurityCard`·`BriefingDoc` 등 LLM/렌더 DTO** — W2+/W3+ (BAL-1-m1a §2.4).
- **KOSDAQ(.KQ) 서브마켓 해소** — W2(W1=005930 KOSPI만).
