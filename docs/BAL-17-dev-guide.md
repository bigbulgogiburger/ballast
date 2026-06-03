# BAL-17 dev-guide — `app/collect.py` 일배치 통합자 (수집 오케스트레이션 + collect_run 게이트 + 백필)

> SSoT 우선순위: `docs/04-backend.md`(최우선) → `docs/05-database.md` → `docs/01-product-spec.md`.
> 시그니처 정본: `docs/BAL-2-w2-orchestration.md §2.5/§2.6/§2.7` (이 표를 벗어난 새 시그니처 발명 금지).
> ⚠️ **`TECH-DESIGN.md`는 레포에 없음**. W1 dev-guide가 인용한 `§15`는 부재 파일이므로 **04/05/01만 정본**으로 사용한다. W1 구현 정본 시그니처는 `docs/BAL-1-m1a-orchestration.md §2(v2)` + `docs/BAL-1-m1a-decisions.md`.
> 범위: W2 데이터 슬라이스의 **통합자**. 하위작업 BAL-51(`_collect_market`/`_collect_fx`/`_collect_regime` + `TokenBucket`), BAL-52(`_status_of` 5분기 + `missing_tickers` + `collect_run` upsert), BAL-53(백필 `--backfill`).

---

## 1. 요구사항 & 수용기준(AC)

### 이슈 요약
`app/collect.py`는 현재 W2 스텁(1줄 docstring, `collect.py:1`)이다. BAL-17은 이를 **일배치 통합자**로 채운다 — W2-2 어댑터 4종(us/fx/regime/etf) + W1 `kr.py` + W1/W2 `db.upsert_*`를 모두 import해 하루치 수집을 시장별로 격리 실행하고, 결과를 `collect_run`에 게이트 가능한 형태로 기록한다. collect는 **raw 적재까지만** 책임지고 지표 계산·라벨링은 하지 않는다(04 §9 = W3).

책임 4가지(04 §8.1~§8.6):
1. **`run_collect(mode)`** — 진입점. `holdings=db.auto_holdings(1)` → KR·US 시장 루프 `_collect_market` → `_collect_fx` → `_collect_regime`. 각 시장/축 독립 격리(04:517-524).
2. **`_collect_market`** — 거래일 판정 → auto 종목 루프(try ohlcv+validate→upsert_price / funda→upsert_funda / headlines→upsert_news) → 종목 격리 catch(`n_fail++`, `missing.append`) → `_status_of` → `upsert_collect_run`(04:537-560).
3. **`_status_of` + `_collect_fx`/`_collect_regime`** — 5분기 status 판정(04:568-577), FX 실패 시 `collect_run(FX,FAIL)`, regime degrade(NULL 유지).
4. **`TokenBucket`** + **백필 모드** — rps blocking limiter(04:587-594), `mode='backfill'` 시 status=`BACKFILL` + FMP percentile 250req/day 분할(04:578-582).

### 수용기준 (검증 게이트 = orchestration §5 / 04 §8)
- **AC1** `run_collect(mode='backfill')` → KR+US auto 종목(약 30종) price/funda row 적재(05:582 백필 완료 = 모든 auto 종목 row 존재).
- **AC2** 시장별 `collect_run` row 1건씩 — 거래일 정상=`OK`(n_ok>0 **AND** 최신일자 일치, 05:209/358), 휴장=`OK_HOLIDAY`, 일부 실패=`PARTIAL`(missing_tickers JSON 배열), 백필=`BACKFILL`. **FAIL만 게이트 차단**(05:211).
- **AC3** `_collect_fx` → `collect_run(market='FX', status='OK')` + `fx_snapshot` USDKRW row. fx 실패 시 `FAIL`(04:489-491, 05:162).
- **AC4** `_collect_regime` → `market_regime` row에 `shiller_cape`(US) + `kospi_pbr`(KR). 한쪽 실패=그 필드만 NULL(degrade, 04:533) — collect 전체를 죽이지 않음.
- **AC5** **종목 격리**: 단일 종목 raise가 배치를 죽이지 않음 — `missing_tickers`에 격리 기록(04:446/557).
- **AC6** **빈응답 가드**: `validate_response(rows=0)` → `EmptyResponseError` → `n_fail` 집계(OK 오인 방지, 04:457/05:209).
- **AC7** **백필 분할**: FMP 250req/day 한도 시 `per_pctile_5y` NULL + `status='BACKFILL'`, 다음날 이어받기(TokenBucket FMP 소진 후 status 유지, 04:581).
- **AC8** `_status_of`가 5분기(OK_HOLIDAY는 `_collect_market` 선분기) — `backfill→BACKFILL / n_ok==0→FAIL / n_fail>0→PARTIAL / else→OK`(04:568-573).
- **AC9** `pytest -q` green + 편집 파일 `py_compile` 통과. **외부 API(stooq/yf/finnhub/fmp/ecos/pykrx/네이버/yale)는 전량 모킹**.

