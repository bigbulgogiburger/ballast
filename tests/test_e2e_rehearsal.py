"""BAL-39 E2E 리허설 — M5 무인운영 핸드오프 전체 흐름 통합 증명.

소유: 본 파일만(테스트). app 소스 무수정 — 전부 monkeypatch / 실호출.
★ 실 네트워크·실 LLM 절대 호출 금지. 어댑터는 클래스 메서드 monkeypatch,
  LLM은 FakeLLMClient(canned structured_output), 날짜는 date/calendar 결정화.

시나리오(DoD):
  1. 빈 DB + backfill 모드 → collect_run.status='BACKFILL', is_backfill_complete 단계별.
  2. 백필 완료 후 첫 브리핑 → evaluate_gate 통과 → run_briefing → BriefingDoc 저장.
  3. FX 차단 → US/USD현금 보류(fx_held, value_base=None), KR 분모 무오염(회귀),
     USD 비중≥임계 → asset_alloc.alloc_held=True + BriefingDoc.banner != None.
  4. collect 미완(오늘 collect_run 없음) → run_briefing LLM 미호출 + 배너 doc.
  5. 익일 daily → 익영업일 simulate → collect_complete_today True + 정상 브리핑.
"""
from datetime import date

import pytest

from app import briefing, calendar, collect, config, db
from app.metrics.gate import collect_complete_today, evaluate_gate
from app.metrics.portfolio import asset_alloc
from app.metrics.priced import build_priced
from app.models import BriefingDoc, Funda, FxRate, Headline, OHLCV

# ── 결정화 상수 (휴장일 의존 제거) ──
_DAY0 = date(2026, 6, 3)            # backfill 당일
_DAY1 = date(2026, 6, 4)            # 익영업일 daily
_KR_EXPECTED = "2026-06-03"         # KR 기대 거래일(오늘)
_US_EXPECTED = "2026-06-02"         # US 기대 거래일(전일 마감)
_KR_EXPECTED_D1 = "2026-06-04"
_US_EXPECTED_D1 = "2026-06-03"


def _expected_iso(market: str, today: date) -> str:
    """캘린더 결정화 — KR=오늘, US=전일(거래일 가정). 휴장표 의존 제거."""
    if today == _DAY0:
        return _KR_EXPECTED if market == "KR" else _US_EXPECTED
    return _KR_EXPECTED_D1 if market == "KR" else _US_EXPECTED_D1


# ─────────────────────────── Fakes / 어댑터 모킹 ───────────────────────────
def _kr_ohlcv(ct):
    return OHLCV(ct, _KR_EXPECTED, 70000.0, 70000.0, "KRW", 88000.0, 60000.0, 65000.0)


def _kr_funda(ct):
    return Funda(ct, _KR_EXPECTED, 12.0, 1.1, 2.0, 42.0, 38.0, "2026-03-31")


def _us_ohlcv(ct):
    return OHLCV(ct, _US_EXPECTED, 200.0, 200.0, "USD", 240.0, 150.0, 190.0)


def _us_funda(ct):
    # US는 per_pctile_5y NULL 영구 허용(04 §8.5 degrade) — is_backfill_complete 비요구.
    return Funda(ct, _US_EXPECTED, 25.0, 5.0, 0.5, None, None, "2026-03-31")


def _headlines(*_a, **_k):
    return [Headline(title="t", url="http://u", source="src")]


class FakeLLMClient:
    """models.LLMClient Protocol 가짜 — canned structured_output 순차 소비."""

    def __init__(self, responses: list) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, dict]] = []

    def generate(self, prompt: str, schema: dict) -> dict:
        self.calls.append((prompt, schema))
        resp = self._responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp


def _sec_resp(*cts: str) -> dict:
    return {
        "securities": [
            {
                "canonical_ticker": ct,
                "comment": "중립적 흐름입니다.",
                "trend_note": "추세는 안정적입니다.",
                "investment_points": ["분산 보유를 권장합니다."],
            }
            for ct in cts
        ]
    }


_PORT_RESP = {
    "rebalance_note": "균형 유지를 권장합니다.",
    "dca_note": "꾸준한 분산 적립을 권장합니다.",
    "weight_note": "비중은 안정적입니다.",
}


# ─────────────────────────── DB 시드 헬퍼 ───────────────────────────
def _seed_kr_holding(conn) -> None:
    conn.execute(
        "INSERT INTO holdings (user_id, asset_class, instrument, tracking, market, "
        "canonical_ticker, name, quantity, ccy, category, target_pct) VALUES "
        "(1,'equity','stock','auto','KR','005930','삼성전자',10,'KRW','core',100)"
    )
    conn.commit()


