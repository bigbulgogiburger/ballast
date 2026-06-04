---
issue: BAL-5
title: W5 M4 프론트엔드 (부모, 슬라이스 BAL-29~33)
type: composite
status: closed
week: W5
parent: null
related_adrs: [ADR-0002]
persona: Python Expert
created: 2026-06-04
closed: 2026-06-04
---

# BAL-5 dev-guide — W5 M4 프론트엔드 (30초 스캔 대시보드)

> 부모 에픽 **BAL-5**. 슬라이스 **BAL-29 / 30 / 31 / 32 / 33** (전부 형제 작업, subtask 없음 → `--subtasks` no-op).
> 실행 모드: **단일트리 의존순서** (브랜치 `feat/BAL-5`). 5-worktree 팬아웃 폐기 — 코드 영역 충돌(main.py·tokens.css·템플릿 상호의존) 때문.
> SoT: `docs/03-frontend.md` (라우트/DTO/색/검증 정본), `docs/02-design.md §4.1`(면책), `docs/08-dev-roadmap.md` Week 5.
> 작성일: 2026-06-04

---

## 1. 현재 상태 (그린필드)

- `app/main.py` = 11줄 스텁(`/healthz`만).
- `app/templates/`·`app/static/` = `.gitkeep`만(빈 디렉토리).
- 기존 백엔드 자산(재사용): `app/models.py`(BriefingDoc·SecurityCard·HoldExcluded·FreshnessBadge·HoldingRow DTO 존재), `app/db.py`(`holdings()`·`insert_briefing()`), `app/briefing.py`(`run_briefing()`), `app/tickers.py`(`CORE_ETF_WHITELIST`), `app/config.py`(`DISCLAIMER`·`Settings`·`SETTINGS_DEFAULTS`).
- 의존성: `jinja2` ✅ 설치됨. **`python-multipart` 누락** → Form 파싱(POST /holdings·/settings)에 필요 → BAL-32가 requirements에 추가.

## 2. 파일 소유권 (충돌 0 — 단일 소유 원칙)

| 슬라이스 | 생성/수정 파일 (이 슬라이스 외 누구도 안 건드림) |
|---|---|
| **BAL-29** | `app/static/css/tokens.css` |
| **BAL-33** | `app/briefing.py`(+`build_freshness_badge`), `app/static/css/app.css`, `app/templates/_components.html`(Jinja 매크로) |
| **BAL-32** | `app/main.py`(라우트 4개 전부), `app/templates/base.html`, `app/templates/settings.html`, `app/db.py`(+`save_holdings`·`load_latest_briefing`·`get_settings`·`save_settings`), `requirements.txt`(+`python-multipart`) |
| **BAL-31** | `app/holdings_form.py`(폼 DTO + `parse_holdings_form` + `validate_holdings`), `app/templates/holdings.html` |
| **BAL-30** | `app/templates/dashboard.html` |

> **결정 — 폼 DTO 위치**: 03 §2.3은 `models.py`를 지목하나, `HoldingForm`/`HoldingsValidation`/`FieldError`는 `app/holdings_form.py`에 co-locate(BAL-31 단일 소유 유지 → models.py 레이스 제거). spec과의 의도된 편차이며 필드명·시맨틱은 §2.3 그대로.

## 3. 웨이브 (의존순서 — 동시성은 웨이브 내부에서만)

```
Wave 1 (foundation, 병렬)  : BAL-29 tokens.css  ‖  BAL-33 badge+app.css+_components
        ↓ (통합: import OK + ruff)
Wave 2 (route+form, 병렬)  : BAL-32 main.py·base·settings·db helpers  ‖  BAL-31 holdings_form·holdings.html
        ↓ (통합: app import OK + 라우트 스모크 + pytest + ruff)
Wave 3 (consume)           : BAL-30 dashboard.html
        ↓ (통합: 전체 pytest + ruff + 라우트 200/400 스모크)
```

