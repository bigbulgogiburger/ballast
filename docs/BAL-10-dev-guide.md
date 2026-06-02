# BAL-10 dev-guide — `app/calendar.py` (XKRX/XNYS 거래일 로직)

> SSoT 우선순위: **TECH-DESIGN.md §15 (Contract SoT)** > `docs/05-database.md` / `docs/04-backend.md`.
> 시그니처 정본: **`docs/BAL-1-m1a-orchestration.md` §2.3 seam 계약** (단, §15는 calendar를 정의하지 않으므로 §2.3 ↔ 04-backend §6.1 사이에 **파라미터 순서/타입 드리프트**가 존재 — `## 미해결 질문` Q1·Q2 참조. 본 가이드는 §2.3을 정본으로 채택하되 그 충돌을 명시한다).
> 범위: **W1 (BAL-1 수직 슬라이스, Wave-1)** 만. 어댑터·collect·metrics는 Out of scope.

---

## 1. 목표 & 배경

### 이슈 요약
`app/calendar.py`는 KR(XKRX)/US(XNYS) 시장의 **거래일 판정·직전 거래일 계산·수집 기준일(expected_trade_date) 산출**을 담당하는 순수 계산 모듈이다. 현재 W0 스텁(1줄 docstring)만 존재한다. `pandas_market_calendars`의 `XKRX`(한국거래소)·`XNYS`(NYSE) 캘린더를 래핑해 3개 함수로 자체 분해한다.

- `is_trading_day` — 특정 날짜가 해당 시장 거래일인지 판정
- `prev_trading_day` — 특정 날짜 **이전**의 가장 가까운 거래일
- `expected_trade_date` — collect가 "오늘 기준 기대하는 데이터 거래일". **핵심은 US 규칙**: 무료 소스 EOD publish 지연 때문에 08:00 KST 수집 시점에 받을 수 있는 미국 데이터는 **직전 거래일** 마감분이다(KR은 오늘이 거래일이면 오늘).

### W1 슬라이스(BAL-1) 내 역할/의존
`BAL-1-m1a-orchestration.md` §1 DAG 기준:

- BAL-10은 **격리 foundation 3종(BAL-8 db / BAL-9 tickers / BAL-10 calendar) 중 하나**. 파일 비중복, 충돌 0 → **Wave-1에서 BAL-8·9와 3-way 진짜 병렬** 가능.
- **의존: 없음**. `pandas_market_calendars` 외부 라이브러리만 의존.
- **소비자**: BAL-11 `app/sources/kr.py`가 `calendar.expected_trade_date`를 내부에서 사용(§2.5 주석), BAL-12 통합 E2E가 005930 expected_trade_date 정확성을 게이트로 검증(§3 W-1 게이트).
- Wave-1 게이트(§3): **"calendar: 005930 expected_trade_date 정확"** — KR 종목 기준 기대 거래일이 휴장·주말을 정확히 반영해야 W-2(BAL-11) 진입.

---

## 2. 영향 파일

| 파일 | 작업 | 비고 |
|------|------|------|
| `app/calendar.py` | **수정(스텁→구현)** | 함수 3종 + 모듈 캘린더 핸들 2개(`XKRX`/`XNYS`) |
| `tests/test_calendar.py` | **신규** | 순수계산 단위 테스트(필수) + mcal 경계 케이스 |
| `requirements.txt` | 변경 없음 | `pandas-market-calendars` 이미 존재(13번째 줄). **단, 현재 venv 미설치 — `pip install -r requirements.txt` 선행 필요**(`## 엣지 & 리스크` R5) |

> 표준 라이브러리 `datetime`(`date`, `datetime`)만 추가 import. `app/models.py`·`app/db.py` 등 타 모듈 **수정 금지**(격리 foundation 원칙).

---

## 3. 구현 단계 (자체 분해 3단계)

전제: 모듈 상단에서 캘린더 핸들을 **모듈 로드 시 1회 생성**해 함수 호출마다 재생성하지 않는다(04-backend §6.1 패턴).

```python
import pandas_market_calendars as mcal
_KR = mcal.get_calendar("XKRX")   # 한국거래소
_US = mcal.get_calendar("XNYS")   # NYSE
```

