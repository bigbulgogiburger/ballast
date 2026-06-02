# 05 · 데이터베이스 명세 — AI 투자 브리핑 PoC

> SSoT: `TECH-DESIGN.md` v3.2 (**DTO·색·키·런타임 정본 = §15 Contract SoT, 충돌 시 §15 우선**) (§4 데이터 모델 · §5 어댑터 · §6 지표 · §7 브리핑 · §8 대시보드 · §9 스케줄)
> 연계: `00-e2e-flow.md` (G2 join 키 · G3 day-0 보류 · G4 화이트리스트 · G5 자동목표 · G6 USD 게이트 · G10 신선도 · G11 content_json)
> 대상: `app/db.py` (스키마 init · 연결) 구현자
> 작성일: 2026-06-01

---

## 0. 설계 전제

- **단일 DB 파일**: `data/ballast.db` (SQLite). `data/`는 `.gitignore` + iCloud/Dropbox 동기화 폴더 **밖**(§13 db 유출 리스크).
- **모든 테이블에 `user_id INTEGER NOT NULL DEFAULT 1`**: PoC는 user_id=1 고정, SaaS 마이그레이션 경로 선반영(§7 멀티유저).
- **캐시 PK는 항상 `canonical_ticker` 기준**: 소스별 티커 표기차(`005930.KS`/`BRK-B`)로 시계열이 갈라지지 않게(§5 tickers.py).
- **조회는 `trade_date=today`가 아니라 `canonical_ticker별 MAX(trade_date)`**: 휴장·실패가 자동 흡수(§4 조회규칙).
- 모든 타임스탬프는 **ISO-8601 텍스트** (`YYYY-MM-DD` 날짜, `YYYY-MM-DDTHH:MM:SS` 시각). SQLite는 native datetime이 없으므로 TEXT로 통일.

### 연결 설정 (`db.py`)

```python
import sqlite3

def connect(db_path: str = "data/ballast.db") -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")   # FK 강제 (기본 OFF)
    conn.execute("PRAGMA journal_mode = WAL;")  # 수집 배치 write 중 대시보드 read 동시성
    conn.execute("PRAGMA busy_timeout = 5000;") # WAL 락 충돌 시 5s 대기
    return conn
```

---

## 1. 전체 DDL

> `app/db.py`의 `init_schema(conn)`이 아래를 `CREATE TABLE IF NOT EXISTS`로 실행. 컬럼 순서·타입·제약은 SSoT §4 그대로 + 무결성 제약 보강.

### 1.1 holdings — 보유 자산 통합 모델 (§4)

```sql
CREATE TABLE IF NOT EXISTS holdings (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id          INTEGER NOT NULL DEFAULT 1,
  asset_class      TEXT    NOT NULL,            -- 'equity' | 'cash'  (bond enum 보존, PoC 미사용)
  instrument       TEXT    NOT NULL,            -- 'stock' | 'etf' | 'cash'
  tracking         TEXT    NOT NULL,            -- 'auto' | 'manual'
  market           TEXT,                        -- 'KR' | 'US'  (auto만 NOT NULL 상당)
  canonical_ticker TEXT,                        -- '005930','VOO'  (auto만)
  name             TEXT    NOT NULL,
  quantity         REAL,                        -- auto: 수량 / manual(현금): NULL
  value_manual     REAL,                        -- manual: 평가액 직접입력(달러예금)
  ccy              TEXT,                         -- 'KRW' | 'USD'
  avg_price        REAL,                        -- 평단가(선택, auto, 현지통화) — PoC 손익 미계산(G8)
  category         TEXT,                         -- 'core' | 'satellite' | NULL(확인 필요)
  target_pct       REAL,                         -- 수동 목표비중(선택). 자동목표는 영속화 안 함(G5)
  created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
  updated_at       TEXT    NOT NULL DEFAULT (datetime('now')),

  CHECK (asset_class IN ('equity','cash','bond')),
  CHECK (instrument  IN ('stock','etf','cash')),
  CHECK (tracking    IN ('auto','manual')),
  CHECK (market IS NULL OR market IN ('KR','US')),
  CHECK (ccy    IS NULL OR ccy    IN ('KRW','USD')),
  CHECK (category IS NULL OR category IN ('core','satellite')),
  -- auto 행은 시세 조회 키가 전부 있어야: 조용히 틀린 값 차단(§1 원칙6)
  CHECK (tracking != 'auto' OR (market IS NOT NULL AND canonical_ticker IS NOT NULL AND quantity IS NOT NULL)),
  -- manual(현금) 행은 평가액+통화 필수, 수량 없음
  CHECK (tracking != 'manual' OR (value_manual IS NOT NULL AND ccy IS NOT NULL AND quantity IS NULL)),
  -- target_pct 범위
  CHECK (target_pct IS NULL OR (target_pct >= 0 AND target_pct <= 100))
);

-- 한 유저가 같은 종목을 중복 입력하지 못하게(시장+티커 유니크). 현금은 ct가 NULL이라 다중 허용.
CREATE UNIQUE INDEX IF NOT EXISTS ux_holdings_user_ct
  ON holdings(user_id, market, canonical_ticker)
  WHERE canonical_ticker IS NOT NULL;
```

