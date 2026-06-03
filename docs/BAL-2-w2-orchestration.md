# BAL-2 / W2 오케스트레이션 — 소스 어댑터 + collect 통합 (BAL-13~17)

> 생성: /harness-workflow (ultrathink). SSoT 계약 우선순위 = `docs/04-backend.md` > `docs/05-database.md` > `docs/01-product-spec.md`.
> ⚠️ **`TECH-DESIGN.md`는 레포에 없음**. W1 dev-guide가 참조한 `§15`는 부재 파일이므로 본 문서는 **04/05를 정본**으로 사용한다. W1 구현 정본 시그니처는 `docs/BAL-1-m1a-orchestration.md §2(v2)` + `docs/BAL-1-m1a-decisions.md`를 참조한다.
> 목적: BAL-13~17을 **단일 에픽 BAL-2의 수직 슬라이스**로 안전하게 구현하기 위한 의존 DAG · 모듈 seam 계약 · 실행 파동(wave) · per-issue 범위/DoD를 고정한다.
> 브랜치: `feat/bal-1-m1a-spike` 후속 (W1 = `app/db.py`/`tickers.py`/`calendar.py`/`sources/kr.py`/`regime.py`(KR절반)/`models.py` 일부 + `sources/__init__.py` 가드가 머지된 상태 전제).

---

## 0. 왜 5-부모 parallel-fanout이 아니라 wave인가 (과설계 근거)

`harness-workflow`의 다중 부모(2+) 규칙은 `parallel-fanout.md`(Tier-1 worktree × N)로 분기한다. 그러나 그 프로토콜은 **서로 격리된 패키지를 가진 별개 에픽들**(충돌행렬 대부분 0)을 위한 것이다.

BAL-13~17은 정반대다:
- **단일 에픽(BAL-2) 산하 형제 5개**, 하나의 수직 슬라이스. 최종 산출물 BAL-17(`collect.py`)이 곧 **통합 그 자체** — us/fx/regime/etf/kr 어댑터 전부 + db upsert 헬퍼를 import 하는 통합자.
- 작은 Python 모듈 4개(us/fx/etf + regime 보강) + 통합자 1개. 1인 며칠 작업 규모.
- 명확한 의존 DAG 존재(아래 §1). **공유파일 3종**(`regime.py`/`models.py`/`db.py`)이 병렬 경계를 가로지른다 → 격리 worktree 가정이 깨진다.

→ 5 worktree fanout은 **과설계**(토큰 12–20×, 머지 직렬화 오버헤드 + 공유파일 충돌 재머지). 대신 **공유파일을 선커밋한 뒤 의존 DAG를 반영한 wave 실행**이 정답. W1(BAL-1)과 동일 패턴.

---

## 1. 의존 그래프 (DAG)

```
                                       ┌─ BAL-13 app/sources/us.py    (PriceSource+NewsSource: Stooq→yf→Finnhub / FMP·EDGAR)
W2-1 공유파일 선커밋                    ├─ BAL-14 app/sources/fx.py    (FxSource.usdkrw → FxRate)        ─┐
  models.FxRate (신규 frozen DTO)  ───►├─ BAL-15 app/sources/regime.py(us_cape 채움; ⚠️ W1 기존 파일 수정) ─┼─► BAL-17 app/collect.py
  db W2 upsert 헬퍼                     └─ BAL-16 app/sources/etf.py   (코어 판정 보강 / 룩스루는 R2)      ─┘    (일배치 통합자:
   (upsert_news/regime/collect_run                                                                              _collect_market/_fx/_regime
    + upsert_fx를 FxRate로 전환)        W2-2 어댑터 4-way 병렬                                                  + TokenBucket + _status_of
                                       (BAL-13 ∥ BAL-14 ∥ BAL-15 ∥ BAL-16)                                     + 백필 + collect_run upsert)
                                                                                                              W2-3 통합 (us/fx/regime/etf/kr 전부 의존)
```

