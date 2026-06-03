"""BAL-48 일부 app/sources/regime.py 단위 테스트. pykrx 지수 모킹."""
import pandas as pd
import pytest

import app.sources as sources_pkg
from app.sources import regime
from app.sources.regime import RegimeProvider


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(sources_pkg.time, "sleep", lambda *a, **k: None)


@pytest.mark.unit
def test_regime_kr_only(monkeypatch):
    df = pd.DataFrame(
        {"PBR": [1.0, 1.1, 1.2]},
        index=pd.date_range("2024-05-01", periods=3, freq="D"),
    )
    monkeypatch.setattr(regime.stock, "get_index_fundamental", lambda *a, **k: df)
    r = RegimeProvider().regime()
    assert isinstance(r.kospi_pbr, float) and r.kospi_pbr == 1.2
    assert r.us_cape is None       # W1=KR 절반
    assert r.as_of.endswith("-01")  # 당월 1일


@pytest.mark.unit
def test_regime_failure_raises(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("pykrx down")

    monkeypatch.setattr(regime.stock, "get_index_fundamental", boom)
    with pytest.raises(RuntimeError):  # 실패 시 raise (collect가 W2 degrade)
        RegimeProvider().regime()