> **달러예금** = 한 행(`asset_class='cash'`, `instrument='cash'`, `tracking='manual'`, `value_manual`+`ccy='USD'`). settings.cash_balance는 폐기, holdings로 일원화(§4·§14 v3.1).
> **category 채움 규칙(G4)**: S1 저장 시 `category` 미지정이면 `tickers.CORE_ETF_WHITELIST` frozenset 자동판정 — 매칭 ETF→`core`, 미매칭 ETF→`NULL`(확인 필요), 개별주→`satellite`. 사용자 명시 시 사용자값 우선. **판정 결과를 holdings.category에 영속화**(매 계산 재판정 회피).
> **target_pct 배타(G5)**: "전부 수동 or 전부 자동"만 허용. 일부만 채워지면 POST /holdings에서 400 reject(DB CHECK로는 행간 제약 불가 → 애플리케이션 레이어 검증). 전부 수동이면 합 100% 검증/정규화.
> **`updated_at` 갱신**: SQLite는 `ON UPDATE` 트리거가 없으므로, holdings upsert(POST /holdings) 시 SQL에 `ON CONFLICT(...) DO UPDATE SET ..., updated_at = datetime('now')`를 **명시**해야 수정 시각이 갱신된다(미명시 시 `created_at`에 고정됨).

### 1.2 settings — 키/값 설정 (§4)

```sql
CREATE TABLE IF NOT EXISTS settings (
  user_id INTEGER NOT NULL DEFAULT 1,
  key     TEXT    NOT NULL,
  value   TEXT    NOT NULL,            -- 모든 값 TEXT 저장, 코드가 형변환
  PRIMARY KEY (user_id, key)
);
```

**기본 키 set (코드가 day-0 seed, `config.py` 기본값):**

| key | 기본값 | 용도 |
|---|---|---|
| `base_currency` | `'KRW'` | 통화 정규화 기준(§4) |
| `monthly_contribution` | `'0'` | ⑥ DCA 월 적립금(§6) |
| `satellite_limit_pct` | `'30'` | 새틀 한도·자동 그룹목표(§6) |
| `rebalance_band_abs` | `'5'` | 5/25 절대밴드(%p, §6) |
| `rebalance_band_rel` | `'25'` | 5/25 상대밴드(%, §6) |
| `micro_weight_floor` | `'1.0'` | 미세비중 거짓신호 억제(%p, §6) |
| `usd_cash_gate_threshold` | `'5.0'` | USD 비중 임계(%): 초과 시 fx FAIL→1층 배분 전체 보류(G6) |

> 현금은 settings 아님 — holdings cash 행으로 관리(§4).

### 1.3 price_snapshot — 시세 캐시 (§4)

```sql
CREATE TABLE IF NOT EXISTS price_snapshot (
  canonical_ticker TEXT NOT NULL,
  trade_date       TEXT NOT NULL,        -- 거래일 'YYYY-MM-DD'
  close_adj        REAL,                 -- 분할·배당 조정 종가 (표시·감사용 스냅샷)
  close_raw        REAL,                 -- 미조정 종가 (현재 평가액용)
  ccy              TEXT NOT NULL,        -- 'KRW' | 'USD'
  week52_high      REAL,                 -- 조정가 기준
  week52_low       REAL,                 -- 조정가 기준
  sma200           REAL,                 -- 조정가 기준
  PRIMARY KEY (canonical_ticker, trade_date),
  CHECK (ccy IN ('KRW','USD'))
);
```

