# BAL-1 / M1a 오케스트레이션 — 데이터 스파이크 (BAL-8~12)

> 생성: /harness-workflow (ultrathink). SSoT 계약 = `TECH-DESIGN.md §15` + `docs/05-database.md` + `docs/04-backend.md`.
> 목적: BAL-8~12를 **하나의 결합된 수직 슬라이스**로 안전하게 구현하기 위한 의존 그래프 · 모듈 seam 계약 · 실행 파동(wave) · per-issue 범위/DoD를 고정한다.
> 브랜치: `feat/bal-1-m1a-spike` (베이스 `7a0a815`). 상태: 에픽 BAL-1 + BAL-8~12 = 진행 중.
> 미해결 결정: **전건 해소됨 → `docs/BAL-1-m1a-decisions.md`** (유보 0건, needs_user 0건).

---

## 0. 왜 5-way 병렬 fanout이 아니라 wave인가 (결정 기록)

`harness-workflow`의 다중 부모(2+) 규칙은 `parallel-fanout.md`(Tier-1 worktree × N)로 분기한다. 그러나 그 프로토콜은 **서로 격리된 패키지를 가진 별개 에픽들**을 위한 것이다(예시: 2개 에픽 산하 5이슈, 충돌행렬 대부분 0).

BAL-8~12는 정반대다:
- **단일 에픽(BAL-1) 산하 형제 5개**, 하나의 수직 슬라이스. 최종 산출물(BAL-12)이 곧 **통합 그 자체**.
- 작은 Python 모듈 5개(db/tickers/calendar/sources.kr/validate). 1인 며칠 작업 규모.
- 명확한 의존 DAG 존재(아래 §1).

→ 5 worktree fanout은 **과설계**(토큰 12–20×, 머지 직렬화 오버헤드). 대신 **의존 DAG를 반영한 wave 실행**이 정답.

---

## 1. 의존 그래프 (DAG)

```
BAL-8  app/db.py        (connect/init_schema/조회·upsert)  ─┐
BAL-9  app/tickers.py   (to_source/ETF whitelist/classify) ─┼─► BAL-11 app/sources/kr.py ─► BAL-12 validate + 005930 E2E
BAL-10 app/calendar.py  (XKRX/XNYS 거래일)                  ─┘     (ohlcv/funda/headlines)     (EmptyResponseError + 적재 증명)
        3 격리 foundation (파일 비중복, 충돌 0)              consumer(8·9·10 import)     integration(전부 의존)
```

| 이슈 | 모듈 | 하위작업 | 역할 | 의존 |
|------|------|---------|------|------|
| **BAL-8** | `app/db.py` | BAL-43, BAL-44 (BAL-45=중복, **skip**) | DB 토대 | 없음 |
| **BAL-9** | `app/tickers.py` | 없음 | 티커 정규화/분류 | 없음 |
| **BAL-10** | `app/calendar.py` | 없음 | 거래일 로직 | 없음 |
| **BAL-11** | `app/sources/kr.py` | BAL-46, BAL-47, BAL-48 | KR 어댑터 | **8·9·10** |
| **BAL-12** | validate + E2E | 없음 | 통합 증명 | **8·9·10·11** |

> ⚠️ **BAL-45**는 BAL-44의 중복(`[중복·삭제요망]`). 본 워크플로에서 계획/구현/전이 **대상 제외**. MCP 삭제 API 없음 → 사용자가 Jira UI에서 수동 삭제.

---

## 2. 모듈 seam 계약 v2 (canonical 정합 — 드리프트 방지의 핵심)

> ⚠️ **v2 정정**: 최초 v1 초안은 일부 시그니처가 canonical(`04-backend §4.2/§5.1/§5.3/§6.1/§7.1/§7.5` + `TECH-DESIGN §15.2`)과 어긋났다(dev-guide verify 단계가 적발). 아래 **v2가 정본**이며, dev-guide 코드블록이 v1과 다르게 보이면 **v2(=canonical)** 를 따른다. 충돌 시 §15 > 04 > 05 순.

