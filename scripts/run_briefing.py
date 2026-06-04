"""일배치 브리핑 진입점 (BAL-34).

db.connect() → briefing.run_briefing(conn, llm=make_llm_client()) → conn.close().
성공 exit(0), 예외 logging.error + exit(1).
"""
import logging
import sys

from app import briefing, db
from app.llm import make_llm_client

log = logging.getLogger(__name__)


def main() -> int:
    try:
        conn = db.connect()
        try:
            briefing.run_briefing(conn, llm=make_llm_client())
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 — 진입점 최종 핸들러
        logging.error("run_briefing failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