> **조정/미조정 사용처(§4, 절대 섞지 말 것):**
> - **현재 평가액 = `close_raw`(미조정)**. `value_base = quantity * close_raw * (fx if US else 1)`.
> - **percentile·52주·200SMA 지표 계산 = `close_adj`(조정)**.
> **조정가 stale 방지(§4 핵심)**: SMA200·52주·percentile은 **캐시된 과거 close_adj를 누적 사용하지 않고**, 매 수집 시 소스에서 조정 윈도우를 통째로 다시 받아 그 자리에서 재계산한다. 즉 `price_snapshot.close_adj`·`week52_*`·`sma200`은 **표시·감사용 스냅샷일 뿐 지표 계산의 원천이 아니다**. metrics.security.④trend는 collect 단계가 fresh 재계산해 넘긴 값을 쓴다.

### 1.4 fundamentals_snapshot — 펀더멘털 캐시 (§4)

```sql
CREATE TABLE IF NOT EXISTS fundamentals_snapshot (
  canonical_ticker TEXT NOT NULL,
  trade_date       TEXT NOT NULL,
  per              REAL,                 -- 제공자 계산값 그대로 (자체 재계산 금지)
  pbr              REAL,
  div_yield        REAL,
  per_pctile_5y    REAL,                 -- NULL 허용(US 정밀도/백필 워밍업)
  pbr_pctile_5y    REAL,                 -- NULL 허용
  report_date      TEXT,                 -- 재무 실제 기준일 (수집일과 분리, 신선도 배지용)
  PRIMARY KEY (canonical_ticker, trade_date)
);
```

> 제공자 계산 PER/PBR/배당만 캐시, **자체 가격×EPS 재계산 금지**(§5).
> `per_pctile_5y IS NULL`(백필 워밍업) → ③valuation은 "5년 percentile 워밍업 중(절대 PER만 표시)" degrade 라벨(G3, §5 degrade).
> **음수/NaN PER(적자)**는 metrics에서 밴드 제외 + "PER 산출 불가(적자)" 라벨(§6). DB는 NULL 또는 음수를 그대로 저장하고 판정은 metrics 레이어.

### 1.5 fx_snapshot — 환율 캐시 (§4, 신규)

```sql
CREATE TABLE IF NOT EXISTS fx_snapshot (
  trade_date TEXT NOT NULL,
  pair       TEXT NOT NULL,             -- 'USDKRW'
  rate       REAL NOT NULL,
  PRIMARY KEY (trade_date, pair)
);
```

> fx도 `MAX(trade_date)` fallback 적용. **fx 결측 시 US 평가액은 '분모 제외'가 아니라 '산출 거부(브리핑 보류)'** — NULL을 분모에서 빼면 KR만 100%로 정규화되는 전역오염이 재발하므로 금지(§4·§13 P0).
> **USD 현금도 fx 의존(G6)**: fx FAIL 시 US 종목 + USD 현금 일괄 보류. USD 비중 > `settings.usd_cash_gate_threshold`이면 1층 자산배분 전체 보류.

### 1.6 news_snapshot — 뉴스 헤드라인 캐시 (§4)

```sql
CREATE TABLE IF NOT EXISTS news_snapshot (
  canonical_ticker TEXT NOT NULL,
  trade_date       TEXT NOT NULL,
  url              TEXT NOT NULL,        -- PK 포함해 중복 차단
  title            TEXT NOT NULL,
  source           TEXT,
  PRIMARY KEY (canonical_ticker, trade_date, url)
);
```

> 헤드라인+링크만 저장, **본문 없음**(§5). G7 결정: S6 [Claude 호출 1] 입력 dict에 종목별 `headlines: list[{title,url,source}]` 슬롯으로 연결, LLM은 맥락 참고만(새 사실 생성 금지). 조회: `WHERE canonical_ticker=? AND trade_date=(SELECT MAX(trade_date) ...)` 상위 N건.

### 1.7 market_regime — 시장 레짐 (§4)

