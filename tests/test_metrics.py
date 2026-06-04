"""BAL-23 회귀 + 분기 커버 — app/metrics/* (priced·portfolio·security·gate).

회귀 5종(에픽 DoD):
  ① drift 5/25 작은 쪽 (절대 5%p / 상대 25% 분리)
  ② build_priced(fx_ok=False): US=fx_held·KR 정상·USD현금 보류·리스트 비탈락
  ③ auto_targets 평가액 무인자 + 합 100
  ④ valuation per_pctile None → "워밍업 중"
  ⑤ valuation per<0 음수 제외

import은 전체 모듈 경로 사용. date.today()/calendar는 monkeypatch로 고정.
"""
from datetime import date

import pytest

from app.metrics.gate import (
    collect_complete_today,
    evaluate_gate,
)
from app.metrics.portfolio import (
    DriftResult,
    asset_alloc,
    auto_targets,
    core_sat,
    dca,
    drift,
)
from app.metrics.priced import build_priced
from app.metrics.security import (
    change_pct,
    regime,
    trend,
    valuation,
)
from app.models import (
    Funda,
    OHLCV,
    PricedHolding,
    RegimeRow,
)


# ─────────────────────────── 헬퍼 ───────────────────────────


def _priced(holding, value_base, status="ok"):
    return PricedHolding(holding, value_base, status)


def _ohlcv(**kw):
    base = dict(
        canonical_ticker="005930",
        trade_date="2026-06-03",
        close_raw=100.0,
        close_adj=100.0,
        ccy="KRW",
        week52_high=120.0,
        week52_low=80.0,
        sma200=90.0,
    )
    base.update(kw)
    return OHLCV(**base)


def _funda(**kw):
    base = dict(
        canonical_ticker="005930",
        trade_date="2026-06-03",
        per=10.0,
        pbr=1.0,
        div_yield=2.0,
        per_pctile_5y=0.5,
        pbr_pctile_5y=0.5,
        report_date="2026-03-31",
    )
    base.update(kw)
    return Funda(**base)


def _seed_price(conn, ct, close_raw, ccy="KRW", trade_date="2026-06-03"):
    conn.execute(
        "INSERT INTO price_snapshot "
        "(canonical_ticker, trade_date, close_adj, close_raw, ccy) "
        "VALUES (?, ?, ?, ?, ?)",
        (ct, trade_date, close_raw, close_raw, ccy),
    )
    conn.commit()


def _seed_collect_run(conn, market, status, trade_date):
    conn.execute(
        "INSERT INTO collect_run (trade_date, market, status, n_ok, n_fail) "
        "VALUES (?, ?, ?, 0, 0)",
        (trade_date, market, status),
    )
    conn.commit()


# ═══════════════════════ 회귀 ① drift 5/25 작은 쪽 ═══════════════════════


def test_drift_absolute_band_triggers_first(make_holding):
    """절대 5%p가 상대 25%보다 먼저 닿는 케이스.

    core 목표 80% → 상대 임계 = 80*0.25 = 20%p. 절대 5%p가 더 작다.
    현재 core 86%(gap +6) → 5%p 트리거되나 20%p는 아님 → 절대쪽이 먼저.
    """
    # core 두 종목, satellite 한 종목. 분모=core 86 / sat 14 가 되도록 평가액 구성.
    c1 = _priced(make_holding(canonical_ticker="A", category="core"), 43.0)
    c2 = _priced(make_holding(canonical_ticker="B", category="core"), 43.0)
    s1 = _priced(make_holding(canonical_ticker="C", category="satellite"), 14.0)
    targets = {"A": 40.0, "B": 40.0, "C": 20.0}  # core tgt 80, sat 20
    res = drift([c1, c2, s1], targets, band_abs=5.0, band_rel=0.25, micro_floor=1.0)
    # core gap = 86-80 = +6 → |6| >= min(5, 20)=5 → 트리거
    assert res.per_group["core"] == pytest.approx(6.0)
    assert res.flags["core"] is True
    assert res.rebalance_needed is True


