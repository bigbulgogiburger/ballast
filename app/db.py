"""SQLite 연결·스키마·조회/적재 헬퍼 (BAL-8).

SSoT: TECH-DESIGN §15 > docs/05-database.md > docs/04-backend.md.
시그니처 정본: docs/BAL-1-m1a-orchestration.md §2.1 (v2) + decisions §3.4/§3.6.

범위(W1): connect / init_schema(9테이블 + 인덱스 ②④ + ux + settings seed) /
latest_price·funda·fx / upsert_price·funda·fx. collect_run·holdings 등 그 외
upsert·백필·신선도 집계는 W2+ (Out of scope).
"""
import dataclasses
import sqlite3

from app.config import SETTINGS_DEFAULTS  # @dataclass(frozen=True) Settings 인스턴스
from app.models import Funda, FxRate, Headline, OHLCV, RegimeRow


def connect(db_path: str = "data/ballast.db") -> sqlite3.Connection:
    """PoC 런타임 규약(Row factory · FK · WAL · busy_timeout)으로 연결. 05 §0."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn


# 05 §1.1~1.9 DDL 9테이블 + §2 인덱스 ②④ + ux_holdings_user_ct(05 §1.1).
# ①③⑤는 PK prefix가 핫패스를 커버하므로 생성하지 않는다(05 §2 결론).
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS holdings (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id          INTEGER NOT NULL DEFAULT 1,
  asset_class      TEXT    NOT NULL,
  instrument       TEXT    NOT NULL,
  tracking         TEXT    NOT NULL,
  market           TEXT,
  canonical_ticker TEXT,
  name             TEXT    NOT NULL,
  quantity         REAL,
  value_manual     REAL,
  ccy              TEXT,
  avg_price        REAL,
  category         TEXT,
  target_pct       REAL,
  created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
  updated_at       TEXT    NOT NULL DEFAULT (datetime('now')),
  CHECK (asset_class IN ('equity','cash','bond')),
  CHECK (instrument  IN ('stock','etf','cash')),
  CHECK (tracking    IN ('auto','manual')),
  CHECK (market IS NULL OR market IN ('KR','US')),
  CHECK (ccy    IS NULL OR ccy    IN ('KRW','USD')),
  CHECK (category IS NULL OR category IN ('core','satellite')),
  CHECK (tracking != 'auto' OR (market IS NOT NULL AND canonical_ticker IS NOT NULL AND quantity IS NOT NULL)),
  CHECK (tracking != 'manual' OR (value_manual IS NOT NULL AND ccy IS NOT NULL AND quantity IS NULL)),
  CHECK (target_pct IS NULL OR (target_pct >= 0 AND target_pct <= 100))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_holdings_user_ct
  ON holdings(user_id, market, canonical_ticker)
  WHERE canonical_ticker IS NOT NULL;

CREATE TABLE IF NOT EXISTS settings (
  user_id INTEGER NOT NULL DEFAULT 1,
  key     TEXT    NOT NULL,
  value   TEXT    NOT NULL,
  PRIMARY KEY (user_id, key)
);

CREATE TABLE IF NOT EXISTS price_snapshot (
  canonical_ticker TEXT NOT NULL,
  trade_date       TEXT NOT NULL,
  close_adj        REAL,
  close_raw        REAL,
  ccy              TEXT NOT NULL,
  week52_high      REAL,
  week52_low       REAL,
  sma200           REAL,
  PRIMARY KEY (canonical_ticker, trade_date),
  CHECK (ccy IN ('KRW','USD'))
);

CREATE TABLE IF NOT EXISTS fundamentals_snapshot (
  canonical_ticker TEXT NOT NULL,
  trade_date       TEXT NOT NULL,
  per              REAL,
  pbr              REAL,
  div_yield        REAL,
  per_pctile_5y    REAL,
  pbr_pctile_5y    REAL,
  report_date      TEXT,
  PRIMARY KEY (canonical_ticker, trade_date)
);

CREATE TABLE IF NOT EXISTS fx_snapshot (
  trade_date TEXT NOT NULL,
  pair       TEXT NOT NULL,
  rate       REAL NOT NULL,
  PRIMARY KEY (trade_date, pair)
);

CREATE TABLE IF NOT EXISTS news_snapshot (
  canonical_ticker TEXT NOT NULL,
  trade_date       TEXT NOT NULL,
  url              TEXT NOT NULL,
  title            TEXT NOT NULL,
  source           TEXT,
  PRIMARY KEY (canonical_ticker, trade_date, url)
);

CREATE TABLE IF NOT EXISTS market_regime (
  trade_date   TEXT PRIMARY KEY,
  shiller_cape REAL,
  kospi_pbr    REAL
);

CREATE TABLE IF NOT EXISTS collect_run (
  trade_date      TEXT NOT NULL,
  market          TEXT NOT NULL,
  status          TEXT NOT NULL,
  n_ok            INTEGER NOT NULL DEFAULT 0,
  n_fail          INTEGER NOT NULL DEFAULT 0,
  missing_tickers TEXT,
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (trade_date, market),
  CHECK (market IN ('KR','US','FX')),
  CHECK (status IN ('OK','PARTIAL','FAIL','BACKFILL','OK_HOLIDAY'))
);

CREATE TABLE IF NOT EXISTS briefing (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id       INTEGER NOT NULL DEFAULT 1,
  briefing_date TEXT NOT NULL,
  content_json  TEXT NOT NULL,
  model         TEXT NOT NULL,
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS ix_briefing_user_date
  ON briefing(user_id, briefing_date, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_holdings_user_tracking
  ON holdings(user_id, tracking);
"""


