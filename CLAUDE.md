# CLAUDE.md — Ballast (BAL)

## Project Overview
FastAPI (Python) — AI 투자 브리핑 웹서비스. 한국/해외 시장 데이터(pykrx·DART·yfinance·FMP·SEC 등)를 수집해 LLM으로 일일 브리핑을 생성한다. **응답은 한국어로 해주세요.**

## Architecture

```mermaid
graph TD
  subgraph Sources["sources/ (어댑터)"]
    KR[kr.py]; US[us.py]; FX[fx.py]; RG[regime.py]; ETF[etf.py·R2]
    GUARD[__init__: retry·validate_response·EmptyResponseError]
  end
  subgraph Core
    COLLECT[collect.py 일배치]; DB[(db.py · SQLite 9테이블)]
    TICK[tickers.py]; CAL[calendar.py]; MODELS[models.py DTO]
  end
  subgraph Consume["지표·브리핑 (W3·W4 구현 / main.py=W5 스텁)"]
    MET[metrics/ priced·portfolio·security·gate]; BRIEF[briefing.py 조립]; MAIN[main.py FastAPI/Jinja2]
    LLM[llm.py ClaudeCLIClient]; SCH[schemas.py]; PR[prompts/briefing.md]
  end
  KR & US & FX & RG --> COLLECT --> DB
  GUARD --> KR & US & FX & RG
  COLLECT --> TICK & CAL
  DB --> MET --> BRIEF --> MAIN
  SCH & LLM & PR --> BRIEF
```

### Domain Modules
| Module | 책임 |
|--------|------|
| `app/sources/` | 외부 무료 데이터 어댑터(Protocol, 종목 격리) |
| `app/collect.py` | 일배치 — 수집·적재·collect_run 게이트 |
| `app/db.py` | SQLite 연결/스키마/조회·적재 헬퍼 |
| `app/tickers.py`·`calendar.py` | 티커 정규화 · 거래일(XKRX/XNYS) |
| `app/models.py` | frozen DTO (OHLCV·Funda·Headline·RegimeRow·FxRate + §15.2 SecurityCard·BriefingDoc·PricedHolding·SecurityLLMOut·HoldExcluded) |
| `app/metrics/` | 지표 엔진 — priced(통화정규화)·portfolio(5/25)·security(밸류)·gate(신선도) (W3·BAL-3) |
| `app/briefing.py`·`llm.py`·`schemas.py` | AI 브리핑 — claude -p 어댑터·스키마·run/assemble (숫자는 코드 주입) (W4·BAL-4) |
| `app/main.py`·`holdings_form.py`·`templates/`·`static/` | FastAPI/Jinja2 웹 — 라우트 4종·보유입력 검증·30초 스캔 대시보드·신선도 배지·자산배분 stack-bar (W5·BAL-5) |

## Commands
```bash
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000   # 127.0.0.1 전용
pytest -q                                            # 테스트 (252)
ruff check app/ tests/                               # 린트 (커밋 전)
```

## Key Rules
- **NEVER `0.0.0.0` 바인딩** — `127.0.0.1` 전용.
- **NEVER `.env` 커밋** — `.env.example`만. 시크릿은 `os.environ`. API 키는 URL/로그 노출 금지(헤더 우선).
- **NEVER `data/`를 클라우드 동기화 폴더에** — 금융정보 유출 방지.
- **NEVER 빈 응답을 OK로** — `validate_response(rows=0)`→`EmptyResponseError`. "예외 안 남 ≠ 데이터 실재".
- **NEVER fx 결측 시 분모 제외** — 산출 거부(0/NULL 위장 금지).
- **NEVER 제공자 PER/PBR 자체 재계산** — 제공자 계산값만 캐시.
- **NEVER SQL을 문자열 연결로** — `?`/named param 바인딩만(named param=컬럼 전체명).
- **NEVER LLM이 숫자·면책 생성** — 숫자는 `{placeholder}`만(RAW_NUMBER 린트 reject, 코드가 주입), 면책은 코드 상수(`config.DISCLAIMER`). 보류 종목(hold_status≠'ok')은 LLM 미호출.

## Git Conventions
- 커밋: `<type>(BAL-N): <설명>` (feat/fix/test/docs/chore). base/기본 브랜치 = **`master`가 아니라 `main`** (remote: github.com/bigbulgogiburger/ballast).

## Harness Engineering Integration
- `HARNESS_MODE`(`.claude/settings.local.json`, 현재 **auto**): `auto`=강제 주입+커밋 게이트 차단 / `suggest`=제안만 / `off`=비활성.
- 워크플로: /jira-plan→/harness-plan, /jira-execute Phase 후→/harness-review, /jira-commit 전 aggregate-verdict 확인.
- 에이전트: 프로젝트 `bal-*`(explorer·security-reviewer·test-writer·build-resolver) 우선.
- 아티팩트: dev-guide `docs/{KEY}-dev-guide.md` · Sprint Contract·Verdict·State `.claude/runtime/` (완료분 `archive/{EPIC}/`).

## Reference Docs
| 문서 | 참조 시점 | 경로 |
|------|----------|------|
| 모듈 맵·데이터 흐름 | 새 모듈·seam | `.claude/docs/reference/architecture.md` |
| 어댑터 패턴 | 새 소스·폴백·재시도 | `.claude/docs/reference/source-adapters.md` |
| DB 스키마·헬퍼 | 테이블·쿼리·upsert | `.claude/docs/reference/database.md` |
| 일배치 | collect·게이트·백필 | `.claude/docs/reference/data-collection.md` |
| 테스트 규약 | 테스트 추가 | `.claude/docs/reference/testing.md` |
| 설계 SoT(정본) | 요구·백엔드·DB·AI | `docs/01-product-spec.md` · `04-backend.md` · `05-database.md` · `06-ai-agent.md` |
| 마일스톤 dev-guide | wave·슬라이스·결정 | `docs/BAL-{N}-dev-guide.md`(BAL-3·4·5) · `BAL-{1,2}-*-orchestration.md`·`*-decisions.md` |
| Wiki Index | 착수 시 관련 이슈·dev-guide·상태 조회 | `docs/INDEX.md` |
| Wiki Log | ingest 이벤트 로그 (append-only) | `docs/LOG.md` |
| Wiki Schema | wiki 카테고리·정책 (사용자 편집) | `docs/INDEX-SCHEMA.md` |

> ⚠️ `TECH-DESIGN.md`는 레포에 없음 — `docs/04·05·01`이 정본.
> 📚 새 dev-guide 작성/완료 시 INDEX/LOG 자동 갱신(jira-plan/jira-complete chain). 누락 시 `/jira-ingest <KEY>`.

---
Last Updated: 2026-06-04 (W3 지표엔진 BAL-3 · W4 AI브리핑 BAL-4 · W5 프론트엔드 BAL-5(BAL-29~33) 구현·main 머지)
