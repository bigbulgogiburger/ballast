# BAL-15 dev-guide — `app/sources/regime.py` (US 절반: `us_cape` Shiller CAPE 채움)

> SSoT 우선순위: `docs/04-backend.md`(최우선) → `docs/05-database.md` → `docs/01-product-spec.md`.
> 시그니처 정본: `docs/BAL-2-w2-orchestration.md §2.3`(=canonical 04 §7.5). W1 구현 정본 = `docs/BAL-1-m1a-orchestration.md §2(v2)` + `docs/BAL-1-m1a-decisions.md`(특히 Q10).
> ⚠️ **`TECH-DESIGN.md`는 레포에 없음**. W1 dev-guide 일부가 인용한 `§15.x`는 부재 파일이므로 **인용 금지** — 본 가이드는 04/05/01만 정본으로 쓴다.
> 범위: W2-2 어댑터 파동. 하위작업 분해 = **없음**(BAL-48 잔여 us_cape 단건). W1이 만든 `app/sources/regime.py`를 **in-place 단일 수정**한다.

---

## 1. 요구사항 & AC

### 이슈 요약
`app/sources/regime.py`는 W1(BAL-48 일부)에서 KR 절반만 구현된 상태다 — `kospi_pbr`는 pykrx 지수 PBR(코드 `'1001'`)로 실제 fetch하고, `us_cape=None`은 W2 플레이스홀더로 남겨져 있다(현행 `regime.py:25-29`). BAL-15는 이 **단 하나의 플레이스홀더**(`us_cape=None`)를 실제 Shiller CAPE fetch로 교체한다.

- **US: Shiller CAPE** — Yale `ie_data.xls`(1차) / multpl 스크레이프(2차) (04:498, 04:507).
- **월단위 캐시 재사용** — 같은 달이면 재호출 불필요(가벼움) (04:499). ⚠️ 캐시 위치는 미해결(§5 R3 / orchestration U5): collect 레벨 DB row 존재 체크가 1차, regime.py 내부 메모 캐시는 보조. **본 가이드 기본안 = regime.py 내부에 월단위 메모 캐시 두지 않음**(collect의 month-skip 단일, 04:528) → 어댑터는 매 호출 fetch하되 collect가 skip 결정. 이중화 금지.
- **한쪽만 실패 → 그 필드만 NULL** — `us_cape` fetch 실패 시 `kospi_pbr`는 살리고 `us_cape=None` 반환. 둘 다 NULL이면 metrics.regime이 degrade 라벨(W3) (04:500, 04:533).

### Acceptance Criteria
| # | AC | 근거 |
|---|----|------|
| AC1 | `RegimeProvider().regime().us_cape`가 실수치(float) 반환(외부 fetch 성공 시). | 04:498, 04:507 |
| AC2 | `kospi_pbr` 로직 **회귀 없음** — W1 동작(pykrx `'1001'` 지수 PBR, `as_of='YYYY-MM-01'`) 그대로 보존. | decisions Q10, orchestration §2.3 "kospi_pbr 절대 손대지 않음" |
| AC3 | `us_cape` fetch 실패 시 `kospi_pbr`는 유지하고 `us_cape=None` 반환(한쪽 실패→그 필드만 NULL). 둘 다 실패면 raise(collect가 W2 degrade). | 04:500, 04:533 |
| AC4 | 시그니처 불변: `def regime(self) -> RegimeRow`, `@retry(3)`. canonical 04 §7.5 / orchestration §2.3과 자모 단위 일치. | orchestration §2.3, 04:496-497 |
| AC5 | 1차(Yale `ie_data.xls`) 실패 시 2차(multpl) 폴백 시도 후 둘 다 실패면 `us_cape=None`(AC3 경로). | 04:507 |
| AC6 | 외부 API(Yale xls·multpl·pykrx)는 테스트에서 **전량 모킹** — 네트워크 호출 없음. | 글로벌 testing 규칙 + 본 슬라이스 모킹 정책 |

