"""일배치 브리핑 진입점 (BAL-34).

db.connect() → briefing.run_briefing(conn, llm=make_llm_client()) → conn.close().
성공 시 푸시 알림(send_briefing_alert) 후 exit(0), 예외 logging.error + exit(1).
"""
import logging
import sys

from app import briefing, db, notify
from app.llm import make_llm_client

log = logging.getLogger(__name__)


def _notify_success(conn) -> None:
    """생성된 최신 브리핑 요약으로 도착 알림. 알림 실패가 배치를 실패시키면 안 됨."""
    try:
        doc = db.load_latest_briefing(conn)
        if doc is None:
            return
        headline = doc.banner or doc.regime_label
        flag_count = sum(1 for c in doc.securities if c.rebalance_flag)
        notify.send_briefing_alert(headline, flag_count)
    except Exception as exc:  # noqa: BLE001 — 알림은 best-effort
        log.warning("briefing alert skipped: %s", type(exc).__name__)


def main() -> int:
    try:
        conn = db.connect()
        try:
            briefing.run_briefing(conn, llm=make_llm_client())
            _notify_success(conn)
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 — 진입점 최종 핸들러
        logging.error("run_briefing failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
