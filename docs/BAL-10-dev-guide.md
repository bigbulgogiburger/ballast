---
issue: BAL-10
title: calendar.py XKRX/XNYS 거래일 로직
type: single
status: closed
week: W1
parent: null
persona: Python Expert
created: 2026-06-02
closed: 2026-06-04
---

# BAL-10 개발 가이드 — `app/calendar.py` (XKRX/XNYS 거래일 로직)

> 정본 순위: `TECH-DESIGN.md §15` > `docs/04-backend.md §6.1` > `docs/05-database.md`. seam 정본 = `docs/BAL-1-m1a-orchestration.md §2.3 (v2)`.
> 아래 **확정 시그니처는 canonical 검증을 마친 정본**이다. 그대로 사용한다 — 인자순서/타입 변형 금지.

## 1. 목표 & 배경 (W1 슬라이스 내 역할)

`app/calendar.py`는 "오늘이 거래일인가 / 직전 거래일은 언제인가 / collect 기준일은 며칠인가"를 판정하는 순수 로직 모듈이다. `pandas_market_calendars`(이하 `mcal`)의 공식 거래소 캘린더(KR=`XKRX`, US=`XNYS`)를 단일 진실원으로 삼는다.

W1(BAL-1/M1a) 수직 슬라이스에서의 위치:

- **의존: 없음** — `db.py`(BAL-8), `tickers.py`(BAL-9)와 함께 **W-1의 3개 격리 foundation 중 하나**다. 파일 비중복, 충돌 0이므로 3-way 진짜 병렬로 구현된다 (orchestration §1·§3).
- **소비자: W-2의 `sources/kr.py`(BAL-11)** 가 import 한다. seam 계약(orchestration §2.5)상 KR 어댑터 내부에서 `calendar.expected_trade_date('KR', today)`를 호출해 "어떤 거래일 기준으로 데이터를 fetch할지"를 결정한다.
- **하류(W2+, 본 이슈 범위 밖)**: `collect.py`가 휴장일이면 `status='OK_HOLIDAY'`로 정상 skip(04 §6.2, TECH-DESIGN §9 ⑦), `build_freshness_badge`가 "기대 거래일 vs 실제 수집일" 대조에 사용(04 §6.3). **이 소비자들은 W1에서 구현하지 않는다** — 호환 시그니처만 보장하면 된다.

근거: TECH-DESIGN §9 ③("조회는 최신 거래일 기준 … KR/US 직전 거래일 계산, 기대일 vs 수집일 대조") + ⑦("휴장일이면 collect 정상 skip"). `expected_trade_date`의 KR=오늘 / US=직전거래일 비대칭은 EOD(전일 마감분) 수집 타이밍 때문이다 — 08:00 KST 수집 시점에 한국 시장은 당일분이 곧 생기지만, 미국은 전일 마감분만 확정돼 있다(04 §6.1 주석, TECH-DESIGN §9 ①④).

## 2. 영향 파일

| 파일 | 변경 | 비고 |
|------|------|------|
| `app/calendar.py` | **구현** (현재 W0 스텁: docstring 1줄) | 본 이슈 산출물 |
| `tests/test_calendar.py` | **신규 생성** | `@pytest.mark.unit`, mcal 모킹 |
| `requirements.txt` | 변경 없음 | `pandas-market-calendars` 이미 설치 확인됨 |

> 다른 W-1 형제 파일(`db.py`/`tickers.py`)은 **건드리지 않는다**. seam 계약 위반 방지.

## 3. 구현 단계 (자체 분해 단위 + 검증 포인트)

```
1. 모듈 헤더 + mcal 캘린더 인스턴스 모듈 전역 생성
   → verify: python3 -m py_compile app/calendar.py 통과
2. _cal(market) 내부 디스패처 (KR→_KR, US→_XNYS)
   → verify: _cal('KR') is _KR, _cal('US') is _US
3. is_trading_day(market, d) 구현
   → verify: 평일 거래일 True / 토·일 False / 한국 신정(2024-01-01) False
4. prev_trading_day(market, d) 구현
   → verify: 월요일 d → 직전 금요일 / 화요일(전날 휴장 아님) → 전날
5. expected_trade_date(market, today) 구현
   → verify: KR=거래일이면 today 그대로 / US=항상 prev_trading_day(today 포함 안 함)
6. tests/test_calendar.py 작성 (mcal 모킹) → verify: pytest -q green
```

