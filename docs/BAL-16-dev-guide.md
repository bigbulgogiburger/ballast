---
issue: BAL-16
title: sources/etf.py ETF 코어 판정
type: single
status: closed
week: W2
parent: null
persona: Python Expert
created: 2026-06-03
closed: 2026-06-04
---

# BAL-16 dev-guide — `app/sources/etf.py` ETF 코어 판정 보강

> SSoT 우선순위: `docs/04-backend.md`(최우선) → `docs/05-database.md` → `docs/01-product-spec.md`.
> ⚠️ **`TECH-DESIGN.md`는 레포에 없음**. W1 dev-guide가 인용한 `§15`는 부재 파일이므로 본 가이드는 **04/05/01만** 정본으로 쓴다. `§15` 참조를 답습하지 말 것.
> 시그니처 정본: `docs/BAL-2-w2-orchestration.md §2.4` (이 표를 벗어난 새 시그니처 발명 금지). W1 구현 정본 = `docs/BAL-1-m1a-orchestration.md §2(v2)` + `docs/BAL-1-m1a-decisions.md`.
> 범위: W2 데이터 스파이크, 단일 에픽 BAL-2 수직 슬라이스. 하위작업 **없음**.
> ⚠️ **스코프 모호 — 본 가이드 §3·§8·미해결질문 U1 참조**: ETF 코어 판정은 W1(`tickers.py:41-57`)에서 이미 종료, 룩스루 구성종목 분해는 R2(F-19)로 배제. BAL-16의 W2 실질 산출이 0에 수렴할 수 있어 **사용자 스코프 결정이 선행 권장**이다.

---

## 1. 목표 & 배경

### 이슈 요약
`app/sources/etf.py`는 현재 W2 스텁(1줄 docstring: `"""ETF 구성·보유종목 수집. W2에서 구현."""`)이다. orchestration §2.4가 고정한 W2 범위는 **코어 판정 보강만**(룩스루는 R2 배제):

```python
# 스코프 확정(orchestration §7 U1): W2 = 코어 판정 보강만. 룩스루 구성종목 분해는 R2(F-19)로 배제.
def is_core_etf(ct: str) -> bool:
    # tickers.CORE_ETF_WHITELIST 멤버십 위임(W1이 이미 코어 판정 보유 — classify_category).
    # etf.py 신규 가치 = 화이트리스트 밖 ETF의 발행사 메타 확인(보강)에 한정.
```
근거: orchestration §2.4(`docs/BAL-2-w2-orchestration.md:108-116`).

### ⚠️ 핵심 발견 — 본 이슈의 실질 산출이 0에 수렴할 수 있음
1. **코어 판정은 W1에서 이미 완료**. `app/tickers.py:41-46`의 `CORE_ETF_WHITELIST`(frozenset 9종: 069500/360750/379800/VOO/SPY/VTI/IVV/ITOT/VT) + `classify_category()`(`tickers.py:49-57`)가 ETF→화이트리스트 매칭만 `core`, 미매칭 ETF→`None`("확인 필요")을 이미 판정한다. 01:42 AC4("코어 ETF 화이트리스트 자동판정")·05:80(category 채움 규칙 G4)이 이 한 곳에서 충족된다.
2. **룩스루(F-19)는 R2**. 01:109(F-19 = ETF 구성 PDF/CSV 룩스루 비중, **Could**), 01:248(R2 = 정확도 확장, F-19 명시)이 룩스루를 R1 PoC **범위 밖**으로 못박는다.
3. 따라서 orchestration §2.4가 남긴 "etf.py 신규 가치"는 **화이트리스트 밖 ETF의 발행사 메타 확인(보강)**뿐인데, 이것은 (a) 명확한 canonical 시그니처가 04/05/01 어디에도 없고 (b) 룩스루 없이는 실효 산출이 모호하다.

→ **사용자 결정 선행 권장(U1)**: (옵션 A) 본 이슈를 R2로 미루고 etf.py를 stub 유지, (옵션 B) `is_core_etf` 얇은 위임 함수만 추가(중복이지만 collect/metrics가 ct→bool 단일 진입점을 원할 때), (옵션 C) 룩스루 일부를 W2로 당김(R2 범위 침범, 비권장). 본 가이드는 **옵션 B를 기본안**으로 명세하되(가장 작고 canonical 시그니처 정합), 옵션 A/C 전환 조건을 §8·미해결질문에 명시한다.

