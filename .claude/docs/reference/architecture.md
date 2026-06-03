# Architecture — 모듈 맵 & 데이터 흐름

> 참조 시점: 새 모듈 추가, 데이터 흐름 이해, seam 계약 확인. SoT = `docs/04-backend.md`/`docs/05-database.md`.

## 레이어

```
sources/ (어댑터)  →  collect.py (배치 오케스트레이터)  →  db.py (SQLite 영속)
                                                              ↓
                                       metrics/ → briefing.py (LLM) → main.py (FastAPI/Jinja2)
```

- **sources/** — 외부 무료 데이터 어댑터. Protocol 구현, 종목 단위 격리. (`source-adapters.md`)
- **collect.py** — 일배치. auto 보유종목을 돌며 어댑터 호출 → db 적재 + `collect_run` 게이트 기록. (`data-collection.md`)
- **db.py** — SQLite 연결/스키마/조회·적재 헬퍼. 9테이블. (`database.md`)
- **metrics/** — portfolio/security 계산 (W3 범위, 현재 스텁).
- **briefing.py** — LLM 브리핑 생성 (W3 범위).
- **main.py** — FastAPI 엔드포인트 + Jinja2 렌더.

## 모듈 인벤토리

| 모듈 | 책임 | 상태 |
|------|------|------|
| `app/models.py` | DTO (HoldingInput·OHLCV·Funda·Headline·RegimeRow·FxRate, frozen) | W1+W2 구현 |
| `app/db.py` | connect/init_schema/latest_*/upsert_*/auto_holdings | W1+W2 구현 |
| `app/tickers.py` | to_source 변환·CORE_ETF_WHITELIST·classify_category | W1 구현 |
| `app/calendar.py` | 거래일(XKRX/XNYS) is_trading_day/prev/expected | W1 구현 |
| `app/sources/__init__.py` | 공통 가드: EmptyResponseError·retry·validate_response | W2 구현 |
| `app/sources/kr.py` | KR 어댑터(pykrx/FDR/네이버) | W1 구현 |
| `app/sources/us.py` | US 어댑터(Stooq→yfinance→Finnhub/FMP/SEC) | W2 구현 |
| `app/sources/fx.py` | FX(USDKRW) 어댑터(ECB→yfinance) | W2 구현 |
| `app/sources/regime.py` | 레짐(kospi_pbr KR + us_cape Shiller CAPE) | W1+W2 구현 |
| `app/sources/etf.py` | ETF 코어/룩스루 | 스텁(R2 연기) |
| `app/collect.py` | 일배치 통합자 | W2 구현 |
| `app/metrics/*` | 비중·밸류·트렌드 계산 | W3 스텁 |
| `app/briefing.py` | LLM 브리핑 | W3 스텁 |
| `app/main.py` | FastAPI 진입점 | 스캐폴드 |

## 마일스톤 매핑

- **W1 (BAL-1 / M1a)**: db·tickers·calendar·kr 어댑터·models 일부 — 삼성전자(005930) 단일종목 인입 증명.
- **W2 (BAL-2)**: us·fx·regime(us_cape)·collect 배치·db W2 헬퍼 — 30종목 데이터 레이어 완성. BAL-16(ETF 룩스루)=R2 연기.
- **W3+**: metrics·LLM 브리핑·프론트·손익(G8) — 미착수.

## seam 계약 정본

W1 = `docs/BAL-1-m1a-orchestration.md §2` + `docs/BAL-1-m1a-decisions.md`.
W2 = `docs/BAL-2-w2-orchestration.md §2` + `docs/BAL-2-w2-decisions.md`.
⚠️ `TECH-DESIGN.md`는 레포에 없음 — 04/05/01이 정본(W1 dev-guide의 §15 인용은 부재 파일).
