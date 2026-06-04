# 04 · Backend Spec — AI 투자 브리핑 PoC

> SSoT: `TECH-DESIGN.md` v3.2 (**DTO·색·키·런타임 정본 = §15 Contract SoT, 충돌 시 §15 우선**). 본 문서는 **백엔드 구현 명세**다.
> 범위: FastAPI 앱/라우트 · `sources/` 어댑터 · `tickers.py` · `calendar.py` · `collect.py`(수집·rate limiter·응답유효성·collect_run) · `metrics/` 호출 · `briefing.py`(슬롯조립·검증게이트·금지어 린터) · 스케줄러 · 에러/재시도/fallback.
> AI 호출은 **06-ai-agent에 위임**(여기서는 `LLMClient` Protocol 인터페이스만). G1은 프로젝트 결정에 따라 **(B) `claude -p` CLI 채택**으로 확정 — 단일 어댑터 뒤로 숨긴다.
> 작성일: 2026-06-01 · 의존: `00-e2e-flow.md`(S1~S8), 06-ai-agent(LLM 어댑터), 03-frontend(템플릿·DTO 소비).

---

## 0. 모듈 책임 맵 (SSoT §3 폴더구조 그대로)

| 파일 | 책임 | 본 문서 절 |
|---|---|---|
| `app/main.py` | FastAPI 앱·라우트·POST validation·렌더 | §1 |
| `app/config.py` | `.env` 로드·설정 상수 | §2 |
| `app/db.py` | SQLite 연결·스키마 init·조회 헬퍼(MAX(trade_date)) | §3 |
| `app/models.py` | frozen dataclass DTO + Protocol | §4 |
| `app/tickers.py` | canonical↔source 변환 + CORE_ETF_WHITELIST | §5 |
| `app/calendar.py` | KR/US 거래일 판정·직전 거래일 | §6 |
| `app/sources/{kr,us,fx,etf}.py` | 데이터 어댑터(KR/US 차이 흡수) | §7 |
| `app/collect.py` | 수집 배치·rate limiter·응답유효성·collect_run 기록 | §8 |
| `app/metrics/{portfolio,security}.py` | 순수 계산(호출 계약만 — 상세 알고리즘 SoT = **TECH-DESIGN §6**, §15.6) | §9 |
| `app/briefing.py` | 게이트→슬롯조립→LLM→검증게이트→슬롯주입→저장 | §10 |
| `scripts/run_collect.py`·`run_briefing.py` | cron 엔트리 | §11 |

> `metrics/`의 내부 알고리즘 정본은 **TECH-DESIGN §6**(§15.6 — 별도 metrics 문서 없음). 본 문서는 **collect/briefing이 metrics를 어떤 시그니처로 부르는지**(§9)만 고정한다.

---

## 1. FastAPI 앱 · 라우트 (`main.py`)

### 1.1 앱 부트스트랩

```python
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

app = FastAPI(title="ballast")              # docs 노출 OK (로컬 전용)
templates = Jinja2Templates(directory="app/templates")

# 바인딩: 반드시 127.0.0.1 (SSoT §8 · §12 "로컬 전용"). uvicorn 실행 시 강제.
#   uvicorn app.main:app --host 127.0.0.1 --port 8000
```

> SSoT §12: 자산정보=금융 개인정보. 외부 바인딩 금지. `0.0.0.0` 사용 시 코드리뷰 reject.

### 1.2 라우트 표 (SSoT §8 그대로)

| 메서드·경로 | 핸들러 | 동작 |
|---|---|---|
| `GET /` | `dashboard()` | 오늘 `briefing_date` 중 `MAX(created_at)` row → `BriefingDoc` 역직렬화 → 신선도 배지 산출 → `dashboard.html` |
| `GET /holdings` | `holdings_form()` | 현재 holdings 목록 + 입력 폼 |
| `POST /holdings` | `holdings_save()` | 행 검증(§1.4)→ category 자동판정(§5.3)→ upsert → redirect `/holdings` |
| `GET /settings` | `settings_form()` | settings 표시 |
| `POST /settings` | `settings_save()` | settings upsert → redirect |
| `POST /api/regenerate` | `regenerate()` | **127.0.0.1 한정** 수동 브리핑 재생성(개발용). `briefing.run_briefing()` 호출 |

### 1.3 `GET /` 렌더 계약 (S8)

```python
@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    row = db.latest_briefing(user_id=1)        # 오늘 date 중 MAX(created_at), 없으면 None
    doc = BriefingDoc.from_json(row["content_json"]) if row else None   # §4.4
    badge = build_freshness_badge(user_id=1)           # §6.3 (= freshness_badges, 03-frontend 컨텍스트 키 'badge')
    return templates.TemplateResponse("dashboard.html",
        {"request": request, "doc": doc, "badge": badge})
```

- 템플릿은 **`BriefingDoc` DTO만 신뢰**(G11). content_json 내부를 직접 인덱싱하지 않는다.
- **컨텍스트 키 = `doc`(None이면 day-0 빈상태) + `badge`(단수)** — 03-frontend §1 핸들러·템플릿(`badge.worst_level` 등)과 단일화(별도 `empty`/`badges` 플래그 폐기). `doc is None` → "초기 데이터 적재중" 안내(G3-3).

### 1.4 `POST /holdings` validation (G5 배타·합100% 강제 지점)

폼은 행 배열(JS로 동적 추가). 서버는 `list[HoldingInput]`로 파싱 후 검증.