def test_drift_relative_band_triggers_first(make_holding):
    """상대 25%가 절대 5%p보다 먼저 닿는 케이스.

    satellite 목표 10% → 상대 임계 = 10*0.25 = 2.5%p < 절대 5%p.
    현재 sat 14%(gap +4) → 2.5%p 트리거되나 5%p는 아님 → 상대쪽이 먼저.
    """
    c1 = _priced(make_holding(canonical_ticker="A", category="core"), 43.0)
    c2 = _priced(make_holding(canonical_ticker="B", category="core"), 43.0)
    s1 = _priced(make_holding(canonical_ticker="C", category="satellite"), 14.0)
    targets = {"A": 45.0, "B": 45.0, "C": 10.0}  # sat tgt 10
    res = drift([c1, c2, s1], targets, band_abs=5.0, band_rel=0.25, micro_floor=1.0)
    # sat gap = 14-10 = +4 → |4| >= min(5, 2.5)=2.5 → 트리거(상대쪽)
    assert res.per_group["satellite"] == pytest.approx(4.0)
    assert res.flags["satellite"] is True


def test_drift_micro_floor_suppresses(make_holding):
    """micro_floor 미만 격차는 거짓신호 억제."""
    c1 = _priced(make_holding(canonical_ticker="A", category="core"), 50.0)
    c2 = _priced(make_holding(canonical_ticker="B", category="core"), 50.0)
    targets = {"A": 50.0, "B": 50.0}  # core tgt 100, 현재 100 → gap 0
    res = drift([c1, c2], targets, band_abs=5.0, band_rel=0.25, micro_floor=1.0)
    assert res.flags["core"] is False
    assert res.rebalance_needed is False


def test_drift_suppressed_when_few_equities(make_holding):
    """equity 산출가능 < 2 → 전 플래그 억제."""
    c1 = _priced(make_holding(canonical_ticker="A", category="core"), 100.0)
    targets = {"A": 50.0}
    res = drift([c1], targets, band_abs=5.0, band_rel=0.25, micro_floor=1.0)
    assert res.flags["core"] is False


def test_drift_empty_total(make_holding):
    """value_base 합 0 → cur 빈 dict, tgt만으로 gap=-t."""
    held = _priced(make_holding(canonical_ticker="A", category="core"), None, "fx_held")
    res = drift([held], {"A": 50.0}, band_abs=5.0, band_rel=0.25, micro_floor=1.0)
    # priced_base 비어있음 → cur {} ; tgt에 ticker가 priced_base에 없어 매핑 안됨 → groups 빈
    assert res.flags == {}


# ═════════════ 회귀 ② build_priced(fx_ok=False) 전역 오염 방지 ═════════════


def test_build_priced_fx_fail_us_held_kr_normal(conn, make_holding):
    """fx FAIL: US=fx_held(None)·KR 정상 정규화·USD현금 보류·리스트 비탈락."""
    _seed_price(conn, "005930", 70000.0, "KRW")
    _seed_price(conn, "AAPL", 200.0, "USD")

    kr = make_holding(
        id=1, canonical_ticker="005930", market="KR", ccy="KRW", quantity=10.0
    )
    us = make_holding(
        id=2, canonical_ticker="AAPL", market="US", ccy="USD", quantity=5.0
    )
    usd_cash = make_holding(
        id=3,
        asset_class="cash",
        instrument="cash",
        tracking="manual",
        market=None,
        canonical_ticker=None,
        quantity=None,
        value_manual=1000.0,
        ccy="USD",
        category=None,
    )

    out = build_priced(conn, [kr, us, usd_cash], fx_ok=False, us_ok=True)

    assert len(out) == 3  # 비탈락 — 보류도 리스트에 남는다
    by_id = {p.holding.id: p for p in out}
    # KR: 전역 미정규화 아님 — 정상 value_base
    assert by_id[1].status == "ok"
    assert by_id[1].value_base == pytest.approx(10.0 * 70000.0)
    # US 종목: fx_held, value_base None
    assert by_id[2].status == "fx_held"
    assert by_id[2].value_base is None
    # USD 현금: fx 의존 → 보류
    assert by_id[3].status == "fx_held"
    assert by_id[3].value_base is None