### W2 슬라이스(BAL-2) 내 역할/의존
- BAL-16은 의존 DAG(orchestration §1)에서 **W2-2 어댑터 4-way 병렬**의 한 갈래(BAL-13 us ∥ BAL-14 fx ∥ BAL-15 regime ∥ **BAL-16 etf**). 파일 비중복(`etf.py` 단독)이라 충돌 0.
- 의존: `app/tickers.CORE_ETF_WHITELIST`(W1, 읽기 전용). 그 외 W2 공유파일(`models.py`/`db.py`/`regime.py`)을 **닿지 않는다**(orchestration §1 표: BAL-16 공유파일 닿음 = 없음).
- 하류 소비자: 본 슬라이스에서는 없음(옵션 B의 `is_core_etf`는 W3 metrics core-sat 판정 또는 collect가 잠재 소비자이나 W2 collect는 `classify_category`/영속 `category` 컬럼을 직접 쓴다 — 04 §8.2엔 etf 호출 없음).

---

## 2. 영향 파일

| 파일 | 동작 | 비고 |
|---|---|---|
| `app/sources/etf.py` | **수정**(스텁→구현) | 본 이슈 본체. 옵션 B = `is_core_etf(ct)` 단일 함수. ⚠️ 옵션 A 채택 시 **무변경**(stub 유지) |
| `tests/test_etf.py` | **신규** | 본 가이드 §6 테스트(옵션 B 채택 시). 옵션 A면 미작성 |
| `app/tickers.py` | **읽기 전용 의존** | `CORE_ETF_WHITELIST` import. **변경 절대 금지**(W1 정본, Surgical) |

> 외부 네트워크/API 의존 **없음**(옵션 B는 순수 frozenset 멤버십). 룩스루(pykrx PDF / 발행사 CSV)를 당기지 않는 한 모킹 대상도 없다 — 룩스루를 당기는 옵션 C에서만 외부 API 모킹이 발생(§6 말미).

---

## 3. 구현 단계

> 하위작업 분해: **없음**(orchestration §1 표 "하위작업 = 없음"). ⚠️ **ETF 코어판정/룩스루(KR PDF·US CSV)는 스코프 모호** — 아래는 옵션 B(기본안) 기준. 착수 전 §1 U1 사용자 결정 확인.

### 단계 0 — 스코프 게이트(필수 선행)
구현 전 U1을 사용자에게 확인한다. **옵션 A(R2 연기)면 단계 A~C를 건너뛰고 stub 유지** → 본 이슈는 "스코프 확정 + 문서화"만으로 DoD 충족(§7 참조). 옵션 B면 단계 A~C 진행. 옵션 C(룩스루 당김)는 본 가이드 범위 밖 → 별도 R2 dev-guide 필요.

### 단계 A — `is_core_etf(ct)` (옵션 B, orchestration §2.4)
`CORE_ETF_WHITELIST` 멤버십을 ct 기준으로 위임하는 얇은 함수. canonical 시그니처(orchestration §2.4) 그대로.
```python
from app.tickers import CORE_ETF_WHITELIST


def is_core_etf(ct: str) -> bool:
    """canonical_ticker가 코어 ETF 화이트리스트 소속인지 판정 (G4, 04 §5.2).

    W1 classify_category(tickers.py:55-56)의 코어 판정과 동일 기준의
    ct→bool 단일 진입점. 화이트리스트 밖 ETF/개별주/현금은 모두 False.
    """
    return ct in CORE_ETF_WHITELIST
```
핵심 로직: `classify_category`(`tickers.py:49-57`)는 `HoldingInput`을 받아 `core/satellite/None`을 내지만, `is_core_etf`는 **ct 문자열만** 받아 bool을 낸다(입력형·반환형이 다른 보강 진입점). 화이트리스트는 W1 정본을 그대로 참조 — etf.py에 값을 **복제하지 않는다**(SSoT 단일화, drift 방지).
- **검증 포인트**: `is_core_etf("069500") is True`(KODEX 200), `is_core_etf("VOO") is True`, `is_core_etf("005930") is False`(개별주), `is_core_etf("TQQQ") is False`(화이트리스트 밖 레버리지 ETF).

