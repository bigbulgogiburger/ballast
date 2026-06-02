# BAL-1 / M1a 미해결 결정 종합 (Decisions SoT)

> 생성: 교차 일관성 점검 워크플로(ultrathink). 대상: BAL-8·BAL-9·BAL-10·BAL-11·BAL-12 dev-guide의 미해결 질문 해소 결정.
> 본 문서는 5개 이슈의 결정을 **contract 기준으로 교차 단일화**한 정본이다. 충돌 항목은 contract 우선순위로 재정렬했다.

## 0. 머리말

### 0.1 목적
W1/M1a 데이터 스파이크(삼성전자 005930 인입 증명)에 필요한 모든 미해결 결정을 단일 문서로 종합하고, 이슈 간 모순을 contract 기준으로 해소한다. 각 결정은 wave(W-1b / W-2a / W-2b / W-3)로 태깅되어 실행 순서와 정합한다.

### 0.2 SSoT(정본) 우선순위
1. `TECH-DESIGN.md §15` (DTO·색·키·런타임 Contract SoT — 충돌 시 최우선)
2. `docs/04-backend.md`
3. `docs/05-database.md`
4. **seam 시그니처 정본** = `docs/BAL-1-m1a-orchestration.md §2 (v2, canonical)` — v2 정정 박스가 04/05의 시그니처 드리프트를 override한다(orchestration §2.1 명시). 따라서 시그니처(예: `connect`) 충돌은 §2 v2로 해소한다.

### 0.3 유보(defer) 0건 선언
본 문서의 모든 항목은 **지금 구체적으로 확정**되었다. W1 범위가 좁아 일반화가 W2인 경우에도 "W1=X(최소 메커니즘), W2=Y(확장)"로 **결정 자체는 박았다**. 미정·추후검토 항목 없음. 라이브러리 사실 불확실 항목은 가장 그럴듯한 결정 + 구현 시 1줄 검증법을 함께 명시했다.

### 0.4 점검 결과 요약
- 교차 충돌 **4건** 발견 → 전부 contract 기준으로 단일화(§3 교차 결정 + 하단 conflicts).
- 사용자 확인 필요(needs_user) **0건**.

---

## 1. 이슈별 결정 표

### 1.1 BAL-8 (`app/db.py`) — DB 토대

| # | 질문(요약) | 결정 | 근거(정본) | wave |
|---|---|---|---|---|
| Q1 | settings seed 값 타입(논리 int/float vs 저장 TEXT) | 저장형=TEXT, seed 시 `str(value)` 변환 적재. seed 출처=`dataclasses.asdict(SETTINGS_DEFAULTS)`(7키). 읽는 쪽이 형변환 책임. 산출값: `base_currency='KRW'`, `monthly_contribution='0'`, `satellite_limit_pct='30'`, `rebalance_band_abs='5'`, `rebalance_band_rel='25'`, `micro_weight_floor='1.0'`, `usd_cash_gate_threshold='5.0'`. `str(1.0)=='1.0'`/`str(5.0)=='5.0'` 소수점 보존. | 05 §1.2 `value TEXT NOT NULL`(저장형 강제). §15.5는 논리 기본값만 규정 → layer 차이지 충돌 아님. `config.py:42~48` Settings 7필드·타입 일치 확인 완료. | W-1b |
| Q2 | `upsert_*(conn, row)`의 row 타입 + 변환 책임 | row=frozen dataclass(`upsert_price: OHLCV`, `upsert_funda: Funda`), 변환=db.py 내부 책임(`dataclasses.asdict(row)`→named-bind). caller(BAL-12)는 dict 변환 안 함. **fx 예외**: `FxRate`는 W2 DTO이고 W1 models.py에 없으므로 W1 `upsert_fx`는 surface만 두되 `row: Mapping[str, Any]`(dict-like)로 내부 `dict(row)`. W2에서 `row: FxRate`+asdict로 통일. ⚠️ **단, named param 키명은 §3.4 교차결정으로 재정의됨(05 §4.1 약어 정합 필요).** | orchestration §2.1 v2 L57-63(결정 박스). BAL-12 E2E(`upsert_price(conn, ohlcv)`)와 정합. fx는 §2.4에서 명시적 W2. | W-1b |
| Q3 | 테이블 개수(7 vs 9) | **9테이블**로 검증. dev-guide의 "§3가 7테이블이라 적었다"는 서술이 stale — orchestration에 '7테이블' 문자열 없음(grep 확인). 검증집합 = {holdings, settings, price_snapshot, fundamentals_snapshot, fx_snapshot, news_snapshot, market_regime, collect_run, briefing}. `type='table' AND name NOT LIKE 'sqlite_%'`(sqlite_sequence 제외). | 05 §1.1~1.9 = 9 CREATE TABLE. orchestration §2.1 L52·§3 L128 둘 다 '9테이블'로 일치 → 충돌 자체 없음. | W-1b |
| Q4 | upsert 트랜잭션 경계(헬퍼 commit vs caller commit) | **W1=헬퍼 self-commit**(내부 `conn.commit()`). **W2=`commit: bool = True` 키워드 추가**(배치는 `commit=False` 호출 후 루프 끝 1회 commit, 기본값 True라 W1 하위호환). | BAL-12 E2E가 upsert 직후 explicit commit 없이 `latest_*` 되읽기(L304~318) → self-commit 사실상 요구. WAL+다중 connection 영속화 보장. | W-1b(self-commit) / W-2(commit 키워드) |

