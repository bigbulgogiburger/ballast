---
issue: BAL-3
title: W3 M2 지표 엔진 (부모)
type: composite
status: closed
week: W3
parent: null
related_adrs: [ADR-0002]
persona: Python Expert
created: 2026-06-04
closed: 2026-06-04
---

# [BAL-3] W3 · M2 지표 엔진 — 통합 개발 가이드 (부모)

> 생성일: 2026-06-04
> 스택: Python / FastAPI (SQLite)
> 페르소나: Python Expert
> 실행 형태: **에픽 1개 + 6 자식 슬라이스** (단일 worktree `feat/BAL-3` + Workflow 툴 wave 병렬, ADR-0002)

## 1. 요구사항 요약

### 비즈니스 목표
외부 의존 없는 **순수 계산 로직**(통화정규화·5/25 리밸런싱·밸류에이션·신선도 게이트)을 pytest로 못박는다. 틀리면 치명적인 금융 산출이라 단위 테스트 커버리지를 최대(≥85%)로 끌어올린다. W3 완료 = W4(AI)·W5(프론트) 병렬 분기점 (§15.2 계약 고정).

### 인수조건 (에픽 DoD, `docs/08-dev-roadmap.md` Week 3)
- [ ] `pytest tests/test_metrics.py --cov=app/metrics` 커버리지 **≥ 85%**
- [ ] ① 5/25 "작은 쪽" 트리거 (절대 5%p vs 상대 25% 먼저)
- [ ] ② fx FAIL 시 USD 자산 보류 · **KR만 100% 정규화 안 됨** (전역 오염 회귀)
- [ ] ③ 자동목표 순환차단 (평가액 없이 그룹 균등)
- [ ] ④ per_pctile NULL → warmup 라벨, ⑤ 음수 PER 제외
- [ ] `build_priced`가 보류 종목을 `status`로 표시하되 **분모에서 빼지 않음**

### 제약사항 (CLAUDE.md Key Rules — 위반 시 리뷰 BLOCK)
- **NEVER fx 결측 시 분모 제외** — 산출 거부(0/NULL 위장 금지). 보류는 `status` placeholder.
- **NEVER 제공자 PER/PBR 자체 재계산** — 제공자 계산값만 사용.
- **NEVER 빈 응답을 OK로** — 데이터 0건 → `data_pending` 보류.
- 전부 **frozen dataclass** + **type annotation 전량** (PEP8/black/ruff).

## 2. 슬라이스 의존성 DAG

```
BAL-18 [models.py §15.2 DTO + Protocol]   ← 토대, 전원 import
   │
   ├─> BAL-19 [metrics/priced.py build_priced]   ← 핵심 (PricedHolding 소비)
   │       ├─> BAL-20 [metrics/portfolio.py]  ┐ 형제 — 둘 다 PricedHolding/build_priced 의존
   │       └─> BAL-21 [metrics/security.py]   ┘ 상호 격리 (다른 파일)
   ├─> BAL-22 [metrics/gate.py + db.py]   ← DTO만 의존 (build_priced 무관)
   └─> BAL-23 [tests/test_metrics.py]   ← 18~22 전부 구현 후 마지막
```

**실행 wave (리드 강제):**
1. **Wave A**: BAL-18 (solo) — DTO/Protocol 봉인. 통과 후에만 다음.
2. **Wave B**: BAL-19 (solo) — build_priced + 환율 정규화 봉인.
3. **Wave C**: BAL-20 ‖ BAL-21 ‖ BAL-22 (3-way 동시 — 소유 파일 disjoint).
4. **Wave D**: BAL-23 (solo) — 전 모듈 회귀 테스트 + 커버리지 게이트.

## 3. 파일 소유권 맵 (충돌 0 — Agent Teams 분할)

