"""Standalone worker process: ``python -m app.worker``.

Use it with ``HYPESIFT_EMBEDDED_WORKER=false`` on the API to scale processing
separately (e.g. API on a small VM, worker on a GPU box sharing Postgres + storage).
"""

from __future__ import annotations

import logging
import signal
import threading

from .config import get_settings
from .db import init_db
from .jobs import Worker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main() -> None:
    init_db()
    w = Worker(get_settings().worker_concurrency)
    w.start()
    done = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: done.set())
    signal.signal(signal.SIGTERM, lambda *_: done.set())
    logging.getLogger("hypesift").info("worker running; Ctrl+C to stop")
    done.wait()
    w.stop()


if __name__ == "__main__":
    main()
