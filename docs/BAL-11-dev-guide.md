# BAL-11 dev-guide — `app/sources/kr.py` (KR 어댑터: 시세·재무·뉴스 + 레짐 KR)

> 작성 페르소나: stack 최고 Python 개발자 · 대상 슬라이스: W1 / M1a 데이터 스파이크 (에픽 BAL-1)
> 계약 우선순위(SoT): `TECH-DESIGN.md §15` > `docs/05-database.md` > `docs/04-backend.md`.
> seam 시그니처 정본: `docs/BAL-1-m1a-orchestration.md §2`.
> ⚠️ 본 가이드는 **임의 가정을 본문에 주입하지 않는다**. §2 seam 표와 §15 사이의 불일치는 전부 `## 미해결 질문`으로 모았고, 그 항목들이 해소되기 전에는 해당 시그니처를 확정 구현하지 말 것.

---

## 1. 목표 & 배경

### 이슈 요약
`app/sources/kr.py` 의 W0 스텁(1줄 docstring)을 KR 시장 데이터 어댑터 `KrSource` 로 구현한다. 한 종목(삼성전자 `005930`)에 대해 **시세(조정/미조정 종가·52주·SMA200)**, **펀더멘털(5년 PER/PBR/배당 + percentile)**, **뉴스 헤드라인**, 그리고 **KR 레짐(KOSPI PBR)** 을 무료 소스(pykrx · FinanceDataReader · 네이버 검색 API)에서 긁어 §2.4 의 frozen dataclass 로 반환하는 것을 증명한다("무료 데이터가 진짜 긁히는가" — 08 §Week1 목표).

### W1 슬라이스(BAL-1) 내 역할/의존
- **위치**: 의존 DAG(`BAL-1 §1`)의 **consumer 노드**. foundation 3종(BAL-8 db / BAL-9 tickers / BAL-10 calendar)을 import 한다. 통합 증명(BAL-12)이 본 어댑터의 출력을 `db.upsert_*` → `latest_*` 로 흘려 E2E 를 닫는다.
- **Wave**: `W-2`. foundation 3종이 슬라이스 브랜치에 머지된 뒤 진입. 본 이슈 내부는 **Tier-2 병렬**(BAL-46 ohlcv ∥ BAL-47 fundamentals ∥ BAL-48 headlines+regime) 가능 — 세 메서드가 서로의 상태를 공유하지 않으므로.
- **상위 의존 인터페이스(읽기 전용 계약)**:
  - `tickers.to_source(...)` — canonical `005930` → 소스 표기 변환 (BAL-9 / 04 §5.1). ⚠️ 시그니처 형태가 §2.2 와 04 §5.1 사이에서 갈린다 → 미해결 질문 Q4.
  - `calendar.expected_trade_date(market, ...)` — KR 기대 거래일 (BAL-10 / 04 §6.1). ⚠️ 두 번째 파라미터 타입이 §2.3 과 04 §6.1 사이에서 갈린다 → 미해결 질문 Q5.
- **하위 의존(반환형)**: §2.4 의 `OHLCV` / `Funda` dataclass. 이들은 W1 에 **부분 기여**로 `app/models.py` 에 선정의해야 한다(§2.4 발견 노트 — 전체 DTO 는 W3). `headlines` 반환형은 미해결 질문 Q2 참조.
- **안정성 계약**: 각 메서드는 `@retry(3)` + `validate_response` 로 감싼다(04 §7.1, §12). 외부 네트워크 의존(pykrx/FDR/네이버)은 테스트에서 전부 모킹.
- **핵심 불변식**: 조정 윈도우는 **매 호출마다 소스에서 통째로 다시 받아** 52주/SMA200 을 그 자리에서 재계산한다. 캐시된 과거 `close_adj` 를 누적 사용 금지(05 §1.3 stale 방지 / 04 §8.3).

---

## 2. 영향 파일

