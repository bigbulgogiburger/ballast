# BAL-2 / W2 미해결 결정 종합 (Decisions SoT)

> 생성: 교차 일관성 점검 워크플로(ultrathink). 대상: BAL-13·BAL-14·BAL-15·BAL-16·BAL-17 dev-guide + `docs/BAL-2-w2-orchestration.md`의 미해결 질문 해소.
> 본 문서는 5개 이슈의 결정을 **contract 기준으로 교차 단일화**한 정본이다. 충돌·중복은 SoT 우선순위로 재정렬했고, 문서로 못 정하는 **제품 판단은 needs_user로 분류**(임의 가정 금지)했다.
> 구조: `docs/BAL-1-m1a-decisions.md` 답습 — §1 이슈별 결정표 + §3 교차결정(충돌 단일화) + §4 needs_user.

## 0. 머리말

### 0.1 목적
W2 데이터 슬라이스(BAL-2, 약 30종목 일배치 수집 증명)에 필요한 미해결 결정을 단일 문서로 종합하고, 이슈 간 모순을 contract 기준으로 해소한다. 각 결정은 wave(W2-1 / W2-2 / W2-3)로 태깅되어 실행 순서(orchestration §3)와 정합한다.

### 0.2 SSoT(정본) 우선순위
1. `docs/04-backend.md` (최우선)
2. `docs/05-database.md`
3. `docs/01-product-spec.md`
4. **seam 시그니처 정본** = `docs/BAL-2-w2-orchestration.md §2 (v1, canonical)` — W2 어댑터/collect/db 헬퍼 시그니처는 §2가 정본. W1 구현 정본 시그니처는 `docs/BAL-1-m1a-orchestration.md §2(v2)` + `docs/BAL-1-m1a-decisions.md`.

> ⚠️ **`TECH-DESIGN.md`는 레포에 없음**. W1 dev-guide 일부가 인용한 `§15.x`는 **부재 파일**이므로 본 문서·W2 구현은 04/05/01만 정본으로 쓰고 `§15` 참조를 답습하지 않는다(orchestration §7 말미 재확인).

### 0.3 점검 결과 요약
- 사용자가 지정한 6개 해소 타깃 전부 처리: (1) BAL-16 ETF 스코프, (2) db W2 upsert 헬퍼 소유, (3) FxRate DTO 정의 위치/타입, (4) validate_response 날짜검사 W2, (5) regime.py us_cape 출처, (6) US 시세 소스 폴백 체인 트리거.
- 교차 충돌/중복 **6건** → 전부 SoT 기준 단일화(§3).
- **needs_user 2건**: U1(BAL-16 스코프 — 제품/백로그 판단), U6(db 헬퍼 이슈 귀속 — 오케스트레이션 정책 판단). 나머지는 contract 내 확정.
- dev-guide의 라이브러리 사실 불확실 항목(ECB 합성식·Yale xls 시트 구조·yfinance 컬럼 등)은 "가장 그럴듯한 결정 + 구현 시 1줄 검증"으로 §1 표에 동봉했다(코드 시그니처 불변 → 블로커 아님).

---

## 1. 이슈별 결정 표

### 1.1 BAL-13 (`app/sources/us.py`) — US 시세·펀더·뉴스 어댑터

