# 바인딩은 반드시 127.0.0.1 (SSoT §12 로컬전용).
# uvicorn app.main:app --host 127.0.0.1 --port 8000. 0.0.0.0 금지.
import sqlite3
from datetime import date

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import config, db
from app.briefing import build_freshness_badge
from app.db import (
    get_settings,
    load_latest_briefing,
    save_holdings,
    save_settings,
)
from app.holdings_form import parse_holdings_form, validate_holdings

# §15.5 설정 키 7종 (config.Settings 정본).
SETTINGS_KEYS: tuple[str, ...] = (
    "base_currency",
    "monthly_contribution",
    "satellite_limit_pct",
    "rebalance_band_abs",
    "rebalance_band_rel",
    "micro_weight_floor",
    "usd_cash_gate_threshold",
)

app = FastAPI(title="ballast")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


def _conn() -> sqlite3.Connection:
    """요청 단위 연결(스키마 멱등 보장). 03 §1."""
    conn = db.connect(config.DB_PATH)
    db.init_schema(conn)
    return conn


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """W0 빈 200 DoD 충족용 헬스 라우트."""
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    """대시보드 — 최신 브리핑 + 신선도 배지. doc None → 빈 상태(e2e G3). 03 §1."""
    conn = _conn()
    try:
        doc = load_latest_briefing(conn)
        badge = build_freshness_badge(conn)
    finally:
        conn.close()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "doc": doc,
            "badge": badge,
            "today": date.today().isoformat(),
            "disclaimer": config.DISCLAIMER,
        },
    )


@app.get("/holdings", response_class=HTMLResponse)
def holdings_get(request: Request) -> HTMLResponse:
    """보유자산 입력/편집 폼. 03 §1."""
    conn = _conn()
    try:
        rows = db.holdings(conn)
    finally:
        conn.close()
    return templates.TemplateResponse(
        request,
        "holdings.html",
        {
            "rows": rows,
            "errors": None,
            "form": None,
            "today": date.today().isoformat(),
            "disclaimer": config.DISCLAIMER,
        },
    )


@app.post("/holdings", response_model=None)
async def holdings_post(request: Request) -> HTMLResponse | RedirectResponse:
    """parse→validate. 실패 시 400 상태보존 재렌더(F5), 성공 시 303 PRG(?saved=1). 03 §1."""
    forms = await parse_holdings_form(request)
    result = validate_holdings(forms)
    if not result.ok:
        return templates.TemplateResponse(
            request,
            "holdings.html",
            {
                "rows": result.rows,
                "errors": result.errors,
                "form": forms,
                "today": date.today().isoformat(),
                "disclaimer": config.DISCLAIMER,
            },
            status_code=400,
        )
    conn = _conn()
    try:
        save_holdings(conn, result.rows)
    finally:
        conn.close()
    return RedirectResponse("/holdings?saved=1", status_code=303)


@app.get("/settings", response_class=HTMLResponse)
def settings_get(request: Request) -> HTMLResponse:
    """설정 폼(§15.5 키). 03 §1."""
    conn = _conn()
    try:
        values = get_settings(conn)
    finally:
        conn.close()
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "settings": values,
            "errors": None,
            "today": date.today().isoformat(),
            "disclaimer": config.DISCLAIMER,
        },
    )


@app.post("/settings", response_model=None)
async def settings_post(request: Request) -> HTMLResponse | RedirectResponse:
    """설정 저장(§15.5 키만 채택). POST 실패 시 상태보존 재렌더. 03 §1."""
    form = await request.form()
    values = {k: form[k] for k in SETTINGS_KEYS if k in form}
    conn = _conn()
    try:
        save_settings(conn, values)
    finally:
        conn.close()
    return RedirectResponse("/settings?saved=1", status_code=303)


@app.post("/api/regenerate")
def regenerate(request: Request) -> RedirectResponse:
    """개발용 수동 재생성 — 127.0.0.1 한정(외부 host → 403). 03 §1 / SSoT §8."""
    if request.client is None or request.client.host != "127.0.0.1":
        raise HTTPException(403)
    return RedirectResponse("/", status_code=303)
