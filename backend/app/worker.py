"""Notification delivery worker.

python -m app.worker            # run continuously
python -m app.worker --once     # deliver what is due, then exit (cron / tests)
"""

import argparse
import logging
import time

import app.models  # noqa: F401  (register every model so foreign keys resolve)
from app.modules.notifications.service import dispatch_due

logger = logging.getLogger("clinicflow.worker")


def main() -> None:
    parser = argparse.ArgumentParser(prog="clinicflow-worker")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=15.0)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    while True:
        try:
            counts = dispatch_due()
            if any(counts.values()):
                logger.info("Delivered: %s", counts)
        except Exception:
            logger.exception("Dispatch cycle failed; retrying next cycle")
        if args.once:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