| 이슈 | 모듈 | 하위작업 | 역할 | 의존 | 공유파일 닿음 |
|------|------|---------|------|------|----------------|
| **BAL-13** | `app/sources/us.py` | BAL-49(시세), BAL-50(펀더+뉴스+재무) | US 어댑터 | `sources/__init__`(가드, W1) · `models`(OHLCV/Funda/Headline, W1) · `tickers`(W1) | `models.py`(읽기만) |
| **BAL-14** | `app/sources/fx.py` | 없음 | FX 어댑터 | **`models.FxRate`(W2-1 신규)** · `sources/__init__`(가드) | `models.py`(**FxRate 정의 = W2-1 선행**) |
| **BAL-15** | `app/sources/regime.py` | (BAL-48 잔여 — us_cape) | 레짐 US 절반 | W1 `regime.py` 기존 본체 | **`regime.py`(⚠️ W1 파일 in-place 수정)** |
| **BAL-16** | `app/sources/etf.py` | 없음 | ETF 코어 판정 보강 | `tickers.CORE_ETF_WHITELIST`(W1) | — (단, 스코프 모호 §7) |
| **BAL-17** | `app/collect.py` | BAL-51(_collect_*+rate limiter), BAL-52(_status_of+collect_run), BAL-53(백필) | 일배치 통합자 | **13·14·15·16 + kr(W1) + db upsert** | `db.py`(W2 upsert 헬퍼 호출) |

근거: 어댑터 4종은 `04 §7.3/7.4/7.5` Protocol 구현으로 서로 독립(종목 단위 격리, `04-backend.md:446`). collect는 `04 §8.1`이 명시하듯 `kr_source`/`us_source`/`fx`/`regime` + `db.upsert_*` 전부를 부르는 통합자(`04-backend.md:517-524`, `:537-560`).

> ⚠️ **공유파일 3종**:
> 1. **`regime.py`(BAL-15)** — W1이 만든 파일을 in-place 수정한다. W1 stub은 `us_cape=None` 플레이스홀더(decisions §3.8). BAL-15는 `kospi_pbr` 로직 유지 + `us_cape` 실제 fetch를 **단일 집중 블록**으로 삽입(decisions Q10). 다른 W2 이슈와 동시 편집 시 충돌하므로 W2-2 내에서 regime.py를 단독 소유한다.
> 2. **`models.py`(BAL-14)** — `FxRate` frozen DTO 신규. BAL-13(읽기)·BAL-17(읽기)이 의존 → **W2-1에서 먼저 정의·커밋**.
> 3. **`db.py`(BAL-17)** — W2 upsert 헬퍼(`upsert_news`/`upsert_market_regime`/`upsert_collect_run` + `upsert_fx`의 FxRate 전환)는 collect의 의존물이지만 소유 논쟁이 있다(§7). 본 문서는 **W2-1에서 db.py에 선커밋**으로 박는다.

---

## 2. 모듈 seam 계약 v1 (canonical 04/05 정합 — 드리프트 방지의 핵심)

> 시그니처가 dev-guide 코드블록과 어긋나 보이면 **본 §2(=canonical)** 를 따른다. 충돌 시 **04 > 05 > 01** 순. (`TECH-DESIGN.md`는 부재이므로 인용 금지.)

### 2.1 `app/sources/us.py` (BAL-13) — canonical 04 §7.3

```python
class UsSource:   # PriceSource + NewsSource Protocol (04 §4.3/§7.2 구조 동일)
    def ohlcv(self, ct: str) -> OHLCV
        # BAL-49: 1차 Stooq(pandas_datareader/stooq) → 2차 yfinance auto_adjust=True
        #         → Finnhub /quote(당일가 보조). 조정 윈도우(200일+) fresh fetch
        #         → close_raw/close_adj/52주/sma200 그 자리 계산 (04:475, 04:562-565)
    def fundamentals(self, ct: str) -> Funda
        # BAL-50: FMP 무료 5년 시계열(250req/day) → per/pbr/div_yield + per_pctile_5y 계산
        #         report_date=SEC EDGAR(edgartools) 보조 (04:476-477)
        #         ⚠️ PER/PBR은 제공자 계산값만 캐시, 자체 가격×EPS 재계산 금지 (04:481)
    def headlines(self, ct: str, name: str) -> list[Headline]
        # BAL-50: Finnhub 뉴스, 빈응답=[] (validate_response 미적용 — 04:478, decisions Q9)
    # 내부: tickers.to_source('stooq'/'yf'/'finnhub'/'fmp', ct, 'US'), @retry(3) + validate_response.
    #       KrSource와 동일하게 __init__ 무인자·무부작용(lazy) 계약 유지 (decisions Q10).
```
근거: `04-backend.md:471-479`(US 표), `:462-469`(PriceSource 폴백 체인), `:481`(SSoT §5 재계산 금지). DTO는 W1 `models.OHLCV/Funda/Headline` 재사용(04 §4.2). `OHLCV.week52_*`/`sma200`은 `float|None`(decisions §3.5) — US 신규편입 워밍업 종목에서 None 경로 실제 발현.