### 단계 B — 발행사 메타 확인(보강) — ⚠️ 정본 시그니처 부재, 미구현 권장
orchestration §2.4가 언급한 "화이트리스트 밖 ETF의 발행사 메타 확인"은 04/05/01에 **시그니처·반환 스키마·데이터소스가 정의되어 있지 않다**(05엔 etf 테이블 없음 — `grep` 확인: 05엔 etf 구성용 컬럼/테이블 전무). 정본 없는 시그니처를 발명하지 않는다(orchestration §2 드리프트 방지 규칙). → **본 단계는 구현하지 않는다**. 필요 시 R2에서 F-19 룩스루와 함께 스키마를 정의 후 착수.

### 단계 C — `py_compile` + 단위 테스트 그린
편집 후 `python3 -m py_compile app/sources/etf.py`(degraded-session 수동 대체, orchestration §4) → `pytest -q tests/test_etf.py`.
- **검증 포인트**: §7 DoD 체크리스트 통과.

---

## 4. 인터페이스 (정본 = orchestration §2.4, 그대로 구체화)

> 새 시그니처 발명 금지. 아래는 §2.4 시그니처를 파라미터/반환형/예외 수준으로만 구체화한 것이며, §2.4 텍스트와 1:1 대응한다.

```python
# 옵션 B (기본안):
def is_core_etf(ct: str) -> bool: ...
#   ct = canonical_ticker(예: '069500','VOO','005930'). 반환: 화이트리스트 멤버십 bool.
#   데이터소스: app.tickers.CORE_ETF_WHITELIST(W1, frozenset). 외부 네트워크 없음.
#   예외: 없음(멤버십 검사). None/비문자 ct는 caller 책임(타입주석으로 str 강제).

# 옵션 A (R2 연기): 변경 없음 — etf.py는 1줄 docstring stub 유지.
```

**§2.4와의 정합 확인**:
- `is_core_etf(ct: str) -> bool` — orchestration §2.4와 자모 단위 일치(함수명·파라미터명·반환형).
- §2.4의 "발행사 메타 확인" 보강 함수는 **시그니처 미명시**(orchestration도 표현으로만 둠) → 정본 부재이므로 구현하지 않음(단계 B). 발명 금지 원칙 준수.
- 룩스루 분해 함수(`def lookthrough(...)` 등)는 §2.4가 **명시적으로 R2 배제**(`:111`, `:116`) → 본 인터페이스에 포함하지 않음.

---

## 5. 엣지 & 리스크

| # | 상황 | 영향 | 대응 (본 모듈) |
|---|---|---|---|
| E1 | **코어 판정 SSoT 이중화** | etf.py가 화이트리스트를 복제하면 W1 `tickers.py`와 drift | 화이트리스트 값을 **복제 금지** — `from app.tickers import CORE_ETF_WHITELIST`로 단일 참조. etf.py는 위임만 |
| E2 | **`is_core_etf` vs `classify_category` 책임 중복** | 두 진입점이 코어 판정을 각자 해석 | 동일 기준(`ct in WHITELIST`) 유지. `classify_category`는 `HoldingInput`+enum 우선순위(사용자 명시 우선) 처리, `is_core_etf`는 순수 ct→bool. 둘이 다른 답을 내지 않도록 **같은 frozenset만 참조** |
| E3 | **룩스루를 끌어들임**(F-19) | R2 범위(01:248) 침범, 외부 PDF/CSV 의존·스키마 추가로 슬라이스 폭발 | W2 배제(orchestration §6 "룩스루 ETF 비중 분해(F-19) — BAL-16은 코어 판정 보강만"). 당기려면 사용자 R2 승격 결정 필요 |
| E4 | **05에 etf 테이블 없음** | 룩스루 결과를 적재할 곳 자체가 없음(grep 확인: 05 전무) | 룩스루는 R2에서 테이블 DDL 신규 정의 후 착수. W2는 적재 없음 |
| E5 | **None/대소문자 ct 입력** | `is_core_etf(None)`/`is_core_etf("voo")` 오판 | 타입주석 `ct: str`로 None 방어(caller 계약). 정규화는 `tickers.to_source`/입력단 책임 — etf.py는 canonical(대문자 US/6자리 KR) 기준으로 받음(01 캐시 PK = canonical) |
| E6 | **실질 산출 0** | 옵션 B의 `is_core_etf`가 `classify_category`와 거의 동어반복 → "왜 이 이슈가 있나" | U1 사용자 결정으로 옵션 A(연기) 가능. 본 가이드는 두 경로 모두 DoD 명세(§7) |