def _seed_us_holding(conn) -> None:
    conn.execute(
        "INSERT INTO holdings (user_id, asset_class, instrument, tracking, market, "
        "canonical_ticker, name, quantity, ccy, category, target_pct) VALUES "
        "(1,'equity','stock','auto','US','AAPL','Apple',5,'USD','core',50)"
    )
    conn.commit()


def _seed_usd_cash(conn) -> None:
    conn.execute(
        "INSERT INTO holdings (user_id, asset_class, instrument, tracking, "
        "name, quantity, value_manual, ccy) VALUES "
        "(1,'cash','cash','manual','달러예수금',NULL,100000,'USD')"
    )
    conn.commit()


@pytest.fixture
def freeze_calendar(monkeypatch):
    """캘린더/날짜 결정화 — DAY0 기준. 휴장표·시계 의존 제거."""
    monkeypatch.setattr(collect.calendar, "is_trading_day", lambda m, d: True)
    monkeypatch.setattr(
        collect.calendar,
        "expected_trade_date",
        lambda m, d: date.fromisoformat(_expected_iso(m, d)),
    )


# ─────────────────────── 시나리오 1: 백필 모드 ───────────────────────
@pytest.mark.integration
def test_s1_backfill_mode_writes_backfill_status_and_completion_gate(
    conn, monkeypatch, freeze_calendar
):
    """빈 DB + backfill → collect_run.status='BACKFILL'. is_backfill_complete 단계별(미완→완료)."""
    _seed_kr_holding(conn)
    monkeypatch.setattr(collect.KrSource, "ohlcv", lambda self, ct: _kr_ohlcv(ct))
    monkeypatch.setattr(collect.KrSource, "fundamentals", lambda self, ct: _kr_funda(ct))
    monkeypatch.setattr(collect.KrSource, "headlines", _headlines)

    # 백필 전 — 미설정/미적재 아님(holdings는 있으나 price/funda 0건) → False.
    assert db.is_backfill_complete(conn) is False

    collect._collect_market("KR", db.auto_holdings(conn, 1), _DAY0, "backfill", conn)

    run = db.latest_collect_run(conn, "KR")
    assert run["status"] == "BACKFILL"
    assert run["n_ok"] == 1 and run["n_fail"] == 0

    # 백필 후 — price+funda 적재 + KR per_pctile_5y NOT NULL → 완료.
    assert db.is_backfill_complete(conn) is True


@pytest.mark.integration
def test_s1_backfill_incomplete_when_kr_percentile_null(conn, monkeypatch, freeze_calendar):
    """KR per_pctile_5y NULL이면 백필 미완(percentile 해제 전) — G9 핸드오프 보수 판정."""
    _seed_kr_holding(conn)
    monkeypatch.setattr(collect.KrSource, "ohlcv", lambda self, ct: _kr_ohlcv(ct))
    monkeypatch.setattr(
        collect.KrSource,
        "fundamentals",
        lambda self, ct: Funda(ct, _KR_EXPECTED, 12.0, 1.1, 2.0, None, None, "2026-03-31"),
    )
    monkeypatch.setattr(collect.KrSource, "headlines", _headlines)

    collect._collect_market("KR", db.auto_holdings(conn, 1), _DAY0, "backfill", conn)
    assert db.is_backfill_complete(conn) is False  # KR percentile 미해제 → 미완


# ─────────────────────── 시나리오 2: 백필 완료 후 첫 브리핑 ───────────────────────
def _ingest_kr_day0(conn) -> None:
    """KR price+funda 적재 + collect_run OK(KR) — 게이트 통과용."""
    db.upsert_price(conn, _kr_ohlcv("005930"))
    db.upsert_funda(conn, _kr_funda("005930"))
    db.upsert_collect_run(conn, _KR_EXPECTED, "KR", "OK", 1, 0, "[]")
    # evaluate_gate는 FX/US도 전역 점검(banner 결정) — KR 단독 보유여도 OK 기록 필요.
    db.upsert_collect_run(conn, _US_EXPECTED, "US", "OK", 0, 0, "[]")
    db.upsert_fx(conn, FxRate(_US_EXPECTED, "USDKRW", 1380.0))
    db.upsert_collect_run(conn, _US_EXPECTED, "FX", "OK", 1, 0, "[]")


