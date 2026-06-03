# Sprint Contract — BAL-2 [W2] M1 데이터 레이어 완성 (BAL-13~17)

> 생성: /harness-workflow Phase 3 (harness-plan). SoT: docs/04-backend.md > 05 > 01.
> 계획 산출물: docs/BAL-2-w2-orchestration.md + docs/BAL-{13..17}-dev-guide.md + docs/BAL-2-w2-decisions.md.

## 모드 / 브랜치
- 모드: **wave** (5 부모 단일 에픽 수직 슬라이스 → parallel-fanout 아님, orchestration §0)
- 브랜치: `feat/bal-2-w2-data-layer` (base `b880169` = main)

## Phases (orchestration §3)
| Phase | 내용 | 게이트 |
|------|------|--------|
| **W2-1** | 공유파일 선커밋: `models.FxRate` + `db.py` W2 헬퍼(upsert_news/upsert_market_regime/upsert_collect_run + upsert_fx→FxRate 전환 + auto_holdings) | import 가능 + 라운드트립 단위테스트 green |
| **W2-2** | 어댑터 4-way 병렬: BAL-13 us.py ∥ BAL-14 fx.py ∥ BAL-15 regime.py(us_cape) ∥ BAL-16 etf.py(U1 결정 후) | 각 어댑터 모킹 단위테스트 green |
| **W2-3** | BAL-17 collect.py 통합 (_collect_market/_fx/_regime + TokenBucket + _status_of + 백필 + collect_run upsert) | 30종목 수집 시뮬레이션 + collect_run status 정확 |

## DoD (Definition of Done)
- [ ] `UsSource().ohlcv/fundamentals/headlines` 모킹 테스트 green (Stooq→yf→Finnhub 폴백, FMP 5년, EDGAR report_date)
- [ ] `FxSource().usdkrw()` → FxRate (ECB→yfinance, 무효응답→폴백→raise)
- [ ] `RegimeProvider().regime().us_cape` 실수치 (Yale→multpl), kospi_pbr 불변
- [ ] BAL-16: U1 결정대로 (옵션 A 연기 / 옵션 B is_core_etf 위임)
- [ ] `collect.run_collect()` → collect_run status 5종(_status_of 4분기 + OK_HOLIDAY 선분기), missing_tickers JSON, 백필 모드
- [ ] db W2 헬퍼 라운드트립 + 컬럼 전체명 named-bind 정합 (decisions §3.5)
- [ ] ruff 통과, pytest -q green, py_compile 전건 통과
- [ ] 외부 API(Stooq/yfinance/Finnhub/FMP/SEC/ECB/Yale/pykrx) 테스트 전량 모킹

## Verify Targets (harness-review fan-out)
- bal-security-reviewer: API 키 처리(FMP/Finnhub/SEC_USER_AGENT/ECOS fail-fast), 외부 응답 인젝션, S-1 이월(config os.environ[])
- bal-test-writer: 어댑터 모킹 커버리지, 폴백 체인 분기, collect status 5종, 백필

## Out of Scope (orchestration §6 / decisions)
- 룩스루 ETF 구성종목 분해(F-19) → R2
- metrics 계산·valuation/trend 라벨링 → W3
- LLM/브리핑/Card DTO·프론트 → W3+
- `scripts/run_collect.py --bootstrap` CLI 래퍼 → 운영 단계 (함수 동작까지만)
- 손익/수익률(G8)

## needs_user (decisions §4) — 승인 게이트에서 확인
- **U1**: BAL-16 ETF 스코프 — 옵션 A(R2 연기, etf.py stub 유지) vs 옵션 B(is_core_etf 얇은 위임 추가). 권장 A.
- **U6**: db W2 헬퍼 커밋 귀속 — (a) BAL-17 W2-1 선커밋 vs (b) BAL-8 carryover. 코드 영향 0(순수 귀속). 권장 (a).
