"""AI thumbnails for every clip.

1. Frame: candidate moments across the clip are rendered with the clip's own framing (crop,
   facecam / comparison layout), scored for sharpness, brightness and faces, and the local
   vision model picks the most eye-catching of the best few.
2. Text: the local LLM writes 2-5 punchy words (not a copy of the title); without it the clip's
   strongest key phrase is used.
3. Design: three looks (Bold, Pop, Clean) burned with libass in both sizes: 1080x1920 for
   Shorts / Reels / TikTok covers and 1280x720 for regular YouTube videos.
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

import cv2
import numpy as np

from . import captions as cap
from . import ffmpeg, llm, publish, reframe, render

log = logging.getLogger("hypesift.thumbnail")

DESIGNS = {
    "bold": {
        "label": "Bold",
        "font": "Anton",
        "size": 330,
        "color": "#FFFFFF",
        "accent": "#C6F432",
        "outline": 10,
        "box": False,
    },
    "pop": {
        "label": "Pop",
        "font": "Luckiest Guy",
        "size": 230,
        "color": "#FFE14D",
        "accent": "#FFFFFF",
        "outline": 12,
        "box": False,
        "tilt": -4,
    },
    "clean": {
        "label": "Clean",
        "font": "Poppins ExtraBold",
        "size": 175,
        "color": "#FFFFFF",
        "accent": "#C6F432",
        "outline": 0,
        "box": True,
    },
}
SIZES = {"vertical": (1080, 1920), "wide": (1280, 720)}

# font -> (libass size / em ratio, average uppercase glyph width in em) for fitting text to the frame
_FONT_METRICS = {"Anton": (1.733, 0.5), "Luckiest Guy": (1.226, 0.66), "Poppins ExtraBold": (1.762, 0.72)}

_GENERIC = {"the", "a", "an", "this", "that", "and", "or", "of", "to", "in"}


def _ffmpeg(args: list[str], cwd: Path | None = None) -> None:
    subprocess.run(
        args, check=True, capture_output=True, cwd=cwd, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )


def frame_chain(probe: ffmpeg.Probe, edits: dict, rf: dict, W: int, H: int) -> str:
    """The clip's own framing for a still (no captions); "pair" clips fall back to the top half."""
    e = render.merged_edits(edits)
    if e["crop"].get("mode") == "pair":
        e["crop"] = {**e["crop"], "mode": "center"}
    if W > H:  # the wide thumbnail shows the whole picture
        return f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1[vr]"
    return render.build_video_chain(probe, e, rf, W, H)


def grab(src: Path, probe: ffmpeg.Probe, t: float, edits: dict, rf: dict, size: tuple[int, int], out: Path) -> Path:
    W, H = size
    chain = frame_chain(probe, edits, rf, W, H)
    _ffmpeg(
        [
            ffmpeg.ffmpeg_bin(),
            "-y",
            "-v",
            "error",
            "-ss",
            f"{max(0.0, t):.3f}",
            "-i",
            str(src),
            "-filter_complex",
            chain,
            "-map",
            "[vr]",
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(out),
        ]
    )
    return out


def frame_quality(path: Path) -> float:
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return -1.0
    small = cv2.resize(img, (360, int(360 * img.shape[0] / img.shape[1])))
    sharp = float(cv2.Laplacian(small, cv2.CV_64F).var())
    bright = float(small.mean())
    faces = reframe._faces(small)
    face = max((w * h for *_, w, h in faces), default=0) / small.size
    s = np.log1p(sharp) * (0.4 if bright < 40 or bright > 225 else 1.0)
    return float(s + 6 * min(face, 0.15) + (0.8 if faces else 0))


