"""브리핑 생성 — 슬롯주입·금지어 린트·LLM 배치호출·수치주입 조립 (BAL-27/28).

책임 경계(04 §10.3 / 06 §3·§4·§5):
  - 06 소유: 슬롯주입(`inject`)·금지어 린트(`lint`)·ct 조인(G2)·배치호출
    (`run_securities`/`run_portfolio`) → 텍스트 전용 SecurityLLMOut 반환.
  - 04 소유: 수치(metrics)를 코드가 직접 박아 SecurityCard/BriefingDoc 조립
    (`assemble_briefing`)·파이프라인(`run_briefing`).

NEVER(CLAUDE.md):
  - 숫자는 코드가 박는다 — LLM이 슬롯 밖에 쓴 raw 숫자는 RAW_NUMBER가 reject.
  - 면책(disclaimer)은 코드 상수(config.DISCLAIMER) — LLM 생성 금지.
  - 보류 종목(hold_status != 'ok')은 LLM 미호출(G3/G6).
  - 키·시크릿 로그/예외 노출 금지(LLM 어댑터 책임, 본 모듈은 비용/식별자만 로깅).
"""
import logging
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date

from app import config, db
from app.llm import LLMError
from app.metrics import portfolio as pf
from app.metrics import security as sec
from app.metrics.gate import GateResult, collect_complete_today, evaluate_gate
from app.metrics.priced import build_priced
from app.models import (
    OHLCV,
    BriefingDoc,
    Funda,
    Headline,
    HoldExcluded,
    LLMClient,
    PricedHolding,
    SecurityCard,
    SecurityLLMOut,
)
from app.schemas import PORTFOLIO_SCHEMA, SECURITY_SCHEMA

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-5"
BATCH = 10

# ─────────────────────────── 06 §3·§4 정규식 ───────────────────────────
SLOT = re.compile(r"\{([a-z0-9_]+)\}")
BANNED = re.compile(
    r"(매수하세요|매도하세요|사세요|파세요|지금이?\s*기회|반드시|"
    r"무조건|급등|급락 예상|확실|보장|추천합니다)"
)
RAW_NUMBER = re.compile(r"(?<![{\w])\d+(\.\d+)?\s*(%|원|달러|\$|배)")  # 슬롯 밖 raw 숫자


class LintError(Exception):
    """금지어·슬롯 밖 raw 숫자 검출(06 §4)."""


# ─────────────────────────── 입력 DTO (06 §1.2) ───────────────────────────
@dataclass(frozen=True)
class SecurityInput:
    """지표엔진(S5) → LLM 입력. canonical_ticker가 배치 join 1차 키(G2). 06 §1.2."""

    canonical_ticker: str
    name: str
    market: str
    hold_status: str                       # 'ok'만 LLM 호출, 그 외 보류(G3/G6)
    slots: dict[str, str]                  # {key: 표기문자열} — 슬롯주입용 코드 계산값
    valuation_band: str | None
    valuation_warmup: bool
    per: float | None
    trend_pos_52w: str
    eps_trend: str
    headlines: list[dict]                  # [{title,url,source}] 본문없음(G7)


@dataclass(frozen=True)
class PortfolioInput:
    """포트폴리오 LLM 입력. prompt + 슬롯주입용 계산값. 06 §1.2."""

    prompt: str
    slots: dict[str, str]


# ─────────────────────── 내부 metrics 통합 (04 §10.1) ───────────────────────
# run_all_metrics(§10.1)는 W3 부재 — build_priced + W3 metric 함수 호출 결과를
# run_briefing 안에서 조립하는 최소 컨테이너. metric 로직 자체는 변경 없음(호출만).
@dataclass(frozen=True)
class SecurityMetric:
    """종목별 코드 계산값 묶음 — assemble가 수치를 SecurityCard에 박는 소스."""

    canonical_ticker: str
    name: str
    market: str | None
    instrument: str
    asset_class: str
    category: str | None
    status: str                            # §15.4 enum (hold_status)
    change_pct: float | None
    current_pct: float
    target_pct: float | None
    drift: float | None
    rebalance_flag: bool
    valuation: sec.ValuationLabel
    trend: sec.TrendLabel
    headlines: list[Headline] = field(default_factory=list)


