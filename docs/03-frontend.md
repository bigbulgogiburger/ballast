# 03 · 프론트엔드 명세 — AI 투자 브리핑 PoC

> SSoT: `TECH-DESIGN.md` v3.2 (**DTO·색·키·런타임 정본 = §15 Contract SoT, 충돌 시 §15 우선**) · 연계: `00-e2e-flow.md`(S1/S8 계약, G3/G5/G6/G10/G11), `02-design.md`(디자인 토큰)
> 범위: FastAPI + Jinja2 SSR 프론트엔드 — 라우트/템플릿 구조, 보유자산 입력 폼·검증, 요약뷰 펼침/접힘, 자산배분 시각화, 신선도 배지, 정적 자산·CSS 변수, 접근성.
> 원칙(SSoT §1·§8): **SSR 단일 페이지 · JS 최소 · 표시와 계산 분리(템플릿은 DTO만 신뢰, 계산 없음) · 30초 스캔 가능 요약뷰 · 모든 산출물에 면책.**
> 작성일: 2026-06-01

---

## 0. 결정 요약 (이 문서가 확정하는 것)

| # | 결정 | 근거 |
|---|---|---|
| F1 | 라우트 4개: `GET /`, `GET/POST /holdings`, `GET/POST /settings`, `POST /api/regenerate`(127.0.0.1) | SSoT §8 |
| F2 | 템플릿은 `BriefingDoc` DTO(§3.1)만 신뢰. 계산·집계 0. Jinja2는 포맷팅만 | SSoT §1, e2e G11 |
| F3 | JS는 native `<details>`/`<summary>`로 펼침·접힘 → JS 0줄 가능. 폼 검증은 HTML5 + 서버 검증 이중 | SSoT §8 "JS 최소" |
| F4 | 등락/경고 **기능색**과 **밀도 토큰**을 신규 정의(design.md에 없음) | SSoT §8 명시 |
| F5 | 폼 검증은 **서버가 SoT**. POST 실패 시 동일 폼 + 에러 재렌더(상태 보존) | SSoT §1, e2e G5 |
| F6 | 보류/제외/워밍업 상태는 카드 placeholder로 렌더(숨김 금지) | e2e G3/G6 |
| F7 | 손익/수익률 미표시. 평단은 현지통화 참고만 | e2e G8, SSoT §6 |

---

## 1. 라우트 ↔ 화면 ↔ 핸들러 시그니처

`app/main.py` (FastAPI). 모든 GET은 `HTMLResponse`(Jinja2 `TemplateResponse`).

```python
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

app = FastAPI()
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# --- 대시보드 (SSoT §8: 오늘 briefing_date 중 MAX(created_at) row) ---
@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    doc: BriefingDoc | None = load_latest_briefing()   # db.py, MAX(created_at)
    badge: FreshnessBadge = build_freshness_badge()     # §4 (e2e G10)
    return templates.TemplateResponse("dashboard.html",
        {"request": request, "doc": doc, "badge": badge})

# --- 보유자산 입력/편집 ---
@app.get("/holdings", response_class=HTMLResponse)
def holdings_get(request: Request) -> HTMLResponse:
    rows: list[HoldingRow] = list_holdings()            # db.py
    return templates.TemplateResponse("holdings.html",
        {"request": request, "rows": rows, "errors": None, "form": None})

@app.post("/holdings")
def holdings_post(request: Request) -> HTMLResponse | RedirectResponse:
    form = parse_holdings_form(request)                 # §2.3
    result: HoldingsValidation = validate_holdings(form) # §2.4 (e2e G5/G6)
    if not result.ok:
        return templates.TemplateResponse("holdings.html",
            {"request": request, "rows": result.rows, "errors": result.errors,
             "form": form}, status_code=400)            # F5: 상태 보존 재렌더
    save_holdings(result.rows)                           # db.py, category 영속화(G4)
    return RedirectResponse("/holdings?saved=1", status_code=303)  # PRG 패턴

# --- 설정 ---
@app.get("/settings", response_class=HTMLResponse)
def settings_get(request: Request) -> HTMLResponse: ...
@app.post("/settings")
def settings_post(request: Request) -> HTMLResponse | RedirectResponse: ...

# --- 개발용 수동 재생성 (SSoT §8: 127.0.0.1 바인딩 한정) ---
@app.post("/api/regenerate")
def regenerate(request: Request):
    if request.client.host != "127.0.0.1":
        raise HTTPException(403)
    run_briefing_now()                                   # briefing.py
    return RedirectResponse("/", status_code=303)
```