market 코드 → 캘린더 매핑은 작은 dict 또는 `if/elif`로 분기하고, **알 수 없는 market은 `ValueError`로 즉시 실패**(조용한 잘못된 기본값 금지).

### 단계 1 — `is_trading_day`
- **로직**: `_cal.valid_days(start_date=d, end_date=d)`(또는 `schedule(d, d)`)의 결과 행수가 1이면 거래일, 0이면 휴장/주말. mcal `valid_days`는 tz-aware `DatetimeIndex`를 반환하므로 `len(...) > 0` 으로 판정.
- **검증 포인트**:
  - 평일 정상 거래일 → `True`
  - 토/일 → `False`
  - 알려진 휴장일(예: KR 신정 1/1, US Independence Day 7/4) → `False`
  - `market` ∈ {'KR','US'} 외 값 → `ValueError`

### 단계 2 — `prev_trading_day`
- **로직**: `d` **직전(미포함)**의 가장 가까운 거래일. `valid_days(start=d-lookback, end=d - 1일)` 윈도우의 마지막 원소를 취한다. 연휴를 넘기기 위해 lookback 윈도우는 충분히 넓게(예: 14일) 잡되, 빈 결과 방어(`## 엣지` R2).
- **경계 정의 고정 필요**: "`d` 자신이 거래일이어도 결과는 `d` 미만"인지(strictly previous), 아니면 "`d`가 거래일이면 `d` 반환"인지는 **이름상 strictly-previous로 채택**(`prev`). 04-backend §10.671 "직전 거래일 close_raw" 용례와 정합. 확정은 Q3.
- **반환형**: `date`(tz 제거한 순수 날짜).
- **검증 포인트**:
  - 화요일 입력 → 직전 월요일
  - 월요일 입력 → 직전 금요일(주말 스킵)
  - 연휴 다음 영업일 입력 → 연휴 직전 거래일(다중일 스킵)

### 단계 3 — `expected_trade_date` (핵심)
- **로직** (04-backend §6.1 주석 + TECH-DESIGN v3.2 ⑦ 기준):
  - **KR**: 인자 날짜가 거래일이면 그 날짜, 아니면 직전 거래일.
    → `d if is_trading_day('KR', d) else prev_trading_day('KR', d)`
  - **US**: **무조건 직전 거래일**. 08:00 KST 수집 시점엔 미국 장이 아직 안 열렸거나(당일 데이터 없음) EOD publish 지연으로 전일 마감분만 확보 가능.
    → `prev_trading_day('US', d_or_today)` (인자 날짜가 거래일이어도 직전 거래일을 기대)
- **반환형**: `date`.
- **검증 포인트** (Wave-1 게이트):
  - KR 평일(거래일) → 같은 날
  - KR 토요일 → 직전 금요일
  - KR 휴장일(연휴) → 연휴 직전 거래일
  - US 평일 → 직전 거래일(같은 날 아님!) — US 규칙의 핵심 회귀 방지
  - US 월요일 → 직전 금요일

> ⚠️ **US "직전거래일" 규칙이 본 이슈의 핵심**. KR과 US의 분기가 정확히 나뉘는지가 단위 테스트의 1순위 단언.

---

## 4. 인터페이스 (§2.3 seam 정본)

`BAL-1-m1a-orchestration.md` §2.3을 **정본**으로 가져온다. §15는 calendar를 정의하지 않으므로 §2.3이 시그니처 SoT다.

```python
def is_trading_day(d: date, market: str) -> bool:
    """d가 market 거래일이면 True. market ∈ {'KR','US'} 외엔 ValueError."""

def prev_trading_day(d: date, market: str) -> date:
    """d 직전(미포함)의 가장 가까운 거래일. market ∈ {'KR','US'}."""

def expected_trade_date(market: str, now: datetime) -> date:
    """collect 기준일. KR=now가 거래일이면 그 날(아니면 직전), US=직전 거래일(EOD 지연)."""
```

| 함수 | 파라미터 | 반환형 | 예외 |
|------|----------|--------|------|
| `is_trading_day` | `d: date`, `market: str` | `bool` | `market` 미지원 시 `ValueError` |
| `prev_trading_day` | `d: date`, `market: str` | `date` | `market` 미지원 시 `ValueError`; lookback 윈도우 내 거래일 부재 시 `ValueError`(R2) |
| `expected_trade_date` | `market: str`, `now: datetime` | `date` | `market` 미지원 시 `ValueError` |

