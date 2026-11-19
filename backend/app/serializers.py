from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from .models import Clip, Job, Project, User
from .pipeline import virality
from .storage import sign, storage


def iso(d: datetime | None) -> str | None:
    """SQLite drops tzinfo; every stored time is UTC, so say so explicitly."""
    if d is None:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=UTC)
    return d.astimezone(UTC).isoformat().replace("+00:00", "Z")


def media_url(key: str | None, download_name: str | None = None, ttl: int = 6 * 3600) -> str | None:
    if not key or not storage.exists(key):
        return None
    return "/api/media?" + sign(key, ttl, download_name)


def slug(s: str, n: int = 50) -> str:
    return (re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:n] or "clip").rstrip("-")


def user_out(u: User) -> dict[str, Any]:
    return {"id": u.id, "email": u.email, "name": u.name, "brand_kit": u.brand_kit or {}}


def job_out(j: Job | None) -> dict[str, Any] | None:
    if not j:
        return None
    return {
        "id": j.id,
        "kind": j.kind,
        "status": j.status,
        "stage": j.stage,
        "progress": j.progress,
        "message": j.message,
        "error": j.error,
        "stages": j.stages or [],
        "project_id": j.project_id,
        "clip_id": j.clip_id,
        "created_at": iso(j.created_at),
        "started_at": iso(j.started_at),
        "finished_at": iso(j.finished_at),
        "payload": {k: v for k, v in (j.payload or {}).items() if k == "summary"},
    }


def original_time(c: Clip) -> float | None:
    """Where a clip starts in the original video, when only sections of it were downloaded."""
    sections = ((c.project.media if c.project else None) or {}).get("sections") or []
    for s in sections:
        if s["start"] - 0.5 <= c.start < s["end"]:
            return round(s["orig_start"] + max(0.0, c.start - s["start"]), 2)
    return None


def clip_out(c: Clip, project: Project | None = None) -> dict[str, Any]:
    name = f"{slug(c.title)}-{c.id[:6]}"
    rendered = (c.edits or {}).get("_rendered") or {}
    out = {
        "id": c.id,
        "project_id": c.project_id,
        "rank": c.rank,
        "start": c.start,
        "end": c.end,
        "duration": round(c.end - c.start, 2),
        "output_duration": rendered.get("duration"),
        "title": c.title,
        "hook": c.hook,
        "text": c.text,
        "content_type": c.content_type,
        "score": c.score,
        "score_breakdown": c.score_breakdown,
        "reasons": c.reasons,
        "edits": {k: v for k, v in (c.edits or {}).items() if not k.startswith("_")},
        "reframe": c.reframe or {},
        "publish": c.publish or {},
        "render_status": c.render_status,
        "render_error": c.render_error,
        "rendered_at": iso(c.rendered_at),
        "favorite": c.favorite,
        "feedback": c.feedback,
        "created_at": iso(c.created_at),
        "video_url": media_url(c.output_key),
        "download_url": media_url(c.output_key, f"{name}.mp4"),
        "thumb_url": media_url(c.thumb_key),
        "srt_url": media_url(c.srt_key, f"{name}.srt"),
        "project_name": project.name if project else None,
        "post": c.post or {},
        "original_start": original_time(c),
    }
    out["insights"] = virality.insights(out)
    return out


def project_out(p: Project, clips: bool = False, job: Job | None = None) -> dict[str, Any]:
    probe = (p.media or {}).get("probe") or {}
    preview_key = (p.media or {}).get("preview_key") or (p.media or {}).get("source_key")
    out = {
        "id": p.id,
        "name": p.name,
        "source_type": p.source_type,
        "source_url": p.source_url,
        "status": p.status,
        "error": p.error,
        "settings": p.settings,
        "created_at": iso(p.created_at),
        "updated_at": iso(p.updated_at),
        "duration": probe.get("duration"),
        "width": probe.get("width"),
        "height": probe.get("height"),
        "has_audio": probe.get("has_audio"),
        "thumb_url": media_url((p.media or {}).get("thumb_key")),
        "source_video_url": media_url(preview_key) if probe else None,
        "analysis": {k: v for k, v in (p.analysis or {}).items() if k != "signals"}
        if clips
        else {k: (p.analysis or {}).get(k) for k in ("genre", "seconds")},
        "clip_count": len(p.clips),
        "job": job_out(job),
    }
    if clips:
        out["clips"] = [clip_out(c) for c in p.clips]
        out["signals"] = (p.analysis or {}).get("signals")
    return out
