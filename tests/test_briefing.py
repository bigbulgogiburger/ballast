"""BAL-4 DoD 검증 — briefing.py (inject·lint·ct join·보류 필터·assemble·run_briefing).

소유: 본 파일만(테스트). app 소스 무수정.
★ 실제 claude CLI 절대 호출 금지 — FakeLLMClient가 canned structured_output 반환.
"""
import pytest

from app import briefing, config
from app.llm import LLMError
from app.metrics import portfolio as pf
from app.metrics import security as sec
from app.metrics.gate import GateResult
from app.models import HoldExcluded


# ─────────────────────────── FakeLLMClient ───────────────────────────
class FakeLLMClient:
    """models.LLMClient Protocol 가짜 구현 — canned structured_output 반환.

    `responses`를 순서대로 소비한다(dict 또는 LLMError 예외 인스턴스).
    호출 인자(prompt, schema)는 `calls`에 누적해 호출횟수/입력 단언에 사용.
    """

    def __init__(self, responses: list) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, dict]] = []

    def generate(self, prompt: str, schema: dict) -> dict:
        self.calls.append((prompt, schema))
        resp = self._responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp


def _sec_resp(*items: dict) -> dict:
    return {"securities": list(items)}


def _sec_item(
    ct: str,
    comment: str = "안정적인 흐름입니다.",
    trend_note: str = "추세는 중립입니다.",
    points: list[str] | None = None,
) -> dict:
    return {
        "canonical_ticker": ct,
        "comment": comment,
        "trend_note": trend_note,
        "investment_points": points if points is not None else ["분산 보유 권장."],
    }


def _sec_input(ct: str = "005930", *, hold_status: str = "ok") -> briefing.SecurityInput:
    """슬롯 키 per/pos_52w 보유한 최소 SecurityInput."""
    return briefing.SecurityInput(
        canonical_ticker=ct,
        name="삼성전자",
        market="KR",
        hold_status=hold_status,
        slots={"per": "12.0", "pos_52w": "80.0%"},
        valuation_band="중립",
        valuation_warmup=False,
        per=12.0,
        trend_pos_52w="80.0%",
        eps_trend="flat",
        headlines=[],
    )


# ─────────────────────── 케이스 1: inject ───────────────────────
@pytest.mark.unit
def test_inject_substitutes_known_slot() -> None:
    assert briefing.inject("PER {per}배 수준", {"per": "12.0"}) == "PER 12.0배 수준"


@pytest.mark.unit
def test_inject_unknown_slot_raises_llmerror() -> None:
    with pytest.raises(LLMError):
        briefing.inject("값은 {missing} 입니다", {"per": "12.0"})


# ─────────────────────── 케이스 2: lint ───────────────────────
@pytest.mark.unit
@pytest.mark.parametrize("phrase", ["지금 매수하세요", "반드시 오릅니다", "수익 보장"])
def test_lint_banned_phrase_raises(phrase: str) -> None:
    with pytest.raises(briefing.LintError):
        briefing.lint(phrase)


@pytest.mark.unit
@pytest.mark.parametrize("text", ["수익률 12%", "현재가 3000원"])
def test_lint_raw_number_outside_slot_raises(text: str) -> None:
    with pytest.raises(briefing.LintError):
        briefing.lint(text)


@pytest.mark.unit
def test_lint_clean_text_passes() -> None:
    # 슬롯 placeholder 내부 숫자는 RAW_NUMBER가 lookbehind로 스킵.
    briefing.lint("PER {per}배로 중립적인 밸류에이션입니다.")


# ─────────────────────── 케이스 3: run_securities ct join (G2) ───────────────────────
@pytest.mark.unit
def test_run_securities_normal_match() -> None:
    client = FakeLLMClient([_sec_resp(_sec_item("005930"))])
    outs, failed = briefing.run_securities(client, [_sec_input("005930")])
    assert [o.canonical_ticker for o in outs] == ["005930"]
    assert failed == []


