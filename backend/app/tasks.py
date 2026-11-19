"""Job handlers: the AI Generate pipeline, re-ranking, re-rendering, publishing copy."""

from __future__ import annotations

import contextlib
import json
import logging
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from .config import get_settings
from .db import SessionLocal
from .jobs import JobContext, UserFacingError, handler
from .models import Clip, Project, User
from .pipeline import (
    compare,
    ffmpeg,
    highlights,
    ingest,
    llm,
    longscan,
    publish,
    reframe,
    render,
    signals,
    sites,
    transcribe,
)
from .pipeline.highlights import Prefs
from .pipeline.transcribe import Transcript
from .storage import storage

log = logging.getLogger("hypesift.tasks")


# ----------------------------------------------------------------------------- helpers


def pkey(pid: str, name: str) -> str:
    return f"projects/{pid}/{name}"


def ckey(cid: str, name: str) -> str:
    return f"clips/{cid}/{name}"


def source_path(p: Project) -> Path:
    return storage.path(p.media["source_key"])


def load_rank_words(pid: str) -> list:
    """Words used to choose moments and write titles: an English version of non-English speech
    when one exists, otherwise the caption transcript."""
    path = storage.path(pkey(pid, "rank_words.json"))
    if path.exists():
        return [transcribe.Word(w, s, e, 0.8) for w, s, e in json.loads(path.read_text(encoding="utf-8"))]
    return load_transcript(pid).words


def _scan_caption_words(pid: str) -> tuple[str, list] | None:
    path = storage.path(pkey(pid, "scan_words.json"))
    if not path.exists():
        return None
    d = json.loads(path.read_text(encoding="utf-8"))
    words = [transcribe.Word(w, s, e, 0.8) for w, s, e in d.get("words", [])]
    return (str(d.get("language", "")), words) if len(words) >= 20 else None


def load_transcript(pid: str) -> Transcript:
    path = storage.path(pkey(pid, "transcript.json"))
    if not path.exists():
        return Transcript(language="en")
    return Transcript.from_json(json.loads(path.read_text(encoding="utf-8")))


def save_signals(pid: str, s: signals.Signals) -> None:
    np.savez_compressed(
        storage.path(pkey(pid, "signals.npz")),
        loudness=s.loudness,
        flux=s.flux,
        flatness=s.flatness,
        motion=s.motion,
        cuts=np.array(s.cuts, dtype=np.float32),
        duration=np.array([s.duration]),
    )


def load_signals(pid: str) -> signals.Signals:
    d = np.load(storage.path(pkey(pid, "signals.npz")))
    return signals.Signals(
        duration=float(d["duration"][0]),
        loudness=d["loudness"],
        flux=d["flux"],
        flatness=d["flatness"],
        motion=d["motion"],
        cuts=[float(x) for x in d["cuts"]],
    )


def feedback_bias(db, user_id: str) -> dict[str, float]:
    """Learn small per-creator weight nudges from 👍/👎 ratings (explicit feedback only)."""
    rated = db.query(Clip).join(Project).filter(Project.user_id == user_id, Clip.feedback != 0).limit(500).all()
    if len(rated) < 3:
        return {}
    acc: dict[str, float] = {}
    for c in rated:
        for k, v in (c.score_breakdown.get("dims") or {}).items():
            if k in highlights.DIMENSIONS:
                acc[k] = acc.get(k, 0.0) + c.feedback * (v - 50) / 50
    return {k: max(-0.3, min(0.3, v / len(rated) * 0.6)) for k, v in acc.items()}


def prefs_from(settings: dict, overrides: dict | None = None) -> Prefs:
    s = {**settings, **(overrides or {})}
    pad = s.get("context_padding", True)
    return Prefs(
        count=int(s.get("count", 6)),
        min_dur=float(s.get("min_dur", 20)),
        max_dur=float(s.get("max_dur", 60)),
        genre=s.get("genre") or "auto",
        mood=s.get("mood", "any"),
        position=s.get("position", "any"),
        query=list(s.get("query") or []) + highlights.instruction_terms(s.get("instructions") or ""),
        instructions=(s.get("instructions") or "").strip(),
        pad_before=0.25 if pad else 0.0,
        pad_after=0.45 if pad else 0.05,
    )