### 2.1 `app/db.py` (BAL-8)
```python
def connect(db_path: str = "data/ballast.db") -> sqlite3.Connection
    # row_factory=Row, PRAGMA foreign_keys=ON, journal_mode=WAL, busy_timeout=5000  (05 §0)
def init_schema(conn) -> None
    # 05 §1.1~1.9 DDL 전량(9테이블) CREATE TABLE IF NOT EXISTS + 인덱스 ②④ + ux_holdings_user_ct + settings seed(§15.5)  ← BAL-43
def latest_price(conn, ct: str) -> sqlite3.Row | None     # 05 §3.1  ┐
def latest_funda(conn, ct: str) -> sqlite3.Row | None     # 05 §3.2  ├ BAL-44
def latest_fx(conn, pair: str = "USDKRW") -> sqlite3.Row | None      # ┘
# 슬라이스 E2E(BAL-12 DoD)에 필요 — 명시 하위작업엔 없지만 본 슬라이스 범위에 포함:
def upsert_price(conn, row: OHLCV) -> None    # row=frozen dataclass, 내부 asdict→named bind (05 §4.1 ON CONFLICT)
def upsert_funda(conn, row: Funda) -> None
def upsert_fx(conn, row: FxRate) -> None      # fx 적재 자체는 W2지만 헬퍼는 db.py에 존재
```
> 🔎 **발견①(범위 보강)**: BAL-12 DoD가 `db.upsert_*` 적재를 요구 → 최소 upsert 3종을 db.py(BAL-8) 범위에 포함.
> 🔎 **발견②(seed 함정, dev-guide 적발)**: `config.SETTINGS_DEFAULTS`는 dict가 아니라 `@dataclass(frozen=True) Settings` 인스턴스 → seed 루프는 `dataclasses.asdict(SETTINGS_DEFAULTS).items()`로 순회(직접 `.items()`/`[key]` 금지). value는 `str()` 변환(컬럼 TEXT). `ON CONFLICT DO NOTHING`(사용자값 보존).
> 🔎 **결정(upsert 인자형)**: upsert_*는 **frozen dataclass(OHLCV/Funda/FxRate)** 를 받아 내부에서 `asdict`로 named-bind. (caller가 dict 변환 안 함.) named param은 **컬럼 전체명(`:canonical_ticker` 등)** — 05 §4.1의 약어(`:ct/:td`)는 예시일 뿐, asdict 키와 1:1 정합(decisions #2). `connect(db_path=...)` 인자형 확정(decisions #1).

### 2.2 `app/tickers.py` (BAL-9) — canonical 04 §5.1/§5.3
```python
def to_source(source: Literal["yf","finnhub","stooq","pykrx","fdr","fmp","dart"], ct: str, market: str) -> str
    # to_source('yf','005930','KR')->'005930.KS' / ('stooq','VOO','US')->'voo.us' / ('finnhub','BRK.B','US')->'BRK-B'
CORE_ETF_WHITELIST: frozenset[str]              # 04 §5.2 정본 내용(069500/360750/379800/VOO/SPY/VTI/IVV/ITOT/VT)
def classify_category(h: HoldingInput) -> Literal["core","satellite"] | None
    # 1)h.category 우선 2)stock→satellite 3)etf→whitelist면 core 아니면 None 4)그외 None
```
> 🔎 **정정**: v1의 `to_source(canonical, market=None)`·`classify_category(ticker, instrument)`는 오류. canonical은 `source` 인자 포함 + `classify_category(HoldingInput)`.
> 🔎 **결정(KOSPI/KOSDAQ, decisions #3)**: W1=**무조건 .KS**(005930=KOSPI), KOSDAQ frozenset 분기 코드는 **W2에서 추가**(유보 아님 — wave 분할 확정). 거래일 판정은 KOSPI/KOSDAQ 동일 XKRX라 영향 없음.

### 2.3 `app/calendar.py` (BAL-10) — canonical 04 §6.1 (인자순서 `(market, d)`)
```python
def is_trading_day(market: Literal["KR","US"], d: date) -> bool
def prev_trading_day(market: Literal["KR","US"], d: date) -> date
def expected_trade_date(market: Literal["KR","US"], today: date) -> date   # KR=오늘(거래일), US=직전거래일
# pandas_market_calendars: KR=XKRX, US=XNYS
```
> 🔎 **정정**: v1은 인자순서 `(d, market)`·`expected_trade_date(market, now: datetime)`가 오류. canonical은 `(market, d/today: date)`. mcal 기본 휴장표 신뢰(임시공휴일 보정은 PoC 범위 밖).

### 2.4 `app/models.py` (W1 부분 기여) — canonical 04 §4.2 (첫 필드 `canonical_ticker`)
> §15.2 DTO 전량은 W3이나 W1 코드가 참조하는 것만 선정의: **HoldingInput(mutable) + OHLCV/Funda/Headline/RegimeRow(frozen)**. FxRate는 W2(fx 어댑터)와 함께. SecurityCard/BriefingDoc 등 LLM·렌더 DTO는 W3+.
```python
@dataclass class HoldingInput: instrument; name; canonical_ticker=None; market=None; ...; category=None  # 04 §4.1 (mutable)
@dataclass(frozen=True) class OHLCV:  canonical_ticker; trade_date; close_raw: float; close_adj: float; ccy; week52_high: float|None; week52_low: float|None; sma200: float|None  # 윈도우<200 시 None (decisions #4)
@dataclass(frozen=True) class Funda:  canonical_ticker; trade_date; per; pbr; div_yield; per_pctile_5y; pbr_pctile_5y; report_date
@dataclass(frozen=True) class Headline: title; url; source
@dataclass(frozen=True) class RegimeRow: as_of; kospi_pbr; us_cape   # upsert 매핑 as_of→trade_date, us_cape→shiller_cape
```
> 🔎 **정정**: v1의 `OHLCV.ct`는 오류 → `canonical_ticker`(04 §4.2). FxRate는 W1 미사용(W2로 이동).
> 🔎 **발견③(공유파일 — W-1 병렬 충돌)**: `models.py`는 BAL-8(OHLCV/Funda)·BAL-9(HoldingInput)·BAL-11(Headline/RegimeRow)이 함께 닿는다. 즉 W-1의 "파일 비중복"이 깨지는 유일 지점. → **W-1a로 이 5개 DTO를 먼저 단독 정의·커밋**한 뒤 W-1b 3-way 병렬(각자 `from app.models import ...`)로 충돌 제거.

### 2.5 `app/sources/kr.py` (BAL-11) — canonical 04 §4.3/§7.2 Protocol 구현
```python
class KrSource:   # PriceSource + NewsSource Protocol
    def ohlcv(self, ct: str) -> OHLCV            # BAL-46: FDR/pykrx 조정 윈도우 fresh fetch → close_raw/adj/52주/sma200
    def fundamentals(self, ct: str) -> Funda     # BAL-47: pykrx 5년 PER/PBR/배당, percentile은 어댑터가 계산(04 §7.2)
    def headlines(self, ct: str, name: str) -> list[Headline]   # BAL-48 일부: 네이버, 빈응답=[] (뉴스 0건은 정상)
    # 내부: tickers.to_source('pykrx'/'fdr', ct, 'KR'), calendar.expected_trade_date('KR', today). @retry(3)+validate_response.
```
> 🔎 **정정**: v1 `headlines(self, ct) -> list[dict]`는 오류 → `headlines(self, ct, name) -> list[Headline]`(04 §4.3). 뉴스 빈응답은 `[]` 반환(validate_response 미적용).

### 2.6 `app/sources/regime.py` (BAL-48 일부) — canonical 04 §7.5
```python
class RegimeProvider:   # RegimeSource Protocol
    def regime(self) -> RegimeRow   # W1=KR 절반만: kospi_pbr=pykrx 지수 PBR, us_cape=None
```
> 🔎 **정정**: regime KR은 kr.py가 아니라 **별도 `sources/regime.py`**(04 §7.5). BAL-48("headlines + regime KR")은 두 파일에 걸침: headlines→kr.py, regime→regime.py.

### 2.7 `app/sources/__init__.py` 공통 가드 (04 §7.1) — **W-2 시작 시 먼저 생성**
```python
class EmptyResponseError(Exception): ...
def retry(times: int = 3, backoff: float = 1.5)                      # 지수 백오프, 마지막 실패는 raise
def validate_response(rows: int, latest: str, expected: str) -> None # rows==0 → EmptyResponseError (05 §1.8 OK=데이터 실재)
```
> 🔎 **정정 + 순서 의존**: v1 `validate_response(df_or_obj, *, context)`는 오류 → canonical `(rows:int, latest:str, expected:str)`. 이 가드/retry는 **BAL-11(kr.py)이 import** 하므로 BAL-12가 아니라 **W-2 시작에 먼저 만든다**. BAL-12(W-3)는 이를 쓰는 **빈응답 동작 테스트 + 005930 E2E 증명** 담당.

---

## 3. 실행 파동 (Wave 3→1→1)

| Wave | 이슈 | 병렬성 | 산출 게이트(DoD 요약) |
|------|------|--------|------------------------|
| **W-1** | **W-1a** `models.py` W1 DTO 선정의(단독 커밋) → **W-1b** BAL-8 ∥ BAL-9 ∥ BAL-10 | W-1a 직렬 → W-1b 3-way 병렬 | W-1a: HoldingInput/OHLCV/Funda/Headline/RegimeRow import 가능 / db: init_schema 후 **9테이블** + connect PRAGMA / tickers: to_source 변환표 테스트 green / calendar: 005930 expected_trade_date 정확 |
| **W-2** | **W-2a** `sources/__init__.py` 가드(retry·validate_response·EmptyResponseError) **먼저** → **W-2b** BAL-11 `kr.py`(+Tier-2: ohlcv∥funda∥headlines) + `regime.py` KR | W-2a 직렬 → W-2b Tier-2 병렬 | 가드 import 가능 / `KrSource().ohlcv('005930')` close_raw·52주·sma200 실수치 / fundamentals PER·PBR·per_pctile_5y / headlines / `RegimeProvider().regime()` kospi_pbr |
| **W-3** | BAL-12 | ❌ 순차 | 빈응답→EmptyResponseError 동작 테스트 / 005930 fetch→upsert→latest_* row / `tests/test_tickers.py` green |

병렬은 **계획·구현 시작**만 동시. W-1 3종 커밋 후 W-2 진입(가드 먼저 → kr.py/regime.py), W-2 후 W-3.
> 🔎 **순서 의존(정정)**: `validate_response`/`retry`/`EmptyResponseError`(공통 가드)는 BAL-12 소유로 분류됐으나 BAL-11이 import → **W-2 시작(W-2a)에 먼저 생성**. BAL-12는 그 가드의 빈응답 동작 검증 + E2E 담당.

---

## 4. degraded-session 운영 규약 (현재 세션 = thinking/ 루트)

현재 Claude 세션은 `thinking/`에서 떠서 `investbrief/.claude` hook·`bal-*` 에이전트가 **자동 로드되지 않음**. 그래서 오케스트레이터(메인 루프)가 수동 대체:

| 자동화(원래 hook/agent) | 수동 대체 |
|--------------------------|-----------|
| auto context-inject (jira-plan/execute 강제) | 본 워크플로가 시퀀스를 직접 수행 |
| compile-check (PostToolUse, py_compile) | 편집 후 `python3 -m py_compile <file>` 직접 실행 |
| review-gate (PreToolUse git commit) | 커밋 전 aggregate-verdict 수동 확인 |
| `bal-*` 리뷰 에이전트 fan-out | general-purpose 에이전트에 `bal-*.md` 지침을 주입해 동일 구동 |
| persist-checkpoint (Stop) | `.claude/runtime/checkpoint.md` 수동 작성 |

> 풀 자동화가 필요하면 `cd investbrief && claude` 재실행 후 `/harness-resume`.

브랜치 전략: 결합 슬라이스이므로 **단일 브랜치 `feat/bal-1-m1a-spike`** 에 이슈별 커밋(메시지에 `BAL-N`)으로 적재. 5 worktree 미사용.

---

## 5. 검증 게이트 (W1 통합 DoD, 로드맵 08 §Week1)
- [ ] `python -c "from app.sources.kr import KrSource; print(KrSource().ohlcv('005930'))"` → close_raw·52주·sma200 실수치
- [ ] `fundamentals('005930')` → PER/PBR/배당 + per_pctile_5y(5년 백필)
- [ ] db.upsert_* 적재 후 `latest_price(conn,'005930')` row 반환
- [ ] `tests/test_tickers.py`: to_source 변환표 전 케이스 통과
- [ ] `validate_response`가 빈 응답을 `EmptyResponseError`로 올림
- [ ] `pytest -q` green, 편집 파일 `py_compile` 통과

## 6. Out of scope (W1 아님 — 끌려가지 말 것)
US/FX 어댑터(W2) · **regime US절반(CAPE)**(W2 — W1은 KR=KOSPI PBR만) · collect.py 배치/백필 · metrics 계산(W3) · models.py의 LLM/Card DTO·FxRate(W2+) · 프론트(W5) · 손익/수익률(G8).

## 7. Resume 포인터
- 상태: `.claude/runtime/workflow-state.json` (wave/slice_status)
- dev-guide: `docs/BAL-{8..12}-dev-guide.md`
- Sprint Contract: `.claude/runtime/sprint-contract/BAL-1.md`
- 재개: 본 문서 §3 wave 표의 첫 `pending` 부터.