### 1.2 BAL-9 (`app/tickers.py`) — 티커 정규화/분류

| # | 질문(요약) | 결정 | 근거(정본) | wave |
|---|---|---|---|---|
| Q1 | 정본 변환표 외 source(fdr/fmp/dart) 변환 규칙 | fdr(KR)=pykrx와 동일 6자리 그대로(`005930`→`005930`). dart(KR)=6자리 그대로. fmp(US)=yf/finnhub와 동일(점→하이픈+대문자, `BRK.B`→`BRK-B`). 구현은 그룹 매핑 dict: `KR_BARE={pykrx,fdr,dart}`, `US_PLAIN={yf,finnhub,fmp}`, stooq는 별도. W1 테스트는 정본 4종만 parametrize + fdr/fmp 단언 1줄씩 보강. | 04 §5.1 변환표 + 캐시 PK canonical 원칙. seam §2.5(KR 어댑터는 pykrx/fdr만 호출). 라이브러리 사실: FDR `DataReader('005930')` 6자리 bare, FMP plain 대문자+class share 하이픈. | W-1b |
| Q2 | 미지원 source×market 조합 처리 | **fail-fast `raise ValueError`**. market∉{KR,US} → `ValueError`. 의미상 불가능한 source×market 조합 → `ValueError`. 조용한 폴백/빈문자 금지. W2도 동일 정책(미등록 source=ValueError). | 05 §1.1 holdings CHECK(market∈{KR,US}) + 원칙6 '조용히 틀린 값 차단'. 잘못된 조합 silent 통과 시 캐시 PK 오염. config.py '필수 키 누락=즉시 실패' 철학. | W-1b |
| Q3 | classify_category에서 enum 밖 instrument | **방어적 `None` 반환**(4분기 fall-through). ValueError 안 던짐. 이유: classify는 validate_holdings(04 §1.4)가 instrument를 선검증한 뒤 호출되는 하류 함수. category=None='확인 필요'(05 §1.1)로 안전 영속. to_source와 비대칭(to_source의 silent는 PK 오염, classify의 None은 명시적 '확인 필요'). | 04 §5.3 정본 코드 `return None` fall-through(byte-identical). 04 §1.4 상류 가드 존재 → 재검증은 과설계. None은 05 §1.1 category CHECK(NULL 허용) 정합. | W-1b |

### 1.3 BAL-10 (`app/calendar.py`) — 거래일 로직