| 파일 | 동작 | 근거 |
|---|---|---|
| `app/sources/kr.py` | **수정**(스텁 → `KrSource` 구현 본체) | 본 이슈 |
| `app/models.py` | **수정/부분 기여**: `OHLCV`·`Funda` frozen dataclass 선정의 (반환형). `Headline` 추가 여부는 Q2 결론에 따름 | §2.4 발견 노트, 04 §4.2 |
| `app/sources/__init__.py` | **수정(가능성)**: `validate_response` / `EmptyResponseError` 가 BAL-12 에서 여기에 놓일 예정(§2.6 "위치 제안"). 본 이슈가 먼저 필요로 하면 **선언만** 끌어와 import. 소유권은 BAL-12 → Q6 | §2.6, 04 §7.1 |
| `tests/test_sources_kr.py` | **신규**: 어댑터 모킹/계약 테스트 | testing.md |
| `tests/test_kr_calc.py` | **신규**: 순수 계산(52주/SMA200/percentile) 단위 테스트 | testing.md, §6 |

> `app/tickers.py`·`app/calendar.py`·`app/db.py` 는 **수정하지 않는다**(BAL-9/10/8 소유, W-1 에서 확정). 본 이슈는 그 공개 함수만 호출.
> `sources/regime.py` 는 **만들지 않는다** — 04 §7.5 가 regime 을 별도 모듈로 두지만, BAL-48 분해는 "regime KR" 을 본 이슈 범위로 끌고 온다. 모듈 배치 충돌은 Q3.

---

## 3. 구현 단계

> 권장 순서: **0(models 선정의) → 공통 데코레이터 확인 → BAL-46 → BAL-47 → BAL-48**. Tier-2 병렬로 갈 경우 step 0 와 데코레이터 합의를 **선행 머지**한 뒤 46/47/48 을 분기.

### Step 0 — 반환형 선정의 (`app/models.py`)
§2.4 의 `OHLCV`/`Funda` frozen dataclass 를 `app/models.py` 에 추가한다. **필드명·타입은 §15.2(=04 §4.2)를 정본으로 따른다**(§2.4 발견 노트의 약식 표기 `ct:` 가 아니라 `canonical_ticker:` — Q1).
- `OHLCV(canonical_ticker, trade_date, close_raw, close_adj, ccy, week52_high, week52_low, sma200)`
- `Funda(canonical_ticker, trade_date, per, pbr, div_yield, per_pctile_5y, pbr_pctile_5y, report_date)`
- `ccy: Literal["KRW","USD"]`, nullable 필드는 `float | None` / `str | None`.
- 검증 포인트: `python3 -m py_compile app/models.py` 통과 + `OHLCV(...)` / `Funda(...)` 인스턴스화 시 frozen 동작(재할당 시 `FrozenInstanceError`).

### Step 1 — 공통 안정성 데코레이터 합의 (`app/sources/__init__.py` 또는 kr 내부)
`@retry(3)` 와 `validate_response`/`EmptyResponseError` 사용 계약을 확정. `validate_response` 의 **소유는 BAL-12**(§2.6)이나, 본 어댑터가 빈 DF 를 차단하려면 호출 지점이 필요하다 → Q6 으로 소유/타이밍 확정. 합의 전까지는 어댑터 내부에서 `if df.empty: raise EmptyResponseError(...)` 형태로 **호출 계약만** 맞춰 두고, 공용 함수가 머지되면 교체.
- `@retry(times=3, backoff=1.5)`: 지수 백오프, 마지막 실패는 raise(collect 가 격리, 04 §7.1).
- 검증 포인트: 데코레이터가 3회 시도 후 마지막 예외를 그대로 올림(단위 테스트, §6).

### Step 2 — BAL-46 `ohlcv(self, ct: str) -> OHLCV` (조정 윈도우 fresh fetch)
핵심 로직:
1. `tickers.to_source(...)` 로 `005930` → pykrx/FDR 표기 변환. KR 은 pykrx 가 6자리 그대로, FDR/yf 는 `.KS`/`.KQ` 접미(04 §5.1).
2. `calendar.expected_trade_date("KR", ...)` 로 KR 기대 거래일(`expected`)을 구한다.
3. **조정 종가 윈도우(최소 200영업일 + 52주 커버 ⇒ 안전하게 ~260영업일+α)** 를 소스에서 한 번에 받는다. FDR/pykrx 의 조정종가(`close_adj`) 시계열.
4. 빈 DF 차단: `validate_response`(행수>0 + 최신일자 == `expected` ±허용, 05 §1.8).
5. **그 자리에서 재계산**(캐시 누적 금지):
   - `close_adj` = 윈도우 마지막 행 조정종가, `close_raw` = 윈도우 마지막 행 미조정종가(소스가 둘 다 제공해야 함 — Q7).
   - `week52_high`/`week52_low` = 최근 252영업일 `close_adj` 의 max/min(05 §1.3 "조정가 기준").
   - `sma200` = 최근 200영업일 `close_adj` 평균.