```python
def validate_holdings(rows: list[HoldingInput]) -> list[HoldingRow] | ValidationError:
    # 1) 행 타입 결정
    for r in rows:
        if r.instrument == "cash":
            assert r.value_manual is not None and r.ccy in {"KRW", "USD"}
            r.tracking, r.asset_class, r.quantity, r.canonical_ticker = "manual", "cash", None, None
        else:  # stock | etf
            assert r.canonical_ticker and r.quantity is not None and r.market in {"KR", "US"}
            r.tracking, r.asset_class = "auto", "equity"
            r.ccy = "KRW" if r.market == "KR" else "USD"
    # 2) target_pct 배타 (SSoT §6: 전부 수동 or 전부 자동)
    targeted = [r for r in rows if r.target_pct is not None]
    if 0 < len(targeted) < len([r for r in rows if r.asset_class == "equity"]):
        raise ValidationError("target_pct는 전부 채우거나 전부 비워야 함(혼재 금지)")  # 400
    # 3) 전부 수동이면 합 100% (±0.5%p 허용 후 정규화)
    if targeted:
        s = sum(r.target_pct for r in targeted)
        if abs(s - 100.0) > 0.5:
            raise ValidationError(f"수동 목표비중 합={s}%, 100%여야 함")  # 400
    return rows
```

- 검증 실패 → HTTP 400 + 폼 에러 메시지 재렌더. **자동 목표비중은 여기서 계산하지 않음**(G5: S5 런타임). 미설정 target_pct는 NULL로 저장.
- category 자동판정은 §5.3, 저장 직전 1회.

---

## 2. 설정 / 시크릿 (`config.py`)

```python
from dataclasses import dataclass
import os
from dotenv import load_dotenv
load_dotenv()

@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str | None  # 인증 정본 §15.1: 구독 로그인이면 불필요(종량과금 없음). API 키 경로일 때만 사용
    finnhub_api_key: str
    fmp_api_key: str
    dart_api_key: str
    naver_client_id: str
    naver_client_secret: str
    sec_user_agent: str            # EDGAR 필수 "name email"
    ecos_api_key: str | None       # 한국은행 ECOS 보조용(무료 키). None이면 ECB(1차)·yfinance만 사용
    db_path: str = "data/ballast.db"
    # 무료한도 페이싱(토큰버킷, req/sec)
    fmp_rps: float = 3.0           # 250 req/day → 백필 분할. 순간 rps만 제한
    finnhub_rps: float = 1.0       # 60 req/min 무료
    naver_rps: float = 5.0

def load() -> Settings:
    return Settings(
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        finnhub_api_key=os.environ["FINNHUB_API_KEY"],
        fmp_api_key=os.environ["FMP_API_KEY"],
        dart_api_key=os.environ["DART_API_KEY"],
        naver_client_id=os.environ["NAVER_CLIENT_ID"],
        naver_client_secret=os.environ["NAVER_CLIENT_SECRET"],
        sec_user_agent=os.environ["SEC_USER_AGENT"],
        ecos_api_key=os.environ.get("ECOS_API_KEY"),   # 보조 — 없으면 ECB/yfinance 폴백(KeyError 아님)
    )
```

> 필수 키 누락 시 `KeyError`로 즉시 실패(SSoT 보안규칙 — 조용한 fallback 금지). **환율 1차는 ECB(키 불필요)**, ECOS는 보조라 `ECOS_API_KEY`가 있을 때만 사용(없으면 ECB·yfinance). Stooq·CAPE(Yale)는 키 불필요.

**settings 테이블 기본값**(정본 = TECH-DESIGN §15.5): `monthly_contribution=0`, `base_currency='KRW'`, `satellite_limit_pct=30`, `rebalance_band_abs=5`, `rebalance_band_rel=25`, `micro_weight_floor=1.0`, **`usd_cash_gate_threshold=5.0`**(G6: USD 비중이 이 이상이면 fx FAIL 시 1층 배분 전체 보류).

---

## 3. DB 계층 (`db.py`)

### 3.1 연결 · init

```python
import sqlite3

def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(load().db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_schema(conn) -> None:
    conn.executescript(SCHEMA_SQL)   # SSoT §4의 DDL 전체 (holdings/settings/price_snapshot/
                                     # fundamentals_snapshot/fx_snapshot/news_snapshot/
                                     # market_regime/collect_run/briefing)
```

> 스키마 DDL은 SSoT §4를 **그대로** 사용(변경 금지). `data/`는 `.gitignore` + iCloud/Dropbox 폴더 밖(SSoT §12).

### 3.2 조회 헬퍼 — `MAX(trade_date)` 규칙 (SSoT §4 조회규칙)

metrics·badge가 의존하는 **단일 진입점**. `trade_date=today`가 아니라 **canonical_ticker별 MAX(trade_date)** row를 읽는다(시세·펀더·환율 동일). row 0건 → `None` 반환(G3: 호출측이 "데이터 준비중 보류"로 처리).

```python
def latest_price(conn, ct: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM price_snapshot WHERE canonical_ticker=? "
        "ORDER BY trade_date DESC LIMIT 1", (ct,)).fetchone()

def latest_funda(conn, ct: str) -> sqlite3.Row | None: ...      # fundamentals_snapshot 동일
def latest_fx(conn, pair: str = "USDKRW") -> sqlite3.Row | None: ...  # fx_snapshot 동일

def latest_collect_run(conn, market: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM collect_run WHERE market=? ORDER BY trade_date DESC LIMIT 1",
        (market,)).fetchone()

def latest_briefing(conn, user_id: int = 1) -> sqlite3.Row | None:
    # 오늘 briefing_date 중 MAX(created_at) (SSoT §8)
    return conn.execute(
        "SELECT * FROM briefing WHERE user_id=? AND briefing_date=date('now','localtime') "
        "ORDER BY created_at DESC LIMIT 1", (user_id,)).fetchone()
```

> **조정가 stale 방지(SSoT §4)**: `price_snapshot.close_adj`는 표시·감사용 스냅샷일 뿐 **지표 계산의 원천이 아니다**. SMA200·52주·percentile은 collect 시 소스에서 조정 윈도우를 통째로 다시 받아 그 자리에서 재계산해 저장(§8.3). db는 그 결과를 캐시할 뿐 누적 재계산하지 않는다.

---

## 4. DTO · Protocol (`models.py`)

### 4.1 입력/저장 DTO