| 라우트 | 템플릿 | 핵심 컨텍스트 |
|---|---|---|
| `GET /` | `dashboard.html` | `doc: BriefingDoc \| None`, `badge: FreshnessBadge` |
| `GET /holdings` | `holdings.html` | `rows`, `errors=None`, `form=None`, query `saved` |
| `POST /holdings` | `holdings.html`(실패) / 303→`/holdings`(성공) | `rows`, `errors`, `form`(상태 보존) |
| `GET/POST /settings` | `settings.html` | `settings: dict`, `errors` |

> `doc is None`(아직 브리핑 없음, day-0 적재중) → dashboard는 "초기 데이터 적재중" 빈 상태 카드 렌더(e2e G3).

---

## 2. 보유자산 입력 폼 (`holdings.html`) + 검증

### 2.1 폼 구조 (편집 가능 테이블, 행 = holdings 1건)

자산 타입 3종(SSoT §4 instrument): **개별주(stock) / ETF(etf) / 달러예금(cash)**. 한 폼에서 여러 행 입력·편집. 행 추가는 "빈 행 1개 + JS 없이 서버 왕복" 또는 native `<template>` 복제(JS 5줄). PoC는 **고정 N행 + 빈 행 = 신규**로 단순화.

행별 입력 필드(name은 배열 인덱스: `rows[{i}][field]`):

| 필드 | input | 적용 instrument | 비고 |
|---|---|---|---|
| `instrument` | `<select>` stock/etf/cash | 전체 | 행 타입 선택 |
| `canonical_ticker` | `<input type=text>` | stock, etf | 예 `005930`, `VOO`, `BRK.B`. cash는 비활성 |
| `market` | `<select>` KR/US | stock, etf | cash는 비활성(USD 고정 가정) |
| `quantity` | `<input type=number step=any min=0>` | stock, etf | cash는 비활성 |
| `value_manual` | `<input type=number step=any min=0>` | cash | 평가액 직접입력 |
| `ccy` | `<select>` KRW/USD | 전체 | cash는 USD 기본 |
| `avg_price` | `<input type=number step=any min=0>` | stock, etf (선택) | 현지통화 참고만(F7) |
| `category` | `<select>` 자동/core/satellite | stock, etf (선택) | "자동"=서버 화이트리스트 판정(G4) |
| `target_pct` | `<input type=number step=0.1 min=0 max=100>` | 전체 (선택) | "전부 수동 or 전부 자동" 배타(G5) |

> SSoT §4 매핑: `asset_class` = stock/etf→`equity`, cash→`cash`(서버 자동, 폼에 노출 안 함). `tracking` = stock/etf→`auto`, cash→`manual`(서버 자동). UI는 "개별주/ETF/달러"로만 보여줌(§8).

### 2.2 instrument별 활성 필드 (클라이언트 disable + 서버 검증)

JS 최소 원칙: `instrument` select `onchange`로 비해당 `<input>`을 `disabled`+회색 처리(접근성 §7). JS가 꺼져도 **서버 검증이 SoT**라 안전. cash 행: ticker/market/quantity/avg_price/category 비활성, value_manual+ccy(USD)만 활성.

### 2.3 폼 파싱 DTO (`models.py`)

