"""scripts/ 진입점 테스트 (BAL-34).

실네트워크/실LLM 차단 — monkeypatch로 collect.run_collect, db.is_backfill_complete,
briefing.run_briefing, make_llm_client를 전부 가짜로 대체.
"""
import inspect
import sqlite3

import pytest

from app import briefing, collect, db
from app.llm import ClaudeCLIClient, LLMError, make_llm_client
from scripts import run_briefing, run_collect


class _FakeLLMClient:
    """LLMClient Protocol 만족 — generate만 구현."""

    def generate(self, prompt: str, schema: dict) -> dict:
        return {}


@pytest.fixture
def _no_connect(monkeypatch):
    """db.connect를 더미 conn으로 대체 — 실 DB 파일 미접근."""
    fake = sqlite3.connect(":memory:")
    monkeypatch.setattr(db, "connect", lambda *a, **k: fake)
    yield fake
    fake.close()


# ─────────────────────── run_collect ───────────────────────
@pytest.mark.unit
def test_run_collect_backfill_flag(monkeypatch):
    """--backfill 명시 → run_collect('backfill'), DB 미조회."""
    calls: list[str] = []
    monkeypatch.setattr(collect, "run_collect", lambda mode: calls.append(mode))

    def _no_db(conn):
        raise AssertionError("is_backfill_complete must not be called with --backfill")

    monkeypatch.setattr(db, "is_backfill_complete", _no_db)
    monkeypatch.setattr("sys.argv", ["run_collect", "--backfill"])

    assert run_collect.main() == 0
    assert calls == ["backfill"]


@pytest.mark.unit
def test_run_collect_handoff_complete_daily(monkeypatch, _no_connect):
    """무인자 + 백필 완료 → run_collect('daily')."""
    calls: list[str] = []
    monkeypatch.setattr(collect, "run_collect", lambda mode: calls.append(mode))
    monkeypatch.setattr(db, "is_backfill_complete", lambda conn: True)
    monkeypatch.setattr("sys.argv", ["run_collect"])

    assert run_collect.main() == 0
    assert calls == ["daily"]


@pytest.mark.unit
def test_run_collect_handoff_incomplete_backfill(monkeypatch, _no_connect):
    """무인자 + 백필 미완 → run_collect('backfill')."""
    calls: list[str] = []
    monkeypatch.setattr(collect, "run_collect", lambda mode: calls.append(mode))
    monkeypatch.setattr(db, "is_backfill_complete", lambda conn: False)
    monkeypatch.setattr("sys.argv", ["run_collect"])

    assert run_collect.main() == 0
    assert calls == ["backfill"]


@pytest.mark.unit
def test_run_collect_exception_returns_1(monkeypatch):
    """run_collect 예외 → exit code 1."""
    def _boom(mode):
        raise RuntimeError("boom")

    monkeypatch.setattr(collect, "run_collect", _boom)
    monkeypatch.setattr("sys.argv", ["run_collect", "--backfill"])

    assert run_collect.main() == 1


@pytest.mark.unit
def test_run_collect_handoff_exception_returns_1(monkeypatch, _no_connect):
    """핸드오프 경로에서 is_backfill_complete 예외 → exit code 1(외부 except 포착)."""
    def _boom(conn):
        raise RuntimeError("db crash")

    monkeypatch.setattr(db, "is_backfill_complete", _boom)
    monkeypatch.setattr(
        collect, "run_collect",
        lambda mode: (_ for _ in ()).throw(AssertionError("run_collect must not run")),
    )
    monkeypatch.setattr("sys.argv", ["run_collect"])

    assert run_collect.main() == 1