```python
from dataclasses import dataclass
from typing import Literal, Protocol

@dataclass
class HoldingInput:                 # POST /holdings 폼 파싱용 (mutable: validation에서 채움)
    instrument: Literal["stock", "etf", "cash"]
    name: str
    canonical_ticker: str | None = None
    market: Literal["KR", "US"] | None = None
    quantity: float | None = None
    value_manual: float | None = None
    ccy: Literal["KRW", "USD"] | None = None
    avg_price: float | None = None
    category: Literal["core", "satellite"] | None = None   # 사용자 명시(선택)
    target_pct: float | None = None

@dataclass(frozen=True)
class HoldingRow:                   # holdings 테이블 영속 형태 (검증·자동판정 후)
    id: int | None
    user_id: int
    asset_class: Literal["equity", "cash"]
    instrument: Literal["stock", "etf", "cash"]
    tracking: Literal["auto", "manual"]
    market: Literal["KR", "US"] | None
    canonical_ticker: str | None
    name: str
    quantity: float | None
    value_manual: float | None
    ccy: Literal["KRW", "USD"] | None
    avg_price: float | None
    category: Literal["core", "satellite"] | None
    target_pct: float | None
```

### 4.2 소스 값 DTO (SSoT §5 — 모든 값 as_of_date 동반)

```python
@dataclass(frozen=True)
class OHLCV:
    canonical_ticker: str
    trade_date: str            # 소스 최신 거래일 (YYYY-MM-DD)
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
    per_pctile_5y: float | None    # NULL 허용(백필중/US 정밀도)
    pbr_pctile_5y: float | None
    report_date: str | None    # 재무 실제 기준일 (US 워밍업/DART 미확보 시 NULL — 배지 '워밍업' 표시)

@dataclass(frozen=True)
class Headline:
    title: str
    url: str
    source: str

@dataclass(frozen=True)
class FxRate:
    trade_date: str
    pair: str                  # 'USDKRW'
    rate: float

@dataclass(frozen=True)
class RegimeRow:               # ⑤ market_regime 적재용 (월단위)
    as_of: str                 # 기준월 → 테이블 PK `trade_date`로 매핑(05 §1.7, 'YYYY-MM-01' 등)
    kospi_pbr: float | None    # KR — pykrx 지수 PBR (→ 테이블 `kospi_pbr`)
    us_cape: float | None      # US — Shiller CAPE (Yale) (→ 테이블 `shiller_cape`)
    # 둘 다 NULL이면 regime degrade("레짐 데이터 미확보"). upsert 매핑: as_of→trade_date, us_cape→shiller_cape
```

### 4.3 Protocol (SSoT §5)

```python
class PriceSource(Protocol):
    def ohlcv(self, ct: str) -> OHLCV: ...
    def fundamentals(self, ct: str) -> Funda: ...

class NewsSource(Protocol):
    def headlines(self, ct: str, name: str) -> list[Headline]: ...

class FxSource(Protocol):
    def usdkrw(self) -> FxRate: ...

class RegimeSource(Protocol):
    def regime(self) -> "RegimeRow": ...   # ⑤ CAPE(US)·KOSPI PBR(KR), 월단위

# LLM 어댑터 (06-ai-agent가 구현 — 여기선 계약만, G1 단일 어댑터)
class LLMClient(Protocol):
    def generate(self, prompt: str, schema: dict) -> dict: ...
    # claude -p --output-format json --append-system-prompt 호출(§15.1). 시스템프롬프트는 어댑터 내부 상수.
    # content JSON 스키마 강제는 --json-schema + 코드측 Pydantic 파싱(실패 시 재호출, 06-ai-agent).
```

### 4.4 브리핑 출력 DTO (G11 — content_json 스키마 고정, **정본 = TECH-DESIGN §15.2**)

> 아래는 §15.2 정본을 그대로 옮긴 것이다(충돌 시 §15.2 우선). 수치는 전부 코드 계산값, `comment/trend_note/investment_points`만 LLM(`SecurityLLMOut`, 06-ai-agent §1.3)에서 `canonical_ticker`로 머지한다.

```python
@dataclass(frozen=True)
class SecurityCard:                # 코드가 슬롯주입한 최종형 = 대시보드/JSON 직렬화 정본 (§15.2)
    canonical_ticker: str; name: str; instrument: str; asset_class: str; category: str | None
    change_pct: float | None; current_pct: float; target_pct: float | None; drift: float | None
    rebalance_flag: bool
    per: float | None; pbr: float | None; div_yield: float | None
    valuation_pctile: float | None; valuation_label: str
    week52_pos: float | None; sma200_gap: float | None
    status: str                    # §15.4 enum: 'ok'|'data_pending'|'fx_held'|'warmup'|'failed'
    comment: str; trend_note: str; investment_points: list[str]   # ← LLM(SecurityLLMOut) 머지

@dataclass(frozen=True)
class HoldExcluded:                 # §15.2 — G2 전용(LLM 미매칭/중복 처리실패)
    canonical_ticker: str
    reason: str

@dataclass(frozen=True)
class BriefingDoc:                  # = briefing.content_json 직렬화 정본 (§15.2)
    briefing_date: str; model: str; created_at: str
    banner: str | None                           # 게이트 차단/부분보류 안내(정상시 None)
    regime_label: str                            # ⑤ top-level 1개 (카드별 아님)
    as_of: dict                                  # {'price','funda','fx'} 3키 고정
    asset_allocation: dict                       # 1층 {'equity_pct','cash_pct'} + 2층 {'core_pct','satellite_pct','satellite_over_limit':bool}
    securities: list[SecurityCard]
    holds_excluded: list[HoldExcluded]           # G2(LLM 미매칭/중복)만. 보류는 securities[].status 단일경로
    dca: dict
    portfolio_comment: dict                      # {'rebalance_note','dca_note','weight_note'} (LLM 문장, 슬롯주입 완료)
    disclaimer: str                              # 고정 면책 (코드 상수)

    def to_json(self) -> str: ...
    @classmethod
    def from_json(cls, s: str) -> "BriefingDoc": ...
```