def test_build_priced_fx_ok_full_normalization(conn, make_holding):
    """fx_ok=True: US 종목·USD현금 fx 곱, KR fx=1.0, KRW현금 그대로."""
    _seed_price(conn, "005930", 70000.0, "KRW")
    _seed_price(conn, "AAPL", 200.0, "USD")
    conn.execute(
        "INSERT INTO fx_snapshot (trade_date, pair, rate) VALUES "
        "('2026-06-03', 'USDKRW', 1300.0)"
    )
    conn.commit()

    kr = make_holding(id=1, canonical_ticker="005930", market="KR", quantity=10.0)
    us = make_holding(
        id=2, canonical_ticker="AAPL", market="US", ccy="USD", quantity=5.0
    )
    usd_cash = make_holding(
        id=3, asset_class="cash", instrument="cash", tracking="manual",
        market=None, canonical_ticker=None, quantity=None,
        value_manual=1000.0, ccy="USD", category=None,
    )
    krw_cash = make_holding(
        id=4, asset_class="cash", instrument="cash", tracking="manual",
        market=None, canonical_ticker=None, quantity=None,
        value_manual=500000.0, ccy="KRW", category=None,
    )

    out = build_priced(conn, [kr, us, usd_cash, krw_cash], fx_ok=True, us_ok=True)
    by_id = {p.holding.id: p for p in out}
    assert by_id[1].value_base == pytest.approx(10.0 * 70000.0)
    assert by_id[2].value_base == pytest.approx(5.0 * 200.0 * 1300.0)
    assert by_id[3].value_base == pytest.approx(1000.0 * 1300.0)
    assert by_id[4].value_base == pytest.approx(500000.0)
    assert all(p.status == "ok" for p in out)


def test_build_priced_fx_row_missing_degrades(conn, make_holding):
    """fx_ok=True인데 fx row 실종 → 게이트 일관 보류로 강등(USD 자산 fx_held)."""
    _seed_price(conn, "AAPL", 200.0, "USD")
    us = make_holding(
        id=2, canonical_ticker="AAPL", market="US", ccy="USD", quantity=5.0
    )
    out = build_priced(conn, [us], fx_ok=True, us_ok=True)
    assert out[0].status == "fx_held"
    assert out[0].value_base is None


def test_build_priced_us_collect_fail(conn, make_holding):
    """us_ok=False → US 종목 data_pending 강제 보류(stale price여도)."""
    _seed_price(conn, "AAPL", 200.0, "USD")
    conn.execute(
        "INSERT INTO fx_snapshot (trade_date, pair, rate) VALUES "
        "('2026-06-03', 'USDKRW', 1300.0)"
    )
    conn.commit()
    us = make_holding(
        id=2, canonical_ticker="AAPL", market="US", ccy="USD", quantity=5.0
    )
    out = build_priced(conn, [us], fx_ok=True, us_ok=False)
    assert out[0].status == "data_pending"
    assert out[0].value_base is None


def test_build_priced_price_missing(conn, make_holding):
    """price row 0건 → data_pending 보류."""
    kr = make_holding(id=1, canonical_ticker="UNKNOWN", market="KR", quantity=10.0)
    out = build_priced(conn, [kr], fx_ok=True, us_ok=True)
    assert out[0].status == "data_pending"
    assert out[0].value_base is None


# ═════════════════════ 회귀 ③ auto_targets ═════════════════════


def test_auto_targets_no_value_arg_sums_100(make_holding):
    """평가액 무인자 — 그룹 균등 + 그룹내 균등, 합 100%."""
    holdings = [
        make_holding(canonical_ticker="A", category="core"),
        make_holding(canonical_ticker="B", category="core"),
        make_holding(canonical_ticker="C", category="satellite"),
    ]
    out = auto_targets(holdings)
    # 그룹 2개(core/sat) → 각 50%. core 2종목 → 25/25, sat 1종목 → 50.
    assert out["A"] == pytest.approx(25.0)
    assert out["B"] == pytest.approx(25.0)
    assert out["C"] == pytest.approx(50.0)
    assert sum(out.values()) == pytest.approx(100.0)


def test_auto_targets_uncategorized_group(make_holding):
    """category None은 자체 그룹으로 분리."""
    holdings = [
        make_holding(canonical_ticker="A", category="core"),
        make_holding(canonical_ticker="B", category=None),
    ]
    out = auto_targets(holdings)
    assert out["A"] == pytest.approx(50.0)
    assert out["B"] == pytest.approx(50.0)


def test_auto_targets_excludes_cash_and_empty(make_holding):
    """equity 없으면 빈 dict (cash/canonical None 제외)."""
    cash = make_holding(
        asset_class="cash", instrument="cash", canonical_ticker=None, category=None
    )
    assert auto_targets([cash]) == {}