```python
@dataclass(frozen=True)
class HoldingForm:
    """POST /holdings 원본 입력(검증 전). 모든 값 str|None — 서버에서 타입 변환."""
    instrument: str            # 'stock'|'etf'|'cash'
    canonical_ticker: str | None
    market: str | None         # 'KR'|'US'
    quantity: str | None
    value_manual: str | None
    ccy: str | None
    avg_price: str | None
    category: str | None       # ''|'core'|'satellite'  ('' = 자동판정)
    target_pct: str | None

@dataclass(frozen=True)
class HoldingsValidation:
    ok: bool
    rows: list[HoldingRow]              # 검증 통과 시 정규화된 행
    errors: list["FieldError"]          # 실패 시 (ok=False)

@dataclass(frozen=True)
class FieldError:
    row_index: int                      # -1 = 폼 전역 에러(합계 등)
    field: str | None                   # None = 행 전역
    message: str                        # 사용자 노출 한국어
```

### 2.4 검증 규칙 (서버, `validate_holdings(form) -> HoldingsValidation`)

SSoT §4·§6·e2e G5/G6를 그대로 반영. 실패는 **400 + 동일 폼 재렌더**(F5).

| 규칙 | 조건 | 에러 메시지 |
|---|---|---|
| auto 필수 | stock/etf: `canonical_ticker`·`market`·`quantity` 모두 필수, quantity>0 | "종목코드·시장·수량은 필수입니다" |
| manual 필수 | cash: `value_manual`>0 필수, ccy 필수 | "달러예금은 평가액을 입력하세요" |
| ccy 일관 | market=US → ccy 권장 USD; cash → ccy=USD | "달러예금의 통화는 USD입니다" |
| ticker 형식 | 영숫자·`.`만 (정규화는 tickers.py 책임, 폼은 형식만) | "종목코드 형식이 올바르지 않습니다" |
| category 값 | `''`/`core`/`satellite`만 | — |
| **target 배타** (G5) | target_pct가 **일부 행만** 채워짐 → reject | "목표비중은 전부 입력하거나 전부 비워두세요" |
| **target 합계** | 전부 수동이면 합 100%±0.5 검증(또는 정규화 안내) | "수동 목표비중 합이 100%가 아닙니다 (현재 {sum}%)" |
| 중복 ticker | 같은 canonical_ticker 2행 | "중복된 종목코드: {ct}" |

> **자동 목표비중은 저장하지 않음**(e2e G5): target_pct 미입력 행은 NULL 유지, 비중은 S5 런타임 산출. 폼은 NULL만 저장.
> **category 자동판정**(e2e G4): category=`''`이면 서버가 `CORE_ETF_WHITELIST`(tickers.py frozenset)로 판정 후 `holdings.category`에 영속화. 사용자 명시값 우선.

### 2.5 성공 피드백 / 빈 상태

- 저장 성공: 303 redirect `?saved=1` → 상단 success 배너("저장되었습니다", `--c-success`).
- 보유 0건: "보유 자산을 추가하세요" 안내 + 첫 빈 행.

---

## 3. 대시보드 (`dashboard.html`) — 표시 DTO 계약

### 3.1 `BriefingDoc` DTO (`models.py`, e2e G11) — 템플릿이 신뢰하는 유일한 소스

briefing.py가 슬롯 주입 후 직렬화하고, dashboard가 역직렬화해 렌더. **수치는 코드 계산값**(SSoT §7), 문장은 LLM. 템플릿은 계산/집계 금지.

> **정본 = TECH-DESIGN §15.2/§15.4.** 아래는 그대로 옮긴 것이며 충돌 시 §15가 우선. 템플릿은 이 필드명만 신뢰한다.