def clip_keywords(c: highlights.Candidate, ctx: highlights.Context, k: int = 6) -> list[str]:
    toks = set(highlights.content_tokens(c.text))
    thr = ctx.idf_mean + 0.4 * ctx.idf_std
    ranked = sorted((t for t in toks if ctx.idf.get(t, 0) >= thr), key=lambda t: -ctx.idf.get(t, 0))
    return ranked[:k]


def default_edits(settings: dict, brand: dict, title: str, keywords: list[str]) -> dict:
    style = dict(brand.get("caption_style") or {})
    style["emphasis"] = bool(settings.get("keyword_emphasis", True))
    overlays = []
    if settings.get("hook_title", True) and title:
        overlays.append({"kind": "title", "text": title, "start": 0, "end": 3.2})
    if brand.get("watermark"):
        overlays.append({"kind": "watermark", "text": brand["watermark"], "start": 0})
    return {
        "aspect": settings.get("aspect", "9:16"),
        "crop": {"mode": settings.get("crop_mode", "auto"), "x": 0.5, "y": 0.5, "zoom": 1.0},
        "captions": {
            "enabled": bool(settings.get("captions", True)),
            "preset": brand.get("caption_preset") or settings.get("caption_preset", "bold_creator"),
            "style": style,
            "chunks": None,
            "keywords": keywords,
            "transition": settings.get("caption_transition", "none"),
            "effect": settings.get("caption_effect", "none"),
        },
        "overlays": overlays,
        "silence_removal": bool(settings.get("silence_removal", False)),
        "quality": settings.get("quality", "standard"),
        "zoom": {
            "start": bool(settings.get("zoom_start")),
            "key_phrases": bool(settings.get("zoom_key_phrases", True)),
        },
        "logo": {"key": settings.get("logo_key"), "position": settings.get("logo_position", "top_right")},
        "music": {"key": settings.get("music_key"), "volume": float(settings.get("music_volume", 0.16))},
        "progress_bar": {"enabled": bool(settings.get("progress_bar")), "color": "#C6F432"},
    }


def _with_asset_paths(edits: dict) -> dict:
    """Resolve stored logo/music keys to files for the renderer (paths are never saved)."""
    out = dict(edits)
    for name in ("logo", "music"):
        a = dict(out.get(name) or {})
        if a.get("key") and storage.exists(a["key"]):
            a["path"] = str(storage.path(a["key"]))
        out[name] = a
    return out


def render_clip(ctx: JobContext | None, clip: Clip, project: Project, words, on_progress=None) -> None:
    """Analyse framing if needed, render the MP4, cover and SRT for one clip (idempotent)."""
    src = source_path(project)
    probe = ffmpeg.Probe(**project.media["probe"])
    edits = render.merged_edits(clip.edits)
    rf = clip.reframe or {}
    if edits["crop"]["mode"] in ("auto", "split", "facecam") and (rf.get("range") != [clip.start, clip.end]):
        rf = reframe.analyze(src, clip.start, clip.end)
        rf["range"] = [clip.start, clip.end]
        # The webcam overlay sits in the same place for the whole stream: the video-wide detection
        # also covers clips where the streamer briefly looks away.
        rf["facecam"] = rf.get("facecam") or (project.media or {}).get("facecam")
        clip.reframe = rf
        unlocked = edits["crop"]["mode"] == "auto" and not (clip.edits or {}).get("crop_locked")
        if unlocked and rf.get("facecam") and edits["aspect"] in ("9:16", "4:5"):
            # A streamer's webcam over gameplay or a screen share: keep both, cam on top.
            edits["crop"]["mode"] = "facecam"
            clip.edits = {**(clip.edits or {}), "crop": {**edits["crop"]}}
        elif unlocked and rf.get("split") and edits["aspect"] == "9:16" and project.analysis.get("genre") == "podcast":
            edits["crop"]["mode"] = "split"
            clip.edits = {**(clip.edits or {}), "crop": {**edits["crop"]}}
    if edits["crop"]["mode"] == "facecam" and not rf.get("facecam"):
        edits["crop"]["mode"] = "auto"  # asked for, but no webcam found in this clip
    version = int(time.time())
    out_key = ckey(clip.id, f"clip-{version}.mp4")
    work = storage.path(f"work/{clip.id}-{version}")
    kw = set((edits.get("captions") or {}).get("keywords") or [])
    try:
        info = render.render(
            src,
            probe,
            clip.start,
            clip.end,
            _with_asset_paths(edits),
            rf,
            words,
            storage.path(out_key),
            work,
            kw,
            on_progress=on_progress,
            should_cancel=ctx.cancelled if ctx else None,
        )
        cover_t = render.cover_time(storage.path(out_key), 0, info["duration"])
        thumb_key = ckey(clip.id, f"cover-{version}.jpg")
        ffmpeg.thumbnail(storage.path(out_key), cover_t, storage.path(thumb_key), width=540)
        srt_key = ckey(clip.id, f"captions-{version}.srt")
        storage.path(srt_key).write_text(info["srt"], encoding="utf-8", newline="\n")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    for old in (clip.output_key, clip.thumb_key, clip.srt_key):
        if old and old not in (out_key,):
            with contextlib.suppress(OSError):  # an old file still open in a player isn't fatal
                storage.path(old).unlink(missing_ok=True)
    clip.output_key, clip.thumb_key, clip.srt_key = out_key, thumb_key, srt_key
    clip.render_status, clip.render_error = "rendered", None
    clip.rendered_at = datetime.now(UTC)
    clip.edits = {
        **(clip.edits or {}),
        "_rendered": {
            "duration": info["duration"],
            "width": info["width"],
            "height": info["height"],
            "segments": info["segments"],
        },
    }