# ═══════════════════ 회귀 ④⑤ valuation ═══════════════════


def test_valuation_warmup_when_pctile_none():
    """④ per_pctile_5y None → '워밍업 중', pctile None."""
    res = valuation(_funda(per_pctile_5y=None))
    assert res.label == "워밍업 중"
    assert res.pctile is None


def test_valuation_negative_per_excluded():
    """⑤ per < 0 → pctile 기반 판정 제외, '중립'."""
    res = valuation(_funda(per=-3.0, per_pctile_5y=0.1))
    # pctile 0.1은 저평가 임계지만 음수 PER이라 판정 스킵
    assert res.label == "중립"
    assert res.per == -3.0


def test_valuation_undervalued():
    res = valuation(_funda(per=10.0, per_pctile_5y=0.1))
    assert res.label == "저평가"


def test_valuation_overvalued():
    res = valuation(_funda(per=30.0, per_pctile_5y=0.9))
    assert res.label == "고평가"


def test_valuation_neutral():
    res = valuation(_funda(per=15.0, per_pctile_5y=0.5))
    assert res.label == "중립"


def test_valuation_none_per_with_pctile():
    """per None(적자) + pctile 존재 → 중립(음수와 동일 분기)."""
    res = valuation(_funda(per=None, per_pctile_5y=0.1))
    assert res.label == "중립"


# ═══════════════════ change_pct 분기 ═══════════════════


def test_change_pct_prev_none():
    assert change_pct(_ohlcv(), None) is None


def test_change_pct_prev_zero():
    assert change_pct(_ohlcv(), 0) is None


def test_change_pct_normal():
    res = change_pct(_ohlcv(close_raw=110.0), 100.0)
    assert res == pytest.approx(10.0)


# ═══════════════════ trend 분기 (None-safe) ═══════════════════


def test_trend_normal():
    res = trend(_ohlcv(close_adj=100.0, week52_high=120.0, week52_low=80.0, sma200=90.0))
    assert res.week52_pos == pytest.approx((100 - 80) / (120 - 80))
    assert res.sma200_gap == pytest.approx((100 - 90) / 90)


def test_trend_week52_none():
    res = trend(_ohlcv(week52_high=None, week52_low=None))
    assert res.week52_pos is None


def test_trend_week52_high_equals_low():
    res = trend(_ohlcv(week52_high=100.0, week52_low=100.0))
    assert res.week52_pos is None


def test_trend_sma200_none():
    res = trend(_ohlcv(sma200=None))
    assert res.sma200_gap is None


def test_trend_sma200_zero():
    res = trend(_ohlcv(sma200=0.0))
    assert res.sma200_gap is None


# ═══════════════════ regime 분기 ═══════════════════


def test_regime_none_row():
    assert regime(None) == "레짐 데이터 미확보"


def test_regime_both_null():
    assert regime(RegimeRow(as_of="2026-06-01", kospi_pbr=None, us_cape=None)) == (
        "레짐 데이터 미확보"
    )


def test_regime_kospi_only():
    res = regime(RegimeRow(as_of="2026-06-01", kospi_pbr=1.05, us_cape=None))
    assert res == "KOSPI PBR 1.05"


def test_regime_both_present():
    res = regime(RegimeRow(as_of="2026-06-01", kospi_pbr=1.05, us_cape=32.4))
    assert res == "KOSPI PBR 1.05 · US CAPE 32.4"


def test_regime_sqlite_row_shiller_cape(conn):
    """sqlite Row(shiller_cape) None-safe 접근."""
    conn.execute(
        "INSERT INTO market_regime (trade_date, shiller_cape, kospi_pbr) "
        "VALUES ('2026-06-01', 30.0, NULL)"
    )
    conn.commit()
    row = conn.execute("SELECT * FROM market_regime").fetchone()
    res = regime(row)
    assert res == "US CAPE 30.0"


# ═══════════════════ core_sat 한도 ═══════════════════


def test_core_sat_over_limit(make_holding):
    """satellite 비중 > limit → over_limit True."""
    core = _priced(make_holding(canonical_ticker="A", category="core"), 60.0)
    sat = _priced(make_holding(canonical_ticker="B", category="satellite"), 40.0)
    res = core_sat([core, sat], limit_pct=30.0)
    assert res.core_pct == pytest.approx(60.0)
    assert res.satellite_pct == pytest.approx(40.0)
    assert res.over_limit is True


