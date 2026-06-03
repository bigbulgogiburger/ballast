# BAL-14 dev-guide — `app/sources/fx.py` USD/KRW 환율 어댑터

> SSoT 우선순위: `docs/04-backend.md`(최우선) → `docs/05-database.md` → `docs/01-product-spec.md`.
> 시그니처 정본: `docs/BAL-2-w2-orchestration.md §2.2`(이 표를 벗어난 새 시그니처 발명 금지). W1 구현 정본 = `docs/BAL-1-m1a-orchestration.md §2(v2)` + `docs/BAL-1-m1a-decisions.md`.
> ⚠️ **`TECH-DESIGN.md`는 레포에 없음**. W1 dev-guide가 인용한 `§15`는 부재 파일이므로 본 가이드는 **04/05/01만 정본**으로 사용하고 `§15` 참조를 답습하지 않는다.
> 범위: W2 데이터 스파이크 / 단일 에픽 BAL-2 수직 슬라이스. **하위작업 분해 없음**(orchestration §1 표: BAL-14 하위작업 "없음"). 산출 = `FxRate` frozen DTO 신규 + `FxSource.usdkrw()` 구현(ECB 1차 → yfinance 2차, ECOS 보조).
> 외부 API(ECB·ECOS·yfinance)는 테스트에서 **전량 모킹**.

---

## 1. 요구사항 & AC

### 이슈 요약
`app/sources/fx.py`는 현재 W2 스텁(1줄 docstring: "환율 수집(ECB 1차·ECOS·yfinance 폴백). W2에서 구현.")이다. BAL-14는 이를 USD/KRW 환율 단일 메서드 어댑터로 채운다.

1. **`FxRate` frozen DTO 신규**(`app/models.py`) — `fx_snapshot` 컬럼 1:1(`trade_date/pair/rate`). W1 models.py에는 미정의(decisions §3.8 / Q2)이므로 **W2-1 공유파일 선커밋**으로 추가(orchestration §2.2, §3 W2-1). BAL-13(import 가능성)·BAL-17(`upsert_fx` 인자)이 함께 닿는 유일 신규 DTO.
2. **`FxSource.usdkrw(self) -> FxRate`** — USD/KRW 환율 1건 조회. **1차 ECB**(키 불필요·안정) → **2차 yfinance `KRW=X`**, **ECOS 보조**. 둘 다(모든 소스) 실패 → `raise`(collect가 `collect_run(market='FX', status='FAIL')` 기록 → USD 자산 전체 보류). (04:485-491, orchestration §2.2)

### Acceptance Criteria (canonical 인용 부착)
- **AC1** `from app.models import FxRate` 가능 + `FxRate(trade_date, pair, rate)` 생성. 필드명 = `fx_snapshot` 컬럼 전체명(05:154-160). `@dataclass(frozen=True)`.
- **AC2** `FxSource().usdkrw()`가 **1차 ECB 성공 시** ECB 환율로 `FxRate(pair="USDKRW", ...)` 반환(orchestration §2.2 1차 ECB).
- **AC3** ECB 실패 → **2차 yfinance `KRW=X`** 폴백으로 `FxRate` 반환(04:488 2차). ECOS는 보조 경로(키 보유 시).
- **AC4** **모든 소스 실패 → `raise`**(예외 삼키지 않음). collect가 잡아 `collect_run(FX, FAIL)` 기록 → USD 자산 + USD 현금 보류(04:489-491, 05:162-163). **빈 응답을 FxRate(rate=0/NULL)로 위장 금지**(05:162 "NULL 분모 제외 금지 = 산출 거부").
- **AC5** `rate`는 **USD 1단위 = KRW 환율**(예: 1380.5). `pair` 고정값 `"USDKRW"`. `trade_date`는 소스 최신 기준일 `YYYY-MM-DD`.
- **AC6** `__init__` 무인자·무부작용(lazy) — 네트워크/키 접근은 `usdkrw()` 첫 호출 시(KrSource와 동일 계약, decisions Q10 / kr.py:37).
- **AC7** 외부 호출은 `@retry(3)` 지수 백오프 적용(04:450-452, sources/__init__.py:19). 단일 종목 격리는 collect 책임이므로 어댑터는 마지막 실패를 그대로 raise.
- **AC8** `db.upsert_fx(conn, FxRate(...))` 라운드트립 가능(`dataclasses.asdict(row)` named-bind 1:1 — decisions §3.4, db.py:225-233은 W2에서 `dict(row)`→`asdict(row)`로 전환되나 그 전환은 **BAL-17 W2-1 db 헬퍼 소관**, 본 이슈는 DTO 필드명 정합만 보장).