@dataclass(frozen=True)
class MetricsBundle:
    """run_all_metrics 대체 — securities + portfolio 결과 + 레짐/as_of 묶음."""

    securities: list[SecurityMetric]
    drift: pf.DriftResult
    core_sat: pf.CoreSatResult
    alloc: pf.AllocResult
    dca: pf.DcaResult
    regime_label: str
    as_of: dict


# ─────────────────────────── 06 §3 슬롯주입 ───────────────────────────
def inject(text: str, slots: dict[str, str]) -> str:
    """LLM 문장의 {key}를 코드 계산값으로 단방향 치환. 미정의 키 → LLMError. 06 §3."""

    def repl(m: "re.Match[str]") -> str:
        key = m.group(1)
        if key not in slots:
            raise LLMError(f"unknown slot {{{key}}}")
        return slots[key]

    return SLOT.sub(repl, text)


# ─────────────────────────── 06 §4 린터 ───────────────────────────
def lint(card_text: str) -> None:
    """슬롯주입 후 최종 문자열 검증. 금지어/슬롯 밖 raw 숫자 → LintError. 06 §4."""
    if BANNED.search(card_text):
        raise LintError("banned phrase")
    if RAW_NUMBER.search(card_text):
        raise LintError("raw number outside slot")


def _lint_and_inject(out: SecurityLLMOut, slots: dict[str, str]) -> SecurityLLMOut:
    """LLM 원문(placeholder 보존)에 린트 → 슬롯주입. 06 §3·§4.

    RAW_NUMBER는 placeholder({key})가 남아있는 LLM 원문에서 검사한다(음의 lookbehind
    `(?<![{\\w])`로 슬롯 내부 숫자는 스킵) — 그래야 LLM이 슬롯 밖에 직접 쓴 raw 숫자만
    reject하고, 코드가 주입한 정상 수치는 통과한다. 주입 후 검사는 모든 정상 수치를
    raw로 오탐하므로 금지. 실패 시 LintError 전파.
    """
    lint(
        "\n".join([out.comment, out.trend_note, *out.investment_points])
    )
    return SecurityLLMOut(
        canonical_ticker=out.canonical_ticker,
        comment=inject(out.comment, slots),
        trend_note=inject(out.trend_note, slots),
        investment_points=[inject(p, slots) for p in out.investment_points],
    )


# ─────────────────────── 06 §5 프롬프트 + 배치 호출 ───────────────────────
def build_security_prompt(batch: list[SecurityInput]) -> str:
    """배치 종목별 컨텍스트(수치·뉴스 포함)를 한국어 프롬프트로 직렬화. 06 §6/§10.4.

    canonical_ticker echo를 강제하고, 본문 수치는 placeholder로만 쓰게 한다.
    """
    lines = [
        "다음 종목들에 대해 각각 맥락형 코멘트를 작성하세요.",
        "수치는 직접 쓰지 말고 제시된 placeholder({key})만 사용하세요.",
        "canonical_ticker는 입력값 그대로 echo하세요.",
        "",
    ]
    for s in batch:
        lines.append(f"- canonical_ticker: {s.canonical_ticker} ({s.name}, {s.market})")
        lines.append(f"  밸류에이션: {s.valuation_band or '워밍업 중'}")
        lines.append(f"  추세: {s.trend_pos_52w}, EPS 추세: {s.eps_trend}")
        for h in s.headlines:
            # 외부 뉴스 텍스트 — 개행 제거 + 길이 절단(프롬프트 인젝션 표면 축소).
            title = str(h.get("title", "")).replace("\n", " ").replace("\r", " ")[:100]
            source = str(h.get("source", "")).replace("\n", " ").replace("\r", " ")[:40]
            lines.append(f"  헤드라인: {title} ({source})")
        slot_keys = ", ".join(f"{{{k}}}" for k in s.slots)
        lines.append(f"  사용 가능한 placeholder: {slot_keys}")
    return "\n".join(lines)