def _clip_from_candidate(
    project: Project, c: highlights.Candidate, ctx: highlights.Context, rank: int, brand: dict
) -> Clip:
    kws = clip_keywords(c, ctx)
    return Clip(
        project_id=project.id,
        rank=rank,
        start=round(c.start, 3),
        end=round(c.end, 3),
        title=c.title[:250],
        hook=c.hook,
        text=c.text,
        content_type=ctx.genre,
        score=c.score,
        score_breakdown={
            "dims": c.dims,
            "weights": {k: round(v, 3) for k, v in ctx.weights.items()},
            "heuristic": c.heuristic,
            "semantic": c.semantic,
            "evidence": c.evidence,
            "engine": "signals + local LLM" if c.semantic is not None else "signals",
        },
        reasons=c.reasons,
        edits=default_edits(project.settings, brand, c.title, kws),
        render_status="pending",
    )


def _comparison_clip(project: Project, x: dict, rank: int, brand: dict, src: Path, words) -> Clip:
    """A stacked "A vs B" clip from compare.candidates()."""
    top, bottom = x["top"], x["bottom"]
    scene = compare.describe(src, (x["start"] + x["end"]) / 2)
    title = f"{top} vs {bottom}" + (f": {scene}" if scene else "")
    text = " ".join(w.w for w in words if x["start"] <= w.s < x["end"])
    settings = dict(project.settings)
    edits = default_edits({**settings, "hook_title": False}, brand, title, [])
    edits["crop"] = {**edits["crop"], "mode": x["mode"]}
    edits["silence_removal"] = False
    edits["labels"] = {"top": top, "bottom": bottom, "enabled": True}
    if x["mode"] == "pair":
        edits["pair"] = {"b_start": x["b_start"]}
    else:
        edits["compare"] = {"swap": bool(x.get("swap"))}
    kind = "split screen" if x["mode"] == "compare" else "matching shots"
    dims = {
        "hook": 70.0,
        "context": 75.0,
        "pacing": 60.0,
        "novelty": 80.0,
        "emotion": 55.0,
        "visual": 70.0,
        "relevance": 85.0,
    }
    return Clip(
        project_id=project.id,
        rank=rank,
        start=round(x["start"], 3),
        end=round(x["end"], 3),
        title=title[:250],
        hook=title,
        text=text or title,
        content_type="comparison",
        score=int(x["score"]),
        score_breakdown={"dims": dims, "engine": "comparison layout", "evidence": {}},
        reasons=[
            f"{top} and {bottom} side by side ({kind}), playing at the same time",
            "Comparisons invite comments: viewers pick a side",
        ],
        edits=edits,
        render_status="pending",
    )


