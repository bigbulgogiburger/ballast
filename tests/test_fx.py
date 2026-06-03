"""BAL-14 app/sources/fx.py 단위 테스트. 외부 소스(ECB/yfinance) 전량 모킹."""
import pytest

import app.sources as sources_pkg
from app.sources import EmptyResponseError, fx
from app.sources.fx import FxSource


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(sources_pkg.time, "sleep", lambda *a, **k: None)


@pytest.mark.unit
def test_usdkrw_ecb_primary(monkeypatch):
    monkeypatch.setattr(FxSource, "_from_ecb", lambda self: 1380.5)
    r = FxSource().usdkrw()
    assert r.pair == "USDKRW" and r.rate == 1380.5 and len(r.trade_date) == 10


@pytest.mark.unit
def test_usdkrw_yf_fallback(monkeypatch):
    monkeypatch.setattr(FxSource, "_from_ecb", lambda self: (_ for _ in ()).throw(RuntimeError("ecb")))
    monkeypatch.setattr(FxSource, "_from_ecos", lambda self: None)
    monkeypatch.setattr(FxSource, "_from_yf", lambda self: 1390.0)
    r = FxSource().usdkrw()
    assert r.rate == 1390.0


@pytest.mark.unit
def test_usdkrw_all_fail_raises(monkeypatch):
    monkeypatch.setattr(FxSource, "_from_ecb", lambda self: None)
    monkeypatch.setattr(FxSource, "_from_ecos", lambda self: None)
    monkeypatch.setattr(FxSource, "_from_yf", lambda self: None)
    with pytest.raises(EmptyResponseError):  # 0/NULL 위장 금지 → 산출 거부
        FxSource().usdkrw()


@pytest.mark.unit
def test_valid_rate_rejects_nonpositive():
    assert fx._valid_rate(0) is None
    assert fx._valid_rate(-5) is None
    assert fx._valid_rate(float("nan")) is None
    assert fx._valid_rate(1380.5) == 1380.5


@pytest.mark.unit
def test_ecb_synthesis_math(monkeypatch):
    # USDKRW = (KRW/EUR) / (USD/EUR) = 1491.54 / 1.08 ≈ 1380.13 (decisions §1.2 Q3)
    monkeypatch.setattr(FxSource, "_ecb_rate",
                        lambda self, ccy: 1491.54 if ccy == "KRW" else 1.08)
    assert abs(FxSource()._from_ecb() - 1491.54 / 1.08) < 0.01


@pytest.mark.unit
def test_ecb_synthesis_partial_none(monkeypatch):
    monkeypatch.setattr(FxSource, "_ecb_rate",
                        lambda self, ccy: None if ccy == "KRW" else 1.08)
    assert FxSource()._from_ecb() is None  # 결측 → 폴백 유도


@pytest.mark.unit
def test_usdkrw_invalid_then_valid(monkeypatch):
    # 1차가 무효값(0) 반환 → _from_ecb이 _valid_rate로 None → 다음 폴백
    monkeypatch.setattr(FxSource, "_from_ecb", lambda self: None)
    monkeypatch.setattr(FxSource, "_from_ecos", lambda self: None)
    monkeypatch.setattr(FxSource, "_from_yf", lambda self: 1375.0)
    assert FxSource().usdkrw().rate == 1375.0