def init_schema(conn: sqlite3.Connection) -> None:
    """9테이블 + 인덱스 + settings seed를 멱등 생성. 05 §1~§2 + §15.5."""
    conn.executescript(_SCHEMA_SQL)
    _seed_settings(conn)


def _seed_settings(conn: sqlite3.Connection) -> None:
    """settings 기본값 seed. 출처=asdict(SETTINGS_DEFAULTS), 저장형 TEXT, 사용자값 비파괴(decisions Q1)."""
    for key, value in dataclasses.asdict(SETTINGS_DEFAULTS).items():
        conn.execute(
            "INSERT INTO settings (user_id, key, value) VALUES (1, ?, ?) "
            "ON CONFLICT(user_id, key) DO NOTHING",
            (key, str(value)),
        )
    conn.commit()


def latest_price(conn: sqlite3.Connection, ct: str) -> sqlite3.Row | None:
    """canonical_ticker별 최신 시세 1행. 0건→None. 05 §3.1."""
    return conn.execute(
        "SELECT canonical_ticker, trade_date, close_adj, close_raw, ccy, "
        "week52_high, week52_low, sma200 FROM price_snapshot "
        "WHERE canonical_ticker = ? ORDER BY trade_date DESC LIMIT 1",
        (ct,),
    ).fetchone()


def latest_funda(conn: sqlite3.Connection, ct: str) -> sqlite3.Row | None:
    """canonical_ticker별 최신 펀더 1행. 0건→None. 05 §3.2."""
    return conn.execute(
        "SELECT canonical_ticker, trade_date, per, pbr, div_yield, "
        "per_pctile_5y, pbr_pctile_5y, report_date FROM fundamentals_snapshot "
        "WHERE canonical_ticker = ? ORDER BY trade_date DESC LIMIT 1",
        (ct,),
    ).fetchone()


def latest_fx(conn: sqlite3.Connection, pair: str = "USDKRW") -> sqlite3.Row | None:
    """pair별 최신 환율 1행. 0건→None. 05 §3.2."""
    return conn.execute(
        "SELECT trade_date, pair, rate FROM fx_snapshot "
        "WHERE pair = ? ORDER BY trade_date DESC LIMIT 1",
        (pair,),
    ).fetchone()


def upsert_price(conn: sqlite3.Connection, row: OHLCV) -> None:
    """OHLCV 적재(ON CONFLICT DO UPDATE). named param=컬럼 전체명(decisions §3.4). self-commit(Q4)."""
    conn.execute(
        "INSERT INTO price_snapshot "
        "(canonical_ticker, trade_date, close_adj, close_raw, ccy, week52_high, week52_low, sma200) "
        "VALUES (:canonical_ticker, :trade_date, :close_adj, :close_raw, :ccy, "
        ":week52_high, :week52_low, :sma200) "
        "ON CONFLICT (canonical_ticker, trade_date) DO UPDATE SET "
        "close_adj=excluded.close_adj, close_raw=excluded.close_raw, "
        "week52_high=excluded.week52_high, week52_low=excluded.week52_low, sma200=excluded.sma200",
        dataclasses.asdict(row),
    )
    conn.commit()


def upsert_funda(conn: sqlite3.Connection, row: Funda) -> None:
    """Funda 적재(ON CONFLICT DO UPDATE). named param=컬럼 전체명. self-commit."""
    conn.execute(
        "INSERT INTO fundamentals_snapshot "
        "(canonical_ticker, trade_date, per, pbr, div_yield, per_pctile_5y, pbr_pctile_5y, report_date) "
        "VALUES (:canonical_ticker, :trade_date, :per, :pbr, :div_yield, "
        ":per_pctile_5y, :pbr_pctile_5y, :report_date) "
        "ON CONFLICT (canonical_ticker, trade_date) DO UPDATE SET "
        "per=excluded.per, pbr=excluded.pbr, div_yield=excluded.div_yield, "
        "per_pctile_5y=excluded.per_pctile_5y, pbr_pctile_5y=excluded.pbr_pctile_5y, "
        "report_date=excluded.report_date",
        dataclasses.asdict(row),
    )
    conn.commit()