def _render_and_publish(ctx: JobContext, project_id: str, clip_ids: list[str], words, settings: dict) -> None:
    ctx.stage("render", f"Rendering {len(clip_ids)} clips")
    for i, cid in enumerate(clip_ids):
        ctx.check_cancel()
        with SessionLocal() as db:
            clip = db.get(Clip, cid)
            project = db.get(Project, project_id)
            clip.render_status = "rendering"
            db.commit()
            try:
                render_clip(
                    ctx,
                    clip,
                    project,
                    words,
                    on_progress=lambda f, i=i: ctx.progress(
                        (i + f) / len(clip_ids), f"Rendering clip {i + 1} of {len(clip_ids)}"
                    ),
                )
            except ffmpeg.Cancelled:
                clip.render_status = "pending"
                db.commit()
                raise
            except Exception as e:  # noqa: BLE001 - one bad clip shouldn't sink the batch
                log.exception("render failed for %s", cid)
                clip.render_status, clip.render_error = "failed", str(e)[:600]
            db.commit()
    ctx.stage("publish", "Writing titles, descriptions and hashtags")
    for i, cid in enumerate(clip_ids):
        ctx.check_cancel()
        with SessionLocal() as db:
            clip = db.get(Clip, cid)
            clip.publish = publish.generate(
                clip.title,
                clip.hook,
                clip.text,
                clip.content_type,
                settings.get("platforms"),
                settings.get("tone", "compelling"),
                allow_llm=settings.get("use_llm", True),
            )
            db.commit()
        ctx.progress((i + 1) / len(clip_ids), f"Publishing copy {i + 1} of {len(clip_ids)}")


# ----------------------------------------------------------------------------- handlers


