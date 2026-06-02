# BAL-12 dev-guide — validate: 빈 응답 가드 + 005930 적재 E2E 증명

> SSoT 우선순위: `TECH-DESIGN.md §15`(Contract SoT) > `docs/05-database.md` / `docs/04-backend.md`.
> 시그니처 정본: `docs/BAL-1-m1a-orchestration.md §2` seam 표. (이 가이드는 §2 시그니처를 발명 없이 그대로 가져옴. §2와 다른 문서가 충돌하면 본 가이드는 §2를 따르고 그 사실을 `## 미해결 질문`에 적시한다.)
> 범위: **W1만**. Wave 3(순차) 최종 통합 이슈 — BAL-8·9·10·11 전부에 의존.

---

## 1. 목표 & 배경

### 이슈 요약
BAL-12는 W1/M1a 데이터 스파이크의 **통합 증명(integration)** 이슈다. 두 가지를 한다.

1. **빈 응답 가드**: 소스 어댑터가 빈 DataFrame / 빈 CSV / 0행을 돌려줬을 때 이를 "조용한 성공(OK)"으로 오인하지 않고 `EmptyResponseError`로 명시적으로 올리는 안전장치(`EmptyResponseError` + `validate_response`)를 `app/sources/__init__.py`에 둔다.
2. **005930 적재 E2E**: `KrSource().ohlcv('005930')` / `fundamentals('005930')` → `db.upsert_price/upsert_funda` → `db.latest_price/latest_funda('005930')`가 **실수치 row**를 반환하는 끝-끝 경로를 스모크로 증명한다.

핵심 원칙(`05 §1.8`): **OK 판정은 "예외 안 남"이 아니라 "데이터 실재"(행수>0 + 최신일자 일치)**. Stooq/pykrx의 빈 응답을 OK로 받아들이면 비중·평가액이 조용히 틀어진다 — 이 회귀를 막는 게 BAL-12 가드의 존재 이유다.

### W1 슬라이스(BAL-1) 내 역할/의존
- DAG상 BAL-12는 **integration(전부 의존)** 노드: `BAL-8(db) · BAL-9(tickers) · BAL-10(calendar) · BAL-11(sources.kr)`가 모두 슬라이스 브랜치에 커밋된 뒤 마지막에 진입(`§3 Wave W-3, 순차`).
- 산출 게이트(`§3 W-3 DoD 요약`): `validate_response`가 빈응답→`EmptyResponseError` / 005930 fetch→upsert→`latest_*` row / `tests/test_tickers.py` green.
- 본 이슈는 새 도메인 로직을 거의 만들지 않는다. 8~11이 내놓은 seam을 **조립·검증**하는 얇은 통합 레이어 + 가드 함수 1개 + 예외 1개 + 테스트다.

---

## 2. 영향 파일

| 구분 | 경로 | 내용 |
|---|---|---|
| **수정(스텁→구현)** | `app/sources/__init__.py` | `EmptyResponseError` + `validate_response` 추가 (현재 1줄 docstring만 존재) |
| **생성** | `tests/test_tickers.py` | `to_source` 변환표 전 케이스 단위테스트 (BAL-9 순수계산 검증, W-3 DoD 명시 항목) |
| **생성** | `tests/test_validate.py` | `validate_response`/`EmptyResponseError` 단위테스트 (순수계산) |
| **생성** | `tests/test_e2e_kr_005930.py` | 005930 fetch→upsert→latest 적재 E2E 스모크 (어댑터 모킹 + 실 SQLite) |

> ⚠️ **임포터 측 수정은 BAL-12 범위 밖**: `app/sources/kr.py`의 `from app.sources import validate_response` 사용은 BAL-11(`§2.5` "내부: ... validate_response")의 책임이다. BAL-12는 가드를 **제공**만 하고, kr.py가 이미 그 시그니처로 호출하도록 구현되어 있어야 한다. 호출 시그니처가 어긋나면 `## 미해결 질문`의 드리프트 이슈로 즉시 에스컬레이트(임의로 kr.py를 고치지 말 것 — 슬라이스 계약 위반).
> 참고: `app/collect.py`(W2)도 `validate_response`를 부르지만 **W1 범위 밖**이라 본 이슈에서 건드리지 않는다.