---

## 2. 영향 파일

| 파일 | 동작 | 비고 |
|---|---|---|
| `app/models.py` | **수정**(FxRate 추가) | W2-1 공유파일 선커밋. `@dataclass(frozen=True) FxRate(trade_date, pair, rate)` 추가. **기존 5종 DTO·docstring 손대지 않음**(Surgical). 파일 헤더 주석의 "FxRate…W2+ DTO는 본 슬라이스 범위 밖"은 W1 시점 진술 — 본 이슈가 W2이므로 추가가 정당(주석 1줄 갱신은 선택). |
| `app/sources/fx.py` | **수정**(스텁→구현) | 본 이슈 본체. `FxSource` 클래스 + `usdkrw()`. |
| `tests/test_fx.py` | **신규** | 본 가이드 §6 테스트(외부 API 전량 모킹). |
| `app/sources/__init__.py` | **읽기 전용 의존** | `retry`·`EmptyResponseError` import. 변경 불요(W1 W-2a 확정). |
| `app/config.py` | **읽기 전용 의존** | `ECOS_API_KEY`(선택 키, config.py:29) 참조. 변경 불요. ECB는 키 불필요. |
| `requirements*` | **수정(가능)** | yfinance 미설치 시 추가(현재 kr.py가 pykrx/requests만 사용). degraded-session에선 `.venv` 설치 수동 검증(orchestration §4). |

> ⚠️ **db.py는 본 이슈에서 수정하지 않는다**. `upsert_fx`의 `dict(row)`→`asdict(row)` FxRate 전환은 orchestration §2.6/§3에서 **BAL-17 W2-1 선커밋**으로 귀속(U3). BAL-14는 FxRate 필드명을 컬럼 전체명으로 고정해 그 전환의 선행조건만 만든다.

---

## 3. 구현 단계 (하위작업 분해 없음 — orchestration §1)

> BAL-14는 orchestration §1 표에서 하위작업 "없음". 단일 이슈 내 논리 단계로만 분해한다.

### 단계 A — `FxRate` DTO 정의 (`app/models.py`, W2-1 선커밋) — canonical 05 §1.5
orchestration §2.2 코드블록을 정본 그대로 추가. 필드명 = `fx_snapshot` 컬럼 전체명(asdict 키 1:1, decisions §3.4).
```python
@dataclass(frozen=True)
class FxRate:
    """fx_snapshot 적재용 DTO. 05 §1.5 컬럼 1:1(asdict 키=전체명). 04 §4.2/§7.4."""

    trade_date: str   # 소스 최신 기준일 'YYYY-MM-DD'
    pair: str         # 'USDKRW' 고정
    rate: float       # USD 1단위 = KRW
```
- 위치: `app/models.py` 끝(RegimeRow 다음). 기존 DTO 순서·내용 불변.
- **검증 포인트**: `from app.models import FxRate` 성공 / `dataclasses.asdict(FxRate("2026-06-03","USDKRW",1380.5)).keys() == {"trade_date","pair","rate"}` (05:155-157 컬럼명 == DDL).

### 단계 B — `FxSource` 클래스 골격 (lazy __init__) — canonical 04 §7.4
KrSource와 동일 계약: `__init__` 무인자·무부작용, 네트워크/키 접근은 메서드 첫 호출 시(decisions Q10, kr.py:37).
```python
class FxSource:
    """USD/KRW 환율 어댑터. __init__ 무부작용(lazy). 04 §7.4."""
```
- pair는 모듈 상수 `_PAIR = "USDKRW"`로 고정(05:156). USD 1단위=KRW 의미 주석.