def pick_frame(src: Path, probe: ffmpeg.Probe, start: float, end: float, edits: dict, rf: dict, work: Path) -> float:
    """Clip-relative moment for the thumbnail."""
    dur = max(0.5, end - start)
    times = [dur * f for f in (0.08, 0.22, 0.36, 0.5, 0.64, 0.78, 0.92)]
    scored = []
    for i, t in enumerate(times):
        p = grab(src, probe, start + t, edits, rf, (360, 640), work / f"cand{i}.jpg")
        scored.append((frame_quality(p), t, p))
    scored.sort(key=lambda x: -x[0])
    top = scored[:4]
    if llm.status()["available"] and len(top) > 1:
        try:
            ans = llm.vision_json(
                f"These are candidate thumbnail frames (numbered 1 to {len(top)} in order) for a short video. "
                "Pick the one that would make people most want to click: clear subject, a face with expression or "
                'a striking moment, not blurry. Reply JSON {"best": number}',
                [p.read_bytes() for _, _, p in top],
            )
            k = int(ans.get("best", 1)) - 1
            if 0 <= k < len(top):
                return top[k][1]
        except Exception as e:  # noqa: BLE001
            log.info("vision frame pick failed: %s", e)
    return top[0][1]


def thumb_text(title: str, text: str, allow_llm: bool = True) -> str:
    """2-5 punchy words for the thumbnail, uppercase."""
    if allow_llm and llm.status()["available"]:
        try:
            d = llm.chat_json(
                "You write YouTube thumbnail text. 2 to 5 words, punchy, creates curiosity, truthful to the clip, "
                "different from the title, no emojis, no hashtags. Reply JSON only.",
                f'Title: {title}\nWhat is said: """{text[:1200]}"""\nReturn {{"text": "...", "accent": "one word from text to highlight"}}',
                temperature=0.7,
                max_tokens=80,
            )
            t = re.sub(r"[#\"“”]", "", str(d.get("text", ""))).strip()
            if 1 <= len(t.split()) <= 6 and len(t) <= 40:
                return t.upper() + ("|" + str(d.get("accent", "")).upper() if d.get("accent") else "")
        except Exception as e:  # noqa: BLE001
            log.info("thumbnail text LLM failed: %s", e)
    kp = publish.keyphrases(text or title, 3)
    base = kp[0] if kp else title
    words = [w for w in re.findall(r"[A-Za-z0-9']+", base)][:4] or ["WATCH", "THIS"]
    return " ".join(words).upper()


def _bare(w: str) -> str:
    return re.sub(r"[^A-Z0-9']", "", w.upper())


