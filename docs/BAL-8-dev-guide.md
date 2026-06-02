# BAL-8 dev-guide — `app/db.py` 연결·스키마·조회/적재 헬퍼

> SSoT: `TECH-DESIGN.md §15`(최우선) → `docs/05-database.md` → `docs/04-backend.md`.
> 시그니처 정본: `docs/BAL-1-m1a-orchestration.md §2.1` (이 표를 벗어난 새 시그니처 발명 금지).
> 범위: W1 데이터 스파이크. 하위작업 BAL-43(connect+init_schema), BAL-44(latest 조회), 그리고 슬라이스 E2E(BAL-12 DoD)용 최소 upsert 3종. BAL-45=중복, 무시.

---

## 1. 목표 & 배경

### 이슈 요약
`app/db.py`는 현재 W0 스텁(1줄 docstring)이다. BAL-8은 이를 다음 4가지 책임으로 채운다.

1. **`connect()`** — SQLite 연결을 PoC 런타임 규약(WAL·FK·busy_timeout·`Row` factory)에 맞게 연다. (05 §0)
2. **`init_schema()`** — 05 §1.1~1.9 DDL 9개 테이블 전량을 `CREATE TABLE IF NOT EXISTS`로 생성하고, 05 §2 보강 인덱스 ②④를 만들고, 직후 `settings` 기본값을 seed 한다(§15.5). (BAL-43)
3. **`latest_price/latest_funda/latest_fx`** — `canonical_ticker별 MAX(trade_date)` 최신 1행 조회 헬퍼. 휴장·수집실패가 "새 row 미생성 → 최신 row 재사용"으로 자동 흡수되는 핵심 조회 규칙(05 §3). (BAL-44)
4. **`upsert_price/upsert_funda/upsert_fx`** — `ON CONFLICT ... DO UPDATE` 최소 적재 헬퍼. 명시 하위작업엔 없지만 BAL-12 E2E("005930 fetch → upsert → latest_* row 반환")가 요구하므로 BAL-8 범위에 포함(orchestration §2.1 범위 보강 주석).

### W1 슬라이스(BAL-1) 내 역할/의존
- BAL-8은 의존 그래프(orchestration §1)의 **격리된 foundation 3종 중 하나**(의존 없음). BAL-9(tickers)·BAL-10(calendar)과 파일 비중복이라 **Wave-1에서 진짜 3-way 병렬**로 진행된다.
- 하류: BAL-11(`sources/kr.py`)이 만든 OHLCV/Funda를 BAL-12 E2E가 `db.upsert_*`로 적재하고 `db.latest_*`로 되읽어 적재를 증명한다. 즉 BAL-8은 **슬라이스의 영속화 계층(persistence seam)** 이며 통합 게이트의 양 끝(write·read)을 책임진다.
- 이 가이드 범위에서 `app/sources/kr.py`·`collect.py`·metrics·DTO 등 하류 모듈은 건드리지 않는다(§8 Out of scope).

---

## 2. 영향 파일

| 파일 | 동작 | 비고 |
|---|---|---|
| `app/db.py` | **수정**(스텁→구현) | 본 이슈 본체. connect/init_schema/latest_*×3/upsert_*×3 |
| `tests/test_db.py` | **신규** | 본 가이드 §6 테스트 |
| `app/config.py` | **읽기 전용 의존** | `SETTINGS_DEFAULTS`·`DB_PATH` 참조. 변경 불요. ⚠️ **`SETTINGS_DEFAULTS`는 dict가 아니라 `@dataclass(frozen=True) Settings` 인스턴스**(`Settings()` 호출 결과, config.py:38~51). seed 루프는 `dataclasses.asdict(SETTINGS_DEFAULTS).items()`로 순회할 것(`.items()`/`[key]` 직접 호출 금지 — `AttributeError`/`TypeError`). 키집합(7키)·기본값은 §15.5와 정합(확인됨) |
| `tests/conftest.py` | **수정(소규모)** | in-memory DB 픽스처 추가(§6) — 필요 시. 기존 1줄 주석만 있음 |

> `data/`는 `.gitignore` 대상(이미 등록됨). 실 DB 파일을 테스트가 만들지 않도록 §6 픽스처는 `:memory:` 사용.

---

## 3. 구현 단계