---

## 2. 영향 파일

| 파일 | 동작 | 비고 |
|---|---|---|
| `app/collect.py` | **수정**(스텁→구현) | 본 이슈 본체. `run_collect`/`_collect_market`/`_collect_fx`/`_collect_regime`/`_status_of`/`TokenBucket` |
| `app/db.py` | **수정**(W2 헬퍼 선커밋, orchestration §2.6 / W2-1) | `auto_holdings` + `upsert_news`/`upsert_market_regime`/`upsert_collect_run` 신규 + `upsert_fx` FxRate 전환. ⚠️ **U3**: BAL-17 귀속 vs BAL-8 carryover(§미해결). 본 가이드는 W2-1 선커밋(orchestration §3) 전제 |
| `app/models.py` | **수정**(W2-1 선행, orchestration §2.2) | `FxRate` frozen DTO 신규(BAL-14 소유). collect는 **읽기 의존**만 |
| `app/sources/__init__.py` | **수정 가능성**(U2) | `validate_response` 날짜검사. **본 가이드 기본안 = collect 인라인**(아래 §4/U2) → `__init__.py` 불변 채택 |
| `app/sources/us.py` / `fx.py` / `regime.py` / `etf.py` | **읽기 전용 의존** | W2-2 어댑터(BAL-13~16). collect가 import해 호출만. 본 이슈에서 수정 금지 |
| `app/sources/kr.py` | **읽기 전용 의존**(W1) | `KrSource().ohlcv/fundamentals/headlines` 호출 |
| `app/calendar.py` | **읽기 전용 의존**(W1) | `is_trading_day`/`expected_trade_date`(calendar.py:20,34) |
| `app/config.py` | **읽기 전용 의존** | `FINNHUB_API_KEY`/`FMP_API_KEY`/`ECOS_API_KEY`/`SEC_USER_AGENT`(config.py:23-30) + rps 설정. 사용 시점 fail-fast는 어댑터 책임 |
| `tests/test_collect.py` | **신규** | 본 가이드 §6 — 외부 API 전량 모킹 |

> ⚠️ **04:530은 `db.upsert_regime`**, 05 §1.7 + orchestration §2.6은 **`upsert_market_regime`**. SSoT(04>05)는 04이나 04:530은 약식 표기 코드 예시(`upsert_regime`)이고, orchestration §2.6이 W2 db seam 계약 정본으로 `upsert_market_regime`을 못박았다 → 본 가이드는 **`upsert_market_regime`** 채택(테이블명 정합). 명시 불일치는 §미해결 U6.

---

## 3. 구현 단계 (하위작업 분해)

### 단계 W2-1 (선행) — `app/db.py` W2 헬퍼 + `models.FxRate` (orchestration §2.2/§2.6)
> BAL-17 통합의 **선행물**. orchestration §3에서 W2-1 선커밋으로 박힘. collect 코딩 전 존재해야 한다.

- `models.FxRate`(frozen, 05:154-160 컬럼 1:1):
  ```python
  @dataclass(frozen=True)
  class FxRate:
      trade_date: str   # 'YYYY-MM-DD'
      pair: str         # 'USDKRW'
      rate: float
  ```
- `db.upsert_fx(conn, row: FxRate)` — 기존 `db.py:225-233` 본체 재사용, `dict(row)`→`dataclasses.asdict(row)` 전환(named-bind 1:1, decisions §3.4).
- `db.upsert_news(conn, rows: list[Headline], ct: str, trade_date: str)` — 05:168-176 `news_snapshot`, PK(ct,trade_date,url) → **`ON CONFLICT DO NOTHING`**(url 중복 무시, 05:354). `rows` 각 `Headline.title/url/source` + 인자 `ct/trade_date` 바인딩.
- `db.upsert_market_regime(conn, row: RegimeRow)` — 05:181-188, `as_of→trade_date`·`us_cape→shiller_cape` 매핑(models.py:73), `ON CONFLICT DO UPDATE`.
- `db.upsert_collect_run(conn, trade_date, market, status, n_ok, n_fail, missing_tickers)` — 05:193-207, PK(trade_date,market), `ON CONFLICT DO UPDATE`(05:364-369). `missing_tickers`=JSON 배열 문자열.
- `db.auto_holdings(user_id: int = 1) -> list` — `tracking='auto'` 행 조회(04:520). 반환 row는 `.market`/`.canonical_ticker`/`.name` 접근 가능해야 함(`_collect_market` 루프가 사용, 04:546).
- **검증**: `db.upsert_fx(conn, FxRate(...))` 라운드트립, news/regime/collect_run upsert 후 되읽기 row 반환, `py_compile`+`pytest` green.

