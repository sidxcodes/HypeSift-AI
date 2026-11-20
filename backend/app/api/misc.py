from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..config import get_settings
from ..db import get_db
from ..jobs import enqueue
from ..models import Clip, Job, User
from ..pipeline import assistant, captions, ffmpeg, gemini, llm, publish
from ..pipeline.genres import DIMENSIONS, GENRE_LABELS
from ..schemas import AssistantIn
from ..serializers import job_out
from ..storage import storage, verify
from .projects import get_project

router = APIRouter(prefix="/api", tags=["misc"])


@router.get("/health")
def health():
    try:
        ff = bool(ffmpeg.ffmpeg_bin())
    except ffmpeg.MediaError:
        ff = False
    return {"ok": True, "ffmpeg": ff, "llm": llm.status()}


@router.get("/meta")
def meta():
    s = get_settings()
    try:
        enc = ffmpeg.video_encoder()
    except ffmpeg.MediaError:
        enc = "unavailable"
    return {
        "caption_presets": captions.PRESETS,
        "caption_transitions": captions.TRANSITIONS,
        "caption_effects": captions.EFFECTS,
        "fonts": captions.FONT_FILES,
        "dimensions": DIMENSIONS,
        "genres": GENRE_LABELS,
        "moods": ["any", "funny", "emotional", "intense", "informative", "inspiring"],
        "platforms": publish.PLATFORMS,
        "tones": publish.TONES,
        "aspects": ["9:16", "1:1", "4:5", "16:9"],
        "llm": llm.status(),
        "ai_provider": gemini.provider(),
        "encoder": enc,
        "whisper_model": s.whisper_model,
        "limits": {
            "max_upload_mb": s.max_upload_mb,
            "max_duration_minutes": s.max_duration_minutes,
            "max_clips": s.max_clips,
        },
    }


class AiSettingsIn(BaseModel):
    provider: Literal["gemini", "local"] | None = None
    gemini_api_key: str | None = Field(default=None, max_length=200)
    gemini_model: str | None = Field(default=None, max_length=60)


@router.get("/ai")
def ai_settings(user: User = Depends(current_user)):
    return {**gemini.public_settings(), "local": llm.status()}


@router.put("/ai")
def save_ai_settings(body: AiSettingsIn, user: User = Depends(current_user)):
    key = (body.gemini_api_key or "").strip() or None
    if key is not None:
        ok, msg = gemini.test_key(key)
        if not ok:
            raise HTTPException(400, msg)
    if body.gemini_model is not None and body.gemini_model not in ("auto", *gemini.MODELS):
        raise HTTPException(400, "Unknown model.")
    gemini.save_settings(provider=body.provider, gemini_api_key=key, gemini_model=body.gemini_model)
    return {**gemini.public_settings(), "local": llm.status()}


@router.delete("/ai/key")
def delete_ai_key(user: User = Depends(current_user)):
    s = gemini.load_settings()
    s.pop("gemini_api_key", None)
    gemini.SETTINGS_FILE.write_text(__import__("json").dumps(s), encoding="utf-8")
    return {**gemini.public_settings(), "local": llm.status()}


