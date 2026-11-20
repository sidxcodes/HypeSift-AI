"""Comparison shorts with 2+ versions of the same moment ("GTA IV vs V vs VI: opening a car door").

Each version is a *part*: a time range of the source, optionally the left/right half of a split
screen. Three play modes:

* ``turns`` (default): every version is stacked in one frame; one plays while the others hold a
  still frame, then the next one plays. Only the playing version is heard.
* ``together``: all versions play at once; one soundtrack (the top one by default; "mix" blends).
* ``grid_then_single``: all versions together in one frame for a few seconds, then each version
  full screen, one after another (each with its own sound).

The hook title shows on the join between the panels, each panel gets a name badge (the playing
one is highlighted), and the captions follow whichever version is speaking.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

from . import captions as cap
from . import ffmpeg

GRID_SECONDS = 3.0
PLAY_MODES = {"turns": "Take turns", "together": "Play together", "grid_then_single": "All at once, then one by one"}


def plan(parts: list[dict], play: str, max_total: float | None = None) -> list[dict]:
    """Timeline: which part shows where and when. Returns segments
    [{"kind": "stack"|"single", "t0", "t1", "active": index|None, "parts": [(i, src_from, src_to)]}]."""
    n = len(parts)
    durs = [p["end"] - p["start"] for p in parts]
    if play == "together":
        d = min(durs)
        if max_total:
            d = min(d, max_total)
        return [{"kind": "stack", "t0": 0.0, "t1": d, "active": None}]
    if play == "grid_then_single":
        g = min(GRID_SECONDS, min(durs))
        segs = [{"kind": "stack", "t0": 0.0, "t1": g, "active": None}]
        t = g
        for i in range(n):
            segs.append({"kind": "single", "t0": t, "t1": t + durs[i], "active": i})
            t += durs[i]
        return segs
    segs, t = [], 0.0
    for i in range(n):
        segs.append({"kind": "stack", "t0": t, "t1": t + durs[i], "active": i})
        t += durs[i]
    return segs


def fit_parts(parts: list[dict], play: str, max_dur: float) -> list[dict]:
    """Trim parts so the finished clip fits in max_dur."""
    n = len(parts)
    if play == "together":
        cap_each = max_dur
    elif play == "grid_then_single":
        cap_each = max(3.0, (max_dur - GRID_SECONDS) / n)
    else:
        cap_each = max(3.0, max_dur / n)
    return [{**p, "end": min(p["end"], p["start"] + cap_each)} for p in parts]


def _panel(src: str, part: dict, w: int, h: int, fps: float, label: str) -> list[str]:
    crop = {"left": "crop=iw/2:ih:0:0,", "right": "crop=iw/2:ih:iw/2:0,"}.get(part.get("crop") or "", "")
    return [
        f"[{src}]{crop}scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps={fps:.3f},"
        f"format=yuv420p,setpts=PTS-STARTPTS[{label}]"
    ]


def build_graph(parts: list[dict], play: str, audio: str, W: int, H: int, fps: float, has_audio: bool) -> list[str]:
    n = len(parts)
    segs = plan(parts, play)
    hp = (H // n) // 2 * 2
    g: list[str] = []
    durs = [p["end"] - p["start"] for p in parts]
    div = max(4, int(6 * W / 1080)) // 2 * 2

    def stack(labels: list[str], out: str) -> None:
        last_h = H - hp * (n - 1)
        fixed = []
        for k, lab in enumerate(labels):
            if k == n - 1 and last_h != hp:
                g.append(f"[{lab}]scale={W}:{last_h},setsar=1[{lab}f]")
                fixed.append(f"[{lab}f]")
            else:
                fixed.append(f"[{lab}]")
        boxes = ",".join(
            f"drawbox=x=0:y={hp * k - div // 2}:w={W}:h={div}:color=white@0.95:t=fill" for k in range(1, n)
        )
        g.append("".join(fixed) + f"vstack=inputs={n}" + (f",{boxes}" if boxes else "") + f"[{out}]")

    if play == "together":
        d = segs[0]["t1"]
        for i, p in enumerate(parts):
            g += _panel(f"{i}:v", p, W, hp, fps, f"p{i}")
            g.append(f"[p{i}]trim=0:{d:.3f},setpts=PTS-STARTPTS[q{i}]")
        stack([f"q{i}" for i in range(n)], "vr")
        if has_audio:
            if audio == "mix":
                ins = "".join(f"[{i}:a]" for i in range(n))
                g.append(f"{ins}amix=inputs={n}:duration=shortest:normalize=1,atrim=0:{d:.3f}[ar]")
            else:
                g.append(f"[0:a]atrim=0:{d:.3f},asetpts=PTS-STARTPTS[ar]")
        return g

    if play == "turns":
        total = sum(durs)
        off = 0.0
        for i, p in enumerate(parts):
            g += _panel(f"{i}:v", p, W, hp, fps, f"p{i}")
            before, after = off, total - off - durs[i]
            pads = []
            if before > 0.01:
                pads.append(f"start_duration={before:.3f}:start_mode=clone")
            if after > 0.01:
                pads.append(f"stop_duration={after:.3f}:stop_mode=clone")
            g.append(f"[p{i}]" + (f"tpad={':'.join(pads)}," if pads else "") + f"trim=0:{total:.3f}[q{i}]")
            off += durs[i]
        stack([f"q{i}" for i in range(n)], "vr")
        if has_audio:
            ins = "".join(f"[{i}:a]" for i in range(n))
            g.append(f"{ins}concat=n={n}:v=0:a=1[ar]")
        return g

    # grid_then_single
    gs = segs[0]["t1"]
    for i, p in enumerate(parts):
        g.append(f"[{i}:v]split=2[in{i}a][in{i}b]")
        g += _panel(f"in{i}a", p, W, hp, fps, f"p{i}")
        g.append(f"[p{i}]trim=0:{gs:.3f},setpts=PTS-STARTPTS[q{i}]")
    stack([f"q{i}" for i in range(n)], "grid")
    for i, p in enumerate(parts):
        g += _panel(f"in{i}b", p, W, H, fps, f"s{i}")
    g.append("[grid]" + "".join(f"[s{i}]" for i in range(n)) + f"concat=n={n + 1}:v=1:a=0[vr]")
    if has_audio:
        g.append("[0:a]asplit=2[a0g][a0s]")
        g.append(f"[a0g]atrim=0:{gs:.3f},asetpts=PTS-STARTPTS[ag]")
        rest = "[a0s]" + "".join(f"[{i}:a]" for i in range(1, n))
        g.append(f"[ag]{rest}concat=n={n + 1}:v=0:a=1[ar]")
    return g


def timeline_words(parts: list[dict], play: str, words) -> list[dict]:
    """Words re-timed onto the finished clip's timeline (only the version that's heard)."""
    out = []
    for seg in plan(parts, play):
        idx = seg["active"] if seg["active"] is not None else 0
        src_from = parts[idx]["start"]
        span = seg["t1"] - seg["t0"]
        for w in words:
            rel = w.s - src_from
            if 0 <= rel < span and w.e - src_from <= span + 0.3:
                out.append(
                    {"w": w.w, "s": round(seg["t0"] + rel, 3), "e": round(seg["t0"] + min(span, w.e - src_from), 3)}
                )
    return out


def label_events(parts: list[dict], play: str, W: int, H: int, accent: str = "#FF7A59") -> list[str]:
    """Name badges: on every panel while stacked (the playing one highlighted), top-left when single."""
    n = len(parts)
    hp = H // n
    k = W / 1080
    pad = int(30 * k)
    ev = []
    for seg in plan(parts, play):
        for i, p in enumerate(parts):
            name = cap._esc(str(p.get("label") or "").upper())[:32]
            if not name:
                continue
            if seg["kind"] == "single" and seg["active"] != i:
                continue
            y = pad if seg["kind"] == "single" else hp * i + pad
            on = seg["active"] == i and seg["kind"] == "stack"
            box = cap.ass_color(accent) if on else "&H260F0B0B"
            ev.append(
                f"Dialogue: 2,{cap.ts(seg['t0'])},{cap.ts(seg['t1'])},Lab,,0,0,0,,"
                f"{{\\pos({pad},{y})\\fs{int(56 * k)}\\bord{16 * k:.1f}\\3c{box}}}{name}"
            )
    return ev


def render(
    src: Path,
    probe: ffmpeg.Probe,
    parts: list[dict],
    edits: dict,
    words,
    out_path: Path,
    work_dir: Path,
    W: int,
    H: int,
    keywords: set[str] | None = None,
    on_progress: Callable[[float], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict:
    work_dir.mkdir(parents=True, exist_ok=True)
    mc = edits.get("multi") or {}
    play = mc.get("play") if mc.get("play") in PLAY_MODES else "turns"
    parts = [dict(p) for p in parts if p["end"] - p["start"] >= 0.5]
    if len(parts) < 2:
        raise ffmpeg.MediaError("A comparison needs at least two versions.")
    segs = plan(parts, play)
    out_dur = segs[-1]["t1"]
    fps = min(probe.fps, 60) or 30
    graph = build_graph(parts, play, mc.get("audio", "active"), W, H, fps, probe.has_audio)

    # captions, hook title (on the join), name badges
    ce = edits.get("captions") or {}
    style = cap.style_for(ce) if ce.get("enabled", True) else None
    tw = timeline_words(parts, play, words)
    chunks = cap.chunk_words(tw) if tw else []
    seam = 0.5 if len(parts) == 2 and play != "grid_then_single" else None
    if style and not style.get("pos") and seam is None:
        style["position"] = "lower"
    overlays = []
    for ov in edits.get("overlays") or []:
        o = {**ov, "end": min(float(ov.get("end", 3.0)), out_dur)}
        if o.get("kind") == "title" and not o.get("pos"):
            o["pos"] = {"x": 0.5, "y": 0.5 if len(parts) == 2 else 1 / len(parts)}
        overlays.append(o)
    pb = edits.get("progress_bar") or {}
    ass = cap.build_ass(
        W,
        H,
        chunks,
        style,
        overlays,
        keywords,
        out_dur,
        progress_bar=pb.get("color") if pb.get("enabled") else None,
        seam=seam,
        progress_pos="top" if pb.get("position") == "top" else "bottom",
    )
    if (edits.get("labels") or {}).get("enabled", True):
        ass = ass.rstrip("\n") + "\n" + "\n".join(label_events(parts, play, W, H)) + "\n"
    (work_dir / "captions.ass").write_text(ass, encoding="utf-8")
    from .render import _fonts_rel

    v = edits.get("video") or {}
    vf = [f"ass=filename=captions.ass:fontsdir='{_fonts_rel(work_dir)}'"]
    if float(v.get("fade_out") or 0) > 0:
        d = float(v["fade_out"])
        vf.append(f"fade=t=out:st={max(0, out_dur - d):.2f}:d={d:.2f}")
    vf.append("format=yuv420p")
    graph.append(f"[vr]{','.join(vf)}[vout]")
    if probe.has_audio:
        graph.append(
            f"[ar]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000,afade=t=out:st={max(0, out_dur - 0.4):.2f}:d=0.4[aout]"
        )
    (work_dir / "graph.txt").write_text(";\n".join(graph), encoding="utf-8")

    args = [ffmpeg.ffmpeg_bin(), "-y", "-v", "error"]
    for p in parts:
        args += ["-ss", f"{p['start']:.3f}", "-t", f"{p['end'] - p['start']:.3f}", "-i", str(src)]
    args += ["-/filter_complex", "graph.txt", "-map", "[vout]"]
    if probe.has_audio:
        args += ["-map", "[aout]", "-c:a", "aac", "-b:a", "160k"]
    args += [
        *ffmpeg.encoder_args(edits.get("quality", "standard")),
        "-r",
        f"{fps:.3f}",
        "-movflags",
        "+faststart",
        "out.mp4",
    ]
    ffmpeg.run_with_progress(args, out_dur, on_progress, should_cancel, cwd=work_dir)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(work_dir / "out.mp4"), out_path)
    return {
        "duration": round(out_dur, 3),
        "width": W,
        "height": H,
        "srt": cap.build_srt(chunks, uppercase=bool(style and style.get("uppercase"))),
        "segments": [[0.0, round(out_dur, 3)]],
        "chunks": chunks,
    }