@handler("generate")
def generate(ctx: JobContext) -> None:
    st = get_settings()
    t0 = time.time()
    with SessionLocal() as db:
        p = db.get(Project, ctx.project_id)
        if not p:
            raise UserFacingError("Project not found.")
        p.status, p.error = "processing", None
        db.commit()
        settings, source_type, url = dict(p.settings), p.source_type, p.source_url
        brand = dict(db.get(User, p.user_id).brand_kit or {})
    use_llm = settings.get("use_llm", True) and llm.status()["available"]
    scan = source_type == "url" and bool((p.media or {}).get("scan"))
    ctx.plan(
        {
            **({"scan": 14} if scan else {}),
            "ingest": 14 if source_type == "url" else 2,
            "prepare": 6,
            "transcribe": 30,
            "analyze": 12,
            "rank": 10 if use_llm else 4,
            "render": 34,
            "publish": 8 if use_llm else 2,
        }
    )

    # 1. ingest ---------------------------------------------------------------
    site = ingest.site_label(url or "") if source_type == "url" else None
    ctx.stage("ingest", f"Downloading from {site}" if site else "Importing video")
    if source_type == "url" and not storage.exists((p.media or {}).get("source_key")):
        key = pkey(p.id, "source.mp4")
        extra: dict = {}
        if scan:
            # Long video: find the best moments from captions / replay graph / audio, then fetch only those.
            ctx.stage("scan", "Scanning the whole video for the best moments")
            ranges, scan_words, meta = longscan.plan(
                ingest.clean_site_url(url),
                prefs_from(settings),
                storage.path(pkey(p.id, "scan")),
                progress=lambda f, m=None: ctx.progress(f, m),
                cancelled=ctx.cancelled,
                language=settings.get("language"),
            )
            ctx.stage("ingest", f"Downloading the {len(ranges)} best parts{f' from {site}' if site else ''}")
            sections = sites.download_sections(
                ingest.clean_site_url(url),
                storage.path(key),
                ranges,
                on_progress=lambda f: ctx.progress(f, f"Downloading the best parts ({f:.0%})"),
                should_cancel=ctx.cancelled,
            )
            extra = {"sections": sections, "scan_summary": meta}
            if meta.get("language"):
                # keep the site's caption text for the downloaded parts (used for English titles below)
                storage.path(pkey(p.id, "scan_words.json")).write_text(
                    json.dumps({"language": meta["language"], "words": longscan.map_words(scan_words, sections)}),
                    encoding="utf-8",
                )
        else:
            ingest.download(
                url, storage.path(key), st.max_upload_mb * 2**20, on_progress=ctx.progress, should_cancel=ctx.cancelled
            )
        with SessionLocal() as db:
            pp = db.get(Project, p.id)
            pp.media = {**(pp.media or {}), "source_key": key, **extra}
            db.commit()
            p = pp

    # 2. prepare --------------------------------------------------------------
    ctx.stage("prepare", "Reading video details")
    src = source_path(p)
    probe = ffmpeg.probe(src)
    if probe.duration > st.max_duration_minutes * 60:
        raise UserFacingError(
            f"Videos up to {st.max_duration_minutes} minutes are supported (this one is {probe.duration / 60:.0f})."
        )
    thumb_key = pkey(p.id, "thumb.jpg")
    ffmpeg.thumbnail(src, min(probe.duration * 0.1, 10), storage.path(thumb_key))
    preview_key = None
    browser_ok = probe.video_codec in ("h264", "vp8", "vp9", "av1") and src.suffix.lower() in (
        ".mp4",
        ".webm",
        ".m4v",
        ".mov",
    )
    if not browser_ok:  # build a light H.264 proxy so the editor can preview any upload
        ctx.progress(0.3, "Creating a browser preview copy")
        preview_key = pkey(p.id, "preview.mp4")
        args = [
            ffmpeg.ffmpeg_bin(),
            "-y",
            "-v",
            "error",
            "-i",
            str(src),
            "-vf",
            "scale=-2:'min(720,ih)'",
            *ffmpeg.encoder_args("draft"),
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(storage.path(preview_key)),
        ]
        ffmpeg.run_with_progress(args, probe.duration, lambda f: ctx.progress(0.3 + 0.7 * f), ctx.cancelled)
    with SessionLocal() as db:
        pp = db.get(Project, p.id)
        pp.media = {**pp.media, "probe": probe.as_dict(), "thumb_key": thumb_key, "preview_key": preview_key}
        db.commit()
        p = pp

    # 3. transcribe -----------------------------------------------------------
    ctx.stage("transcribe", "Transcribing speech")
    wav = storage.path(pkey(p.id, "audio.wav"))
    tr = Transcript(language="none", engine="no audio track")
    if probe.has_audio:
        ffmpeg.extract_audio(src, wav)
        llm.unload()  # give Whisper the GPU memory
        tr = transcribe.transcribe(
            wav,
            settings.get("language"),
            probe.duration,
            on_progress=lambda f: ctx.progress(f, f"Transcribing speech ({f:.0%})"),
            should_cancel=ctx.cancelled,
        )
        lang = (tr.language or "").split("-")[0]
        if tr.words and lang and lang != "en":
            # Non-English speech. Titles, descriptions and moment-picking work best in English, so get
            # an English version: the site's English captions if we have them, else Whisper's translation.
            scan = _scan_caption_words(p.id)
            english = scan[1] if scan and scan[0].startswith("en") else None
            if english is None and not settings.get("transcript_only"):
                ctx.progress(0.95, "Translating speech to English for titles and copy")
                english = transcribe.transcribe(wav, tr.language, probe.duration, task="translate").words
            if english:
                storage.path(pkey(p.id, "rank_words.json")).write_text(
                    json.dumps([[w.w, w.s, w.e] for w in english]), encoding="utf-8"
                )
            if settings.get("caption_language") == "english" and english:
                tr.words = english
            elif scan and scan[0].split("-")[0] == lang:
                # The site's own captions in the spoken language are cleaner than a small speech model.
                tr.words = scan[1]
                tr.engine += " + site captions"
        storage.path(pkey(p.id, "transcript.json")).write_text(json.dumps(tr.to_json()), encoding="utf-8")

    if settings.get("transcript_only"):
        with SessionLocal() as db:
            pp = db.get(Project, p.id)
            pp.status = "ready"
            pp.analysis = {
                "language": tr.language,
                "stt_engine": tr.engine,
                "words": len(tr.words),
                "transcript_only": True,
                "seconds": round(time.time() - t0, 1),
            }
            db.commit()
        wav.unlink(missing_ok=True)
        return

    # 4. analyze --------------------------------------------------------------
    ctx.stage("analyze", "Measuring audio energy, motion and scene changes")
    sig = signals.compute(src, wav if probe.has_audio else None, probe.duration)
    save_signals(p.id, sig)
    ctx.progress(0.8, "Looking for a streamer facecam")
    facecam = reframe.detect_facecam(src, 0, probe.duration, samples=48)
    comp = None
    if settings.get("comparison", True) and not (p.media or {}).get("sections"):
        ctx.progress(0.9, "Checking for a side-by-side comparison")
        try:
            comp = compare.analyze(src, probe.duration, title=p.name)
        except Exception:  # noqa: BLE001 - an optional layout; never fail the whole run on it
            log.exception("comparison analysis failed")
    with SessionLocal() as db:
        pp = db.get(Project, p.id)
        pp.media = {**pp.media, "facecam": facecam, "compare": comp}
        db.commit()
        p = pp
    wav.unlink(missing_ok=True)

    # 5. rank -----------------------------------------------------------------
    ctx.stage("rank", "Finding and ranking highlight moments")
    with SessionLocal() as db:
        bias = feedback_bias(db, ctx.user_id)
    prefs = prefs_from(settings)
    prefs.barriers = [s["start"] for s in (p.media or {}).get("sections", [])[1:]]
    prefs.media_src = str(src)
    rank_words = load_rank_words(p.id) or tr.words
    comp_cands = compare.candidates(comp, prefs.min_dur, prefs.max_dur, sig.motion)[: prefs.count] if comp else []
    if comp_cands:
        ctx.progress(0.2, f"Found a comparison video: making {len(comp_cands)} side-by-side clips")
        prefs.count = max(0, prefs.count - len(comp_cands))
    cands, hctx = (
        highlights.discover(rank_words, sig, prefs, bias, semantic=llm.semantic_rank if use_llm else None)
        if prefs.count and (rank_words or not comp_cands)
        else ([], None)
    )
    # speech clips must not repeat a comparison moment
    cands = [c for c in cands if all(c.end <= x["start"] or c.start >= x["end"] for x in comp_cands)]
    if not cands and not comp_cands:
        raise UserFacingError("No usable moments were found in this video.")
    with SessionLocal() as db:
        pp = db.get(Project, p.id)
        for old in list(pp.clips):  # idempotent re-run: replace previous results
            storage.delete_prefix(f"clips/{old.id}")
            db.delete(old)
        db.flush()
        new = [_comparison_clip(pp, x, i, brand, src, tr.words) for i, x in enumerate(comp_cands)]
        new += [_clip_from_candidate(pp, c, hctx, len(new) + i, brand) for i, c in enumerate(cands)]
        db.add_all(new)
        pp.analysis = {
            "genre": hctx.genre if hctx else "comparison",
            "comparison": bool(comp_cands),
            "genre_detected": settings.get("genre", "auto") == "auto",
            "language": tr.language,
            "stt_engine": tr.engine,
            "words": len(tr.words),
            "speech": hctx.speech if hctx else bool(tr.words),
            "scene_cuts": len(sig.cuts),
            "ranking_engine": "signals + " + llm.engine_label() if use_llm else "signals (heuristic)",
            "llm": llm.status(),
            "candidates_scored": "multi-signal",
            "signals": sig.to_json(),
        }
        db.commit()
        clip_ids = [c.id for c in new]

    # 6-7. render + publish -----------------------------------------------------
    _render_and_publish(ctx, p.id, clip_ids, tr.words, settings)

    with SessionLocal() as db:
        pp = db.get(Project, p.id)
        pp.status = "ready"
        pp.analysis = {**pp.analysis, "seconds": round(time.time() - t0, 1)}
        db.commit()