### 단계 C — `usdkrw()` 폴백 체인 (1차 ECB → 2차 yfinance, ECOS 보조) — canonical 04:485-491
orchestration §2.2 + 04 §7.4를 구현. **소스별 fetch는 private 헬퍼로 분리**해 모킹·테스트 가능하게 한다.
```python
@retry(3)
def usdkrw(self) -> FxRate:
    # 1차 ECB → 2차 yfinance 'KRW=X' (ECOS 보조)
    # 모든 소스 실패 → raise (collect가 collect_run(FX, FAIL) 기록)
```
- 내부 폴백 패턴(kr.py `_ohlcv_fdr` 폴백 답습): `_from_ecb()` 시도 → 예외/빈값이면 `_from_yfinance()` → 그래도 실패면 raise. ECOS는 키 보유 시(`config.ECOS_API_KEY`) 보조 경로로 끼워 넣음(키 없으면 skip — config.py:29 선택 키).
- **빈/이상 응답 차단**: rate가 0·음수·NaN·None이면 그 소스를 "실패"로 간주(다음 폴백으로). 마지막까지 유효 rate 없으면 raise. (05:162 "NULL 분모 제외 금지 = 산출 거부" → 0/NULL 위장 금지.)
- `trade_date`: ECB는 응답의 기준일(`time`/`date` 필드), yfinance는 시계열 마지막 인덱스 날짜를 `YYYY-MM-DD`로. 미제공 시 `date.today().isoformat()` fallback(주석 명시).
- **검증 포인트**: §6 테스트 — ECB 성공/ECB실패→yf폴백/전건실패→raise/이상값(0·NaN)→다음폴백.

### 단계 D — 소스별 private fetch 헬퍼
- `_from_ecb() -> FxRate | None` — ECB 환율 API(키 불필요·안정, 04:487). ECB는 EUR 기준이므로 **USD/KRW 합성**이 필요할 수 있음(ECB는 USD/EUR·KRW/EUR 제공 → USDKRW = (KRW/EUR)/(USD/EUR)). ⚠️ ECB 엔드포인트의 USDKRW 직접 제공 여부는 **미해결 질문 U1**(아래) — 합성 방식은 구현자 확정. 실패/이상값 → `None`(폴백 유도).
- `_from_yfinance() -> FxRate | None` — `yfinance` `KRW=X` 티커 시계열 마지막 종가(04:488 2차). 빈 DF → `None`.
- `_from_ecos() -> FxRate | None`(보조) — 한국은행 ECOS(`config.ECOS_API_KEY` 필요, 선택 키). 키 없으면 호출 안 함(`None`).
- 모든 헬퍼는 네트워크 호출을 `requests`/`yfinance`로 직접 수행(kr.py 패턴) → 테스트에서 이 경계를 모킹.

### 단계 E — `py_compile` + 단위 테스트 그린
편집 후 `python3 -m py_compile app/models.py app/sources/fx.py`(degraded-session 수동 대체, orchestration §4) → `pytest -q tests/test_fx.py`.
- **검증 포인트**: §7 DoD 전 항목 통과.

---

## 4. 인터페이스 (정본 = orchestration §2.2, 그대로 구체화)

> 새 시그니처 발명 금지. 아래는 §2.2 시그니처를 파라미터/반환형/예외 수준으로만 구체화하며 §2.2와 1:1 대응한다.

```python
from dataclasses import dataclass

# ── app/models.py (W2-1 선커밋) — canonical 05 §1.5 ──
@dataclass(frozen=True)
class FxRate:
    trade_date: str   # 'YYYY-MM-DD'
    pair: str         # 'USDKRW'
    rate: float       # USD 1단위 = KRW

# ── app/sources/fx.py — canonical 04 §7.4 ──
class FxSource:                                   # FxSource Protocol
    def usdkrw(self) -> FxRate: ...
    #   1차 ECB / 한국은행 ECOS(보조) → 2차 yfinance 'KRW=X' (04:485-491, orchestration §2.2)
    #   @retry(3) 적용. 모든 소스 실패/이상값 → raise (예외 삼키지 않음)
    #   반환 pair="USDKRW" 고정, rate>0 보증(0/NaN/None은 실패로 간주)
```

**§2.2와의 정합 확인**:
- `FxRate` 필드 3종(`trade_date/pair/rate`) — orchestration §2.2 코드블록(L89-94)과 자모 단위 일치. 05:154-160 fx_snapshot 컬럼명과 1:1.
- `usdkrw(self) -> FxRate` — orchestration §2.2(L82) + 04:486과 일치. `self` 외 무인자.
- `conn`/타입주석은 본 이슈 무관(fx.py는 db 직접 미접근 — upsert는 collect 경유).
- ⚠️ **04 §7.4(04:487)는 1차를 "한국은행 ECOS / ECB"로 병기**하나, orchestration §2.2 + 본 이슈 지시는 **ECB 1차·ECOS 보조**로 좁힌다(둘 다 1차군이므로 모순 아님 — 우선순위만 고정). 04 > orchestration 우선이지만 04가 ECOS·ECB를 동급 1차로 두므로 그 안에서 ECB를 먼저 쓰는 것은 04 위반 아님.