각 단계는 독립 함수 1개 단위라 순차로 누적 검증 가능하다. 검증은 §6 테스트로 자동화한다.

## 4. 인터페이스 (확정 시그니처 구체화)

확정 시그니처를 **그대로** 사용한다 (canonical: 04 §6.1, orchestration §2.3 v2):

```python
"""시장 거래일·휴장일 캘린더 헬퍼.

pandas_market_calendars의 공식 거래소 캘린더를 단일 진실원으로 사용한다.
mcal 기본 휴장표를 신뢰한다(임시공휴일 보정은 PoC 범위 밖).
"""

from datetime import date, timedelta
from typing import Literal

import pandas as pd
import pandas_market_calendars as mcal

_KR = mcal.get_calendar("XKRX")   # 한국거래소
_US = mcal.get_calendar("XNYS")   # NYSE


def _cal(market: Literal["KR", "US"]) -> mcal.MarketCalendar:
    """시장 코드를 mcal 캘린더 인스턴스로 매핑."""
    return _KR if market == "KR" else _US


def is_trading_day(market: Literal["KR", "US"], d: date) -> bool:
    """d가 해당 시장의 거래일이면 True, 주말·휴장일이면 False."""
    sessions = _cal(market).valid_days(start_date=d, end_date=d)
    return len(sessions) > 0


def prev_trading_day(market: Literal["KR", "US"], d: date) -> date:
    """d **직전**의 거래일을 반환(d 자신은 포함하지 않음)."""
    start = d - timedelta(days=14)               # 연휴 여유 윈도우
    sessions = _cal(market).valid_days(start_date=start, end_date=d - timedelta(days=1))
    return sessions[-1].date()


def expected_trade_date(market: Literal["KR", "US"], today: date) -> date:
    """collect 기준 거래일.

    KR = 오늘(거래일이면 그대로, 휴장일이면 직전 거래일).
    US = 직전 거래일(전일 마감분 수집, EOD 지연 흡수).
    """
    if market == "KR":
        return today if is_trading_day("KR", today) else prev_trading_day("KR", today)
    return prev_trading_day("US", today)
```

### 파라미터 / 반환형 / 예외

| 함수 | 파라미터 | 반환형 | 예외 |
|------|----------|--------|------|
| `is_trading_day` | `market: Literal["KR","US"]`, `d: date` | `bool` | 없음(빈 세션=False) |
| `prev_trading_day` | `market: Literal["KR","US"]`, `d: date` | `date` | 윈도우 내 거래일 0개면 `IndexError`(아래 §5 참조) |
| `expected_trade_date` | `market: Literal["KR","US"]`, `today: date` | `date` | `prev_trading_day` 위임분만 |

**계약 고정 사항** (변형 금지):
- 인자순서는 모두 **`(market, 날짜)`** — 첫 인자가 market, 둘째가 `date`.
- 둘째 인자는 **`date`이지 `datetime`이 아니다**. 시간/타임존을 받지 않는다. (호출부 `kr.py`도 `date`를 넘긴다.)
- `prev_trading_day`는 **d 자신을 포함하지 않는다**(strict prev). `expected_trade_date('KR', …)`만 today 포함 가능.
- mcal `valid_days()`는 tz-aware `DatetimeIndex`(UTC)를 돌려주므로, 반환 직전 `.date()`로 **순수 `date`로 좁힌다** — tz 오염 방지.

## 5. 엣지 & 리스크