@handler("discover")
def discover(ctx: JobContext) -> None:
    """Re-rank with new preferences (assistant / 'find more') reusing cached analysis."""
    with SessionLocal() as db:
        p = db.get(Project, ctx.project_id)
        if not p or not storage.exists(pkey(p.id, "signals.npz")):
            raise UserFacingError("Run AI Generate on this project first.")
        settings = dict(p.settings)
        brand = dict(db.get(User, p.user_id).brand_kit or {})
        existing = [(c.start, c.end, c.text) for c in p.clips]
        next_rank = max([c.rank for c in p.clips], default=-1) + 1
    overrides = {
        k: v
        for k, v in ctx.payload.items()
        if k in ("count", "min_dur", "max_dur", "mood", "genre", "position", "query") and v is not None
    }
    use_llm = settings.get("use_llm", True) and llm.status()["available"]
    ctx.plan({"rank": 15 if use_llm else 5, "render": 70, "publish": 10})
    ctx.stage("rank", "Searching the video for your request")
    tr = load_transcript(p.id)
    rank_words = load_rank_words(p.id) or tr.words
    sig = load_signals(p.id)
    prefs = prefs_from(settings, overrides)
    want = prefs.count
    prefs.count = want + len(existing)  # ask for extra so we can skip clips you already have
    with SessionLocal() as db:
        bias = feedback_bias(db, ctx.user_id)
        prefs.barriers = [s["start"] for s in (db.get(Project, p.id).media or {}).get("sections", [])[1:]]
        prefs.media_src = str(source_path(db.get(Project, p.id)))
    cands, hctx = highlights.discover(rank_words, sig, prefs, bias, semantic=llm.semantic_rank if use_llm else None)
    fresh = []
    for c in cands:
        dup = any(highlights.overlap(c, highlights.Candidate(start=s, end=e, text=t)) > 0.6 for s, e, t in existing)
        if not dup:
            fresh.append(c)
        if len(fresh) >= want:
            break
    if not fresh:
        raise UserFacingError("Every matching moment is already in your clip list.")
    with SessionLocal() as db:
        pp = db.get(Project, p.id)
        new = [_clip_from_candidate(pp, c, hctx, next_rank + i, brand) for i, c in enumerate(fresh)]
        for n in new:
            n.score_breakdown = {**n.score_breakdown, "request": ctx.payload.get("summary")}
        db.add_all(new)
        db.commit()
        ids = [c.id for c in new]
    _render_and_publish(ctx, p.id, ids, tr.words, settings)


