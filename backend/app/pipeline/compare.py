"""Comparison videos ("GTA 6 vs Cyberpunk 2077", "old vs new", "before / after").

Two common formats are recognised and turned into stacked vertical shorts:

* **Split screen**: both versions side by side, divided by a straight vertical line in the middle.
  → the left half goes on top, the right half below.
* **Alternating blocks**: a stretch of version A, then the same scenario in version B (often
  marked by a small logo badge). → each A stretch is paired with the neighbouring B stretch and
  both play at the same time, one above the other.

Layout and grouping use plain computer vision (fast and dependable). The optional local vision
model (via Ollama) only names the two sides from the video title ("GTA 6", "Cyberpunk
2077") and describes scenes for clip titles; without it, sides are named in title order.
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

import cv2
import numpy as np

from . import ffmpeg, llm

log = logging.getLogger("hypesift.compare")

FPS = 2.0
WIDTH = 320
_VS = re.compile(r"\s+(?:vs\.?|versus|v/s|or)\s+", re.I)
_COMPARE_WORDS = re.compile(
    r"\b(vs\.?|versus|v/s|comparison|compared|side by side|before and after|old and new)\b", re.I
)


def names_from_title(title: str) -> list[str]:
    """'GTA 6 vs Cyberpunk 2077 - ULTIMATE Comparison! ...' -> ['GTA 6', 'Cyberpunk 2077']."""
    head = re.split(r"[-–—|:!(\[]", title, maxsplit=1)
    parts = _VS.split(title if len(head) < 2 or not _VS.search(head[0]) else head[0])
    if len(parts) < 2:
        return []
    a = re.split(r"[-–—|:!(\[,]", parts[0])[-1].strip()
    b = re.split(r"[-–—|:!(\[,]", parts[1])[0].strip()
    a = re.sub(r"(?i)^(the|comparison|compare)\s+", "", a)[-40:].strip()
    b = re.sub(r"(?i)\s+(comparison|compared|graphics|gameplay)$", "", b)[:40].strip()
    return [a, b] if a and b and a.lower() != b.lower() else []


def looks_like_comparison(title: str) -> bool:
    return bool(_COMPARE_WORDS.search(title or ""))


def read_rgb(src: Path, start: float, end: float, fps: float = FPS, width: int = WIDTH) -> np.ndarray:
    """(n, h, w, 3) uint8 frames."""
    probe = ffmpeg.probe(src)
    h = int(round(probe.height * width / probe.width / 2)) * 2
    cmd = [
        ffmpeg.ffmpeg_bin(),
        "-v",
        "error",
        "-ss",
        f"{start:.3f}",
        "-t",
        f"{max(0.5, end - start):.3f}",
        "-i",
        str(src),
        "-vf",
        f"fps={fps},scale={width}:{h}",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-",
    ]
    r = subprocess.run(cmd, capture_output=True, check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    n = len(r.stdout) // (width * h * 3)
    return np.frombuffer(r.stdout[: n * width * h * 3], np.uint8).reshape(n, h, width, 3)


# ----------------------------------------------------------------------------- detection


def split_scores(frames: np.ndarray) -> np.ndarray:
    """Per frame: how strongly a straight vertical line divides the frame in the middle."""
    gray = frames.mean(axis=3)
    g = np.abs(np.diff(gray, axis=2))  # n, h, w-1
    W = frames.shape[2]
    out = np.zeros(len(frames))
    for i in range(len(frames)):
        col = g[i].mean(axis=0)
        c = W // 2
        seam = col[c - 3 : c + 3].max()
        # a real divider spans the full height: most rows show the jump at the same column
        rows = (g[i][:, c - 3 : c + 3].max(axis=1) > 18).mean()
        left, right = gray[i][:, : c - 4], gray[i][:, c + 4 :]
        diff = abs(left.mean() - right.mean()) + abs(left.std() - right.std())
        out[i] = (seam / (np.median(col) + 1e-6)) * rows * (1 if diff > 4 else 0.5)
    return out


def _runs(mask: np.ndarray, min_len: int) -> list[tuple[int, int]]:
    out, i = [], 0
    while i < len(mask):
        if mask[i]:
            j = i
            while j < len(mask) and mask[j]:
                j += 1
            if j - i >= min_len:
                out.append((i, j))
            i = j
        else:
            i += 1
    return out


def _smooth_labels(lab: np.ndarray, k: int = 7) -> np.ndarray:
    pad = np.pad(lab, (k // 2, k // 2), mode="edge")
    return np.array([np.bincount(pad[i : i + k]).argmax() for i in range(len(lab))])


def badge_box(frames: np.ndarray) -> tuple[int, int, int, int] | None:
    """A persistent overlay (version badge / watermark) in the top band: pixels that stay very
    bright or very consistent in most frames while the picture behind them changes."""
    n, H, W, _ = frames.shape
    top = frames[:, : max(6, int(H * 0.14))].astype(np.float32)
    gray = top.mean(axis=3)
    bright = (gray > 205).mean(axis=0)
    mask = bright > 0.55
    if mask.sum() < 12:
        return None
    ys, xs = np.where(mask)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    if (x1 - x0) > W * 0.5:
        return None  # a bright sky / UI bar, not a badge
    return int(y0), int(y1), int(x0), int(x1)


def badge_features(frames: np.ndarray, box: tuple[int, int, int, int] | None = None) -> np.ndarray:
    """Colour signature of the version badge (or, without one, of the top band)."""
    n, H, W, _ = frames.shape
    if box:
        y0, y1, x0, x1 = box
        region = frames[:, y0:y1, x0:x1]
    else:
        region = frames[:, : max(4, int(H * 0.11)), int(W * 0.3) : int(W * 0.7)]
    feats = []
    for b in region:
        hsv = cv2.cvtColor(np.ascontiguousarray(b), cv2.COLOR_RGB2HSV)
        sat = hsv[..., 1] > 60
        hue = np.histogram(hsv[..., 0][sat], bins=12, range=(0, 180))[0].astype(np.float32)
        hue /= hue.sum() + 1e-6
        small = (
            cv2.resize(cv2.cvtColor(np.ascontiguousarray(b), cv2.COLOR_RGB2GRAY), (12, 4)).astype(np.float32).ravel()
        )
        small = (small - small.mean()) / (small.std() + 1e-6)
        feats.append(np.concatenate([hue * 3, [sat.mean() * 3], small * (0.25 if box else 0.0)]))
    return np.array(feats, np.float32)


def _kmeans2(x: np.ndarray, iters: int = 25, restarts: int = 8) -> tuple[np.ndarray, float]:
    """2-means with several random starts (outlier frames can't hijack a cluster); returns labels and
    how well separated the two groups are (centre distance / typical in-cluster distance)."""
    rng = np.random.default_rng(0)
    best: tuple[float, np.ndarray, np.ndarray] | None = None
    for _ in range(restarts):
        c = x[rng.choice(len(x), 2, replace=False)]
        for _ in range(iters):
            d = np.linalg.norm(x[:, None] - c[None], axis=2)
            lab = d.argmin(1)
            c = np.stack([x[lab == k].mean(0) if (lab == k).any() else c[k] for k in range(2)])
        d = np.linalg.norm(x[:, None] - c[None], axis=2)
        inertia = float((d.min(1) ** 2).sum())
        if best is None or inertia < best[0]:
            best = (inertia, d, c)
    _, d, c = best
    spread = float(np.median(d.min(1))) + 1e-6
    return d.argmin(1), float(np.linalg.norm(c[0] - c[1]) / spread)


def analyze(src: Path, duration: float, title: str = "") -> dict | None:
    """Find split-screen stretches and alternating A/B blocks. None when the video isn't a comparison."""
    frames = read_rgb(src, 0, duration)
    if len(frames) < 10:
        return None
    t = lambda i: round(i / FPS, 2)  # noqa: E731
    split = split_scores(frames) > 6.0
    split = _smooth_labels(split.astype(int), 5).astype(bool)
    splits = [(t(a), t(b)) for a, b in _runs(split, int(3 * FPS))]

    blocks: list[tuple[float, float, int]] = []
    full = np.where(~split)[0]
    if len(full) >= 20 and (looks_like_comparison(title) or splits):
        box = badge_box(frames[full])
        if box:  # only frames where the badge is actually on screen (not transitions / end cards)
            y0, y1, x0, x1 = box
            visible = frames[full, y0:y1, x0:x1].mean(axis=(1, 2, 3)) > 150
            full = full[visible]
        lab, sep = _kmeans2(badge_features(frames[full], box)) if len(full) >= 20 else (np.zeros(0, int), 0.0)
        lab = _smooth_labels(lab, 9)
        share = np.bincount(lab, minlength=2) / len(lab)
        if sep > 2.5 and share.min() > 0.15:
            seq = np.full(len(frames), -1)
            seq[full] = lab
            for k in (0, 1):
                for a, b in _runs(seq == k, int(3 * FPS)):
                    blocks.append((t(a), t(b), k))
            blocks.sort()
            # real A/B structure alternates: both sides need several stretches
            if min(sum(1 for *_, k in blocks if k == side) for side in (0, 1)) < 2:
                blocks = []
    if not splits and not blocks:
        return None
    names = names_from_title(title)
    side_names = _name_sides(src, blocks, names) if blocks else {}
    split_names = _name_split(src, splits, names) if splits else None
    return {
        "splits": [list(s) for s in splits],
        "blocks": [[a, b, k] for a, b, k in blocks],
        "names": names,
        "side_names": side_names,  # cluster id -> name
        "split_names": split_names,  # [left, right]
    }


# ----------------------------------------------------------------------------- naming (vision)


def _frame_jpg(src: Path, t: float, crop: str | None = None) -> bytes:
    vf = (crop + "," if crop else "") + "scale=640:-2"
    r = subprocess.run(
        [
            ffmpeg.ffmpeg_bin(),
            "-v",
            "error",
            "-ss",
            f"{t:.2f}",
            "-i",
            str(src),
            "-frames:v",
            "1",
            "-vf",
            vf,
            "-f",
            "image2",
            "-c:v",
            "mjpeg",
            "-",
        ],
        capture_output=True,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return r.stdout


def ask_which(src: Path, t: float, names: list[str], crop: str | None = None) -> str | None:
    if len(names) != 2 or not llm.status()["available"]:
        return None
    img = _frame_jpg(src, t, crop)
    if not img:
        return None
    q = (
        f"This frame comes from a video comparing {names[0]} and {names[1]}. Look at logos, badges, "
        f'text and style. Which one is shown? Reply JSON {{"answer": "{names[0]}" or "{names[1]}" or "unsure"}}'
    )
    try:
        ans = str(llm.vision_json(q, [img]).get("answer", ""))
    except Exception as e:  # noqa: BLE001
        log.info("vision naming failed: %s", e)
        return None
    for n in names:
        if n.lower() in ans.lower():
            return n
    return None


def _name_sides(src: Path, blocks: list[tuple[float, float, int]], names: list[str]) -> dict[str, str]:
    """Majority vote of the vision model over a few stretches per side; title order as fallback."""
    if len(names) != 2:
        return {"0": "A", "1": "B"}
    votes: dict[int, dict[str, int]] = {0: {}, 1: {}}
    for side in (0, 1):
        for a, b, _ in [x for x in blocks if x[2] == side][:3]:
            n = ask_which(src, (a + b) / 2, names)
            if n:
                votes[side][n] = votes[side].get(n, 0) + 1
    best = {s: max(v, key=v.get) if v else None for s, v in votes.items()}
    if best[0] and best[1] and best[0] != best[1]:
        return {"0": best[0], "1": best[1]}
    if best[0] and not best[1]:
        return {"0": best[0], "1": names[1] if best[0] == names[0] else names[0]}
    if best[1] and not best[0]:
        return {"1": best[1], "0": names[1] if best[1] == names[0] else names[0]}
    first = blocks[0][2]
    return {str(first): names[0], str(1 - first): names[1]}


def _name_split(src: Path, splits: list[tuple[float, float]], names: list[str]) -> list[str]:
    if len(names) != 2:
        return ["A", "B"]
    a, b = splits[0]
    left = ask_which(src, (a + b) / 2, names, crop="crop=iw/2:ih:0:0")
    right = ask_which(src, (a + b) / 2, names, crop="crop=iw/2:ih:iw/2:0")
    if left and right and left != right:
        return [left, right]
    if left:
        return [left, names[1] if left == names[0] else names[0]]
    if right:
        return [names[1] if right == names[0] else names[0], right]
    return list(names)


def describe(src: Path, t: float) -> str | None:
    """A few words about what happens in a frame (clip titles), from the local vision model."""
    if not llm.status()["available"]:
        return None
    img = _frame_jpg(src, t)
    try:
        d = llm.vision_json(
            'Describe what happens in this game/video frame in at most 6 words. JSON {"scene": "..."}', [img]
        )
        s = str(d.get("scene", "")).strip().strip(".")
        return s[:60] if len(s) >= 3 else None
    except Exception:  # noqa: BLE001
        return None


# ----------------------------------------------------------------------------- clips


def candidates(comp: dict, min_dur: float, max_dur: float, motion: np.ndarray | None = None) -> list[dict]:
    """Comparison clips: split-screen stretches and paired A/B stretches.

    Each item: {start, end, mode: compare|pair, b_start?, top, bottom, score}."""
    names = comp.get("names") or ["A", "B"]
    out: list[dict] = []
    sn = comp.get("split_names") or names
    # the version named first in the title goes on top, so every clip reads the same way
    swap = bool(names) and sn[1] == names[0]
    for a, b in comp.get("splits", []):
        a += 0.6  # skip the wipe into the split
        d = min(b - a, max_dur)
        if d >= max(4.0, min_dur * 0.4):
            out.append(
                {
                    "start": a,
                    "end": a + d,
                    "mode": "compare",
                    "swap": swap,
                    "top": sn[1] if swap else sn[0],
                    "bottom": sn[0] if swap else sn[1],
                }
            )
    blocks = comp.get("blocks", [])
    side = comp.get("side_names") or {}
    first_name = names[0] if names else None
    used: set[int] = set()
    for i, (a0, a1, ka) in enumerate(blocks):
        if i in used:
            continue
        # the neighbouring stretch of the other side shows the same scenario
        for j in (i + 1, i - 1):
            if 0 <= j < len(blocks) and j not in used and blocks[j][2] != ka:
                b0, b1, kb = blocks[j]
                d = min(a1 - a0, b1 - b0, max_dur) - 1.0
                if d < max(4.0, min_dur * 0.4):
                    continue
                top, bottom = (a0, ka), (b0, kb)
                # the side named first in the title goes on top
                if first_name and side.get(str(kb)) == first_name:
                    top, bottom = bottom, top
                out.append(
                    {
                        "start": round(top[0] + 0.6, 2),
                        "end": round(top[0] + 0.6 + d, 2),
                        "mode": "pair",
                        "b_start": round(bottom[0] + 0.6, 2),
                        "top": side.get(str(top[1]), "A"),
                        "bottom": side.get(str(bottom[1]), "B"),
                    }
                )
                used.update({i, j})
                break
    for c in out:
        dur = c["end"] - c["start"]
        mo = 0.0
        if motion is not None and len(motion):
            a, b = int(c["start"] * 2), max(int(c["end"] * 2), int(c["start"] * 2) + 1)
            mo = float(np.mean(motion[a:b])) / (float(np.mean(motion)) + 1e-6)
        sweet = 1.0 - min(1.0, abs(dur - 28) / 30)
        c["score"] = int(
            round(max(35, min(95, 55 + 15 * (mo - 1) + 15 * sweet + (5 if c["mode"] == "compare" else 0))))
        )
    return sorted(out, key=lambda c: -c["score"])