```sql
CREATE TABLE IF NOT EXISTS market_regime (
  trade_date  TEXT PRIMARY KEY,
  shiller_cape REAL,                    -- US=CAPE (월단위)
  kospi_pbr    REAL                     -- KR=KOSPI PBR
);
```

> ⑤regime는 `MAX(trade_date)` 1행을 읽어 한 줄 라벨(§6). user_id 불필요(전 유저 공유 거시지표) — SaaS에서도 공유 가능하나 일관성 위해 멀티유저 마이그레이션 시 user_id 추가 검토(§4 멀티유저).

### 1.8 collect_run — 수집 실행 기록 (§4, 신선도 게이트 핵심)

```sql
CREATE TABLE IF NOT EXISTS collect_run (
  trade_date      TEXT NOT NULL,
  market          TEXT NOT NULL,        -- 'KR' | 'US' | 'FX'
  status          TEXT NOT NULL,        -- 'OK'|'PARTIAL'|'FAIL'|'BACKFILL'|'OK_HOLIDAY'
  n_ok            INTEGER NOT NULL DEFAULT 0,
  n_fail          INTEGER NOT NULL DEFAULT 0,
  missing_tickers TEXT,                 -- JSON 배열 문자열 '["AAPL","005930"]'
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (trade_date, market),
  CHECK (market IN ('KR','US','FX')),
  CHECK (status IN ('OK','PARTIAL','FAIL','BACKFILL','OK_HOLIDAY'))
);
```

> **OK 판정 = '예외 안 남'이 아니라 '데이터 실재'(행수>0 + 최신일자 일치)**. Stooq 빈 CSV 등 조용한 실패를 OK로 오인 금지(§4·§5).
> **상태 의미**: `BACKFILL`=신규편입/시계열 워밍업(n_fail과 구분), `OK_HOLIDAY`=거래일 아님(calendar.py 판정, 신선도 배너 오작동 방지).
> **게이트 차단은 `FAIL`일 때만**(§7): FX FAIL→US 전체 보류, US FAIL→US 종목만 제외+KR 정상, KR·US·FX 모두 미갱신→생성 거부. BACKFILL/OK_HOLIDAY는 정상 진행+라벨.

### 1.9 briefing — 생성된 브리핑 (§4, 이력 보존)

```sql
CREATE TABLE IF NOT EXISTS briefing (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id       INTEGER NOT NULL DEFAULT 1,
  briefing_date TEXT NOT NULL,          -- 'YYYY-MM-DD'
  content_json  TEXT NOT NULL,          -- BriefingDoc 직렬화 (G11)
  model         TEXT NOT NULL,          -- 예 'claude-sonnet-4-5' (실제 CLI 모델 ID, 하이픈)
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
```

> **date 단독 PK 아님** → 재생성 시 이력 유지(§4). 대시보드는 `오늘 briefing_date 중 MAX(created_at)` 1행 표시(§8).
> `content_json` 내부 = `BriefingDoc` frozen dataclass(정본 §15.2): `securities: list[SecurityCard]`(각 카드에 `canonical_ticker` echo — G2 join 키), `holds_excluded: list[HoldExcluded]`(LLM 미매칭/중복만), `asset_allocation: dict`, `portfolio_comment: dict`, `regime_label: str`, `banner: str|None`, `as_of: dict`, `dca: dict`, `disclaimer: str`. Jinja2 템플릿은 이 DTO만 신뢰.

---

## 2. 인덱스

> PoC 규모(종목 ≤30, 일일 1배치)에서 PK 인덱스로 대부분 충분. 아래는 `MAX(trade_date)` 조회·신선도·브리핑 최신본 조회를 위한 **최소 보강**(과설계 금지).