---

## 3. 구현 단계

자체 분해(하위작업 없음). 순서는 의존 역순(가드 먼저 → 순수계산 테스트 → E2E).

### 단계 1 — `EmptyResponseError` + `validate_response` (`app/sources/__init__.py`)
- 위치는 `§2.6`이 제안한 `app/sources/__init__.py`. kr.py/us.py/fx.py가 패키지 루트에서 임포트하므로 순환참조 없는 최적 위치.
- `EmptyResponseError(Exception)` 정의 — 빈 응답 전용 마커 예외.
- `validate_response`는 `§2.6` 시그니처 `validate_response(df_or_obj, *, context: str) -> None`를 정본으로 구현(상세 `## 4`). 빈 응답이면 `EmptyResponseError`, 정상이면 `None`(부작용 없음).
- **검증 포인트**: `python3 -m py_compile app/sources/__init__.py` 통과. `from app.sources import validate_response, EmptyResponseError` 임포트 성공.

### 단계 2 — `tests/test_tickers.py` (BAL-9 변환표)
- `docs/04-backend.md §5.1` 변환표(검증 가능 케이스)를 그대로 테스트 케이스로 박는다. `005930→005930.KS`, `BRK.B→BRK-B`(`§2.2` 예시) 포함.
- `to_source` 정확한 시그니처는 `BAL-9` 구현(`§2.2`)을 정본으로 호출. (시그니처 충돌 가능성은 `## 미해결 질문` 참고 — 발명 금지.)
- **검증 포인트**: `pytest tests/test_tickers.py -q` green. W-3 DoD "to_source 변환표 전 케이스 통과" 충족.

### 단계 3 — `tests/test_validate.py` (가드 단위)
- 빈 응답 → `EmptyResponseError` raise / 정상 응답 → 통과(예외 없음) 두 분기를 못박는다.
- 순수계산이므로 네트워크 모킹 불필요(`08 §3` 횡단 규율: 순수 계산은 단위테스트 필수).
- **검증 포인트**: `pytest tests/test_validate.py -q` green. W-1/W-3 DoD "빈 응답을 `EmptyResponseError`로 올림" 충족.

### 단계 4 — `tests/test_e2e_kr_005930.py` (적재 E2E)
- 흐름(`§2.6` E2E 계약): `KrSource().ohlcv/fundamentals('005930')` → `db.upsert_price/upsert_funda` → `db.latest_price/latest_funda(conn,'005930')`가 실수치 row 반환.
- DB는 **실 SQLite**(`tmp_path / "ballast.db"` 또는 `:memory:`)에 `db.connect` + `db.init_schema`로 스키마 구축 — 적재 경로를 진짜로 통과시켜야 "데이터 실재"를 증명한다.
- 외부 네트워크(pykrx/FDR/네이버)는 **모킹**(프로젝트 룰: 외부 네트워크 의존은 테스트에서 모킹). `KrSource.ohlcv`/`fundamentals`가 결정적 `OHLCV`/`Funda`를 반환하도록 패치.
- assert: `latest_price` row의 `close_raw`/`week52_high`/`sma200`이 모킹한 실수치와 일치, `latest_funda` row의 `per`/`pbr`/`per_pctile_5y`가 일치.
- **검증 포인트**: `pytest tests/test_e2e_kr_005930.py -q` green. W-3 DoD "005930 fetch→upsert→latest_* row" 충족.

### 단계 5 — 통합 게이트 확인(수동 스모크)
- `08 Week1 DoD`의 라이브 명령은 실 네트워크 의존이라 **수동 스모크**(테스트 자동화 아님, `08 §3` "어댑터·LLM = 계약 테스트 + 수동 스모크"):
  - `python -c "from app.sources.kr import KrSource; print(KrSource().ohlcv('005930'))"` → close_raw·52주·sma200 실수치.
  - `fundamentals('005930')` → PER/PBR/배당 + per_pctile_5y.
