# Source Adapters — 외부 데이터 어댑터 패턴

> 참조 시점: 새 소스 어댑터 추가, 폴백 체인·재시도·빈응답 처리. SoT = `docs/04-backend.md §7`.

## 공통 가드 (`app/sources/__init__.py`)

```python
class EmptyResponseError(Exception): ...        # rows==0 = '조용한 실패'를 예외로 승격
def retry(times=3, backoff=1.5): ...            # 지수 백오프, 마지막 실패는 re-raise
def validate_response(rows, latest, expected): ...  # rows==0 → EmptyResponseError (W1: rows만)
```

- **날짜검사**(`latest != expected`)는 W1/W2 가드 본체에 넣지 않는다 — `collect._collect_market` 인라인이 담당(decisions §3.4). `validate_response` 시그니처·본체 불변.

## NEVER (위반 시 데이터 무결성 붕괴)

- **빈 응답을 성공으로 취급 금지** — `validate_response(rows=0)`이 `EmptyResponseError`로 승격. "예외 안 남 ≠ OK = 데이터 실재"(05 §1.8).
- **제공자 PER/PBR/배당을 자체 재계산 금지** — 가격×EPS 재계산은 이중 진실(04 §7.3). 제공자 값 그대로 캐시.
- **0/NULL FxRate 위장 금지** — fx 무효 시 다음 폴백, 전부 실패면 raise(분모 제외 아님, 05 §1.5).
- **필수 API 키 부재 시 조용한 빈 결과 금지** — `raise KeyError`(fail-fast, 04 §2).
- **API 키를 URL 쿼리/로그에 노출 금지** — 헤더 우선(Finnhub `X-Finnhub-Token`). 불가피한 경우(FMP `apikey`) HTTPError를 status-only로 재포장.

## Protocol 구현 패턴

`__init__` 무인자·무부작용(lazy) — 네트워크/키 접근은 메서드 첫 호출 시(decisions Q10). `@retry(3)` 메서드 데코레이트.

| 어댑터 | 시세 폴백 | 펀더 | 뉴스/기타 |
|--------|-----------|------|-----------|
| `kr.py` KrSource | pykrx(adjusted 2회) → FDR 폴백(raw=adj) | pykrx 5년 월말 | 네이버 검색 |
| `us.py` UsSource | Stooq → yfinance → Finnhub /quote(당일가, week52/sma200=None) | FMP 5년 ratios + EDGAR report_date(현재 None degrade) | Finnhub 뉴스 |
| `fx.py` FxSource | ECB(EUR 합성 KRW/EUR÷USD/EUR) → ECOS(보조) → yfinance 'KRW=X' | — | — |
| `regime.py` RegimeProvider | kospi_pbr=pykrx 지수 '1001' | us_cape=Yale ie_data.xls → multpl | — |

## 공통 규칙

- **close_raw/close_adj 분리**(05 §1.3) — raw=현재 평가액용(미조정), adj=지표(52주/sma200) 계산용.
- **윈도우 부족** — sma200<200거래일→None, week52<252→None(`float|None`, decisions §3.5). 005930 등 충분 종목은 실수치.
- **percentile**(5년 분포): `(dist<=current).mean()*100`, 유효표본<20→None, PER은 음수 제외.
- **헤드라인 빈응답=`[]`**(뉴스 0건은 정상, `validate_response` 미적용). 시세/펀더 0행=`EmptyResponseError`.
- **regime 한쪽 실패** — us_cape만 실패 시 NULL(kospi_pbr 보존), kospi_pbr 실패는 메서드 raise.

## 미설치 라이브러리 (lazy import)

`pandas_datareader`(Stooq)·`openpyxl`/`xlrd`(Yale xls)는 requirements엔 있으나 venv 미설치 가능 → **메서드 내부 lazy import**로 모듈 로드 비차단. 테스트는 `_fetch_*` 경계 모킹. 실 네트워크 스모크 시 설치 필요.

## 이월 처리 현황

- ~~headline 텍스트 → LLM 프롬프트 주입 격리~~ — **구현됨**: `briefing.build_security_prompt`가 개행 제거 + title 100자/source 40자 절단, Jinja2 autoescape (`ai-briefing.md`).
- EDGAR report_date 실제 CIK 매핑 — 여전히 None degrade (배지 '워밍업' 표시).