---

## 2. 영향 파일

| 파일 | 동작 | 비고 |
|---|---|---|
| `app/sources/regime.py` | **수정**(in-place) | 본 이슈 본체. `regime()` 내 `us_cape=None`(현행 line 28) → 실제 CAPE fetch 호출로 교체 + `_fetch_us_cape()` 모듈 헬퍼 신규. **`kospi_pbr` 블록(line 22-24)·`as_of`(line 26)·import·클래스 구조는 불변**(Surgical). |
| `tests/test_regime.py` | **신규** | 본 가이드 §6 테스트. pykrx·Yale xls·multpl 전량 모킹. |
| `app/models.py` | **읽기 전용** | `RegimeRow`(frozen, `as_of/kospi_pbr/us_cape`) 재사용. 변경 불요(W1 정의, `models.py:69-78`). |
| `app/sources/__init__.py` | **읽기 전용** | `@retry(3)` 재사용(현행 `__init__.py:18-40`). 변경 불요. |
| `requirements*` | **수정 가능성** | Yale `ie_data.xls` 파싱에 `pandas`(기존)·`openpyxl`(xls/xlsx 엔진) 필요 시 추가. multpl 스크레이프는 `pandas.read_html`(lxml/html5lib) 또는 `requests`. ⚠️ 신규 라이브러리는 degraded-session에서 `.venv` 설치 수동 검증(orchestration §4). |

> `kospi_pbr` fetch가 이미 pykrx를 import하므로 신규 import는 CAPE 소스용(예: `pandas`/`requests` 또는 `urllib`)만 추가. 04/05는 구체 라이브러리를 강제하지 않음 — Yale `ie_data.xls`를 pandas로 읽는 것이 가장 단순(아래 §3 단계 B 참조).

---

## 3. 구현 단계

### 하위작업 분해
**없음** — BAL-15는 BAL-48의 W2 잔여(us_cape) 단건이라 별도 하위 이슈로 쪼개지 않는다(orchestration §1 표: "BAL-15 하위작업 = (BAL-48 잔여 — us_cape)"). 아래는 단일 이슈 내 구현 단계.

### 단계 A — `_fetch_us_cape()` 모듈 헬퍼 신규 (04:498, 04:507)
모듈 레벨 private 함수로 CAPE 소스 폴백 체인을 캡슐화한다. `RegimeProvider` 메서드가 아닌 모듈 함수로 두는 이유 = `kospi_pbr` 블록과 물리적으로 분리해 "단일 집중 블록" 수정(decisions Q10 / orchestration §2.3)을 보장하고 테스트에서 독립 모킹 가능.

```python
def _fetch_us_cape() -> float:
    """Shiller CAPE: Yale ie_data.xls(1차) → multpl 스크레이프(2차).
    둘 다 실패 시 예외 전파(호출부 regime()이 한쪽-NULL 규칙으로 흡수)."""
    try:
        return _cape_from_yale()      # 1차: Yale ie_data.xls
    except Exception:
        return _cape_from_multpl()    # 2차: multpl 스크레이프
```
- 1차 `_cape_from_yale()`: Yale `ie_data.xls`를 받아(`pandas.read_excel`) CAPE 컬럼 최신 비결측 값을 `float`로 반환. xls 시트 구조(헤더 오프셋·"Data" 시트·CAPE 컬럼명)는 구현 시 실측으로 고정하되, **빈/결측 시 raise**(빈응답을 OK로 오인 금지, 04:456 철학).
- 2차 `_cape_from_multpl()`: multpl Shiller PE 페이지를 `pandas.read_html`/스크레이프해 현재값 `float` 추출. 실패 시 raise.
- **검증 포인트**: 1차 성공 → 2차 호출 안 함. 1차 raise → 2차 시도. 둘 다 raise → 예외 전파.