```sql
-- ① canonical_ticker별 MAX(trade_date) — 시세/펀더 조회 핫패스
--    PK가 (ct, trade_date)라 ct 선두 prefix로 이미 커버됨. 별도 인덱스 불필요.
--    (SQLite는 PK B-tree로 ct=? ORDER BY trade_date DESC LIMIT 1을 효율 처리)

-- ② 브리핑 최신본: 오늘 날짜 중 MAX(created_at)
CREATE INDEX IF NOT EXISTS ix_briefing_user_date
  ON briefing(user_id, briefing_date, created_at DESC);

-- ③ 뉴스 종목별 최신일
--    PK (ct, trade_date, url) 선두 prefix로 커버. 별도 불필요.

-- ④ holdings 유저별 조회 (auto 종목 목록 추출 등)
CREATE INDEX IF NOT EXISTS ix_holdings_user_tracking
  ON holdings(user_id, tracking);

-- ⑤ collect_run 게이트 조회: 시장별 최신 status
--    PK (trade_date, market) — market별 MAX(trade_date)는 풀스캔이지만 행수 극소(일×3 market)라 무시.
```

> 결론: 신규 인덱스는 **②(브리핑 최신본)·④(holdings 필터)** 2개면 충분. price/funda/news는 PK가 핫패스를 커버.

---

## 3. 조회 패턴 (구현자 레퍼런스 쿼리)

### 3.1 canonical_ticker별 MAX(trade_date) — 시세 (S5 입력, §4 조회규칙)

```sql
-- 단일 종목 최신 시세 (fallback이 휴장·실패를 자동 흡수: 새 row를 만들지 않고 '최신 row 사용')
SELECT canonical_ticker, trade_date, close_adj, close_raw, ccy, week52_high, week52_low, sma200
FROM price_snapshot
WHERE canonical_ticker = :ct
ORDER BY trade_date DESC
LIMIT 1;

-- 보유 auto 종목 전체의 최신 시세 (배치) — 상관 서브쿼리
SELECT p.*
FROM price_snapshot p
JOIN (
  SELECT canonical_ticker, MAX(trade_date) AS md
  FROM price_snapshot
  WHERE canonical_ticker IN (/* holdings.auto ct 목록 */)
  GROUP BY canonical_ticker
) m ON p.canonical_ticker = m.canonical_ticker AND p.trade_date = m.md;
```

> **row 0건 종목 처리(G3)**: 위 조인이 0건을 반환하는 종목 = "데이터 준비중 보류". metrics는 이 종목을 **분모 제외가 아니라 비중 미산출·placeholder 카드**로 처리(KeyError/0분모 방지). 코드에서 `holdings ct - returned ct` 차집합으로 보류 종목 식별.

### 3.2 펀더멘털·환율 최신 (동일 패턴)

```sql
SELECT per, pbr, div_yield, per_pctile_5y, pbr_pctile_5y, report_date
FROM fundamentals_snapshot WHERE canonical_ticker = :ct
ORDER BY trade_date DESC LIMIT 1;

SELECT trade_date, rate FROM fx_snapshot
WHERE pair = 'USDKRW' ORDER BY trade_date DESC LIMIT 1;
```

> fx가 0건 또는 최신일이 게이트 기준 미달 → collect_run.FX status로 이미 판정(§1.5·§1.8). metrics는 fx 결측 시 USD 자산 산출 거부(G6).

### 3.3 신선도 배지 입력 (S8, G10·§8)

```sql
-- 시세 기준일 (포트폴리오 최악값 = 가장 오래된 trade_date)
SELECT MIN(md) AS oldest_price_date FROM (
  SELECT canonical_ticker, MAX(trade_date) AS md FROM price_snapshot
  WHERE canonical_ticker IN (/* auto ct */) GROUP BY canonical_ticker
);
-- 펀더 기준일 = report_date (수집일 아님), 종목별 최악값
SELECT MIN(report_date) FROM (
  SELECT canonical_ticker, report_date FROM fundamentals_snapshot f
  WHERE f.trade_date = (SELECT MAX(trade_date) FROM fundamentals_snapshot
                        WHERE canonical_ticker = f.canonical_ticker)
    AND canonical_ticker IN (/* auto ct */)
);
-- 환율 기준일
SELECT MAX(trade_date) FROM fx_snapshot WHERE pair='USDKRW';
```