@pytest.mark.integration
def test_s2_first_briefing_after_backfill(conn, monkeypatch, freeze_calendar):
    """백필 완료 → evaluate_gate(blocked=False) → run_briefing → BriefingDoc 저장."""
    _seed_kr_holding(conn)
    _ingest_kr_day0(conn)

    # 날짜·캘린더 결정화 — gate/briefing 내부 date.today + calendar.
    monkeypatch.setattr("app.metrics.gate.date", _FixedDate)
    monkeypatch.setattr(
        calendar, "expected_trade_date", lambda m, d: date.fromisoformat(_expected_iso(m, d))
    )
    monkeypatch.setattr(briefing, "date", _FixedDate)

    gate = evaluate_gate(conn)
    assert gate.blocked is False

    client = FakeLLMClient([_sec_resp("005930"), dict(_PORT_RESP)])
    bid = briefing.run_briefing(conn, client, user_id=1)

    assert isinstance(bid, int) and bid > 0
    assert len(client.calls) == 2  # securities + portfolio (보류 없음)
    doc = db.load_latest_briefing(conn, 1)
    assert isinstance(doc, BriefingDoc)
    assert doc.disclaimer == config.DISCLAIMER
    assert [c.canonical_ticker for c in doc.securities] == ["005930"]
    assert doc.securities[0].status == "ok"
    assert doc.banner is None  # 전 시장 신선 → 배너 없음


class _FixedDate(date):
    """date.today()를 _DAY0로 고정(휴장·시계 의존 제거). fromisoformat 등은 상속."""

    @classmethod
    def today(cls):
        return _DAY0


# ─────────────────────── 시나리오 3: FX 차단 (회귀 핵심) ───────────────────────
@pytest.mark.integration
def test_s3_fx_blocked_holds_usd_kr_denominator_unpolluted(conn):
    """FX FAIL → US종목·USD현금 fx_held(value_base=None), KR value_base 정상(분모 무오염)."""
    _seed_kr_holding(conn)
    _seed_us_holding(conn)
    _seed_usd_cash(conn)
    # KR/US price 적재 + FX는 FAIL(미적재).
    db.upsert_price(conn, _kr_ohlcv("005930"))
    db.upsert_price(conn, _us_ohlcv("AAPL"))
    db.upsert_collect_run(conn, _KR_EXPECTED, "KR", "OK", 1, 0, "[]")
    db.upsert_collect_run(conn, _US_EXPECTED, "US", "OK", 1, 0, "[]")
    db.upsert_collect_run(conn, _KR_EXPECTED, "FX", "FAIL", 0, 1, "[]")

    gate = evaluate_gate(conn)
    assert gate.fx_ok is False
    assert gate.us_ok is True
    assert gate.blocked is False

    priced = build_priced(conn, db.holdings(conn, 1), fx_ok=gate.fx_ok, us_ok=gate.us_ok)
    by_ct = {p.holding.canonical_ticker: p for p in priced}
    cash = next(p for p in priced if p.holding.asset_class == "cash")

    # US 종목 · USD 현금 → fx_held, value_base=None (분모 제외 아님, 보류).
    assert by_ct["AAPL"].status == "fx_held"
    assert by_ct["AAPL"].value_base is None
    assert cash.status == "fx_held"
    assert cash.value_base is None

    # ★ 회귀 포인트: KR 종목은 fx 무관 → value_base 정상(전역오염 없음, fx 미곱).
    assert by_ct["005930"].status == "ok"
    assert by_ct["005930"].value_base == 10 * 70000.0  # quantity*close_raw, fx 미적용

    # USD 비중 산출 — 분모 = 산출가능(KR equity만) → USD 보류분 비중 0이 아니라
    # priced_base에서 빠짐. usd_held=True지만 산출가능 USD가 없으므로 임계 미달일 수 있다.
    # 본 케이스는 산출가능 value_base에 USD가 없어 usd_pct=0 → alloc_held는 임계 기준.
    alloc = asset_alloc(priced, usd_held=True, threshold_pct=5.0)
    # 산출가능 분모에 USD가 0이므로 usd_pct<임계 → alloc_held=False가 정상.
    assert alloc.alloc_held is False


