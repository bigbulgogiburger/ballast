"""일배치 수집 진입점 (BAL-34).

--backfill 명시 → backfill 모드.
미지정(G9 핸드오프) → DB 백필 완료 여부 조회: 미완이면 backfill, 완료면 daily.
성공 exit(0), 예외 logging.error + exit(1).
"""
import argparse
import logging
import sys

from app import collect, db

log = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Ballast 일배치 수집")
    parser.add_argument("--backfill", action="store_true", help="백필 모드 강제")
    args = parser.parse_args()

    try:
        if args.backfill:
            collect.run_collect("backfill")
        else:
            # G9 핸드오프: 백필 완료 여부에 따라 모드 결정.
            conn = db.connect()
            try:
                complete = db.is_backfill_complete(conn)
            finally:
                conn.close()
            collect.run_collect("daily" if complete else "backfill")
    except Exception as exc:  # noqa: BLE001 — 진입점 최종 핸들러
        logging.error("run_collect failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