> 🚨 **드리프트 경고 — 본문에 임의 가정 주입 금지, 미해결 질문으로 이관**:
> - `is_trading_day`/`prev_trading_day`: §2.3은 `(d, market)` 순서이나 **04-backend §6.1 + 실제 모든 호출부**(04-backend L539 `calendar.is_trading_day(market, today)`)는 `(market, d)` 순서다 → **Q1**.
> - `expected_trade_date`: §2.3은 `(market, now: datetime)`, 04-backend §6.1·호출부(L545·L724 `calendar.expected_trade_date(market, today)`)는 `(market, today: date)`다. 2번째 인자 **타입(datetime vs date)** 도 불일치 → **Q2**.
> - 위 충돌을 본 가이드는 §2.3 채택으로 봉합했으나, **그대로 구현하면 BAL-11/collect 호출부가 깨진다**. 구현 착수 전 Q1·Q2를 반드시 해소해 §2.3 또는 §6.1 중 하나로 표를 갱신(§2 머리말의 "충돌 시 §15/05 우선, 그 결과를 본 표에 반영" 절차)할 것.

---

## 5. 엣지 & 리스크

| ID | 케이스 | 대응 |
|----|--------|------|
| R1 | **빈 DF / 빈 valid_days 인덱스** (mcal가 0행 반환) | `is_trading_day`는 `len>0`로 안전. `prev_trading_day`는 빈 결과 시 lookback 확대 또는 `ValueError`로 명시 실패(조용히 잘못된 날짜 반환 금지) |
| R2 | **lookback 윈도우 내 거래일 부재** (장기 연휴 + 너무 좁은 윈도우) | lookback 충분히(≥14일) 확보. 그래도 비면 `ValueError`. mcal 데이터가 미래/과거 범위를 벗어나는 극단 입력 방어 |
| R3 | **휴장일 판정 정확성** (US Good Friday·KR 임시공휴일 등 데이터 소스 의존) | mcal 버전에 정의된 휴장만 반영됨 → 신규 임시공휴일은 라이브러리 갱신 전까지 미반영 가능. **W1 PoC 범위에선 mcal 기본값 신뢰**, 임시공휴일 보정은 Out of scope |
| R4 | **타임존 경계** (mcal valid_days는 tz-aware index) | 입력 `date`/`datetime`을 naive로 다루고, 비교는 **날짜(date) 단위**로 정규화. `expected_trade_date(now: datetime)`의 시각(HH:MM)은 **무시**하고 date만 사용(KST 08:00 cron 전제, 시각 의존 로직 넣지 말 것) |
| R5 | **`pandas_market_calendars` venv 미설치** (현재 환경) | 구현/테스트 전 `pip install -r requirements.txt`. import 실패 시 단계 1부터 막힘 |
| R6 | **NULL percentile / 조정가 stale / 백필** | **본 모듈 범위 밖.** percentile은 BAL-11 fundamentals(per_pctile_5y), 조정가 stale·백필은 BAL-11 ohlcv/collect 책임. calendar는 날짜만 산출하므로 이들 NULL/stale을 생성하지도 소비하지도 않음 → 대응 불필요(혼입 금지) |

> 본 가이드의 "빈 DF/백필/휴장/NULL percentile/조정가 stale"은 W1 슬라이스 전체의 리스크 카탈로그에서 가져온 것으로, **calendar 모듈이 실제 책임지는 것은 R1~R4(빈 결과·휴장)** 뿐임을 명확히 한다. 나머지(R6)는 소비자 이슈 책임으로 경계 표시.

---

## 6. 테스트 계획

파일: **`tests/test_calendar.py`** (신규). 전부 **순수계산 단위 테스트**(외부 네트워크 없음 — mcal는 로컬 휴장 데이터셋이므로 모킹 불필요, 그러나 mcal import 실패 시를 위해 마커 `@pytest.mark.unit`). 고정 날짜(하드코딩된 과거 거래일/휴장일)로 결정론적 단언.