### 단계 B — `regime()` 내 `us_cape=None` 교체 (decisions Q10 / orchestration §2.3, 단일 수정 지점)
현행 `regime.py:25-29`의 return 직전에 us_cape를 채운다. **`kospi_pbr` 블록(line 22-24)은 절대 손대지 않는다.**

```python
@retry(3)
def regime(self) -> RegimeRow:
    today = date.today()
    fromdate = (today - timedelta(days=30)).strftime("%Y%m%d")
    df = stock.get_index_fundamental(fromdate, today.strftime("%Y%m%d"), _KOSPI_INDEX)
    kospi_pbr = float(df["PBR"].iloc[-1])          # ← W1 불변
    try:
        us_cape: float | None = _fetch_us_cape()   # ← W2 신규(단일 집중 블록)
    except Exception:
        us_cape = None                             # 한쪽 실패 → 그 필드만 NULL (04:500)
    return RegimeRow(
        as_of=today.replace(day=1).isoformat(),
        kospi_pbr=kospi_pbr,
        us_cape=us_cape,                           # ← None 플레이스홀더 교체
    )
```
- **`@retry(3)`는 메서드 전체에 걸린다** — 즉 kospi_pbr fetch가 실패하면 전체 메서드가 재시도된다(W1 계약 유지). us_cape의 try/except는 retry **안쪽**이므로, us_cape만 실패해도 메서드는 성공 반환(us_cape=None). 이는 "한쪽 실패→그 필드만 NULL"(04:500) + "kospi_pbr 실패 시 raise→collect degrade"(decisions Q10) 둘을 동시에 만족한다.
- ⚠️ **둘 다 실패 시**: kospi_pbr fetch(pykrx)가 raise하면 `@retry(3)` 소진 후 메서드가 raise → collect의 `_collect_regime`이 잡아 degrade(04:531-533). us_cape는 try/except로 흡수되므로 us_cape 단독 실패는 메서드를 죽이지 않는다. "둘 다 NULL"은 (kospi_pbr가 NaN-like일 때) metrics가 라벨링하는 경우이며 본 어댑터 책임은 NULL 정직 전달까지.
- **검증 포인트**: us_cape mock=실수 → return.us_cape == 그 값 + kospi_pbr 보존. us_cape mock=raise → return.us_cape is None + kospi_pbr 보존. kospi_pbr fetch raise → 메서드 raise.

### 단계 C — 월단위 캐시: 어댑터에 두지 않음 (orchestration U5 기본안)
04:499 "같은 달이면 캐시 재사용"은 **collect 레벨의 DB row 존재 체크(04:528 "이미 이번 달 row 있으면 skip")로 충족**한다. regime.py 어댑터는 내부 메모 캐시를 두지 않는다(이중화 금지, Surplus 제거). BAL-15 어댑터 책임 = 호출 시 fresh fetch. 월단위 skip은 BAL-17(`_collect_regime`) 소관.
- **검증 포인트**: regime.py에 module-level 캐시 변수/lru_cache 없음(테스트로 강제하지 않되 코드 리뷰 항목).

### 단계 D — `py_compile` + 단위 테스트 그린 (degraded-session 수동 대체, orchestration §4)
```bash
python3 -m py_compile app/sources/regime.py
pytest -q tests/test_regime.py
```
- **검증 포인트**: §7 DoD 전 항목 통과.

---

## 4. 인터페이스 (정본 = orchestration §2.3 = canonical 04 §7.5)

> 새 시그니처 발명 금지. 공개 시그니처는 W1과 동일하게 **불변**이며, 본 이슈는 본체만 성장시킨다.

```python
from app.models import RegimeRow
from app.sources import retry

class RegimeProvider:                 # RegimeSource Protocol (W1에서 이미 존재 — 구조 불변)
    @retry(3)
    def regime(self) -> RegimeRow:    # ← 시그니처 불변(orchestration §2.3, 04:496-497, decisions Q10)
        ...                           # kospi_pbr(W1) 보존 + us_cape(W2) 채움

# 모듈 private 헬퍼(신규, 비공개 — 시그니처 발명 아님, 내부 구현):
def _fetch_us_cape() -> float: ...    # Yale ie_data.xls(1차) → multpl(2차). 실패 시 raise.
```

