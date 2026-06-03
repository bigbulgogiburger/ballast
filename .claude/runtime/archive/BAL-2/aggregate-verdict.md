# Aggregate Verdict — BAL-2 W2 (BAL-13~17) — 전 wave 종합

- **Epic**: BAL-2 [W2] M1 데이터 레이어 완성
- **Verdict**: PASS
- **Mode**: auto · **Participants**: bal-security-reviewer, bal-test-writer (wave별 fan-out)
- **Branch**: feat/bal-2-w2-data-layer (base b880169=main)

## Wave별 게이트
| Wave | 이슈 | Verdict | 비고 |
|---|---|---|---|
| W2-1 | FxRate + db 헬퍼 | PASS | 라운드트립 11 테스트 |
| W2-2 | BAL-13/14/15 어댑터 | PASS (iter1) | S-2 path traversal·S-1 Finnhub헤더·S-3 https + 테스트갭 해소 |
| W2-3 | BAL-17 collect | PASS (iter1) | S-1 FMP 키 로그유출 차단(어댑터 마스킹) + collect 테스트갭 해소 |

## 해소된 Blocker 요약
- 보안: S-2(FMP URL traversal→quote), S-1(키 노출: Finnhub 헤더 전환 + FMP HTTPError 마스킹), S-3(Yale https)
- 테스트: finnhub trade_date, 소표본 pctile, FMP 빈→raise, ECB 합성 수학, us_cape both-fail, collect all-fail/backfill/news-date/격리연속성

## 이월 Advisory (W2+/W3)
- FMP apikey query param(제공자 제약 — 헤더 미지원, 로그 마스킹으로 완화)
- S-4 headline→LLM/템플릿 인젝션 격리 (W3 프롬프트 조립)
- S-5 config os.environ[] fast-fail (W2+ 하드닝)
- 미설치 lib(pandas_datareader/openpyxl/xlrd) — 실 네트워크 스모크 시 설치 필요(테스트는 모킹)
- EDGAR report_date 실제 CIK 매핑(현재 None degrade)

## BAL-16
U1=옵션 A → R2 연기. etf.py stub 유지(코드 변경 0). 코어판정은 W1 tickers.py 완료.

## 최종
138 passed (unit 134 + integration 4), ruff 통과, py_compile 전건. → Phase 6/7 진입.
