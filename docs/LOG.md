# LOG.md — Ballast(BAL) Wiki 이벤트 로그 (append-only)

> `jira-ingest`가 append. 수동 편집 금지. 형식: `[<ts> KST <EVENT> <key> <mode>] <detail>`

[2026-06-04T16:30 KST BOOTSTRAP] wiki 초기화 — INDEX-SCHEMA.md·INDEX.md·LOG.md 생성. entries=38 (foundational 9·decisions 3·issue_guides 24·process 2). issue_prefix=BAL.
[2026-06-02T13:43 KST INGEST BAL-8 closure] guide=BAL-8-dev-guide.md week=W1 owns=app/db.py
[2026-06-02T13:43 KST INGEST BAL-9 closure] guide=BAL-9-dev-guide.md week=W1 owns=app/tickers.py
[2026-06-02T13:43 KST INGEST BAL-10 closure] guide=BAL-10-dev-guide.md week=W1 owns=app/calendar.py
[2026-06-02T13:43 KST INGEST BAL-11 closure] guide=BAL-11-dev-guide.md week=W1 owns=app/sources/kr.py,regime.py
[2026-06-02T13:43 KST INGEST BAL-12 closure] guide=BAL-12-dev-guide.md week=W1 owns=tests/e2e(005930)
[2026-06-03T15:06 KST INGEST BAL-13 closure] guide=BAL-13-dev-guide.md week=W2 owns=app/sources/us.py
[2026-06-03T15:06 KST INGEST BAL-14 closure] guide=BAL-14-dev-guide.md week=W2 owns=app/sources/fx.py
[2026-06-03T15:06 KST INGEST BAL-15 closure] guide=BAL-15-dev-guide.md week=W2 owns=app/sources/regime.py
[2026-06-03T15:06 KST INGEST BAL-16 closure] guide=BAL-16-dev-guide.md week=W2 owns=app/sources/etf.py
[2026-06-03T15:06 KST INGEST BAL-17 closure] guide=BAL-17-dev-guide.md week=W2 owns=app/collect.py
[2026-06-04T13:23 KST INGEST BAL-3 closure] guide=BAL-3-dev-guide.md week=W3 parent=- (epic) slices=BAL-18..23
[2026-06-04T13:23 KST INGEST BAL-3::BAL-18 closure] guide=BAL-3-BAL-18-dev-guide.md parent=BAL-3 owns=app/models.py
[2026-06-04T13:23 KST INGEST BAL-3::BAL-19 closure] guide=BAL-3-BAL-19-dev-guide.md parent=BAL-3 owns=app/metrics/priced.py
[2026-06-04T13:23 KST INGEST BAL-3::BAL-20 closure] guide=BAL-3-BAL-20-dev-guide.md parent=BAL-3 owns=app/metrics/portfolio.py
[2026-06-04T13:23 KST INGEST BAL-3::BAL-21 closure] guide=BAL-3-BAL-21-dev-guide.md parent=BAL-3 owns=app/metrics/security.py
[2026-06-04T13:23 KST INGEST BAL-3::BAL-22 closure] guide=BAL-3-BAL-22-dev-guide.md parent=BAL-3 owns=app/metrics/gate.py,db.py
[2026-06-04T13:23 KST INGEST BAL-3::BAL-23 closure] guide=BAL-3-BAL-23-dev-guide.md parent=BAL-3 owns=tests/test_metrics.py
[2026-06-04T14:56 KST INGEST BAL-4 closure] guide=BAL-4-dev-guide.md week=W4 parent=- (epic) slices=BAL-24..28
[2026-06-04T14:56 KST INGEST BAL-4::BAL-24 closure] guide=BAL-4-BAL-24-dev-guide.md parent=BAL-4 owns=app/llm.py
[2026-06-04T14:56 KST INGEST BAL-4::BAL-25 closure] guide=BAL-4-BAL-25-dev-guide.md parent=BAL-4 owns=app/prompts/briefing.md
[2026-06-04T14:56 KST INGEST BAL-4::BAL-26 closure] guide=BAL-4-BAL-26-dev-guide.md parent=BAL-4 owns=app/schemas.py
[2026-06-04T14:56 KST INGEST BAL-4::BAL-27 closure] guide=BAL-4-BAL-27-dev-guide.md parent=BAL-4 owns=app/briefing.py
[2026-06-04T14:56 KST INGEST BAL-4::BAL-28 closure] guide=BAL-4-BAL-28-dev-guide.md parent=BAL-4 owns=app/briefing.py,config.py
[2026-06-04T16:04 KST INGEST BAL-5 closure] guide=BAL-5-dev-guide.md week=W5 parent=- (epic) slices=BAL-29..33 (단일 master) merge=ffcf6ac
[2026-06-04T16:40 KST LINT baseline] mode=full score=88 errors=1(L05) warnings=3(L08·L06·L11) clean=10
[2026-06-04T16:42 KST LINT-FIX BAL-3] rule=L05 action=phantom-adr-resolved detail=ADR-070→ADR-0002(신규 docs/adr/0002) 참조 교체
[2026-06-04T16:42 KST LINT-FIX *] rule=L08 action=frontmatter-added detail=dev-guide 24개 YAML frontmatter prepend (issue/type/status/week/parent/created/closed)
[2026-06-04T16:43 KST LINT post-fix] score=96 errors=0 warnings=2(L06 정보성·L11 정렬 수용) clean=12