**정합 확인**:
- `regime(self) -> RegimeRow` + `@retry(3)`: orchestration §2.3 / 04:496-497 / decisions Q10과 자모 단위 일치.
- `RegimeRow` 매핑: `as_of`('YYYY-MM-01') → `market_regime.trade_date`, `us_cape` → `market_regime.shiller_cape`, `kospi_pbr` → `market_regime.kospi_pbr`(05:181-188, `models.py:73`). **이 매핑은 db.upsert_market_regime(BAL-17/W2-1) 책임** — regime.py는 DTO만 반환.
- `_fetch_us_cape`는 04/05에 시그니처가 없는 **내부 구현 디테일** → 공개 계약 발명이 아님. 04:507(Yale 1차/multpl 2차)을 캡슐화할 뿐.

---

## 5. 엣지 & 리스크

| # | 상황 | 영향 | 대응 (본 모듈) |
|---|------|------|----------------|
| E1 | **Yale ie_data.xls 결측/빈 셀**(최신월 CAPE 미확정) | NaN을 float로 캐스팅 → 오염값 | `_cape_from_yale`이 최신 **비결측** 행을 취하고, 비결측 없으면 raise → 2차 폴백. 빈응답=OK 오인 금지(04:456 철학) |
| E2 | **Yale xls 다운/포맷 변경** | 1차 raise | 2차 multpl 폴백(AC5). 둘 다 실패 → us_cape=None(한쪽 NULL, AC3) |
| E3 | **us_cape 단독 실패, kospi_pbr 정상** | 둘 다 NULL로 죽이면 안 됨 | 단계 B try/except가 us_cape만 None 처리, kospi_pbr 보존(04:500) |
| E4 | **kospi_pbr fetch 실패**(pykrx 빈 DF/예외) | 메서드 raise 필요 | W1 계약 유지 — `@retry(3)` 소진 후 raise → collect degrade(decisions Q10, 04:531). ⚠️ pykrx 빈 DF는 예외 아닌 빈 DataFrame일 수 있음(decisions Q13) — W1 현행 코드는 `iloc[-1]`이 빈 DF에서 IndexError를 일으켜 retry 작동. **us_cape 추가가 이 동작을 바꾸지 않도록** kospi_pbr 라인 불변 유지 |
| E5 | **월단위 중복 fetch**(매일 collect) | 불필요한 네트워크 | collect의 month-skip(04:528)이 1차 방어. 어댑터는 캐시 안 둠(단계 C). 과설계 방지 |
| E6 | **multpl HTML 구조 변경** | 2차도 raise | us_cape=None(AC3). metrics가 degrade 라벨(W3). 어댑터는 NULL 정직 전달 |
| E7 | **CAPE 값 타입**(문자열·콤마·% 포함) | float 캐스팅 실패 | 파싱 시 정규화 후 `float()`. 실패 시 raise(빈/오염값 OK 오인 금지) |
| E8 | **신규 라이브러리 미설치**(openpyxl/lxml) | import 실패 | degraded-session에서 `.venv` 수동 설치 검증(orchestration §4). requirements 반영 |
| E9 | **키 불필요 확인** | API 키 누수/누락 우려 | regime 소스는 **키 불필요**(04:509, 05:관련). config.py 키 참조 없음 — 신규 env 의존 0 |

---

## 6. 테스트 계획 (외부 API 전량 모킹)

**파일: `tests/test_regime.py`** (pytest, `@pytest.mark.unit`). pykrx·Yale xls·multpl **전부 모킹** — 네트워크 0.