### 단계 A — BAL-51-1: `TokenBucket` (04 §8.6, :587-594)
rps 초과 시 blocking sleep. 소스별 인스턴스(FMP/finnhub/naver).
```python
class TokenBucket:
    def __init__(self, rps: float) -> None: ...
    def acquire(self) -> None: ...   # rps 초과 시 blocking sleep
```
- 최소 구현: 마지막 토큰 발급 시각 기준 `1/rps` 간격 보장(monotonic clock). 과설계 금지 — 정밀 토큰 누적 버킷 불요, "직전 호출과 최소 간격" 수준이면 04:589 충족.
- FMP 백필은 일일 250req 소진 시 다음날 이어받기(status=`BACKFILL` 유지, 04:593) — 이 카운팅은 collect 레벨 책임이나 **W2 PoC에선 rps blocking까지만**, 일일 한도 누적 추적은 백필 분할 로직(단계 F)에서 status 유지로 흡수.
- **검증**: `acquire()` 2회 연속 호출 간 경과시간 ≥ `1/rps`(시간은 `time.monotonic` 모킹 또는 짧은 rps로 검증).

### 단계 B — BAL-51-2: `_collect_market` (04 §8.2, :537-560)
거래일 판정 → auto 종목 loop → 종목 격리.
```python
def _collect_market(market, holdings, today, mode) -> None:
    if not calendar.is_trading_day(market, today):
        db.upsert_collect_run(conn, today, market, "OK_HOLIDAY", 0, 0, "[]")
        return                                   # 정상 skip, 배너 오발동 방지(04:542)
    src = kr_source if market == "KR" else us_source
    n_ok, n_fail, missing = 0, 0, []
    expected = calendar.expected_trade_date(market, today)
    for h in (x for x in holdings if x.market == market):
        try:
            ohlcv = src.ohlcv(h.canonical_ticker)            # @retry 내장(어댑터)
            validate_response(rows=1, latest=ohlcv.trade_date, expected=expected.isoformat())
            # (U2 기본안) 날짜검사 인라인: if ohlcv.trade_date != expected.isoformat(): raise
            db.upsert_price(conn, ohlcv)
            db.upsert_funda(conn, src.fundamentals(h.canonical_ticker))
            db.upsert_news(conn, src.headlines(h.canonical_ticker, h.name),
                           h.canonical_ticker, ohlcv.trade_date)
            n_ok += 1
        except Exception as e:                               # 종목 격리(04:557)
            n_fail += 1; missing.append(h.canonical_ticker)
            log.warning("collect fail %s: %s", h.canonical_ticker, e)
    status = _status_of(n_ok, n_fail, mode)
    db.upsert_collect_run(conn, today, market, status, n_ok, n_fail, json.dumps(missing))
```
- 핵심: **종목 단위 try/except**가 배치를 죽이지 않음(AC5/04:446). `missing`은 JSON 배열로 직렬화(`json.dumps`, 05:201).
- `conn`은 `run_collect`이 열어 격리 함수에 전달(아래 §4 conn 소유). `_collect_market(market, holdings, today, mode, conn)` 시그니처에 conn 추가 — orchestration §2.5는 conn 미표기지만 db 호출에 필요(타입 추가, 의미 모순 없음).
- **검증**: 휴장→`OK_HOLIDAY` row + 루프 미진입. 거래일 3종목 중 1종 raise→`PARTIAL` + missing 1건. 전건 raise→`FAIL`.

### 단계 C — BAL-51-3: `_collect_fx` + `_collect_regime` (04 §8.1, :523-533)
```python
def _collect_fx(today, mode, conn) -> None:
    try:
        db.upsert_fx(conn, fx_source.usdkrw())               # FxRate 반환(04:486)
        db.upsert_collect_run(conn, today, "FX", "OK", 1, 0, "[]")
    except Exception as e:
        db.upsert_collect_run(conn, today, "FX", "FAIL", 0, 1, "[]")  # USD 자산 보류(04:489)
        log.warning("fx collect fail: %s", e)

def _collect_regime(today, conn) -> None:
    # 04:528 이미 이번 달 row 있으면 skip (collect 레벨 DB 체크가 1차, U5)
    try:
        db.upsert_market_regime(conn, regime_source.regime())
    except Exception as e:
        log.warning("regime collect fail (degrade): %s", e)  # NULL 유지 → metrics degrade
```
- fx 실패는 **collect 전체를 죽이지 않음** — `collect_run(FX,FAIL)`로 게이트가 USD 자산만 보류(05:162). regime 실패도 degrade(전체 비차단, 04:532).
- regime 월단위 skip: `_collect_regime`이 이번 달 row 존재 시 호출 생략(04:528, U5 — collect DB 체크 1차).
- **검증**: fx 정상→FX OK row + fx_snapshot. fx raise→FX FAIL row(예외 전파 안 함). regime 한쪽 NULL row 적재.

