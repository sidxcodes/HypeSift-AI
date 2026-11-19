"""Brand assets (logo, music), storage usage and the post / schedule plan for clips."""

from __future__ import annotations

import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..models import Clip, Project, User
from ..schemas import PostIn
from ..serializers import clip_out, media_url
from ..storage import storage
from .clips import get_clip

router = APIRouter(prefix="/api", tags=["library"])

ASSET_TYPES = {
    "logo": ({".png", ".jpg", ".jpeg", ".webp"}, 8 * 2**20),
    "music": ({".mp3", ".m4a", ".aac", ".wav", ".ogg", ".flac"}, 40 * 2**20),
}


def user_asset_key(user: User, key: str | None) -> str | None:
    """Only accept asset keys that belong to this user (settings arrive from the browser)."""
    if not key:
        return None
    if not key.startswith(f"users/{user.id}/assets/") or ".." in key or not storage.exists(key):
        raise HTTPException(422, "That logo or music file was not found. Upload it again.")
    return key


@router.post("/assets")
async def upload_asset(kind: str, name: str, request: Request, user: User = Depends(current_user)):
    if kind not in ASSET_TYPES:
        raise HTTPException(422, "Unknown asset type.")
    exts, limit = ASSET_TYPES[kind]
    ext = Path(name).suffix.lower()
    if ext not in exts:
        raise HTTPException(422, f"Supported {kind} files: {', '.join(sorted(e.lstrip('.') for e in exts))}.")
    key = f"users/{user.id}/assets/{kind}-{uuid.uuid4().hex[:10]}{ext}"
    path = storage.path(key)
    size = 0
    with open(path, "wb") as f:
        async for chunk in request.stream():
            size += len(chunk)
            if size > limit:
                f.close()
                path.unlink(missing_ok=True)
                raise HTTPException(413, f"That file is larger than {limit // 2**20} MB.")
            f.write(chunk)
    if size == 0:
        path.unlink(missing_ok=True)
        raise HTTPException(422, "The file is empty.")
    if kind == "music":
        from ..pipeline import ffmpeg

        try:
            pr = ffmpeg.probe(path)
            if not pr.has_audio:
                raise ffmpeg.MediaError("no audio")
        except ffmpeg.MediaError as e:
            path.unlink(missing_ok=True)
            raise HTTPException(422, "That file has no readable audio.") from e
    return {"key": key, "name": Path(name).name[:120], "kind": kind, "size": size, "url": media_url(key)}


@router.get("/storage")
def storage_usage(user: User = Depends(current_user), db: Session = Depends(get_db)):
    def du(key: str) -> int:
        p = storage.path(key)
        if p.is_file():
            return p.stat().st_size
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.is_dir() else 0

    projects = []
    for p in db.scalars(select(Project).where(Project.user_id == user.id).order_by(Project.created_at.desc())):
        src = du(f"projects/{p.id}")
        clips = sum(du(f"clips/{c.id}") for c in p.clips)
        projects.append(
            {
                "id": p.id,
                "name": p.name,
                "clips": len(p.clips),
                "source_bytes": src,
                "clip_bytes": clips,
                "total": src + clips,
                "thumb_url": media_url((p.media or {}).get("thumb_key")),
            }
        )
    assets = du(f"users/{user.id}/assets")
    disk = shutil.disk_usage(storage.root)
    return {
        "projects": projects,
        "assets_bytes": assets,
        "total": sum(x["total"] for x in projects) + assets,
        "disk_free": disk.free,
        "disk_total": disk.total,
    }


@router.put("/clips/{cid}/post")
def set_post(cid: str, body: PostIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = get_clip(db, cid, user)
    plan = dict(c.post or {})
    when = None
    if body.status == "scheduled":
        if not body.scheduled_at:
            raise HTTPException(422, "Pick a date and time.")
        try:
            when = datetime.fromisoformat(body.scheduled_at.replace("Z", "+00:00"))
        except ValueError as e:
            raise HTTPException(422, "That date and time isn't valid.") from e
        if when.tzinfo is None:
            raise HTTPException(422, "The time needs a time zone.")
        when = when.astimezone(UTC)
    plan.update(
        {
            "status": body.status,
            "scheduled_at": when.isoformat().replace("+00:00", "Z") if when else None,
            "timezone": body.timezone or plan.get("timezone"),
            "platforms": {k: v for k, v in body.platforms.items() if isinstance(v, dict)} or plan.get("platforms", {}),
            "updated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }
    )
    if body.status == "posted":
        plan["posted_at"] = plan.get("posted_at") or datetime.now(UTC).isoformat().replace("+00:00", "Z")
    else:
        plan.pop("posted_at", None)
    c.post = plan
    db.commit()
    return clip_out(c, c.project)


@router.get("/posts")
def posts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Every clip with a schedule or marked posted, for the calendar."""
    rows = db.scalars(select(Clip).join(Project).where(Project.user_id == user.id)).all()
    return [clip_out(c, c.project) for c in rows if (c.post or {}).get("status") in ("scheduled", "posted")]