```python
@dataclass(frozen=True)
class SecurityCard:                       # §15.2 — 수치는 코드 계산값, comment/trend_note/investment_points만 LLM
    canonical_ticker: str                 # join 키(e2e G2). 표시는 name 우선
    name: str; instrument: str; asset_class: str; category: str | None
    status: str                           # §15.4: 'ok'|'data_pending'|'fx_held'|'warmup'|'failed' ← 렌더 분기
    # --- 수치 슬롯(코드 주입) ---
    change_pct: float | None              # 전일 대비 등락(등락색)
    current_pct: float                    # 전체 대비 현재 비중
    target_pct: float | None; drift: float | None   # 자동목표면 drift 참고용
    rebalance_flag: bool                  # 5/25 플래그(작은 쪽)
    per: float | None; pbr: float | None; div_yield: float | None
    valuation_pctile: float | None        # NULL → warmup degrade(G3)
    valuation_label: str                  # ③ 양면 라벨 or "5년 워밍업 중(절대 PER만)"
    week52_pos: float | None; sma200_gap: float | None   # ④ 맥락용
    # --- 문장 슬롯(LLM = SecurityLLMOut 머지) ---
    comment: str                          # 맥락형 코멘트(요약뷰 노출)
    trend_note: str                       # 추세·밸류 양면 문장(펼침 본문)
    investment_points: list[str]          # 투자 포인트 항목

@dataclass(frozen=True)
class HoldExcluded:                       # §15.2 — G2 전용(LLM 미매칭/중복)
    canonical_ticker: str
    reason: str

@dataclass(frozen=True)
class BriefingDoc:                        # §15.2 — content_json 직렬화 정본
    briefing_date: str; model: str; created_at: str
    banner: str | None                    # "초기 데이터 적재중"·"데이터 미갱신" 등(G3/S4). 정상시 None
    regime_label: str                     # ⑤ top-level 1개(카드별 아님)
    as_of: dict                           # {"price","funda","fx"} 3키 고정
    asset_allocation: dict                # 1층 {equity_pct,cash_pct} + 2층 {core_pct,satellite_pct,satellite_over_limit:bool}
    securities: list[SecurityCard]        # 보류/제외/워밍업 포함(status로 분기)
    holds_excluded: list[HoldExcluded]    # LLM 미매칭/중복만(G2). fx/데이터 보류는 securities[].status
    dca: dict                             # 적립 후보(드리프트 우선)
    portfolio_comment: dict               # {rebalance_note, dca_note, weight_note} (LLM 문장)
    disclaimer: str                       # 고정 면책(SSoT §1·§12)
```

> **요약뷰 펼침 판정(needs_attention)은 템플릿이 `status != 'ok'` 또는 `rebalance_flag` 또는 `asset_allocation.satellite_over_limit`로 파생**(별도 DTO 필드 없음 — 표시 계산이 아니라 단순 분기라 허용). 자산배분 1층 보류 여부는 `fx_held` 종목 존재로 표시.

### 3.2 대시보드 화면 순서 (SSoT §8 위→아래)

```
1. 헤더 (워드마크 리브랜딩 + 날짜) + 면책 한 줄 + regime_label(레짐 한 줄, top-level)
2. doc.banner (있으면, --c-warn 블록)          ······· G3/S4
3. 신선도 배지 (시세/펀더/환율 기준일)         ······· §4
4. 포트폴리오 요약: 1층/2층 자산배분 시각화      ······· §5 (asset_allocation dict)
   - fx_held 종목 존재 → "1층 배분 산출 보류(환율 데이터 결측)" placeholder
5. 요약뷰 종목 리스트(status로 분기):
   - 펼침(<details open>): status!='ok' 또는 rebalance_flag (needs_attention 파생)
   - 나머지 접힘(<details>) — comment만 노출
   - status='data_pending' → "데이터 준비중" placeholder 카드
   - status='warmup'       → valuation "5년 워밍업 중(절대 PER만)"
   - status='fx_held'      → "환율 결측으로 비중 산출 보류"
   - status='failed'       → holds_excluded에도 등장(LLM 처리 실패, reason 표시)
6. 리밸런싱 검토구간 + DCA (portfolio_comment.rebalance_note / .dca_note)
7. 면책 푸터 (disclaimer 전문)
```

---

## 4. 신선도 배지 (e2e G10, SSoT §8)

### 4.1 입력 계약 (`build_freshness_badge() -> FreshnessBadge`)

```python
@dataclass(frozen=True)
class FreshnessBadge:
    price_age_days: int          # MAX(price_snapshot.trade_date) vs 오늘 기대 거래일(calendar)
    funda_label: str             # report_date 기반 "3개월 전" 등
    fx_age_days: int             # MAX(fx_snapshot.trade_date) vs 기대일
    worst_level: str             # 'fresh'|'stale'|'warn' — 종목별 최악(최고령) 집계
    consecutive_fallback: bool   # N일 연속 fallback → 경고 블록(SSoT §8)
```