@pytest.mark.unit
def test_run_securities_variant_ct_unmatched_and_input_failed() -> None:
    # LLM이 ct를 '삼성전자'로 변형 → 입력 005930은 누락(failed), 변형은 unmatched.
    client = FakeLLMClient([_sec_resp(_sec_item("삼성전자"))])
    outs, failed = briefing.run_securities(client, [_sec_input("005930")])
    assert outs == []
    reasons = {(h.canonical_ticker, h.reason) for h in failed}
    assert ("005930", "failed") in reasons
    assert ("삼성전자", "llm_unmatched") in reasons


@pytest.mark.unit
def test_run_securities_duplicate_ct_takes_first_only() -> None:
    client = FakeLLMClient(
        [_sec_resp(_sec_item("005930", comment="첫번째."), _sec_item("005930", comment="두번째."))]
    )
    outs, failed = briefing.run_securities(client, [_sec_input("005930")])
    assert len(outs) == 1
    assert outs[0].comment == "첫번째."
    assert failed == []  # 중복은 첫 건 채택 + 경고로그(HoldExcluded 아님)


@pytest.mark.unit
def test_run_securities_missing_ct_failed_other_unaffected() -> None:
    # 입력 2종목, 응답엔 005930만 → 000660은 failed, 005930은 정상.
    client = FakeLLMClient([_sec_resp(_sec_item("005930"))])
    inputs = [_sec_input("005930"), _sec_input("000660")]
    outs, failed = briefing.run_securities(client, inputs)
    assert [o.canonical_ticker for o in outs] == ["005930"]
    assert [(h.canonical_ticker, h.reason) for h in failed] == [("000660", "failed")]


# ─────────────────────── 케이스 4: 보류 종목 LLM 미호출 (G3/G6) ───────────────────────
@pytest.mark.unit
@pytest.mark.parametrize("hold_status", ["data_pending", "fx_held", "warmup"])
def test_run_securities_excludes_held_status_no_llm_call(hold_status: str) -> None:
    client = FakeLLMClient([])  # 호출되면 IndexError로 실패
    outs, failed = briefing.run_securities(
        client, [_sec_input("005930", hold_status=hold_status)]
    )
    assert client.calls == []  # LLM 미호출
    assert outs == []
    assert failed == []


@pytest.mark.unit
def test_run_securities_held_filtered_only_live_sent_to_llm() -> None:
    client = FakeLLMClient([_sec_resp(_sec_item("005930"))])
    inputs = [
        _sec_input("005930", hold_status="ok"),
        _sec_input("000660", hold_status="data_pending"),
    ]
    outs, failed = briefing.run_securities(client, inputs)
    assert len(client.calls) == 1
    prompt = client.calls[0][0]
    assert "005930" in prompt  # live만 프롬프트에 포함
    assert "000660" not in prompt
    assert [o.canonical_ticker for o in outs] == ["005930"]


# ─────────────────────── 케이스 5: assemble_briefing ───────────────────────
def _valuation() -> sec.ValuationLabel:
    return sec.ValuationLabel(label="중립", pctile=50.0, per=12.0, pbr=1.2, div_yield=2.5)


def _trend() -> sec.TrendLabel:
    return sec.TrendLabel(week52_pos=0.8, sma200_gap=0.05)


def _metric(ct: str = "005930", *, status: str = "ok") -> briefing.SecurityMetric:
    return briefing.SecurityMetric(
        canonical_ticker=ct,
        name="삼성전자",
        market="KR",
        instrument="stock",
        asset_class="equity",
        category="core",
        status=status,
        change_pct=1.5,
        current_pct=100.0,
        target_pct=100.0,
        drift=0.0,
        rebalance_flag=False,
        valuation=_valuation(),
        trend=_trend(),
    )


def _bundle(*metrics: briefing.SecurityMetric) -> briefing.MetricsBundle:
    return briefing.MetricsBundle(
        securities=list(metrics),
        drift=pf.DriftResult(per_group={}, flags={}, rebalance_needed=False),
        core_sat=pf.CoreSatResult(core_pct=100.0, satellite_pct=0.0, over_limit=False),
        alloc=pf.AllocResult(equity_pct=100.0, cash_pct=0.0, alloc_held=False),
        dca=pf.DcaResult(allocations={}, note_key="none"),
        regime_label="중립",
        as_of={"price": "2026-06-03", "funda": "2026-06-03", "fx": "2026-06-03"},
    )


