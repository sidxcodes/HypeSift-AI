from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..config import get_settings
from ..db import get_db
from ..jobs import active_jobs, enqueue
from ..models import Job, Project, Upload, User
from ..pipeline import ingest
from ..pipeline.ffmpeg import MediaError
from ..schemas import GenerateSettings, ProjectCreateIn, UrlCheckIn
from ..serializers import project_out
from ..storage import storage
from ..tasks import load_transcript
from .uploads import upload_key

router = APIRouter(prefix="/api", tags=["projects"])


def get_project(db: Session, pid: str, user: User) -> Project:
    p = db.get(Project, pid)
    if not p or p.user_id != user.id:
        raise HTTPException(404, "Project not found.")
    return p


def latest_job(db: Session, pid: str, kinds: tuple[str, ...] = ("generate", "discover")) -> Job | None:
    return db.scalar(
        select(Job).where(Job.project_id == pid, Job.kind.in_(kinds)).order_by(Job.created_at.desc()).limit(1)
    )


def _check_assets(settings: GenerateSettings, user: User) -> None:
    from .library import user_asset_key

    settings.logo_key = user_asset_key(user, settings.logo_key)
    settings.music_key = user_asset_key(user, settings.music_key)


def _quota(db: Session, user: User) -> None:
    if active_jobs(db, user.id) >= get_settings().max_active_jobs_per_user:
        raise HTTPException(429, "You already have several jobs running. Wait for one to finish.")


@router.post("/url/check")
def check_url(body: UrlCheckIn, user: User = Depends(current_user)):
    try:
        return ingest.inspect_url(body.url).__dict__
    except MediaError as e:
        raise HTTPException(422, str(e)) from e


@router.post("/projects")
def create(body: ProjectCreateIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.settings.count > get_settings().max_clips:
        raise HTTPException(422, f"Up to {get_settings().max_clips} clips per run.")
    _check_assets(body.settings, user)
    if body.start:
        _quota(db, user)
    if body.upload_id:
        up = db.get(Upload, body.upload_id)
        if not up or up.user_id != user.id or up.status != "complete":
            raise HTTPException(422, "Finish uploading the file first.")
        p = Project(
            user_id=user.id,
            name=(body.name or Path(up.filename).stem)[:200],
            source_type="upload",
            source_filename=up.filename,
            settings=body.settings.model_dump(),
            status="draft",
        )
        db.add(p)
        db.flush()
        ext = Path(up.filename).suffix.lower()
        key = f"projects/{p.id}/source{ext}"
        shutil.move(str(storage.path(upload_key(up))), storage.path(key))
        storage.delete_prefix(f"uploads/{up.id}")
        db.delete(up)
        p.media = {"source_key": key}
    else:
        try:
            info = ingest.inspect_url(body.url or "")
        except MediaError as e:
            raise HTTPException(422, str(e)) from e
        if not info.importable:
            raise HTTPException(422, info.message)
        if not info.scan and info.size_bytes and info.size_bytes > get_settings().max_upload_mb * 2**20:
            raise HTTPException(413, "That file is larger than the upload limit.")
        p = Project(
            user_id=user.id,
            name=(body.name or info.title or "Imported video")[:200],
            source_type="url",
            source_url=info.url,
            settings=body.settings.model_dump(),
            status="draft",
            media={"scan": True, "source_duration": info.duration} if info.scan else {},
        )
        db.add(p)
    db.commit()
    job = None
    if body.start:
        p.status = "queued"
        job = enqueue(db, user_id=user.id, kind="generate", project_id=p.id)
        db.commit()
    return project_out(p, job=job)


@router.get("/projects")
def list_projects(user: User = Depends(current_user), db: Session = Depends(get_db)):
    ps = db.scalars(select(Project).where(Project.user_id == user.id).order_by(Project.created_at.desc())).all()
    return [project_out(p, job=latest_job(db, p.id)) for p in ps]


@router.get("/projects/{pid}")
def get_one(pid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = get_project(db, pid, user)
    return project_out(p, clips=True, job=latest_job(db, p.id))


@router.patch("/projects/{pid}")
def rename(pid: str, body: dict, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = get_project(db, pid, user)
    if "name" in body and str(body["name"]).strip():
        p.name = str(body["name"]).strip()[:200]
    db.commit()
    return project_out(p)


@router.post("/projects/{pid}/generate")
def regenerate(pid: str, settings: GenerateSettings, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = get_project(db, pid, user)
    j = latest_job(db, p.id)
    if j and j.status in ("queued", "running"):
        raise HTTPException(409, "This project is already processing.")
    _quota(db, user)
    _check_assets(settings, user)
    p.settings = settings.model_dump()
    p.status, p.error = "queued", None
    job = enqueue(db, user_id=user.id, kind="generate", project_id=p.id)
    db.commit()
    return project_out(p, job=job)


@router.delete("/projects/{pid}")
def delete(pid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = get_project(db, pid, user)
    for j in db.scalars(select(Job).where(Job.project_id == p.id, Job.status.in_(("queued", "running")))):
        j.cancel_requested = True
    clip_ids = [c.id for c in p.clips]
    db.delete(p)
    db.commit()
    storage.delete_prefix(f"projects/{pid}")
    for cid in clip_ids:
        storage.delete_prefix(f"clips/{cid}")
    return {"ok": True}


@router.get("/projects/{pid}/transcript")
def transcript(pid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    get_project(db, pid, user)
    tr = load_transcript(pid)
    return {"language": tr.language, "engine": tr.engine, "segments": tr.segments}
