"""BAL-37 app/notify.py 단위 테스트 + collect.py FAIL 분기 hook 검증.

urllib.request.urlopen·os.environ를 monkeypatch로 모킹하여 네트워크 없이 검증.
"""
from datetime import date

import pytest

from app import collect, notify


class _FakeResp:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def captured(monkeypatch):
    """urlopen 호출 인자를 수집(Request, timeout)."""
    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append((req, timeout))
        return _FakeResp()

    monkeypatch.setattr(notify.urllib.request, "urlopen", fake_urlopen)
    return calls


def _clear_env(monkeypatch):
    for k in ("NTFY_URL", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.delenv(k, raising=False)


# ── ntfy 경로 ──
@pytest.mark.unit
def test_ntfy_posts_once_to_url(captured, monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("NTFY_URL", "https://ntfy.sh/ballast-secret")
    notify.send_fail_alert("KR", "3건 전부 실패")
    assert len(captured) == 1
    req, timeout = captured[0]
    assert req.full_url == "https://ntfy.sh/ballast-secret"
    assert req.method == "POST"
    assert b"KR" in req.data
    assert timeout == 5


# ── telegram 경로 ──
@pytest.mark.unit
def test_telegram_posts_once_token_in_path(captured, monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "12345:ABCDEF")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "99")
    notify.send_fail_alert("FX", "rate fetch failed")
    assert len(captured) == 1
    req, _ = captured[0]
    assert req.full_url == "https://api.telegram.org/bot12345:ABCDEF/sendMessage"
    assert b"chat_id=99" in req.data


@pytest.mark.unit
def test_both_channels_when_both_set(captured, monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("NTFY_URL", "https://ntfy.sh/t")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    notify.send_fail_alert("US", "x")
    assert len(captured) == 2


# ── 미설정 noop ──
@pytest.mark.unit
def test_no_channel_no_urlopen(captured, monkeypatch):
    _clear_env(monkeypatch)
    notify.send_fail_alert("KR", "x")
    assert captured == []


@pytest.mark.unit
def test_telegram_partial_config_skips(captured, monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")  # CHAT_ID 없음
    notify.send_fail_alert("KR", "x")
    assert captured == []


# ── HTTP 오류 삼킴 ──
@pytest.mark.unit
def test_http_error_swallowed(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("NTFY_URL", "https://ntfy.sh/t")

    def boom(req, timeout=None):
        raise OSError("network down")

    monkeypatch.setattr(notify.urllib.request, "urlopen", boom)
    notify.send_fail_alert("KR", "x")  # 예외 전파되면 안 됨


# ── 브리핑 도착 알림 (send_briefing_alert) ──
@pytest.mark.unit
def test_briefing_alert_posts_summary(captured, monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("NTFY_URL", "https://ntfy.sh/ballast")
    notify.send_briefing_alert("중립 레짐", 2)
    assert len(captured) == 1
    req, _ = captured[0]
    body = req.data.decode("utf-8")
    assert "브리핑 도착" in body
    assert "중립 레짐" in body
    assert "2건" in body
    assert "http://127.0.0.1:8000/" in body


@pytest.mark.unit
def test_briefing_alert_dashboard_url_env_override(captured, monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("NTFY_URL", "https://ntfy.sh/ballast")
    monkeypatch.setenv("BALLAST_DASHBOARD_URL", "https://my.tailnet/")
    notify.send_briefing_alert("중립 레짐", 0)
    req, _ = captured[0]
    assert b"https://my.tailnet/" in req.data


@pytest.mark.unit
def test_briefing_alert_headline_truncated(captured, monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("NTFY_URL", "https://ntfy.sh/ballast")
    notify.send_briefing_alert("가" * 300, 0)
    req, _ = captured[0]
    assert ("가" * 100).encode("utf-8") in req.data
    assert ("가" * 101).encode("utf-8") not in req.data


@pytest.mark.unit
def test_briefing_alert_no_channel_noop(captured, monkeypatch):
    _clear_env(monkeypatch)
    notify.send_briefing_alert("중립 레짐", 1)
    assert captured == []


# ── collect.py FAIL 분기 → send_fail_alert 호출 ──
_TODAY = date(2026, 6, 3)
_EXPECTED = date(2026, 6, 2)


@pytest.fixture
def trading(monkeypatch):
    monkeypatch.setattr(collect.calendar, "is_trading_day", lambda m, d: True)
    monkeypatch.setattr(collect.calendar, "expected_trade_date", lambda m, d: _EXPECTED)


@pytest.mark.unit
def test_collect_market_fail_triggers_alert(conn, trading, monkeypatch):
    calls = []
    monkeypatch.setattr(collect.notify, "send_fail_alert",
                        lambda market, reason: calls.append((market, reason)))
    monkeypatch.setattr(collect.UsSource, "ohlcv",
                        lambda self, ct: (_ for _ in ()).throw(RuntimeError("boom")))
    collect._collect_market("US", [{"market": "US", "canonical_ticker": "AAPL", "name": "Apple"}],
                            _TODAY, "daily", conn)
    assert len(calls) == 1 and calls[0][0] == "US"


@pytest.mark.unit
def test_collect_market_partial_no_alert(conn, trading, monkeypatch):
    from app.models import Funda, OHLCV

    calls = []
    monkeypatch.setattr(collect.notify, "send_fail_alert",
                        lambda market, reason: calls.append((market, reason)))

    def ohlcv(self, ct):
        if ct == "BAD":
            raise RuntimeError("boom")
        return OHLCV(canonical_ticker=ct, trade_date=_EXPECTED.isoformat(), close_raw=100.0,
                     close_adj=99.0, ccy="USD", week52_high=120.0, week52_low=80.0, sma200=95.0)

    monkeypatch.setattr(collect.UsSource, "ohlcv", ohlcv)
    monkeypatch.setattr(collect.UsSource, "fundamentals",
                        lambda self, ct: Funda(canonical_ticker=ct, trade_date=_EXPECTED.isoformat(),
                                               per=12.0, pbr=1.1, div_yield=2.0, per_pctile_5y=40.0,
                                               pbr_pctile_5y=35.0, report_date=None))
    monkeypatch.setattr(collect.UsSource, "headlines", lambda self, ct, name: [])
    holdings = [{"market": "US", "canonical_ticker": "AAPL", "name": "Apple"},
                {"market": "US", "canonical_ticker": "BAD", "name": "Bad"}]
    collect._collect_market("US", holdings, _TODAY, "daily", conn)
    assert calls == []  # PARTIAL은 미호출


@pytest.mark.unit
def test_collect_market_ok_no_alert(conn, trading, monkeypatch):
    from app.models import Funda, OHLCV

    calls = []
    monkeypatch.setattr(collect.notify, "send_fail_alert",
                        lambda market, reason: calls.append((market, reason)))
    monkeypatch.setattr(collect.UsSource, "ohlcv",
                        lambda self, ct: OHLCV(canonical_ticker=ct, trade_date=_EXPECTED.isoformat(),
                                               close_raw=100.0, close_adj=99.0, ccy="USD",
                                               week52_high=120.0, week52_low=80.0, sma200=95.0))
    monkeypatch.setattr(collect.UsSource, "fundamentals",
                        lambda self, ct: Funda(canonical_ticker=ct, trade_date=_EXPECTED.isoformat(),
                                               per=12.0, pbr=1.1, div_yield=2.0, per_pctile_5y=40.0,
                                               pbr_pctile_5y=35.0, report_date=None))
    monkeypatch.setattr(collect.UsSource, "headlines", lambda self, ct, name: [])
    collect._collect_market("US", [{"market": "US", "canonical_ticker": "AAPL", "name": "Apple"}],
                            _TODAY, "daily", conn)
    assert calls == []


@pytest.mark.unit
def test_collect_fx_fail_triggers_alert(conn, monkeypatch):
    calls = []
    monkeypatch.setattr(collect.notify, "send_fail_alert",
                        lambda market, reason: calls.append((market, reason)))
    monkeypatch.setattr(collect.FxSource, "usdkrw",
                        lambda self: (_ for _ in ()).throw(RuntimeError("fx down secret-url")))
    collect._collect_fx(_TODAY, "daily", conn)
    assert len(calls) == 1 and calls[0][0] == "FX"
    # 예외 원문(API 키 포함 URL 등)을 알림 본문에 넣지 않음 — 고정 메시지만.
    assert "secret-url" not in calls[0][1]


@pytest.mark.unit
def test_collect_fx_fail_backfill_no_alert(conn, monkeypatch):
    """backfill 모드 FX FAIL → _collect_market과 일관되게 알림 억제(스팸 방지)."""
    calls = []
    monkeypatch.setattr(collect.notify, "send_fail_alert",
                        lambda market, reason: calls.append((market, reason)))
    monkeypatch.setattr(collect.FxSource, "usdkrw",
                        lambda self: (_ for _ in ()).throw(RuntimeError("fx down")))
    collect._collect_fx(_TODAY, "backfill", conn)
    assert calls == []


# ── 스킴 검증 / Content-Type (Wave2 리뷰 보완) ──
@pytest.mark.unit
def test_non_http_scheme_rejected(captured, monkeypatch):
    """file:// 등 비-HTTP 스킴 NTFY_URL → urlopen 미호출(SSRF/로컬파일 차단)."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("NTFY_URL", "file:///etc/passwd")
    notify.send_fail_alert("KR", "x")
    assert captured == []


@pytest.mark.unit
def test_telegram_sets_content_type(captured, monkeypatch):
    """Telegram POST에 Content-Type 헤더 명시(서버 파싱 400 방지)."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    notify.send_fail_alert("KR", "x")
    req, _ = captured[0]
    assert req.get_header("Content-type") == "application/x-www-form-urlencoded"