---

## 6. 테스트 계획

**파일: `tests/test_etf.py`** (pytest, `@pytest.mark.unit` — 옵션 B는 순수 frozenset 멤버십, **외부 네트워크 없음 → 모킹 대상 없음**).

> 옵션 A(R2 연기) 채택 시 본 파일 미작성(테스트할 신규 코드 없음).

| 테스트명 | 검증 대상 | 핵심 단언 |
|---|---|---|
| `test_is_core_etf_kr_whitelist` | 단계 A (KR 코어) | `is_core_etf("069500") is True`, `is_core_etf("360750") is True`, `is_core_etf("379800") is True` |
| `test_is_core_etf_us_whitelist` | 단계 A (US 코어) | `is_core_etf("VOO") is True`, `is_core_etf("SPY") is True`, `is_core_etf("VT") is True` |
| `test_is_core_etf_individual_stock` | 단계 A (개별주) | `is_core_etf("005930") is False`, `is_core_etf("AAPL") is False` |
| `test_is_core_etf_non_core_etf` | 단계 A (화이트리스트 밖 ETF) | `is_core_etf("TQQQ") is False`(레버리지), `is_core_etf("ARKK") is False`(액티브) |
| `test_is_core_etf_single_source_of_truth` | E1 (SSoT 단일화) | `etf.CORE_ETF_WHITELIST is tickers.CORE_ETF_WHITELIST`(동일 객체 참조 — 복제 아님). 또는 `is_core_etf`가 화이트리스트 전체 멤버에 True, 비멤버 샘플에 False |
| `test_is_core_etf_consistent_with_classify_category` | E2 (책임 정합) | 모든 화이트리스트 ct에 대해 `is_core_etf(ct)` == (`classify_category(HoldingInput(instrument="etf", canonical_ticker=ct, category=None)) == "core"`) |

> ⚠️ **외부 API 전량 모킹 원칙**: 옵션 B엔 외부 호출이 없어 모킹이 불필요하다. **룩스루를 당기는 옵션 C에서만** 외부 API(pykrx ETF PDF / 발행사 CSV / etf-scraper)가 등장하며, 이때는 `monkeypatch`/`unittest.mock`으로 네트워크·파일 fetch를 **전량 모킹**하고 실제 호출 0을 보장해야 한다(orchestration §4 degraded-session: `.venv` 신규 라이브러리 수동 검증). 옵션 C는 본 가이드 범위 밖.

---

## 7. DoD (Definition of Done)

> ⚠️ **선행**: U1 스코프 결정. 아래는 채택 옵션에 따라 분기.

**옵션 B(코어 판정 보강 — 기본안) 채택 시:**
- [ ] `app/sources/etf.py`에 `is_core_etf(ct: str) -> bool` 구현(orchestration §2.4 시그니처 정합).
- [ ] 화이트리스트는 `app.tickers.CORE_ETF_WHITELIST` **단일 참조**(복제 없음, E1).
- [ ] `is_core_etf`가 W1 `classify_category`의 코어 판정과 동일 기준(같은 frozenset)임을 테스트로 보장(E2).
- [ ] `tests/test_etf.py` 전 케이스 green, 외부 네트워크 호출 0(모킹 불필요).
- [ ] `pytest -q` green, `python3 -m py_compile app/sources/etf.py` 통과(degraded-session 수동 대체, orchestration §4).
- [ ] 코딩 규칙 준수: PEP8 + 전 함수 타입주석. `print()` 미사용. `app/tickers.py` **무변경**.

**옵션 A(R2 연기) 채택 시:**
- [ ] `etf.py` stub 유지(무변경)임을 명시 — 코어 판정이 W1 `tickers.py`에서 종료되어 W2 신규 산출이 없음을 근거(01:42 AC4·05:80)로 문서화.
- [ ] 룩스루(F-19)를 R2 백로그로 이관(01:248) 확인.
- [ ] 본 이슈를 "스코프 명료화 완료"로 종결(코드 변경 0, DoD = 결정 기록).

