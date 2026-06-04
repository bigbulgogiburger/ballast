# INDEX.md — Ballast(BAL) Wiki 카탈로그

> LLM-maintained 카탈로그. **수동 편집 금지** — `jira-ingest`가 갱신한다(정책: `docs/INDEX-SCHEMA.md`).
> 사람용 changelog는 `README`/`CHANGELOG.md`, 이벤트 로그는 `docs/LOG.md`.
> Bootstrap: 2026-06-04 · entries 46 (foundational 9 · decisions 4 · issue_guides 31 · process 2)

<!-- ingest-managed:begin file=INDEX.md -->

## 기반 스펙 (foundational)

| num | file | summary | updated |
|-----|------|---------|---------|
| 00 | [00-e2e-flow.md](00-e2e-flow.md) | E2E 플로우 · S1~S8 계약 · G-게이트 | 2026-06-02 |
| 01 | [01-product-spec.md](01-product-spec.md) | 제품 명세 (요구·AC) | 2026-06-02 |
| 02 | [02-design.md](02-design.md) | 디자인 토큰 (색·타이포·간격) | 2026-06-02 |
| 03 | [03-frontend.md](03-frontend.md) | 프론트엔드 정본 (라우트·DTO·색·검증) | 2026-06-02 |
| 04 | [04-backend.md](04-backend.md) | 백엔드 정본 (어댑터·seam 시그니처) | 2026-06-02 |
| 05 | [05-database.md](05-database.md) | DB 스키마·헬퍼 정본 | 2026-06-02 |
| 06 | [06-ai-agent.md](06-ai-agent.md) | AI 브리핑 에이전트 정본 (프롬프트·면책) | 2026-06-02 |
| 07 | [07-consistency-review.md](07-consistency-review.md) | 정합성 리뷰 | 2026-06-02 |
| 08 | [08-dev-roadmap.md](08-dev-roadmap.md) | W1~W5 마일스톤 로드맵 | 2026-06-02 |

## 의사결정 (decisions)

| file | scope | updated |
|------|-------|---------|
| [adr/0001-claude-md-reference-layer.md](adr/0001-claude-md-reference-layer.md) | ADR-0001 CLAUDE.md 참조 레이어 | 2026-06-04 |
| [adr/0002-single-tree-wave-execution.md](adr/0002-single-tree-wave-execution.md) | ADR-0002 단일트리 wave 실행 (BAL-3·4·5 참조) | 2026-06-04 |
| [BAL-1-m1a-decisions.md](BAL-1-m1a-decisions.md) | W1 M1a 의사결정 로그 | 2026-06-02 |
| [BAL-2-w2-decisions.md](BAL-2-w2-decisions.md) | W2 의사결정 로그 | 2026-06-03 |

## 이슈 dev-guide (issue_guides)