- **검증 포인트**: `pytest -q` 전체 green + 편집 파일 `py_compile` 통과(`§5`, degraded-session에서 PostToolUse 훅 부재 → 수동 실행).

---

## 4. 인터페이스

> 시그니처 정본 = `docs/BAL-1-m1a-orchestration.md §2.6`. 아래는 §2.6을 그대로 가져와 구체화한 것이며, 새 시그니처는 발명하지 않았다. **§2.6과 다른 문서(`04 §7.1`)의 `validate_response` 시그니처가 충돌**한다 — 본 가이드는 규칙에 따라 §2.6을 정본으로 채택하고, 충돌 사실을 `## 미해결 질문 Q1`에 적시한다.

### 4.1 `app/sources/__init__.py` (BAL-12 — 본 이슈가 생성)

```python
class EmptyResponseError(Exception):
    """소스가 빈 응답(0행/빈 DF/None)을 반환 — '조용한 실패'를 OK로 오인 금지 (05 §1.8)."""


def validate_response(df_or_obj, *, context: str) -> None:
    """소스 응답이 '데이터 실재'인지 검증. 빈 응답이면 EmptyResponseError, 정상이면 None(부작용 없음).

    Parameters
    ----------
    df_or_obj : pandas.DataFrame | list | object | None
        어댑터가 받은 원천 응답. 빈 여부 판정 대상.
    context : str (keyword-only)
        실패 메시지·로깅용 식별자 (예: 'kr.ohlcv 005930').

    Raises
    ------
    EmptyResponseError
        df_or_obj가 비었을 때(05 §1.8: OK=데이터 실재, 빈 CSV OK 오인 금지).
    """
```
- **반환형**: `None`(가드 함수, 통과 시 무반환).
- **예외**: `EmptyResponseError` (빈 응답일 때만).
- **"빈" 판정 범위**(§2.6 "빈 응답을 OK로 오인 금지"): `None`, 길이 0인 시퀀스/DataFrame(`.empty`). 구체 판정 규칙은 `## 미해결 질문 Q2` 참조 — 본문에 임의 규칙을 주입하지 않는다.

### 4.2 의존 seam (BAL-8/9/11 — 본 이슈가 소비, 시그니처는 각 이슈가 정본)

```python
# BAL-9 app/tickers.py (§2.2) — test_tickers.py가 호출
def to_source(canonical: str, market: str | None = None) -> str   # 005930→005930.KS, BRK.B→BRK-B

# BAL-11 app/sources/kr.py (§2.5) — E2E가 호출
class KrSource:
    def ohlcv(self, ct: str) -> OHLCV          # close_raw/close_adj/52주/sma200 (05 §1.3)
    def fundamentals(self, ct: str) -> Funda   # PER/PBR/배당 → per_pctile_5y

# BAL-8 app/db.py (§2.1) — E2E가 호출
def connect(db_path: str = "data/ballast.db") -> sqlite3.Connection
def init_schema(conn) -> None
def upsert_price(conn, row) -> None            # 05 §4.1 ON CONFLICT DO UPDATE
def upsert_funda(conn, row) -> None
def latest_price(conn, ct: str) -> sqlite3.Row | None   # 05 §3.1
def latest_funda(conn, ct: str) -> sqlite3.Row | None   # 05 §3.2
```
- `OHLCV`/`Funda` DTO 필드는 `§2.4`(= `05 §1.3/1.4` 컬럼 정합)를 정본으로 한다.
- `upsert_price/upsert_funda`의 인자 `row`가 `OHLCV`/`Funda` frozen dataclass인지 dict/tuple인지의 어댑테이션 책임은 BAL-8에 있다 — `## 미해결 질문 Q3` 참조.

---

## 5. 엣지 & 리스크