> 🔎 **degrade 규칙(04:481)**: FMP 한도가 빠듯하면 percentile을 "현재 PER vs 자기 5년 평균"으로 낮춤. `per_pctile_5y` NULL 허용 → metrics가 "워밍업 중" 라벨(W3). W2 어댑터는 NULL 반환까지 책임, 라벨링은 W3.

### 2.2 `app/sources/fx.py` (BAL-14) — canonical 04 §7.4

```python
class FxSource:   # FxSource Protocol
    def usdkrw(self) -> FxRate
        # 1차: ECB / 한국은행 ECOS(보조) → 2차: yfinance 'KRW=X'
        # 둘 다 실패 → raise → collect가 collect_run(market='FX', status='FAIL') 기록
        #   → briefing 게이트가 USD 자산 전체 보류 (04:485-491, 05:162-163)
```
근거: `04-backend.md:483-491`. ⚠️ **`FxRate` DTO는 W2 신규**(W1 models.py에 없음, decisions §3.8 / Q2). W2-1에서 정의:
```python
@dataclass(frozen=True)
class FxRate:   # 05 §1.5 fx_snapshot 컬럼 1:1 (asdict 키 = 전체명)
    trade_date: str   # 'YYYY-MM-DD'
    pair: str         # 'USDKRW'
    rate: float
```
근거: `05-database.md:154-160`(fx_snapshot DDL: trade_date/pair/rate, PK(trade_date,pair)). 필드명 = 컬럼 전체명으로 고정 → db.upsert_fx의 `asdict(row)` named-bind와 1:1(decisions §3.4 교차결정).

### 2.3 `app/sources/regime.py` (BAL-15) — canonical 04 §7.5 ⚠️ W1 파일 in-place 수정

```python
class RegimeProvider:   # RegimeSource Protocol (W1에서 이미 존재)
    def regime(self) -> RegimeRow
        # W1: kospi_pbr=pykrx 지수 PBR('1001'), us_cape=None   ← 기존
        # W2(BAL-15): us_cape = Shiller CAPE — Yale ie_data.xls(1차) / multpl 스크레이프(2차)
        #             월단위 캐시 재사용(같은 달이면 재호출 안 함). 한쪽만 실패 → 그 필드만 NULL.
```
근거: `04-backend.md:495-501`, `:504-509`(Yale ie_data.xls 1차·multpl 2차, 월단위 캐시, 한쪽 실패→NULL). **수정 지점 = 단 한 곳**: W1 `regime()` 내 `us_cape=None` 플레이스홀더를 실제 fetch로 교체(decisions §3.8 / Q10). **`kospi_pbr` 로직 절대 손대지 않음**(Surgical). `RegimeRow.us_cape → market_regime.shiller_cape` 매핑은 W1 계약 유지(05:181-188).

### 2.4 `app/sources/etf.py` (BAL-16) — canonical 04 §7.3/7.4 표 + 01 §F-19 ⚠️ 스코프 §7 참조

```python
# 스코프 확정(§7): W2 = 코어 판정 보강만. 룩스루 구성종목 분해는 R2(F-19)로 배제.
def is_core_etf(ct: str) -> bool
    # tickers.CORE_ETF_WHITELIST 멤버십 위임(W1이 이미 코어 판정 보유 — classify_category).
    # ⚠️ "발행사 메타 확인" 류 보강은 04/05/01에 시그니처·스키마·데이터소스 정본이 없어
    #     R2로 배제(decisions §1.4 Q3). W2 etf.py 산출이 0에 수렴 → 이슈 존속/연기는 needs_user U1.
```
근거: `01-product-spec.md:109`(F-19 룩스루 = §5), `:248`(**R2 = 룩스루 ETF 비중(F-19)** — 정확도 확장, R1 PoC 아님). `app/tickers.py:15-37` to_source + `CORE_ETF_WHITELIST`(W1)가 이미 코어 판정 보유(`01:42` AC4 화이트리스트 자동판정). ⚠️ 룩스루(KR pykrx PDF / US 발행사 CSV·etf-scraper 분해)는 **W2 범위 밖**(§7 결정 필요 — 본 문서 기본안 = R2 배제).