핵심 계약(웨이브 경계에서 고정):
- `main.py`(32)는 `from app.holdings_form import parse_holdings_form, validate_holdings`(31), `from app.db import save_holdings, load_latest_briefing, get_settings, save_settings`(32), `from app.briefing import build_freshness_badge`(33)를 import. **시그니처는 아래 §4에 고정** → 병렬 안전.

## 4. 고정 시그니처 (웨이브 간 계약 — 변경 금지)

```python
# app/briefing.py  (BAL-33)
def build_freshness_badge(conn: sqlite3.Connection) -> FreshnessBadge: ...
#   price_age_days: MAX(price_snapshot.trade_date) vs calendar 기대거래일
#   funda_label: MAX(fundamentals_snapshot.report_date) 기반 "N개월 전"
#   fx_age_days: MAX(fx_snapshot.trade_date) vs 기대일
#   worst_level: 'fresh'(0~1)|'stale'(2~4)|'warn'(5+) — 종목별 최악 집계
#   consecutive_fallback: collect_run 연속 fallback 판정(데이터 없으면 False)

# app/db.py  (BAL-32)
def save_holdings(conn, rows: list[HoldingRow], user_id: int = 1) -> None: ...   # category 영속화(G4), 기존 행 교체
def load_latest_briefing(conn, user_id: int = 1) -> BriefingDoc | None: ...      # MAX(created_at), content_json → BriefingDoc.from_dict
def get_settings(conn, user_id: int = 1) -> dict: ...                            # §15.5 키
def save_settings(conn, values: dict, user_id: int = 1) -> None: ...

# app/holdings_form.py  (BAL-31)
@dataclass(frozen=True) class HoldingForm: ...          # 03 §2.3 (전 필드 str|None)
@dataclass(frozen=True) class FieldError: row_index:int; field:str|None; message:str
@dataclass(frozen=True) class HoldingsValidation: ok:bool; rows:list[HoldingRow]; errors:list[FieldError]
def parse_holdings_form(request) -> list[HoldingForm]: ...   # async form → 행 리스트
def validate_holdings(forms: list[HoldingForm]) -> HoldingsValidation: ...  # 03 §2.4 규칙 전량
```

## 5. 슬라이스별 상세 + DoD

### BAL-29 — tokens.css (§15.3 색 정본)
- `app/static/css/tokens.css`: 03 §6.2 블록을 **그대로** 옮긴다(design.md 매핑 + 신규 등락/상태/alloc/density 토큰 + `.tabular`).
- 등락 한국관습: 상승 `--c-up:#d92d4e` / 하락 `--c-down:#1971c2`, CTA Teal `--c-primary:#0c8599`.
- **DoD**: 색 토큰이 §15.3과 일치 / 등락색(`--c-up/--c-down`)이 CTA·링크·헤더에 미사용(=app.css·템플릿에서 CTA는 `--c-primary`만).

### BAL-33 — build_freshness_badge + 컴포넌트 (placeholder/fail 카드·badge·stack-bar)
- `app/briefing.py`: `build_freshness_badge(conn)` 추가(§4 위 시그니처). DB 결측 시 안전 기본값(age=큰값/worst='warn' 또는 0/'fresh' — 데이터 없으면 'warn'으로 안전 degrade, banner는 dashboard 책임).
- `app/static/css/app.css`: tokens.css 변수만 참조. placeholder 카드(`--c-hold-soft`), fail 카드(`--c-fail-soft`), `.badge`/`.badge--{fresh,stale,warn}`, `.stack-bar`/`.stack-seg`/`.seg-label`(03 §5 flex+width%), density 표(`--density-*`, `tabular-nums`), `.warn-block`. **드롭섀도 금지**(hairline-only).
- `app/templates/_components.html`: Jinja 매크로 — `security_card(card)`(status 분기: ok/data_pending/fx_held/warmup/failed → placeholder/fail), `freshness_badge(badge)`(§4.2), `stack_bar(...)`(§5). 등락은 색+부호(`+`/`-`) 병기(접근성 §7).
- **DoD**: 보류/제외/워밍업 placeholder 표시(빈칸 금지, e2e G3/G6) / dense 셀 전부 `tabular-nums` / 매크로가 `_components.html` 단독.

