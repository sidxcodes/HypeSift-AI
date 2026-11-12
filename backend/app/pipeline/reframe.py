"""Subject-aware reframing.

Samples the clip at 3 fps, finds faces with OpenCV's bundled Haar cascades (frontal +
profile, no downloads), falls back to the motion centroid, then turns the noisy
per-frame subject position into a calm "camera operator" path: hold still while the
subject stays inside a dead zone, pan smoothly when it leaves. Also detects two
stable, well-separated faces and proposes a stacked dual-speaker layout.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from . import ffmpeg

SAMPLE_FPS = 3.0
ASPECTS = {"9:16": (1080, 1920), "1:1": (1080, 1080), "4:5": (1080, 1350), "16:9": (1920, 1080)}

_front = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
_profile = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_profileface.xml")


def _faces(gray: np.ndarray) -> list[tuple[int, int, int, int]]:
    g = cv2.equalizeHist(gray)
    min_side = max(24, gray.shape[0] // 14)
    f = list(_front.detectMultiScale(g, scaleFactor=1.15, minNeighbors=6, minSize=(min_side, min_side)))
    if not f:
        f = list(_profile.detectMultiScale(g, scaleFactor=1.15, minNeighbors=6, minSize=(min_side, min_side)))
        if not f:
            flipped = cv2.flip(g, 1)
            w = g.shape[1]
            f = [
                (w - x - fw, y, fw, fh)
                for (x, y, fw, fh) in _profile.detectMultiScale(
                    flipped, scaleFactor=1.15, minNeighbors=6, minSize=(min_side, min_side)
                )
            ]
    return [tuple(int(v) for v in r) for r in f]


def analyze(src: Path, start: float, end: float) -> dict:
    frames, _ = ffmpeg.read_frames(src, start, end, SAMPLE_FPS, 480)
    n = len(frames)
    if n == 0:
        return {"source": "center", "path": [[0.0, 0.5, 0.5]], "face_ratio": 0.0, "split": None}
    H, W = frames.shape[1:]
    xs: list[float | None] = []
    ys: list[float | None] = []
    all_faces: list[list[tuple[float, float, float]]] = []
    hits = 0
    prev = None
    for i, fr in enumerate(frames):
        faces = _faces(fr)
        norm = [((x + w / 2) / W, (y + h / 2) / H, w * h / (W * H)) for x, y, w, h in faces]
        all_faces.append(norm)
        if norm:
            hits += 1
            # prefer the biggest face, but stick with the previous subject when sizes are close
            norm.sort(key=lambda f: -f[2])
            pick = norm[0]
            if prev is not None and len(norm) > 1:
                close = [f for f in norm if f[2] > norm[0][2] * 0.6]
                pick = min(close, key=lambda f: abs(f[0] - prev))
            xs.append(pick[0])
            ys.append(pick[1])
            prev = pick[0]
        else:
            xs.append(None)
            ys.append(None)
            if i > 0:
                d = cv2.absdiff(fr, frames[i - 1])
                m = cv2.moments(cv2.threshold(d, 25, 255, cv2.THRESH_BINARY)[1], binaryImage=True)
                if m["m00"] > W * H * 0.01:
                    xs[-1] = m["m10"] / m["m00"] / W
                    ys[-1] = m["m01"] / m["m00"] / H
    face_ratio = hits / n
    source = "faces" if face_ratio >= 0.3 else ("motion" if any(x is not None for x in xs) else "center")
    cx = _fill(xs)
    cy = _fill(ys)
    path = _operator_path(cx, cy, 1 / SAMPLE_FPS)
    return {
        "source": source,
        "path": path,
        "face_ratio": round(face_ratio, 2),
        "split": _split_layout(all_faces),
        "src_w": W,
        "src_h": H,
    }


def _fill(vals: list[float | None]) -> np.ndarray:
    arr = np.array([np.nan if v is None else v for v in vals], dtype=float)
    if np.all(np.isnan(arr)):
        return np.full(len(arr), 0.5)
    idx = np.arange(len(arr))
    good = ~np.isnan(arr)
    arr = np.interp(idx, idx[good], arr[good])
    # median filter (k=5) to kill detector jitter
    k = 5
    pad = np.pad(arr, (k // 2, k // 2), mode="edge")
    return np.array([np.median(pad[i : i + k]) for i in range(len(arr))])


def _operator_path(
    cx: np.ndarray, cy: np.ndarray, dt: float, dead: float = 0.07, pan: float = 0.6
) -> list[list[float]]:
    """Keyframes [t, cx, cy] with holds + linear pans (renders as a piecewise-linear crop)."""
    if len(cx) == 0:
        return [[0.0, 0.5, 0.5]]
    keys = [[0.0, round(float(cx[0]), 4), round(float(cy[0]), 4)]]
    hold_x, hold_y = float(cx[0]), float(cy[0])
    i = 1
    while i < len(cx):
        if abs(cx[i] - hold_x) > dead or abs(cy[i] - hold_y) > dead * 1.6:
            t0 = i * dt
            # target = median of the next second (where the subject settles)
            j = min(len(cx), i + int(1 / dt))
            tx, ty = float(np.median(cx[i:j])), float(np.median(cy[i:j]))
            keys.append([round(t0, 3), round(hold_x, 4), round(hold_y, 4)])
            keys.append([round(t0 + pan, 3), round(tx, 4), round(ty, 4)])
            hold_x, hold_y = tx, ty
            i = int((t0 + pan) / dt) + 1
            continue
        i += 1
    # collapse to at most 40 keyframes to keep the ffmpeg expression small
    if len(keys) > 40:
        step = len(keys) / 40
        keys = [keys[int(k * step)] for k in range(40)]
    return keys


def _split_layout(all_faces: list[list[tuple[float, float, float]]]) -> dict | None:
    pts = [f[0] for fs in all_faces for f in fs if f[2] > 0.004]
    if len(pts) < max(6, len(all_faces) * 0.6):
        return None
    pts_arr = np.array(sorted(pts))
    # 2-means in 1-D
    a, b = float(np.percentile(pts_arr, 20)), float(np.percentile(pts_arr, 80))
    for _ in range(10):
        left = pts_arr[np.abs(pts_arr - a) <= np.abs(pts_arr - b)]
        right = pts_arr[np.abs(pts_arr - a) > np.abs(pts_arr - b)]
        if len(left) == 0 or len(right) == 0:
            return None
        a, b = float(left.mean()), float(right.mean())
    frames_both = sum(
        1 for fs in all_faces if any(abs(f[0] - a) < 0.12 for f in fs) and any(abs(f[0] - b) < 0.12 for f in fs)
    )
    if b - a > 0.3 and min(len(left), len(right)) >= len(pts_arr) * 0.25 and frames_both >= len(all_faces) * 0.2:
        return {"left": round(a, 4), "right": round(b, 4)}
    return None


# ----------------------------------------------------------------------------- geometry


def crop_box(src_w: int, src_h: int, aspect: str, zoom: float = 1.0) -> tuple[int, int]:
    tw, th = ASPECTS.get(aspect, ASPECTS["9:16"])
    target = tw / th
    if src_w / src_h > target:
        ch = src_h / zoom
        cw = ch * target
    else:
        cw = src_w / zoom
        ch = cw / target
    return int(cw // 2 * 2), int(ch // 2 * 2)


def piecewise_expr(keys: list[list[float]], idx: int, src_len: int, crop_len: int) -> str:
    """ffmpeg expression for the crop x (idx=1) or y (idx=2) offset over time ``t``."""
    span = src_len - crop_len
    if span <= 0:
        return "0"

    def pos(v: float) -> float:
        return round(min(max(v * src_len - crop_len / 2, 0), span), 1)

    pts = [(k[0], pos(k[idx])) for k in keys]
    if len(pts) == 1 or all(abs(p[1] - pts[0][1]) < 0.5 for p in pts):
        return str(pts[0][1])
    expr = str(pts[-1][1])
    for (t0, v0), (t1, v1) in reversed(list(zip(pts, pts[1:], strict=False))):
        if t1 - t0 <= 1e-3 or abs(v1 - v0) < 0.5:
            seg = str(v0)
        else:
            seg = f"{v0}+({v1 - v0})*(t-{t0})/{t1 - t0:.3f}"
        expr = f"if(lt(t,{t1}),{seg},{expr})"
    return f"if(lt(t,{pts[0][0]}),{pts[0][1]},{expr})"