모킹 전략:
- `stock.get_index_fundamental`(pykrx)는 `monkeypatch`로 클래스/모듈 레벨 패치하여 `PBR` 컬럼을 가진 DataFrame 반환(decisions Q10/Q13 패턴 답습 — `app.sources.regime.stock.get_index_fundamental` 패치).
- `_cape_from_yale` / `_cape_from_multpl`(또는 그들이 부르는 `pandas.read_excel`/`read_html`)을 `monkeypatch`로 패치해 실수/예외를 주입. 헬퍼 단위로 폴백 분기를 검증.
- ⚠️ `@retry(3)`가 걸린 메서드 테스트 시 실패 케이스는 `time.sleep`이 backoff로 호출됨 → `monkeypatch.setattr("app.sources.regime.time.sleep", lambda *_: None)` 또는 retry 경로를 타지 않는 입력으로 테스트 시간 단축(retry는 `app/sources/__init__.py` 소관, 본 테스트는 sleep만 무력화).

| 테스트명 | 검증 대상 | 핵심 단언 |
|---|---|---|
| `test_regime_fills_us_cape` | 단계 B 정상 | pykrx mock + `_fetch_us_cape` mock=28.5 → `regime().us_cape == 28.5` |
| `test_regime_preserves_kospi_pbr` | AC2 회귀 가드 | pykrx mock(PBR 마지막=1.05) → `regime().kospi_pbr == 1.05` (us_cape 추가가 KR 로직 안 깸) |
| `test_regime_as_of_format` | AC2/decisions Q10 | `regime().as_of`가 `'YYYY-MM-01'` 형식(당월 1일) |
| `test_regime_us_cape_fail_keeps_kospi` | AC3 / E3 | `_fetch_us_cape` mock=raise → `us_cape is None` **그리고** `kospi_pbr`는 실수치 보존 |
| `test_regime_kospi_fail_raises` | AC3 / E4 | pykrx mock=빈 DF(또는 raise) → `regime()`이 raise(@retry 소진 후). sleep 무력화 |
| `test_fetch_us_cape_yale_primary` | 단계 A / AC1 | `_cape_from_yale` mock=30.0 → `_fetch_us_cape() == 30.0`, multpl 미호출 |
| `test_fetch_us_cape_falls_back_to_multpl` | 단계 A / AC5 / E2 | yale mock=raise + multpl mock=29.1 → `_fetch_us_cape() == 29.1` |
| `test_fetch_us_cape_both_fail_raises` | 단계 A / E2 | yale·multpl 둘 다 raise → `_fetch_us_cape()` raise(상위 regime이 None 흡수) |
| `test_cape_from_yale_skips_nan` | E1 | xls mock에 최신행 NaN + 직전행 28.0 → 28.0 반환(비결측 최신) |
| `test_cape_from_yale_empty_raises` | E1 | 비결측 CAPE 없음 → raise(빈응답 OK 오인 금지) |
| `test_no_module_level_cache` | 단계 C / E5 | `app.sources.regime`에 월단위 캐시 상태 없음(2회 호출 시 fetch 2회 — collect가 skip 담당) |

> 외부 의존(pykrx/Yale/multpl)은 **전량 모킹** — 실제 네트워크/파일 다운로드 금지. 통합(실 fetch) 검증은 BAL-17 W2-3 collect E2E 소관(orchestration §5).

---

## 7. DoD (Definition of Done)

orchestration §5(W2 통합 DoD) 중 **regime/BAL-15에 해당하는 항목만** + 08 §Week2 인용:

- [ ] (orchestration §5 regime) `RegimeProvider().regime().us_cape`가 실수치 반환(외부 fetch 성공 시, mock 검증). (AC1)
- [ ] (orchestration §5 regime) `kospi_pbr` **회귀 없음** — W1 동작(pykrx `'1001'`, `as_of='YYYY-MM-01'`) 보존(테스트 가드). (AC2)
- [ ] (04:500) `us_cape` 단독 실패 시 `kospi_pbr` 유지 + `us_cape=None`(한쪽 NULL). 둘 다 실패 경로(kospi 실패)는 raise→collect degrade. (AC3)
- [ ] (orchestration §2.3) 시그니처 불변 — `regime(self) -> RegimeRow` + `@retry(3)`. canonical 04 §7.5 정합. (AC4)
- [ ] (04:507) Yale `ie_data.xls`(1차) → multpl(2차) 폴백 체인. (AC5)
- [ ] (모킹 정책) 외부 API(pykrx/Yale/multpl) 전량 모킹, 네트워크 0. (AC6)
- [ ] (orchestration §4) `pytest -q` green, `python3 -m py_compile app/sources/regime.py` 통과.
- [ ] 코딩 규칙: PEP8 + 전 함수 타입주석. `print()` 미사용(`log.warning`는 collect 소관, 어댑터는 raise/None). Surgical — `kospi_pbr`/import/클래스 구조 불변.
- [ ] regime.py에 월단위 메모 캐시 미도입(단계 C, 이중화 금지).

> ⚠️ `db.upsert_market_regime`(as_of→trade_date, us_cape→shiller_cape 매핑)·`_collect_regime`의 month-skip·degrade 로깅은 **BAL-17/W2-1 범위** — BAL-15 DoD 아님.

---

## 8. Out of scope (W2 / BAL-15 아님)

- **`db.upsert_market_regime`** (05:181-188 market_regime 적재, as_of→trade_date·us_cape→shiller_cape 매핑) — W2-1 선커밋 / BAL-17 의존(orchestration §2.6).
- **`_collect_regime`** 통합(월단위 month-skip 04:528, degrade try/except 04:531-533, collect 호출) — BAL-17/W2-3(orchestration §2.5).
- **metrics `regime()`** 라벨 변환(CAPE/PBR → 한 줄 라벨, degrade 라벨링) — W3(04:509, 04 §9).
- **`kospi_pbr` 로직 변경** — W1(BAL-48)에서 완료, 본 이슈는 보존만. 수정 금지(Surgical).
- **다른 어댑터**(us.py/fx.py/etf.py) — BAL-13/14/16 각자 소관(orchestration §1).
- **`models.RegimeRow` 변경** — W1 정의 재사용(`models.py:69-78`), 변경 불요.
- **임시공휴일/거래일 판정** — regime은 월단위라 거래일 무관. calendar 확장은 본 슬라이스 밖(orchestration §6).

---

## 미해결 / 결정필요 (orchestration §7과 정합 — 임의 가정 주입 금지)

| # | 항목 | 본 가이드 기본안(근거) | 결정 필요 주체 |
|---|------|------------------------|----------------|
| R1 (=orch U5) | **월단위 캐시 위치** | regime.py 내부 캐시 안 둠 → collect `_collect_regime`의 DB row 존재 체크(04:528)가 단일 skip. 이중화 금지(단계 C). | 구현자(BAL-17) — 본 어댑터는 캐시 미도입으로 고정 |
| R2 | **Yale ie_data.xls 시트/컬럼 구조** | 04:507이 파일만 명시하고 시트명·CAPE 컬럼명·헤더 오프셋은 미명시. 구현 시 실측으로 고정(최신 비결측 CAPE 취득). multpl 2차는 PE 페이지 현재값. | 구현자(BAL-15) — 실측 후 상수 고정 |
| R3 | **"둘 다 NULL → degrade" 판정 위치** | 어댑터는 NULL 정직 전달까지. "둘 다 NULL이면 degrade 라벨"은 metrics.regime(04:500, W3) 책임. 본 이슈 범위 밖. | metrics(W3) |

> ⚠️ **TECH-DESIGN.md 부재 재확인**: W1 dev-guide의 `§15.x` 인용은 부재 파일을 가리킨다. 본 가이드는 04/05/01만 인용했으며 `§15` 참조를 답습하지 않았다.
