from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..jobs import enqueue
from ..models import Clip, Job, Project, User
from ..pipeline import captions
from ..pipeline.render import default_chunks
from ..schemas import ClipEditIn, FavoriteIn, FeedbackIn, PublishIn, PublishUpdateIn
from ..serializers import clip_out, job_out, project_out
from ..storage import storage
from ..tasks import caption_language, caption_words, load_signals, load_transcript, pkey

router = APIRouter(prefix="/api/clips", tags=["clips"])

ALLOWED_EDIT_KEYS = {
    "aspect",
    "crop",
    "captions",
    "overlays",
    "silence_removal",
    "audio",
    "video",
    "quality",
    "crop_locked",
    "zoom",
    "logo",
    "music",
    "progress_bar",
    "pair",
    "compare",
    "labels",
    "multi",
    "layout",
}


def get_clip(db: Session, cid: str, user: User) -> Clip:
    c = db.get(Clip, cid)
    if not c or c.project.user_id != user.id:
        raise HTTPException(404, "Clip not found.")
    return c


def clip_job(db: Session, cid: str) -> Job | None:
    return db.scalar(select(Job).where(Job.clip_id == cid).order_by(Job.created_at.desc()).limit(1))


@router.get("")
def library(
    favorite: bool = False, rendered: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    q = select(Clip).join(Project).where(Project.user_id == user.id)
    if favorite:
        q = q.where(Clip.favorite.is_(True))
    if rendered:
        q = q.where(Clip.render_status == "rendered")
    clips = db.scalars(q.order_by(Clip.created_at.desc()).limit(500)).all()
    return [clip_out(c, c.project) for c in clips]


@router.get("/{cid}")
def get_one(cid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = get_clip(db, cid, user)
    p = c.project
    lang = caption_language(p, c)
    all_words = caption_words(p, lang)
    lo, hi = max(0.0, c.start - 60), c.end + 60
    words = [[w.w, w.s, w.e] for w in all_words if lo <= w.s <= hi]
    edits = c.edits or {}
    ce = edits.get("captions") or {}
    chunks = ce.get("chunks") or default_chunks(
        all_words, c.start, c.end, ce.get("preset", "bold_creator"), (ce.get("style") or {}).get("max_words")
    )
    env = None
    if storage.exists(pkey(p.id, "signals.npz")):
        sig = load_signals(p.id)
        a, b = int(lo * 10), int(min(hi, sig.duration) * 10)
        env = {"start": lo, "hop": 0.2, "loudness": [round(float(x), 1) for x in sig.loudness[a:b:2]]}
    return {
        "clip": clip_out(c, p),
        "project": project_out(p),
        "words": words,
        "chunks": chunks,
        "envelope": env,
        "job": job_out(clip_job(db, c.id)),
        "caption_language": lang,
        "spoken_language": load_transcript(p.id).language,
        "has_english": storage.exists(pkey(p.id, "rank_words.json")),
    }


@router.get("/{cid}/words")
def clip_words(cid: str, lang: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Transcript words around the clip in another caption language (the editor's language switch)."""
    if lang not in ("english", "hinglish", "original"):
        raise HTTPException(422, "Unknown caption language.")
    c = get_clip(db, cid, user)
    lo, hi = max(0.0, c.start - 60), c.end + 60
    return {"language": lang, "words": [[w.w, w.s, w.e] for w in caption_words(c.project, lang) if lo <= w.s <= hi]}


@router.patch("/{cid}")
def update(cid: str, body: ClipEditIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = get_clip(db, cid, user)
    dur = (c.project.media.get("probe") or {}).get("duration") or 1e9
    start = c.start if body.start is None else body.start
    end = c.end if body.end is None else body.end
    end = min(end, dur)
    if end - start < 1.0:
        raise HTTPException(422, "A clip must be at least 1 second long.")
    if end - start > 180:
        raise HTTPException(422, "Clips can be at most 3 minutes long.")
    if (start, end) != (c.start, c.end):
        c.start, c.end = round(start, 3), round(end, 3)
        ce = dict((c.edits or {}).get("captions") or {})
        if body.edits is None or "captions" not in body.edits:
            ce["chunks"] = None  # timings changed: rebuild captions from the transcript
            c.edits = {**(c.edits or {}), "captions": ce}
    if body.title is not None:
        c.title = body.title.strip()[:250]
    if body.edits:
        new = {k: v for k, v in body.edits.items() if k in ALLOWED_EDIT_KEYS}
        if "captions" in new and isinstance(new["captions"], dict):
            cap = new["captions"]
            if cap.get("preset") and cap["preset"] not in captions.PRESETS:
                raise HTTPException(422, "Unknown caption preset.")
            if cap.get("chunks"):
                cap["chunks"] = [
                    captions.retime_chunk(
                        {
                            "s": float(ch["s"]),
                            "e": float(ch["e"]),
                            "text": str(ch.get("text", ""))[:200],
                            "words": ch.get("words") or [],
                        }
                    )
                    for ch in cap["chunks"][:400]
                    if str(ch.get("text", "")).strip()
                ]
        if "layout" in new:  # gameplay layout: split, cam/game crops, swap
            lay = new["layout"] if isinstance(new["layout"], dict) else {}
            clean: dict = {}
            if lay.get("split") is not None:
                clean["split"] = max(0.2, min(0.7, float(lay["split"])))
            for k in ("cam", "game"):
                if isinstance(lay.get(k), dict):
                    clean[k] = {
                        a: max(0.0, min(1.0, float(lay[k][a]))) for a in ("x", "y", "w") if lay[k].get(a) is not None
                    }
            clean["swap"] = bool(lay.get("swap"))
            new["layout"] = clean
        if isinstance(new.get("captions"), dict) and new["captions"].get("language") not in (
            None,
            "english",
            "hinglish",
            "original",
        ):
            raise HTTPException(422, "Unknown caption language.")
        if "multi" in new:  # comparison clips: only the play mode / sound can change, not the parts
            ask = new["multi"] if isinstance(new["multi"], dict) else {}
            cur = dict((c.edits or {}).get("multi") or {})
            if not cur.get("parts"):
                raise HTTPException(422, "This clip isn't a comparison.")
            if ask.get("play") in ("turns", "together", "grid_then_single"):
                cur["play"] = ask["play"]
            if ask.get("audio") in ("active", "a", "mix"):
                cur["audio"] = ask["audio"]
            new["multi"] = cur
        if "crop" in new and isinstance(new["crop"], dict):
            new["crop_locked"] = True
        from .library import user_asset_key

        for name in ("logo", "music"):
            if isinstance(new.get(name), dict):
                new[name] = {k: v for k, v in new[name].items() if k != "path"}
                new[name]["key"] = user_asset_key(user, new[name].get("key"))
        c.edits = {**(c.edits or {}), **new}
    job = None
    if body.render:
        if c.render_status == "rendering":
            raise HTTPException(409, "This clip is already rendering.")
        c.render_status = "pending"
        job = enqueue(db, user_id=user.id, kind="render", project_id=c.project_id, clip_id=c.id)
    db.commit()
    return {"clip": clip_out(c), "job": job_out(job)}


@router.post("/{cid}/render")
def rerender(cid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return update(cid, ClipEditIn(render=True), user, db)


@router.post("/{cid}/publish")
def regen_publish(cid: str, body: PublishIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = get_clip(db, cid, user)
    job = enqueue(
        db,
        user_id=user.id,
        kind="publish",
        project_id=c.project_id,
        clip_id=c.id,
        payload={"platforms": body.platforms, "tone": body.tone},
    )
    return {"job": job_out(job)}


@router.put("/{cid}/publish")
def save_publish(cid: str, body: PublishUpdateIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = get_clip(db, cid, user)
    pub = dict(c.publish or {})
    pub["platforms"] = {**pub.get("platforms", {}), **(body.publish.get("platforms") or {})}
    pub["edited"] = True
    c.publish = pub
    db.commit()
    return clip_out(c)


@router.post("/{cid}/feedback")
def feedback(cid: str, body: FeedbackIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = get_clip(db, cid, user)
    c.feedback, c.feedback_note = body.rating, body.note
    db.commit()
    return clip_out(c)


@router.post("/{cid}/favorite")
def favorite(cid: str, body: FavoriteIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = get_clip(db, cid, user)
    c.favorite = body.favorite
    db.commit()
    return clip_out(c)


@router.delete("/{cid}")
def delete(cid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = get_clip(db, cid, user)
    db.delete(c)
    db.commit()
    storage.delete_prefix(f"clips/{cid}")
    return {"ok": True}