def test_core_sat_under_limit(make_holding):
    core = _priced(make_holding(canonical_ticker="A", category="core"), 80.0)
    sat = _priced(make_holding(canonical_ticker="B", category="satellite"), 20.0)
    res = core_sat([core, sat], limit_pct=30.0)
    assert res.over_limit is False


# ═══════════════════ asset_alloc usd_held 임계 ═══════════════════


def test_asset_alloc_usd_held_over_threshold(make_holding):
    """usd_held True + USD 비중 >= threshold → alloc_held True."""
    eq = _priced(make_holding(canonical_ticker="A", market="KR", ccy="KRW"), 70.0)
    usd = _priced(
        make_holding(canonical_ticker="B", market="US", ccy="USD"), 30.0
    )
    res = asset_alloc([eq, usd], usd_held=True, threshold_pct=20.0)
    assert res.equity_pct == pytest.approx(100.0)
    assert res.cash_pct == pytest.approx(0.0)
    assert res.alloc_held is True


def test_asset_alloc_usd_held_under_threshold(make_holding):
    eq = _priced(make_holding(canonical_ticker="A", market="KR", ccy="KRW"), 90.0)
    usd = _priced(make_holding(canonical_ticker="B", market="US", ccy="USD"), 10.0)
    res = asset_alloc([eq, usd], usd_held=True, threshold_pct=20.0)
    assert res.alloc_held is False


def test_asset_alloc_equity_cash_split(make_holding):
    eq = _priced(make_holding(canonical_ticker="A", asset_class="equity"), 60.0)
    cash = _priced(
        make_holding(
            canonical_ticker=None, asset_class="cash", instrument="cash",
            market=None, ccy="KRW",
        ),
        40.0,
    )
    res = asset_alloc([eq, cash], usd_held=False, threshold_pct=20.0)
    assert res.equity_pct == pytest.approx(60.0)
    assert res.cash_pct == pytest.approx(40.0)
    assert res.alloc_held is False


def test_asset_alloc_empty_total(make_holding):
    """value_base 합 0 → 0/0, alloc_held=usd_held 통과."""
    held = _priced(make_holding(canonical_ticker="A"), None, "fx_held")
    res = asset_alloc([held], usd_held=True, threshold_pct=20.0)
    assert res.equity_pct == 0.0
    assert res.cash_pct == 0.0
    assert res.alloc_held is True


# ═══════════════════ evaluate_gate ═══════════════════


def test_evaluate_gate_blocked_both_dead(conn):
    """KR·US 모두 FAIL → blocked."""
    _seed_collect_run(conn, "KR", "FAIL", "2026-06-03")
    _seed_collect_run(conn, "US", "FAIL", "2026-06-03")
    res = evaluate_gate(conn)
    assert res.blocked is True
    assert res.fx_ok is False
    assert res.us_ok is False


def test_evaluate_gate_fx_only_dead(conn):
    """FX만 FAIL → blocked 아님, fx_ok=False, banner."""
    _seed_collect_run(conn, "KR", "OK", "2026-06-03")
    _seed_collect_run(conn, "US", "OK", "2026-06-03")
    _seed_collect_run(conn, "FX", "FAIL", "2026-06-03")
    res = evaluate_gate(conn)
    assert res.blocked is False
    assert res.fx_ok is False
    assert res.us_ok is True
    assert res.banner == "일부 시장 데이터 보류"


def test_evaluate_gate_all_ok(conn):
    _seed_collect_run(conn, "KR", "OK", "2026-06-03")
    _seed_collect_run(conn, "US", "OK", "2026-06-03")
    _seed_collect_run(conn, "FX", "OK", "2026-06-03")
    res = evaluate_gate(conn)
    assert res.blocked is False
    assert res.fx_ok is True
    assert res.us_ok is True
    assert res.banner is None


def test_evaluate_gate_holiday_backfill_not_blocking(conn):
    """OK_HOLIDAY·BACKFILL은 alive로 취급, 차단 아님."""
    _seed_collect_run(conn, "KR", "OK_HOLIDAY", "2026-06-03")
    _seed_collect_run(conn, "US", "BACKFILL", "2026-06-03")
    res = evaluate_gate(conn)
    assert res.blocked is False
    assert res.us_ok is True