> **보류/제외는 `securities[].status` 단일 경로**(§15.2). `holds_excluded`는 LLM이 응답에서 누락/중복으로 떨어뜨린 종목(G2)만 담는다 — `data_pending`/`fx_held`/`warmup` 보류는 카드의 `status`로 표시하고 `holds_excluded`에 넣지 않는다.

---

## 5. 티커 정규화 (`tickers.py`)

### 5.1 canonical → source 변환 (SSoT §5)

```python
def to_source(source: Literal["yf", "finnhub", "stooq", "pykrx", "fdr", "fmp", "dart"],
              ct: str, market: str) -> str:
    # 예: to_source('yf','005930','KR') -> '005930.KS'
    #     to_source('finnhub','BRK.B','US') -> 'BRK-B'
    #     to_source('stooq','VOO','US') -> 'voo.us'
    ...
```

**규칙(검증 가능 케이스):**
| canonical | yf | finnhub | stooq | pykrx |
|---|---|---|---|---|
| `005930`(KR) | `005930.KS` | `005930.KS` | `005930.KS` | `005930` |
| `VOO`(US) | `VOO` | `VOO` | `voo.us` | — |
| `BRK.B`(US) | `BRK-B` | `BRK-B` | `brk-b.us` | — |

> **모든 캐시 PK는 canonical 기준**(SSoT §5) — 소스 표기 차이로 시계열이 갈라지지 않는다. KOSDAQ은 `.KQ` 접미(yf/stooq), pykrx는 6자리 그대로.

### 5.2 코어 ETF 화이트리스트 (G4 — 코드 상수 frozenset)

```python
CORE_ETF_WHITELIST: frozenset[str] = frozenset({
    # KR 광범위 지수
    "069500",   # KODEX 200
    "360750",   # TIGER 미국S&P500
    "379800",   # KODEX 미국S&P500TR
    # US 광범위 지수
    "VOO", "SPY", "VTI", "IVV", "ITOT", "VT",
})
# 섹터·테마·레버리지·액티브 ETF는 포함 금지 (한도 오염 방지, SSoT §6).
```

### 5.3 category 자동판정 (G4 — 우선순위 명시)

```python
def classify_category(h: HoldingInput) -> Literal["core", "satellite"] | None:
    if h.category is not None:          # 1) 사용자 명시 우선
        return h.category
    if h.instrument == "stock":         # 2) 개별주 → satellite
        return "satellite"
    if h.instrument == "etf":           # 3) ETF: 화이트리스트 매칭만 core
        return "core" if h.canonical_ticker in CORE_ETF_WHITELIST else None  # NULL="확인 필요"
    return None                          # cash 등
```

> 결과를 **holdings.category에 영속화**(POST /holdings 저장 시 1회) — 매 계산 재판정 비용 회피(G4 fix).

---

## 6. 거래일 캘린더 (`calendar.py`)

### 6.1 판정 (SSoT §9 ③⑦)

```python
import pandas_market_calendars as mcal

_KR = mcal.get_calendar("XKRX")   # 한국거래소
_US = mcal.get_calendar("XNYS")   # NYSE

def is_trading_day(market: Literal["KR", "US"], d: date) -> bool: ...
def prev_trading_day(market: Literal["KR", "US"], d: date) -> date: ...
def expected_trade_date(market: Literal["KR", "US"], today: date) -> date:
    # collect 기준일: KR=오늘(거래일), US=직전 거래일(전일 마감분 수집)
    ...
```

### 6.2 사용처
- `collect.py`: 오늘이 거래일 아니면 `status='OK_HOLIDAY'`로 정상 skip(§8.5).
- badge(§6.3): "기대 거래일 vs 실제 수집일" 대조 → 어긋나면 fallback 배너.

### 6.3 신선도 배지 산출 (G10 — 입력 일원화)

```python
@dataclass(frozen=True)
class FreshnessBadge:        # 정본 = §15.2 (렌더 소비자=03-frontend 필드명 기준)
    price_age_days: int      # 기대거래일 - MAX(price_snapshot.trade_date), 종목별 최악(최고령)
    funda_label: str         # report_date 기반 라벨('최신'/'N분기 전'/'워밍업'). NULL 종목은 '워밍업'
    fx_age_days: int         # 기대거래일 - MAX(fx_snapshot.trade_date)
    worst_level: str         # 'fresh'(0~1일)|'stale'(2~4일)|'warn'(5일+) — 최악 등급(배지 색, 03-frontend §4)
    consecutive_fallback: bool   # N일 연속 fallback이면 True → 경고 블록

def build_freshness_badge(conn, user_id: int = 1) -> FreshnessBadge:   # 03-frontend §1 호출명과 동일
    # 내부적으로 as_of(날짜)를 구한 뒤 기대거래일과의 차이를 days로 환산해 반환.
    # 시세=MAX(trade_date) vs calendar.expected_trade_date, 펀더=report_date(NULL→'워밍업'),
    # 환율=MAX(trade_date). 종목별 최악값을 포트폴리오 배지로 집계 → worst_level 산출.
    # consecutive_fallback은 collect_run 이력에서 연속 fallback 일수>임계면 True (SSoT §8).
    ...
```

---

## 7. 데이터 어댑터 (`sources/`)

각 어댑터는 `PriceSource`/`NewsSource`/`FxSource` Protocol 구현. **종목 단위 격리**(한 종목 실패가 배치를 죽이지 않음) — 예외는 collect가 잡아 `collect_run.missing_tickers`에 기록.

### 7.1 공통 안정성 데코레이터 (SSoT §5 안정성 규칙)

```python
def retry(times: int = 3, backoff: float = 1.5):
    """@retry(3) — 지수 백오프. 마지막 실패는 raise (collect가 격리)."""

def validate_response(rows: int, latest: str, expected: str) -> None:
    """응답 유효성: 행수>0 AND 최신일자가 기대거래일과 일치(±허용).
       Stooq 빈 CSV 등 '조용한 실패'를 OK로 오인 금지 (SSoT §4 OK 판정)."""
    if rows == 0:
        raise EmptyResponseError("행수 0 — 조용한 실패")
```