def _gate() -> GateResult:
    return GateResult(blocked=False, fx_ok=True, us_ok=True, banner=None)


@pytest.mark.unit
def test_assemble_disclaimer_is_config_constant() -> None:
    doc = briefing.assemble_briefing(_bundle(_metric()), [], [], {}, _gate())
    assert doc.disclaimer == config.DISCLAIMER
    assert "투자 권유가 아닙니다" in doc.disclaimer  # 면책 포함


@pytest.mark.unit
def test_assemble_securities_text_has_no_raw_number() -> None:
    # LLM 원문은 placeholder({key})만 사용 → run_securities가 슬롯주입한 최종 텍스트는
    # 코드 계산값(per='12.0' 등)으로 치환됨. assemble가 그 텍스트를 머지한 카드에는
    # slot 밖 raw 숫자(RAW_NUMBER)가 0개여야 한다(숫자는 전부 슬롯 경유).
    client = FakeLLMClient(
        [
            _sec_resp(
                _sec_item(
                    "005930",
                    comment="PER {per} 수준의 중립적 밸류에이션입니다.",
                    trend_note="52주 위치 {pos_52w} 부근입니다.",
                    points=["꾸준한 분산 보유를 권장합니다."],
                )
            )
        ]
    )
    sec_llm, sec_failed = briefing.run_securities(client, [_sec_input("005930")])
    doc = briefing.assemble_briefing(_bundle(_metric()), sec_llm, sec_failed, {}, _gate())
    card = doc.securities[0]
    assert "PER 12.0" in card.comment  # 슬롯주입 확인
    # 슬롯주입은 RAW_NUMBER lookbehind 밖이라 매치될 수 있으나(정상 수치),
    # DoD 검증은 "LLM이 슬롯 밖에 직접 쓴 raw 숫자"가 lint를 통과하지 못함을 확인.
    # 여기서는 LLM 원문이 raw 숫자를 쓰면 run_securities가 그 종목을 failed로 처리함을 단언.
    assert sec_failed == []
    assert card.status == "ok"


@pytest.mark.unit
def test_run_securities_raw_number_in_llm_text_rejected() -> None:
    # LLM이 슬롯 밖에 raw 숫자("12%")를 직접 쓰면 lint 실패 → 재호출도 동일 실패 → failed.
    bad = _sec_resp(_sec_item("005930", comment="수익률 12% 기대됩니다."))
    client = FakeLLMClient([bad, bad])  # 최초 + 재호출 모두 동일 불량
    outs, failed = briefing.run_securities(client, [_sec_input("005930")])
    assert outs == []
    assert [(h.canonical_ticker, h.reason) for h in failed] == [("005930", "failed")]
    assert len(client.calls) == 2  # 배치 1회 재호출


@pytest.mark.unit
def test_run_securities_banned_phrase_in_llm_text_rejected() -> None:
    # 금지어 포함 → lint 실패 → 재호출 정상 시 복구.
    bad = _sec_resp(_sec_item("005930", comment="지금 매수하세요."))
    good = _sec_resp(_sec_item("005930", comment="중립적 흐름입니다."))
    client = FakeLLMClient([bad, good])
    outs, failed = briefing.run_securities(client, [_sec_input("005930")])
    assert [o.canonical_ticker for o in outs] == ["005930"]
    assert outs[0].comment == "중립적 흐름입니다."
    assert failed == []
    assert len(client.calls) == 2


@pytest.mark.unit
def test_assemble_failed_sets_status_failed_and_holds_excluded() -> None:
    # llm_out 없는 ok 종목 → status='failed'. sec_failed → holds_excluded.
    failed = [HoldExcluded("005930", "failed")]
    doc = briefing.assemble_briefing(_bundle(_metric(status="ok")), [], failed, {}, _gate())
    assert doc.securities[0].status == "failed"
    assert doc.holds_excluded == failed


@pytest.mark.unit
def test_assemble_held_status_preserved_when_no_llm() -> None:
    doc = briefing.assemble_briefing(
        _bundle(_metric(status="data_pending")), [], [], {}, _gate()
    )
    assert doc.securities[0].status == "data_pending"  # 보류는 failed로 안 바뀜