| 슬라이스 | 소유(수정/신규) 파일 | 읽기 전용 의존 |
|----------|----------------------|----------------|
| **BAL-18** | `app/models.py` (DTO 7종 추가) | 04 §4.4 / §9.1 / §15.2 |
| **BAL-19** | `app/metrics/priced.py` (신규) | `models.PricedHolding`, `db.latest_price`, `db.latest_fx` |
| **BAL-20** | `app/metrics/portfolio.py` | `models.PricedHolding/HoldingRow` |
| **BAL-21** | `app/metrics/security.py` | `models.OHLCV/Funda` |
| **BAL-22** | `app/metrics/gate.py` (신규) + `app/db.py` (헬퍼 2종 추가) + `app/calendar.py`(필요 시) | `db.latest_collect_run` |
| **BAL-23** | `tests/test_metrics.py` (신규), `tests/conftest.py`(픽스처 추가 시) | 전 모듈 |
| **리드(통합)** | `app/metrics/__init__.py` (export 일괄) | — |

> ⚠️ **공유 파일은 `app/metrics/__init__.py` 뿐 — 리드가 통합 시점에만 편집.** 슬라이스는 절대 `__init__.py`를 만지지 않고 전체 모듈 경로로 import(`from app.metrics.portfolio import drift`). `db.py`는 BAL-22 단독 touch.

## 4. Cross-cutting 설계 결정 (전 슬라이스 공통)

1. **§15.2 DTO 경계**: `SecurityCard/SecurityLLMOut/BriefingDoc/HoldExcluded/FreshnessBadge/HoldingRow/PricedHolding` + Protocol → `models.py`(BAL-18). 기존 `OHLCV/Funda/Headline/RegimeRow/FxRate`는 **이미 존재** (중복 정의 금지).
2. **metric 결과 타입은 §15.2 아님**: `DriftResult/CoreSatResult/DcaResult/AllocResult/ValuationLabel/TrendLabel`은 스펙에 필드 미고정 → **각 metrics 모듈이 frozen dataclass로 로컬 정의**(소유 모듈 내). models.py에 넣지 않는다.
3. **status enum (§15.4)**: `'ok'|'data_pending'|'fx_held'|'warmup'|'failed'` — 문자열 상수, BAL-19/21이 사용.
4. **통화 정규화 base=KRW**: USD → `value * fx_rate`. fx 결측 시 USD 자산은 `fx_held` 보류(분모 유지, value_base=None).
5. **순환 차단(G5)**: `auto_targets`는 평가액 타입을 **인자로 받지 않는다**(컴파일 레벨 차단).
6. **5/25 "작은 쪽"(①)**: 자산군 단위 집계 후 `min(절대 5%p 초과, 상대 25% 초과)` 먼저 트리거. `micro_floor` 미만은 억제.

## 5. 슬라이스 진입점

| 슬라이스 | dev-guide |
|----------|-----------|
| BAL-18 | `docs/BAL-3-BAL-18-dev-guide.md` |
| BAL-19 | `docs/BAL-3-BAL-19-dev-guide.md` |
| BAL-20 | `docs/BAL-3-BAL-20-dev-guide.md` |
| BAL-21 | `docs/BAL-3-BAL-21-dev-guide.md` |
| BAL-22 | `docs/BAL-3-BAL-22-dev-guide.md` |
| BAL-23 | `docs/BAL-3-BAL-23-dev-guide.md` |

## 6. 위험 요소

| 위험 | 영향 | 대응 |
|------|------|------|
| fx 결측 전역 오염 (KR까지 미정규화) | 높음 | BAL-19 `market=='US'`에만 fx 적용. BAL-23 회귀 ② 필수 |
| metric 결과 타입 미정의로 슬라이스간 시그니처 불일치 | 중간 | §4.2 — 각 모듈 로컬 정의, 부모 가이드에 시그니처 고정 |
| `__init__.py` 동시 편집 충돌 | 중간 | 리드 단독 소유 (§3) |
| 커버리지 85% 미달 | 중간 | BAL-23이 분기 케이스(NULL/음수/보류) 전수. metrics 함수는 순수→테스트 용이 |

## 7. 검증
- 각 슬라이스: `pytest -q` + `ruff check app/` GREEN.
- 통합: `pytest tests/test_metrics.py --cov=app/metrics --cov-report=term-missing` ≥ 85%.