| 엣지/리스크 | 출처 | 대응 |
|---|---|---|
| pykrx/FDR가 특정 종목·기간 **빈 DF** 반환 | `08 W1 리스크`, `05 §1.8` | `validate_response`가 0행을 `EmptyResponseError`로 승격 → OK 오인 차단. BAL-11이 `@retry(3)` + 가드 호출(§2.5). |
| **백필 워밍업**(`per_pctile_5y` NULL) | `05 §1.4`, `08 W1 리스크` | E2E는 `per_pctile_5y`가 **NULL이어도 통과**해야 함(NULL 허용 컬럼). 가드는 percentile NULL을 "빈 응답"으로 오판하면 안 됨 — `Funda` 객체 자체가 실재하면 OK. |
| **휴장일**(OK_HOLIDAY) | `05 §1.8` | W1 BAL-12 가드는 "행수 0"만 본다. 휴장/기대일 불일치 판정은 calendar.expected_trade_date 기반이며 그 강제 위치는 `## 미해결 질문 Q1`(가드가 latest/expected를 받느냐)에 종속. E2E는 모킹 데이터라 휴장 영향 없음. |
| **NULL percentile를 빈 응답으로 오인** | 위 + `05 §1.4` | 가드 판정 대상은 **컨테이너의 빈 여부**이지 개별 필드 NULL이 아님(Q2). `Funda(per_pctile_5y=None)`는 정상. |
| **조정가 stale**(close_adj 누적 사용) | `05 §1.3`, `04 §7.2` | W1 BAL-12 범위 밖(fresh 재계산은 BAL-11 `ohlcv`의 책임, `§2.5`). E2E는 BAL-11이 넘긴 값을 그대로 적재·재조회만 검증. |
| **빈 CSV가 예외 없이 흘러감** | `05 §1.8`, `04 §7.1` | 핵심 회귀. test_validate.py에 "빈 입력→raise" 케이스로 고정. |
| 같은 거래일 중복 적재 | `05 §4.1` PK(ct, trade_date) | upsert `ON CONFLICT DO UPDATE`(BAL-8). E2E를 두 번 돌려도 멱등 — 같은 row 1건 유지 검증 가능(선택). |
| **degraded-session**: PostToolUse `py_compile`/리뷰 훅 미로드 | `BAL-1 §4` | 편집 후 `python3 -m py_compile` 수동 실행, 커밋 전 aggregate-verdict 수동 확인. |

---

## 6. 테스트 계획

> 순수계산=단위 필수, 어댑터=모킹/계약(`08 §3`, 프로젝트 룰). pytest + `@pytest.mark.unit`/`integration` 마커(testing.md).

### `tests/test_validate.py` (단위 — 순수계산)
| 테스트명 | 검증 |
|---|---|
| `test_validate_raises_on_empty_dataframe` | 빈 `pd.DataFrame()` → `EmptyResponseError` |
| `test_validate_raises_on_none` | `None` 입력 → `EmptyResponseError` |
| `test_validate_raises_on_empty_list` | `[]` → `EmptyResponseError` |
| `test_validate_passes_on_nonempty` | 1행 이상 DF/list → 예외 없음, 반환 `None` |
| `test_empty_response_error_is_exception` | `EmptyResponseError`가 `Exception` 서브클래스 |

> 정확한 "빈" 판정 케이스 집합은 `## 미해결 질문 Q2` 확정 후 케이스 가감. 위는 §2.6 의미(빈→raise)에서 모순 없이 도출되는 최소 집합.

### `tests/test_tickers.py` (단위 — 순수계산, W-3 DoD 명시)
| 테스트명 | 검증 (출처 `04 §5.1` 표) |
|---|---|
| `test_to_source_kr_samsung` | `005930`(KR) → `005930.KS` |
| `test_to_source_us_voo` | `VOO`(US) → `VOO` |
| `test_to_source_us_brk_b` | `BRK.B`(US) → `BRK-B` |

