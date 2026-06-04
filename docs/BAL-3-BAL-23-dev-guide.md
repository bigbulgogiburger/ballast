# [BAL-23] test_metrics 커버리지 ≥85% — 회귀 5종 — slice dev-guide

> 부모: `docs/BAL-3-dev-guide.md` · Wave D (18~22 전부 후, 마지막) · 소유: `tests/test_metrics.py`(신규)

### 0. Touched Files
- **신규**: `tests/test_metrics.py`
- **수정**(필요 시): `tests/conftest.py` (인메모리 conn 픽스처·holdings 빌더)
- 읽기 전용: `app/metrics/*`, `app/models.py`, `app/db.py`

### 1. 작업 범위
`pytest tests/test_metrics.py --cov=app/metrics` **≥ 85%**. 회귀 케이스 5종 + 함수별 분기 커버.

### 2. 회귀 케이스 5종 (에픽 DoD — 전부 통과 필수)
- **① 5/25 작은 쪽**: `drift` — 절대 5%p와 상대 25% 중 먼저 닿는 임계로 트리거됨을 검증 (둘을 분리한 케이스 2개).
- **② fx FAIL 전역 오염 방지**: `build_priced(fx_ok=False)` — US 자산은 `fx_held`(value_base=None), **KR 자산은 정상 value_base 산출**(전역 미정규화 아님). + USD 현금도 보류.
- **③ 자동목표 순환차단**: `auto_targets`가 평가액 없이 그룹 균등 산출 (시그니처에 value 인자 없음 + 결과 합 100%).
- **④ warmup**: `valuation(Funda(per_pctile_5y=None))` → label "워밍업 중", pctile None.
- **⑤ 음수 PER 제외**: `valuation(Funda(per=-3.0))` → 판정에서 제외 (pctile 기반 라벨 안 함).

### 3. 추가 분기 커버 (85% 달성용)
- `build_priced`: manual KRW현금 / manual USD현금(fx_ok T·F) / US종목 us_ok=False / price None / 정상 KR·US.
- `change_pct`: prev_close None·0 → None, 정상 등락.
- `trend`: week52/sma200 None-safe.
- `regime`: 둘 다 NULL → "미확보", 일부 존재.
- `evaluate_gate`: KR·US 모두 죽음→blocked / FX만 죽음→fx_ok=False / OK_HOLIDAY·BACKFILL 비차단.
- `collect_complete_today`: row 없음→False, trade_date 불일치→False, 일치→True.
- `core_sat`: 30% 초과/이하. `asset_alloc`: usd_held 임계.

### 4. 픽스처 전략
- `conftest.py`의 기존 패턴 재사용 (인메모리 sqlite + `init_schema`). holdings/collect_run/price/fx는 직접 upsert 또는 빌더 헬퍼.
- `freezegun` 또는 `monkeypatch`로 `date.today()`/`calendar.expected_trade_date` 고정 (collect_complete_today 결정성).

### 5. 검증
`pytest tests/test_metrics.py --cov=app/metrics --cov-report=term-missing` → ≥85% + 5종 PASS. `ruff check tests/test_metrics.py`.
