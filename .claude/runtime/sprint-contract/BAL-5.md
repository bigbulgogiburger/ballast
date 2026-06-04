# Sprint Contract — BAL-5 (W5 M4 프론트엔드)

> dev-guide: `docs/BAL-5-dev-guide.md` · 브랜치 `feat/BAL-5` · 단일트리 의존순서(Wave 1→2→3) · Workflow 툴 웨이브 내부 병렬.

## Phases (= Waves)
| Phase | 슬라이스 | 병렬 | 산출 |
|---|---|---|---|
| 1 | BAL-29, BAL-33 | 2 | tokens.css / build_freshness_badge·app.css·_components.html |
| 2 | BAL-32, BAL-31 | 2 | main.py·base·settings·db helpers / holdings_form·holdings.html |
| 3 | BAL-30 | 1 | dashboard.html |

## Definition of Done (집계)
- [ ] 5 슬라이스 §5 DoD 전부 충족
- [ ] `python -c "import app.main"` 성공, `uvicorn app.main:app` 임포트 OK
- [ ] `ruff check app/ tests/` 클린
- [ ] `pytest -q` 그린(기존 222 + 신규)
- [ ] 라우트 스모크 6종(§6) 통과
- [ ] 색 토큰 §15.3 일치 / 등락색 CTA·링크 미사용
- [ ] 템플릿 계산 0(F2) / 손익·수익률 미표시(F7)

## Verify Targets
- `tests/test_main_routes.py`(신규): GET / (200, doc None), /holdings GET/POST(400 상태보존·303), /settings, /api/regenerate 403
- `tests/test_holdings_form.py`(신규): validate_holdings 규칙 8종(§2.4)
- `tests/test_freshness_badge.py`(신규): worst_level 경계(0/1/2/4/5일), 결측 안전 degrade

## Key Rules (CLAUDE.md)
- NEVER 0.0.0.0 바인딩 — 127.0.0.1 전용 / `/api/regenerate` host 게이트
- NEVER SQL 문자열 연결 — named param 바인딩
- NEVER LLM 숫자·면책 생성 — 본 웨이브는 표시 전용(숫자 없음), 면책=`config.DISCLAIMER`
- 템플릿은 BriefingDoc DTO만 신뢰(계산 0)

## Out of Scope
- LLM 호출·일배치 / 행추가 JS / 인증·멀티유저(user_id=1 고정)

## Conflict Resolution (단일 소유)
briefing.py=33 · db.py/main.py/requirements=32 · holdings_form=31 · tokens.css=29 · app.css/_components=33 · templates 분리(base/settings=32, _components=33, holdings=31, dashboard=30). models.py 미수정.

## Iteration / Escalate
- 웨이브 통합 실패 → 해당 슬라이스 재작업(최대 3회) → ESCALATE 시 사용자 재계획.
