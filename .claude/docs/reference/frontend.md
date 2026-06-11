# Frontend — FastAPI/Jinja2 웹 (`app/main.py`·`templates/`·`static/`)

> 참조 시점: 라우트·템플릿·CSS·폼 검증 수정. SoT = `docs/03-frontend.md`(03 §) / `docs/04-backend.md §6`.

## 라우트 (`app/main.py`)

| 라우트 | 동작 |
|--------|------|
| `GET /` | 대시보드 — `load_latest_briefing` + `build_freshness_badge`. doc None → 빈 상태(G3) |
| `GET/POST /holdings` | 보유입력 — parse→validate, 실패 400 상태보존 재렌더, 성공 303 PRG(`?saved=1`) |
| `GET/POST /settings` | §15.5 설정 7키만 채택 |
| `POST /api/regenerate` | 수동 재생성 — `request.client.host != '127.0.0.1'` → 403 |
| `GET /healthz` | 헬스체크 |

연결은 요청 단위 `_conn()`(connect + init_schema 멱등). **바인딩 127.0.0.1 전용 — 0.0.0.0 금지.**

## 템플릿 구조

- `base.html` — 톱바·면책 라인·폰트(IBM Plex Mono/Sans KR)·tokens.css+app.css.
- `_components.html` 매크로 — `freshness_badge` / `stack_bar`(CSS 누적바) / `change_badge`(색+부호 병기) / `security_card`(status 분기: failed·보류 placeholder·ok `<details>` 펼침).
- `dashboard.html` — 레짐 → 배너 → 배지 → 자산배분 1·2층 → 종목 카드 → 리밸런싱/DCA → **데이터 기준일·출처 섹션**(Level 1) → 면책 푸터.
- **계산 0 원칙** — 템플릿은 DTO 필드 포맷팅만, 수치 연산 금지.

## 보유입력 검증 (`app/holdings_form.py`)

`parse_holdings_form`(rows[i][field] 파싱) → `validate_holdings`(category 자동판정, target_pct 배타·합100%).
실패 시 입력값 보존 재렌더(F5).

## CSS (`static/css/`)

- `tokens.css` — 색·간격·라운드 변수(다크 터미널 팔레트, `--c-up/--c-down` 한국 관습).
- `app.css` — Data-Dense 트레이딩 터미널. 주요 클래스: `.density`(모노 tabular 표)·`.sec-card`·`.stack-bar`·`.badge--{fresh,stale,warn}`·`.why-note`(변동 귀인 강조)·`.source-line`(출처 표기).
- **모바일 `@media (max-width: 640px)`** (Level 1) — 톱바 wrap·탭 타깃 확대·카드 summary wrap·종목명 말줄임·density/holdings 테이블 가로 스크롤.

## 카드 status 렌더 분기 (빈칸 금지 — G3/G6)

`failed`(처리 실패) / `data_pending`(데이터 준비중) / `fx_held`(환율 결측 보류) / `warmup`(5년 워밍업) / `ok`(정상 — rebalance_flag 시 펼침). 현금은 'ok' 값 카드.

## NEVER

- 템플릿에서 수치 계산 금지 — 코드(metrics/briefing)가 계산, Jinja는 포맷만.
- JS 의존 금지 — `<details>` 등 네이티브 요소로 동작(현재 JS 0).
- 면책 문구 하드코딩 금지 — `config.DISCLAIMER` 주입.
