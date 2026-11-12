"""Resumable chunked uploads: init → PUT chunks at ?offset= → complete.

A client that loses its connection asks ``GET /api/uploads/{id}`` for ``received``
and continues from there. ``complete`` probes the file with ffprobe, so a renamed
non-video is rejected before any processing is queued.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from ..auth import current_user
from ..config import get_settings
from ..db import get_db
from ..models import Upload, User
from ..pipeline import ffmpeg
from ..schemas import UploadInitIn
from ..storage import storage

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


def upload_key(u: Upload) -> str:
    ext = "." + u.filename.rsplit(".", 1)[-1].lower()
    return f"uploads/{u.id}/data{ext}"


def _get(db: Session, upload_id: str, user: User) -> Upload:
    u = db.get(Upload, upload_id)
    if not u or u.user_id != user.id:
        raise HTTPException(404, "Upload not found.")
    return u


def _out(u: Upload) -> dict:
    s = get_settings()
    return {
        "id": u.id,
        "filename": u.filename,
        "size": u.size,
        "received": u.received,
        "status": u.status,
        "chunk_size": s.upload_chunk_mb * 2**20,
    }


@router.post("")
def init(body: UploadInitIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = get_settings()
    if body.size > s.max_upload_mb * 2**20:
        raise HTTPException(413, f"Files up to {s.max_upload_mb // 1024} GB are supported.")
    u = Upload(user_id=user.id, filename=body.filename, size=body.size)
    db.add(u)
    db.commit()
    storage.path(upload_key(u)).write_bytes(b"")
    return _out(u)


@router.get("/{upload_id}")
def status(upload_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _out(_get(db, upload_id, user))


@router.put("/{upload_id}")
async def chunk(
    upload_id: str,
    request: Request,
    offset: int = Query(ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    u = _get(db, upload_id, user)
    if u.status != "uploading":
        raise HTTPException(409, "Upload already completed.")
    if offset != u.received:
        raise HTTPException(409, f"Expected offset {u.received}.")
    limit = get_settings().upload_chunk_mb * 2**20 + 1024
    path = storage.path(upload_key(u))
    written = 0
    with open(path, "r+b") as f:
        f.seek(offset)
        async for part in request.stream():
            written += len(part)
            if written > limit or offset + written > u.size:
                f.truncate(offset)
                raise HTTPException(413, "Chunk too large.")
            f.write(part)
        f.truncate(offset + written)
    u.received = offset + written
    db.commit()
    return _out(u)


@router.post("/{upload_id}/complete")
def complete(upload_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    u = _get(db, upload_id, user)
    if u.received != u.size:
        raise HTTPException(409, f"Upload incomplete ({u.received} of {u.size} bytes).")
    try:
        probe = ffmpeg.probe(storage.path(upload_key(u)))
    except ffmpeg.MediaError as e:
        storage.delete_prefix(f"uploads/{u.id}")
        db.delete(u)
        db.commit()
        raise HTTPException(422, str(e)) from e
    s = get_settings()
    if probe.duration > s.max_duration_minutes * 60:
        raise HTTPException(422, f"Videos up to {s.max_duration_minutes} minutes are supported.")
    u.status = "complete"
    db.commit()
    return {**_out(u), "probe": probe.as_dict()}