### 단계 D — BAL-52: `_status_of` 5분기 + `collect_run` upsert (04 §8.4, :568-577)
```python
def _status_of(n_ok, n_fail, mode) -> str:
    if mode == "backfill":  return "BACKFILL"     # 게이트 차단 아님
    if n_ok == 0:           return "FAIL"          # 전부 실패 → 게이트 차단
    if n_fail > 0:          return "PARTIAL"        # 일부 실패
    return "OK"
```
- **5번째 분기 `OK_HOLIDAY`는 `_status_of`가 아니라 `_collect_market`의 선분기**(거래일 판정 직후 early return, 단계 B). `_status_of`는 4분기 — 04:569-573 그대로. (05:358-362가 5종 status를 열거하나 OK_HOLIDAY 진입은 거래일 판정 경로.)
- `upsert_collect_run`은 `missing_tickers`를 **이미 직렬화된 JSON 문자열**로 받음(`json.dumps(missing)`은 caller에서, 05:201). 헬퍼는 재직렬화하지 않음.
- **검증**: `_status_of`를 순수함수로 단위 테스트 — (backfill,5,0)→BACKFILL / (daily,0,3)→FAIL / (daily,2,1)→PARTIAL / (daily,3,0)→OK.

### 단계 E — `run_collect` 진입점 조립 (04 §8.1, :517-524)
```python
def run_collect(mode: Literal["daily", "backfill"] = "daily") -> None:
    today = date.today()
    conn = db.connect()
    holdings = db.auto_holdings(user_id=1)
    for market in ("KR", "US"):
        _collect_market(market, holdings, today, mode, conn)
    _collect_fx(today, mode, conn)
    _collect_regime(today, conn)
```
- 시장 독립 격리: KR 실패가 US 수집을 막지 않음(루프 단위 — 각 `_collect_market`이 내부에서 종목 격리 + 자체 collect_run 기록).
- **검증**: 모킹된 어댑터로 `run_collect('backfill')` 1회 → KR/US/FX collect_run 3건 + market_regime 1건 + price/funda row 적재(AC1).

### 단계 F — BAL-53: 백필 모드 `--backfill` (04 §8.5, :578-582)
- `mode='backfill'`: 어댑터 bulk fetch가 200일+ 시계열 즉시 반환 → 52주/SMA200 day-0 확보(04:580). `_status_of`가 `BACKFILL` 반환(게이트 비차단).
- FMP percentile 250req/day 한도 → 분할 동안 `per_pctile_5y` NULL + `status='BACKFILL'`. 다음날 이어받기(TokenBucket FMP 소진 후 status 유지, 04:581).
- CLI 진입(04:373 `scripts/run_collect.py --bootstrap` 대응): `run_collect`에 `mode='backfill'` 전달하는 얇은 래퍼. **본 이슈 범위 = `run_collect(mode='backfill')` 동작까지**; `scripts/` CLI 파일 신규 여부는 §8 참조(W2 PoC는 함수 호출까지면 충분).
- **검증**: `mode='backfill'` → 모든 시장 collect_run status=`BACKFILL`. percentile 한도 모킹 시 funda row의 `per_pctile_5y=None` 보존.

### 단계 G — `py_compile` + 단위 테스트 그린 (degraded-session 수동 대체, orchestration §4)
`python3 -m py_compile app/collect.py app/db.py app/models.py` → `pytest -q tests/test_collect.py`.

---

## 4. 인터페이스 (정본 = orchestration §2.5/§2.6/§2.7, 그대로 구체화)

> 새 시그니처 발명 금지. 아래는 orchestration §2.5의 시그니처를 파라미터/반환형 수준으로만 구체화한 것이며 1:1 대응한다. `conn` 파라미터는 orchestration이 미표기하나 db 호출에 필수 → **타입 추가일 뿐 의미 모순 없음**(BAL-8 dev-guide §4 `conn` 좁히기 선례 답습).