---

## 5. 엣지 & 리스크

| # | 상황 | 영향 | 대응 (본 모듈) |
|---|---|---|---|
| E1 | **모든 소스 실패**(ECB·yf·ECOS 전건) | 환율 없음 | `raise`(삼키지 않음). collect가 `collect_run(FX, FAIL)` → USD 자산+현금 보류(04:489-491, 05:163). **0/NULL FxRate 위장 절대 금지**(05:162) |
| E2 | **빈/이상 응답**(rate=0·음수·NaN·None) | "조용한 실패"가 OK처럼 보임 | 그 소스를 실패로 간주 → 다음 폴백. 마지막까지 무효면 raise. (04:456 SSoT §4 "데이터 실재" 원칙) |
| E3 | **ECB가 USDKRW 직접 미제공**(EUR 기준) | 합성 필요 | USDKRW = (KRW/EUR)÷(USD/EUR) 합성. 합성 입력 중 하나라도 결측 → `_from_ecb()`=None(폴백). ⚠️ 정확한 엔드포인트·합성식은 U1 |
| E4 | **ECOS_API_KEY 없음**(선택 키) | 보조 경로 불가 | `config.ECOS_API_KEY is None`이면 ECOS 호출 skip(에러 아님). ECB·yf만으로 충족 가능(둘 다 키 불필요) |
| E5 | **yfinance `KRW=X` 빈 DF**(주말·휴장·차단) | 폴백 실패 | 빈 DF → `_from_yfinance()`=None. ECB가 1차이므로 보통 이미 충족 |
| E6 | **소스 간 trade_date 불일치**(주말 등) | 어느 날짜를 적재? | 채택한 소스의 자체 기준일 사용. fx는 `MAX(trade_date)` fallback 조회(05:162)라 약간 과거여도 정상 흡수 |
| E7 | **네트워크 일시 장애** | 1회 실패로 보류 | `@retry(3)` 지수 백오프로 흡수(04:450-452). 마지막 실패만 raise |
| E8 | **rate 단위 혼동**(KRW per USD vs 역수) | USD 평가액 1380²배/1380분의1 오류 | `rate` = **USD 1단위당 KRW**로 고정(05:157 REAL, 04 의도). yfinance `KRW=X`가 이 방향(USDKRW). ECB 합성도 동일 방향 산출 검증 |
| E9 | **db.upsert_fx 키 불일치**(W1 dict-surface) | asdict 키 미스매치 | FxRate 필드명=컬럼 전체명(05:155-157)이라 `asdict` 1:1. W1 `dict(row)`도 동일 키라 호환. 전환 자체는 BAL-17 소관 |
| E10 | **모델 import 순환/누락** | fx.py가 FxRate 못 찾음 | FxRate는 단계 A에서 models.py에 **선커밋**(W2-1) 후 fx.py가 import. 순서 역전 금지(orchestration §3 W2-1→W2-2) |

---

## 6. 테스트 계획 (외부 API 전량 모킹)

**파일: `tests/test_fx.py`** (pytest, `@pytest.mark.unit`). **ECB·ECOS·yfinance 네트워크 호출은 전량 모킹** — 실제 외부 API를 절대 때리지 않는다. 모킹 경계 = 단계 D의 private fetch 헬퍼(`_from_ecb`/`_from_yfinance`/`_from_ecos`) 또는 그 안의 `requests`/`yfinance` 호출(`monkeypatch`/`unittest.mock.patch`).

권장 픽스처/패턴:
```python
import pytest
from app.sources import fx as fxmod
from app.sources import EmptyResponseError  # 사용 시

@pytest.fixture
def src():
    return fxmod.FxSource()
```