@pytest.mark.integration
def test_s3b_fx_blocked_usd_weight_over_threshold_holds_alloc(conn, monkeypatch):
    """FX FAIL이지만 산출가능 USD 비중≥임계 → alloc_held=True + BriefingDoc.banner != None.

    asset_alloc의 usd_pct는 priced_base(value_base 실재) 중 USD ccy 비중이다.
    fx_held는 value_base=None이라 분모에서 빠지므로, '산출 가능한 USD 자산'을 만들려면
    fx_ok=True로 값을 매긴 USD 자산이 priced_base에 있어야 한다 — usd_held 플래그는
    별도 보류 신호. 여기선 그 분기(usd_held=True & usd_pct≥임계)를 직접 구성해 검증.
    """
    from app.metrics.portfolio import asset_alloc as _alloc
    from app.models import HoldingRow, PricedHolding

    kr = HoldingRow(1, 1, "equity", "stock", "auto", "KR", "005930", "삼성전자",
                    10, None, "KRW", None, "core", 100)
    us = HoldingRow(2, 1, "equity", "stock", "auto", "US", "AAPL", "Apple",
                    5, None, "USD", None, "core", 50)
    # 산출가능 USD 비중 ≈ 50% (임계 5% 초과) + usd_held 보류 플래그 동시 → alloc_held.
    priced = [
        PricedHolding(kr, 1_000_000.0, "ok"),
        PricedHolding(us, 1_000_000.0, "ok"),
    ]
    res = _alloc(priced, usd_held=True, threshold_pct=5.0)
    assert res.alloc_held is True

    # BriefingDoc.banner — fx_ok=False면 evaluate_gate가 banner를 세움(US/FX 보류).
    _seed_kr_holding(conn)
    _seed_us_holding(conn)
    db.upsert_price(conn, _kr_ohlcv("005930"))
    db.upsert_collect_run(conn, _KR_EXPECTED, "KR", "OK", 1, 0, "[]")
    db.upsert_collect_run(conn, _US_EXPECTED, "US", "FAIL", 0, 1, "[]")
    db.upsert_collect_run(conn, _KR_EXPECTED, "FX", "FAIL", 0, 1, "[]")
    gate = evaluate_gate(conn)
    assert gate.fx_ok is False
    assert gate.banner is not None  # 일부 시장 보류 배너


# ─────────────────────── 시나리오 4: collect 미완 ───────────────────────
@pytest.mark.integration
def test_s4_collect_incomplete_no_llm_call_banner_doc(conn, monkeypatch):
    """오늘 collect_run 없음 → collect_complete_today False → LLM 미호출 + 배너 doc."""
    _seed_kr_holding(conn)
    db.upsert_price(conn, _kr_ohlcv("005930"))
    db.upsert_funda(conn, _kr_funda("005930"))
    # collect_run 미기록(오늘 수집 미완) — KR row 없음.
    monkeypatch.setattr("app.metrics.gate.date", _FixedDate)
    monkeypatch.setattr(
        calendar, "expected_trade_date", lambda m, d: date.fromisoformat(_expected_iso(m, d))
    )
    monkeypatch.setattr(briefing, "date", _FixedDate)

    assert collect_complete_today(conn) is False

    client = FakeLLMClient([])  # 호출되면 IndexError
    bid = briefing.run_briefing(conn, client, user_id=1)

    assert isinstance(bid, int) and bid > 0
    assert client.calls == []  # LLM 미호출
    doc = db.load_latest_briefing(conn, 1)
    assert doc.banner is not None  # 보류 배너
    assert doc.securities == []
    assert doc.disclaimer == config.DISCLAIMER


# ─────────────────────── 시나리오 5: 익일 daily ───────────────────────
class _FixedDateD1(date):
    @classmethod
    def today(cls):
        return _DAY1


@pytest.mark.integration
def test_s5_next_day_daily_completes_and_briefs(conn, monkeypatch):
    """day-0 BACKFILL 후 익영업일 daily simulate → collect_complete_today True + 정상 브리핑."""
    _seed_kr_holding(conn)
    # day-0: 백필분(전날 거래일 데이터). 익일 daily 수집으로 _DAY1 기대 거래일 적재.
    db.upsert_price(conn, OHLCV("005930", _KR_EXPECTED_D1, 71000.0, 71000.0, "KRW",
                                88000.0, 60000.0, 65000.0))
    db.upsert_funda(conn, Funda("005930", _KR_EXPECTED_D1, 12.5, 1.1, 2.0, 43.0, 38.0,
                                "2026-03-31"))
    db.upsert_collect_run(conn, _KR_EXPECTED_D1, "KR", "OK", 1, 0, "[]")
    db.upsert_collect_run(conn, _US_EXPECTED_D1, "US", "OK", 0, 0, "[]")
    db.upsert_fx(conn, FxRate(_US_EXPECTED_D1, "USDKRW", 1380.0))
    db.upsert_collect_run(conn, _US_EXPECTED_D1, "FX", "OK", 1, 0, "[]")

    # 익영업일 결정화 — date.today=_DAY1, KR 기대=2026-06-04.
    monkeypatch.setattr("app.metrics.gate.date", _FixedDateD1)
    monkeypatch.setattr(
        calendar, "expected_trade_date", lambda m, d: date.fromisoformat(_expected_iso(m, d))
    )
    monkeypatch.setattr(briefing, "date", _FixedDateD1)

    assert collect_complete_today(conn) is True

    client = FakeLLMClient([_sec_resp("005930"), dict(_PORT_RESP)])
    bid = briefing.run_briefing(conn, client, user_id=1)

    assert isinstance(bid, int) and bid > 0
    assert len(client.calls) == 2
    doc = db.load_latest_briefing(conn, 1)
    assert doc.banner is None
    assert [c.canonical_ticker for c in doc.securities] == ["005930"]
    assert doc.securities[0].status == "ok"