| # | 질문(요약) | 결정 | 근거(정본) | wave |
|---|---|---|---|---|
| 1 | 임시공휴일/대체휴일 보정 | **W1=보정 안 함**(mcal XKRX/XNYS 기본 휴장표 100% 신뢰, 하드코딩 오버라이드 set 금지). known-limitation docstring 1줄 유지. **W2=실측 시 `config.py EXTRA_HOLIDAYS: frozenset[date]` 오버레이**(거래소 단위 1개 set). | orchestration §2.3 + 04 §6.1 '임시공휴일 보정 PoC 범위 밖'. 임시휴장 연 0~2회라 005930 정확성 무영향. | W-1b(안 함) / W-2(오버레이) |
| 2 | prev_trading_day 14일 윈도우 0거래일 IndexError 방어 | **W1=방어 안 함**(자연 IndexError 그대로, try/except·길이체크 금지). 14일 고정 윈도우=계약값. **W2=14일 초과 비거래 관측 시 30일로 단일 상수 상향**(동적 확장 루프 금지). | §4 표가 IndexError를 명시 계약 예외로 고정. §5 '정상 입력 불가' 보증. probe로 설 연휴·US 연말 14일 내 해결 확인. Simplicity/'불가능 시나리오 방어 금지'. | W-1b |
| 3 | datetime 입력 가드/정규화 | **W1=가드 안 함**(타입힌트 date + 호출부 계약만 보증). `d.date()` 방어 호출 금지(date엔 없음). 반환만 `.date()`로 좁혀 tz 오염 차단. **W2=변경 없음**(누출 시 호출부 collect.py 수정, calendar에 가드 안 넣음). | §4 계약 '호출부 책임'. 04 §6.1 canonical 시그니처=date. Surgical/Simplicity. | W-1b |
| 4 | valid_days tz-aware(UTC) Timestamp의 tz 변환 여부 | **W1=tz 변환 안 함**(`sessions[-1].date()`로 UTC 라벨 날짜 그대로, `tz_convert`/`astimezone` 금지). mcal valid_days는 자정 UTC 라벨이라 `.date()`=거래소 현지 거래일과 일치. **W2=변경 없음**(EOD 타이밍은 collect.py 책임). | §5 '타임존' + §4 'PoC는 거래일 날짜만'. probe로 변환 불필요 확인. tz_convert 시 off-by-one 위험. | W-1b |
| 5 | 모킹 단위테스트 only vs 실 mcal 통합테스트 포함 | **W1=§6 8케이스 모킹 + 실 mcal 통합테스트 1개(`@pytest.mark.integration`)**. 내용: `expected_trade_date('KR',2024-01-02)==2024-01-02` + `expected_trade_date('US',2024-01-02)==2023-12-29`. **W2=통합 케이스 추가 불필요**(거래소 단위). | orchestration §3 게이트 '005930 expected_trade_date 정확' → 모킹만으론 mcal 실 휴장표 보유 증명 못 함. probe로 green 확인. pytest.mark 분류 규칙 정합. | W-1b |
| 6 | import 시점 break_start/break_end UserWarning 억제 | **W1=억제 안 함**(`warnings.filterwarnings`/`-W ignore`/`remove_time()` 금지, 기능 무영향). 단위테스트는 monkeypatch로 페이크 치환→실 캘린더 경로 안 탐. **W2=CI 노이즈 문제 시 pytest.ini filterwarnings에 격리**(calendar.py 코드 불변). | §5 'UserWarning 기능 무영향, -W ignore 불필요'. Surgical Changes. | W-1b |
| 7 | 모듈 전역 _KR/_US 인스턴스 import 시점 vs lazy | **W1=import 시점 모듈 톱레벨 1회 생성**(`_KR=mcal.get_calendar('XKRX')`, `_US=...XNYS`). lazy/`@lru_cache` 금지. 단위테스트 `monkeypatch.setattr(cal._KR,'valid_days',...)`와 정합. **W2=변경 없음**. | 04 §6.1 정본 코드=모듈 톱레벨. lazy화 시 §6 monkeypatch 모킹 전략이 깨짐. Simplicity. | W-1b |
| 8 | KR/US 외 서브마켓(KOSPI/KOSDAQ) 구분 | **W1=구분 안 함**(`market: Literal['KR','US']` 고정). KOSPI/KOSDAQ 모두 동일 XKRX 캘린더 공유 → 'KR'로 동일 판정. tickers.py의 .KS/.KQ 미결은 티커 문제이지 거래일 문제 아님(직교). **W2=무변경**. | §8 '거래일은 거래소 단위, 서브마켓 구분 불필요'. KRX는 KOSPI/KOSDAQ 동일 휴장표. | W-1b |
| 9 | KR=오늘 vs US=직전거래일 비대칭 통일 여부 | **W1=비대칭 계약대로 유지**(KR=today(거래일이면 그대로/휴장이면 prev), US=항상 prev). 통일 안 함. **W2=KR 당일분 미확정은 collect.py 재시도/fallback 책임, calendar 비대칭 불변**. | BAL-10 §1 + 04 §6.1 + TECH-DESIGN §9 ①④(EOD 타이밍). orchestration §2.3 canonical='KR=오늘,US=직전'. | W-1b |
| 10 | 하류 소비자(collect OK_HOLIDAY, build_freshness_badge) W1 구현/stub | **W1=구현·stub 모두 안 함**. calendar.py는 판정 3함수(is_trading_day/prev_trading_day/expected_trade_date)만 export. seam=import 가능성만 보장. **W2=collect OK_HOLIDAY, W3+=freshness badge**가 3함수 호출해 각자 구현. | §8 Out of Scope 명시. §1 '호환 시그니처만 보장'. Simplicity/Surgical. | W-1b(3함수) / W-2(OK_HOLIDAY) / W-3(badge) |

### 1.4 BAL-11 (`app/sources/kr.py`) — KR 어댑터