### 단계 A — BAL-43-1: `connect()` (05 §0)
05 §0 코드 블록을 정본 그대로 옮긴다. 추가/변형 금지.
```python
def connect(db_path: str = "data/ballast.db") -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn
```
핵심 로직: PRAGMA 3종은 **연결마다** 적용되어야 한다(WAL은 DB 영속이지만 FK·busy_timeout은 connection-scope). `row_factory=Row`로 컬럼명 접근 보장.
- **검증 포인트**: `connect(":memory:")` 후 `conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1`, `PRAGMA busy_timeout == 5000`. (WAL은 `:memory:`에서 `memory`로 보고될 수 있으므로 파일 DB로 별도 확인 — §6 엣지 참조.)

### 단계 B — BAL-43-2: `init_schema()` DDL 전량 (05 §1.1~1.9 + §2 인덱스 ②④)
05 §1.1~1.9의 9개 `CREATE TABLE IF NOT EXISTS`를 **컬럼 순서·타입·CHECK 제약·DEFAULT까지 그대로** 실행한다. 테이블 목록(정본 = 05 §1):
`holdings · settings · price_snapshot · fundamentals_snapshot · fx_snapshot · news_snapshot · market_regime · collect_run · briefing` (총 **9개**).
이어서 05 §2 보강 인덱스 2개만:
```sql
CREATE INDEX IF NOT EXISTS ix_briefing_user_date ON briefing(user_id, briefing_date, created_at DESC);  -- ②
CREATE INDEX IF NOT EXISTS ix_holdings_user_tracking ON holdings(user_id, tracking);                    -- ④
CREATE UNIQUE INDEX IF NOT EXISTS ux_holdings_user_ct ON holdings(user_id, market, canonical_ticker) WHERE canonical_ticker IS NOT NULL;  -- 05 §1.1 동봉
```
> ①③⑤는 PK prefix가 핫패스를 커버하므로 **만들지 않는다**(05 §2 결론, 과설계 금지). `ux_holdings_user_ct`는 05 §1.1에 DDL과 함께 정의된 부분 유니크 인덱스이므로 init_schema에 포함.

구현 권장: DDL은 모듈 상수 `_SCHEMA_SQL: str`(멀티라인)로 두고 `conn.executescript(_SCHEMA_SQL)`로 일괄 실행 → 멱등(`IF NOT EXISTS`)이므로 반복 호출 안전. `executescript`는 암묵 commit을 수행한다.
- **검증 포인트**: `init_schema` 후 `sqlite_master`의 `type='table'` 개수 = 9(`sqlite_sequence` 등 내부 테이블 제외). 동일 conn에 2회 호출해도 예외 없음(멱등).

### 단계 C — BAL-43-3: settings seed (§15.5, init_schema 직후)
init_schema **마지막**에 `settings` 기본값을 seed한다. 정본 키·기본값 = **§15.5**(05 §1.2 표와 동일 키집합이나 §15가 우선).

- **값 출처(중요 — 정정)**: `app/config.py`의 `SETTINGS_DEFAULTS`. 단 이것은 **dict가 아니라 `@dataclass(frozen=True) Settings` 인스턴스**(config.py:51 `SETTINGS_DEFAULTS = Settings()`)다. 따라서 `SETTINGS_DEFAULTS.items()`·`SETTINGS_DEFAULTS[key]` 같은 dict 접근은 **`AttributeError`/`TypeError`로 실패**한다. seed는 `dataclasses.asdict()`로 dict 변환 후 순회하라(필드별 `getattr`도 가능하나 `asdict`가 간결). 필드명 7개는 §15.5의 7키와 자모 단위 일치(`base_currency · monthly_contribution · satellite_limit_pct · rebalance_band_abs · rebalance_band_rel · micro_weight_floor · usd_cash_gate_threshold`) — config.py:42~48 확인됨.
- `settings.value`는 **TEXT NOT NULL**(05 §1.2)이므로 seed 시 각 value를 `str(value)`로 텍스트 변환해 저장(예: `0`→`'0'`, `1.0`→`'1.0'`). 코드 읽을 때 형변환(05 §1.2 "모든 값 TEXT 저장, 코드가 형변환").
- 멱등성: 재호출 시 사용자가 바꾼 값을 덮지 않도록 `INSERT ... ON CONFLICT(user_id, key) DO NOTHING` 사용(seed는 "없을 때만 채움"). `user_id`는 PoC 고정값 `1`로 INSERT.