```python
from typing import Literal
from datetime import date

def run_collect(mode: Literal["daily", "backfill"] = "daily") -> None: ...
#   04:517-524. today=date.today() → db.auto_holdings(1) → KR/US _collect_market
#   → _collect_fx → _collect_regime. 각 축 독립 격리. 반환 None.

def _collect_market(market: str, holdings: list, today: date,
                    mode: str, conn) -> None: ...
#   04:537-560. 거래일 판정→종목 loop(ohlcv+validate→upsert_price/funda/news)
#   →종목 격리 catch→_status_of→upsert_collect_run. OK_HOLIDAY 선분기.

def _collect_fx(today: date, mode: str, conn) -> None: ...
#   04:523. fx_source.usdkrw()→db.upsert_fx(FxRate). 실패→collect_run(FX,FAIL).

def _collect_regime(today: date, conn) -> None: ...
#   04:526-533. regime_source.regime()→db.upsert_market_regime. 실패=degrade(NULL 유지).
#   이번 달 row 존재 시 skip(04:528, U5).

def _status_of(n_ok: int, n_fail: int, mode: str) -> str: ...
#   04:568-573. backfill→BACKFILL / n_ok==0→FAIL / n_fail>0→PARTIAL / else→OK. (순수함수)

class TokenBucket:                                  # 04:587-594
    def __init__(self, rps: float) -> None: ...
    def acquire(self) -> None: ...                  # rps 초과 시 blocking sleep
```

**db.py W2 헬퍼(W2-1 선커밋, orchestration §2.6 — collect가 호출)**:
```python
def auto_holdings(conn, user_id: int = 1) -> list: ...                 # 04:520 tracking='auto'
def upsert_fx(conn, row: FxRate) -> None: ...                          # asdict(row), 05:154-160
def upsert_news(conn, rows: list[Headline], ct: str, trade_date: str) -> None: ...  # 05:168-176, DO NOTHING
def upsert_market_regime(conn, row: RegimeRow) -> None: ...           # 05:181-188, as_of→trade_date
def upsert_collect_run(conn, trade_date, market, status, n_ok, n_fail, missing_tickers) -> None: ...  # 05:193-207
```

**`validate_response`(W1 가드 — 시그니처 불변, orchestration §2.7)**:
```python
def validate_response(rows: int, latest: str, expected: str) -> None  # __init__.py:41, 불변
#   W1 본체=rows==0만. 날짜검사(latest!=expected)는 U2 기본안=collect 인라인 → 본체 불변.
```

**정합 확인**:
- `run_collect`/`_collect_market`/`_collect_fx`/`_collect_regime`/`_status_of`/`TokenBucket` — orchestration §2.5와 자모 단위 일치(파라미터명·기본값·반환형). `conn` 추가만 superset.
- `mode` 파라미터: orchestration §2.5 `run_collect`은 `Literal["daily","backfill"]` 명시 → 그대로 채택. 내부 `_collect_*`의 `mode`는 `str`로 전달.
- `upsert_market_regime` 명칭: 04:530 `upsert_regime`(약식 예시)이 아니라 orchestration §2.6 정본 채택(U6).

---

## 5. 엣지 & 리스크