> `to_source` 정확한 파라미터(§2.2 `(canonical, market)` vs `04 §5.1` `(source, ct, market)`)는 `## 미해결 질문 Q4`. 본 가이드는 §2.2를 정본으로 작성하되, BAL-9 실제 구현 시그니처에 맞춰 호출. KOSDAQ `.KQ`/stooq 변형은 W1 005930 슬라이스 밖이라 케이스 생략(끌려가지 말 것).

### `tests/test_e2e_kr_005930.py` (integration — 모킹 + 실 SQLite)
| 테스트명 | 검증 |
|---|---|
| `test_ohlcv_upsert_latest_roundtrip` | `KrSource.ohlcv` 모킹 → `upsert_price` → `latest_price(conn,'005930')` row의 close_raw/week52_high/sma200 == 모킹값 |
| `test_fundamentals_upsert_latest_roundtrip` | `KrSource.fundamentals` 모킹 → `upsert_funda` → `latest_funda(conn,'005930')` row의 per/pbr/per_pctile_5y == 모킹값(percentile NULL 케이스 포함) |
| `test_latest_returns_none_when_empty`(선택) | 적재 전 `latest_price` → `None`(0건 보류 경로, `05 §3.1` G3) |

- 픽스처: `tmp_path` 기반 SQLite + `db.init_schema`. `monkeypatch`로 `KrSource.ohlcv`/`fundamentals` 또는 그 내부 pykrx/FDR 호출을 패치.
- **네트워크 0회** 보장(룰 준수). 모킹 객체는 `§2.4` `OHLCV`/`Funda` 필드 전량 채움.

---

## 7. DoD (체크리스트)

`08 Week1 DoD` + `BAL-1 §5`(W1 통합 DoD)에서 BAL-12 해당 항목 인용:

- [ ] (`§5`) `validate_response`가 빈 응답을 `EmptyResponseError`로 올림 (빈 CSV를 OK로 오인 안 함, `05 §1.8`)
- [ ] (`§5` / `08 W1 DoD`) `db.upsert_*` 적재 후 `latest_price(conn,'005930')` row 반환 — close_raw·52주·sma200 실수치
- [ ] (`08 W1 DoD`) `fundamentals('005930')` 적재 → `latest_funda` PER/PBR/배당 + per_pctile_5y(5년 백필, NULL 허용)
- [ ] (`§5` / `08 W1 DoD`) `tests/test_tickers.py`: to_source 변환표 전 케이스 통과
- [ ] (`§5`) `pytest -q` green, 편집 파일 `py_compile` 통과
- [ ] (`08 W1 DoD` 수동 스모크) `python -c "from app.sources.kr import KrSource; print(KrSource().ohlcv('005930'))"` → 실수치 출력
- [ ] (`BAL-1 §4`) degraded-session 수동 게이트: 편집 후 `py_compile` 직접 실행 + 커밋 전 aggregate-verdict 확인

---

## 8. Out of scope (W1 아님 — 끌려가지 말 것)

`BAL-1 §6` / `08 §4`·`§W2~` 인용:

- **US/FX/regime 어댑터** (`sources/us.py`·`fx.py`·`regime.py` US 절반) — W2.
- **`collect.py` 배치·백필**: `run_collect`/`_status_of`/`collect_run` upsert/`missing_tickers` JSON/`TokenBucket`/`OK_HOLIDAY`·`PARTIAL` 분기 판정 — W2. (BAL-12 가드는 collect가 쓰지만 collect 자체는 안 만듦.)
- **metrics 계산**(통화정규화·5/25·valuation·trend·regime) — W3.
- **LLM/Card DTO**(`SecurityCard`·`BriefingDoc`·`SecurityLLMOut`·`HoldExcluded` 등 §15.2 LLM·렌더 DTO) — W3.
- **프론트엔드**(templates/static) — W5.
- **손익/수익률**(G8) — PoC 범위 밖.
- `validate_response`의 **휴장·기대일 일치 검증 강제 위치**가 collect 쪽이라면 그 적용은 W2 — 본 이슈는 가드 함수의 빈-응답 책임만 확정.