### 2.5 `app/collect.py` (BAL-17) — canonical 04 §8

```python
def run_collect(mode: Literal["daily","backfill"] = "daily") -> None
    # 04:517-524: today=date.today() → holdings=db.auto_holdings(user_id=1)
    #   → for market in ("KR","US"): _collect_market(market, holdings, today, mode)
    #   → _collect_fx(today, mode) → _collect_regime(today). 각 시장 독립 격리.

def _collect_market(market, holdings, today, mode) -> None
    # 04:537-560: is_trading_day False → upsert_collect_run(OK_HOLIDAY, missing="[]") return
    #   거래일 → expected=expected_trade_date(market, today)
    #   for h in holdings if h.market==market:
    #     try: ohlcv=src.ohlcv(ct); validate_response(rows=1, latest=ohlcv.trade_date, expected=...)
    #          upsert_price; funda=src.fundamentals; upsert_funda; upsert_news(headlines); n_ok++
    #     except: n_fail++; missing.append(ct); log.warning  ← 종목 격리
    #   status=_status_of(n_ok,n_fail,mode); upsert_collect_run(today,market,status,n_ok,n_fail,json.dumps(missing))

def _collect_fx(today, mode) -> None        # fx_source.usdkrw() → db.upsert_fx(FxRate). 실패→collect_run(FX,FAIL)
def _collect_regime(today) -> None          # 04:526-533: regime_source.regime() → db.upsert_market_regime; 실패=degrade(NULL 유지)

def _status_of(n_ok, n_fail, mode) -> str   # 04:568-577: backfill→BACKFILL / n_ok==0→FAIL / n_fail>0→PARTIAL / else→OK

class TokenBucket:                          # 04:587-594
    def __init__(self, rps: float): ...
    def acquire(self) -> None: ...          # rps 초과 시 blocking. FMP/finnhub/naver 소스별 인스턴스. FMP 백필=日×250req.
```
근거: `04-backend.md:517-524`(run_collect), `:537-560`(_collect_market), `:526-533`(_collect_regime degrade), `:568-577`(_status_of), `:587-594`(TokenBucket), `:578-582`(백필 분할). `05:209-211`(OK=데이터 실재 + 게이트 차단은 FAIL만), `05:358-362`(status 판정).

> 🔎 **조정가 fresh 재계산(04:562-565, SSoT §4 핵심)**: `ohlcv()`가 매 호출 조정 윈도우(200일+)를 통째 재수신해 52주/SMA200/percentile을 그 자리 계산. `price_snapshot.close_adj`는 결과 스냅샷일 뿐 다음 계산 입력 아님. → 이 책임은 **어댑터(us.py/kr.py)** 에 있고 collect는 호출만.

### 2.6 `app/db.py` W2 upsert 헬퍼 (BAL-17 의존 — W2-1 선커밋) — canonical 05 §4.1

W1이 `upsert_price`/`upsert_funda`(전체명 named-bind + `asdict` + self-commit, `db.py:207-223`) + `upsert_fx`(dict-surface, `db.py:225-233`)를 보유. W2 신규/전환:
```python
def upsert_fx(conn, row: FxRate) -> None
    # W1 surface(row: Mapping) → W2: row=FxRate frozen dataclass, dataclasses.asdict(row)로 통일
    #   (db.py:225-233 본체 재사용, dict(row)→asdict(row). decisions §3.8 / Q2)
def upsert_news(conn, rows: list[Headline], ct: str, trade_date: str) -> None
    # 05:168-176 news_snapshot. PK(ct,trade_date,url) → ON CONFLICT DO NOTHING(url 중복 무시, 05:354)
def upsert_market_regime(conn, row: RegimeRow) -> None
    # 05:181-188 market_regime. as_of→trade_date, us_cape→shiller_cape 매핑. ON CONFLICT DO UPDATE
def upsert_collect_run(conn, trade_date, market, status, n_ok, n_fail, missing_tickers) -> None
    # 05:193-207 collect_run. PK(trade_date,market). missing_tickers=JSON 배열 문자열. ON CONFLICT DO UPDATE(05:364-369)
```
근거: `05-database.md:345-350`(upsert ON CONFLICT 패턴), `:354`(news=DO NOTHING), `:358-369`(collect_run 기록). ⚠️ **named param 키명 = 컬럼 전체명**(decisions §3.4 — 05 §4.1의 약어 `:ct/:td`는 예시일 뿐, `asdict` 키와 1:1 정합 필수). `db.py:207-223` W1 패턴 그대로 답습.