@handler("render")
def render_job(ctx: JobContext) -> None:
    ctx.plan({"render": 1})
    ctx.stage("render", "Rendering clip")
    with SessionLocal() as db:
        clip = db.get(Clip, ctx.clip_id)
        if not clip:
            raise UserFacingError("Clip not found.")
        project = db.get(Project, clip.project_id)
        clip.render_status = "rendering"
        db.commit()
        words = load_transcript(project.id).words
        render_clip(ctx, clip, project, words, on_progress=ctx.progress)
        db.commit()


@handler("publish")
def publish_job(ctx: JobContext) -> None:
    ctx.plan({"publish": 1})
    ctx.stage("publish", "Writing publishing copy")
    with SessionLocal() as db:
        clip = db.get(Clip, ctx.clip_id)
        if not clip:
            raise UserFacingError("Clip not found.")
        project = db.get(Project, clip.project_id)
        pkg = publish.generate(
            clip.title,
            clip.hook,
            clip.text,
            clip.content_type,
            ctx.payload.get("platforms"),
            ctx.payload.get("tone", "compelling"),
            allow_llm=project.settings.get("use_llm", True),
        )
        # keep platforms that weren't regenerated
        merged = {**(clip.publish or {}).get("platforms", {}), **pkg["platforms"]}
        clip.publish = {**pkg, "platforms": merged}
        db.commit()


def cleanup_temp() -> None:
    """Delete abandoned work dirs and stale incomplete uploads (temp-file lifecycle)."""
    from .models import Upload

    ttl = get_settings().temp_file_ttl_hours * 3600
    for root in (storage.path("work"), storage.path("uploads")):
        if root.is_dir():
            for d in root.iterdir():
                if time.time() - d.stat().st_mtime > ttl:
                    shutil.rmtree(d, ignore_errors=True) if d.is_dir() else d.unlink(missing_ok=True)
    with SessionLocal() as db:
        cutoff = datetime.fromtimestamp(time.time() - ttl, UTC)
        db.query(Upload).filter(Upload.status == "uploading", Upload.created_at < cutoff).delete()
        db.commit()