- **`valid_days`의 경계 반열림**: `start_date`/`end_date`는 양끝 포함(inclusive)이다. `prev_trading_day`에서 d 자신 제외를 위해 `end_date=d - 1day`로 명시했다. d가 거래일이어도 결과에 포함되지 않는다(strict prev 계약 충족).
- **연휴 윈도우 길이**: `prev_trading_day`의 lookback을 14일로 잡았다. 한국 설/추석 연휴(최대 ~5거래일 + 주말)와 미국 연말 휴장을 모두 포괄한다. 정상 입력에서 14일 내 거래일이 0개가 되는 일은 없다.
- **타임존**: `valid_days`는 UTC tz-aware index를 반환. `.date()`로 좁히면 KST/EST 변환 없이 "거래소 달력상의 날짜"가 그대로 나온다. PoC는 거래일 **날짜**만 필요하므로 충분하다. `expected_trade_date`에 넘기는 `today`도 호출부(`collect.py`)가 KST `date.today()`로 산출한다는 전제(W2 책임).
- **임시공휴일/대체휴일**: mcal `XKRX`/`XNYS` 기본 휴장표를 신뢰한다. 정부 지정 임시공휴일(예: 선거일)이 mcal에 없으면 거래일로 오판할 수 있으나, **보정은 PoC 범위 밖**(orchestration §2.3, 04 §6.1 주석). known limitation으로 남긴다.
- **`mcal.get_calendar` 임포트 시 UserWarning**: `XKRX` 로드 시 `break_start/break_end discontinued` 경고가 뜬다(확인됨). 기능 영향 없음. 테스트에서 `-W ignore` 불필요 — 모킹으로 우회한다.
- **모듈 전역 캘린더 인스턴스**: `_KR`/`_US`를 import 시점에 1회 생성한다. mcal 객체 생성 비용을 호출마다 치르지 않기 위함이며, 04 §6.1 정본 코드 형태와 동일하다.

## 6. 테스트 계획 (pytest, 어댑터=모킹)

`tests/test_calendar.py` 신규 작성. 기존 컨벤션(`@pytest.mark.unit`, `tests/test_smoke.py` 스타일)을 따른다.

**모킹 전략**: 외부 네트워크는 없지만 mcal은 외부 휴장표(데이터)에 의존하므로 결정성 확보를 위해 **`_cal`이 돌려주는 캘린더의 `valid_days`를 모킹**한다. 모킹 대상은 `app.calendar._KR` / `_US`의 `valid_days` 메서드(또는 `monkeypatch`로 `_cal` 자체를 페이크 캘린더로 치환).

```python
import datetime as dt
import pandas as pd
import pytest

import app.calendar as cal


def _fake_valid_days(trading_dates: set[dt.date]):
    def _vd(start_date, end_date):
        days = pd.date_range(start=start_date, end=end_date, freq="D")
        keep = [ts for ts in days if ts.date() in trading_dates]
        return pd.DatetimeIndex(keep, tz="UTC")
    return _vd


@pytest.mark.unit
def test_is_trading_day_weekday(monkeypatch):
    monkeypatch.setattr(cal._KR, "valid_days",
                        _fake_valid_days({dt.date(2024, 1, 2)}))
    assert cal.is_trading_day("KR", dt.date(2024, 1, 2)) is True


@pytest.mark.unit
def test_is_trading_day_weekend(monkeypatch):
    monkeypatch.setattr(cal._KR, "valid_days", _fake_valid_days(set()))
    assert cal.is_trading_day("KR", dt.date(2024, 1, 6)) is False  # 토


@pytest.mark.unit
def test_prev_trading_day_skips_weekend(monkeypatch):
    # 직전 거래일 = 2024-01-05(금), d=2024-01-08(월)
    monkeypatch.setattr(cal._KR, "valid_days",
                        _fake_valid_days({dt.date(2024, 1, 5)}))
    assert cal.prev_trading_day("KR", dt.date(2024, 1, 8)) == dt.date(2024, 1, 5)


@pytest.mark.unit
def test_expected_trade_date_kr_today_when_trading(monkeypatch):
    monkeypatch.setattr(cal._KR, "valid_days",
                        _fake_valid_days({dt.date(2024, 1, 2)}))
    assert cal.expected_trade_date("KR", dt.date(2024, 1, 2)) == dt.date(2024, 1, 2)


@pytest.mark.unit
def test_expected_trade_date_kr_holiday_falls_back(monkeypatch):
    # 신정 2024-01-01 휴장 → 직전 거래일 2023-12-29
    monkeypatch.setattr(cal._KR, "valid_days",
                        _fake_valid_days({dt.date(2023, 12, 29)}))
    assert cal.expected_trade_date("KR", dt.date(2024, 1, 1)) == dt.date(2023, 12, 29)


@pytest.mark.unit
def test_expected_trade_date_us_always_prev(monkeypatch):
    # US는 today가 거래일이어도 직전 거래일을 반환
    monkeypatch.setattr(cal._US, "valid_days",
                        _fake_valid_days({dt.date(2024, 1, 4)}))
    assert cal.expected_trade_date("US", dt.date(2024, 1, 5)) == dt.date(2024, 1, 4)
```