def test_evaluate_gate_us_dead_kr_alive(conn):
    """US FAIL·KR OK → blocked 아님, us_ok=False."""
    _seed_collect_run(conn, "KR", "OK", "2026-06-03")
    _seed_collect_run(conn, "US", "FAIL", "2026-06-03")
    res = evaluate_gate(conn)
    assert res.blocked is False
    assert res.us_ok is False
    assert res.banner == "일부 시장 데이터 보류"


# ═══════════════════ collect_complete_today ═══════════════════


def _patch_today_and_calendar(monkeypatch, today_iso, expected_iso):
    """date.today()와 calendar.expected_trade_date를 고정."""
    import app.metrics.gate as gate_mod

    class _FixedDate(date):
        @classmethod
        def today(cls):
            return date.fromisoformat(today_iso)

    monkeypatch.setattr(gate_mod, "date", _FixedDate)
    monkeypatch.setattr(
        gate_mod.calendar,
        "expected_trade_date",
        lambda market, today: date.fromisoformat(expected_iso),
    )


def _seed_holding_market(conn, market, ct):
    conn.execute(
        "INSERT INTO holdings (asset_class, instrument, tracking, market, "
        "canonical_ticker, name, quantity) VALUES "
        "('equity', 'stock', 'auto', ?, ?, 'x', 1.0)",
        (market, ct),
    )
    conn.commit()


def test_collect_complete_today_no_row(conn, monkeypatch):
    """collect_run row 없음 → False."""
    _seed_holding_market(conn, "KR", "005930")
    _patch_today_and_calendar(monkeypatch, "2026-06-03", "2026-06-03")
    assert collect_complete_today(conn) is False


def test_collect_complete_today_mismatch(conn, monkeypatch):
    """trade_date 불일치(전날값) → False."""
    _seed_holding_market(conn, "KR", "005930")
    _seed_collect_run(conn, "KR", "OK", "2026-06-02")
    _patch_today_and_calendar(monkeypatch, "2026-06-03", "2026-06-03")
    assert collect_complete_today(conn) is False


def test_collect_complete_today_match(conn, monkeypatch):
    """모든 시장 trade_date 일치 → True."""
    _seed_holding_market(conn, "KR", "005930")
    _seed_collect_run(conn, "KR", "OK", "2026-06-03")
    _patch_today_and_calendar(monkeypatch, "2026-06-03", "2026-06-03")
    assert collect_complete_today(conn) is True


def test_collect_complete_today_no_markets(conn, monkeypatch):
    """보유 시장 없음(cash only) → 빈 루프 True."""
    _patch_today_and_calendar(monkeypatch, "2026-06-03", "2026-06-03")
    assert collect_complete_today(conn) is True


# ═══════════════════ dca (월 적립 배분) ═══════════════════


def _drift_result(per_group):
    flags = {g: gap > 0 for g, gap in per_group.items()}
    return DriftResult(
        per_group=per_group, flags=flags, rebalance_needed=any(flags.values())
    )


def test_dca_no_contribution(make_holding):
    """monthly <= 0 → 빈 배분, note=dca_no_contribution."""
    res = dca([], _drift_result({}), None, monthly=0.0)
    assert res.allocations == {}
    assert res.note_key == "dca_no_contribution"


def test_dca_balanced_no_under_group(make_holding):
    """미달 자산군(gap<0) 없음 → 빈 배분, note=dca_balanced."""
    p = _priced(make_holding(canonical_ticker="A", category="core"), 100.0)
    res = dca([p], _drift_result({"core": 5.0}), None, monthly=1000.0)
    assert res.allocations == {}
    assert res.note_key == "dca_balanced"


def test_dca_drift_priority(make_holding):
    """미달 자산군 종목에 부족분 비례 배분."""
    a = _priced(make_holding(canonical_ticker="A", category="core"), 50.0)
    b = _priced(make_holding(canonical_ticker="B", category="satellite"), 50.0)
    # core 미달(-10), satellite 초과(+10) → core(A)에만 배분
    res = dca([a, b], _drift_result({"core": -10.0, "satellite": 10.0}), None, 1000.0)
    assert res.note_key == "dca_drift_priority"
    assert res.allocations == {"A": pytest.approx(1000.0)}