| issue | status | title | week | parent | owns | persona | updated |
|-------|--------|-------|------|--------|------|---------|---------|
| BAL-8 | closed | db.py 연결·스키마·조회/적재 헬퍼 | W1 | – | app/db.py | Python Expert | 2026-06-02 |
| BAL-9 | closed | tickers.py 변환표·코어 ETF 화이트리스트·분류 | W1 | – | app/tickers.py | Python Expert | 2026-06-02 |
| BAL-10 | closed | calendar.py XKRX/XNYS 거래일 | W1 | – | app/calendar.py | Python Expert | 2026-06-02 |
| BAL-11 | closed | sources/kr.py KR 어댑터 + regime KR | W1 | – | app/sources/kr.py, regime.py | Python Expert | 2026-06-02 |
| BAL-12 | closed | validate 빈응답 가드 + 005930 적재 E2E | W1 | – | tests/e2e | Python Expert | 2026-06-02 |
| BAL-13 | closed | sources/us.py US 시세·펀더·뉴스 | W2 | – | app/sources/us.py | Python Expert | 2026-06-03 |
| BAL-14 | closed | sources/fx.py USD/KRW 환율 | W2 | – | app/sources/fx.py | Python Expert | 2026-06-03 |
| BAL-15 | closed | sources/regime.py US CAPE | W2 | – | app/sources/regime.py | Python Expert | 2026-06-03 |
| BAL-16 | closed | sources/etf.py ETF 코어 판정 | W2 | – | app/sources/etf.py | Python Expert | 2026-06-03 |
| BAL-17 | closed | collect.py 일배치 통합자 | W2 | – | app/collect.py | Python Expert | 2026-06-03 |
| BAL-3 | closed | W3 M2 지표 엔진 (부모) | W3 | – | app/metrics/ | Python Expert | 2026-06-04 |
| BAL-3::BAL-18 | closed | §15.2 DTO 전량 + Protocol | W3 | BAL-3 | app/models.py | Python Expert | 2026-06-04 |
| BAL-3::BAL-19 | closed | build_priced 통화정규화·보류 | W3 | BAL-3 | app/metrics/priced.py | Python Expert | 2026-06-04 |
| BAL-3::BAL-20 | closed | metrics.portfolio auto_targets·drift·dca | W3 | BAL-3 | app/metrics/portfolio.py | Python Expert | 2026-06-04 |
| BAL-3::BAL-21 | closed | metrics.security change_pct·valuation·trend | W3 | BAL-3 | app/metrics/security.py | Python Expert | 2026-06-04 |
| BAL-3::BAL-22 | closed | gate evaluate_gate + collect_complete_today | W3 | BAL-3 | app/metrics/gate.py, db.py | Python Expert | 2026-06-04 |
| BAL-3::BAL-23 | closed | test_metrics 커버리지 ≥85% | W3 | BAL-3 | tests/test_metrics.py | Python Expert | 2026-06-04 |
| BAL-4 | closed | W4 M3 AI 브리핑 (부모) | W4 | – | app/briefing.py 외 | Python Expert | 2026-06-04 |
| BAL-4::BAL-24 | closed | ClaudeCLIClient subprocess | W4 | BAL-4 | app/llm.py | Python Expert | 2026-06-04 |
| BAL-4::BAL-25 | closed | prompts/briefing.md | W4 | BAL-4 | app/prompts/briefing.md | Python Expert | 2026-06-04 |
| BAL-4::BAL-26 | closed | SECURITY/PORTFOLIO_SCHEMA | W4 | BAL-4 | app/schemas.py | Python Expert | 2026-06-04 |
| BAL-4::BAL-27 | closed | run_securities/run_portfolio | W4 | BAL-4 | app/briefing.py | Python Expert | 2026-06-04 |
| BAL-4::BAL-28 | closed | assemble_briefing + run_briefing | W4 | BAL-4 | app/briefing.py, config.py | Python Expert | 2026-06-04 |
| BAL-5 | closed | W5 M4 프론트엔드 (부모, 슬라이스 BAL-29~33 단일 master) | W5 | – | app/main.py·templates·static | Python Expert | 2026-06-04 |
| BAL-6 | closed | W6 M5 통합·무인운영·하드닝 (부모, 형제 BAL-34~39) | W6 | – | scripts/·ops/·app(notify·collect·db·llm) | Python Expert | 2026-06-04 |
| BAL-6::BAL-34 | closed | scripts 진입점 + make_llm_client 팩토리 | W6 | BAL-6 | scripts/, app/llm.py | Python Expert | 2026-06-04 |
| BAL-6::BAL-35 | closed | launchd 스케줄러(08:00/08:30) + wake | W6 | BAL-6 | ops/*.plist, install.sh | Python Expert | 2026-06-04 |
| BAL-6::BAL-36 | closed | 백필완료 게이트 G9 핸드오프(순환버그 수정) | W6 | BAL-6 | app/db.py | Python Expert | 2026-06-04 |
| BAL-6::BAL-37 | closed | 수집 FAIL 푸시 알림(ntfy/Telegram) | W6 | BAL-6 | app/notify.py, collect.py | Python Expert | 2026-06-04 |
| BAL-6::BAL-38 | closed | 보안 하드닝 회귀(127.0.0.1·.env·data/) | W6 | BAL-6 | app/main.py, .gitignore | Python Expert | 2026-06-04 |
| BAL-6::BAL-39 | closed | E2E 무인 1사이클 리허설 | W6 | BAL-6 | tests/test_e2e_rehearsal.py | Python Expert | 2026-06-04 |

> BAL-5 슬라이스(BAL-29 tokens·30 dashboard·31 holdings·32 routes·33 components)는 단일 master dev-guide(BAL-5-dev-guide.md)로 관리 — 별도 슬라이스 파일 없음.
> BAL-6 형제 중 BAL-35만 dev-guide(BAL-35-dev-guide.md) 보유 — 나머지는 Workflow 툴 wave 직접 구현. 머지 e0f99a3·37672e6·e51d37e.

## 오케스트레이션 (process)

| file | scope | updated |
|------|-------|---------|
| [BAL-1-m1a-orchestration.md](BAL-1-m1a-orchestration.md) | W1 M1a wave 실행 + seam 시그니처 정본 §2 | 2026-06-02 |
| [BAL-2-w2-orchestration.md](BAL-2-w2-orchestration.md) | W2 wave 실행 + 시그니처 정본 §2.1~2.7 | 2026-06-03 |

<!-- ingest-managed:end file=INDEX.md -->