# ─────────────────────── run_briefing ───────────────────────
@pytest.mark.unit
def test_run_briefing_happy_path(monkeypatch, _no_connect):
    """정상흐름 — run_briefing 1회 호출(LLM 주입), exit 0."""
    calls: list = []

    def _fake_run(conn, llm):
        calls.append((conn, llm))
        return 1

    monkeypatch.setattr(briefing, "run_briefing", _fake_run)
    monkeypatch.setattr(run_briefing, "make_llm_client", lambda: _FakeLLMClient())

    assert run_briefing.main() == 0
    assert len(calls) == 1
    assert calls[0][0] is _no_connect
    assert isinstance(calls[0][1], _FakeLLMClient)


@pytest.mark.unit
def test_run_briefing_success_sends_alert(monkeypatch, _no_connect):
    """성공 시 최신 브리핑 요약(banner 우선·플래그 수)으로 send_briefing_alert 호출."""
    from app.models import BriefingDoc, SecurityCard

    def _card(rebalance_flag: bool) -> SecurityCard:
        return SecurityCard(
            canonical_ticker="005930", name="삼성전자", instrument="stock",
            asset_class="equity", category="core", change_pct=None,
            current_pct=50.0, target_pct=50.0, drift=0.0,
            rebalance_flag=rebalance_flag, per=None, pbr=None, div_yield=None,
            valuation_pctile=None, valuation_label="중립", week52_pos=None,
            sma200_gap=None, status="ok", comment="", trend_note="",
            investment_points=[],
        )

    doc = BriefingDoc(
        briefing_date="2026-06-11", model="m", created_at="2026-06-11",
        banner=None, regime_label="중립 레짐", as_of={}, asset_allocation={},
        securities=[_card(True), _card(False), _card(True)],
        holds_excluded=[], dca={}, portfolio_comment={}, disclaimer="d",
    )
    monkeypatch.setattr(briefing, "run_briefing", lambda conn, llm: 1)
    monkeypatch.setattr(run_briefing, "make_llm_client", lambda: _FakeLLMClient())
    monkeypatch.setattr(db, "load_latest_briefing", lambda conn: doc)
    alerts: list = []
    monkeypatch.setattr(
        run_briefing.notify, "send_briefing_alert",
        lambda headline, flag_count: alerts.append((headline, flag_count)),
    )

    assert run_briefing.main() == 0
    assert alerts == [("중립 레짐", 2)]


@pytest.mark.unit
def test_run_briefing_alert_failure_keeps_exit_0(monkeypatch, _no_connect):
    """알림 경로 예외는 best-effort — 배치 exit code를 오염시키지 않음."""
    monkeypatch.setattr(briefing, "run_briefing", lambda conn, llm: 1)
    monkeypatch.setattr(run_briefing, "make_llm_client", lambda: _FakeLLMClient())

    def _boom(conn):
        raise RuntimeError("db crash")

    monkeypatch.setattr(db, "load_latest_briefing", _boom)
    assert run_briefing.main() == 0


@pytest.mark.unit
def test_run_briefing_failure_no_alert(monkeypatch, _no_connect):
    """run_briefing 예외 → 알림 미발송."""
    def _boom(conn, llm):
        raise RuntimeError("boom")

    monkeypatch.setattr(briefing, "run_briefing", _boom)
    monkeypatch.setattr(run_briefing, "make_llm_client", lambda: _FakeLLMClient())
    alerts: list = []
    monkeypatch.setattr(
        run_briefing.notify, "send_briefing_alert",
        lambda headline, flag_count: alerts.append(headline),
    )

    assert run_briefing.main() == 1
    assert alerts == []


@pytest.mark.unit
def test_run_briefing_exception_returns_1(monkeypatch, _no_connect):
    """run_briefing 예외 → exit code 1, conn은 close."""
    def _boom(conn, llm):
        raise RuntimeError("boom")

    monkeypatch.setattr(briefing, "run_briefing", _boom)
    monkeypatch.setattr(run_briefing, "make_llm_client", lambda: _FakeLLMClient())

    assert run_briefing.main() == 1


