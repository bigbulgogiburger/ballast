# Architecture — 모듈 맵 & 데이터 흐름

> 참조 시점: 새 모듈 추가, 데이터 흐름 이해, seam 계약 확인. SoT = `docs/04-backend.md`/`docs/05-database.md`.

## 레이어 (W1~W6 전량 구현 완료)

```
sources/ (어댑터)  →  collect.py (일배치 08:00)  →  db.py (SQLite 9테이블)
                                                       ↓
                metrics/ (priced·portfolio·security·gate)
                                                       ↓
                briefing.py + llm.py (08:30, claude -p)  →  main.py (FastAPI/Jinja2)
                                                       ↓
                notify.py (수집 FAIL · 브리핑 도착 푸시)
```

- **sources/** — 외부 무료 데이터 어댑터. Protocol 구현, 종목 단위 격리. (`source-adapters.md`)
- **collect.py** — 일배치 + `collect_run` 게이트 기록. (`data-collection.md`)
- **db.py** — 연결/스키마/조회·적재 헬퍼. (`database.md`)
- **metrics/** — 5종 지표 + 신선도 게이트. (`metrics.md`)
- **briefing.py·llm.py·schemas.py** — LLM 브리핑(슬롯주입·린트·why_note). (`ai-briefing.md`)
- **main.py·templates/·static/** — 웹 대시보드. (`frontend.md`)
- **scripts/·ops/·notify.py** — 무인운영·스케줄·알림. (`operations.md`)

## 모듈 인벤토리

| 모듈 | 책임 | 상태 |
|------|------|------|
| `app/models.py` | frozen DTO 전량 (§15.2 — OHLCV·Funda·SecurityCard·BriefingDoc 등) | 구현 |
| `app/db.py` | connect/init_schema/latest_*/upsert_*/load_latest_briefing/is_backfill_complete | 구현 |
| `app/tickers.py` · `calendar.py` | 티커 정규화 · 거래일(XKRX/XNYS) | 구현 |
| `app/sources/{kr,us,fx,regime}.py` | KR/US/FX/레짐 어댑터 (+ `__init__` 공통 가드) | 구현 |
| `app/sources/etf.py` | ETF 룩스루 | 스텁(R2 연기) |
| `app/collect.py` | 일배치 통합자 (daily/backfill) | 구현 |
| `app/metrics/{priced,portfolio,security,gate}.py` | 통화정규화·5/25·밸류·게이트 | 구현 (W3) |
| `app/briefing.py` · `llm.py` · `schemas.py` · `prompts/` | AI 브리핑 + why_note 변동 귀인 | 구현 (W4 + Level 1) |
| `app/main.py` · `holdings_form.py` · `templates/` · `static/` | 라우트 4종·검증·터미널 UI·모바일 | 구현 (W5 + Level 1) |
| `app/notify.py` | ntfy/Telegram 푸시 (FAIL + 브리핑 도착) | 구현 (W6 + Level 1) |
| `scripts/` · `ops/` | 진입점·launchd 스케줄·백필 핸드오프(G9) | 구현 (W6) |

## 마일스톤 매핑

- **W1~W6 (BAL-1~6)**: 데이터 레이어 → 지표 → AI 브리핑 → 프론트 → 무인운영 — 전량 closed.
- **Level 1 (2026-06)**: 브리핑 도착 푸시 · 모바일 반응형 · 변동 귀인(why_note) · 데이터 출처 UI.
- **이후**: dogfooding 검증 → `docs/PRODUCT-VISION-NEXT-LEVEL.md`(Level 2: 대화형 Q&A·주간 리뷰·장중 트리거).

## seam 계약 정본

W별 = `docs/BAL-{N}-*-orchestration.md` + `*-decisions.md` / dev-guide.
⚠️ `TECH-DESIGN.md`는 레포에 없음 — `docs/01·03·04·05·06`이 정본.