### 2.7 `validate_response` 본체 성장 (W1 가드 — BAL-17이 날짜검사 추가) — canonical 04 §7.1

```python
def validate_response(rows: int, latest: str, expected: str) -> None  # 시그니처 불변(W1, 04:454-458)
    # W1 본체: if rows == 0: raise EmptyResponseError  ← sources/__init__.py:41-44 (현존)
    # W2 추가(collect 경로): if latest != expected: raise  ← 본체만 성장, 시그니처 불변 (decisions §3.7 / Q1)
```
근거: `04-backend.md:454-458`, `app/sources/__init__.py:41-44`(W1 body=rows==0만), decisions §3.7(시그니처 immutable, body grows). ⚠️ **소유 = §7 미해결**: 날짜검사(`latest != expected`)를 `validate_response` 본체에 넣을지(공통 가드 변경) vs `_collect_market`이 호출 결과로 자체 비교할지. decisions Q12/Q1은 "W2 collect.py로 이관"이라 명시하나, **본체에 넣는지 collect 인라인인지**는 §7 참조.

---

## 3. 실행 파동 (Wave 3단계: 1 → 4-way 병렬 → 1)

| Wave | 이슈 | 병렬성 | 산출 게이트(DoD 요약) |
|------|------|--------|------------------------|
| **W2-1** 공유파일 선커밋 | `models.FxRate` 정의 + `db.py` W2 upsert 헬퍼(`upsert_fx` FxRate 전환 + `upsert_news`/`upsert_market_regime`/`upsert_collect_run`) | ❌ 단독 직렬 | `from app.models import FxRate` 가능 / `db.upsert_fx(conn, FxRate(...))` 라운드트립 / news·regime·collect_run upsert 후 되읽기 row 반환 / `pytest`·`py_compile` green |
| **W2-2** 어댑터 4-way 병렬 | **BAL-13** us.py ∥ **BAL-14** fx.py ∥ **BAL-15** regime.py(us_cape) ∥ **BAL-16** etf.py | 4-way 병렬 (파일 비중복 — regime.py만 W1 in-place 단독 소유) | us: `UsSource().ohlcv(<US종목>)` close_raw·52주·sma200 + `fundamentals` per_pctile_5y + `headlines` / fx: `FxSource().usdkrw()` → FxRate / regime: `RegimeProvider().regime().us_cape` 실수치(+kospi_pbr 회귀 없음) / etf: `is_core_etf` 화이트리스트 정합 |
| **W2-3** collect 통합 | **BAL-17** collect.py (BAL-51 `_collect_*`+TokenBucket → BAL-52 `_status_of`+collect_run → BAL-53 백필) | ❌ 순차(13·14·15·16·kr·db 전부 의존) | §5 통합 DoD 전건 |

병렬은 **계획·구현 시작**만 동시. **W2-1 커밋 후** W2-2 진입(4 어댑터), **W2-2 머지 후** W2-3 통합.

> 🔎 **W2-1을 먼저 박는 이유**: `models.FxRate`는 BAL-14(정의)·BAL-13(import 가능성)·BAL-17(upsert 인자)가 함께 닿는 유일 신규 DTO. db upsert 헬퍼는 BAL-17 통합의 선행물. 둘을 W2-2 병렬 안에 두면 `models.py`/`db.py` 머지 충돌 → W1의 "W-1a 공유파일 선커밋" 패턴(orchestration §2.4 발견③)을 그대로 답습.
> 🔎 **regime.py 단독 소유**: BAL-15만 `regime.py`를 수정하므로 4-way 병렬 안에서 충돌 없음. 단 W2-2 내 다른 이슈가 regime.py를 건드리지 않도록 경계 고정.

---

## 4. degraded-session 운영 규약 (현재 세션 = thinking/ 루트)

현재 Claude 세션은 `thinking/`에서 떠서 `investbrief/.claude` hook·`bal-*` 에이전트가 **자동 로드되지 않음**. 오케스트레이터(메인 루프)가 수동 대체:

| 자동화(원래 hook/agent) | 수동 대체 |
|--------------------------|-----------|
| auto context-inject (jira-plan/execute 강제) | 본 워크플로가 시퀀스를 직접 수행 |
| compile-check (PostToolUse, py_compile) | 편집 후 `python3 -m py_compile <file>` 직접 실행 |
| review-gate (PreToolUse git commit) | 커밋 전 aggregate-verdict 수동 확인 |
| `bal-*` 리뷰 에이전트 fan-out | general-purpose 에이전트에 `bal-*.md` 지침 주입해 동일 구동 |
| persist-checkpoint (Stop) | `.claude/runtime/checkpoint.md` 수동 작성 |

> 풀 자동화가 필요하면 `cd investbrief && claude` 재실행 후 `/harness-resume`.

브랜치 전략: 결합 슬라이스이므로 **단일 브랜치**에 이슈별 커밋(메시지에 `BAL-N`)으로 적재. 5 worktree 미사용. W2-2 4-way는 동일 브랜치 순차 커밋(파일 비중복이라 충돌 0).

> 🔎 **W2 신규 외부 의존 + 키**: us/fx 어댑터는 `app/config.py:23-30`의 `FINNHUB_API_KEY`/`FMP_API_KEY`/`SEC_USER_AGENT`/`ECOS_API_KEY`(W1에서 이미 선언, `os.environ.get()`→None)를 사용. **사용 시점 fail-fast**(`os.environ[key]`)는 W2 어댑터에서 비로소 구현(decisions: fast-fail은 W1 '계획'이었고 실제 구현은 W2). 신규 라이브러리(pandas_datareader/stooq, edgartools, etf-scraper, multpl 스크레이프)는 `requirements`에 추가 — degraded-session에선 `.venv` 설치를 수동 검증.

---

## 5. 검증 게이트 (W2 통합 DoD, 로드맵 08 §Week2 / 04 §8)

- [ ] **30종목 수집**: `run_collect(mode='backfill')` → KR+US auto 종목 약 30종 price/funda row 적재(05:582 백필 완료 판정 = 모든 auto 종목 row 존재). bulk fetch로 200일+ 즉시 확보.
- [ ] **collect_run status**: 시장별 `collect_run` row 기록 — 거래일 정상 = `OK`(n_ok>0 + 최신일자 일치, 05:209/358), 휴장 = `OK_HOLIDAY`, 일부 실패 = `PARTIAL`(missing_tickers JSON 배열), 백필 = `BACKFILL`(04:568-577). FAIL만 게이트 차단(05:211).
- [ ] **FX**: `_collect_fx` → `collect_run(market='FX', status='OK')` + `fx_snapshot` USDKRW row. fx 실패 시 `FAIL` → USD 자산 보류 경로(04:489-491, 05:162).
- [ ] **regime**: `_collect_regime` → `market_regime` row에 `shiller_cape`(US, BAL-15) + `kospi_pbr`(KR, W1) 둘 다 채워짐(한쪽 실패 시 그 필드만 NULL, degrade — 04:533).
- [ ] **백필 분할**: FMP percentile 250req/day 한도 → 며칠 분할 동안 `per_pctile_5y` NULL + `status='BACKFILL'`(04:581). 다음날 이어받기(TokenBucket FMP 소진 후 status 유지).
- [ ] **종목 격리**: 단일 종목 raise가 배치를 죽이지 않음 — `missing_tickers`에 격리 기록(04:446/557).
- [ ] **빈응답 가드**: `validate_response(rows=0)` → `EmptyResponseError` → n_fail 집계(OK 오인 방지, 04:457/05:209). collect 경로 날짜검사 = §7 결정에 따름.
- [ ] `pytest -q` green, 편집 파일 `py_compile` 통과.

---

## 6. Out of scope (W2 아님 — 끌려가지 말 것)

- **metrics 계산**(drift/core-sat/valuation/trend/regime/dca 5종, 04 §9 / W3) — collect는 raw 적재까지, 계산·라벨링은 W3.
- **LLM/브리핑 생성**(Claude 호출, SecurityCard/BriefingDoc DTO, 04 §10+ / W3+).
- **프론트**(Jinja2 렌더·freshness badge·신선도 배너, 03 / W5).
- **손익/수익률**(lots·매입환율 기반, G8 / R2 W-01 해제).
- **룩스루 ETF 비중 분해**(F-19, 01:248 R2 — BAL-16은 코어 판정 보강만, §7).
- **임시공휴일/KOSDAQ frozenset**(decisions: W2 calendar/tickers 확장은 별도 — 본 슬라이스는 소스+collect 집중).