def assemble_llm_outs(
    batch: list[SecurityInput], resp_securities: list[dict]
) -> tuple[list[SecurityLLMOut], list[HoldExcluded]]:
    """ct left-join(G2) + 슬롯주입 + 린트. 텍스트 전용 SecurityLLMOut/HoldExcluded 반환. 06 §4·§5.

    - 미매칭(변형) → HoldExcluded(ct, 'llm_unmatched').
    - 중복 ticker → 첫 건만 채택, 경고 로그('llm_duplicate').
    - 누락(응답에 없는 입력 종목) → HoldExcluded(ct, 'failed').
    - 슬롯주입/린트 실패 → LLMError/LintError 전파(호출측이 배치 1회 재호출).
    """
    by_ct: dict[str, dict] = {}
    for item in resp_securities:
        ct = item.get("canonical_ticker")
        if ct is None:
            continue
        if ct in by_ct:
            logger.warning("llm_duplicate: %s", ct)  # 첫 건만 채택
            continue
        by_ct[ct] = item

    input_cts = {s.canonical_ticker for s in batch}
    outs: list[SecurityLLMOut] = []
    failed: list[HoldExcluded] = []

    for s in batch:
        item = by_ct.pop(s.canonical_ticker, None)
        if item is None:  # 응답 누락
            failed.append(HoldExcluded(s.canonical_ticker, "failed"))
            continue
        raw = SecurityLLMOut(
            canonical_ticker=s.canonical_ticker,
            comment=item.get("comment", ""),
            trend_note=item.get("trend_note", ""),
            investment_points=list(item.get("investment_points", [])),
        )
        outs.append(_lint_and_inject(raw, s.slots))

    # 입력에 없는 응답 ct(변형/환각) → 미매칭
    for ct in by_ct:
        if ct not in input_cts:
            failed.append(HoldExcluded(ct, "llm_unmatched"))

    return outs, failed


def run_securities(
    client: LLMClient, items: list[SecurityInput]
) -> tuple[list[SecurityLLMOut], list[HoldExcluded]]:
    """배치분할 LLM 호출 + ct조인 + 슬롯주입 + 린트. 06 §5.2.

    보류(hold_status != 'ok') 종목은 live 필터로 제외 → LLM 미호출(G3/G6).
    린트/슬롯/LLM 실패 시 해당 배치 1회 재호출, 재실패 시 그 종목 failed 카드.
    수치는 절대 안 건드림 — 최종 SecurityCard 수치주입은 assemble_briefing 소유.
    """
    live = [s for s in items if s.hold_status == "ok"]
    outs: list[SecurityLLMOut] = []
    failed: list[HoldExcluded] = []
    for i in range(0, len(live), BATCH):
        batch = live[i : i + BATCH]
        try:
            resp = client.generate(build_security_prompt(batch), SECURITY_SCHEMA)
            batch_outs, batch_failed = assemble_llm_outs(batch, resp["securities"])
        except (LLMError, LintError):
            try:  # 배치 1회 재호출
                resp = client.generate(build_security_prompt(batch), SECURITY_SCHEMA)
                batch_outs, batch_failed = assemble_llm_outs(batch, resp["securities"])
            except (LLMError, LintError):  # 재실패 → 배치 전 종목 failed 카드
                batch_outs = []
                batch_failed = [
                    HoldExcluded(s.canonical_ticker, "failed") for s in batch
                ]
        outs += batch_outs
        failed += batch_failed
    return outs, failed