> 기준일은 종목별 `MAX(trade_date)` vs `calendar.py` 기대 거래일. 펀더는 `report_date`. **포트폴리오 배지 = 종목별 최악(가장 오래된)값 집계.** 휴장(`OK_HOLIDAY`)은 stale로 오판 금지(배지가 calendar 기대일로 판정하므로 자동 흡수).

### 4.2 렌더

```html
<div class="badge-row" role="status" aria-label="데이터 신선도">
  <span class="badge badge--{{ badge.worst_level }}">시세: {{ badge.price_age_days }}일 전</span>
  <span class="badge">펀더멘털: {{ badge.funda_label }}</span>
  <span class="badge">환율: {{ badge.fx_age_days }}일 전</span>
</div>
{% if badge.consecutive_fallback %}
  <p class="warn-block" role="alert">데이터가 N일 연속 갱신되지 않았습니다.</p>
{% endif %}
```

- `fresh`(0~1일) `--c-success` / `stale`(2~4일) `--c-muted` / `warn`(5일+) `--c-warn`.

---

## 5. 자산배분 시각화 (CSS only, JS 0)

2층 구조(SSoT §6: [1층] 주식/현금, [2층] 코어/새틀). **수평 누적 바**로 표현 — SVG/canvas 불필요, flex + width%.

`asset_allocation` dict(§15.2) = 1층 `{equity_pct, cash_pct}` + 2층 `{core_pct, satellite_pct, satellite_over_limit}`. 보류 판정은 `fx_held` 종목 존재 여부(템플릿에 `alloc.equity_pct is none`로 전달하거나 `doc.banner`로 표시).

```html
<section class="alloc">
  {% set a = doc.asset_allocation %}
  <h3 class="title-sm">자산군 배분 (주식 / 현금)</h3>
  {% if a.equity_pct is none %}
    <p class="placeholder">환율 데이터 결측으로 1층 배분 산출을 보류했습니다.</p>
  {% else %}
    <div class="stack-bar" role="img"
         aria-label="주식 {{ a.equity_pct }}% 현금 {{ a.cash_pct }}%">
      <span class="stack-seg" style="width: {{ a.equity_pct }}%; background: var(--alloc-equity);">
        <span class="seg-label">주식 {{ '%.0f'|format(a.equity_pct) }}%</span></span>
      <span class="stack-seg" style="width: {{ a.cash_pct }}%; background: var(--alloc-cash);">
        <span class="seg-label">현금 {{ '%.0f'|format(a.cash_pct) }}%</span></span>
    </div>
  {% endif %}

  <h3 class="title-sm">주식 내 코어 / 새틀</h3>
  <div class="stack-bar" role="img" aria-label="코어 {{ a.core_pct }}% 새틀 {{ a.satellite_pct }}%">
    <span class="stack-seg" style="width: {{ a.core_pct }}%; background: var(--alloc-core);">
      <span class="seg-label">코어 {{ '%.0f'|format(a.core_pct) }}%</span></span>
    <span class="stack-seg" style="width: {{ a.satellite_pct }}%; background: var(--alloc-sat);">
      <span class="seg-label">새틀 {{ '%.0f'|format(a.satellite_pct) }}%</span></span>
  </div>
  {% if a.satellite_over_limit %}
    <p class="warn-block">새틀라이트(개별주)가 한도(30%)를 초과했습니다.</p>
  {% endif %}
</section>
```