---

## 7. 미해결 / 결정필요 포인트

| # | 항목 | 쟁점 | 본 문서 기본안(근거) | 결정 필요 주체 |
|---|------|------|----------------------|----------------|
| **U1** | **BAL-16 ETF 스코프 모호** | etf.py가 (a) 룩스루 구성종목 분해인지 (b) 코어 판정 보강인지. W1 `tickers.CORE_ETF_WHITELIST`+`classify_category`가 **이미 코어 판정 보유**(`tickers.py:15-37`, `01:42` AC4). | **(b) 코어 판정 보강만 W2**. 룩스루(KR pykrx PDF / US 발행사 CSV·etf-scraper)는 `01:109` F-19 = §5, `01:248` **R2(정확도 확장)** 로 명시 → R1 PoC 범위 밖. etf.py는 화이트리스트 밖 ETF 메타 확인 정도로 최소화하거나 **W2 stub 유지 후 R2 구현**도 가능. ⚠️ 코어 판정이 W1에서 끝났다면 BAL-16의 W2 실질 산출이 0에 수렴 → **이슈 자체를 R2로 미루거나 룩스루 일부를 W2로 당길지** 사용자 결정 필요. | 사용자(스코프) |
| **U2** | **validate_response 날짜검사 W2 범위 + 소유** | `if latest != expected: raise`를 (a) `validate_response` 본체에 추가(공통 가드 변경, decisions §3.7) vs (b) `_collect_market`이 호출 후 자체 비교(가드는 rows-only 유지). decisions Q1/Q12는 "W2 collect로 이관"만 명시, **본체 vs 인라인은 미확정**. | **기본 = (a) 본체 성장**(decisions §3.7 "시그니처 불변, 본체만 성장" 직설). 단 (b)가 더 surgical(`sources/__init__` 불변 + collect가 status PARTIAL/FAIL 판정에 직접 활용, decisions Q12 'stale 대조는 collect.py'와 정합). 둘 다 canonical 위반 아님 → **구현 시 1택 고정 필요**. | 구현자(BAL-17) |
| **U3** | **db W2 upsert 헬퍼 소유** | `upsert_news`/`upsert_market_regime`/`upsert_collect_run` + `upsert_fx` FxRate 전환을 (a) BAL-17(collect 통합자) 커밋에 포함 vs (b) BAL-8(db.py 소유 이슈)의 W2 carryover로 분리. W1 W-1a가 db upsert를 선커밋한 선례 있음(orchestration §2.1 발견①). | **(a) BAL-17 범위 + W2-1 선커밋**으로 박음(본 문서 §2.6/§3). db.py는 BAL-8 소유지만 W2 신규 헬퍼는 collect 의존물이라 BAL-17 슬라이스에 귀속하는 게 응집적. 단 BAL-8을 "DB 헬퍼 단일 소유"로 강제하는 정책이 있으면 (b)로 재배치. | 사용자/오케스트레이터(이슈 귀속) |
| U4 | FxRate↔fx_snapshot 1:1 + asdict 키 | W1 `upsert_fx`가 dict-surface라 W2 FxRate 전환 시 키명 정합 필요. | FxRate 필드명 = `trade_date/pair/rate`(05:154-160 컬럼 전체명) → `asdict` named-bind 1:1(decisions §3.4 패턴). 라운드트립 E2E가 검증 게이트(별도 어서션 불필요). | 구현자(BAL-14/17) |
| U5 | regime 월단위 캐시 위치 | "같은 달이면 재호출 안 함"(04:499)을 regime.py 내부 캐시 vs collect `_collect_regime`의 month-skip(04:528 "이미 이번 달 row 있으면 skip") 중 어디서. | **collect의 DB row 존재 체크가 1차**(04:528 명시), regime.py 내부 메모 캐시는 보조. 이중 안 함 — collect 레벨 skip 단일. | 구현자(BAL-17) |

> ⚠️ **TECH-DESIGN.md 부재 재확인**: W1 dev-guide 일부가 `§15.x`를 인용하나 해당 파일은 레포에 없다. W2 dev-guide/구현은 **04/05/01만 인용**하고 `§15` 참조를 답습하지 말 것.
