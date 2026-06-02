# Ballast (BAL) — AI 투자 브리핑

FastAPI 기반 AI 투자 브리핑 웹서비스. 한국/해외 시장 데이터(pykrx·DART·yfinance 등)를 수집해 LLM으로 일일 브리핑을 생성한다.

## 스택
- Python / FastAPI / Jinja2, 테스트는 pytest + httpx
- 데이터 소스 어댑터: `app/sources/`

## 실행 / 테스트
```bash
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000   # 127.0.0.1 전용 바인딩 (0.0.0.0 금지)
pytest
```

## 문서 (docs/)
- `00-e2e-flow.md` · `01-product-spec.md` · `02-design.md` · `03-frontend.md`
- `04-backend.md` · `05-database.md` · `06-ai-agent.md` · `07-consistency-review.md` · `08-dev-roadmap.md`

## 보안 주의
- `.env`는 커밋 금지(`.env.example`만). 시크릿은 `os.environ`로 로드.
- `data/`는 클라우드 동기화 폴더 밖에 둔다(금융정보 유출 방지).

## Harness Engineering Integration
### 운영 모드
- `HARNESS_MODE`는 `.claude/settings.local.json` 참조 (현재: **auto**)
- `auto`: Hook이 harness 단계를 강제 주입 + 커밋 게이트 차단
- `suggest`: Hook이 제안만
- `off`: Harness 비활성
### 워크플로 규칙
- /jira-plan 완료 후 /harness-plan 실행을 제안하라
- /jira-execute 각 Phase 완료 후 /harness-review를 제안하라
- /jira-commit 전 aggregate-verdict.md 확인을 권장하라
### 에이전트 디스패치
- 프로젝트 에이전트(bal-*)는 글로벌 에이전트보다 우선
- 핵심 4종: `bal-explorer`, `bal-security-reviewer`, `bal-test-writer`, `bal-build-resolver`
### 아티팩트 경로
- dev-guide: `docs/{ISSUE-KEY}-dev-guide.md`
- Sprint Contract: `.claude/runtime/sprint-contract/{ISSUE-KEY}.md`
- Verdict: `.claude/runtime/aggregate-verdict.md`
- State: `.claude/runtime/workflow-state.json`