| 테스트명 | 검증 |
|----------|------|
| `test_is_trading_day_weekday_true` | KR/US 평일 정상 거래일 → True |
| `test_is_trading_day_weekend_false` | 토/일 → False (KR·US 각각) |
| `test_is_trading_day_known_holiday_false` | KR 신정(2025-01-01)·US 7/4 등 알려진 휴장 → False |
| `test_is_trading_day_invalid_market_raises` | `market='JP'` 등 → `ValueError` |
| `test_prev_trading_day_skips_weekend` | 월요일 입력 → 직전 금요일 |
| `test_prev_trading_day_skips_holiday_block` | 연휴 다음 영업일 입력 → 연휴 직전 거래일(다중일 스킵) |
| `test_prev_trading_day_is_strictly_before` | 거래일 입력 시 결과 < 입력(strictly previous, Q3 확정 후) |
| `test_expected_trade_date_kr_tradingday_returns_same` | KR 평일 → 같은 날 |
| `test_expected_trade_date_kr_holiday_returns_prev` | KR 휴장/주말 → 직전 거래일 |
| `test_expected_trade_date_us_returns_prev_even_on_tradingday` | **US 평일 → 직전 거래일(같은 날 아님)** — 핵심 회귀 |
| `test_expected_trade_date_us_monday_returns_friday` | US 월요일 → 직전 금요일 |
| `test_expected_trade_date_005930_kr_smoke` | Wave-1 게이트: 005930(KR) 기대 거래일이 주말/휴장 정확 반영 |

> 어댑터(BAL-11) 같은 외부 네트워크 의존이 아니므로 모킹/계약 테스트 불필요. mcal는 패키징된 휴장 캘린더라 결정론적. **테스트 날짜는 mcal에 확실히 정의된 과거 연도(예: 2025)** 를 사용해 라이브러리 갱신에 흔들리지 않게 한다.

실행: `pytest -q tests/test_calendar.py` 및 `python3 -m py_compile app/calendar.py`.

---

## 7. DoD (체크리스트)

로드맵 08 §Week1 + `BAL-1-m1a-orchestration.md` §3·§5에서 해당 항목 인용:

- [ ] **(§3 W-1 게이트 인용)** "calendar: 005930 expected_trade_date 정확" — KR 005930 기준 기대 거래일이 주말·휴장을 정확 반영
- [ ] `is_trading_day`/`prev_trading_day`/`expected_trade_date` 3종 구현, §2.3 시그니처 준수(Q1·Q2 해소 후 표 확정)
- [ ] **US=직전거래일 / KR=당일(거래일시) 분기** 단위 테스트 green (`test_expected_trade_date_us_returns_prev_even_on_tradingday` 포함)
- [ ] 미지원 market → `ValueError`, 빈 결과 → `ValueError`(조용한 실패 없음)
- [ ] **(§5 인용)** `pytest -q` green
- [ ] **(§5 인용)** 편집 파일 `py_compile` 통과 (`python3 -m py_compile app/calendar.py`)
- [ ] `tests/test_calendar.py` 신규 추가, 위 12 케이스 통과
- [ ] PEP8 + 전 함수 타입주석 + (가능 시) frozen/불변 스타일 준수, `print()` 미사용

> 주: §5의 나머지 항목(KrSource ohlcv/fundamentals, db.upsert_*, validate_response, test_tickers)은 BAL-11/BAL-12 DoD이며 본 이슈 게이트 아님.

---

## 8. Out of scope (W1 아님)

- **US/FX/regime 어댑터** (W2) — calendar는 날짜만 산출, 데이터 fetch 없음
- **collect.py 배치/백필** (W2) — `is_trading_day` 기반 `OK_HOLIDAY` skip 로직은 collect 책임(04-backend §8.2). calendar는 판정 함수만 제공
- **metrics 계산** (W3) — per_pctile_5y, sma200, 52주, change_pct 등
- **신선도 배지** `build_freshness_badge`/`FreshnessBadge` (04-backend §6.3) — **calendar.expected_trade_date를 소비**하지만 본 모듈 아님(W3 렌더 영역)
- **models.py LLM/Card DTO** (W3), **프론트** (W5), **손익/수익률** (G8)
- 임시공휴일 수동 보정·캘린더 캐싱/성능 최적화 — PoC 과설계 금지(mcal 기본값 신뢰)