> 배지 입력 = 시세 `MAX(price_snapshot.trade_date)` vs 오늘 기대 거래일(calendar.py), 펀더 `report_date`, 환율 `MAX(fx_snapshot.trade_date)`. **종목별 최악(최고령)값을 포트폴리오 배지로 집계**(G10·§8). N일 연속 fallback이면 경고 블록.
> ⚠️ **`report_date` NULL 은폐 주의**: `report_date`는 NULL 허용(US 워밍업/DART 미확보)인데 `MIN(report_date)`는 SQLite에서 NULL을 무시한다 → 일부 NULL이면 최악 종목이 집계에서 빠져 신선도가 실제보다 좋게 보일 수 있다. `report_date IS NULL` 종목은 **'워밍업/미확보'로 별도 표시**(배지 `funda_label`에 반영)하고, `Funda.report_date`(04 §4.2)는 `str | None`으로 둔다.

### 3.4 브리핑 최신본 (S8, §8)

```sql
SELECT content_json, model, created_at
FROM briefing
WHERE user_id = :uid AND briefing_date = :today
ORDER BY created_at DESC
LIMIT 1;
```

### 3.5 게이트 판정 (S4, §7)

```sql
-- 시장별 최신 status (오늘 또는 직전 거래일)
SELECT market, status, trade_date FROM collect_run cr
WHERE trade_date = (SELECT MAX(trade_date) FROM collect_run WHERE market = cr.market)
  AND market IN ('KR','US','FX');
```

---

## 4. 캐시 적재 / 백필 운영 (§9·§5)

### 4.1 upsert 패턴 (일일 cron · `collect.py`)

```sql
INSERT INTO price_snapshot (canonical_ticker, trade_date, close_adj, close_raw, ccy, week52_high, week52_low, sma200)
VALUES (:ct, :td, :adj, :raw, :ccy, :hi, :lo, :sma)
ON CONFLICT (canonical_ticker, trade_date) DO UPDATE SET
  close_adj = excluded.close_adj, close_raw = excluded.close_raw,
  week52_high = excluded.week52_high, week52_low = excluded.week52_low, sma200 = excluded.sma200;
```

> 조정가 소급변경(배당/분할) 흡수: collect가 **조정 윈도우 전체를 fresh로 재계산** → 과거 trade_date row의 `close_adj`·`sma200`·`week52_*`도 upsert로 덮어쓴다(§4 stale 방지). `close_raw`(미조정)는 거래일별 불변이라 신규 trade_date만 추가.

fundamentals/fx/news/market_regime도 동일 `ON CONFLICT ... DO UPDATE` upsert. news는 PK에 url 포함이라 동일 url 중복 무시(`DO NOTHING` 가능).

### 4.2 collect_run 기록 (수집 끝 · 시장별)

```python
# 데이터 실재 검증 후 status 결정 (예외 무발생 ≠ OK)
status = "OK" if (n_ok > 0 and latest_date == expected_trade_date) else "PARTIAL"
# 거래일 아님 → "OK_HOLIDAY", 백필 진행 → "BACKFILL", 전건 실패 → "FAIL"
```

```sql
INSERT INTO collect_run (trade_date, market, status, n_ok, n_fail, missing_tickers)
VALUES (:td, :mkt, :status, :n_ok, :n_fail, :missing_json)
ON CONFLICT (trade_date, market) DO UPDATE SET
  status = excluded.status, n_ok = excluded.n_ok, n_fail = excluded.n_fail,
  missing_tickers = excluded.missing_tickers, created_at = datetime('now');
```

### 4.3 초기 백필 (day-0, 정상 cron과 분리 · §9)

- **bulk 1회 실행**(`scripts/run_collect.py --bootstrap`): pykrx/FDR/Stooq가 과거 시계열을 한 번에 반환 → 200일·52주·SMA200 **day-0 즉시 확보**.
- **FMP percentile만 250req/day 한도로 며칠 분할** → 그동안 `per_pctile_5y` NULL + `collect_run.status='BACKFILL'`.
- **백필 완료 판정(G9)**: 모든 auto 종목이 price/funda row 존재 + percentile BACKFILL 해제(`status` OK 전환) → 그 다음 영업일부터 정상 08:00 cron 활성.
- **day-0 첫 브리핑**: row 0건 종목은 보류(§3.1), per_pctile NULL은 degrade 라벨(§1.4), 전역 "초기 데이터 적재중" 배너(G3).

---

## 5. 무결성 제약 요약