| # | 질문(요약) | 결정 | 근거(정본) | wave |
|---|---|---|---|---|
| Q1 | **US 시세 소스 폴백 체인 트리거 조건** (사용자 타깃 6) | **빈/무효 응답 기반 트리거**(키 부재 기반 아님). 1차 Stooq `DataReader` → 빈 DF면 2차 yfinance `auto_adjust=True` → 시계열 여전히 비면 보조 Finnhub `/quote`(당일가만, week52/sma200=None). 전 소스 빈 → `validate_response(rows=0)`이 `EmptyResponseError`. "예외 안 남 ≠ OK"(05:209) — 빈 CSV는 폴백 트리거지 성공 아님. ⚠️ **KR(kr.py)와 비대칭**: KR은 @retry(3)가 빈응답을 흡수 후 FDR 폴백, US는 소스 **간** 폴백이 @retry 안쪽 순차 시도. | 04 §7.3 표(1차 Stooq / 2차 yfinance·Finnhub /quote 보조 — **순서만 규정, 트리거 조건은 미명시**). 04 §7.1 `validate_response` rows==0 가드 + 05:209 "데이터 실재" OK 판정. kr.py FDR 폴백(빈 DF→다음 소스) 패턴 미러. | W2-2 |
| Q2 | `close_raw`/`close_adj` 분리 소스(yfinance 1콜 2컬럼 vs 2콜) | **구현자 1택 고정**(계약 불변). 권장: yfinance `auto_adjust=True/False` 2회 또는 1콜 `Close`/`Adj Close` 2컬럼 — yfinance 버전 확인 후 고정. Stooq Close=close_raw, 조정가는 yfinance 우선, 둘 다 실패 시 `close_adj=close_raw`+`log.warning`(kr.py FDR 정직성 규약 미러). `OHLCV.close_raw`/`close_adj` 분리는 05 §1.3 강제. | 04 §7.3 'auto_adjust=True', 05 §1.3 raw/adj 분리. kr.py:46-49 2회 호출 패턴. (BAL-13 미해결 #1·#2 — 시그니처 불변 내부 디테일.) | W2-2 |
| Q3 | Finnhub `/quote` 보조의 trade_date | **응답 timestamp(`t`) 변환 사용**(date.today() 아님). 이유: W2 collect 경로 날짜검사(§3.4)의 `latest==expected` 비교가 today 하드코딩이면 휴장·시차에 거짓 일치/불일치. 미제공 시 `date.today().isoformat()` fallback + 주석. | 04 §7.1 'latest=최신일자'. §3.4 collect 날짜검사 정합. (BAL-13 미해결 #3.) | W2-2 |
| Q4 | EDGAR `report_date` 매핑(filing date vs period-of-report) | **period-of-report(재무 실제 기준일) 사용**. filing date는 제출일이라 신선도 배지(05 §3.3 'report_date=재무 실제 기준일')를 오판. edgartools 진입점에서 period 추출, 미확보·실패 시 `report_date=None` degrade(시세/펀더는 살림). | 04 §7.3 'SEC EDGAR 보조', models.py:57 'report_date=재무 실제 기준일'. W1 BAL-9 Q9(pykrx 날짜≠재무 기준일 오용 금지)와 동일 철학. (BAL-13 미해결 #4.) | W2-2 |
| Q5 | PER/PBR 자체 재계산(가격×EPS) | **금지**(제공자 FMP 계산값만 캐시). SSoT §5 위반(이중 진실). 적자/표본부족/한도 시 해당 필드 None(degrade), 라벨링은 W3 metrics. | 04 §7.3 degrade 규칙 'PER/PBR은 제공자 계산값만 캐시, 자체 가격×EPS 재계산 금지'. | W2-2 |
| Q6 | week52/sma200 윈도우 부족 시 None | **`OHLCV.week52_*`/`sma200`은 `float|None`**(W1 §3.5 확장 그대로 재사용, US 신규편입 워밍업에서 None 경로 실제 발현). 윈도우<200→sma200=None, <252→week52=None, +log.warning. | W1 decisions §3.5(OHLCV 타입 확장), 05 §1.3 REAL NULL. **W1에서 이미 확정 — W2 신규 결정 아님**(재확인). | W2-2 |
| Q7 | 키 부재 처리(FMP/Finnhub) | **`raise KeyError`**(사용 시점 fail-fast, 조용한 빈 결과 금지). collect가 종목 격리로 `missing_tickers` 기록. W1은 'fail-fast 계획'이었고 **실제 구현이 W2 어댑터**(orchestration §4). | 04 §2 '필수 키 누락=즉시 실패', kr.py:138-139 패턴. | W2-2 |

### 1.2 BAL-14 (`app/sources/fx.py` + `models.FxRate`) — FX 어댑터

| # | 질문(요약) | 결정 | 근거(정본) | wave |
|---|---|---|---|---|
| Q1 | **FxRate DTO 정의 위치/타입** (사용자 타깃 3) | **`app/models.py` 끝(RegimeRow 다음)에 `@dataclass(frozen=True) FxRate(trade_date: str, pair: str, rate: float)` 신규**. 필드명=`fx_snapshot` 컬럼 **전체명**(asdict named-bind 1:1). **W1 models.py에 미정의 → W2-1 공유파일 선커밋**(BAL-14 소유). W1 decisions §3.8 연속: W1은 FxRate를 명시적 W2로 유보했고 `upsert_fx`를 dict-surface로 둠 → 본 이슈가 그 유보를 해제한다. | 05 §1.5 fx_snapshot DDL(trade_date/pair/rate, PK(trade_date,pair)). W1 decisions §3.4(전체명 named param)·§3.8(FxRate=W2). orchestration §2.2 코드블록. | W2-1 |
| Q2 | 1차 소스 우선순위(ECOS vs ECB) | **ECB 1차·ECOS 보조·yfinance 2차**. 04 §7.4는 "ECOS / ECB"를 **동급 1차**로 병기 → 그 안에서 ECB를 먼저 쓰는 것은 04 위반 아님(orchestration §2.2 지시). ECOS는 `config.ECOS_API_KEY` 보유 시만 보조 경로(키 없으면 skip, 에러 아님 — config.py:29 선택 키). | 04 §7.4(ECOS/ECB 동급 1차 병기 + yfinance 2차), orchestration §2.2. (BAL-14 미해결 U2 — 04 동급군 내 우선순위 고정, 충돌 아님.) | W2-2 |
| Q3 | ECB USDKRW 직접 제공 여부 + 합성식 | **구현자 실측 확정**(시그니처 불변). ECB SDW는 통상 EUR 기준 → `USDKRW = (KRW/EUR) ÷ (USD/EUR)` 합성. 합성 입력 중 하나라도 결측 → `_from_ecb()=None`(폴백 유도). 부담스러우면 yfinance를 사실상 1차로 강등도 04(동급군) 위반 아님. | 04 §7.4 'ECB'(엔드포인트·합성식 미명시). (BAL-14 미해결 U1 — 외부 운영 디테일, 블로커 아님.) | W2-2 |
| Q4 | 무효 응답(rate=0/음수/NaN/None) 처리 | **그 소스를 실패로 간주 → 다음 폴백**. 마지막까지 유효 rate 없으면 raise. **0/NULL FxRate 위장 절대 금지**(05:162 "NULL 분모 제외 금지=산출 거부"). collect가 `collect_run(FX,FAIL)` 기록 → USD 자산+현금 보류. | 05:162-163, 04 §7.4 '둘 다 실패→raise'. | W2-2 |
| Q5 | rate 단위/방향 | **USD 1단위 = KRW**(예: 1380.5). `pair="USDKRW"` 고정. yfinance `KRW=X`가 이 방향. ECB 합성도 동일 방향 산출 검증. | 05 §1.5 rate REAL, 04 §7.4 의도. | W2-2 |
| Q6 | trade_date 소스 불일치 | **채택 소스의 자체 기준일 사용**. `fx_snapshot`은 `MAX(trade_date)` fallback 조회(05:162)라 약간 과거여도 정상 흡수. | 05:162 MAX fallback. (BAL-14 미해결 U4 — 블로커 아님.) | W2-2 |
| Q7 | `upsert_fx` FxRate 전환 귀속 | **§3.5(db 헬퍼 소유)에 종속**. BAL-14는 FxRate 필드명을 컬럼 전체명으로 고정(전환 선행조건)까지. `dict(row)`→`asdict(row)` 본체 전환은 db 헬퍼 소유 이슈(§3.5/U6) 소관. | orchestration §2.6/U3. (BAL-14 미해결 U3.) | W2-1 |

### 1.3 BAL-15 (`app/sources/regime.py`) — 레짐 US 절반(us_cape)

| # | 질문(요약) | 결정 | 근거(정본) | wave |
|---|---|---|---|---|
| Q1 | **us_cape 출처(Shiller CAPE 데이터 소스)** (사용자 타깃 5) | **Yale `ie_data.xls`(1차) → multpl 스크레이프(2차)**. quandl·하드코딩 fallback은 **채택 안 함**(SoT 미언급 + 하드코딩=stale 값 위험, 04 §7.1 '조용한 실패 OK 오인 금지' 철학 위반). 둘 다 실패 → `us_cape=None`(한쪽 NULL, AC3). 키 불필요(04 §7.5 'regime 키 불필요'). | 04 §7.5 표('Shiller CAPE: 1차 Yale ie_data.xls / 2차 multpl 스크레이프'), 05 §1.7 'US=CAPE'. **04는 Yale·multpl만 명시 — quandl/하드코딩 출처 없음**. | W2-2 |
| Q2 | 수정 지점(단일 집중 블록) | **`regime()` 내 `us_cape=None`(현행 regime.py:28) 한 줄만 교체** + 모듈 private `_fetch_us_cape()` 신규. **`kospi_pbr` 블록(regime.py:24)·`as_of`(regime.py:26)·import·클래스 구조 절대 불변**(Surgical). | decisions(W1) Q10, orchestration §2.3 'kospi_pbr 절대 손대지 않음'. 현행 regime.py:20-29 확인. | W2-2 |
| Q3 | 한쪽 실패 시 동작 | us_cape fetch는 `regime()` 내부 try/except(`@retry` **안쪽**) → us_cape만 실패해도 메서드 성공 반환(us_cape=None, kospi_pbr 보존). kospi_pbr fetch(pykrx) 실패는 `@retry(3)` 소진 후 메서드 raise → collect degrade. | 04 §7.5 '한쪽만 실패→그 필드만 NULL', W1 decisions Q10. | W2-2 |
| Q4 | Yale xls 시트/컬럼 구조 | **구현자 실측 후 상수 고정**. 최신 비결측 CAPE 취득, NaN 행 skip, 비결측 없으면 raise(빈응답 OK 오인 금지). multpl 2차는 PE 페이지 현재값. | 04 §7.5(파일만 명시, 시트명·컬럼 미명시). (BAL-15 미해결 R2 — 시그니처 불변 내부 디테일.) | W2-2 |
| Q5 | 월단위 캐시 위치 | **§3.6(regime 월단위 skip)에 종속**. 어댑터는 캐시 미도입(collect DB row 체크 단일). | 04 §7.5 '월단위 캐시'. (BAL-15 R1 = orchestration U5 = §3.6.) | W2-2 |

### 1.4 BAL-16 (`app/sources/etf.py`) — ETF 코어 판정 보강

| # | 질문(요약) | 결정 | 근거(정본) | wave |
|---|---|---|---|---|
| Q1 | **BAL-16 ETF 스코프(코어 판정 보강 vs 룩스루)** (사용자 타깃 1) | **W2 범위에서 룩스루(F-19)는 배제 확정**(R2 이관). 코어 판정 자체는 W1 `tickers.py:41-57`(CORE_ETF_WHITELIST+classify_category)에서 **이미 종료**. 따라서 BAL-16 W2 실질 산출이 0에 수렴 → **이슈 자체를 R2로 미룰지(옵션 A) vs `is_core_etf` 얇은 위임만 추가(옵션 B)는 needs_user**(§4 U1). 문서로는 "룩스루 배제"까지만 확정 가능, A/B는 제품/백로그 판단. | 01:109(F-19=§5, Could), **01:248(R2=룩스루 정확도 확장)** → R1 PoC 밖. tickers.py:41-57(W1 코어 판정 보유). 05엔 etf 테이블 전무(grep). | W2-2(옵션 B) / R2(옵션 A) |
| Q2 | (옵션 B 채택 시) `is_core_etf` 구현 | `def is_core_etf(ct: str) -> bool: return ct in CORE_ETF_WHITELIST`. 화이트리스트는 `from app.tickers import CORE_ETF_WHITELIST` **단일 참조**(복제 절대 금지, SSoT drift 방지). classify_category(HoldingInput→core/sat/None)와 **같은 frozenset**만 참조해 답 불일치 차단. | orchestration §2.4 시그니처. tickers.py:41-46. | W2-2 |
| Q3 | "발행사 메타 확인"(orchestration §2.4) 구현 | **미구현**(정본 부재). 04/05/01에 시그니처·반환 스키마·데이터소스·적재 테이블 전무 → 정본 없는 시그니처 발명 금지(orchestration §2 드리프트 방지). R2에서 F-19와 함께 스키마 정의 후 착수. | orchestration §2 발명 금지. (BAL-16 미해결 #3.) | R2 |

### 1.5 BAL-17 (`app/collect.py` + db W2 헬퍼) — 일배치 통합자

| # | 질문(요약) | 결정 | 근거(정본) | wave |
|---|---|---|---|---|
| Q1 | **validate_response 날짜검사 W2 추가 여부/소유** (사용자 타깃 4) | **W2에서 날짜검사(`latest != expected`) 추가하되 소유=`_collect_market` 인라인**(가드 본체 불변). 즉 `validate_response`는 W1대로 rows==0만, collect가 `ohlcv.trade_date != expected.isoformat()`을 자체 비교해 raise→종목 격리/PARTIAL. 04 §7.1 docstring이 "행수>0 AND 최신일자 일치(±허용)"를 명시하나 본체는 rows==0뿐 → 날짜검사 추가는 정당, 위치는 §3.4가 인라인으로 단일화. | 04 §7.1(docstring '최신일자 일치', 본체 rows==0), W1 decisions §3.7/Q12('stale 대조는 collect.py'). §3.4 교차결정. (BAL-17 미해결 U2 = orchestration U2.) | W2-3 |
| Q2 | `_collect_*` conn 전달 | **`run_collect`이 `db.connect()` 1회 → 격리 함수에 인자 전달**(전역 conn 아님). orchestration §2.5 시그니처에 `conn` 추가는 superset(타입 추가, 의미 모순 없음 — W1 BAL-8 conn 좁히기 선례). 헬퍼 self-commit 전제(종목 격리와 정합). | orchestration §2.5, W1 db.py self-commit 패턴. (BAL-17 미해결 U-conn.) | W2-3 |
| Q3 | `upsert_regime` vs `upsert_market_regime` 명칭 | **`upsert_market_regime` 채택**(테이블명 정합). 04:530 `upsert_regime`은 약식 예시 코드, 05 §1.7 테이블=`market_regime` + orchestration §2.6이 W2 db seam 정본으로 `upsert_market_regime` 못박음. 04:530은 오기로 처리. | 05 §1.7, orchestration §2.6. (BAL-17 미해결 U6.) | W2-1 |
| Q4 | `_status_of` 분기 수(4 vs 5) | **`_status_of`=4분기**(`backfill→BACKFILL / n_ok==0→FAIL / n_fail>0→PARTIAL / else→OK`). 5번째 `OK_HOLIDAY`는 `_collect_market`의 거래일 판정 **선분기**(early return)이지 `_status_of` 내부 아님. 05:358-362가 5종 status를 열거하나 OK_HOLIDAY 진입은 별도 경로. | 04 §8.4(:568-577), 05 §1.8 status enum 5종. | W2-3 |
| Q5 | `scripts/run_collect.py --bootstrap` CLI 신규 여부 | **본 이슈 범위=`run_collect(mode='backfill')` 함수 동작까지**. `scripts/` CLI 래퍼 파일 신규는 운영 단계로 보류(W2 PoC는 함수 호출까지면 충분). | 04:373/582(CLI 가정), orchestration §6(운영 단계). (BAL-17 미해결 U7.) | (보류) |
| Q6 | conn 트랜잭션 경계 | **헬퍼 self-commit**(W1 BAL-8 db.py:206/222 선례). 종목 격리와 정합(한 종목 커밋이 다음 종목과 독립). 배치 단일 트랜잭션은 W2 PoC 범위 밖. | W1 decisions Q4(self-commit), 05 §0. | W2-3 |

---

## 2. (db.py W2 헬퍼는 §3.5 교차결정에 통합)

> db W2 upsert 헬퍼(`upsert_fx` 전환 + `upsert_news`/`upsert_market_regime`/`upsert_collect_run` + `auto_holdings`)는 BAL-14·BAL-15·BAL-17이 공유하는 계약면이므로 §3.5 교차결정에서 단일화한다. 별도 절 불필요.

---

## 3. 교차 결정 (이슈 공유 — 충돌 단일화)

여러 이슈가 같은 계약면을 건드린다. 아래는 **SoT 기준 단일 정본**이며, 개별 이슈 결정과 어긋나는 부분은 본 절이 override한다.

### 3.1 FxRate DTO 정의 위치·타입 (BAL-14 ↔ BAL-13/BAL-17 공유) [사용자 타깃 3]
- **단일 결정**: `models.FxRate = @dataclass(frozen=True)`, 필드 `trade_date: str / pair: str / rate: float`(컬럼 전체명). 위치=`app/models.py` 끝, 정의·커밋=**W2-1 선행**(BAL-14 소유). BAL-13(import 가능성)·BAL-17(`upsert_fx` 인자)은 읽기 의존.
- **근거**: 05 §1.5 fx_snapshot 컬럼 1:1. W1 decisions §3.8(FxRate=W2 유보) **연속** — 본 슬라이스가 유보 해제. §3.4 named-bind 1:1(전체명 키)로 db 정합.
- **W1 정합**: W1 `upsert_fx`는 dict-surface(`Mapping[str,Any]`)였고 W1 decisions §3.4/§3.8이 "W2에서 `row: FxRate`+asdict로 통일"을 예고 → 본 결정이 그 예고를 실행. 필드명이 컬럼 전체명이라 W1 `dict(row)`와도 키 호환(전환 무중단).
- **검증 1줄**: `dataclasses.asdict(FxRate("2026-06-03","USDKRW",1380.5)).keys() == {"trade_date","pair","rate"}`(05:154-160 컬럼명 == DDL).

### 3.2 us_cape 데이터 출처 (BAL-15) [사용자 타깃 5]
- **단일 결정**: Shiller CAPE = **Yale `ie_data.xls`(1차) → multpl 스크레이프(2차)**. quandl·하드코딩 fallback **불채택**.
- **근거**: 04 §7.5 표가 1차/2차를 Yale·multpl로 **명시적으로 고정**(다른 출처 미언급). 05 §1.7 'US=CAPE(월단위)'. quandl은 SoT 어디에도 없고(추측 금지), 하드코딩 fallback은 04 §7.1 '조용한 실패를 OK로 오인 금지' 및 05:209 '데이터 실재' 원칙과 충돌(stale 상수가 OK처럼 적재됨). 둘 다 실패는 `us_cape=None`(정직한 NULL)이 정본이지 하드코딩 상수가 아님.
- **검증 1줄**: `_cape_from_yale` mock=raise + `_cape_from_multpl` mock=29.1 → `_fetch_us_cape()==29.1`; 둘 다 raise → `regime().us_cape is None`(kospi_pbr 보존).

### 3.3 US 시세 폴백 체인 트리거 조건 (BAL-13) [사용자 타깃 6]
- **단일 결정**: 폴백 트리거 = **빈/무효 응답**(소스 호출이 빈 DataFrame/시계열 0행/무효값 반환). 키 부재는 트리거가 아니라 **fail-fast `KeyError`**(§1.1 Q7). 순서: Stooq → (빈) yfinance → (빈) Finnhub `/quote` 보조(당일가, week52/sma200=None) → (전 소스 빈) `validate_response(rows=0)` → `EmptyResponseError`.
- **근거**: 04 §7.3 표가 **순서만** 규정하고 트리거 조건은 미명시 → 04 §7.1 `validate_response`(rows==0 + docstring '최신일자 일치') + 05:209('OK=예외 안 남이 아니라 데이터 실재')가 트리거 의미를 공급. "빈 CSV는 폴백 사유지 성공 아님"(04 §7.1 'Stooq 빈 CSV 조용한 실패 OK 오인 금지' 직설).
- **비대칭 명시**: KR(kr.py)은 @retry(3)가 KRX 빈응답을 흡수한 뒤 FDR 폴백, US는 **소스 간 순차 폴백이 @retry 안쪽**(Stooq→yf→Finnhub). 둘 다 "빈 응답=다음 소스" 철학은 동일.
- **검증 1줄**: Stooq mock=빈 DF → yfinance mock 경로 진입(yfinance mock 호출됨); 전 소스 빈 → `EmptyResponseError`.

### 3.4 validate_response 날짜검사 W2 추가·소유 (BAL-13 ↔ BAL-17 공유) [사용자 타깃 4]
- **충돌**: 04 §7.1 docstring은 "행수>0 **AND** 최신일자 일치(±허용)"인데 W1 본체는 `if rows==0`뿐. W2에서 날짜검사를 (a) `validate_response` 본체에 추가(공통 가드 변경) vs (b) `_collect_market` 인라인 비교(가드 rows-only 유지). BAL-13은 "가드 그대로 사용"(어댑터는 본체 안 건드림), BAL-17 기본안은 (b) 인라인.
- **단일 결정 (SoT 우선)**: **(b) `_collect_market` 인라인 날짜검사**. `validate_response` 시그니처·본체 불변(W1 rows==0 유지), collect가 `if ohlcv.trade_date != expected.isoformat(): raise`를 종목 루프 try 내부에서 수행 → 실패 시 종목 격리(PARTIAL/missing).
  - **근거**: W1 decisions Q12 "stale 대조는 W2 collect.py(collect_run status PARTIAL/FAIL) 책임" + Q1 "날짜검사는 W2 collect로 이관" 직설. (b)는 more surgical(`sources/__init__` 불변) + collect가 status 판정에 결과를 직접 활용. 04 §7.1 docstring의 '최신일자 일치'는 **계약 의도**이고 그 의도를 collect 레벨에서 실현하는 것이 위반 아님.
  - **(a)를 배제하는 이유**: 본체에 날짜검사를 넣으면 어댑터 단독 호출(`validate_response(rows=1, latest=..., expected=...)`)도 날짜로 raise → 어댑터 단위테스트가 expected 모킹을 강제당함(결합 증가). BAL-13이 "어댑터는 W1 가드 그대로"라 명시한 것과도 정합.
- **검증 1줄**: `_collect_market`에서 `ohlcv.trade_date`가 expected와 다른 모킹 → 해당 종목 n_fail++ & missing 기록(PARTIAL), `sources/__init__.py` 본체는 rows==0만 유지(diff 없음).

### 3.5 db W2 upsert 헬퍼 정의·정합 (BAL-14/BAL-15/BAL-17 공유) [사용자 타깃 2 — 정의/정합]
- **단일 결정 (계약 정의)**: W2 db 헬퍼 4종 + `auto_holdings`를 **W2-1 선커밋**으로 `db.py`에 박는다. 시그니처(orchestration §2.6 canonical):
  - `upsert_fx(conn, row: FxRate) -> None` — W1 dict-surface 본체 재사용, `dict(row)`→`dataclasses.asdict(row)` 전환. 키=컬럼 전체명(§3.1).
  - `upsert_news(conn, rows: list[Headline], ct: str, trade_date: str) -> None` — 05 §1.6, PK(ct,trade_date,url) → `ON CONFLICT DO NOTHING`(url 중복 무시, 05:354).
  - `upsert_market_regime(conn, row: RegimeRow) -> None` — 05 §1.7, `as_of→trade_date`·`us_cape→shiller_cape` 매핑, `ON CONFLICT DO UPDATE`. **명칭=`upsert_market_regime`**(§1.5 Q3).
  - `upsert_collect_run(conn, trade_date, market, status, n_ok, n_fail, missing_tickers) -> None` — 05 §1.8, PK(trade_date,market), `ON CONFLICT DO UPDATE`. `missing_tickers`=caller가 `json.dumps`한 JSON 문자열(헬퍼 재직렬화 안 함).
  - `auto_holdings(conn, user_id: int = 1) -> list` — `tracking='auto'` 행, row는 `.market`/`.canonical_ticker`/`.name` 접근 가능.
- **근거**: 05 §4.1 upsert ON CONFLICT 패턴 + 05:354/364-369. named param 키명=**컬럼 전체명**(W1 decisions §3.4 — 약어 `:ct/:td`는 예시일 뿐, asdict 키 1:1 필수). W1 `db.py:207-223` 패턴 답습.
- **소유(이슈 귀속)는 §4 U6로 분리**: "정의·시그니처·W2-1 선커밋"은 본 절에서 확정하나, **어느 이슈 커밋에 귀속하는가**(BAL-17 슬라이스 vs BAL-8 carryover)는 오케스트레이션 정책 판단 → needs_user.
- **검증 1줄**: `:memory:` + init_schema 후 각 헬퍼 upsert → 되읽기 row 동일(라운드트립). `upsert_market_regime` 호출명이 `upsert_regime` 아님(NameError 회피).

### 3.6 regime 월단위 캐시 위치 (BAL-15 ↔ BAL-17 공유)
- **단일 결정**: **collect `_collect_regime`의 DB row 존재 체크가 단일 skip 지점**(04:528 "이미 이번 달 row 있으면 skip"). regime.py 어댑터는 내부 메모/lru_cache **미도입**(이중화 금지). 어댑터=호출 시 fresh fetch, 월단위 skip=collect 책임.
- **근거**: 04 §7.5 '월단위 캐시'를 04:528 collect month-skip으로 충족(단일 진실). regime.py 내부 캐시는 04:499 표현이나 collect DB 체크가 1차이므로 이중 캐시는 Simplicity 위반.
- **검증 1줄**: `app.sources.regime`에 module-level 캐시 변수/lru_cache 없음(2회 호출 시 fetch 2회 — collect가 skip 담당).

---

## 4. 사용자 확인 필요 (needs_user)

문서(04/05/01/orchestration/decisions)로 **단일 정답을 도출할 수 없는** 제품/정책 판단 2건. 임의 가정을 주입하지 않고 옵션과 trade-off만 제시한다.

### U1 — BAL-16 ETF 이슈를 R2 연기(옵션 A) vs `is_core_etf` 얇은 위임 추가(옵션 B) [사용자 타깃 1]
- **상황**: 코어 판정은 W1 `tickers.py:41-57`에서 종료, 룩스루는 R2(01:248) 확정 배제(§1.4 Q1) → BAL-16 W2 실질 산출이 0에 수렴.
- **옵션 A (R2 연기)**: etf.py stub 유지(무변경), 이슈를 "스코프 명료화 완료"로 종결 + 룩스루를 R2 백로그로 이관. 가장 정직(중복 코드 0).
- **옵션 B (얇은 위임)**: `is_core_etf(ct)->bool` 추가. orchestration §2.4 시그니처 정합이나 `classify_category`와 거의 동어반복이고 **W2 시점 호출처가 없음**(collect는 영속 category 컬럼 사용, metrics는 W3). W3 metrics가 ct→bool 단일 진입점을 실제로 쓸지 확인되면 정당.
- **옵션 C (룩스루 W2 당김)**: R2 범위(01:248) 침범 → 명시적 R2 승격 결정 없으면 비권장.
- **왜 needs_user**: "이슈를 비우는가 / 미래 소비자를 위해 위임 함수를 미리 두는가 / 백로그를 재배치하는가"는 SoT가 답하지 않는 **제품·백로그 우선순위 판단**. 문서로는 "룩스루 배제·코어 판정 W1 종료"까지만 확정 가능.
- **권장 기본안(채택 시)**: 옵션 A(연기) — 동어반복 함수보다 정직. 단 사용자/오케스트레이터 결정 우선.

### U6 — db W2 upsert 헬퍼의 **이슈 귀속** (BAL-17 슬라이스 W2-1 vs BAL-8 db.py carryover) [사용자 타깃 2 — 소유]
- **상황**: 헬퍼 정의·시그니처·W2-1 선커밋은 §3.5에서 확정. 남은 것은 **커밋 귀속**: (a) BAL-17 슬라이스에 포함(collect 의존물이라 응집적, W1 W-1a가 db upsert를 선커밋한 선례) vs (b) BAL-8(db.py 단일 소유 이슈)의 W2 carryover로 분리.
- **왜 needs_user**: "db.py 변경은 그 소유 이슈(BAL-8)만 한다"는 **오케스트레이션/소유권 정책**이 있는지에 따라 갈림 — 문서로 결정 불가(정책 결정).
- **trade-off**: (a)는 수직 슬라이스 응집·리뷰 단순; (b)는 db.py 단일 소유 규율 유지(파일 소유권 명확). 둘 다 산출물·시그니처는 동일(§3.5) — **순수 귀속/커밋 경계 문제**라 구현 결과엔 영향 없음.
- **권장 기본안(채택 시)**: (a) BAL-17 W2-1 선커밋(orchestration §3 답습). 정책 우선 시 (b).

> 그 외 항목(ECB 합성식·Yale xls 구조·yfinance 컬럼·CLI 신규·trade_date 라벨링)은 **시그니처 불변 내부 구현 디테일**로, 구현자 1택 고정이 가능하며 본 슬라이스 진행을 막지 않으므로 needs_user가 아니다(§1 표 결정/근거에 1줄 검증 동봉).

---

## 5. 충돌 점검 결과 (6건, 단일화/분류 완료)

| # | 충돌·모호 | 단일화 결정 | 정본 근거 | 분류 |
|---|---|---|---|---|
| 1 | FxRate DTO 위치/타입(W1 미정의) | models.py 끝 frozen `(trade_date,pair,rate)`, W2-1 선커밋 | §3.1 / 05 §1.5 + W1 §3.8 | 확정 |
| 2 | us_cape 출처(Yale/quandl/하드코딩) | Yale 1차·multpl 2차, quandl·하드코딩 불채택 | §3.2 / 04 §7.5 | 확정 |
| 3 | US 폴백 트리거 조건(미명시) | 빈/무효 응답 트리거(키 부재=fail-fast 별개) | §3.3 / 04 §7.3+§7.1+05:209 | 확정 |
| 4 | validate_response 날짜검사 위치(본체 vs 인라인) | `_collect_market` 인라인(가드 본체 불변) | §3.4 / W1 §3.7+Q12 | 확정 |
| 5 | db W2 헬퍼 정의·명칭(`upsert_regime` 오기) | W2-1 선커밋 4종+auto_holdings, `upsert_market_regime` | §3.5 / 05 §4.1+orch §2.6 | 확정(정의) |
| 6 | BAL-16 스코프 / db 헬퍼 귀속 | 룩스루 배제 확정 + A/B는 needs_user / 귀속 needs_user | §4 U1·U6 | needs_user |

> ⚠️ **TECH-DESIGN.md 부재 재확인**: W1 dev-guide 일부의 `§15.x` 인용은 부재 파일을 가리킨다. 본 문서·W2 구현은 04/05/01 + orchestration §2 + W1 decisions만 인용하고 `§15` 참조를 답습하지 않는다.