def run_portfolio(client: LLMClient, port_input: PortfolioInput) -> dict:
    """포트폴리오 LLM 1회 호출 + 슬롯주입 + 린트 → {rebalance_note,dca_note,weight_note}. 06 §5.2."""
    resp = client.generate(port_input.prompt, PORTFOLIO_SCHEMA)
    out: dict[str, str] = {}
    for key in ("rebalance_note", "dca_note", "weight_note"):
        raw = resp.get(key, "")
        lint(raw)  # LLM 원문(placeholder 보존)에서 raw 숫자 검사 — _lint_and_inject 참조
        out[key] = inject(raw, port_input.slots)
    return out


# ─────────────────────── 04 §10.4 LLM 입력 조립 ───────────────────────
def _fmt(value: float | None, suffix: str = "", *, signed: bool = False) -> str:
    """슬롯 표기문자열 포맷(None → '—'). signed=True면 부호 포함."""
    if value is None:
        return "—"
    if signed:
        return f"{value:+.1f}{suffix}"
    return f"{value:.1f}{suffix}"


def _pct100(ratio: float | None) -> float | None:
    """0~1 비율 → % 스케일(None-safe)."""
    return None if ratio is None else ratio * 100.0


def _security_slots(m: SecurityMetric) -> dict[str, str]:
    """SecurityMetric → 슬롯주입용 표기 dict(코드 계산값). 06 §3."""
    v = m.valuation
    t = m.trend
    return {
        "per": _fmt(v.per),
        "pbr": _fmt(v.pbr),
        "div_yield": _fmt(v.div_yield, "%"),
        "valuation_band": v.label,
        "pos_52w": _fmt(_pct100(t.week52_pos), "%"),
        "sma200_gap": _fmt(_pct100(t.sma200_gap), "%", signed=True),
        "change_pct": _fmt(m.change_pct, "%", signed=True),
        "current_pct": _fmt(m.current_pct, "%"),
        "target_pct": _fmt(m.target_pct, "%"),
        "drift": _fmt(m.drift, "%p", signed=True),
    }


def build_security_inputs(
    metrics: MetricsBundle, news: dict[str, list[Headline]]
) -> list[SecurityInput]:
    """종목별 LLM 입력 조립(보류 hold_status 포함 — live 필터는 run_securities). 04 §10.4."""
    inputs: list[SecurityInput] = []
    for m in metrics.securities:
        v = m.valuation
        headlines = [
            {"title": h.title, "url": h.url, "source": h.source}
            for h in news.get(m.canonical_ticker, [])
        ]
        inputs.append(
            SecurityInput(
                canonical_ticker=m.canonical_ticker,
                name=m.name,
                market=m.market or "",
                hold_status=m.status,
                slots=_security_slots(m),
                valuation_band=None if v.pctile is None else v.label,
                valuation_warmup=v.pctile is None,
                per=v.per,
                trend_pos_52w=_fmt(_pct100(m.trend.week52_pos), "%"),
                eps_trend="flat",  # EPS 추세 산출은 W3 범위 밖(BAL-23) — 중립 고정
                headlines=headlines,
            )
        )
    return inputs


def build_portfolio_input(metrics: MetricsBundle) -> PortfolioInput:
    """포트폴리오 LLM 입력(prompt + 슬롯). 04 §10.4 / 06 §1.2."""
    slots = {
        "core_pct": _fmt(metrics.core_sat.core_pct, "%"),
        "satellite_pct": _fmt(metrics.core_sat.satellite_pct, "%"),
        "equity_pct": _fmt(metrics.alloc.equity_pct, "%"),
        "cash_pct": _fmt(metrics.alloc.cash_pct, "%"),
    }
    drift_lines = [
        f"- {g}: 드리프트 {gap:+.1f}%p (트리거: {metrics.drift.flags.get(g, False)})"
        for g, gap in metrics.drift.per_group.items()
    ]
    prompt = "\n".join(
        [
            "포트폴리오 리밸런싱·적립·비중 코멘트를 작성하세요.",
            "수치는 직접 쓰지 말고 placeholder({key})만 사용하세요.",
            f"레짐: {metrics.regime_label}",
            *drift_lines,
            f"사용 가능한 placeholder: {', '.join(f'{{{k}}}' for k in slots)}",
        ]
    )
    return PortfolioInput(prompt=prompt, slots=slots)


