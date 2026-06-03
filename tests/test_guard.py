"""W-2a app/sources/__init__.py (retry + validate_response) 직접 단위 테스트."""
import pytest

import app.sources as sources_pkg
from app.sources import EmptyResponseError, retry, validate_response


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(sources_pkg.time, "sleep", lambda *a, **k: None)


@pytest.mark.unit
def test_retry_eventual_success():
    calls = {"n": 0}

    @retry(times=3)
    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("transient")
        return "ok"

    assert flaky() == "ok" and calls["n"] == 3


@pytest.mark.unit
def test_retry_exhaustion_reraises_last_exc():
    @retry(times=3)
    def always_fail():
        raise ValueError("permanent")

    with pytest.raises(ValueError, match="permanent"):
        always_fail()


@pytest.mark.unit
def test_retry_success_on_first_attempt():
    calls = {"n": 0}

    @retry(times=3)
    def ok() -> int:
        calls["n"] += 1
        return 42

    assert ok() == 42 and calls["n"] == 1


@pytest.mark.unit
def test_validate_response_zero_rows_raises():
    with pytest.raises(EmptyResponseError):
        validate_response(0, "2024-01-02", "2024-01-02")


@pytest.mark.unit
def test_validate_response_positive_rows_pass():
    validate_response(1, "2024-01-02", "2024-01-02")  # 예외 없음


@pytest.mark.unit
def test_validate_response_ignores_date_mismatch_in_w1():
    validate_response(5, "2024-01-01", "2024-01-02")  # W1=날짜 검사 안 함