| 제약 | 위치 | 막는 것 |
|---|---|---|
| auto 행 = market+ct+quantity NOT NULL | holdings CHECK | 시세 조회 키 누락 → 조용히 틀린 평가액 |
| manual 행 = value_manual+ccy NOT NULL, quantity NULL | holdings CHECK | 현금 행 형식 오류 |
| `ux_holdings_user_ct` 유니크 | holdings 부분 인덱스 | 같은 종목 중복 입력 → 비중 이중계산 |
| ccy/market/status/category enum | 각 테이블 CHECK | 오타 값으로 게이트·통화 분기 실패 |
| PK (ct, trade_date) | price/funda/news | 동일 거래일 중복 row → MAX 조회 모호 |
| PK (trade_date, market) | collect_run | 시장별 게이트 상태 단일성 |
| target_pct 0~100 + 배타(app) | CHECK + POST validation | 합 100% 위반·자동/수동 혼재(G5) |
| FK 없음 (의도) | — | PoC는 holdings↔snapshot을 ct 문자열 join. FK 미설정(종목 삭제 시 캐시 고아 허용 — 재가입 시 시계열 재사용) |

> **G2 join 키 무결성(브리핑↔holdings)**: DB 제약이 아니라 briefing.py 레이어. LLM 응답 SecurityCard의 `canonical_ticker`(식별자 echo)로 holdings 기준 **left-join**, 미매칭/중복 ct는 "처리 실패" 카드. content_json 저장 전 코드가 보장.

---

## 6. user_id 멀티유저 마이그레이션 경로 (§4·§7)

PoC는 user_id=1 고정이나 **컬럼은 day-0부터 존재** → SaaS 전환 시 스키마 변경 최소화.

1. **users 테이블 신설** (SaaS 시점):
   ```sql
   CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE NOT NULL,
                       created_at TEXT NOT NULL DEFAULT (datetime('now')));
   INSERT INTO users (id, email) VALUES (1, '<owner-email>');  -- 기존 데이터 귀속
   ```
2. **FK 추가**: holdings/settings/briefing의 user_id → users(id). SQLite는 `ALTER TABLE ADD CONSTRAINT` 미지원 → 테이블 재생성(`CREATE new → INSERT SELECT → DROP → RENAME`) 마이그레이션 스크립트 필요.
3. **캐시 테이블(price/funda/fx/news/market_regime)은 user_id 무관 공유** 유지 — 시세는 유저 독립. holdings·settings·briefing만 user_id 스코프. 이미 그렇게 설계됨(캐시 테이블에 user_id 없음).
4. **유니크 인덱스**는 이미 `(user_id, market, canonical_ticker)`라 멀티유저 안전.
5. **DB 백엔드 교체**: SQLite → PostgreSQL 전환 시 평문 SQLite 저장 시정(§12 PIPA) + 컬럼/PK 타입은 호환(AUTOINCREMENT→SERIAL, TEXT datetime→timestamptz 검토).

> PoC 단계에서 users 테이블·FK는 **만들지 않는다**(과설계 금지). user_id 컬럼 존재 + 캐시/유저데이터 분리만으로 마이그레이션 경로 확보.

---

## 7. 다른 영역과의 인터페이스 계약

- **collect.py(04 §8)** → 본 스키마에 upsert(§4.1) + collect_run 기록(§4.2). 데이터 실재 검증 후 status 결정.
- **metrics/(04 §9, 알고리즘 정본 §6)** ← `MAX(trade_date)` 조회(§3.1~3.2)만 읽음(쓰기 없음). row 0건 보류·fx 결측 산출거부 규칙 준수. ④trend는 collect가 넘긴 fresh 재계산값 사용(캐시 close_adj 원천 아님).
- **briefing.py(06)** ← metrics dict + news_snapshot 헤드라인. → briefing 테이블에 content_json(BriefingDoc, §15.2) 저장. G2 join 키(SecurityCard.canonical_ticker)는 코드 레이어 무결성.
- **main.py/templates(03-frontend)** → holdings/settings POST(배타·합100% validation), briefing 최신본·신선도 배지 조회(§3.3~3.4).
- **models.py(04 §4.4 = §15.2 정본)** ← 본 스키마 행 ↔ frozen dataclass DTO 매핑(`BriefingDoc`/`SecurityCard`/`HoldExcluded`/`HoldingRow` 등) 정의.
