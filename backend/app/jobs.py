"""Persistent job queue backed by the ``jobs`` table.

Why not Redis + Celery? For a single-node, zero-cost deployment the database already
gives durability, atomic claiming and status history; one fewer service to run. The
handler interface (``kind`` → function) maps 1:1 onto Celery tasks if scale demands it.

Workers either run inside the API process (``HYPESIFT_EMBEDDED_WORKER=true``, default
for local dev) or as a separate process: ``python -m app.worker``.
"""

from __future__ import annotations

import logging
import threading
import time
import traceback
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select, update

from .config import get_settings
from .db import SessionLocal
from .models import Job
from .pipeline.ffmpeg import Cancelled, MediaError

log = logging.getLogger("hypesift.jobs")

HANDLERS: dict[str, Callable[[JobContext], None]] = {}


def handler(kind: str):
    def deco(fn):
        HANDLERS[kind] = fn
        return fn

    return deco


class UserFacingError(Exception):
    """Errors whose message is safe and useful to show in the UI."""


class JobContext:
    """Handed to handlers: real progress reporting + cooperative cancellation."""

    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        self._last_write = 0.0
        self._stage_weights: dict[str, float] = {}
        self._done_weight = 0.0
        self._stage: str | None = None
        with SessionLocal() as db:
            j = db.get(Job, job_id)
            assert j
            self.kind, self.payload = j.kind, dict(j.payload or {})
            self.user_id, self.project_id, self.clip_id = j.user_id, j.project_id, j.clip_id

    def plan(self, stages: dict[str, float]) -> None:
        total = sum(stages.values()) or 1
        self._stage_weights = {k: v / total for k, v in stages.items()}
        with SessionLocal() as db:
            j = db.get(Job, self.job_id)
            j.stages = [{"key": k, "status": "pending"} for k in stages]
            db.commit()

    def stage(self, key: str, message: str = "") -> None:
        if self._stage and self._stage in self._stage_weights:
            self._done_weight += self._stage_weights[self._stage]
        self._stage = key
        self._write(stage=key, message=message, progress=self._done_weight, force=True, stage_status=(key, "running"))

    def progress(self, frac: float, message: str | None = None) -> None:
        w = self._stage_weights.get(self._stage or "", 0)
        self._write(progress=self._done_weight + w * max(0.0, min(1.0, frac)), message=message)

    def cancelled(self) -> bool:
        with SessionLocal() as db:
            return bool(db.scalar(select(Job.cancel_requested).where(Job.id == self.job_id)))

    def check_cancel(self) -> None:
        if self.cancelled():
            raise Cancelled("cancelled")

    def _write(self, force: bool = False, stage_status: tuple[str, str] | None = None, **fields) -> None:
        now = time.time()
        if not force and now - self._last_write < 0.7:
            return
        self._last_write = now
        with SessionLocal() as db:
            j = db.get(Job, self.job_id)
            if not j:
                return
            for k, v in fields.items():
                if v is not None:
                    setattr(j, k, round(v, 4) if isinstance(v, float) else v)
            if stage_status:
                stages = [dict(s) for s in (j.stages or [])]
                for s in stages:
                    if s["key"] == stage_status[0]:
                        s["status"] = stage_status[1]
                        s["started_at"] = datetime.now(UTC).isoformat()
                    elif s["status"] == "running":
                        s["status"] = "done"
                j.stages = stages
            db.commit()


def enqueue(
    db,
    *,
    user_id: str,
    kind: str,
    project_id: str | None = None,
    clip_id: str | None = None,
    payload: dict | None = None,
) -> Job:
    job = Job(user_id=user_id, kind=kind, project_id=project_id, clip_id=clip_id, payload=payload or {})
    db.add(job)
    db.commit()
    return job


def active_jobs(db, user_id: str) -> int:
    from sqlalchemy import func

    return (
        db.scalar(
            select(func.count()).select_from(Job).where(Job.user_id == user_id, Job.status.in_(("queued", "running")))
        )
        or 0
    )


def _claim() -> str | None:
    with SessionLocal() as db:
        job_id = db.scalar(select(Job.id).where(Job.status == "queued").order_by(Job.created_at).limit(1))
        if not job_id:
            return None
        res = db.execute(
            update(Job)
            .where(Job.id == job_id, Job.status == "queued")
            .values(status="running", started_at=datetime.now(UTC), attempts=Job.attempts + 1)
        )
        db.commit()
        return job_id if res.rowcount == 1 else None


def _finish(job_id: str, status: str, error: str | None = None) -> None:
    with SessionLocal() as db:
        j = db.get(Job, job_id)
        if not j:
            return
        j.status = status
        j.error = error
        j.finished_at = datetime.now(UTC)
        if status == "succeeded":
            j.progress = 1.0
            j.stage = "done"
            j.stages = [{**s, "status": "done"} for s in (j.stages or [])]
        else:
            j.stages = [
                {**s, "status": "failed" if s["status"] == "running" else s["status"]} for s in (j.stages or [])
            ]
        db.commit()


def run_job(job_id: str) -> None:
    ctx = JobContext(job_id)
    fn = HANDLERS.get(ctx.kind)
    try:
        if not fn:
            raise UserFacingError(f"Unknown job type '{ctx.kind}'.")
        fn(ctx)
        _finish(job_id, "succeeded")
    except Cancelled:
        _finish(job_id, "cancelled", "Cancelled by user.")
        _on_fail(ctx, "Cancelled.")
    except (UserFacingError, MediaError) as e:
        log.warning("job %s failed: %s", job_id, e)
        _finish(job_id, "failed", str(e))
        _on_fail(ctx, str(e))
    except Exception as e:  # noqa: BLE001
        log.error("job %s crashed:\n%s", job_id, traceback.format_exc())
        with SessionLocal() as db:
            j = db.get(Job, job_id)
            retry = j and j.attempts < get_settings().job_max_attempts and ctx.payload.get("retry_safe", True)
            if retry:  # transient failures: requeue once (handlers are idempotent)
                j.status, j.message = "queued", f"Retrying after an unexpected error: {type(e).__name__}"
                db.commit()
                return
        _finish(job_id, "failed", f"Unexpected error ({type(e).__name__}): {e}"[:800])
        _on_fail(ctx, f"Unexpected error: {e}"[:500])


def _on_fail(ctx: JobContext, message: str) -> None:
    from .models import Clip, Project

    with SessionLocal() as db:
        if ctx.kind == "generate" and ctx.project_id:
            p = db.get(Project, ctx.project_id)
            if p:
                p.status, p.error = "failed", message
        if ctx.kind == "render" and ctx.clip_id:
            c = db.get(Clip, ctx.clip_id)
            if c:
                c.render_status, c.render_error = "failed", message
        db.commit()


def recover_stale() -> None:
    """Jobs left 'running' by a crashed process go back to the queue on startup."""
    with SessionLocal() as db:
        db.execute(update(Job).where(Job.status == "running").values(status="queued", message="Resumed after restart"))
        db.commit()


class Worker:
    def __init__(self, concurrency: int = 1) -> None:
        self.concurrency = concurrency
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        from . import tasks  # noqa: F401  (register handlers)

        recover_stale()
        for i in range(self.concurrency):
            t = threading.Thread(target=self._loop, name=f"hs-worker-{i}", daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        poll = get_settings().worker_poll_seconds
        while not self._stop.is_set():
            try:
                job_id = _claim()
            except Exception:  # noqa: BLE001
                log.exception("claim failed")
                job_id = None
            if job_id:
                run_job(job_id)
            else:
                self._stop.wait(poll)