### BAL-32 — main.py 라우트 + settings + 영속화
- `app/main.py`: 03 §1 그대로 — `StaticFiles` mount(`app/static`), `Jinja2Templates("app/templates")`, 라우트 `GET /`, `GET/POST /holdings`, `GET/POST /settings`, `POST /api/regenerate`. **`/api/regenerate`는 `request.client.host != "127.0.0.1"` → `HTTPException(403)`**. POST /holdings는 §1 흐름(parse→validate→실패 400 상태보존 재렌더 / 성공 303 PRG `?saved=1`).
- `app/templates/base.html`: 헤더(워드마크+날짜)+면책 한 줄+`{% block %}`. tokens.css·app.css `<link>`.
- `app/templates/settings.html`: §15.5 키 폼(base_currency·monthly_contribution·satellite_limit_pct·rebalance_band_abs·rebalance_band_rel·micro_weight_floor·usd_cash_gate_threshold). POST 실패 시 상태보존.
- `app/db.py`: `save_holdings`·`load_latest_briefing`·`get_settings`·`save_settings`(§4 시그니처). named param 바인딩만(문자열 연결 금지).
- `requirements.txt`: `python-multipart` 추가.
- **DoD**: 설정 폼이 §15.5 키와 일치 / `/api/regenerate` 외부 접근 차단(403) / `uvicorn` 임포트 성공 / 0.0.0.0 미바인딩.

### BAL-31 — holdings.html + POST /holdings 검증
- `app/holdings_form.py`: §4 시그니처. `validate_holdings`는 03 §2.4 표 전량(auto 필수·manual 필수·ccy 일관·ticker 형식·category 값·**target 배타 G5**·**target 합 100%±0.5**·중복 ticker). 실패는 `FieldError` 리스트. 자동 target_pct는 NULL 유지(저장 안 함). category=`''`이면 `CORE_ETF_WHITELIST` 자동판정.
- `app/templates/holdings.html`: §2.1 편집 테이블(고정 N행+빈 행=신규), instrument별 활성 필드, 인라인 에러(`aria-describedby`·`role=alert`), 성공 배너(`?saved=1`), 빈 상태. native `<details>` 불필요(폼).
- **DoD**: 검증 에러 인라인 표시(배타·합100%) / 실패 시 상태보존 400 재렌더 / 중복 ticker 거부.

### BAL-30 — dashboard.html (30초 스캔)
- `app/templates/dashboard.html`: 03 §3.2 순서 — 헤더+면책+regime_label → `doc.banner`(있으면 `--c-warn`) → 신선도 배지(`_components.freshness_badge`) → 자산배분 1·2층 stack-bar(`_components.stack_bar`, `fx_held`시 보류 placeholder) → 요약뷰 종목(`<details open>`=`status!='ok'` or `rebalance_flag`, 나머지 `<details>`; `_components.security_card`) → 리밸런싱/DCA(`portfolio_comment`) → 면책 푸터. `doc is None` → "초기 데이터 적재중" 빈 상태(G3).
- 템플릿은 **계산 0**(F2) — DTO 필드만 신뢰, Jinja 포맷팅만.
- **DoD**: 30초 스캔 흐름 렌더 / JS 꺼도 details 펼침·접힘 / 모바일·데스크톱 반응형 / 손익·수익률 미표시(F7).

## 6. 통합 검증 (각 웨이브 종료 + 최종)
- `python -c "import app.main"` (import 성공)
- `ruff check app/ tests/`
- `pytest -q` (기존 222 그린 유지 + 신규 라우트/검증 테스트)
- 라우트 스모크: `GET /`(200, doc None 빈상태), `GET /holdings`(200), `POST /holdings` 실패(400 상태보존)·성공(303), `GET /settings`(200), `POST /api/regenerate` 외부 host(403).

## 7. Out of Scope
- 실제 LLM 호출/일배치 수집(W3·W4 기존). 대시보드는 `load_latest_briefing()`만.
- 행 추가 JS·`<template>` 복제(§8 선택사항) — PoC는 고정 N행.
- 인증/멀티유저(user_id=1 고정).