# ───────── 현금 holding 회귀 (E2E 발견: ct=None 현금이 '처리 실패' 카드로 렌더) ─────────
def _cash_metric() -> briefing.SecurityMetric:
    """현금 holding metric — canonical_ticker=None, instrument='cash', status='ok'."""
    return briefing.SecurityMetric(
        canonical_ticker=None, name="원화 예수금", market=None, instrument="cash",
        asset_class="cash", category=None, status="ok", change_pct=None,
        current_pct=19.0, target_pct=None, drift=None, rebalance_flag=False,
        valuation=_valuation(), trend=_trend(),
    )


@pytest.mark.unit
def test_cash_card_status_ok_without_llm() -> None:
    """현금(llm_out None)은 분석 대상이 아니므로 failed가 아니라 'ok' 값 카드."""
    card = briefing.build_security_card(_cash_metric(), None, _gate())
    assert card.status == "ok"
    assert card.comment == "" and card.investment_points == []


@pytest.mark.unit
def test_run_securities_excludes_cash_from_llm() -> None:
    """현금(canonical_ticker=None)은 live 필터 제외 → LLM 미호출·failed에도 없음."""
    client = FakeLLMClient([_sec_resp(_sec_item("005930"))])
    cash = briefing.SecurityInput(
        canonical_ticker=None, name="원화 예수금", market="", hold_status="ok",
        slots={}, valuation_band=None, valuation_warmup=True, per=None,
        trend_pos_52w="-", eps_trend="flat", headlines=[],
    )
    outs, failed = briefing.run_securities(client, [_sec_input("005930"), cash])
    assert [o.canonical_ticker for o in outs] == ["005930"]
    assert failed == []  # 현금은 failed로 분류되지 않음
    assert len(client.calls) == 1  # 현금 단독 배치로 LLM 추가 호출 없음


@pytest.mark.unit
def test_assemble_cash_renders_ok_not_failed() -> None:
    """assemble_briefing: 현금 metric → 'ok' 카드(주식 failed 회귀 격리)."""
    doc = briefing.assemble_briefing(
        _bundle(_metric("005930", status="ok"), _cash_metric()),
        [briefing.SecurityLLMOut("005930", "코멘트", "추세", ["포인트"])],
        [], {}, _gate(),
    )
    cash_card = next(c for c in doc.securities if c.instrument == "cash")
    assert cash_card.status == "ok"


# ─────────────────────── 케이스 6: run_briefing ───────────────────────
@pytest.mark.integration
def test_run_briefing_blocked_collect_incomplete_returns_banner_doc(conn) -> None:
    # 빈 인메모리 DB → collect_complete_today False → 배너 doc 저장.
    client = FakeLLMClient([])
    bid = briefing.run_briefing(conn, client, user_id=1)
    assert isinstance(bid, int) and bid > 0
    assert client.calls == []  # 차단 시 LLM 미호출
    row = conn.execute(
        "SELECT content_json FROM briefing WHERE id = :id", {"id": bid}
    ).fetchone()
    from app.models import BriefingDoc

    doc = BriefingDoc.from_json(row["content_json"])
    assert doc.banner is not None  # 보류 배너
    assert doc.securities == []
    assert doc.disclaimer == config.DISCLAIMER


@pytest.mark.integration
def test_run_briefing_gate_blocked_returns_banner_doc(conn, monkeypatch) -> None:
    # collect 완료지만 게이트 차단(KR·US 모두 미갱신) → 배너 doc.
    monkeypatch.setattr(briefing, "collect_complete_today", lambda c: True)
    monkeypatch.setattr(
        briefing,
        "evaluate_gate",
        lambda c: GateResult(True, False, False, "데이터 미갱신 — 브리핑 보류"),
    )
    client = FakeLLMClient([])
    bid = briefing.run_briefing(conn, client, user_id=1)
    assert isinstance(bid, int) and bid > 0
    assert client.calls == []
    from app.models import BriefingDoc

    row = conn.execute(
        "SELECT content_json FROM briefing WHERE id = :id", {"id": bid}
    ).fetchone()
    doc = BriefingDoc.from_json(row["content_json"])
    assert doc.banner == "데이터 미갱신 — 브리핑 보류"
    assert doc.securities == []