### 7.2 KR (`sources/kr.py`)

| 데이터 | 라이브러리 | 함수 |
|---|---|---|
| 시세/52주/SMA(조정) | pykrx · FinanceDataReader | `ohlcv(ct)` — FDR/pykrx 조정종가 윈도우 fresh fetch → close_raw/close_adj/52주/sma200 계산 |
| PER/PBR/배당 + 5년 | pykrx `get_market_fundamental` | `fundamentals(ct)` — 5년 시계열 OK, percentile 계산 |
| 공시·재무 | DART (OpenDartReader) | (보조, PoC는 report_date 확보용) |
| 뉴스 | 네이버 검색 API | `headlines(ct, name)` — 헤드라인+링크만 |
| ETF 구성 | pykrx PDF | `etf.py` 위임 |

### 7.3 US (`sources/us.py`)

| 데이터 | 1차 | 2차/보조 |
|---|---|---|
| 시세/52주/SMA(조정) | **Stooq** (`pandas_datareader`/`stooq`) | **yfinance** `auto_adjust=True` · Finnhub `/quote`(당일가 보조) |
| PER/PBR/배당 + 5년 | **FMP 무료**(5년 시계열, 250req/day) | yfinance/Finnhub 스냅샷 보조 |
| 공시·재무 | SEC EDGAR (edgartools) | — |
| 뉴스 | Finnhub 뉴스 | — |
| ETF 구성 | 발행사 공식 CSV | etf-scraper(2차) |

> **degrade 규칙(SSoT §5)**: FMP 한도가 빠듯하면 percentile을 "현재 PER vs 자기 5년 평균"으로 낮춤. `per_pctile_5y` NULL 허용 → metrics가 "워밍업 중(절대 PER만)" 라벨(G3-2). **PER/PBR은 제공자 계산값만 캐시, 자체 가격×EPS 재계산 금지**(SSoT §5).

### 7.4 FX (`sources/fx.py`)

```python
def usdkrw(self) -> FxRate:
    # 1차: 한국은행 ECOS (키 불필요·안정) / ECB
    # 2차: yfinance 'KRW=X'
    # 둘 다 실패 → raise → collect_run(market='FX', status='FAIL')
    #   → briefing 게이트가 USD 자산 전체 보류 (NULL 분모 제외 금지, SSoT §4)
```

### 7.5 Regime (`sources/regime.py`) — ⑤ 시장 레짐 (월단위)

```python
class RegimeProvider:                          # RegimeSource Protocol 구현
    def regime(self) -> RegimeRow:
        # KR: pykrx 지수 PBR (KOSPI). US: Shiller CAPE — Yale ie_data.xls(1차)·multpl(2차).
        # 월단위라 매일 호출해도 같은 달이면 캐시 재사용(가벼움).
        # 한쪽만 실패하면 그 필드만 NULL(둘 다 NULL이면 metrics.regime이 degrade 라벨).
        ...
```

| 데이터 | 1차 | 2차 |
|---|---|---|
| KOSPI 지수 PBR | pykrx (지수 PBR) | — |
| Shiller CAPE | Yale `ie_data.xls` | multpl 스크레이프 |

> 키 불필요. `market_regime` 테이블(05-database)에 `as_of`(월) PK로 upsert. metrics `regime()`(§9.2)이 이 row를 한 줄 라벨로 변환.

---

## 8. 수집 배치 (`collect.py`)

### 8.1 진입점

```python
def run_collect(mode: Literal["daily", "backfill"] = "daily") -> None:
    today = date.today()
    holdings = db.auto_holdings(user_id=1)      # tracking='auto' 행
    for market in ("KR", "US"):
        _collect_market(market, holdings, today, mode)
    _collect_fx(today, mode)
    _collect_regime(today)                      # CAPE / KOSPI PBR (월단위, 가벼움)

def _collect_regime(today) -> None:
    # sources/regime.py(RegimeProvider) 호출 → market_regime upsert (as_of=YYYY-MM PK).
    # 이미 이번 달 row가 있으면 skip. 실패해도 collect 전체를 죽이지 않음(regime은 degrade 가능).
    try:
        db.upsert_regime(regime_source.regime())
    except Exception as e:
        log.warning("regime collect fail (degrade): %s", e)   # NULL 유지 → metrics가 degrade 라벨
```

### 8.2 시장별 수집 + collect_run 게이트 기록 (SSoT §4·§9⑦)

```python
def _collect_market(market, holdings, today, mode) -> None:
    if not calendar.is_trading_day(market, today):
        db.upsert_collect_run(today, market, status="OK_HOLIDAY",
                              n_ok=0, n_fail=0, missing_tickers="[]")   # JSON 배열(05-database 정본)
        return                                  # 정상 skip, 배너 오발동 방지
    src = kr_source if market == "KR" else us_source
    n_ok, n_fail, missing = 0, 0, []
    expected = calendar.expected_trade_date(market, today)
    for h in (x for x in holdings if x.market == market):
        try:
            ohlcv = src.ohlcv(h.canonical_ticker)          # @retry 내장
            validate_response(rows=1, latest=ohlcv.trade_date, expected=expected.isoformat())
            db.upsert_price(ohlcv)
            funda = src.fundamentals(h.canonical_ticker)   # 백필 분할이면 일부 skip
            db.upsert_funda(funda)
            db.upsert_news(h.canonical_ticker, src.headlines(h.canonical_ticker, h.name))
            n_ok += 1
        except Exception as e:
            n_fail += 1; missing.append(h.canonical_ticker)
            log.warning("collect fail %s: %s", h.canonical_ticker, e)   # 종목 격리
    status = _status_of(n_ok, n_fail, mode)     # §8.4
    db.upsert_collect_run(today, market, status, n_ok, n_fail, json.dumps(missing))  # JSON 배열(05-database 정본)
```

### 8.3 조정가 fresh 재계산 (SSoT §4 핵심)