@router.get("/jobs")
def jobs(
    project_id: str | None = None,
    active: bool = False,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    q = select(Job).where(Job.user_id == user.id)
    if project_id:
        q = q.where(Job.project_id == project_id)
    if active:
        q = q.where(Job.status.in_(("queued", "running")))
    return [job_out(j) for j in db.scalars(q.order_by(Job.created_at.desc()).limit(100))]


@router.get("/jobs/{jid}")
def job(jid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    j = db.get(Job, jid)
    if not j or j.user_id != user.id:
        raise HTTPException(404, "Job not found.")
    return job_out(j)


@router.post("/jobs/{jid}/cancel")
def cancel(jid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    j = db.get(Job, jid)
    if not j or j.user_id != user.id:
        raise HTTPException(404, "Job not found.")
    if j.status == "queued":
        j.status, j.error = "cancelled", "Cancelled by user."
        if j.kind == "generate" and j.project_id:
            from ..models import Project

            p = db.get(Project, j.project_id)
            if p:
                p.status, p.error = "failed", "Cancelled."
    elif j.status == "running":
        j.cancel_requested = True
    db.commit()
    return job_out(j)


@router.get("/media")
def media(key: str, exp: int, sig: str, dl: str | None = Query(default=None)):
    """Serve stored files via signed, expiring links (supports HTTP Range for seeking)."""
    if not verify(key, exp, sig):
        raise HTTPException(403, "This link has expired. Reload the page.")
    try:
        path = storage.path(key)
    except ValueError as e:
        raise HTTPException(400, "Bad key") from e
    if not path.exists():
        raise HTTPException(404, "File not found.")
    headers = {"Cache-Control": "private, max-age=3600"}
    if dl:
        return FileResponse(path, filename=dl, headers=headers)
    return FileResponse(path, headers=headers)


@router.post("/assistant")
def assistant_cmd(body: AssistantIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = get_project(db, body.project_id, user)
    action = assistant.parse(body.text, has_clip=bool(body.clip_id))
    out = {
        "action": action,
        "executed": False,
        "message": action.get("summary") or action.get("message", ""),
        "jobs": [],
    }
    if action["type"] == "unsupported" or not body.execute:
        return out
    if p.status not in ("ready",) and action["type"] != "unsupported":
        out["message"] = "Run AI Generate first — the assistant edits clips from a finished analysis."
        return out

    clips: list[Clip]
    if body.clip_id:
        c = db.get(Clip, body.clip_id)
        if not c or c.project_id != p.id:
            raise HTTPException(404, "Clip not found.")
        clips = [c]
    else:
        clips = list(p.clips)

    t = action["type"]
    if t == "find_clips":
        payload = {k: action.get(k) for k in ("count", "min_dur", "max_dur", "mood", "genre", "position", "query")}
        payload["summary"] = action.get("summary")
        payload["count"] = max(1, min(int(payload.get("count") or 3), get_settings().max_clips))
        j = enqueue(db, user_id=user.id, kind="discover", project_id=p.id, payload=payload)
        out["jobs"].append(job_out(j))
        out["message"] = f"{action['summary']} — searching the analysed video, new clips will appear when rendered."
    elif t in ("set_captions", "set_aspect", "set_silence_removal"):
        for c in clips:
            e = dict(c.edits or {})
            if t == "set_captions":
                ce = dict(e.get("captions") or {})
                ce["enabled"] = bool(action.get("enabled", True))
                if action.get("preset") in captions.PRESETS:
                    ce["preset"] = action["preset"]
                    ce["chunks"] = None
                style = {
                    **(ce.get("style") or {}),
                    **{
                        k: v
                        for k, v in (action.get("style") or {}).items()
                        if k in captions.PRESETS["bold_creator"] or k == "size_scale"
                    },
                }
                ce["style"] = style
                e["captions"] = ce
            elif t == "set_aspect":
                e["aspect"] = action["aspect"]
            else:
                e["silence_removal"] = bool(action.get("enabled", True))
            c.edits = e
            c.render_status = "pending"
            out["jobs"].append(job_out(enqueue(db, user_id=user.id, kind="render", project_id=p.id, clip_id=c.id)))
        scope = "this clip" if body.clip_id else f"all {len(clips)} clips"
        out["message"] = f"{action['summary']} on {scope} — re-rendering now."
    elif t == "generate_publish":
        target = clips[:1] if body.clip_id else sorted(clips, key=lambda c: -c.score)[:1]
        if not target:
            out["message"] = "There are no clips yet."
            return out
        j = enqueue(
            db,
            user_id=user.id,
            kind="publish",
            project_id=p.id,
            clip_id=target[0].id,
            payload={"platforms": action.get("platforms"), "tone": action.get("tone", "compelling")},
        )
        out["jobs"].append(job_out(j))
        who = "this clip" if body.clip_id else f"your top clip (“{target[0].title}”)"
        out["message"] = f"{action['summary']} for {who}."
    db.commit()
    out["executed"] = True
    return out