def _ass(text: str, design: dict, W: int, H: int, face_y: float | None = None, face_x: float | None = None) -> str:
    text, _, accent = text.partition("|")
    words = text.split()
    acc = _bare(accent) or _bare(
        max(words, key=lambda w: (len(_bare(w)) if w.lower() not in _GENERIC else 0), default="")
    )
    k = W / 1080 if H > W else H / 1080
    size = int(design["size"] * k * (0.8 if len(text) > 18 else 1))
    col, acc_col = cap.ass_color(design["color"]), cap.ass_color(design["accent"])
    family = cap._ASS_FONT.get(design["font"], (design["font"], 0, 0))[0]
    border = 3 if design["box"] else 1
    outline = 22 * k if design["box"] else design["outline"] * k
    back = cap.ass_color("#0B0F14", 0.82) if design["box"] else cap.ass_color("#000000", 0.5)
    outline_col = cap.ass_color("#0B0F14", 0.82) if design["box"] else cap.ass_color("#000000")
    # put the words where the face isn't
    if H > W:
        if face_y is not None and face_y < 0.42:
            pos, align = (W // 2, int(H * 0.9)), 2  # face up top: text in the lower part
        else:
            pos, align = (W // 2, int(H * 0.08)), 8
        wrap_at = 2
    else:
        if face_x is not None and face_x < 0.5:
            pos, align = (int(W * 0.95), int(H * 0.5)), 6
        else:
            pos, align = (int(W * 0.05), int(H * 0.5)), 4
        wrap_at = 2
    lines, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= wrap_at:
            lines.append(cur)
            cur = []
    if cur:
        lines.append(cur)
    # shrink the text until the longest line fits the space available (no clipped words)
    em_ratio, char_w = _FONT_METRICS.get(design["font"], (1.6, 0.62))
    room = W * (0.9 if H > W else 0.5)
    longest = max(len(" ".join(ln)) for ln in lines) if lines else 1
    fit = room / (longest * (size / em_ratio) * char_w + 2 * outline)
    if fit < 1:
        size = int(size * fit)
        outline = outline * fit
    body = "\\N".join(
        " ".join(f"{{\\1c{acc_col}}}{cap._esc(w)}{{\\1c{col}}}" if _bare(w) == acc else cap._esc(w) for w in ln)
        for ln in lines
    )
    tilt = f"\\frz{design.get('tilt', 0)}" if design.get("tilt") else ""
    return (
        "\n".join(
            [
                "[Script Info]",
                "ScriptType: v4.00+",
                f"PlayResX: {W}",
                f"PlayResY: {H}",
                "WrapStyle: 2",
                "ScaledBorderAndShadow: yes",
                "",
                "[V4+ Styles]",
                "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
                "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
                "MarginR, MarginV, Encoding",
                f"Style: T,{family},{size},{col},{col},{outline_col},{back},0,0,0,0,100,100,0,0,{border},{outline:.1f},"
                f"{0 if design['box'] else 6 * k:.1f},{align},0,0,0,1",
                "",
                "[Events]",
                "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
                f"Dialogue: 0,0:00:00.00,0:00:05.00,T,,0,0,0,,{{\\an{align}\\pos({pos[0]},{pos[1]}){tilt}}}{body}",
            ]
        )
        + "\n"
    )


def face_center(frame: Path) -> tuple[float, float] | None:
    img = cv2.imread(str(frame), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    small = cv2.resize(img, (360, int(360 * img.shape[0] / img.shape[1])))
    faces = reframe._faces(small)
    if not faces:
        return None
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    return (x + w / 2) / small.shape[1], (y + h / 2) / small.shape[0]


def compose(frame: Path, text: str, design_key: str, size: tuple[int, int], out: Path, work: Path) -> Path:
    """Burn the text design onto a frame (with a soft shade behind the text for contrast)."""
    W, H = size
    design = DESIGNS[design_key]
    face = face_center(frame)
    ass = work / f"t_{design_key}_{W}.ass"
    ass.write_text(_ass(text, design, W, H, face[1] if face else None, face[0] if face else None), encoding="utf-8")
    fonts = render._fonts_rel(work)
    if H > W:
        low = face is not None and face[1] < 0.42
        y0 = int(H * 0.55) if low else 0
        shade = f"drawbox=x=0:y={y0}:w={W}:h={int(H * 0.45)}:color=black@0.3:t=fill"
    else:
        right = face is not None and face[0] < 0.5
        shade = f"drawbox=x={int(W * 0.45) if right else 0}:y=0:w={int(W * 0.55)}:h={H}:color=black@0.32:t=fill"
    vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},eq=saturation=1.18:contrast=1.06,{shade},ass=filename={ass.name}:fontsdir='{fonts}'"
    _ffmpeg(
        [
            ffmpeg.ffmpeg_bin(),
            "-y",
            "-v",
            "error",
            "-i",
            str(frame),
            "-vf",
            vf,
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(out),
        ],
        cwd=work,
    )
    return out


def make_thumbnails(
    src: Path,
    probe: ffmpeg.Probe,
    start: float,
    end: float,
    edits: dict,
    rf: dict,
    title: str,
    text: str,
    out_dir: Path,
    work: Path,
    custom_text: str | None = None,
    allow_llm: bool = True,
) -> dict:
    """Returns {"text": ..., "t": ..., "files": {design: {vertical: path, wide: path}}}."""
    work.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    t = pick_frame(src, probe, start, end, edits, rf, work)
    words = (custom_text.strip().upper() if custom_text else None) or thumb_text(title, text, allow_llm)
    files: dict[str, dict[str, Path]] = {}
    for size_key, size in SIZES.items():
        frame = grab(src, probe, start + t, edits, rf, size, work / f"frame_{size_key}.jpg")
        for d in DESIGNS:
            files.setdefault(d, {})[size_key] = compose(
                frame, words, d, size, out_dir / f"thumb-{d}-{size_key}.jpg", work
            )
    return {"text": words.split("|")[0], "t": round(t, 2), "files": files}