# ─────────────────────── 04 §10.3 SecurityCard 조립 ───────────────────────
def build_security_card(
    m: SecurityMetric, llm_out: SecurityLLMOut | None, gate: GateResult
) -> SecurityCard:
    """수치(metrics)는 코드가 박고 텍스트는 LLM에서 머지. llm_out None → status='failed'. 04 §10.3."""
    v = m.valuation
    t = m.trend
    if llm_out is None:
        # 보류(data_pending/fx_held/warmup)는 상태 유지, ok인데 LLM 누락이면 failed.
        status = m.status if m.status != "ok" else "failed"
        comment = trend_note = ""
        points: list[str] = []
    else:
        status = m.status
        comment = llm_out.comment
        trend_note = llm_out.trend_note
        points = llm_out.investment_points
    return SecurityCard(
        canonical_ticker=m.canonical_ticker,
        name=m.name,
        instrument=m.instrument,
        asset_class=m.asset_class,
        category=m.category,
        change_pct=m.change_pct,
        current_pct=m.current_pct,
        target_pct=m.target_pct,
        drift=m.drift,
        rebalance_flag=m.rebalance_flag,
        per=v.per,
        pbr=v.pbr,
        div_yield=v.div_yield,
        valuation_pctile=v.pctile,
        valuation_label=v.label,
        week52_pos=t.week52_pos,
        sma200_gap=t.sma200_gap,
        status=status,
        comment=comment,
        trend_note=trend_note,
        investment_points=points,
    )


def assemble_briefing(
    metrics: MetricsBundle,
    sec_llm: list[SecurityLLMOut],
    sec_failed: list[HoldExcluded],
    port_comment: dict,
    gate: GateResult,
) -> BriefingDoc:
    """수치 코드주입 + LLM 텍스트 머지 → 최종 BriefingDoc. 면책=코드 상수. 04 §10.3."""
    by_ct = {o.canonical_ticker: o for o in sec_llm}
    cards = [
        build_security_card(m, by_ct.get(m.canonical_ticker), gate)
        for m in metrics.securities
    ]
    asset_allocation = {
        "equity_pct": metrics.alloc.equity_pct,
        "cash_pct": metrics.alloc.cash_pct,
        "core_pct": metrics.core_sat.core_pct,
        "satellite_pct": metrics.core_sat.satellite_pct,
        "satellite_over_limit": metrics.core_sat.over_limit,
    }
    now = date.today().isoformat()
    return BriefingDoc(
        briefing_date=now,
        model=_MODEL,
        created_at=now,
        banner=gate.banner,
        regime_label=metrics.regime_label,
        as_of=metrics.as_of,
        asset_allocation=asset_allocation,
        securities=cards,
        holds_excluded=sec_failed,
        dca={"allocations": metrics.dca.allocations, "note": metrics.dca.note_key},
        portfolio_comment=port_comment,
        disclaimer=config.DISCLAIMER,
    )


# ─────────────────────── 04 §10.1 metrics 최소 통합 ───────────────────────
def _ohlcv_from_row(row: sqlite3.Row) -> OHLCV:
    return OHLCV(
        canonical_ticker=row["canonical_ticker"],
        trade_date=row["trade_date"],
        close_raw=row["close_raw"],
        close_adj=row["close_adj"],
        ccy=row["ccy"],
        week52_high=row["week52_high"],
        week52_low=row["week52_low"],
        sma200=row["sma200"],
    )


