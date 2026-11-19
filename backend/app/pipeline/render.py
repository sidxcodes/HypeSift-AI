"""Compose a finished short: trim → reframe → silence cut → captions/overlays → fades → encode."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from . import captions as cap
from . import ffmpeg, reframe
from .transcribe import Word

FONTS_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"

DEFAULT_EDITS: dict[str, Any] = {
    "aspect": "9:16",
    "crop": {"mode": "auto", "x": 0.5, "y": 0.5, "zoom": 1.0},  # auto | manual | center | split | fit
    "captions": {"enabled": True, "preset": "bold_creator", "style": {}, "chunks": None},
    "overlays": [],  # [{kind: title|watermark, text, start, end}]
    "silence_removal": False,
    "audio": {"gain_db": 0.0, "normalize": True, "fade_in": 0.15, "fade_out": 0.4},
    "video": {"fade_in": 0.0, "fade_out": 0.25},
    "quality": "standard",  # draft | standard | high
    "zoom": {"start": False, "key_phrases": False},  # punch-in at the start / on key phrases
    "logo": {"key": None, "position": "top_right", "size": 0.16, "opacity": 0.92},
    "music": {"key": None, "volume": 0.16},  # background bed, ducked under speech
    "progress_bar": {"enabled": False, "color": "#C6F432"},
}

LOGO_POS = {
    "top_left": "{m}:{m}",
    "top_right": "W-w-{m}:{m}",
    "bottom_left": "{m}:H-h-{m}",
    "bottom_right": "W-w-{m}:H-h-{m}",
}


def zoom_moments(chunks: list[dict], keywords: set[str], out_dur: float, limit: int = 6) -> list[float]:
    """Output-timeline moments where a key phrase is spoken, at least 3.5 s apart."""
    hits: list[float] = []
    for ch in chunks:
        for w in ch.get("words") or []:
            tok = "".join(c for c in w["w"].lower() if c.isalnum())
            if tok in keywords and 0.8 < w["s"] < out_dur - 1.2 and (not hits or w["s"] - hits[-1] >= 3.5):
                hits.append(round(w["s"], 2))
    return hits[:limit]


def zoom_expr(start: bool, moments: list[float]) -> str | None:
    """zoompan z(t): ease out of a 1.18x punch at the start; quick 1.12x punch-ins held ~1.1 s."""
    terms = []
    if start:
        terms.append("0.18*pow(max(0,1-it/1.1),2)")
    for m in moments:
        a, b = m - 0.08, m + 1.1
        terms.append(f"0.12*min(1,max(0,(it-{a:.2f})/0.14))*min(1,max(0,({b:.2f}-it)/0.3))")
    if not terms:
        return None
    return "1+" + "+".join(terms)


def merged_edits(edits: dict | None) -> dict:
    out = {
        k: (dict(v) if isinstance(v, dict) else (list(v) if isinstance(v, list) else v))
        for k, v in DEFAULT_EDITS.items()
    }
    for k, v in (edits or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = {**out[k], **v}
        else:
            out[k] = v
    return out


@dataclass
class Segment:
    s: float  # relative to clip start
    e: float


def keep_segments(
    words: list[Word],
    start: float,
    end: float,
    enabled: bool,
    max_gap: float = 0.7,
    lead: float = 0.12,
    tail: float = 0.18,
) -> list[Segment]:
    dur = end - start
    if not enabled:
        return [Segment(0.0, dur)]
    ws = [w for w in words if w.s >= start - 0.05 and w.e <= end + 0.05]
    if len(ws) < 2:
        return [Segment(0.0, dur)]
    segs: list[Segment] = []
    cur_s = 0.0
    for a, b in zip(ws, ws[1:], strict=False):
        if b.s - a.e > max_gap:
            segs.append(Segment(cur_s, min(dur, a.e - start + tail)))
            cur_s = max(0.0, b.s - start - lead)
    segs.append(Segment(cur_s, dur))
    return [s for s in segs if s.e - s.s > 0.15]


def time_mapper(segs: list[Segment]) -> Callable[[float], float | None]:
    """Map original clip-relative time → output time (None if the moment was cut)."""

    def f(t: float) -> float | None:
        acc = 0.0
        for sg in segs:
            if t < sg.s:
                return acc  # inside a removed gap: snap to next segment start
            if t <= sg.e:
                return acc + (t - sg.s)
            acc += sg.e - sg.s
        return acc if segs else t

    return f


def clip_words(words: list[Word], start: float, end: float) -> list[dict]:
    return [
        {"w": w.w, "s": round(w.s - start, 3), "e": round(w.e - start, 3)} for w in words if w.e > start and w.s < end
    ]


def default_chunks(words: list[Word], start: float, end: float, preset: str) -> list[dict]:
    style = cap.PRESETS.get(preset, cap.PRESETS["bold_creator"])
    return cap.chunk_words(
        clip_words(words, start, end), max_words=style["max_words"], max_chars=16 * style["max_words"] // 2 + 12
    )


def _map_chunks(chunks: list[dict], fmap: Callable[[float], float | None]) -> list[dict]:
    out = []
    for ch in chunks:
        ch = cap.retime_chunk(ch)
        words = [{**w, "s": fmap(w["s"]), "e": fmap(w["e"])} for w in ch["words"]]
        words = [w for w in words if w["s"] is not None and w["e"] is not None and w["e"] > w["s"] - 1e-6]
        if words:
            out.append(
                {**ch, "s": fmap(ch["s"]) or words[0]["s"], "e": fmap(ch["e"]) or words[-1]["e"], "words": words}
            )
    return out


def output_size(aspect: str, quality: str) -> tuple[int, int]:
    w, h = reframe.ASPECTS.get(aspect, reframe.ASPECTS["9:16"])
    if quality == "draft":
        w, h = int(w * 2 / 3) // 2 * 2, int(h * 2 / 3) // 2 * 2
    return w, h


def build_video_chain(probe: ffmpeg.Probe, edits: dict, rf: dict, W: int, H: int) -> str:
    """Filter chain from [0:v] to [vr] (reframed, scaled)."""
    crop = edits["crop"]
    mode = crop.get("mode", "auto")
    aspect = edits["aspect"]
    zoom = max(1.0, min(3.0, float(crop.get("zoom") or 1.0)))
    sw, sh = probe.width, probe.height
    if mode == "split" and rf.get("split") and aspect == "9:16":
        half_h = H // 2
        cw, ch = crop_for_ratio(sw, sh, W / half_h)
        y = (sh - ch) // 2
        xa = int(min(max(rf["split"]["left"] * sw - cw / 2, 0), sw - cw))
        xb = int(min(max(rf["split"]["right"] * sw - cw / 2, 0), sw - cw))
        return (
            f"[0:v]split=2[sa][sb];[sa]crop={cw}:{ch}:{xa}:{y},scale={W}:{half_h}:flags=lanczos[ta];"
            f"[sb]crop={cw}:{ch}:{xb}:{y},scale={W}:{half_h}:flags=lanczos[tb];[ta][tb]vstack=2,setsar=1[vr]"
        )
    if mode == "fit":
        return (
            f"[0:v]split=2[bg][fg];[bg]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
            f"boxblur=24:2,eq=brightness=-0.08[bgb];[fg]scale={W}:{H}:force_original_aspect_ratio=decrease"
            f":flags=lanczos[fgs];[bgb][fgs]overlay=(W-w)/2:(H-h)/2,setsar=1[vr]"
        )
    cw, ch = reframe.crop_box(sw, sh, aspect, zoom)
    if mode == "auto" and rf.get("path"):
        keys = rf["path"]
    elif mode == "manual":
        keys = [[0.0, float(crop.get("x", 0.5)), float(crop.get("y", 0.5))]]
    else:
        keys = [[0.0, 0.5, 0.5]]
    xe = reframe.piecewise_expr(keys, 1, sw, cw)
    ye = reframe.piecewise_expr(keys, 2, sh, ch)
    return f"[0:v]crop=w={cw}:h={ch}:x='{xe}':y='{ye}',scale={W}:{H}:flags=lanczos,setsar=1[vr]"


def crop_for_ratio(sw: int, sh: int, ratio: float) -> tuple[int, int]:
    if sw / sh > ratio:
        ch = sh
        cw = int(sh * ratio)
    else:
        cw = sw
        ch = int(sw / ratio)
    return cw // 2 * 2, ch // 2 * 2


def _fonts_rel(work_dir: Path) -> str:
    try:
        return os.path.relpath(FONTS_DIR, work_dir).replace("\\", "/")
    except ValueError:  # different drive on Windows: copy fonts next to the job
        dst = work_dir / "fonts"
        if not dst.exists():
            shutil.copytree(FONTS_DIR, dst)
        return "fonts"


def render(
    src: Path,
    probe: ffmpeg.Probe,
    start: float,
    end: float,
    edits_in: dict | None,
    rf: dict,
    words: list[Word],
    out_path: Path,
    work_dir: Path,
    keywords: set[str] | None = None,
    on_progress: Callable[[float], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict:
    edits = merged_edits(edits_in)
    work_dir.mkdir(parents=True, exist_ok=True)
    start = max(0.0, start)
    end = min(probe.duration, end)
    if end - start < 0.5:
        raise ffmpeg.MediaError("Clip is shorter than half a second.")
    W, H = output_size(edits["aspect"], edits["quality"])
    segs = keep_segments(words, start, end, bool(edits.get("silence_removal")))
    fmap = time_mapper(segs)
    out_dur = sum(s.e - s.s for s in segs)

    ce = edits["captions"]
    chunks = ce.get("chunks") or default_chunks(words, start, end, ce.get("preset", "bold_creator"))
    mapped = _map_chunks(chunks, fmap)
    style = cap.style_for(ce) if ce.get("enabled", True) else None
    overlays = []
    for ov in edits.get("overlays") or []:
        o = dict(ov)
        o["start"] = fmap(float(o.get("start", 0))) or 0.0
        o["end"] = fmap(float(o.get("end", out_dur))) or out_dur
        overlays.append(o)
    pb = edits.get("progress_bar") or {}
    ass = cap.build_ass(
        W, H, mapped, style, overlays, keywords, out_dur, progress_bar=pb.get("color") if pb.get("enabled") else None
    )
    (work_dir / "captions.ass").write_text(ass, encoding="utf-8")
    srt = cap.build_srt(mapped, uppercase=bool(style and style.get("uppercase")))

    graph = [build_video_chain(probe, edits, rf, W, H)]
    has_a = probe.has_audio
    vlast, alast = "[vr]", "[0:a]" if has_a else None
    if len(segs) > 1 or segs[0].s > 0.01 or segs[0].e < (end - start) - 0.01:
        n = len(segs)
        graph.append(f"[vr]split={n}" + "".join(f"[vs{i}]" for i in range(n)))
        if has_a:
            graph.append("[0:a]asplit=" + str(n) + "".join(f"[as{i}]" for i in range(n)))
        cat_in = ""
        for i, sg in enumerate(segs):
            graph.append(f"[vs{i}]trim=start={sg.s:.3f}:end={sg.e:.3f},setpts=PTS-STARTPTS[v{i}]")
            if has_a:
                graph.append(f"[as{i}]atrim=start={sg.s:.3f}:end={sg.e:.3f},asetpts=PTS-STARTPTS[a{i}]")
                cat_in += f"[v{i}][a{i}]"
            else:
                cat_in += f"[v{i}]"
        graph.append(f"{cat_in}concat=n={n}:v=1:a={1 if has_a else 0}[vc]" + ("[ac]" if has_a else ""))
        vlast, alast = "[vc]", "[ac]" if has_a else None

    vf = []
    zm = edits.get("zoom") or {}
    zx = zoom_expr(
        bool(zm.get("start")), zoom_moments(mapped, set(keywords or ()), out_dur) if zm.get("key_phrases") else []
    )
    fps = min(probe.fps, 60) or 30
    if zx:
        vf.append(f"zoompan=z='{zx}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={fps:.3f}")
    logo = edits.get("logo") or {}
    logo_path = Path(logo["path"]) if logo.get("path") else None
    if logo_path and logo_path.exists():
        # captions go on top of the logo; the logo sits on the reframed (and zoomed) picture
        pre = f"{vlast}{','.join(vf) or 'null'}[vz]"
        graph.append(pre)
        lw = int(W * max(0.06, min(0.4, float(logo.get("size") or 0.16)))) // 2 * 2
        op = max(0.1, min(1.0, float(logo.get("opacity") or 0.92)))
        m = int(36 * W / 1080)
        pos = LOGO_POS.get(logo.get("position") or "top_right", LOGO_POS["top_right"]).format(m=m)
        graph.append(f"[1:v]scale={lw}:-1,format=rgba,colorchannelmixer=aa={op:.2f}[lg]")
        graph.append(f"[vz][lg]overlay={pos}:format=auto[vl]")
        vlast, vf = "[vl]", []
    vf.append(f"ass=filename=captions.ass:fontsdir='{_fonts_rel(work_dir)}'")
    v = edits.get("video") or {}
    if float(v.get("fade_in") or 0) > 0:
        vf.append(f"fade=t=in:st=0:d={float(v['fade_in']):.2f}")
    if float(v.get("fade_out") or 0) > 0:
        d = float(v["fade_out"])
        vf.append(f"fade=t=out:st={max(0, out_dur - d):.2f}:d={d:.2f}")
    vf.append("format=yuv420p")
    graph.append(f"{vlast}{','.join(vf)}[vout]")
    music = edits.get("music") or {}
    music_path = Path(music["path"]) if music.get("path") else None
    has_music = bool(music_path and music_path.exists())
    mus_idx = 2 if (logo_path and logo_path.exists()) else 1
    if has_music:
        vol = max(0.02, min(1.0, float(music.get("volume") or 0.16)))
        graph.append(f"[{mus_idx}:a]atrim=0:{out_dur:.3f},volume={vol:.3f},aresample=48000[mus]")
    if has_a or has_music:
        a = edits.get("audio") or {}
        af = []
        if float(a.get("gain_db") or 0) != 0:
            af.append(f"volume={float(a['gain_db']):.1f}dB")
        if a.get("normalize", True):
            af.append("loudnorm=I=-14:TP=-1.5:LRA=11")
        if float(a.get("fade_in") or 0) > 0:
            af.append(f"afade=t=in:st=0:d={float(a['fade_in']):.2f}")
        if float(a.get("fade_out") or 0) > 0:
            d = float(a["fade_out"])
            af.append(f"afade=t=out:st={max(0, out_dur - d):.2f}:d={d:.2f}")
        fades = [x for x in af if x.startswith("afade")]
        af = [x for x in af if not x.startswith("afade")]
        af.append("aresample=48000")
        if has_a and has_music:
            # speech first, then the music bed ducked whenever someone talks
            graph.append(f"{alast}{','.join(af)},asplit=2[sp][key]")
            graph.append("[mus][key]sidechaincompress=threshold=0.02:ratio=9:attack=15:release=400[duck]")
            graph.append(f"[sp][duck]amix=inputs=2:duration=first:normalize=0{''.join(',' + f for f in fades)}[aout]")
        elif has_music:
            graph.append(f"[mus]anull{''.join(',' + f for f in fades)}[aout]")
        else:
            graph.append(f"{alast}{','.join(af + fades)}[aout]")
    (work_dir / "graph.txt").write_text(";\n".join(graph), encoding="utf-8")

    tmp_out = work_dir / "out.mp4"
    args = [
        ffmpeg.ffmpeg_bin(),
        "-y",
        "-v",
        "error",
        "-ss",
        f"{start:.3f}",
        "-t",
        f"{end - start:.3f}",
        "-i",
        str(src),
    ]
    if logo_path and logo_path.exists():
        args += ["-i", str(logo_path)]
    if has_music:
        args += ["-stream_loop", "-1", "-i", str(music_path)]
    args += [
        "-/filter_complex",
        "graph.txt",
        "-map",
        "[vout]",
    ]
    if has_a or has_music:
        args += ["-map", "[aout]", "-c:a", "aac", "-b:a", "160k"]
    args += [
        *ffmpeg.encoder_args(edits["quality"]),
        "-r",
        f"{min(probe.fps, 60):.3f}",
        "-movflags",
        "+faststart",
        "out.mp4",
    ]
    ffmpeg.run_with_progress(args, out_dur, on_progress, should_cancel, cwd=work_dir)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(tmp_out), out_path)
    return {
        "duration": round(out_dur, 3),
        "width": W,
        "height": H,
        "srt": srt,
        "segments": [[round(s.s, 3), round(s.e, 3)] for s in segs],
        "chunks": mapped,
    }


def cover_time(src: Path, start: float, end: float) -> float:
    """Pick a sharp, face-forward frame for the cover (relative seconds)."""
    try:
        frames, _ = ffmpeg.read_frames(src, start, min(end, start + 30), 1.0, 320)
    except ffmpeg.MediaError:
        return 0.5
    best, best_t = -1.0, 0.5
    for i, fr in enumerate(frames):
        sharp = float(cv2.Laplacian(fr, cv2.CV_64F).var())
        faces = reframe._faces(fr)
        bright = float(np.mean(fr))
        s = sharp * (1.6 if faces else 1.0) * (0.4 if bright < 35 else 1.0)
        if i == 0:
            s *= 0.8  # first frame is often mid-transition
        if s > best:
            best, best_t = s, i + 0.5
    return best_t