| 테스트명 | 검증 대상 | 핵심 단언 |
|---|---|---|
| `test_fxrate_dataclass_fields` | FxRate DTO (단계 A) | `dataclasses.asdict(FxRate("2026-06-03","USDKRW",1380.5)).keys() == {"trade_date","pair","rate"}`(05 컬럼명) + frozen(`fields` 변경 시 `FrozenInstanceError`) |
| `test_usdkrw_ecb_primary` | 1차 ECB 성공 (AC2) | `_from_ecb` 모킹이 `FxRate` 반환 → `usdkrw()`가 ECB 값 반환, `pair=="USDKRW"`, `_from_yfinance` **미호출**(폴백 안 탐) |
| `test_usdkrw_falls_back_to_yfinance` | ECB 실패→yf 2차 (AC3, E5) | `_from_ecb` 모킹=None(또는 raise) + `_from_yfinance` 모킹=FxRate → yf 값 반환 |
| `test_usdkrw_all_sources_fail_raises` | 전건 실패 (AC4, E1) | 세 헬퍼 전부 None/raise 모킹 → `usdkrw()`가 **예외 raise**(0/NULL FxRate 반환 안 함) |
| `test_usdkrw_zero_or_nan_treated_as_fail` | 이상값 차단 (E2, E8) | `_from_ecb`가 rate=0(또는 NaN/음수) 반환하도록 모킹 → 다음 폴백으로 넘어감(0 채택 안 함) |
| `test_usdkrw_rate_is_positive_float` | rate 단위/형 (AC5, E8) | 성공 경로 반환 `rate`가 `float` & `> 0` |
| `test_usdkrw_pair_constant` | pair 고정 (AC5) | 모든 성공 경로 반환 `pair == "USDKRW"` |
| `test_ecos_skipped_when_no_key` | ECOS 선택 키 (E4) | `config.ECOS_API_KEY=None` monkeypatch + ECOS fetch 모킹에 호출 카운터 → `_from_ecos` 네트워크 미호출(또는 None 즉시 반환) |
| `test_init_is_lazy_no_network` | lazy __init__ (AC6) | `FxSource()` 생성만으로 어떤 fetch 헬퍼도 호출 안 됨(생성자 무부작용) |
| `test_retry_applied` | @retry(3) (AC7, E7) | 1차 소스가 2회 raise 후 3회째 성공하도록 모킹 → `usdkrw()` 성공(재시도 흡수). ※ retry는 sources/__init__ 검증 끝났으므로 적용 여부만 가볍게 |
| `test_upsert_fx_roundtrip` | DTO↔db 정합 (AC8, E9) | `:memory:` db.connect+init_schema → `db.upsert_fx(conn, asdict(FxRate(...)))` → `db.latest_fx(conn)`가 동일 rate row. ※ W1 `upsert_fx`가 dict-surface라 `asdict` 전달; FxRate 직접 인자는 BAL-17 전환 후 |

> **모킹 원칙**: ECB/ECOS는 `requests.get` 모킹 또는 `_from_*` 헬퍼 직접 모킹, yfinance는 `yf.Ticker`/`yf.download` 모킹. 실제 HTTP 금지(테스트 결정성·오프라인·외부 한도 보호). degraded-session에서도 외부 호출 0.
> 본 모듈은 DB 직접 의존이 없으므로 `test_upsert_fx_roundtrip`만 SQLite(`:memory:`) 사용, 나머지는 순수 모킹.

---

## 7. DoD (Definition of Done)

로드맵 08 §Week2 + orchestration §5에서 **fx.py/FxRate에 해당하는 항목만** 인용:

- [ ] (orchestration §3 W2-1) `from app.models import FxRate` 가능, `FxRate(trade_date,pair,rate)` frozen DTO 생성. 필드명 = `fx_snapshot` 컬럼 전체명(05:155-157).
- [ ] (orchestration §2.2 / §5 FX) `FxSource().usdkrw()`가 ECB 1차 성공 시 `FxRate(pair="USDKRW")` 반환(모킹 기반 단위테스트).
- [ ] (04:488) ECB 실패 시 yfinance `KRW=X` 2차 폴백으로 `FxRate` 반환. ECOS 보조(키 보유 시).
- [ ] (04:489-491, 05:162-163) 모든 소스 실패/이상값 → **예외 raise**(0/NULL FxRate 위장 금지). collect의 `collect_run(FX, FAIL)` 경로 전제 충족.
- [ ] (AC7) 외부 호출 `@retry(3)` 적용(04:450-452).
- [ ] (AC6) `FxSource.__init__` 무부작용 — 생성만으로 네트워크 0(decisions Q10).
- [ ] (orchestration §5) `pytest -q tests/test_fx.py` green — **외부 API 전량 모킹**(실제 HTTP 0). 편집 파일 `py_compile` 통과(degraded-session 수동 대체, §4).
- [ ] (AC8) `db.upsert_fx`↔`latest_fx` 라운드트립 정합(asdict 키 = 컬럼 전체명).
- [ ] 코딩 규칙: PEP8 + 전 함수 타입주석 + `FxRate` frozen dataclass. `print()` 미사용(logging 사용).