- 라벨이 세그먼트보다 넓으면 바 위에 범례로 fallback(작은 비중 종목 텍스트 클리핑 방지).
- 색은 **기능색 신규 토큰**(§6): `--alloc-equity`/`--alloc-cash`/`--alloc-core`/`--alloc-sat`. design.md timeline 파스텔은 "in-product agent timeline 전용"이라 **재사용 금지**(design.md Don't) → 별도 토큰 정의.

---

## 6. 정적 자산 · CSS 변수 (02-design 토큰 연동)

### 6.1 구조

```
app/static/
├── css/
│   ├── tokens.css      # design.md → CSS 변수 (리브랜딩) + 신규 기능색·밀도
│   └── app.css         # 컴포넌트 스타일 (tokens.css 변수만 참조)
└── fonts/              # Inter(CursorGothic 대체, design.md 명시) · JetBrains Mono
```

### 6.2 `tokens.css` — design.md 토큰 매핑 + 신규 정의

design.md 색/타이포/간격/라운드를 그대로 CSS 변수로. **워드마크·Cursor Orange·타임라인 펄은 리브랜딩**(SSoT §8) — Orange는 1차 CTA/워드마크에만 scarce 유지(design.md Do).

```css
:root {
  /* === design.md 매핑 === */
  --c-canvas: #f7f7f4; --c-canvas-soft: #fafaf7; --c-card: #ffffff;
  --c-surface-strong: #e6e5e0;
  --c-hairline: #e6e5e0; --c-hairline-soft: #efeee8; --c-hairline-strong: #cfcdc4;
  --c-ink: #26251e; --c-body: #5a5852; --c-muted: #807d72; --c-muted-soft: #a09c92;
  --c-primary: #0c8599; --c-primary-active: #0a6e7f; --c-on-primary: #ffffff; /* Brief Teal, §15.3 */
  --c-success: #1f8a65; --c-error: #cf2d56;
  --r-xs:4px; --r-sm:6px; --r-md:8px; --r-lg:12px; --r-pill:9999px;
  --s-xxs:4px; --s-xs:8px; --s-sm:12px; --s-base:16px; --s-md:20px;
  --s-lg:24px; --s-xl:32px; --s-xxl:48px; --s-section:80px;
  --font-sans: Inter, system-ui, "Helvetica Neue", Arial, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, monospace;

  /* === 신규: 등락/경고 기능색 (SSoT §15.3 정본 — 한국 관습) === */
  --c-up:   #d92d4e;   /* 상승=빨강 (move-up) */
  --c-down: #1971c2;   /* 하락=파랑 (move-down) */
  --c-up-soft:   #fbe6ec; --c-down-soft: #e7f0fb;
  --c-flat: #807d72;

  /* === 신규: 상태/경고 색 (02-design §2.2 정본 전량 이전, §15.3) === */
  --c-warn: #b8740f;        --c-warn-soft: #fbf0dd;   /* 5/25·연속 fallback·한도초과 (=status-warn) */
  --c-hold: #807d72;        --c-hold-soft: #efeee8;   /* 보류 placeholder (data_pending/fx_held) */
  --c-degrade: #8a7fc2;                               /* warmup degrade (valuation_pctile NULL) */
  --c-info: #0c8599;                                  /* 정보 배너(초기 적재중/BACKFILL) = primary */
  --c-fail: #b3243f;        --c-fail-soft: #fbe6ec;   /* 처리 실패 카드(LLM 미매칭/중복, G2) */

  /* === 신규: 자산배분 시각화 색 (timeline 파스텔 재사용 금지) === */
  --alloc-equity:#26251e; --alloc-cash:#807d72;
  --alloc-core:  #5a5852; --alloc-sat: #c08532;

  /* === 신규: 데이터 밀도 토큰 (30종목 고밀도 표, SSoT §8) === */
  --density-row-h: 32px;        /* 고밀도 행 높이 */
  --density-fs: 13px;           /* 표 폰트 */
  --density-lh: 1.35;           /* 좁은 행간 */
}
.tabular { font-variant-numeric: tabular-nums; font-feature-settings:"tnum"; }
```

> **색 정본(SSoT §15.3)**: 등락색은 한국 관습(상승=빨강 #d92d4e / 하락=파랑 #1971c2). design.md `semantic-success/error`(검증 상태용)와 hex·용도 모두 분리. CTA는 Teal(#0c8599). 상태색·alloc 토큰의 전체 정의는 02-design §2를 정본으로 본 tokens.css에 동기화(누락 금지).

### 6.3 적용 경계 (SSoT §8)

- design.md 톤(Inter 400, cream, hairline-only, 80px rhythm) = **헤더·면책·브리핑 내러티브 텍스트**.
- 30종목 수치표 = **밀도 서브시스템**(`--density-*`, `tabular-nums`, 좁은 행간) — 별도.
- 드롭섀도 금지(hairline-only). 라운드: CTA `--r-md`, 카드 `--r-lg`, 배지 `--r-pill`.

---

## 7. 접근성 (WCAG AA 목표, PoC 현실 수준)

| 항목 | 적용 |
|---|---|
| 시맨틱 마크업 | `<main>`/`<section>`/`<h1~h3>` 순서 유지, 카드 = `<article>` |
| 펼침/접힘 | native `<details>/<summary>` — 키보드·SR 기본 지원(JS 불필요) |
| 폼 라벨 | 모든 `<input>`에 `<label for>` 연결. disabled 필드는 `aria-disabled` |
| 에러 | `FieldError`를 해당 input에 `aria-describedby`로 연결, `role="alert"` |
| 상태 영역 | 신선도 배지 `role="status"`, 경고 블록 `role="alert"` |
| 색 의존 금지 | 등락은 색 + 부호(`+`/`-`)/화살표 텍스트 병기(색맹 대응) |
| 대비 | body #5a5852 on #f7f7f4 ≈ 7:1(AA 통과). muted-soft는 비활성 텍스트만 |
| 터치 타깃 | CTA 40px+, 폼 input 44px(design.md) |
| 시각화 | stack-bar `role="img"` + `aria-label`에 수치 명시 |
| 단위 표기 | 모든 % 뒤 "%", 통화는 ₩/$ 명시. 비중 미산출은 "—" + 사유 |

---

## 8. JS 정책 (최소)

- **필수 0**: 펼침/접힘은 `<details>`. 검증은 서버 SoT.
- **선택(progressive enhancement, 꺼져도 동작)**:
  1. instrument select → 비해당 input `disabled` 토글 (~10줄, §2.2)
  2. 행 추가 버튼 → `<template>` 복제 (~10줄)
- 외부 JS 프레임워크·번들러 없음. `app/static/js/holdings-form.js` 1개 파일, `<script defer>`.

---

## 9. 다른 영역과의 인터페이스 (의존 계약)

| 방향 | 계약 | 출처 |
|---|---|---|
| ← `briefing.py` | `BriefingDoc`(§3.1) JSON 직렬화 후 `briefing.content_json` 저장 → `load_latest_briefing()`이 역직렬화 | e2e G11 |
| ← `db.py` | `list_holdings()→list[HoldingRow]`, `save_holdings(rows)`(category 영속화), `load_latest_briefing()`(MAX created_at) | SSoT §8, G4 |
| ← `metrics/` | 모든 수치 슬롯은 metrics 계산값(템플릿 계산 0). 1층 보류는 `asset_allocation.equity_pct is None`(fx 게이트 결과) | SSoT §6/§7, G6 |
| ← `calendar.py` | 신선도 배지의 "기대 거래일" | e2e G10 |
| ← `tickers.py` | `CORE_ETF_WHITELIST` frozenset(category 자동판정) | e2e G4 |
| → `models.py` | 폼 DTO(`HoldingForm`·`HoldingsValidation`·`FieldError`)는 본 문서 소유. `BriefingDoc`·`SecurityCard`·`HoldExcluded`·`FreshnessBadge`는 **§15.2 정본**(여기선 소비만) | §15.2 |

> **상위 의존**: `SecurityCard.canonical_ticker`를 LLM join 키로 쓰는 전제는 e2e **G2**(briefing.py). `status` enum(`ok/data_pending/fx_held/warmup/failed`, §15.4)은 **G3/G6** 게이트 결과에 의존 — metrics/briefing이 이 값을 채워줘야 템플릿이 분기 가능. `asset_allocation`·`portfolio_comment`는 dict(§15.2)로 전달된다.