def _funda_from_row(row: sqlite3.Row) -> Funda:
    return Funda(
        canonical_ticker=row["canonical_ticker"],
        trade_date=row["trade_date"],
        per=row["per"],
        pbr=row["pbr"],
        div_yield=row["div_yield"],
        per_pctile_5y=row["per_pctile_5y"],
        pbr_pctile_5y=row["pbr_pctile_5y"],
        report_date=row["report_date"],
    )


def _security_valuation(conn: sqlite3.Connection, ct: str | None) -> sec.ValuationLabel:
    """ct별 최신 펀더 → valuation 라벨(없으면 워밍업)."""
    if ct is None:
        return sec.ValuationLabel("워밍업 중", None, None, None, None)
    row = db.latest_funda(conn, ct)
    if row is None:
        return sec.ValuationLabel("워밍업 중", None, None, None, None)
    return sec.valuation(_funda_from_row(row))


def _security_trend(conn: sqlite3.Connection, ct: str | None) -> sec.TrendLabel:
    """ct별 최신 시세 → trend 라벨(없으면 None-pair)."""
    if ct is None:
        return sec.TrendLabel(None, None)
    row = db.latest_price(conn, ct)
    if row is None:
        return sec.TrendLabel(None, None)
    return sec.trend(_ohlcv_from_row(row))


def _latest_regime(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT trade_date, shiller_cape, kospi_pbr FROM market_regime "
        "ORDER BY trade_date DESC LIMIT 1"
    ).fetchone()


def _build_as_of(conn: sqlite3.Connection) -> dict:
    """as_of 3키 — 각 스냅샷 최신 trade_date(없으면 None). §15.2."""

    _ALLOWED = {"price_snapshot", "fundamentals_snapshot", "fx_snapshot"}

    def _max(table: str) -> str | None:
        if table not in _ALLOWED:  # 화이트리스트 — f-string 주입 표면 차단
            raise ValueError(f"disallowed table: {table}")
        r = conn.execute(
            f"SELECT MAX(trade_date) AS d FROM {table}"  # noqa: S608 (화이트리스트 검증됨)
        ).fetchone()
        return r["d"] if r is not None else None

    return {
        "price": _max("price_snapshot"),
        "funda": _max("fundamentals_snapshot"),
        "fx": _max("fx_snapshot"),
    }


def _build_metrics(
    conn: sqlite3.Connection,
    priced: list[PricedHolding],
    settings: config.Settings,
) -> MetricsBundle:
    """run_all_metrics 부재 → W3 metric 함수 호출 결과를 MetricsBundle로 최소 조립.

    metric 로직 자체는 호출만(변경 없음). 종목별 current_pct만 equity value_base
    합으로 산출(분모=산출가능 equity, 보류 종목은 0% — 분모 제외 아님).
    """
    # 사용자 명시 target_pct 우선, 미지정은 자동목표(평가액 비의존, G5).
    auto = pf.auto_targets([p.holding for p in priced if p.value_base is None])
    targets = {
        p.holding.canonical_ticker: (
            p.holding.target_pct
            if p.holding.target_pct is not None
            else auto.get(p.holding.canonical_ticker, 0.0)
        )
        for p in priced
        if p.holding.canonical_ticker is not None
    }
    drift_res = pf.drift(
        priced,
        targets,
        band_abs=float(settings.rebalance_band_abs),
        band_rel=settings.rebalance_band_rel / 100.0,
        micro_floor=settings.micro_weight_floor,
    )
    core_sat_res = pf.core_sat(priced, float(settings.satellite_limit_pct))
    usd_held = any(p.status == "fx_held" for p in priced)
    alloc_res = pf.asset_alloc(priced, usd_held, settings.usd_cash_gate_threshold)

    equity_total = sum(
        p.value_base
        for p in priced
        if p.value_base is not None and p.holding.asset_class == "equity"
    )
    regime_label = sec.regime(_latest_regime(conn))

    valuation_results: list[tuple[str, str]] = []
    securities: list[SecurityMetric] = []
    for p in priced:
        h = p.holding
        ct = h.canonical_ticker
        valuation = _security_valuation(conn, ct)
        trend = _security_trend(conn, ct)
        cur_pct = 0.0
        if equity_total > 0 and p.value_base is not None and h.asset_class == "equity":
            cur_pct = (p.value_base / equity_total) * 100.0
        grp = h.category if h.category is not None else "uncategorized"
        if ct is not None:
            valuation_results.append((ct, valuation.label))
        securities.append(
            SecurityMetric(
                canonical_ticker=ct or h.name,
                name=h.name,
                market=h.market,
                instrument=h.instrument,
                asset_class=h.asset_class,
                category=h.category,
                status=p.status,
                change_pct=None,  # 전일대비는 prev_close 미확보(MVP) → None
                current_pct=cur_pct,
                target_pct=targets.get(ct) if ct is not None else None,
                drift=drift_res.per_group.get(grp),
                rebalance_flag=drift_res.flags.get(grp, False),
                valuation=valuation,
                trend=trend,
            )
        )
    dca_res = pf.dca(
        priced, drift_res, valuation_results, float(settings.monthly_contribution)
    )
    return MetricsBundle(
        securities=securities,
        drift=drift_res,
        core_sat=core_sat_res,
        alloc=alloc_res,
        dca=dca_res,
        regime_label=regime_label,
        as_of=_build_as_of(conn),
    )