`ohlcv()`는 매 호출 시 **소스에서 조정 윈도우(200일+)를 통째로 다시 받아** 52주/SMA200/percentile을 그 자리에서 계산한다. 캐시된 과거 close_adj를 누적 사용하지 않는다(배당/분할 소급변경 흡수). `price_snapshot.close_adj`는 결과 스냅샷일 뿐 다음 계산의 입력이 아니다.

### 8.4 collect_run status 판정 (SSoT §4)

```python
def _status_of(n_ok, n_fail, mode) -> str:
    if mode == "backfill":  return "BACKFILL"     # 워밍업 중 (게이트 차단 아님)
    if n_ok == 0:           return "FAIL"          # 전부 실패 → 게이트 차단
    if n_fail > 0:          return "PARTIAL"        # 일부 실패 → 해당 종목만 제외
    return "OK"
```

> **OK 판정 = "예외 안 남"이 아니라 "데이터 실재"**(행수>0 + 최신일자 일치). `validate_response`가 빈 CSV를 `EmptyResponseError`로 올려 n_fail로 집계 → OK 오인 방지(SSoT §4).

### 8.5 백필 모드 (SSoT §9 초기 백필)

- `mode="backfill"`: pykrx/FDR/Stooq는 과거 시계열을 한 번에 반환 → 200일·52주·SMA200 day-0 즉시 확보.
- FMP percentile만 250req/day 한도 → **며칠 분할**, 그동안 `per_pctile_5y` NULL + `status='BACKFILL'`.
- 백필 완료 판정(G9): **모든 auto 종목 price/funda row 존재 + percentile BACKFILL 해제** → 익영업일부터 정상 daily cron.

### 8.6 Rate limiter (토큰버킷, SSoT §5)

```python
class TokenBucket:
    def __init__(self, rps: float): ...
    def acquire(self) -> None:        # rps 초과 시 blocking sleep
        ...

# 소스별 인스턴스 (config의 fmp_rps/finnhub_rps/naver_rps).
# FMP 백필은 일일 250req 소진 시 다음날 이어받기 (status는 BACKFILL 유지).
```

### 8.7 실패 알림 (SSoT §9⑥)
- `_collect_market`이 market FAIL이면 ntfy.sh 또는 Telegram 무료 푸시 1회.

---

## 9. 지표 엔진 호출 계약 (`metrics/` — 알고리즘 상세 정본 = TECH-DESIGN §6, §15.6)

briefing이 metrics를 부르는 **시그니처만** 고정(순환차단·통화정규화 강제 지점).

### 9.1 입력 조립 (briefing이 수행)

```python
@dataclass(frozen=True)
class PricedHolding:           # 통화정규화 완료 (base=KRW)
    holding: HoldingRow
    value_base: float | None   # quantity*close_raw*(fx if US else 1); USD현금=value_manual*fx
    status: str                # §15.4 enum: 'ok'|'data_pending'|'fx_held'|'warmup'|'failed'

def _held(h) -> PricedHolding:                 # fx 결측으로 USD 자산 보류 (§15.4)
    return PricedHolding(h, None, "fx_held")
```

```python
def build_priced(conn, holdings, fx_ok: bool, us_ok: bool) -> list[PricedHolding]:
    # fx_ok면 환율 1회 조회(없으면 NameError 방지 — fx_ok=True인데 row 없으면 모순이라 보류 처리)
    fx_rate = None
    if fx_ok:
        fx_row = db.latest_fx(conn, "USDKRW")
        fx_rate = fx_row["rate"] if fx_row is not None else None
        fx_ok = fx_rate is not None             # row 실종 시 게이트와 일관되게 보류로 강등
    out = []
    for h in holdings:
        if h.tracking == "manual":      # 현금
            if h.ccy == "USD":
                if not fx_ok: out.append(_held(h)); continue   # G6: USD현금도 fx 의존
                v = h.value_manual * fx_rate
            else: v = h.value_manual                            # KRW 현금
            out.append(PricedHolding(h, v, "ok")); continue
        if h.market == "US" and not us_ok:   # US collect FAIL → stale price여도 강제 보류(게이트 일관)
            out.append(PricedHolding(h, None, "data_pending")); continue
        price = db.latest_price(conn, h.canonical_ticker)
        if price is None:               # G3: row 0건 → 데이터 준비중 보류
            out.append(PricedHolding(h, None, "data_pending")); continue
        if h.market == "US" and not fx_ok:   # fx FAIL → US 평가액 산출 거부 (SSoT §4)
            out.append(_held(h)); continue
        fx = fx_rate if h.market == "US" else 1.0
        out.append(PricedHolding(h, h.quantity * price["close_raw"] * fx, "ok"))
    return out
```

> 보류(`held`/`data_pending`) 종목은 **분모에서 빠지는 게 아니라 "비중 미산출·placeholder"**(G3). USD 자산 보류 시 G6 임계 판정으로 1층 배분 전체 보류 여부 결정.

### 9.2 metrics 함수 시그니처 (순환차단 — SSoT §6)

```python
# portfolio.py
def auto_targets(holdings_without_value: list[HoldingRow]) -> dict[str, float]:
    # G5: 평가액 타입을 아예 안 받음(순환 컴파일-차단). 그룹목표→그룹내 균등.

def drift(priced: list[PricedHolding], targets: dict[str, float],
          band_abs: float, band_rel: float, micro_floor: float) -> DriftResult:
    # ① 자산군(코어/새틀) 단위 집계 후 5/25 "작은 쪽" 플래그. micro_floor 억제.

def core_sat(priced: list[PricedHolding], limit_pct: float) -> CoreSatResult:
    # ② category 기준 코어/새틀 합계 + 30% 한도 초과.

def dca(priced, drift_result, valuation_results, monthly: float) -> DcaResult:
    # ⑥ 드리프트 음수 우선, 저평가는 펀더멘털 게이트 통과 종목만 보조.

def asset_alloc(priced: list[PricedHolding], usd_held: bool,
                threshold_pct: float) -> AllocResult:
    # 1층 equity vs cash. G6: usd_held & USD비중>=threshold → alloc_held=True.

# security.py
def change_pct(ohlcv: OHLCV, prev_close: float | None) -> float | None:
    # 전일 대비 등락. prev_close = 직전 거래일 close_raw(db.prev_close 조회). 없으면 None(MVP는 nullable 허용).
    ...
def valuation(funda: Funda) -> ValuationLabel:
    # ③ 양면 라벨. per_pctile_5y NULL → "워밍업 중(절대 PER만)". 음수PER 제외.
def trend(ohlcv: OHLCV) -> TrendLabel:      # ④ 52주위치·이격도, 맥락용
def regime(market_regime_row) -> str:        # ⑤ CAPE/KOSPI PBR 한 줄
```