권장 코드 패턴(dict-아님 전제 교정 반영):
```python
import dataclasses
from app.config import SETTINGS_DEFAULTS  # @dataclass(frozen=True) Settings 인스턴스

def _seed_settings(conn: sqlite3.Connection) -> None:
    for key, value in dataclasses.asdict(SETTINGS_DEFAULTS).items():
        conn.execute(
            "INSERT INTO settings (user_id, key, value) VALUES (1, ?, ?) "
            "ON CONFLICT(user_id, key) DO NOTHING",
            (key, str(value)),
        )
    conn.commit()
```
> ⚠️ `asdict`는 frozen dataclass도 안전하게 평탄화한다(중첩 없는 단순 필드라 1-depth dict 반환). `Settings` 필드가 모두 스칼라(str/int/float)이므로 `str(value)` 변환만으로 TEXT 적재가 완결된다.

- **검증 포인트**: seed 후 `SELECT key, value FROM settings WHERE user_id=1`이 7행, 값은 모두 TEXT. 두 번째 init_schema 호출 후에도 7행 유지(중복·덮어쓰기 없음).

> ⚠️ **§15.5 vs 05 §1.2 타입 표기 차이**(미해결 질문 1): §15.5는 `monthly_contribution: 0`(int), 05 §1.2는 `'0'`(text). 컬럼 제약(TEXT NOT NULL)상 **저장형은 TEXT가 확정**이므로 본문은 `str()` seed로 진행. §15 우선 원칙과 충돌 없음(§15.5는 "기본값"의 논리값, 저장형은 05 컬럼 타입). 논리 기본값 자체(7키·값)는 §15.5 = config.py `Settings` 필드와 정합이므로 그대로 사용.

### 단계 D — BAL-44: 조회 헬퍼 `latest_price/latest_funda/latest_fx` (05 §3.1, §3.2)
05 §3.1/3.2의 단일종목 `ORDER BY trade_date DESC LIMIT 1` 패턴을 그대로 파라미터 바인딩으로 옮긴다.
```python
def latest_price(conn, ct):
    return conn.execute(
        "SELECT canonical_ticker, trade_date, close_adj, close_raw, ccy, "
        "week52_high, week52_low, sma200 FROM price_snapshot "
        "WHERE canonical_ticker = ? ORDER BY trade_date DESC LIMIT 1", (ct,)
    ).fetchone()
```
- `latest_funda`: `SELECT ... FROM fundamentals_snapshot WHERE canonical_ticker=? ORDER BY trade_date DESC LIMIT 1` (05 §3.2). 컬럼: `canonical_ticker, trade_date, per, pbr, div_yield, per_pctile_5y, pbr_pctile_5y, report_date`.
- `latest_fx`: `SELECT trade_date, pair, rate FROM fx_snapshot WHERE pair=? ORDER BY trade_date DESC LIMIT 1` (05 §3.2). 기본 `pair="USDKRW"`.
- 반환: `sqlite3.Row | None`(0건이면 `fetchone()`이 `None`). **0건을 예외로 만들지 않는다** — 보류 판정(G3)은 상위 metrics 레이어 책임.
- SQL injection 방지: 모든 식별자/값은 `?` 바인딩(f-string 금지).
- **검증 포인트**: (1) upsert로 005930 2거래일 적재 → `latest_price`가 **더 최신 trade_date** row 반환. (2) 미존재 ct → `None`. (3) `latest_fx()`가 기본 USDKRW 조회.