> ⚠️ `upsert_fx`의 `dict(row)`→`asdict(row)` FxRate **전환 자체**는 BAL-17 W2-1 db 헬퍼 소관(U3) — 본 이슈 DoD 아님. 본 이슈는 필드명 정합(전환 선행조건)까지.

---

## 8. Out of scope (W2 / BAL-14 아님)

- **`db.py` `upsert_fx` 본체 전환**(`dict`→`asdict`, FxRate 인자 타입) — orchestration §2.6/§3에서 **BAL-17 W2-1 선커밋**으로 귀속(U3). BAL-14는 FxRate 필드명만 고정.
- **`_collect_fx`·`run_collect`·`collect_run(FX, FAIL)` 기록** — BAL-17(collect 통합자, 04:523/8.1, orchestration §2.5).
- **fx 결측 시 USD 자산 보류 게이트 판정**(usd_cash_gate_threshold 비교, G6) — metrics/게이트 레이어(05:163, W3).
- **`fx_snapshot` DDL·`latest_fx` 조회 헬퍼** — BAL-8 W1에서 이미 완료(05:154-160, db.py:225-233 / latest_fx).
- **US/regime/etf 어댑터, US 시세·펀더**(BAL-13/15/16), **metrics·LLM·프론트·손익/룩스루** — orchestration §6.
- **다중 통화쌍**(USDKRW 외) — PoC는 USDKRW 단일(05:156 pair='USDKRW'). 확장은 R2+.
- **임시공휴일/거래일 정밀 매핑** — fx는 `MAX(trade_date)` fallback으로 흡수(05:162), calendar 확장은 별도(orchestration §6).

---

## 미해결 질문
(04/05/01/orchestration 간 명시 불일치 또는 미정의 — 임의 가정 주입 없이 모음.)

1. **U1 — ECB 엔드포인트 + USDKRW 합성식**: 04:487/orchestration §2.2는 "ECB"만 명시하고 구체 엔드포인트·USDKRW 직접 제공 여부를 정하지 않았다. ECB Statistical Data Warehouse는 통상 EUR 기준(USD/EUR·KRW/EUR)이라 **USDKRW = (KRW/EUR)÷(USD/EUR) 합성**이 필요할 수 있다. 합성 방식·정확한 엔드포인트는 구현자 확정 필요(본 가이드는 합성 전제 + E3에 명시). 대안: ECB가 부담스러우면 **yfinance를 사실상 1차로** 쓰고 ECB를 보조로 강등하는 것도 04(ECOS/ECB·yf 동급군) 위반 아님 → 사용자/구현자 선택.
2. **U2 — 1차 소스 우선순위(04 vs orchestration/지시)**: 04:487은 "한국은행 ECOS / ECB"를 1차로 **병기**(동급), orchestration §2.2 + 본 이슈 지시는 **ECB 1차·ECOS 보조**. 본 가이드는 후자(ECB 1차)로 진행했다. 04가 둘을 동급 1차로 두므로 충돌은 아니나, ECOS를 1차로 올릴지(키 보유 환경에서 안정적) 의도 확인만 필요.
3. **U3 — `upsert_fx` FxRate 전환 귀속**: orchestration §7 U3대로 `upsert_fx`의 `dict`→`asdict`·`row: FxRate` 전환을 **BAL-17 W2-1**에 귀속했다. BAL-8을 "db 헬퍼 단일 소유"로 강제하는 정책이 있으면 BAL-8 W2 carryover로 재배치 — 이슈 귀속만 사용자/오케스트레이터 확정.
4. **U4 — `trade_date` 소스 불일치 처리**: 소스별 최신 기준일이 다를 때(주말·시차) 채택 소스의 날짜를 그대로 쓴다(E6). `MAX(trade_date)` fallback(05:162)이 흡수하므로 블로커 아니나, "어제 환율을 오늘 trade_date로 라벨링"할지 여부(정확성 vs 신선도)는 확인 가능.

> 📌 본 가이드 미해결 질문 중 시그니처/DTO 관련(FxRate 필드·usdkrw 반환형)은 orchestration §2.2 = canonical로 **확정**. U1/U2/U4는 외부 소스 운영 디테일(코드 시그니처 불변)로, 구현 시 1택 고정 가능하며 본 슬라이스 진행을 막지 않는다.
> ⚠️ **TECH-DESIGN.md 부재 재확인**: 본 가이드는 `§15` 미인용. 정본은 04/05/01 + orchestration §2.2 + decisions.