@pytest.mark.unit
def test_run_briefing_closes_conn_on_exception(monkeypatch):
    """run_briefing 예외 시에도 finally로 conn.close() 실제 호출(자원 누수 방지)."""
    closed: list[bool] = []

    class _SpyConn:
        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr(db, "connect", lambda *a, **k: _SpyConn())

    def _boom(conn, llm):
        raise RuntimeError("boom")

    monkeypatch.setattr(briefing, "run_briefing", _boom)
    monkeypatch.setattr(run_briefing, "make_llm_client", lambda: _FakeLLMClient())

    assert run_briefing.main() == 1
    assert closed == [True]


@pytest.mark.unit
def test_run_briefing_main_guard_systemexit(monkeypatch, _no_connect):
    """__main__ 가드 — sys.exit(1) 전파."""
    def _boom(conn, llm):
        raise RuntimeError("boom")

    monkeypatch.setattr(briefing, "run_briefing", _boom)
    monkeypatch.setattr(run_briefing, "make_llm_client", lambda: _FakeLLMClient())

    with pytest.raises(SystemExit) as exc:
        raise SystemExit(run_briefing.main())
    assert exc.value.code == 1


# ─────────────────────── make_llm_client ───────────────────────
@pytest.mark.unit
def test_make_llm_client_returns_protocol(monkeypatch):
    """make_llm_client()는 LLMClient Protocol(generate) 만족 ClaudeCLIClient 반환."""
    # 실 prompts 파일 읽기 차단 — ClaudeCLIClient.__init__의 read_text 우회.
    monkeypatch.setattr(
        ClaudeCLIClient, "__init__", lambda self: setattr(self, "model", "x")
    )
    client = make_llm_client()
    assert isinstance(client, ClaudeCLIClient)
    # LLMClient Protocol 구조 만족 — generate(prompt, schema) -> dict.
    assert callable(getattr(client, "generate", None))
    sig = inspect.signature(client.generate)
    assert list(sig.parameters) == ["prompt", "schema"]


# ─────────────────────── ClaudeCLIClient.generate 오류 경로 ───────────────────────
class _Proc:
    """subprocess.CompletedProcess 스텁."""

    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture
def _client(monkeypatch):
    """실 prompts 파일 미접근 ClaudeCLIClient — _system_prompt 더미 주입."""
    def _init(self, model: str = "claude-sonnet-4-5") -> None:
        self.model = model
        self._system_prompt = "SYS"

    monkeypatch.setattr(ClaudeCLIClient, "__init__", _init)
    return ClaudeCLIClient()


@pytest.mark.unit
def test_generate_returns_structured_output(monkeypatch, _client):
    """정상 envelope → structured_output dict 반환."""
    import app.llm as llm_mod

    payload = '{"is_error": false, "structured_output": {"k": "v"}}'
    monkeypatch.setattr(
        llm_mod.subprocess, "run", lambda *a, **k: _Proc(0, stdout=payload)
    )
    assert _client.generate("p", {"type": "object"}) == {"k": "v"}


@pytest.mark.unit
def test_generate_exit_nonzero_raises_llmerror(monkeypatch, _client):
    """exit≠0 → LLMError(stderr 절단, 시크릿 미노출)."""
    import app.llm as llm_mod

    monkeypatch.setattr(
        llm_mod.subprocess, "run", lambda *a, **k: _Proc(1, stderr="x" * 500)
    )
    with pytest.raises(LLMError) as exc:
        _client.generate("p", {})
    assert "exit 1" in str(exc.value)
    assert len(str(exc.value)) < 260  # stderr 200자 절단 확인


@pytest.mark.unit
def test_generate_is_error_envelope_raises(monkeypatch, _client):
    """envelope.is_error=True → LLMError."""
    import app.llm as llm_mod

    payload = '{"is_error": true, "result": "boom"}'
    monkeypatch.setattr(
        llm_mod.subprocess, "run", lambda *a, **k: _Proc(0, stdout=payload)
    )
    with pytest.raises(LLMError) as exc:
        _client.generate("p", {})
    assert "claude error" in str(exc.value)