| # | 상황 | 영향 | 대응 (본 모듈) |
|---|---|---|---|
| E1 | **휴장일 수집** | 새 row 미생성 → "데이터 없음" 오인 가능 | `is_trading_day` False → `OK_HOLIDAY` collect_run + early return. 배너 오발동 방지(04:542). latest_* fallback이 직전 거래일 재사용(05:209) |
| E2 | **빈 응답(Stooq 빈 CSV 등)** | "조용한 실패"가 OK처럼 보임 | `validate_response(rows=1,...)` 호출 — 어댑터가 rows=0이면 `EmptyResponseError`→catch→n_fail. **collect는 rows를 어댑터 반환으로 산정**(단일 종목 ohlcv 성공=1), 빈응답 승격은 어댑터/가드 책임(04:457) |
| E3 | **단일 종목 raise** | 배치 전체 중단 위험 | 종목 단위 try/except로 격리, `missing`에 기록(04:557). 배치 계속 진행(AC5) |
| E4 | **fx 실패** | USD 자산 평가 불가 | `collect_run(FX,FAIL)` 기록(예외 비전파). 게이트가 USD 자산+USD 현금 보류(05:162-163). collect는 FAIL 기록까지만 |
| E5 | **regime 한쪽/양쪽 실패** | CAPE 또는 KOSPI PBR NULL | degrade — 그 필드만 NULL row 적재 또는 upsert skip. collect 전체 비차단(04:532). 라벨링은 W3 |
| E6 | **백필 FMP 250req/day 소진** | percentile 미완 | `per_pctile_5y` NULL + `status='BACKFILL'` 유지, 다음날 이어받기(04:581). TokenBucket FMP 소진 → blocking 또는 skip(status 유지) |
| E7 | **`per_pctile_5y` NULL(워밍업)** | funda row에 NULL | 정상 — 컬럼 NULL 허용(05:1.4). collect는 NULL 보존, degrade 라벨은 W3 metrics |
| E8 | **조정가 stale(배당/분할)** | 과거 close_adj 갱신 필요 | **어댑터(us/kr.ohlcv) 책임** — 윈도우 통째 fresh 재계산(04:562-565). collect는 호출만, `upsert_price`의 `ON CONFLICT DO UPDATE`가 덮어쓰기 보장(05:349) |
| E9 | **news url 중복** | PK 충돌 | `upsert_news`가 `ON CONFLICT DO NOTHING`(05:354) — 중복 무시. collect는 headlines 전건 전달 |
| E10 | **CHECK 제약 위반(잘못된 status/market)** | `IntegrityError` | `_status_of` 반환은 5종 enum 내, market은 KR/US/FX만 → 정상 경로 미발생. 위반 시 전파(조용히 틀린 값 차단, 05:204-205) |
| E11 | **API 키 부재(FMP/Finnhub/ECOS)** | 어댑터 호출 실패 | 사용 시점 fail-fast는 **어댑터 책임**(orchestration §4). collect 입장에선 종목 raise→격리. 키 누락 전체 차단은 W2 어댑터 구현 |
| E12 | **WAL 동시성·락** | 배치 write 중 대시보드 read | `db.connect`의 `busy_timeout=5000`(05 §0). collect는 단일 conn 재사용 — 트랜잭션 경계는 헬퍼 self-commit(BAL-8 §4) |
| E13 | **`upsert_regime` vs `upsert_market_regime` 명칭** | 호출 NameError | orchestration §2.6 정본=`upsert_market_regime`. 04:530 약식 예시에 끌려가 `upsert_regime` 호출 금지(U6) |
| E14 | **conn 소유 모호(헬퍼 self-commit vs 배치 트랜잭션)** | 부분 커밋 | 본 가이드 기본 = 헬퍼 self-commit(BAL-8 db.py:206/222 선례). 종목 격리와 정합(한 종목 커밋이 다음 종목과 독립). 배치 단일 트랜잭션은 W2 PoC 범위 밖 |

---

## 6. 테스트 계획 (외부 API 전량 모킹)

**파일: `tests/test_collect.py`** (pytest). collect는 외부 네트워크(stooq/yf/finnhub/fmp/ecos/pykrx/네이버/yale)에 닿는 어댑터를 호출하므로 **어댑터 객체(`kr_source`/`us_source`/`fx_source`/`regime_source`)를 전량 모킹**(`monkeypatch`/`unittest.mock`). DB는 `db.connect(":memory:")`+`init_schema` 실제 사용(로컬 SQLite, 네트워크 없음).

픽스처:
```python
@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.init_schema(c)
    yield c
    c.close()

@pytest.fixture
def fake_sources(monkeypatch):
    # collect 모듈의 kr_source/us_source/fx_source/regime_source를 Mock으로 치환
    # ohlcv→OHLCV(...), fundamentals→Funda(...), headlines→[Headline(...)],
    # usdkrw→FxRate(...), regime→RegimeRow(...)
    ...
```

| 테스트명 | 마크 | 검증 대상 | 핵심 단언 |
|---|---|---|---|
| `test_status_of_backfill` | unit | `_status_of` (단계 D) | `(.,.,'backfill')` → `'BACKFILL'` (n_ok/n_fail 무관) |
| `test_status_of_fail` | unit | `_status_of` | `(0,3,'daily')` → `'FAIL'` |
| `test_status_of_partial` | unit | `_status_of` | `(2,1,'daily')` → `'PARTIAL'` |
| `test_status_of_ok` | unit | `_status_of` | `(3,0,'daily')` → `'OK'` |
| `test_token_bucket_throttles` | unit | `TokenBucket` (단계 A) | `acquire()` 2회 간 경과 ≥ `1/rps` (작은 rps 또는 monotonic 모킹) |
| `test_collect_market_holiday` | unit | `_collect_market` (E1) | `is_trading_day=False` 모킹 → `collect_run` status=`OK_HOLIDAY`, missing=`'[]'`, 어댑터 미호출 |
| `test_collect_market_all_ok` | integration | `_collect_market` (단계 B) | 거래일+3 auto 종목 모두 성공 → status=`OK`, n_ok=3, price/funda/news row 적재 |
| `test_collect_market_isolation` | integration | 종목 격리 (E3/AC5) | 3종 중 1종 `ohlcv` raise → status=`PARTIAL`, n_fail=1, `missing_tickers`에 해당 ct, 나머지 2종 적재됨 |
| `test_collect_market_all_fail` | integration | 전건 실패 (AC8) | 전 종목 raise → status=`FAIL`, n_ok=0 |
| `test_collect_market_empty_response` | integration | 빈응답 가드 (E2/AC6) | 어댑터가 `EmptyResponseError` raise → n_fail 집계(OK 오인 안 함) |
| `test_collect_fx_ok` | integration | `_collect_fx` (단계 C/AC3) | `usdkrw→FxRate` → `fx_snapshot` USDKRW row + `collect_run(FX,OK)` |
| `test_collect_fx_fail` | integration | fx 실패 (E4) | `usdkrw` raise → `collect_run(FX,FAIL)`, 예외 비전파, fx_snapshot 무 |
| `test_collect_regime_both` | integration | `_collect_regime` (AC4) | `regime→RegimeRow(kospi_pbr, us_cape 둘 다)` → `market_regime` row 두 필드 채움 |
| `test_collect_regime_degrade` | integration | regime 한쪽 NULL (E5) | `us_cape=None`인 RegimeRow → row의 `shiller_cape` NULL, `kospi_pbr` 보존, 예외 비전파 |
| `test_run_collect_backfill_e2e` | integration | `run_collect` (AC1/AC7) | `mode='backfill'`, KR+US 종목 모킹 → collect_run 3건(KR/US/FX) 전부 status=`BACKFILL`, market_regime 1건, price/funda row 존재, `per_pctile_5y=None` 보존 |
| `test_run_collect_daily_ok` | integration | `run_collect` daily | 거래일 모킹 → KR/US collect_run=`OK`, FX=`OK` |
| `test_missing_tickers_is_json_array` | unit | missing 직렬화 (단계 B) | `collect_run.missing_tickers`가 `json.loads` 가능한 배열 문자열 |

