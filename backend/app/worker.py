"""Notification delivery worker.

python -m app.worker            # run continuously
python -m app.worker --once     # deliver what is due, then exit (cron / tests)
"""

import argparse
import logging
import threading

import app.models  # noqa: F401  (register every model so foreign keys resolve)
from app.modules.notifications.service import dispatch_due

logger = logging.getLogger("clinicflow.worker")


def run(interval: float, stop: threading.Event | None = None, *, once: bool = False) -> None:
    """Deliver due messages every `interval` seconds until `stop` is set."""
    stop = stop or threading.Event()
    while not stop.is_set():
        try:
            counts = dispatch_due()
            if any(counts.values()):
                logger.info("Delivered: %s", counts)
        except Exception:
            logger.exception("Dispatch cycle failed; retrying next cycle")
        if once:
            return
        stop.wait(interval)


def main() -> None:
    parser = argparse.ArgumentParser(prog="clinicflow-worker")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=15.0)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.interval, once=args.once)


if __name__ == "__main__":
    main()