# ─────────────────────── 04 §10.1 파이프라인 ───────────────────────
def _save_blocked_briefing(conn: sqlite3.Connection, gate: GateResult) -> int:
    """게이트 차단/수집 미완 시 배너 doc 저장(빈 종목). 04 §10.1."""
    now = date.today().isoformat()
    doc = BriefingDoc(
        briefing_date=now,
        model=_MODEL,
        created_at=now,
        banner=gate.banner,
        regime_label="레짐 데이터 미확보",
        as_of=_build_as_of(conn),
        asset_allocation={},
        securities=[],
        holds_excluded=[],
        dca={},
        portfolio_comment={},
        disclaimer=config.DISCLAIMER,
    )
    return db.insert_briefing(conn, 1, doc.to_json(), model=_MODEL)


def run_briefing(conn: sqlite3.Connection, llm: LLMClient, user_id: int = 1) -> int:
    """일배치 브리핑 생성 파이프라인. 생성된 briefing.id 반환. 04 §10.1."""
    if not collect_complete_today(conn):  # 선검사(08:00→08:30 핸드오프)
        return _save_blocked_briefing(
            conn, GateResult(True, False, False, "수집 미완 — 브리핑 보류")
        )
    gate = evaluate_gate(conn)
    if gate.blocked:
        return _save_blocked_briefing(conn, gate)

    priced = build_priced(
        conn, db.holdings(conn, user_id), fx_ok=gate.fx_ok, us_ok=gate.us_ok
    )
    metrics = _build_metrics(conn, priced, config.SETTINGS_DEFAULTS)

    sec_inputs = build_security_inputs(metrics, news=db.headlines_map(conn))
    port_input = build_portfolio_input(metrics)

    sec_llm, sec_failed = run_securities(llm, sec_inputs)
    port_comment = run_portfolio(llm, port_input)

    doc = assemble_briefing(metrics, sec_llm, sec_failed, port_comment, gate)
    # total_cost_usd: LLMClient.generate는 structured_output만 노출(envelope 비용 미surface)
    # → 비용 합산 불가. 식별자/규모만 로깅(키·시크릿 비노출).
    logger.info(
        "briefing assembled: securities=%d failed=%d total_cost_usd=unavailable",
        len(doc.securities),
        len(sec_failed),
    )
    return db.insert_briefing(conn, user_id, doc.to_json(), model=_MODEL)