> ⚠️ **모킹 경계**: collect 테스트는 어댑터 **객체**를 모킹할 뿐 `db.upsert_*`/`init_schema`/`calendar`는 실제 사용(로컬·결정적). 어댑터 내부 외부 API 계약 테스트는 BAL-13~16 소관. `date.today()`는 테스트에서 거래일/휴장일 제어 위해 모킹 또는 `calendar.is_trading_day` 모킹으로 우회.

---

## 7. DoD (Definition of Done)

로드맵 08 §Week2 + orchestration §5에서 **collect.py에 해당하는 항목**:

- [ ] (orchestration §5) `run_collect(mode='backfill')` → KR+US auto 종목 약 30종 price/funda row 적재(05:582 백필 완료 판정).
- [ ] (orchestration §5) 시장별 `collect_run` row — `OK`(n_ok>0 AND 최신일자 일치) / `OK_HOLIDAY` / `PARTIAL`(missing_tickers JSON) / `BACKFILL`. **FAIL만 게이트 차단**(05:211).
- [ ] (orchestration §5) `_collect_fx` → `collect_run(FX,OK)` + `fx_snapshot` USDKRW row, 실패 시 `FAIL`(USD 보류 경로).
- [ ] (orchestration §5) `_collect_regime` → `market_regime` row에 `shiller_cape`+`kospi_pbr`, 한쪽 실패=그 필드만 NULL(degrade).
- [ ] (orchestration §5) **백필 분할**: FMP 250req/day 한도 시 `per_pctile_5y` NULL + `status='BACKFILL'`, 다음날 이어받기.
- [ ] (orchestration §5) **종목 격리**: 단일 종목 raise가 배치를 죽이지 않음 — `missing_tickers` 기록.
- [ ] (orchestration §5) **빈응답 가드**: `validate_response(rows=0)` → `EmptyResponseError` → n_fail 집계.
- [ ] (orchestration §5) `pytest -q` green, 편집 파일 `py_compile` 통과(degraded-session 수동 대체, §4).
- [ ] `_status_of` 5분기(OK_HOLIDAY는 `_collect_market` 선분기) 단위 테스트 통과(04:568-577).
- [ ] **외부 API 전량 모킹** — collect 테스트에 실제 네트워크 호출 0건.
- [ ] 코딩 규칙: PEP8 + 전 함수 타입주석. `print()` 미사용(`logging` 사용).

---

## 8. Out of scope (W2 / BAL-17 아님)