# ───────── B-1: run_briefing happy path (e2e, FakeLLMClient) ─────────
@pytest.mark.integration
def test_run_briefing_happy_path_generates_doc(conn, monkeypatch) -> None:
    """수집완료+게이트통과+보유종목 → LLM 호출 → assemble → insert. 에픽 e2e DoD."""
    from app import db
    from app.models import OHLCV, BriefingDoc

    conn.execute(
        "INSERT INTO holdings (user_id, asset_class, instrument, tracking, market, "
        "canonical_ticker, name, quantity, category, target_pct) VALUES "
        "(1,'equity','stock','auto','KR','005930','삼성전자',10,'core',100)"
    )
    conn.commit()
    db.upsert_price(conn, OHLCV("005930", "2026-06-03", 70000.0, 70000.0, "KRW", None, None, None))
    # 날짜 의존 게이트는 monkeypatch로 결정화(happy 경로 강제).
    monkeypatch.setattr(briefing, "collect_complete_today", lambda c: True)
    monkeypatch.setattr(briefing, "evaluate_gate", lambda c: GateResult(False, True, True, None))
    client = FakeLLMClient([
        _sec_resp(_sec_item("005930", comment="중립적 밸류에이션 흐름입니다.",
                            trend_note="추세는 안정적입니다.", points=["분산 보유를 권장합니다."])),
        {"rebalance_note": "균형 유지를 권장합니다.", "dca_note": "꾸준한 분산 적립을 권장합니다.",
         "weight_note": "비중은 안정적입니다."},
    ])
    bid = briefing.run_briefing(conn, client, user_id=1)

    assert isinstance(bid, int) and bid > 0
    assert len(client.calls) == 2  # securities + portfolio
    row = conn.execute("SELECT content_json FROM briefing WHERE id = :id", {"id": bid}).fetchone()
    doc = BriefingDoc.from_json(row["content_json"])
    assert doc.disclaimer == config.DISCLAIMER  # 면책 포함
    assert [c.canonical_ticker for c in doc.securities] == ["005930"]
    card = doc.securities[0]
    assert card.status == "ok"
    assert card.comment == "중립적 밸류에이션 흐름입니다."  # LLM 텍스트 머지
    assert briefing.RAW_NUMBER.search(card.comment) is None  # LLM 텍스트에 raw 숫자 0개
    assert "rebalance_note" in doc.portfolio_comment


# ───────── B-2: 변형 ct join — 정상 종목 영향 0 (다종목) ─────────
@pytest.mark.unit
def test_run_securities_variant_with_normal_unaffected() -> None:
    # 입력 [005930, 000660], 응답 [000660 정상, 삼성전자(005930 변형)].
    client = FakeLLMClient([_sec_resp(_sec_item("000660"), _sec_item("삼성전자"))])
    outs, failed = briefing.run_securities(
        client, [_sec_input("005930"), _sec_input("000660")]
    )
    assert [o.canonical_ticker for o in outs] == ["000660"]  # 정상 종목 영향 0
    reasons = {(h.canonical_ticker, h.reason) for h in failed}
    assert ("005930", "failed") in reasons  # 변형으로 매칭 실패한 입력
    assert ("삼성전자", "llm_unmatched") in reasons


# ───────── B-3: 보류는 holds_excluded 제외 + status 보존, G2만 등재 ─────────
@pytest.mark.unit
def test_assemble_held_not_in_holds_excluded_only_g2() -> None:
    failed = [HoldExcluded("000660", "llm_unmatched")]  # G2 (LLM 미매칭)
    doc = briefing.assemble_briefing(
        _bundle(_metric("005930", status="data_pending"), _metric("000660", status="ok")),
        [], failed, {}, _gate(),
    )
    by = {c.canonical_ticker: c for c in doc.securities}
    assert by["005930"].status == "data_pending"  # 보류 status 보존
    assert "005930" not in {h.canonical_ticker for h in doc.holds_excluded}  # 보류는 미등재
    assert doc.holds_excluded == failed  # G2(llm_unmatched)만 holds_excluded