6. `OHLCV(...)` 로 반환. `ccy="KRW"`, `trade_date` = 윈도우 최신 거래일(ISO `YYYY-MM-DD`).
- 검증 포인트:
  - `KrSource().ohlcv('005930')` → `close_raw`·`week52_high/low`·`sma200` 가 **실수치**(BAL-1 §5 DoD #1, 08 §Week1 DoD).
  - **윈도우 부족 시(상장 200일 미만 등) 거동 정의 필요** → Q8.
  - 단위 테스트: 알려진 시계열 fixture 로 52주/SMA200 산식 정확성 검증(외부 호출 모킹).

### Step 3 — BAL-47 `fundamentals(self, ct: str) -> Funda` (5년 PER/PBR/배당 percentile)
핵심 로직:
1. pykrx `get_market_fundamental` 로 **5년 PER/PBR/배당 시계열** 수집(04 §7.2). **제공자 계산값만 사용, 자체 가격×EPS 재계산 금지**(05 §1.4 / 04 §7.3 degrade 노트 / §6).
2. 빈/결측 차단: `validate_response`.
3. 최신값 = 시계열 마지막 PER/PBR/`div_yield`. **음수/NaN PER(적자)** 는 `None` 으로 저장(밴드 제외·라벨링은 metrics 레이어, 05 §1.4).
4. **percentile 계산**: `per_pctile_5y` = 현재 PER 이 5년 분포에서 차지하는 백분위(%). `pbr_pctile_5y` 동일. 산식 정밀 정본은 §6 / §15.6(metrics) — 어댑터가 percentile 을 계산할지, 원시 시계열만 넘기고 percentile 은 collect/metrics 가 계산할지 **책임 경계가 불명확** → Q9.
5. percentile 산출 불가(5년 데이터 부족·결측) → `per_pctile_5y=None`(NULL 허용, 05 §1.4 "워밍업"). 음수 PER 다수로 분포가 깨지면 percentile 제외 처리(§6).
6. `report_date`: 재무 실제 기준일. pykrx 펀더는 report_date 를 직접 주지 않을 수 있음 → `None` 허용(05 §1.4, §3.3 NULL 은폐 주의). DART 확보는 04 §7.2 에서 "보조"이며 **W1 범위 아님** → `None` 기본.
- 검증 포인트:
  - `fundamentals('005930')` → PER/PBR/배당 + `per_pctile_5y`(5년 백필 OK) (BAL-1 §5 DoD #2, 08 §Week1 DoD #2).
  - 단위 테스트: 알려진 5년 시계열 fixture 로 percentile 산식 검증 + 음수 PER → `per=None` + percentile NULL 경로.

### Step 4 — BAL-48 `headlines(...)` + 레짐 KR(KOSPI PBR)
핵심 로직(headlines):
1. 네이버 검색 API(뉴스)로 종목 관련 헤드라인 N건 수집(04 §7.2). `naver_client_id`/`naver_client_secret` 은 `config.load()` 에서(04 §2). **헤드라인 + 링크만, 본문 없음**(05 §1.6 / §5).
2. 반환 형태가 §2.5(`list[dict]`)와 §15.2/04 §4.2(`list[Headline]`, 인자 `name` 포함)에서 갈린다 → **Q2**. 결론 전까지 `Headline` dataclass 경로(§15 우선)를 가정하되 본문 확정 금지.
3. `validate_response` 로 빈 응답 차단(0건이 정상일 수 있는지 vs 실패인지 정책 → Q10).

핵심 로직(regime KR):
4. pykrx 지수 PBR(KOSPI)로 KR 레짐을 수집(04 §7.5 / 05 §1.7). 04 §7.5 의 정본 인터페이스는 `RegimeProvider.regime() -> RegimeRow`(별도 모듈). BAL-48 은 이를 `kr.py` 로 끌어오므로 **메서드 시그니처·모듈 배치가 §2 에 미정의** → Q3.
- 검증 포인트:
  - `headlines(...)` 가 N건 반환(BAL-1 §3 wave 표 W-2 게이트).
  - KOSPI PBR 가 실수치로 수집됨(모킹 계약 테스트).
  - 레짐 반환형/배치는 Q3 해소 후 확정.

---

## 4. 인터페이스 (정본 = `BAL-1 §2` seam 표)

> **새 시그니처 발명 금지.** 아래는 §2 표를 그대로 옮기고 §15/05/04 로 구체화한 것이다. §2 와 §15(또는 04/05)가 충돌하는 항목은 `[CONFLICT→Qn]` 으로 표시하고 본문 확정 대신 미해결 질문으로 넘긴다.

### 4.1 `app/sources/kr.py` — `KrSource` (정본 §2.5)
```python
class KrSource:
    def ohlcv(self, ct: str) -> OHLCV: ...
        # BAL-46. 조정 윈도우 fresh fetch → close_raw/close_adj/week52_high/week52_low/sma200.
        # 예외: 빈 DF/최신일 불일치 → EmptyResponseError(validate_response). 3회 재시도 후 실패는 raise.

    def fundamentals(self, ct: str) -> Funda: ...
        # BAL-47. pykrx 5년 PER/PBR/배당 → per_pctile_5y/pbr_pctile_5y(NULL 허용).
        # 예외: 동일. 음수/NaN PER → per=None. report_date 미확보 → None.

    def headlines(self, ct: str) -> list[dict]: ...
        # BAL-48. §2.5 정본 시그니처는 (ct) -> list[dict].
        # [CONFLICT→Q2] §15.2/04 §4.2 NewsSource.headlines(self, ct: str, name: str) -> list[Headline]
        #   (인자 name 추가 + 반환 list[Headline]). §15 우선 규칙상 §15 형태가 맞을 가능성 — Q2 에서 확정.
        # [SCOPE→Q3] regime KR(KOSPI PBR) 도 BAL-48 범위. §2 에 KR 레짐 메서드 시그니처 미정의.
```
- 내부 의존(정본 §2.5 주석): `tickers.to_source`, `calendar.expected_trade_date` 사용. `@retry(3)` + `validate_response`.

### 4.2 반환형 (정본 §2.4)
```python
@dataclass(frozen=True)
class OHLCV:
    canonical_ticker: str   # [NOTE→Q1] §2.4 약식표기는 `ct`; §15.2/04 §4.2 정본은 `canonical_ticker`
    trade_date: str
    close_raw: float
    close_adj: float
    ccy: Literal["KRW", "USD"]
    week52_high: float
    week52_low: float
    sma200: float

@dataclass(frozen=True)
class Funda:
    canonical_ticker: str   # [NOTE→Q1] 동일
    trade_date: str
    per: float | None
    pbr: float | None
    div_yield: float | None
    per_pctile_5y: float | None
    pbr_pctile_5y: float | None
    report_date: str | None
```
- 필드 정합: 05 §1.3(price)·§1.4(funda) 컬럼과 1:1. §2.4 노트 "dev-guide 가 §15 대비 최종 확정" → **본 가이드는 §15.2 필드명을 채택**(Q1).

### 4.3 상위 의존 함수 (읽기 전용 — 본 이슈가 호출만)
```python
# tickers (BAL-9)
#   §2.2 정본:  to_source(canonical: str, market: str | None = None) -> str
#   [CONFLICT→Q4] 04 §5.1: to_source(source, ct, market) -> str  (source 인자 선두 + market 필수)
CORE_ETF_WHITELIST: frozenset[str]
classify_category(...)   # 본 이슈 미사용

# calendar (BAL-10)
#   §2.3 정본:  expected_trade_date(market: str, now: datetime) -> date
#   [CONFLICT→Q5] 04 §6.1: expected_trade_date(market, today: date) -> date  (2번째 인자 date)
is_trading_day(...); prev_trading_day(...)   # 본 이슈 ohlcv 검증 보조로 사용 가능
```

### 4.4 검증 유틸 (정본 §2.6, 소유=BAL-12)
```python
class EmptyResponseError(Exception): ...           # 위치 제안: app/sources/__init__.py
def validate_response(df_or_obj, *, context: str) -> None
    # 빈 응답을 OK 로 오인 금지(05 §1.8). [OWNERSHIP→Q6] 04 §7.1 시그니처와 형태 차이.
```

---

## 5. 엣지 & 리스크

| 케이스 | 증상 | 대응 |
|---|---|---|
| **빈 DF** (pykrx/FDR 가 특정 종목·기간에 0행) | 조용한 실패가 OK 로 오인 | `validate_response`(행수>0) → `EmptyResponseError`. `@retry(3)` 백오프 후 최종 raise(08 §Week1 리스크). |
| **최신일 불일치** | 전일/오래된 데이터를 당일로 오판정 | `validate_response` 가 `expected_trade_date` 와 최신 거래일 대조(05 §1.8 "최신일자 일치"). |
| **휴장일 호출** | 기대 거래일이 없음 | `calendar.expected_trade_date` 가 직전 거래일로 흡수(KR=오늘 거래일, 04 §6.1). 휴장 status(`OK_HOLIDAY`) 판정은 collect(W2) 소유 — 어댑터는 기대일과 대조만. |
| **조정가 stale** | SMA200/52주가 과거 캐시 누적으로 틀림 | **윈도우 통째 fresh 재계산**(05 §1.3 / 04 §8.3). 캐시 `close_adj` 를 입력으로 쓰지 않음. 이게 본 이슈의 1순위 불변식. |
| **윈도우 부족**(상장<200일·신규편입) | SMA200/52주 산출 불가 | 정책 미정 → **Q8**(NULL? 부분윈도우? `BACKFILL` 신호?). 05 §1.4 의 percentile 워밍업과 유사 처리 후보. |
| **음수/NaN PER**(적자) | percentile 분포 오염 | `per=None` 저장 + percentile 산출 시 제외(05 §1.4 / §6). 라벨링은 metrics. |
| **5년 percentile 결측** | `per_pctile_5y` 못 구함 | `None`(NULL 허용, 05 §1.4 "워밍업"). degrade("절대 PER만") 라벨은 W3 metrics 소유 — 어댑터는 NULL 만 전달. |
| **report_date NULL** | 신선도 배지가 실제보다 좋게 보임(MIN(report_date) NULL 무시) | `report_date: str | None` 유지(05 §3.3 경고). 어댑터는 미확보 시 `None` — 배지 '워밍업' 표시는 W3/badge 소유. |
| **네이버 0건** | 빈 헤드라인이 실패인지 정상인지 모호 | 정책 미정 → **Q10**. 종목/뉴스는 0건이 정상일 수 있어 ohlcv 와 다른 빈응답 정책 필요. |
| **외부 네트워크 의존** | 테스트 비결정성·CI 실패 | pykrx/FDR/네이버 호출 **전부 모킹**(범위 규칙). 순수 계산은 fixture 기반 단위 테스트로 분리. |

---

## 6. 테스트 계획

> 원칙(testing.md): **순수 계산 = 단위(필수)**, **어댑터 외부호출 = 모킹/계약**. pytest + `pytest.mark`.

### 6.1 `tests/test_kr_calc.py` (단위 — 외부 호출 없음, 필수)
| 테스트명 | 검증 |
|---|---|
| `test_sma200_from_window` | 알려진 200+행 `close_adj` fixture → SMA200 = 산술평균 정확 |
| `test_week52_high_low` | 252영업일 fixture → max/min 일치(조정가 기준) |
| `test_close_raw_vs_adj_distinct` | raw 와 adj 가 서로 다른 컬럼에서 옴(혼동 금지, 05 §1.3) |
| `test_per_pctile_5y_calc` | 5년 PER 분포 fixture → percentile 정확 |
| `test_negative_per_excluded` | 음수/NaN PER → `per=None` + percentile 에서 제외 |
| `test_pctile_null_when_insufficient` | 5년 미만/결측 → `per_pctile_5y is None` |

### 6.2 `tests/test_sources_kr.py` (계약/모킹)
| 테스트명 | 검증 |
|---|---|
| `test_ohlcv_returns_ohlcv_dataclass` | pykrx/FDR 모킹 → `OHLCV` 타입 + 실수치 필드(005930) |
| `test_ohlcv_empty_df_raises_empty_response` | 모킹이 빈 DF → `EmptyResponseError` (05 §1.8) |
| `test_ohlcv_stale_latest_raises` | 모킹 최신일 ≠ expected → `EmptyResponseError`/검증 실패 |
| `test_ohlcv_calls_to_source_and_expected_date` | `tickers.to_source`/`calendar.expected_trade_date` 호출 계약(mock assert) |
| `test_ohlcv_fresh_recompute_not_cached` | 윈도우 입력이 매 호출 소스에서 옴(캐시 누적 아님, 05 §1.3) |
| `test_retry_three_times_then_raise` | 모킹이 3회 예외 → `@retry(3)` 후 raise |
| `test_fundamentals_returns_funda` | pykrx fundamental 모킹 → `Funda` + PER/PBR/배당/percentile |
| `test_headlines_returns_n_items` | 네이버 모킹 → N건(반환형은 Q2 결론에 맞춤) |
| `test_regime_kr_kospi_pbr` | pykrx 지수 PBR 모킹 → KOSPI PBR 실수치(배치/시그니처는 Q3 후 확정) |

### 6.3 (BAL-12 소유, 본 이슈에서 green 의존 확인만)
- `tests/test_tickers.py`: `to_source` 변환표 전 케이스(08 §Week1 DoD #4) — BAL-9/12 소유. 본 이슈는 호출 형태가 통과하는지만 확인.

---

## 7. DoD (체크리스트)

> 인용: 08 §Week1 DoD + `BAL-1 §5` 검증 게이트. 본 이슈는 그중 **KR 어댑터에 귀속되는 항목**만 책임진다(나머지 db.upsert/latest·tickers·validate_response 는 BAL-8/9/12 와 공동).

- [ ] `python -c "from app.sources.kr import KrSource; print(KrSource().ohlcv('005930'))"` → `close_raw`·52주·`sma200` 가 **실수치** (08 §Week1 DoD #1 / `BAL-1 §5` 1번)
- [ ] `fundamentals('005930')` → PER/PBR/배당 + `per_pctile_5y`(5년 백필) (08 §Week1 DoD #2 / `BAL-1 §5` 2번)
- [ ] `headlines(...)` → 헤드라인 N건 (`BAL-1 §3` W-2 게이트)
- [ ] (BAL-12 와 공동) `db.upsert_*` 적재 후 `latest_price(conn,'005930')` row 반환 — 본 이슈는 **반환 OHLCV/Funda 가 upsert 입력 계약과 정합**함만 보증 (`BAL-1 §5` 3번 / 08 §Week1 DoD #3)
- [ ] `validate_response` 가 빈 응답을 `EmptyResponseError` 로 올림 — 어댑터가 **호출**하는 경로 확인(소유는 BAL-12, `BAL-1 §5` 5번 / 08 §Week1 DoD #5)
- [ ] 조정 윈도우 **통째 재계산** 불변식 테스트 green(05 §1.3 stale 방지)
- [ ] `pytest -q` green, 편집 파일 `python3 -m py_compile` 통과 (`BAL-1 §5` 6번)
- [ ] PEP8 + 타입주석 + frozen dataclass(반환형) 준수 (프로젝트 스타일 규칙)
- [ ] 외부 호출(pykrx/FDR/네이버) 테스트 전부 모킹 — 네트워크 비의존 CI green (범위 규칙)

---

## 8. Out of scope (W1 아님 — 끌려가지 말 것)

- **US/FX/regime(US 절반·CAPE) 어댑터** — `sources/us.py`·`sources/fx.py`·`sources/regime.py` US 부분은 W2(08 §Week2 / `BAL-1 §6`).
- **`collect.py` 배치·백필·rate limiter·`collect_run` 기록·`missing_tickers`** — W2(04 §8). 어댑터는 값만 반환, status/게이트 판정은 collect 소유.
- **metrics 계산**(drift/valuation/trend/regime 라벨·percentile→라벨 변환·degrade 문장) — W3(04 §9 / §6 / §15.6). 어댑터는 수치/NULL 만 전달.
- **`db.upsert_*`/`latest_*` 구현 자체** — BAL-8(W-1). 본 이슈는 입력 정합만.
- **`tickers.to_source` 변환표·`validate_response`/`EmptyResponseError` 구현 본체** — BAL-9 / BAL-12. 본 이슈는 호출.
- **DART(OpenDartReader) 공시·재무 보조 경로** — 04 §7.2 에서 "보조", W1 미구현(`report_date` 는 None 허용으로 우회).
- **models.py 의 LLM/Card DTO**(`SecurityCard`/`SecurityLLMOut`/`BriefingDoc`/`FreshnessBadge`/`HoldingRow`/`RegimeRow`/`PricedHolding`) — W3(08 §Week3). 본 이슈는 `OHLCV`/`Funda`(+가능 시 `Headline`)만 선기여.
- **프론트엔드·브리핑 파이프라인** — W4/W5.
- **손익/수익률(G8)** — 전 범위 제외.