- **db.py W2 헬퍼·`FxRate` DTO 정의 자체** — orchestration §3 W2-1 **선커밋**(BAL-14/db). 본 이슈는 이들을 **호출**(존재 전제). ⚠️ U3: 헬퍼 귀속이 BAL-8 carryover로 재배치되면 본 이슈는 호출만.
- **어댑터 내부 구현**(us/fx/regime/etf의 외부 API 폴백 체인·조정가 재계산·percentile) — BAL-13~16(orchestration §2.1~2.4). collect는 Protocol 호출만.
- **metrics 계산**(drift/core-sat/valuation/trend/regime/dca 5종, 04 §9 / W3) — collect는 raw 적재까지.
- **LLM/브리핑 생성**(Claude 호출, SecurityCard/BriefingDoc DTO, 04 §10+ / W3+).
- **프론트**(Jinja2 렌더·freshness badge·신선도 배너, 03 / W5).
- **손익/수익률**(lots·매입환율, G8 / R2).
- **룩스루 ETF 비중 분해**(F-19, 01:248 R2 — BAL-16 코어 판정 보강과도 별개).
- **임시공휴일/KOSDAQ frozenset 확장**(calendar/tickers, decisions: 별도 슬라이스).
- **실패 알림(ntfy.sh/Telegram 푸시, 04:597)** — 04 §8.7. W2 PoC는 `collect_run` 기록까지, 푸시 연동은 운영 단계.
- **`scripts/run_collect.py --bootstrap` CLI 파일 신규**(04:373) — 본 이슈는 `run_collect(mode='backfill')` **함수 동작**까지. CLI 래퍼 파일 생성 여부는 §미해결 U7.

---

## 미해결 질문
(04/05/01/orchestration 간 명시 불일치 또는 미정의 — 본문에 임의 가정을 주입하지 않고 모았다. orchestration §7 U1~U5와 연동.)

1. **U2(orchestration §7) — `validate_response` 날짜검사 소유**: `if latest != expected: raise`를 (a) `validate_response` 본체에 추가(공통 가드 변경, decisions §3.7) vs (b) `_collect_market` 인라인 비교(`sources/__init__` 불변, status PARTIAL/FAIL 직접 활용). **본 가이드 기본안 = (b) collect 인라인**(more surgical, decisions Q12 "stale 대조는 collect.py"와 정합). 구현 시 1택 고정 필요. → **결정 주체: 구현자(BAL-17)**.
2. **U5(orchestration §7) — regime 월단위 캐시 위치**: collect `_collect_regime`의 DB row 존재 체크(04:528) vs regime.py 내부 메모 캐시(04:499). **본 가이드 기본안 = collect DB row 체크 1차**(04:528 명시), 이중 캐시 안 함. → **결정 주체: 구현자(BAL-17)**.
3. **U3(orchestration §7) — db W2 헬퍼 귀속**: `upsert_news`/`upsert_market_regime`/`upsert_collect_run` + `upsert_fx` FxRate 전환 + `auto_holdings`를 (a) BAL-17 슬라이스 W2-1 선커밋 vs (b) BAL-8 db.py carryover. **본 가이드 기본안 = (a)**(collect 의존물, orchestration §3). BAL-8을 "DB 헬퍼 단일 소유"로 강제 시 (b). → **결정 주체: 사용자/오케스트레이터**.
4. **U6(신규) — `upsert_regime` vs `upsert_market_regime` 명칭**: 04:530은 `db.upsert_regime`, 05 §1.7 + orchestration §2.6은 `upsert_market_regime`. SSoT(04>05)는 04이나 04:530은 약식 예시 코드. **본 가이드 = `upsert_market_regime`(orchestration §2.6 정본, 테이블명 정합)**. 04:530 문구가 오기인지 확인 필요. → **결정 주체: 사용자(문서 정합)**.
5. **U7(신규) — `scripts/run_collect.py` CLI 신규 여부**: 04:373/582는 `scripts/run_collect.py --bootstrap` 백필 진입을 가정. 본 이슈가 (a) `run_collect(mode='backfill')` 함수까지만 vs (b) `scripts/` CLI 래퍼 파일도 신규. **본 가이드 기본안 = (a)**(W2 PoC는 함수 호출까지, CLI는 운영 단계). → **결정 주체: 사용자(스코프)**.
6. **U-conn(신규) — `_collect_*` conn 전달 방식**: orchestration §2.5 시그니처는 conn 미표기이나 db 호출에 필수. **본 가이드 = `run_collect`이 `db.connect()` 1회 → 격리 함수에 인자 전달**(superset, 의미 모순 없음). 전역 conn vs 인자 전달 확정 필요(헬퍼 self-commit 전제는 BAL-8 선례). → **결정 주체: 구현자(BAL-17)**.

> 📌 본 가이드의 시그니처 정본 = `docs/BAL-2-w2-orchestration.md §2.5/§2.6/§2.7`(v1). 미해결 질문 1~3은 orchestration §7 U2/U5/U3과 동일 항목 — 그 결정에 종속된다.
> ⚠️ **TECH-DESIGN.md 부재 재확인**: W1 dev-guide 일부가 `§15.x`를 인용하나 해당 파일은 레포에 없다. 본 가이드는 **04/05/01 + orchestration**만 인용하고 `§15` 참조를 답습하지 않았다.