> ⚠️ **W2 통합 DoD(orchestration §5)에 BAL-16은 직접 항목 없음** — §5는 us/fx/regime/collect 중심이며 etf는 룩스루 배제로 통합 게이트에 미참여. 본 이슈 DoD는 위 두 분기로 자족 완결.

---

## 8. Out of scope (W2 / BAL-16 아님)

- **룩스루 ETF 비중 분해(F-19)** — R2(01:248, 정확도 확장). KR pykrx ETF PDF 구성종목 / US 발행사 공식 CSV·etf-scraper 분해, 비중 계산, 적재 테이블 신규 DDL 전부 R2. (orchestration §6 명시)
- **`classify_category` 수정·`CORE_ETF_WHITELIST` 갱신** — W1 BAL-9 소유(`tickers.py`). 화이트리스트 종목 추가/변경은 별도 이슈(Surgical, 본 이슈 무변경).
- **`collect.py` 통합·`collect_run` 로깅** — BAL-17(W2-3). 04 §8.2 `_collect_market`은 etf.py를 호출하지 않음(영속 `category` 컬럼·`classify_category`로 충족).
- **metrics core-satellite 판정·드리프트 계산** — W3(04 §9). `is_core_etf`의 잠재 소비자이나 본 슬라이스 밖.
- **`models.py`/`db.py`/`regime.py` 등 W2 공유파일** — orchestration §1 표: BAL-16 공유파일 닿음 = 없음. 본 이슈는 닿지 않음.
- **US/FX/regime 어댑터, LLM/Card DTO, 프론트, 손익/수익률(W-01)** — orchestration §6.

---

## 미해결 질문
(04/05/01 간 명시 불일치 또는 미정의 — 본문에 임의 가정을 주입하지 않고 모았다. orchestration §7 U1과 정합.)

1. **(U1, 블로커) BAL-16 W2 스코프 — 옵션 A vs B vs C**: 코어 판정은 W1 `tickers.py:41-57`에서 이미 종료(01:42 AC4·05:80), 룩스루는 R2(01:248). 따라서 BAL-16의 W2 실질 산출이 **0에 수렴**한다. 본 가이드 기본안은 **옵션 B**(`is_core_etf` 얇은 위임 — 가장 작고 §2.4 시그니처 정합)이나, `classify_category`와 거의 동어반복이라 **옵션 A(이슈를 R2로 연기, stub 유지)** 가 더 정직할 수 있다. **옵션 C(룩스루 일부 W2로 당김)** 는 R2 범위(01:248)를 침범하므로 사용자의 명시적 R2 승격 결정이 없으면 비권장. → **착수 전 사용자 스코프 결정 필수**.
2. **`is_core_etf` 소비자 부재 — 실효성 확인**: orchestration §2.4는 `is_core_etf`를 명세하나 04 §8.2 collect는 etf.py를 호출하지 않고(영속 `category` + `classify_category` 사용), metrics는 W3이다. 즉 옵션 B 구현 시 W2 시점엔 **호출처가 없는 함수**가 된다. W3 metrics가 ct→bool 단일 진입점을 실제로 쓸지 확인되면 옵션 B 정당화, 아니면 옵션 A가 우세.
3. **"발행사 메타 확인"(orchestration §2.4) 정본 부재**: §2.4가 "화이트리스트 밖 ETF의 발행사 메타 확인(보강)"을 언급하나 04/05/01에 시그니처·반환 스키마·데이터소스·적재 테이블이 **전무**(05엔 etf 테이블 없음). 정본 없는 시그니처 발명 금지 원칙상 단계 B는 미구현. R2에서 F-19와 함께 스키마 정의 필요 — 그때 본 항목 해소.

---
> ⚠️ **TECH-DESIGN.md 부재 재확인**: W1 dev-guide 일부가 `§15.x`를 인용하나 해당 파일은 레포에 없다. 본 가이드는 04/05/01만 인용했고 `§15` 참조를 답습하지 않았다. 시그니처 정본 = orchestration §2.4(v1). W1 구현 정본 = `docs/BAL-1-m1a-orchestration.md §2(v2)` + `docs/BAL-1-m1a-decisions.md`.