> 소수종목(<2)·자동목표 엣지 → drift/core_sat가 플래그 억제(SSoT §6). metrics는 **수치만** 산출, 라벨 문장 톤은 LLM이 덧입힘.

---

## 10. 브리핑 (`briefing.py`)

### 10.1 파이프라인 (SSoT §7 그대로)

```python
def run_briefing(conn, llm: LLMClient, user_id: int = 1) -> int:
    # [선검사] 오늘 수집 완료 핸드오프 (08:00 collect → 08:30 briefing 사이 미완 방지)
    if not collect_complete_today(conn):            # §10.2 — 오늘 기대 거래일 collect_run 부재
        return _save_blocked_briefing(conn, GateResult(True, False, False, "수집 미완 — 브리핑 보류"))
    # [게이트] §10.2
    gate = evaluate_gate(conn)
    if gate.blocked:
        return _save_blocked_briefing(conn, gate)   # "데이터 미갱신" 배너 doc 저장
    # [코드] 통화정규화 + 지표
    priced = build_priced(conn, db.holdings(conn, user_id), fx_ok=gate.fx_ok, us_ok=gate.us_ok)
    metrics = run_all_metrics(priced, conn, settings)        # §9
    # [조립] LLM 입력 dict (문장 생성용, 수치 placeholder)
    sec_inputs = build_security_inputs(metrics, news=db.headlines_map(conn))  # G7 뉴스 슬롯
    port_input = build_portfolio_input(metrics)
    # [LLM 호출+텍스트조립] 06-ai-agent 소유: 배치분할·ct조인(G2)·금지어린트·텍스트 슬롯주입까지.
    #   반환은 **텍스트 전용** SecurityLLMOut + LLM이 누락/중복한 ct(=failed) 목록. 수치는 안 건드림.
    sec_llm, sec_failed = run_securities(llm, sec_inputs)          # 06 §5.2 → (list[SecurityLLMOut], list[HoldExcluded])
    port_comment = run_portfolio(llm, port_input)                 # 06 → {rebalance_note,dca_note,weight_note}
    # [조립] 04 소유: 수치(metrics)를 코드가 직접 박아 최종 SecurityCard/BriefingDoc 생성 (SSoT §7)
    doc = assemble_briefing(metrics, sec_llm, sec_failed, port_comment, gate)   # §10.3
    # [저장] 이력 보존 (date 단독 PK 아님)
    return db.insert_briefing(conn, user_id, doc.to_json(), model="claude-sonnet-4-5")
```

### 10.2 신선도 게이트 (SSoT §7 · S4 · G6)

```python
def collect_complete_today(conn) -> bool:
    """08:00 수집 → 08:30 브리핑 핸드오프 보장(두 cron 독립 실행이라 락 대용 선검사).
       보유 종목이 있는 각 시장(KR/US)에 대해 '오늘 기대 거래일' collect_run row가
       존재(OK/PARTIAL/BACKFILL/OK_HOLIDAY/FAIL 중 무엇이든)하면 수집 사이클이 돈 것으로 본다.
       row 자체가 없으면(=아직 수집 안 끝남) False → 브리핑 보류(전날값 오판정 방지)."""
    today = date.today()
    markets = db.markets_in_use(conn)              # 보유 종목이 있는 시장 집합
    for m in markets:
        run = db.latest_collect_run(conn, m)
        expected = calendar.expected_trade_date(m, today).isoformat()
        if run is None or run["trade_date"] != expected:
            return False                            # 오늘 사이클 미완
    return True

@dataclass(frozen=True)
class GateResult:
    blocked: bool                  # KR·US·FX 모두 미갱신 → 생성 거부
    fx_ok: bool                    # FX FAIL → False (USD 자산 전체 보류)
    us_ok: bool                    # US FAIL → US 종목 제외
    banner: str | None

def evaluate_gate(conn) -> GateResult:
    kr = db.latest_collect_run(conn, "KR")
    us = db.latest_collect_run(conn, "US")
    fx = db.latest_collect_run(conn, "FX")
    def alive(r): return r is not None and r["status"] in {"OK","PARTIAL","BACKFILL","OK_HOLIDAY"}
    if not (alive(kr) or alive(us)):
        return GateResult(True, False, False, "데이터 미갱신 — 브리핑 보류")
    return GateResult(
        blocked=False,
        fx_ok=alive(fx),                       # FX FAIL → USD 자산 보류 (SSoT §4)
        us_ok=alive(us),                       # US FAIL → US 종목 제외
        banner=None if alive(fx) and alive(us) else "일부 시장 데이터 보류",
    )
```

> `BACKFILL`/`OK_HOLIDAY`는 **차단 아님**(정상 진행 + 라벨). `FAIL`만 차단. fx_ok=False → `build_priced`가 USD 자산(US 종목 + USD 현금)을 일괄 보류(G6).

### 10.3 브리핑 조립 (04 소유 — 수치 주입 + DTO 생성)

> **책임 경계(단일화)**: canonical_ticker 조인(G2)·금지어 린트(`BANNED`)·텍스트 슬롯주입은 **06-ai-agent §4·§5가 소유**하고 `run_securities`가 텍스트 전용 `SecurityLLMOut` + 누락/중복 `HoldExcluded`를 반환한다. 04는 그 결과에 **수치(metrics)만 코드로 박아** 최종 `SecurityCard`/`BriefingDoc`을 만든다(04에 별도 `_call_securities`/`validate_briefing`/`inject_slots` 3단을 두지 않음 — 06과 중복·시그니처 충돌 제거).

