# Operations — 무인운영·스케줄·알림 (`ops/`·`scripts/`·`app/notify.py`)

> 참조 시점: 배치 스케줄·진입점·알림 채널·백필 핸드오프 수정. SoT = W6 dev-guide(BAL-34~39).

## 스케줄 (macOS launchd — SoT)

| plist | 시각 (KST, 월~금) | 실행 |
|-------|------------------|------|
| `ops/com.ballast.collect.plist` | 08:00 | `scripts/run_collect.py` |
| `ops/com.ballast.briefing.plist` | 08:30 | `scripts/run_briefing.py` |

`ops/install.sh` 원클릭 등록. `caffeinate`/`pmset` 절전 대응 — 단, 맥북 전원 꺼짐은 수집 불가(알려진 한계).

## 진입점 (`scripts/`)

- `run_collect.py` — `--backfill` 명시 시 backfill, 무인자 시 `db.is_backfill_complete`로 **G9 핸드오프**
  (모든 auto 종목 price/funda row + KR percentile NOT NULL → daily 전환). status='BACKFILL' 기준 판정은
  순환버그라 금지 — 데이터 완성도로만 판정.
- `run_briefing.py` — `briefing.run_briefing(conn, llm=make_llm_client())`. 성공 시 `_notify_success`
  (best-effort — 알림 예외가 exit code 오염 금지), 예외 → exit 1.

## 알림 (`app/notify.py` — urllib만, 외부 라이브러리 없음)

| 함수 | 트리거 | 본문 |
|------|--------|------|
| `send_fail_alert(market, reason)` | 수집 FAIL (backfill 모드는 억제) | 고정 문자열 — 예외 원문/시크릿 금지, 200자 절단 |
| `send_briefing_alert(headline, flag_count)` | 브리핑 생성 성공 (Level 1) | 헤드라인(banner 우선)·리밸런싱 플래그 수·대시보드 링크 |

채널 env: `NTFY_URL` / `TELEGRAM_BOT_TOKEN`+`TELEGRAM_CHAT_ID`(둘 다 필요) / `BALLAST_DASHBOARD_URL`(링크 교체, 기본 127.0.0.1:8000). 미설정 → 조용히 스킵(log.warning).

## NEVER

- **알림 실패가 배치를 중단 금지** — HTTP 예외 전부 삼킴, 예외 '타입명'만 로그(토큰 포함 URL 로그 금지).
- **비-HTTP 스킴 차단** — `file://` 등은 발송 거부(SSRF/로컬파일 방지).
- **Telegram 토큰은 URL path에만** — 로그/예외 메시지 노출 금지.
- **`data/` 클라우드 동기화 금지** — 금융정보 유출 방지(CLAUDE.md).

## 운영 점검

- `collect_run` status: OK / PARTIAL / FAIL / BACKFILL / OK_HOLIDAY — 차단은 FAIL만.
- 신선도 배지 `consecutive_fallback` — 전 시장 연속 비정상 시 대시보드 경고.
- 수동 재생성: 로컬에서 `POST /api/regenerate`(127.0.0.1 한정).
