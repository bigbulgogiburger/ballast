# Testing — pytest 규약

> 참조 시점: 테스트 추가. 프레임워크 = pytest (+ httpx TestClient).

## 실행

```bash
source .venv/bin/activate
pytest -q                      # 전체
pytest -q -m unit              # 단위만
pytest -q -m integration       # 통합만
ruff check app/ tests/         # 린트 (커밋 전 필수)
```

마커: `@pytest.mark.unit`(로컬·결정적) / `@pytest.mark.integration`(실 mcal·E2E 라운드트립).

## NEVER

- **실 네트워크 호출 금지** — pykrx/FDR/yfinance/Stooq/Finnhub/FMP/ECB/Yale/네이버는 **전량 모킹**. 어댑터는 `_fetch_*`/메서드 경계 또는 `requests.get`/`stock.*` monkeypatch.
- **실 DB(`data/ballast.db`) 오염 금지** — conftest `conn` 픽스처는 `connect(":memory:")` + `init_schema`.
- **retry 테스트에서 실제 sleep 금지** — `monkeypatch.setattr(app.sources.time, "sleep", ...)` (autouse 픽스처 패턴).

## 픽스처

- `tests/conftest.py` `conn` — in-memory DB. db/collect 테스트가 사용.
- 어댑터 테스트 파일별 autouse `_no_sleep` — retry 백오프 무력화.

## 모킹 경계

| 대상 | 모킹 지점 |
|------|-----------|
| KR/US 시세 | `KrSource._ohlcv_*`/`UsSource._ohlcv_stooq/_yf` 또는 `kr.stock.*` |
| FMP/Finnhub/ECB | `us.requests.get`/`UsSource._fmp_ratios`/`FxSource._ecb_rate` |
| Yale CAPE | `regime._cape_from_yale/_cape_from_multpl` |
| pykrx 지수 | `regime.stock.get_index_fundamental` |
| collect E2E | `KrSource/UsSource/FxSource/RegimeProvider` 클래스 메서드 + `collect.calendar.*`. `db.connect`는 no-close 프록시로 conn 주입 |

## 커버리지 우선순위 (harness-review가 점검)

happy path + 폴백 분기 + 빈응답→EmptyResponseError + degrade(None) + 게이트 status 전 분기 + 종목 격리 연속성 + DTO↔컬럼 라운드트립(전필드).

## 현재 상태

138 tests (unit 134 + integration 4). `sqlite3.Connection`은 C타입이라 인스턴스 메서드 monkeypatch 불가 → 위임 프록시 사용(test_collect E2E 참고).