| # | 질문(요약) | 결정 | 근거(정본) | wave |
|---|---|---|---|---|
| 1 | SMA200 윈도우<200(신규상장) 처리 | 가용분 계산, 200거래일<→`sma200=None`, 252거래일<→week52도 가용분 max/min, `log.warning` 1회. EmptyResponseError 안 던짐(빈 DF가 아니라 짧은 윈도우). 005930은 윈도우 충분→정상. BACKFILL 라벨은 W2(collect `_status_of='BACKFILL'`). ⚠️ **OHLCV.sma200 None 허용은 §3.4 교차결정(모델 타입 확장)에 의존.** | 05 §1.3 sma200 REAL(NULL 허용), 04 §9 'NULL→맥락 degrade'. 적자 PER None 패턴과 일관. | W-2b |
| 2 | KOSDAQ(.KQ) vs KOSPI(.KS) 서브마켓 구분 | to_source KR 분기는 pykrx KOSDAQ frozenset 멤버십으로 .KS/.KQ 결정. ⚠️ **단, frozenset 빌드 시점은 §3.1 교차결정으로 W2로 재배치됨**(W1=무조건 .KS, set 빌드 안 함). 005930은 KOSDAQ에 없음→.KS. | 04 §5.1 'KOSDAQ=.KQ' 명시하나 판별 메커니즘 미정. pykrx `get_market_ticker_list(market='KOSDAQ')`. (충돌 #3 참조) | W-2(frozenset) — 본래 제출 W-1b에서 재배치 |
| 3 | FDR vs pykrx 1차 소스(close_raw/adj 분리) | **1차=pykrx `get_market_ohlcv(adjusted=True/False)` 두 번 호출**. close_adj=adjusted=True 최신, close_raw=adjusted=False 최신. week52/sma200=adjusted=True. KRX 빈응답 시 @retry(3) 흡수, 소진 시 FDR 폴백(close_raw=close_adj=동일 Close + `fdr_fallback_adj_eq_raw` warning). | FDR KR은 Close 단일 컬럼이라 raw/adj 분리 불가. pykrx만 adjusted 플래그로 양값 제공. 05 §1.3 raw/adj 분리 강제. | W-2b |
| 4 | 조정 윈도우 fetch 시작일 상수 | `start = today - timedelta(days=420)`(주말·공휴일 30% 손실 가정 시 ≈290거래일>252·200 동시 커버). end=today. 매 호출 통째 재fetch. 부족 시 SMA200<200 None 경로. | 05 §1.3·04 §8.3 '조정 윈도우 통째 재계산'. 252거래일 확실 마진. PoC 단순성(config 노출 불요). | W-2b |
| 5 | 5년 percentile 계산법 | `dist=series.dropna(); pctile=float((dist<=current).mean()*100)`(scipy 불요). 음수/NaN PER row 제외. 유효표본<20→`per_pctile_5y=None`. pbr 동일(음수 제외 불요). | 04 §7.2 '어댑터가 계산', 05 §1.4 'NULL 허용'. 중앙값→~50 기대와 일치. | W-2b |
| 6 | fundamentals 5년 fetch 형태/freq/컬럼 | `stock.get_market_fundamental(fromdate, todate, ticker=ct, freq='m')` 월말 5년. 컬럼 `['BPS','PER','PBR','EPS','DIV','DPS']`. per=PER, pbr=PBR, div_yield=DIV. 최신 row=현재값. @retry(3), 소진 시 빈 DF→EmptyResponseError. | 04 §7.2 'pykrx 5년 PER/PBR/배당'. pykrx 고정 스키마. KRX 'Expecting value' 다발 실패가 @retry 근거. | W-2b |
| 7 | div_yield 단위(% vs 소수) | pykrx 'DIV' 값 그대로(퍼센트, 2.5=2.5%) 저장. 어댑터 변환·재계산 안 함. 표시 단위 정규화는 렌더/metrics 책임. | 04 §7.3·05 §1.4 '제공자 계산값 그대로, 자체 재계산 금지'. /100 변환은 위반 + US(FMP) 단위 불일치 위험. | W-2b |
| 8 | 적자(음수/NaN PER) 시 per만 None인가 | per<0 or NaN → per=None, per_pctile_5y=None. pbr/div_yield/pbr_pctile_5y는 독립 유효 시 그대로. NaN(데이터 부재)은 해당 필드 None. 적자 밴드 제외/라벨링은 W3 metrics. | 05 §1.4 'metrics에서 밴드 제외, DB는 NULL/원값'. per/pbr 독립 지표. | W-2b |
| 9 | report_date W1 None 확정 여부 | **report_date=None 고정(W1)**. pykrx 시계열 날짜는 시세 기준일이지 재무 기준일이 아니므로 오용 금지. 재무 실제 기준일=DART(W2 보조). funda_label은 report_date NULL→'워밍업' 정상. | 04 §4.2 'report_date=재무 실제 기준일'. pykrx 날짜를 넣으면 신선도 배지 오판. DART는 04 §7.2 명시적 W2. | W-2b |
| 10 | RegimeRow.as_of 포맷 + KOSPI 지수 PBR 산출 | `as_of=date.today().replace(day=1).isoformat()`('YYYY-MM-01'). `kospi_pbr=stock.get_index_fundamental(start, today, '1001')['PBR'].iloc[-1]`(코스피 코드 '1001'). start=당월 1일. 실패 시 raise(collect가 W2 degrade). us_cape=None 고정. @retry(3). | 04 §4.2 'as_of=기준월→trade_date 매핑', 05 §1.7. 04 §7.5 'KR: pykrx 지수 PBR'. 코드 '1001'=코스피 표준. | W-2b |
| 11 | headlines 건수/정렬/dedup/HTML 제거 | 네이버 news API(`display=10`, `sort='date'`). source='naver' 또는 originallink 도메인. HTML 제거=`re.sub(r'<[^>]+>','',title)`+`html.unescape`. url 기준 dedup(05 §1.6 PK가 최종 차단, 어댑터는 응답순 보존). 빈 items→`[]`. | 04 §7.2 '헤드라인+링크만', 05 §1.6 'url PK 중복차단'. seam §2.5 '빈응답=[]'. display 10건=PoC 충분. | W-2b |
| 12 | ohlcv validate_response 날짜 불일치 처리 | validate_response 호출하되 **W1 어댑터는 rows==0(EmptyResponseError)만 강제, 날짜 불일치는 예외로 안 올림**. stale 대조는 W2 collect.py(collect_run status PARTIAL/FAIL) + 신선도 배지. 어댑터='데이터 실재'까지. | 04 §7.1 본문이 rows==0만 raise. seam §2.7 canonical. 05 §0 'MAX(trade_date) fallback이 휴장 흡수'와 충돌 방지. | W-2b |
| 13 | KRX(pykrx) 간헐 빈응답('Expecting value') 대응 | pykrx는 빈 바디 시 예외 아닌 **빈 DataFrame** 반환(실측) → fetch 후 `df.empty` 검사→빈 DF면 명시적 raise해 @retry(3) 작동시킴(@retry는 예외 기반). 소진 시 마지막 예외 raise. ohlcv/fundamentals/regime 동일. backoff=1.5 지수. | 본 세션 실측: 빈 DF 반환(예외 미발생). 04 §7.1 'rows==0→EmptyResponseError 승격' 철학을 fetch 직후 적용. | W-2b |
| 14 | week52_high/low 윈도우 정의 | **거래일 기준 최근 252거래일**(adjusted `tail(252)`) max/min. sma200=`tail(200)` 평균. 252<→가용분 전체(SMA200<200과 동일 degrade). 420캘린더일 fetch가 252거래일 항상 커버→005930 full. | dev-guide §3 '조정가 최근 252거래일 max/min', 04 §4.2. 거래일 252≈1년 금융 표준. | W-2b |

### 1.5 BAL-12 (validate + 005930 E2E) — 통합 증명

| # | 질문(요약) | 결정 | 근거(정본) | wave |
|---|---|---|---|---|
| Q1 | validate_response latest/expected W1 미사용 | **W1=rows==0 가드만 구현, latest/expected는 시그니처에만 보존**. 날짜 일치 검사는 W2 collect로 이관. 시그니처는 04 §7.1 canonical `(rows:int, latest:str, expected:str)->None` 고정, W2는 본체에 `if latest != expected: raise`만 추가(시그니처 불변, 본체만 성장). | 04 §7.1 본문이 `if rows==0`만 raise(canonical 자신이 W1=rows-only 표현). seam §2.7 정합. W1 날짜 로직은 expected 모킹 필요→과설계. | W-2a(가드 본체) / W-2(날짜검사) |
| Q2 | fdr/fmp/dart 변환 규칙 + W1 테스트 범위 | 규칙: fdr=6자리 그대로, fmp=US canonical 그대로(점 표기 수용은 §3.2 교차결정으로 yf 규칙과 단일화), dart=6자리 그대로. **W1 테스트는 정본 4종(yf/finnhub/stooq/pykrx)만 parametrize**, fdr/fmp/dart는 구현은 규칙대로 들어가되 변환표 테스트 케이스 미추가(005930 실경로=pykrx/fdr 둘 다 6자리라 중복). ⚠️ **fmp 점 표기 처리는 §3.2 교차결정 참조.** | 04 §5.1 표는 4소스만 열 보유. '추측 금지' + '유보 금지' 절충. fdr 6자리=pykrx 정책. surgical. | W-1b(규칙) / W-3(테스트 4소스) |
| Q3 | KOSDAQ .KS/.KQ 구분 | **W1=무조건 .KS(005930=KOSPI), set 빌드 안 함**. W2=pykrx KOSDAQ frozenset 조회(`'.KQ' if ct in _KOSDAQ_TICKERS else '.KS'`, 모듈 로드 1회 빌드, 실패 시 빈 set→.KS 폴백). | orchestration §2.2 L74 '005930=.KS 진행, .KQ는 W2 유보'. 04 §5.1 표 005930→005930.KS 고정. (충돌 #3에서 BAL-11보다 우선) | W-1b(.KS) / W-2(frozenset) |
| Q4 | E2E 모킹 경계(메서드 vs 내부 fetch) | **메서드 경계 모킹**(`KrSource.ohlcv/fundamentals`). 내부 fetch 경계는 BAL-11 단위테스트 책임으로 분리. BAL-12 E2E='db 적재 라운드트립' 증명. 실 네트워크는 DoD 수동 스모크 1회. | orchestration §2.5 KrSource Protocol 시그니처 canonical(안정 계약면). 내부 함수명은 BAL-11 소유(미고정)→모킹 시 결합 취약. surgical. | W-3 |
| Q5 | 인메모리 DB WAL 무시 처리 | conftest `db.connect(':memory:')` 그대로, WAL 무시 명시 수용(가드/분기 없음). connect()는 PRAGMA WAL 무조건 실행하되 인메모리 자동 'memory' 강등=정상. E2E 단일 connection·스레드라 WAL 동시성 무관. | 05 §0 connect() 4 PRAGMA 무조건 실행(db.py=BAL-8 소유, BAL-12 변경 권한 없음). SQLite ':memory:'는 WAL 미지원→자동 강등(예외 없음). | W-3 |
| Q6 | SMA200/52주 윈도우<200 E2E 반환값 | 가용분 계산, 부족 시 해당 필드 None+WARNING. BACKFILL 신호=W2 collect. **W1 005930=bulk fetch로 200일+ 즉시 확보→항상 실수치**(부족 케이스는 다종목 W2만). E2E fake=실수치라 float assert 통과. ⚠️ **None 허용은 §3.4 모델 타입 확장에 의존.** | 05 §4.3/§9 'day-0 bulk로 200일 즉시 확보'. 04 §9.2 trend/change_pct None 허용 패턴. BACKFILL=collect_run 책임(W2). | W1=실수치 / W-2b(None+로깅) / W-2(BACKFILL) |
| Q7 | connect() 시그니처 충돌(04 인자없음 vs 05/orch db_path) | **정본=`connect(db_path: str='data/ballast.db')->sqlite3.Connection`**(05 §0 + orch §2.1 v2). 04 §3.1의 인자없는 connect()는 오기. 기본값=리터럴 'data/ballast.db'(config.load() 아님, orch §2.1 명시). conftest `db.connect(':memory:')` 그대로. | seam 시그니처 정본=orch §2 v2(§15는 connect 미정의→04 vs 05 충돌은 orch로 해소). 기능적으로도 conftest가 `connect(':memory:')` 호출→인자없으면 TypeError로 E2E 불가. (충돌 #1) | W-1b(db.py) / W-3(conftest) |
| Q8 | OHLCV 필드↔price_snapshot 컬럼 1:1 검증 + asdict 바인드 | BAL-12 E2E가 검증 게이트 자체(별도 어서션 없이 라운드트립 통과=1:1 증명). 불일치는 sqlite3 에러로 자동 실패→BAL-8 책임. ⚠️ **단, 05 §4.1 INSERT가 약어 named param(`:ct/:td/:adj`)이고 asdict는 전체명 → BAL-8이 바인드 키명을 정합시켜야 함(§3.4 교차결정).** | 04 §4.2 OHLCV 8필드=05 §1.3 price_snapshot 8컬럼 동일 이름. dev-guide L166 '불일치는 BAL-8 책임, E2E가 검출'. (충돌 #4 관련) | W-3(검증) / W-1b(바인딩 정합) |
| Q9 | headlines 빈응답([]) 가드 경계 | validate_response는 ohlcv/fundamentals에만 호출, headlines엔 절대 안 함. 뉴스 0건=정상([]), 시세/펀더 0행=EmptyResponseError. BAL-12 가드테스트는 headlines 미포함. 구분=호출지점 선택(collect.py W2가 ohlcv/funda 뒤에만 호출). | orchestration §2.5 'headlines 빈응답=[](validate_response 미적용)'. 04 §4.3 빈 list 정상 계약. validate_response는 순수 행수 검사기. | W-2a(가드) / W-3(테스트 범위) / W-2(호출지점) |
| Q10 | monkeypatch 클래스 패치 + KrSource() 인스턴스화 보장 | 클래스 레벨 monkeypatch 유지 + **KrSource.__init__는 무인자·무부작용(lazy 초기화)** 계약을 BAL-11에 명시. __init__에서 네트워크/키 검증 안 함→메서드 첫 호출 시 소스 접근. E2E `KrSource()` 항상 성공. DART 키 의존은 W2 범위. | 04 §7.2 어댑터 패턴, Protocol은 __init__ 미강제. dev-guide 6.4 `KrSource()` 무인자 전제. 05 §10 '시세는 키 불필요'. Simplicity. | W-3(모킹) / W-2b(무인자 __init__ 계약) |

---

## 2. (BAL-8 추가 항목 — 입력 JSON의 `BAL-8-unresolved-resolutions`는 §1.1에 통합됨)

> BAL-8의 Q1~Q4는 §1.1 표에 이미 반영. 별도 절 불필요.

---

## 3. 교차 결정 (이슈 공유 — 충돌 단일화)

여러 이슈가 같은 계약면을 건드린다. 아래는 **contract 기준 단일 정본**이며, 개별 이슈 결정과 어긋나는 부분은 본 절이 override한다.

### 3.1 KOSDAQ .KS/.KQ frozenset 빌드 시점 (BAL-11 ↔ BAL-12 Q3 충돌 해소) [충돌 #3]
- **단일 결정**: `to_source`의 KR 시세소스(yf/stooq) 접미는 **W1=무조건 `.KS`**, KOSDAQ frozenset(`pykrx.get_market_ticker_list(market='KOSDAQ')` 모듈 로드 1회 빌드, 빈 set 폴백)는 **W2로 배치**한다.
- **근거**: `to_source`는 BAL-9(tickers.py) 소유 함수이고 그 W1 범위는 orchestration §2.2 L74('005930=KOSPI(.KS)로 진행, .KQ는 W2 유보')가 canonical. BAL-12 Q3가 이 canonical과 일치. BAL-11이 "모듈 로드 시 W1에 set 빌드"라 한 것은 over-scope(자체 caveat도 'W1 실행 경로 무영향' 인정) + 무의미한 W1 import-time 네트워크 호출이라 Simplicity 위반.
- **영향**: BAL-11 KOSDAQ 결정의 wave를 W-1b→**W-2**로 정정. W1 tickers.py에는 `_KOSDAQ_TICKERS` 빌드 코드를 넣지 않는다.

### 3.2 fmp(US) 변환 규칙 단일화 (BAL-9 Q1 ↔ BAL-12 Q2)
- **단일 결정**: fmp(US)는 **yf/finnhub와 동일 정규화**(점→하이픈+대문자, `BRK.B`→`BRK-B`). BAL-12 Q2의 "fmp는 점 표기 수용(`BRK.B`)" 표현은 BAL-9 Q1의 그룹 매핑(`US_PLAIN={yf,finnhub,fmp}`)으로 단일화한다(점→하이픈 정규화 적용).
- **근거**: 04 §5.1 표가 yf/finnhub US를 `BRK-B`로 고정. 캐시 PK는 canonical 기준이라 소스 표기가 점/하이픈으로 갈리면 안 됨(시계열 분기 방지). FMP API는 class share에 하이픈(BRK-B)도 수용하므로 정규화가 안전. W1 005930·VOO 경로엔 무영향(검증: `to_source('fmp','BRK.B','US')=='BRK-B'`).

### 3.3 to_source 그룹 매핑 일관성 (BAL-9 / BAL-11 / BAL-12 공유)
- **단일 결정**: `to_source` 구현은 source별 if문이 아니라 **그룹 dict**: `_KR_BARE={pykrx,fdr,dart}`(KR→6자리 그대로), KR 그 외(yf/finnhub/stooq)→`{ct}.KS`(W1) ; `_US_PLAIN={yf,finnhub,fmp}`(US→점→하이픈+대문자), US stooq→`{ct.replace('.','-').lower()}.us`. 미등록 source×market→`ValueError`(fail-fast).
- **근거**: 04 §5.1 표 전 케이스 + BAL-9 Q2 fail-fast 정책. BAL-11(KR 어댑터는 pykrx/fdr→6자리), BAL-12(테스트 4소스)와 모순 없음. 검증: `to_source('finnhub','005930','KR')=='005930.KS'`, `to_source('finnhub','BRK.B','US')=='BRK-B'`, `to_source('stooq','VOO','US')=='voo.us'`.

### 3.4 upsert asdict ↔ 05 §4.1 약어 named param 정합 (BAL-8 Q2 ↔ BAL-12 Q8) [충돌 #2]
- **충돌**: 05 §4.1 canonical INSERT는 **약어 named param** `VALUES (:ct, :td, :adj, :raw, :ccy, :hi, :lo, :sma)`을 쓰는데, BAL-8 Q2/BAL-12 Q8 결정은 `dataclasses.asdict(OHLCV)`(키=`canonical_ticker, trade_date, close_adj, close_raw, ccy, week52_high, week52_low, sma200`)를 named-bind한다. **키명이 불일치** → `asdict` dict를 05 §4.1 SQL에 그대로 바인드하면 `sqlite3.ProgrammingError`(파라미터 누락).
- **단일 결정 (contract 우선)**: **db.py의 upsert INSERT는 컬럼 전체명을 named param으로 사용**한다 — 즉 05 §4.1의 약어(`:ct` 등)를 **전체명(`:canonical_ticker, :trade_date, :close_adj, :close_raw, :ccy, :week52_high, :week52_low, :sma200`)으로 치환**하여 `asdict(row)` 키와 1:1 정합시킨다. 약어→전체명 매핑 dict를 따로 두지 않는다(키 변환 레이어 추가는 과설계).
  - 05 §4.1 SQL은 예시(약어)이고 컬럼명 자체는 05 §1.3 정본(`canonical_ticker, trade_date, close_adj, close_raw, ccy, week52_high, week52_low, sma200`). 따라서 named param을 전체명으로 쓰는 것이 컬럼 정본과 asdict 키 둘 다와 일치하는 유일한 정합 해법.
  - fundamentals_snapshot/fx_snapshot도 동일 원칙(컬럼 전체명=asdict 키). fx_snapshot은 컬럼이 `trade_date, pair, rate`로 이미 전체명이라 `dict(row)`로 그대로 정합.
- **검증 1줄**: `upsert_price(conn, fake_ohlcv); assert latest_price(conn, fake_ohlcv.canonical_ticker)['close_raw']==fake_ohlcv.close_raw`(라운드트립 통과=키명 정합).
- **영향**: BAL-8 구현 시 05 §4.1 약어를 전체명으로 박는다. BAL-12 Q8의 라운드트립 게이트가 이 정합을 자동 검출.

### 3.5 OHLCV.sma200/week52 타입 None 허용 (BAL-11 #1 ↔ 04 §4.2 DTO) [충돌 #4]
- **충돌**: 04 §4.2 `OHLCV.sma200: float`, `week52_high: float`, `week52_low: float`(non-Optional)인데, BAL-11 #1/#14 + BAL-12 Q6는 윈도우 부족 시 이 필드에 `None`을 넣는다.
- **단일 결정 (contract 우선)**: models.py의 **`OHLCV.sma200/week52_high/week52_low` 타입을 `float | None`으로 확장**한다. 05 §1.3이 이미 `sma200/week52_* REAL`(NULL 허용)이고 04 §9가 'NULL→degrade'를 가정하므로 DB·소비 레이어는 None을 수용한다. DTO만 non-Optional이라 불일치 → DTO를 05/04소비계약에 맞춰 넓힌다(Funda는 이미 전 필드 `float | None`이라 일관).
- **W1 영향 0**: 005930은 day-0 bulk(05 §4.3)로 200일+ 확보→항상 실수치. None 경로는 W2 다종목 워밍업에서만 실행. 타입 확장만 W1 models.py에 반영(실행 무영향).
- **검증 1줄**: `OHLCV(canonical_ticker='X', trade_date='2024-01-02', close_raw=1.0, close_adj=1.0, ccy='KRW', week52_high=None, week52_low=None, sma200=None)`이 TypeError 없이 생성됨.

### 3.6 connect() 시그니처 (전 이슈 공유) [충돌 #1]
- **단일 결정**: `connect(db_path: str='data/ballast.db')->sqlite3.Connection`(05 §0 + orch §2.1 v2). 04 §3.1의 인자없는 `connect()`는 오기로 폐기. 기본값=리터럴 문자열('data/ballast.db', `config.load().db_path` 아님).
- **근거**: seam 시그니처 정본=orch §2 v2. conftest가 `db.connect(':memory:')` 호출→인자형 필수(기능적 강제). BAL-8(구현)·BAL-12(conftest 소비) 양쪽 정합.

### 3.7 validate_response 시그니처·동작 (BAL-11 #12 ↔ BAL-12 Q1·Q9 공유)
- **단일 결정**: `validate_response(rows: int, latest: str, expected: str)->None`, **W1 본체=`if rows==0: raise EmptyResponseError`만**. latest/expected는 시그니처 보존·본체 미사용. ohlcv/fundamentals에만 호출, headlines엔 미적용. 날짜 일치 검사는 W2 collect로 확장(시그니처 불변, 본체에 `if latest!=expected: raise` 추가).
- **근거**: 04 §7.1 본문 + seam §2.7 canonical. BAL-11(어댑터는 rows==0까지) + BAL-12(가드테스트 rows-only, headlines 제외) 완전 정합.

### 3.8 W1 모델 DTO 정의 범위 (W-1a 선커밋)
- **단일 결정**: W-1a에서 `HoldingInput`(mutable) + `OHLCV/Funda/Headline/RegimeRow`(frozen) 5개만 선정의·커밋. **FxRate는 W2**(W1 models.py 미정의)→BAL-8 `upsert_fx`는 W1에 dict-like(`Mapping[str,Any]`) surface로만 존재. OHLCV는 §3.5대로 sma200/week52를 `float|None`로 정의.
- **근거**: orchestration §2.4. BAL-8 Q2 fx 예외 결정과 정합(FxRate import 불가 회피).

---

## 4. 사용자 확인 필요 (needs_user)

**없음.** 전 항목 needs_user=false. 모든 결정이 contract(§15 > 04 > 05 > seam §2 v2) 내에서 확정 가능했으며, 제품/판단 콜(문서로 못 정하는 것)에 해당하는 항목은 발생하지 않았다. 라이브러리 사실 불확실 항목(pykrx adjusted/freq, FDR 단일 Close 컬럼, 네이버 news API 필드 등)은 가장 그럴듯한 결정 + 구현 시 1줄 검증법을 §1 표의 결정/근거에 동봉했다.

---

## 5. 충돌 점검 결과 (4건, 전부 단일화 완료)

| # | 충돌 | 단일화 결정 | 정본 근거 |
|---|---|---|---|
| 1 | connect() 시그니처: 04 §3.1 인자없음 vs 05 §0/orch §2.1 db_path 인자 | db_path 인자형 채택, 04 §3.1=오기 | §3.6 / seam §2 v2 + conftest 기능 강제 |
| 2 | upsert asdict 전체명 키 ↔ 05 §4.1 약어 named param(:ct 등) | INSERT named param을 컬럼 전체명으로 치환(약어 폐기) | §3.4 / 05 §1.3 컬럼 정본 + asdict 키 |
| 3 | KOSDAQ frozenset 빌드 시점: BAL-11 W1 vs BAL-12 Q3 W2 | W1=.KS 하드코딩(set 빌드 안 함), frozenset=W2 | §3.1 / orch §2.2 L74 |
| 4 | OHLCV.sma200/week52 타입: 04 §4.2 float vs 어댑터 None 삽입 | DTO를 `float \| None`로 확장 | §3.5 / 05 §1.3 REAL NULL + 04 §9 |
