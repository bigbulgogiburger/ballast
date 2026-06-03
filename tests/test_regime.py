"""BAL-48(W1) + BAL-15(W2 us_cape) app/sources/regime.py 단위 테스트. 외부 전량 모킹."""
import pandas as pd
import pytest

import app.sources as sources_pkg
from app.sources import regime
from app.sources.regime import RegimeProvider


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(sources_pkg.time, "sleep", lambda *a, **k: None)


def _kospi_df():
    return pd.DataFrame({"PBR": [1.0, 1.1, 1.2]}, index=pd.date_range("2026-05-01", periods=3))


@pytest.mark.unit
def test_regime_kr_and_us(monkeypatch):
    monkeypatch.setattr(regime.stock, "get_index_fundamental", lambda *a, **k: _kospi_df())
    monkeypatch.setattr(regime, "_fetch_us_cape", lambda: 33.2)
    r = RegimeProvider().regime()
    assert r.kospi_pbr == 1.2 and r.us_cape == 33.2  # W2: 양쪽 채움
    assert r.as_of.endswith("-01")


@pytest.mark.unit
def test_regime_us_cape_failure_keeps_kospi(monkeypatch):
    monkeypatch.setattr(regime.stock, "get_index_fundamental", lambda *a, **k: _kospi_df())

    def boom():
        raise RuntimeError("yale+multpl down")

    monkeypatch.setattr(regime, "_fetch_us_cape", boom)
    r = RegimeProvider().regime()
    assert r.kospi_pbr == 1.2 and r.us_cape is None  # us_cape만 NULL, kospi 보존


@pytest.mark.unit
def test_regime_kospi_failure_raises(monkeypatch):
    monkeypatch.setattr(regime, "_fetch_us_cape", lambda: 33.2)
    monkeypatch.setattr(regime.stock, "get_index_fundamental",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("pykrx down")))
    with pytest.raises(RuntimeError):
        RegimeProvider().regime()


@pytest.mark.unit
def test_fetch_us_cape_yale_primary(monkeypatch):
    monkeypatch.setattr(regime, "_cape_from_yale", lambda: 30.5)
    monkeypatch.setattr(regime, "_cape_from_multpl", lambda: 99.9)
    assert regime._fetch_us_cape() == 30.5  # 1차 우선


@pytest.mark.unit
def test_fetch_us_cape_multpl_fallback(monkeypatch):
    monkeypatch.setattr(regime, "_cape_from_yale", lambda: (_ for _ in ()).throw(ValueError("xls")))
    monkeypatch.setattr(regime, "_cape_from_multpl", lambda: 29.1)
    assert regime._fetch_us_cape() == 29.1  # 1차 실패 → 2차


@pytest.mark.unit
def test_fetch_us_cape_both_fail_raises(monkeypatch):
    monkeypatch.setattr(regime, "_cape_from_yale", lambda: (_ for _ in ()).throw(ValueError("xls")))
    monkeypatch.setattr(regime, "_cape_from_multpl", lambda: (_ for _ in ()).throw(ValueError("html")))
    with pytest.raises(ValueError):
        regime._fetch_us_cape()