**필수 케이스 매트릭스**:
1. `is_trading_day` 평일 거래일 → True
2. `is_trading_day` 주말 → False
3. `is_trading_day` 공휴일(신정) → False
4. `prev_trading_day` 월요일 → 직전 금요일(주말 건너뜀)
5. `prev_trading_day` 화요일(전날 거래일) → 전날
6. `expected_trade_date('KR', 거래일)` → today 그대로
7. `expected_trade_date('KR', 휴장일)` → 직전 거래일
8. `expected_trade_date('US', 거래일)` → today 아님, 직전 거래일 (KR/US 비대칭 보증)

> 실 mcal을 쓰는 통합 테스트 1개(`005930` KR 평일 거래일 판정)는 선택. 결정성·격리 우선이면 전부 모킹으로 충분하다.

## 7. DoD (Definition of Done)

로드맵 `08-dev-roadmap.md §Week1`(M1a: `calendar` 포함 KR 데이터 레이어) + **orchestration §3 W-1 게이트** + **§5 검증 게이트** 인용:

orchestration §3 W-1 calendar 게이트:
> "calendar: 005930 expected_trade_date 정확"

orchestration §5(W1 통합 DoD) 중 본 이슈 관련:
> "`pytest -q` green, 편집 파일 `py_compile` 통과"

**BAL-10 완료 조건 체크리스트**:
- [ ] `app/calendar.py`에 확정 시그니처 3종 구현(인자순서 `(market, date)` 정합).
- [ ] `python3 -m py_compile app/calendar.py` 통과 (degraded-session compile-check 수동 대체, orchestration §4).
- [ ] `expected_trade_date('KR', d)` = 거래일이면 today / 휴장일이면 직전 거래일.
- [ ] `expected_trade_date('US', d)` = 항상 직전 거래일(today 미포함).
- [ ] `tests/test_calendar.py` §6 매트릭스 8케이스 전부 green (`pytest -q`).
- [ ] 반환형이 순수 `date`(tz-naive). `datetime`/tz-aware 누출 없음.
- [ ] seam 호환: `from app.calendar import expected_trade_date` import 가능(kr.py가 소비).

## 8. Out of Scope (W1 아님 — 끌려가지 말 것)

- **`collect.py`의 `OK_HOLIDAY` skip 로직**(04 §6.2) — W2. calendar는 판정만 제공.
- **`build_freshness_badge`**(04 §6.3) — 신선도 배지 산출은 렌더 소비자, W3+.
- **임시공휴일/대체휴일 보정** — mcal 기본 휴장표 신뢰, PoC 범위 밖.
- **타임존/마감시각 정밀 계산** — `date` 단위만. 시·분 EOD 타이밍은 스케줄러(collect, W2) 책임.
- **US/FX 어댑터, regime US(CAPE)** — orchestration §6 명시 Out of scope.
- **다종목·KOSDAQ 등 시장 확장** — calendar는 KR/US 2개 거래소만. 서브마켓 구분 불필요(거래일은 거래소 단위).

---
> 📌 본 가이드의 "미해결 질문"은 **전건 해소됨** → `docs/BAL-1-m1a-decisions.md` (유보 0건). 시그니처 정본 = orchestration §2 v2.
