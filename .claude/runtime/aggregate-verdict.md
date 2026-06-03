# Aggregate Verdict — BAL-2 W2-2 (BAL-13/14/15) Phase W2-2 (Iteration 1)

- **Issue**: BAL-13(us) / BAL-14(fx) / BAL-15(regime us_cape). BAL-16=R2 연기(U1=A).
- **Phase**: W2-2 (어댑터 3-way)
- **Verdict**: PASS
- **Iteration**: 1/3
- **Mode**: auto · **Participants**: [bal-security-reviewer, bal-test-writer]
- **Target Commits**: adf865f..0a5813f + 77d608e(fix)

## Blockers (iteration 1 내 해소)
| ID | Agent | 요지 | 상태 |
|---|------|------|------|
| S-2 | security | FMP URL path traversal(ct 미인코딩) | ✅ urllib.parse.quote |
| G1/G2 | test | finnhub trade_date(ts/fallback) 미검증 | ✅ 추가 |
| G3 | test | 소표본 pctile None 미검증 | ✅ 추가 |
| G4 | test | FMP 빈→EmptyResponseError 미검증 | ✅ 추가 |
| G5/G6 | test | ECB 합성식 한번도 실행 안됨(전량 모킹) | ✅ _ecb_rate 모킹 수학검증 추가 |

## Advisories (이월/처리)
| ID | 요지 | 처리 |
|---|------|------|
| S-1 | FMP/Finnhub 키 query param 노출 | Finnhub 헤더 전환(완화). FMP는 apikey 헤더 미지원(제공자 제약)→query 유지, 로그 URL 주의 이월 |
| S-3 | Yale CAPE http | ✅ https 전환 |
| S-4 | headline→LLM/템플릿 인젝션 | W3 프롬프트 격리 과제(W1부터 이월) |
| S-5 | config os.environ[] fast-fail | W2+ 하드닝 이월 |
| S-6 | fx 광범위 except가 auth 마스킹 | ECB 키리스라 저영향, 이월 |
| G7/G8 | ECOS skip·us_cape both-fail | ✅ both-fail 추가(G7 간접 커버) |

## Next Action
→ PASS: W2-3(BAL-17 collect.py 통합) 진입. 117 passed, ruff 통과.