def test_dca_undervalued_weighting_tuple(make_holding):
    """저평가(게이트 통과) 종목 2배 가중 — (ct, label) 튜플 형태."""
    a = _priced(make_holding(canonical_ticker="A", category="core"), 50.0)
    b = _priced(make_holding(canonical_ticker="B", category="core"), 50.0)
    # 둘 다 core 미달. A는 '저평가' → 가중 2배.
    valuations = [("A", "저평가"), ("B", "중립")]
    res = dca([a, b], _drift_result({"core": -10.0}), valuations, 900.0)
    # A weight=10*2=20, B weight=10 → A=600, B=300
    assert res.allocations["A"] == pytest.approx(600.0)
    assert res.allocations["B"] == pytest.approx(300.0)


def test_dca_undervalued_weighting_object(make_holding):
    """저평가 추출 — 객체(attr) 형태 + dict.items() 경로."""

    class _V:
        def __init__(self, ct, label):
            self.canonical_ticker = ct
            self.label = label

    a = _priced(make_holding(canonical_ticker="A", category="core"), 50.0)
    valuations = {"A": _V("A", "undervalued")}
    res = dca([a], _drift_result({"core": -10.0}), valuations, 1000.0)
    # 단일 종목이라 가중 무관하게 전액
    assert res.allocations["A"] == pytest.approx(1000.0)


def test_dca_skips_cash_and_no_ticker(make_holding):
    """cash·canonical None 종목은 배분 대상 아님 → total_w 0이면 balanced."""
    cash = _priced(
        make_holding(
            canonical_ticker=None, asset_class="cash", instrument="cash",
            market=None, category=None, ccy="KRW",
        ),
        100.0,
    )
    # cash만 있고 equity 없음 → weights 비어 total_w<=0 → balanced
    res = dca([cash], _drift_result({"uncategorized": -10.0}), None, 1000.0)
    assert res.allocations == {}
    assert res.note_key == "dca_balanced"


def test_dca_undervalued_none_valuations(make_holding):
    """valuation_results None → 저평가 가중 없이 정상 배분."""
    a = _priced(make_holding(canonical_ticker="A", category="core"), 50.0)
    res = dca([a], _drift_result({"core": -10.0}), None, 1000.0)
    assert res.allocations["A"] == pytest.approx(1000.0)


# ═══════════════ 회귀 보강 (harness-review advisory A-2/A-4/A-5) ═══════════════


def test_evaluate_gate_kr_dead_us_alive(conn):
    """A-2: KR FAIL·US OK → blocked 아님, us_ok=True (reverse 조합 회귀)."""
    _seed_collect_run(conn, "KR", "FAIL", "2026-06-03")
    _seed_collect_run(conn, "US", "OK", "2026-06-03")
    _seed_collect_run(conn, "FX", "OK", "2026-06-03")
    res = evaluate_gate(conn)
    assert res.blocked is False
    assert res.us_ok is True
    assert res.fx_ok is True
    assert res.banner is None  # KR FAIL은 alive 집합 밖이지만 US·FX alive → 부분보류 배너 없음


def test_collect_complete_today_fail_status_counts(conn, monkeypatch):
    """A-4: status=FAIL이어도 기대거래일 row가 존재하면 사이클은 '돈 것' → True.
    (04 §10.2 정본: status 무관, row 존재 = 수집 사이클 완료. FAIL 차단은 evaluate_gate 책임.)"""
    _seed_holding_market(conn, "KR", "005930")
    _seed_collect_run(conn, "KR", "FAIL", "2026-06-03")
    _patch_today_and_calendar(monkeypatch, "2026-06-03", "2026-06-03")
    assert collect_complete_today(conn) is True


def test_build_priced_fx_fail_krw_cash_unaffected(conn, make_holding):
    """A-5: fx FAIL이어도 KRW 현금은 보류 없이 정상(value_manual 그대로)."""
    krw_cash = make_holding(
        id=9,
        asset_class="cash",
        instrument="cash",
        tracking="manual",
        market=None,
        canonical_ticker=None,
        quantity=None,
        value_manual=500000.0,
        ccy="KRW",
        category=None,
    )
    out = build_priced(conn, [krw_cash], fx_ok=False, us_ok=True)
    assert len(out) == 1
    assert out[0].status == "ok"
    assert out[0].value_base == pytest.approx(500000.0)
