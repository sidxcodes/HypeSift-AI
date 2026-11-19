from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import account, clips, library, misc, projects, uploads
from .config import get_settings
from .db import init_db
from .jobs import Worker
from .pipeline.render import FONTS_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("hypesift")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    s = get_settings()
    init_db()
    worker = None
    if s.embedded_worker:
        worker = Worker(s.worker_concurrency)
        worker.start()
        log.info("embedded worker started (%d thread(s))", s.worker_concurrency)

    stop = threading.Event()

    def janitor() -> None:
        from .tasks import cleanup_temp

        while not stop.wait(3600):
            try:
                cleanup_temp()
            except Exception:  # noqa: BLE001
                log.exception("cleanup failed")

    threading.Thread(target=janitor, daemon=True).start()
    yield
    stop.set()
    if worker:
        worker.stop()


app = FastAPI(title="HypeSift AI API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (account.router, uploads.router, projects.router, clips.router, library.router, misc.router):
    app.include_router(r)

# Caption fonts, so the browser preview renders with exactly the fonts libass burns in.
app.mount("/api/fonts", StaticFiles(directory=FONTS_DIR), name="fonts")


@app.exception_handler(ValueError)
async def value_error(_req: Request, exc: ValueError):
    return JSONResponse(status_code=422, content={"detail": str(exc)})