### 단계 E — BAL-8 범위 보강: `upsert_price/upsert_funda/upsert_fx` (05 §4.1)
05 §4.1 `INSERT ... ON CONFLICT (PK) DO UPDATE SET ...` 패턴.
```python
def upsert_price(conn, row) -> None:
    conn.execute(
        "INSERT INTO price_snapshot "
        "(canonical_ticker, trade_date, close_adj, close_raw, ccy, week52_high, week52_low, sma200) "
        "VALUES (:canonical_ticker,:trade_date,:close_adj,:close_raw,:ccy,:week52_high,:week52_low,:sma200) "
        "ON CONFLICT (canonical_ticker, trade_date) DO UPDATE SET "
        "close_adj=excluded.close_adj, close_raw=excluded.close_raw, "
        "week52_high=excluded.week52_high, week52_low=excluded.week52_low, sma200=excluded.sma200",
        row,
    )
    conn.commit()
```
- `upsert_funda`: PK `(canonical_ticker, trade_date)`, `DO UPDATE`로 `per/pbr/div_yield/per_pctile_5y/pbr_pctile_5y/report_date` 갱신.
- `upsert_fx`: PK `(trade_date, pair)`, `DO UPDATE SET rate=excluded.rate`.
- **`close_raw`는 거래일별 불변**이지만 `ON CONFLICT`에 포함해도 무해(같은 값 재기록). 05 §4.1 DDL과 동일하게 `excluded.*` 전부 갱신.
- `row` 파라미터 형태: 05 §4.1은 **named bind(`:ct` 등)** 를 쓰므로 본 가이드는 `row`를 **named-param 매핑(dict 또는 dict-like)** 로 가정한다. 단 orchestration §2.1 시그니처는 `row`의 타입을 명시하지 않음 → **미해결 질문 2**(아래 ## 미해결 질문).
- **검증 포인트**: 동일 `(ct, trade_date)` 2회 upsert → 행수 1 유지 + 두 번째 값으로 갱신(멱등·UPSERT 의미). 신규 trade_date upsert → 행 추가.

### 단계 F — `py_compile` + 단위 테스트 그린
편집 후 `python3 -m py_compile app/db.py`(degraded-session 수동 대체, orchestration §4) → `pytest -q tests/test_db.py`.
- **검증 포인트**: §7 DoD 체크리스트 전 항목 통과.

---

## 4. 인터페이스 (정본 = orchestration §2.1, 그대로 구체화)

> 새 시그니처 발명 금지. 아래는 §2.1 시그니처를 파라미터/반환형/예외 수준으로만 구체화한 것이며, §2.1 텍스트와 1:1 대응한다.

```python
import sqlite3

def connect(db_path: str = "data/ballast.db") -> sqlite3.Connection: ...
#   PRAGMA: foreign_keys=ON, journal_mode=WAL, busy_timeout=5000; row_factory=Row (05 §0)
#   예외: 잘못된 경로 → sqlite3.OperationalError 전파(잡지 않음)

def init_schema(conn: sqlite3.Connection) -> None: ...
#   05 §1.1~1.9 DDL 9테이블(CREATE TABLE IF NOT EXISTS) + 05 §2 인덱스 ②④
#   + ux_holdings_user_ct(05 §1.1) + settings seed(§15.5, ON CONFLICT DO NOTHING)
#   seed 값 출처 = app/config.py SETTINGS_DEFAULTS(=Settings() 인스턴스, dict 아님)
#     → dataclasses.asdict(SETTINGS_DEFAULTS).items() 순회 + str(value) 변환 (단계 C)
#   멱등. 반환 None. (BAL-43)

def latest_price(conn: sqlite3.Connection, ct: str) -> sqlite3.Row | None: ...   # 05 §3.1
def latest_funda(conn: sqlite3.Connection, ct: str) -> sqlite3.Row | None: ...   # 05 §3.2
def latest_fx(conn: sqlite3.Connection, pair: str = "USDKRW") -> sqlite3.Row | None: ...  # 05 §3.2
#   (BAL-44) 0건 → None. 예외 없음(보류 판정은 상위 레이어).

# 슬라이스 범위 보강(orchestration §2.1 주석 — BAL-12 DoD가 요구):
def upsert_price(conn: sqlite3.Connection, row) -> None: ...   # 05 §4.1 ON CONFLICT DO UPDATE
def upsert_funda(conn: sqlite3.Connection, row) -> None: ...
def upsert_fx(conn: sqlite3.Connection, row) -> None: ...
#   row = named-param 매핑(가정). 타입 미명시 → 미해결 질문 2.
```

**§2.1과의 정합 확인**:
- `connect`/`init_schema`/`latest_price`/`latest_funda`/`latest_fx`/`upsert_price`/`upsert_funda`/`upsert_fx` — 8개 모두 §2.1과 자모 단위 일치(파라미터명·기본값·반환형).
- `conn` 파라미터는 §2.1에서 타입주석 없이 `conn`으로 표기됨 → 본 가이드는 PEP8/타입주석 규칙(글로벌 coding-style)에 따라 `sqlite3.Connection`으로 좁힌다. 이는 §2.1 의미와 모순 없음(타입 추가일 뿐).
- `init_schema`의 seed 동작은 §2.1 주석("settings seed(§15.5)")의 구체화이며, **값 출처가 dict라는 오해를 제거**해 `asdict` 순회로 못박았다(시그니처 불변, 내부 구현 정정).

---

## 5. 엣지 & 리스크

| # | 상황 | 영향 | 대응 (본 모듈) |
|---|---|---|---|
| E1 | **조회 0건**(휴장·미적재·신규편입) | `latest_*`가 None | 예외 금지, `None` 반환. 보류/placeholder는 상위 metrics(G3, 05 §3.1). db.py는 None만 정직하게 전달 |
| E2 | **빈 DF/빈 CSV upsert 시도** | "조용한 실패"가 OK처럼 보임 | db.py 범위 아님 — `validate_response`/`EmptyResponseError`는 BAL-12. db.py는 들어온 row만 적재. **단, upsert 호출 전 빈 응답 차단은 caller(kr.py) 책임**임을 주석 명시 |
| E3 | **`per_pctile_5y` NULL**(백필 워밍업) | `latest_funda` row에 NULL 컬럼 | 정상 — 컬럼 NULL 허용(05 §1.4). degrade 라벨(G3)은 metrics. db.py는 NULL 보존 |
| E4 | **`report_date` NULL 은폐**(05 §3.3 ⚠️) | `MIN(report_date)`가 NULL 무시 | 본 이슈 `latest_funda`는 단일종목 단순 조회라 미해당. 포트폴리오 집계(MIN) 쿼리는 W2+ 신선도 로직 — Out of scope. row의 `report_date`는 `str|None` 그대로 반환 |
| E5 | **조정가 stale**(배당/분할 소급) | 과거 `close_adj`/`sma200` 갱신 필요 | `upsert_price`의 `ON CONFLICT DO UPDATE`가 `close_adj/sma200/week52_*`를 `excluded.*`로 덮음(05 §4.1) → 동일 trade_date 재upsert 시 fresh 재계산값으로 갱신. **윈도우 통째 재계산은 caller(kr.py) 책임**, db.py는 덮어쓰기 가능성만 보장 |
| E6 | **음수/NaN PER(적자)** | DB에 음수/NULL 그대로 | 05 §1.4: DB는 NULL/음수 그대로 저장, 판정은 metrics. upsert가 값 변형하지 않음 |
| E7 | **WAL 동시성·락** | 배치 write 중 대시보드 read | `busy_timeout=5000`로 5s 대기(05 §0). db.py는 PRAGMA만 보장, 트랜잭션 경계는 caller |
| E8 | **CHECK 제약 위반 upsert**(잘못된 ccy/status 등) | `sqlite3.IntegrityError` | 전파(삼키지 않음) — "조용히 틀린 값 차단"(05 원칙). 본 이슈 upsert 대상(price/funda/fx)엔 ccy CHECK만 관여 |
| E9 | **seed 재실행이 사용자 설정 덮어씀** | 사용자 변경 유실 | `ON CONFLICT DO NOTHING`으로 방지(단계 C) |
| E10 | **테스트가 실 DB(`data/ballast.db`) 오염** | 사이드이펙트 | 픽스처는 `:memory:` 또는 `tmp_path`. 절대 기본 경로 사용 금지 |
| E11 | **seed 출처를 dict로 오인** | `SETTINGS_DEFAULTS.items()`/`[key]` → `AttributeError`/`TypeError` (구현 즉시 깨짐) | `SETTINGS_DEFAULTS`는 `Settings()` frozen dataclass 인스턴스(config.py:51). **`dataclasses.asdict(SETTINGS_DEFAULTS).items()`** 로 순회(단계 C). dict 접근 패턴 금지 |

---

## 6. 테스트 계획

**파일: `tests/test_db.py`** (pytest, `@pytest.mark.unit` — db.py는 순수 로컬 SQLite, 외부 네트워크 없음 → 전부 단위 테스트. 모킹 불필요).

픽스처(파일 상단 또는 conftest):
```python
@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.init_schema(c)
    yield c
    c.close()
```

| 테스트명 | 검증 대상 | 핵심 단언 |
|---|---|---|
| `test_connect_pragmas` | connect (단계 A) | `PRAGMA foreign_keys==1`, `PRAGMA busy_timeout==5000`, `row_factory is sqlite3.Row` |
| `test_connect_wal_on_file_db` | WAL(파일 DB) | `tmp_path` DB로 `connect` 후 `PRAGMA journal_mode`가 `'wal'` (※ `:memory:`는 wal 불가 → 파일로 검증) |
| `test_init_schema_creates_9_tables` | init_schema (단계 B) | `sqlite_master` table 9개 정확히. 이름집합 == {holdings, settings, price_snapshot, fundamentals_snapshot, fx_snapshot, news_snapshot, market_regime, collect_run, briefing} |
| `test_init_schema_indexes` | 인덱스 ②④+유니크 | `ix_briefing_user_date`, `ix_holdings_user_tracking`, `ux_holdings_user_ct` 존재 |
| `test_init_schema_idempotent` | 멱등 (단계 B) | `init_schema(conn)` 2회 호출 무예외 + 테이블·seed 행수 불변 |
| `test_settings_seed` | seed (단계 C, §15.5) | `settings` 7행, 키집합 == §15.5 7키(== `dataclasses.asdict(SETTINGS_DEFAULTS)` 키), 값 전부 `str`, `monthly_contribution=='0'` |
| `test_settings_seed_source_is_dataclass` | seed 출처 (E11) | `SETTINGS_DEFAULTS`가 dict 아님 확인 + `dataclasses.asdict(SETTINGS_DEFAULTS)` 키집합 == DB seed 키집합 (구현이 dict 접근으로 회귀하지 않도록 가드) |
| `test_settings_seed_no_override` | seed 멱등 | 사용자가 `base_currency='USD'`로 수정 후 init_schema 재호출 → 여전히 `'USD'`(DO NOTHING) |
| `test_holdings_check_auto_keys` | CHECK 제약 (E8) | `tracking='auto'`인데 `canonical_ticker NULL` insert → `IntegrityError` |
| `test_holdings_check_ccy_enum` | CHECK enum | `ccy='JPY'` insert → `IntegrityError` |
| `test_upsert_price_insert_then_update` | upsert (단계 E, E5) | 동일 `(ct, trade_date)` 2회 upsert → 행 1개, 두 번째 `close_adj`로 갱신 |
| `test_upsert_price_new_date_appends` | upsert | 신규 trade_date upsert → 행 2개 |
| `test_upsert_funda_null_pctile` | upsert + NULL (E3) | `per_pctile_5y=None` upsert 성공, latest_funda가 NULL 보존 |
| `test_upsert_fx_default_pair` | upsert_fx | USDKRW upsert → latest_fx 기본인자 조회로 동일 row |
| `test_latest_price_returns_max_date` | latest (단계 D) | 2거래일 적재 → 더 최신 trade_date row 반환 |
| `test_latest_price_none_when_empty` | latest 0건 (E1) | 미존재 ct → `None` |
| `test_e2e_upsert_then_latest` | 슬라이스 E2E 축소판 | 005930 price/funda upsert dict → `latest_price/funda`가 실수치 row(BAL-12 DoD §5의 db 부분 사전검증) |

> 네트워크 의존(pykrx/FDR/네이버)은 **본 모듈에 없음** → 모킹 대상 없음. 어댑터 계약 테스트는 BAL-11/12 소관.

---

## 7. DoD (Definition of Done)

로드맵 08 Week1 + orchestration §5에서 **db.py에 해당하는 항목만** 인용:

- [ ] (08 W1 작업) `db.py`: `connect()`(WAL·FK·busy_timeout, 05 §0) + `init_schema()`(05 §1 DDL 전체) + `MAX(trade_date)` 조회 헬퍼 `latest_price/funda/fx`(05 §3) 구현.
- [ ] (orchestration §3 W-1 게이트) `init_schema` 후 테이블 생성 + connect PRAGMA 적용 확인. ※ §3은 "7테이블"로 표기하나 05 §1은 **9테이블**이 정본 → 9테이블로 검증(미해결 질문 3).
- [ ] (orchestration §5 / 08 W1 DoD) `db.upsert_*` 적재 후 `latest_price(conn,'005930')`가 row 반환.
- [ ] settings seed 7키가 §15.5 기본값으로 채워짐(init_schema 직후, **출처 = `dataclasses.asdict(SETTINGS_DEFAULTS)`, dict 접근 아님**), 재실행 시 사용자값 비파괴.
- [ ] (orchestration §5) `pytest -q` green, 편집 파일 `py_compile` 통과(degraded-session 수동 대체, §4).
- [ ] CHECK 제약(auto 키 NOT NULL·ccy/category enum 등)이 위반 insert를 `IntegrityError`로 차단.
- [ ] 코딩 규칙 준수: PEP8 + 전 함수 타입주석 + (해당 시) frozen dataclass. `print()` 미사용.

> ⚠️ `validate_response`/`EmptyResponseError`(orchestration §5의 빈응답 항목)는 **BAL-12 범위**(위치: `app/sources/__init__.py`) — db.py DoD 아님.

---

## 8. Out of scope (W1 / BAL-8 아님)

- **`collect.py`** 전체 upsert·백필·`collect_run` 로깅 — W2(orchestration §2.1 주석: "전체 upsert/collect_run 로깅은 W2 collect.py"). 본 이슈는 `collect_run` 테이블 **DDL만** 생성, upsert 헬퍼는 미작성.
- **`upsert_holdings/settings/news/market_regime/briefing`** — W2+. 본 이슈 upsert는 price/funda/fx **3종만**. (settings는 seed만, upsert 헬퍼 아님.)
- **신선도 배지 집계 쿼리**(05 §3.3 MIN/MAX 포트폴리오 집계), **게이트 판정 쿼리**(05 §3.5), **브리핑 최신본 조회**(05 §3.4) — 소비자(S4/S8/main.py) 레이어, W2+.
- **`validate_response`/`EmptyResponseError`** — BAL-12.
- **`models.py` DTO**(OHLCV/Funda/FxRate frozen dataclass) — BAL-11 가이드 소관(orchestration §2.4). db.py는 `sqlite3.Row`/dict로만 다룸.
- **US/FX/regime 어댑터, metrics 계산, LLM/Card DTO, 프론트, 손익/수익률(G8)** — orchestration §6.
- **users 테이블·FK 추가**(멀티유저 마이그레이션) — 05 §6 "PoC 단계에서 만들지 않는다".

---

## 미해결 질문
(아래는 §15/§2.1/05 간 명시 불일치 또는 미정의 — 본문에 임의 가정을 주입하지 않고 모았다.)

1. **settings seed 값 타입**: §15.5는 `monthly_contribution=0`(int)·`micro_weight_floor=1.0`(float) 등 논리 타입, 05 §1.2는 `'0'`(text). `settings.value`가 `TEXT NOT NULL`이라 저장형은 TEXT 확정이므로 본 가이드는 `str()` seed로 진행했다. 의도 확인만 필요(저장 TEXT + 코드 형변환이 맞는지). ※ 값 출처(`SETTINGS_DEFAULTS`=`Settings()` frozen dataclass)와 키집합·논리 기본값은 §15.5와 정합함을 코드(config.py:38~51)로 확인 완료 — 이 항목은 더 이상 블로커 아님, 저장형 의도 확인만.
2. **`upsert_*(conn, row)`의 `row` 타입**: orchestration §2.1은 `row` 타입을 명시하지 않음. 05 §4.1은 named bind(`:ct`)를 사용하므로 본 가이드는 **dict(또는 dict-like 매핑)** 로 가정했다. 그러나 BAL-11 반환형은 `OHLCV`/`Funda` frozen dataclass(orchestration §2.4)다 → upsert가 dataclass를 받을지(`asdict()` 변환을 db.py가 할지 caller가 할지), 아니면 dict를 받을지 확정 필요. (E2E caller가 누가 변환할지의 책임 경계.)
3. **테이블 개수 표기 불일치**: orchestration §3 W-1 게이트는 "init_schema 후 **7테이블**"이라 적었으나 05 §1.1~1.9 DDL은 **9테이블**(holdings·settings·price_snapshot·fundamentals_snapshot·fx_snapshot·news_snapshot·market_regime·collect_run·briefing)이다. SSoT 우선순위(05 > orchestration 요약)에 따라 9를 채택했으나, §3 문구가 오기인지 확인 필요.
4. **upsert 트랜잭션 경계**: 단계 E는 각 upsert 끝에 `conn.commit()`을 가정했다. 그러나 배치(W2 collect.py)에서 다건을 한 트랜잭션으로 묶고 싶다면 헬퍼 내부 commit이 방해가 된다. §2.1/05는 commit 위치를 명시하지 않음 → 헬퍼가 commit할지(자기완결) caller가 할지 확정 필요.
