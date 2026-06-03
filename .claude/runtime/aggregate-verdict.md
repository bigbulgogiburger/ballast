# Aggregate Verdict — BAL-1 W-1 (BAL-8/9/10) Phase W-1 (Iteration 1)

<!-- ═══ Metadata (Tier 3 측정) ═══ -->
- **Issue**: BAL-1 (W-1: BAL-8, BAL-9, BAL-10; subtasks BAL-43/44, —, —)
- **Phase**: W-1 (foundation 3-way)
- **Verdict**: PASS
- **Iteration**: 1/3
- **Ran At**: 2026-06-03T13:25:56+09:00
- **Ended At**: 2026-06-03T13:29:56+09:00
- **Duration**: ~4m (fan-out + 갭 수정 포함)
- **Tokens (approx)**: ~161k (bal-security-reviewer ~59k + bal-test-writer ~102k, 추정치)
- **Mode**: auto
- **Shadow Run**: N
- **Participants**: [bal-security-reviewer, bal-test-writer]
- **Skipped**: [bal-explorer (리뷰 비대상, 매핑 전용), bal-build-resolver (빌드 정상)]
- **Target Commits**: 1ccd17f..1d23c71 (W-1a models + W-1b db/tickers/calendar) + 후속 갭 테스트 커밋

<!-- ═══ Body ═══ -->
## Blockers
초기 fan-out에서 테스트 커버리지 Blocker 4건 제기 → **iteration 1 내 전건 해소(테스트 추가, 59 passed)**.

| ID | Agent | 위치 | 요지 | 상태 |
|---|------|------|------|------|
| G-02 | bal-test-writer | test_db.py | settings 7키 전값 단언 누락(usd_cash_gate_threshold 등 게이트 임계치) | ✅ test_settings_seed_all_values 추가 |
| G-03 | bal-test-writer | test_db.py | holdings manual tracking CHECK 위반 테스트 누락 | ✅ test_holdings_check_manual_keys 추가 |
| G-04 | bal-test-writer | test_db.py | latest_funda/latest_fx MAX(trade_date) 미검증 | ✅ 2종 추가 |
| G-07 | bal-test-writer | test_db.py | decisions §3.4 전필드 라운드트립 부분 커버 | ✅ E2E 8+8필드 전체 단언으로 확장 |

## Advisories
| ID | Agent | 요지 | 처리 |
|---|------|------|------|
| S-01 | bal-security-reviewer | config.py 필수 키 `.get()`→None silent (04 §2 fast-fail 위반) | **W-1 범위 밖**(config.py=baseline, 키는 W-2 어댑터에서 소비). W-2 진입 시 `os.environ[...]` 전환 권고로 이월 |
| S-02 | bal-security-reviewer | upsert_fx `Mapping` surface 타입검증 없음 | 의도된 결정(§3.8, FxRate=W2). W-2에서 `row: FxRate`+asdict 통일 |
| G-01/05/06/08/09 | bal-test-writer | WAL :memory· none-on-empty· funda update· 추가 불가조합· etf None ticker | ✅ 대부분 함께 추가(저비용 고가치) |
| G-10/11/12 | bal-test-writer | calendar 케이스 행렬 보강(US 평일·KR 신정 통합) | ✅ 일부 추가 |

## Next Action
→ **PASS: W-2 진입 가능** (sources/__init__ 가드 → BAL-11 kr.py + regime.py). 커밋 게이트 통과.

<!-- ═══ Post-merge Scoring (7일+ 경과 후 /harness-score로 채움) ═══ -->
## Post-merge Scoring
> ⏰ 비워두세요. 머지 후 7일+ 별도 세션에서 /harness-score로만 채웁니다.

- **Scored At**: (empty)
- **Scored By**: (empty)
- **Days After Merge**: (empty)
- **Blocker Results**:
  | ID | Status | Evidence |
  |---|---|---|
  | (to be filled) | VALID/INVALID/UNCERTAIN | |
- **Regression filed?**: (empty)
- **Production incident linked?**: (empty)