def upsert_fx(conn: sqlite3.Connection, row: FxRate) -> None:
    """fx 적재. W2에서 FxRate frozen dataclass로 통일(decisions §3.1, W1 dict-surface 대체). self-commit."""
    conn.execute(
        "INSERT INTO fx_snapshot (trade_date, pair, rate) "
        "VALUES (:trade_date, :pair, :rate) "
        "ON CONFLICT (trade_date, pair) DO UPDATE SET rate=excluded.rate",
        dataclasses.asdict(row),
    )
    conn.commit()


# ── W2 헬퍼 (BAL-2 / decisions §3.5) — collect.py(BAL-17) 의존물, W2-1 선커밋 ──

def auto_holdings(conn: sqlite3.Connection, user_id: int = 1) -> list[sqlite3.Row]:
    """tracking='auto' 보유종목 행. collect가 market/canonical_ticker/name 키로 순회. 05 §1.1."""
    return conn.execute(
        "SELECT id, market, canonical_ticker, name, quantity, ccy "
        "FROM holdings WHERE user_id = ? AND tracking = 'auto'",
        (user_id,),
    ).fetchall()


def latest_collect_run(conn: sqlite3.Connection, market: str) -> sqlite3.Row | None:
    """market별 최신 수집 실행 1행(MAX(trade_date)). 0건→None. 게이트(04 §10.2)용. 05 §1.8."""
    return conn.execute(
        "SELECT trade_date, market, status, n_ok, n_fail, missing_tickers "
        "FROM collect_run WHERE market = ? ORDER BY trade_date DESC LIMIT 1",
        (market,),
    ).fetchone()


def markets_in_use(conn: sqlite3.Connection, user_id: int = 1) -> list[str]:
    """보유 종목이 있는 시장 집합(holdings.market DISTINCT, NULL=cash 제외). 04 §10.2."""
    rows = conn.execute(
        "SELECT DISTINCT market FROM holdings "
        "WHERE user_id = ? AND market IS NOT NULL",
        (user_id,),
    ).fetchall()
    return [r["market"] for r in rows]


def upsert_news(
    conn: sqlite3.Connection, rows: list[Headline], ct: str, trade_date: str
) -> None:
    """뉴스 헤드라인 적재. PK(ct,trade_date,url) → DO NOTHING(url 중복 무시, 05 §1.6/§4.1)."""
    for h in rows:
        conn.execute(
            "INSERT INTO news_snapshot (canonical_ticker, trade_date, url, title, source) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT (canonical_ticker, trade_date, url) DO NOTHING",
            (ct, trade_date, h.url, h.title, h.source),
        )
    conn.commit()


def upsert_market_regime(conn: sqlite3.Connection, row: RegimeRow) -> None:
    """레짐 적재. as_of→trade_date, us_cape→shiller_cape 매핑(05 §1.7). ON CONFLICT DO UPDATE."""
    conn.execute(
        "INSERT INTO market_regime (trade_date, shiller_cape, kospi_pbr) "
        "VALUES (:trade_date, :shiller_cape, :kospi_pbr) "
        "ON CONFLICT (trade_date) DO UPDATE SET "
        "shiller_cape=excluded.shiller_cape, kospi_pbr=excluded.kospi_pbr",
        {"trade_date": row.as_of, "shiller_cape": row.us_cape, "kospi_pbr": row.kospi_pbr},
    )
    conn.commit()


def upsert_collect_run(
    conn: sqlite3.Connection,
    trade_date: str,
    market: str,
    status: str,
    n_ok: int,
    n_fail: int,
    missing_tickers: str | None,
) -> None:
    """수집 실행 기록. PK(trade_date,market). missing_tickers=caller가 json.dumps한 문자열. 05 §1.8/§4.2."""
    conn.execute(
        "INSERT INTO collect_run "
        "(trade_date, market, status, n_ok, n_fail, missing_tickers) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (trade_date, market) DO UPDATE SET "
        "status=excluded.status, n_ok=excluded.n_ok, n_fail=excluded.n_fail, "
        "missing_tickers=excluded.missing_tickers, created_at=datetime('now')",
        (trade_date, market, status, n_ok, n_fail, missing_tickers),
    )
    conn.commit()
