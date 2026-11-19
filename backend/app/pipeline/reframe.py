"""Subject-aware reframing.

Samples the clip at 3 fps, finds faces with OpenCV's bundled Haar cascades (frontal +
profile, no downloads), falls back to the motion centroid, then turns the noisy
per-frame subject position into a calm "camera operator" path: hold still while the
subject stays inside a dead zone, pan smoothly when it leaves. Also detects two
stable, well-separated faces and proposes a stacked dual-speaker layout, and finds a
streamer's webcam overlay for the gameplay layout (facecam on top, game below).
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
        "facecam": detect_facecam(src, start, end),
        "src_w": W,
        "src_h": H,
    }


FACECAM_SAMPLES = 16
FACECAM_WIDTH = 960


def detect_facecam(src: Path, start: float, end: float, samples: int = FACECAM_SAMPLES) -> dict | None:
    """Find a streamer's webcam overlay: a small, live face that stays in the same place for much
    of the video, sitting on top of other content (gameplay, a shared screen).

    Returns {"box": [x, y, w, h] (0-1, source frame), "face": [cx, cy, size], "snapped": bool,
    "content_motion": float} or None. The box is snapped to the overlay's border when one is visible
    in the time-averaged frame (static borders stay sharp while the game behind them blurs out).
    """
    dur = max(0.5, end - start)
    fps = min(2.0, samples / dur)
    try:
        frames, _ = ffmpeg.read_frames(src, start, end, fps, FACECAM_WIDTH)
    except ffmpeg.MediaError:
        return None
    if len(frames) < 4:
        return None
    H, W = frames.shape[1:]
    min_side = max(20, H // 22)
    # cluster detections by position: each cluster is one face location over time
    clusters: list[dict] = []
    for i, fr in enumerate(frames):
        g = cv2.equalizeHist(fr)
        for x, y, w, h in _front.detectMultiScale(g, scaleFactor=1.1, minNeighbors=5, minSize=(min_side, min_side)):
            c = (x + w / 2, y + h / 2, float(w), float(h))
            for cl in clusters:
                m = cl["mean"]
                if abs(c[0] - m[0]) < W * 0.06 and abs(c[1] - m[1]) < H * 0.08 and 0.6 < c[3] / m[3] < 1.6:
                    cl["dets"].append(c)
                    cl["frames"].add(i)
                    cl["mean"] = np.median(np.array(cl["dets"]), axis=0)
                    break
            else:
                clusters.append({"dets": [c], "frames": {i}, "mean": np.array(c)})
    best = None
    for cl in clusters:
        cx, cy, fw, fh = (float(v) for v in cl["mean"])
        if len(cl["frames"]) < max(3, len(frames) * 0.3) or fh / H > 0.24:
            continue  # too rare, or a big face (talking head / podcast: normal reframing handles it)
        # A real person moves a little; faces in game art, posters or thumbnails don't.
        x0, y0 = int(max(0, cx - fw / 2)), int(max(0, cy - fh / 2))
        patch = frames[:, y0 : int(y0 + fh), x0 : int(x0 + fw)].astype(np.float32)
        live = float(patch.std(axis=0).mean()) if patch.size else 0.0
        if live < 3.0:
            continue
        score = len(cl["frames"]) * min(live, 12)
        if best is None or score > best[0]:
            best = (score, cx, cy, fw, fh)
    if best is None:
        return None
    _, cx, cy, fw, fh = best
    # Content elsewhere must change (gameplay / screen share), otherwise it's just a wide shot.
    mask = np.ones((H, W), bool)
    mask[int(max(0, cy - 2.5 * fh)) : int(min(H, cy + 3 * fh)), int(max(0, cx - 3 * fw)) : int(min(W, cx + 3 * fw))] = (
        False
    )
    diffs = [float(np.mean(cv2.absdiff(a, b)[mask])) for a, b in zip(frames, frames[1:], strict=False)]
    content_motion = float(np.median(diffs)) if diffs else 0.0

    box, snapped = _facecam_box(frames, cx, cy, fw, fh)
    x0, y0, x1, y1 = box
    return {
        "box": [round(x0 / W, 4), round(y0 / H, 4), round((x1 - x0) / W, 4), round((y1 - y0) / H, 4)],
        "face": [round(cx / W, 4), round(cy / H, 4), round(fh / H, 4)],
        "snapped": snapped,
        "content_motion": round(content_motion, 2),
    }


def _edge_peak(profile: np.ndarray, lo: int, hi: int, outward: int) -> int | None:
    """The border closest to the face in profile[lo:hi] that clearly stands out.

    ``outward`` is +1 when searching away from the face towards higher indices, -1 towards lower.
    Overlays are often followed by other static UI lines (menus, panels), so the nearest clear edge
    is the webcam frame, not necessarily the strongest one.
    """
    lo, hi = max(0, lo), min(len(profile), hi)
    if hi - lo < 3:
        return None
    seg = profile[lo:hi]
    base = float(np.median(seg)) + 1e-6
    strong = max(float(seg.max()) * 0.55, base * 2.4, 6.0)
    idx = range(len(seg)) if outward > 0 else range(len(seg) - 1, -1, -1)
    for i in idx:
        if seg[i] >= strong:
            # settle on the local maximum of this edge (edges are 2-3 px wide)
            j = i
            while 0 <= j + outward < len(seg) and seg[j + outward] > seg[j]:
                j += outward
            return lo + j
    return None


def _facecam_box(
    frames: np.ndarray, cx: float, cy: float, fw: float, fh: float
) -> tuple[tuple[int, int, int, int], bool]:
    H, W = frames.shape[1:]
    mean = frames.astype(np.float32).mean(axis=0)
    gx = np.abs(cv2.Sobel(mean, cv2.CV_32F, 1, 0, ksize=3))
    gy = np.abs(cv2.Sobel(mean, cv2.CV_32F, 0, 1, ksize=3))
    rows = slice(int(max(0, cy - 1.2 * fh)), int(min(H, cy + 1.8 * fh)))
    cols = slice(int(max(0, cx - 1.5 * fw)), int(min(W, cx + 1.5 * fw)))
    vprof = gx[rows].mean(axis=0)  # vertical borders, per column
    hprof = gy[:, cols].mean(axis=1)  # horizontal borders, per row
    left = _edge_peak(vprof, int(cx - 4.5 * fw), int(cx - 1.0 * fw), -1)
    right = _edge_peak(vprof, int(cx + 1.0 * fw), int(cx + 4.5 * fw), 1)
    top = _edge_peak(hprof, int(cy - 3.2 * fh), int(cy - 0.9 * fh), -1)
    bottom = _edge_peak(hprof, int(cy + 1.2 * fh), int(cy + 4.0 * fh), 1)
    # A frame edge is a border too: overlays usually sit in a corner.
    if left is None and cx - 4.5 * fw <= 0:
        left = 0
    if top is None and cy - 3.2 * fh <= 0:
        top = 0
    if right is None and cx + 4.5 * fw >= W:
        right = W
    if bottom is None and cy + 4.0 * fh >= H:
        bottom = H
    # Fill in missing sides with a webcam-shaped box around the face.
    x0 = left if left is not None else int(cx - 1.9 * fw)
    x1 = right if right is not None else int(cx + 1.9 * fw)
    y0 = top if top is not None else int(cy - 1.5 * fh)
    y1 = bottom if bottom is not None else int(cy + 1.9 * fh)
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
    snapped = sum(v is not None for v in (left, right, top, bottom)) >= 3
    # sanity: the box must comfortably contain the face and not be most of the frame
    if (x1 - x0) < 1.6 * fw or (y1 - y0) < 1.6 * fh or (x1 - x0) * (y1 - y0) > 0.45 * W * H:
        x0, x1 = int(max(0, cx - 1.9 * fw)), int(min(W, cx + 1.9 * fw))
        y0, y1 = int(max(0, cy - 1.5 * fh)), int(min(H, cy + 1.9 * fh))
        snapped = False
    return (x0, y0, x1, y1), snapped


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