```python
def assemble_briefing(metrics, sec_llm: list[SecurityLLMOut],
                      sec_failed: list[HoldExcluded],
                      port_comment: dict, gate) -> BriefingDoc:
    # 1) ct로 SecurityLLMOut ↔ metrics 병합 → 최종 SecurityCard (수치는 metrics 값, 텍스트는 LLM)
    by_ct = {o.canonical_ticker: o for o in sec_llm}
    cards = [build_security_card(m, by_ct.get(m.canonical_ticker), gate) for m in metrics.securities]
    #    LLM 누락분(sec_failed)은 status='failed' 카드 + holds_excluded에 등재
    # 2) asset_allocation(1·2층)·dca·regime_label·as_of·banner를 metrics/gate에서 코드가 채움
    # 3) disclaimer는 코드 상수
    return BriefingDoc(..., securities=cards, holds_excluded=sec_failed,
                       portfolio_comment=port_comment, ...)
```

> **숫자 무결성(SSoT §7)**: LLM은 문장·라벨만(`SecurityLLMOut`). 모든 수치 필드는 04가 `metrics`에서 직접 주입. `canonical_ticker` echo는 *식별자*라 §7이 폐기한 "수치 echo 대조"와 별개 — 허용(G2).

### 10.4 LLM 입력 dict 슬롯 (G7 뉴스 연결)

`build_security_inputs`는 종목별로 `{canonical_ticker, name, valuation_label, trend_label, regime, headlines: [{title,url,source}]}`를 LLM에 넘긴다. **수치는 넘기되 LLM은 echo만, 생성 금지.** headlines는 **맥락 참고만**(새 사실 생성 금지 — `prompts/briefing.md`에 명시, 06-ai-agent). 뉴스 미사용 결정 시 이 슬롯 drop.

---

## 11. 스케줄러 (`scripts/`)

### 11.1 엔트리 스크립트

```python
# scripts/run_collect.py
from app import collect, db
if __name__ == "__main__":
    conn = db.connect()
    collect.run_collect(mode="daily")    # 백필은 --backfill 인자

# scripts/run_briefing.py
from app import briefing, db
from app.llm import make_llm_client      # 06-ai-agent 팩토리 (claude -p 어댑터)
if __name__ == "__main__":
    conn = db.connect()
    briefing.run_briefing(conn, llm=make_llm_client())
```

### 11.2 cron (SSoT §9 — 월~금만)

```cron
0  8 * * 1-5  cd .../investbrief && python scripts/run_collect.py
30 8 * * 1-5  cd .../investbrief && python scripts/run_briefing.py
```

> 08:00 수집(겨울 EST 마감+무료소스 EOD publish 지연 흡수) → 08:30 브리핑. 두 cron은 독립 실행이라 **`run_briefing`이 진입 시 `collect_complete_today`로 오늘 수집 완료를 선검사**(§10.2)해 미완이면 보류한다(전날/부분 데이터 오판정 방지). 30분 윈도우가 빠듯하면(FMP 백오프로 수집 지연) 수집 07:45 또는 브리핑 08:45로 조정. **macOS SoT = launchd `StartCalendarInterval` + `caffeinate`/`pmset` wake**(절전 대응, G9), cron은 fallback 문서. 휴장일은 collect가 `OK_HOLIDAY`로 정상 skip.

> macOS SoT=launchd, cron=fallback 확정(BAL-35 — `ops/*.plist`·`install.sh`, dev-guide `docs/BAL-35-dev-guide.md`).

---

## 12. 에러 처리 · 재시도 · fallback 요약

| 계층 | 전략 | 근거 |
|---|---|---|
| 소스 호출 | `@retry(3)` 지수백오프 + 종목 단위 격리 | SSoT §5 |
| 응답 유효성 | 행수>0 + 최신일자 일치, 빈 CSV→`EmptyResponseError` | SSoT §4 |
| 시세 fallback | US: Stooq→yfinance→Finnhub quote. 새 row 안 만들고 MAX(trade_date) 사용 | SSoT §4·§5 |
| fx 결측 | **산출 거부**(USD 자산 보류) — NULL 분모 제외 금지 | SSoT §4 |
| row 0건 | "데이터 준비중" 보류(분모 제외 아님) | G3 |
| LLM 금지어 | 정규식 검출→재호출 1회→재실패 차단 | SSoT §7 |
| LLM 종목 누락/중복 | ct left-join, 미매칭→"처리 실패" 카드 | G2 |
| collect FAIL | ntfy.sh/Telegram 푸시 + 게이트 차단/제외 | SSoT §9 |

---

## 13. 다른 영역 의존 / 인터페이스 요약

- **06-ai-agent**: `LLMClient.generate(prompt, schema)->dict` 구현(`claude -p --output-format json --append-system-prompt`(§15.1) + `--json-schema`·Pydantic 파싱·재호출). `make_llm_client()` 팩토리·`prompts/briefing.md`·content JSON 스키마(`SECURITY_SCHEMA`/`PORTFOLIO_SCHEMA`)·금지어 `BANNED`·few-shot·캐싱 정책 소유. LLM 출력 DTO = `SecurityLLMOut`(텍스트만). **canonical_ticker echo 필수**(G2).
- **metrics**: §9 시그니처 구현. 내부 알고리즘 정본 = TECH-DESIGN §6(§15.6). 본 문서는 호출 계약·통화정규화·순환차단 강제만 소유.
- **03-frontend**: `BriefingDoc`/`SecurityCard`(§4.4=§15.2) DTO + `FreshnessBadge`(§6.3) 소비. `portfolio_comment`는 dict(`{rebalance_note,dca_note,weight_note}`). 템플릿은 DTO만 신뢰, content_json 직접 인덱싱 금지.
- **DB**: SSoT §4 DDL 그대로. `db.py`가 `MAX(trade_date)` 조회·조정가 비누적 캐시 소유.
