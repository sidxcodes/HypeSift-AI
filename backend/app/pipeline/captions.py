"""Caption chunking, style presets, ASS (burn-in) and SRT generation.

The same preset table is served to the browser (``/api/meta``) so the editor's live
preview uses identical fonts, sizes, colours and timing to the exported video.
Sizes are defined for a 1080-px-wide frame and scaled to the output.

A caption look is three independent choices:
  * style      - font, colours, outline/box, word animation (``PRESETS``)
  * transition - how each new line enters (``TRANSITIONS``)
  * effect     - an extra treatment on top (``EFFECTS``)
"""

from __future__ import annotations

import copy
import re
from typing import Any

# display name -> font file (all free: SIL OFL / Apache 2.0, licences next to the files)
FONT_FILES = {
    "Poppins Medium": "Poppins-Medium.ttf",
    "Poppins SemiBold": "Poppins-SemiBold.ttf",
    "Poppins ExtraBold": "Poppins-ExtraBold.ttf",
    "Anton": "Anton-Regular.ttf",
    "Bebas Neue": "BebasNeue-Regular.ttf",
    "Bangers": "Bangers-Regular.ttf",
    "DM Serif Display": "DMSerifDisplay-Regular.ttf",
    "DM Serif Display Italic": "DMSerifDisplay-Italic.ttf",
    "Archivo Black": "ArchivoBlack-Regular.ttf",
    "Permanent Marker": "PermanentMarker-Regular.ttf",
    "Luckiest Guy": "LuckiestGuy-Regular.ttf",
    "Bungee": "Bungee-Regular.ttf",
    "Courier Prime": "CourierPrime-Bold.ttf",
}

# display name -> (family name inside the file, bold flag, italic flag) for libass
_ASS_FONT = {
    "DM Serif Display Italic": ("DM Serif Display", 0, 1),
    "Courier Prime": ("Courier Prime", 1, 0),
}

_BASE: dict[str, Any] = {
    "label": "",
    "font": "Poppins ExtraBold",
    "size": 80,
    "color": "#FFFFFF",
    "highlight": "#FFE14D",
    "outline": 5,
    "outline_color": "#000000",
    "shadow": 0,
    "box": False,
    "box_color": "#000000",
    "box_opacity": 0.0,
    "uppercase": False,
    "max_words": 3,
    "position": "lower",
    "animation": "highlight",  # none | pop | highlight | fade | karaoke
    "emphasis": False,
    "emphasis_color": "#FFE14D",
    "glow": 0,  # blurred halo radius (0 = off)
    "glow_color": "#000000",
    "opacity": 1.0,
}


def _p(**kw: Any) -> dict[str, Any]:
    return {**_BASE, **kw}


# Order = order in the style picker. The first six keys predate the picker redesign and stay
# valid for clips made earlier.
PRESETS: dict[str, dict[str, Any]] = {
    "basic": _p(
        label="Basic",
        font="Poppins SemiBold",
        size=62,
        highlight="#FFFFFF",
        outline=0,
        box=True,
        box_opacity=0.62,
        max_words=5,
        animation="none",
    ),
    "modern": _p(
        label="Modern",
        font="Archivo Black",
        size=72,
        highlight="#C4B5FD",
        outline=0,
        shadow=4,
        max_words=3,
        animation="highlight",
    ),
    "scribble": _p(
        label="Scribble",
        font="Permanent Marker",
        size=86,
        highlight="#FFE14D",
        outline=5,
        max_words=3,
        animation="pop",
    ),
    "funky": _p(
        label="Funky",
        font="Luckiest Guy",
        size=94,
        highlight="#FF4FD8",
        outline=7,
        outline_color="#2B0B3F",
        uppercase=True,
        max_words=2,
        animation="pop",
        emphasis_color="#7CFF4F",
    ),
    "spotlight": _p(
        label="Spotlight",
        font="Poppins ExtraBold",
        size=70,
        color="#A1A1AA",
        highlight="#FFFFFF",
        outline=0,
        box=True,
        box_color="#0B0B10",
        box_opacity=0.78,
        max_words=4,
        animation="highlight",
    ),
    "classic": _p(
        label="Classic",
        font="Poppins ExtraBold",
        size=86,
        color="#FDE047",
        highlight="#FFFFFF",
        outline=6,
        shadow=2,
        max_words=3,
        animation="pop",
    ),
    "heat": _p(
        label="Heat",
        font="Anton",
        size=104,
        highlight="#FF7A1A",
        outline=6,
        outline_color="#3A0A00",
        uppercase=True,
        max_words=2,
        animation="pop",
        glow=10,
        glow_color="#FF5A00",
    ),
    "icy": _p(
        label="Icy",
        font="Archivo Black",
        size=78,
        color="#E6FAFF",
        highlight="#22D3EE",
        outline=3,
        outline_color="#0B4A6F",
        uppercase=True,
        animation="highlight",
        glow=10,
        glow_color="#22D3EE",
    ),
    "ghost": _p(
        label="Ghost",
        font="Poppins SemiBold",
        size=66,
        highlight="#FFFFFF",
        outline=0,
        shadow=3,
        max_words=4,
        animation="fade",
        opacity=0.82,
    ),
    "editorial": _p(
        label="Editorial",
        font="DM Serif Display",
        size=78,
        highlight="#FDE68A",
        outline=0,
        shadow=3,
        max_words=5,
        animation="highlight",
    ),
    "tallboy": _p(
        label="Tallboy",
        font="Bebas Neue",
        size=132,
        highlight="#4ADE80",
        outline=5,
        uppercase=True,
        animation="highlight",
    ),
    "elegant": _p(
        label="Elegant",
        font="DM Serif Display Italic",
        size=74,
        color="#F7F1E6",
        highlight="#F7F1E6",
        outline=0,
        shadow=2,
        max_words=6,
        animation="fade",
    ),
    "bold_creator": _p(
        label="Punch",
        font="Poppins ExtraBold",
        size=90,
        outline=6,
        shadow=2,
        uppercase=True,
        animation="pop",
        emphasis=True,
    ),
    "clean_minimal": _p(
        label="Clean",
        font="Poppins Medium",
        size=58,
        highlight="#FFFFFF",
        outline=0,
        box=True,
        box_opacity=0.55,
        max_words=6,
        position="bottom",
        animation="none",
        emphasis_color="#C4B5FD",
    ),
    "roundtable": _p(
        label="Roundtable",
        font="Poppins SemiBold",
        size=60,
        color="#111827",
        highlight="#7C3AED",
        outline=0,
        box=True,
        box_color="#FFFFFF",
        box_opacity=0.94,
        max_words=5,
        animation="highlight",
        emphasis_color="#7C3AED",
    ),
    "matrix": _p(
        label="Matrix",
        font="Courier Prime",
        size=74,
        color="#39FF14",
        highlight="#D9FFD0",
        outline=3,
        outline_color="#001A00",
        uppercase=True,
        animation="highlight",
        glow=8,
        glow_color="#16A34A",
    ),
    "bubbly": _p(
        label="Bubbly",
        font="Luckiest Guy",
        size=96,
        color="#FF3E9A",
        highlight="#FFE14D",
        outline=7,
        outline_color="#FFFFFF",
        shadow=4,
        max_words=2,
        animation="pop",
    ),
    "mint": _p(
        label="Mint",
        font="Bungee",
        size=118,
        color="#6EE7B7",
        highlight="#FFFFFF",
        outline=6,
        outline_color="#064E3B",
        uppercase=True,
        max_words=2,
        animation="pop",
    ),
    "karaoke": _p(
        label="Karaoke",
        font="Poppins ExtraBold",
        size=76,
        highlight="#22D3EE",
        outline=5,
        uppercase=True,
        max_words=4,
        animation="karaoke",
        emphasis_color="#22D3EE",
    ),
    "gaming_energy": _p(
        label="Arcade",
        font="Bangers",
        size=104,
        highlight="#7CFF4F",
        outline=7,
        outline_color="#0B0B12",
        shadow=3,
        uppercase=True,
        max_words=2,
        animation="pop",
        emphasis=True,
        emphasis_color="#FF4FD8",
    ),
    "podcast": _p(
        label="Podcast",
        font="Poppins SemiBold",
        size=66,
        highlight="#A78BFA",
        outline=4,
        outline_color="#111111",
        max_words=4,
        animation="highlight",
        emphasis_color="#A78BFA",
    ),
    "cinematic": _p(
        label="Cinematic",
        font="DM Serif Display",
        size=64,
        color="#F5EBDD",
        highlight="#F5EBDD",
        outline=0,
        shadow=3,
        max_words=7,
        position="bottom",
        animation="fade",
        emphasis_color="#E8C07D",
    ),
}

TRANSITIONS = {
    "none": "None",
    "fade_up": "Fade Up",
    "fade_down": "Fade Down",
    "fade_left": "Fade Left",
    "fade_right": "Fade Right",
    "bounce": "Bounce",
}

EFFECTS = {
    "none": "None",
    "glow": "Glow",
    "shadow3d": "3D shadow",
    "typewriter": "Typewriter",
    "tilt": "Tilt",
}

POSITIONS = {"top": (8, 0.12), "middle": (5, 0.0), "lower": (2, 0.24), "bottom": (2, 0.12)}


def style_for(edits_captions: dict[str, Any] | None) -> dict[str, Any]:
    ec = edits_captions or {}
    base = copy.deepcopy(PRESETS.get(ec.get("preset", "bold_creator"), PRESETS["bold_creator"]))
    for k, v in (ec.get("style") or {}).items():
        if k == "size_scale" and v:
            base["size"] = int(base["size"] * max(0.5, min(2.0, float(v))))
        elif k in base and v is not None:
            base[k] = v
    base["transition"] = ec.get("transition") if ec.get("transition") in TRANSITIONS else "none"
    base["effect"] = ec.get("effect") if ec.get("effect") in EFFECTS else "none"
    return base


# ----------------------------------------------------------------------------- chunking


def chunk_words(words: list[dict], max_words: int = 3, max_chars: int = 28, max_gap: float = 0.55) -> list[dict]:
    """words: [{w,s,e}] with times relative to the clip. Returns caption chunks."""
    chunks: list[dict] = []
    cur: list[dict] = []

    def flush() -> None:
        if cur:
            chunks.append(
                {
                    "s": cur[0]["s"],
                    "e": cur[-1]["e"],
                    "text": " ".join(x["w"] for x in cur),
                    "words": [dict(x) for x in cur],
                }
            )
            cur.clear()

    for w in words:
        if cur:
            gap = w["s"] - cur[-1]["e"]
            chars = sum(len(x["w"]) + 1 for x in cur) + len(w["w"])
            if len(cur) >= max_words or chars > max_chars or gap > max_gap or re.search(r"[.?!]$", cur[-1]["w"]):
                flush()
        cur.append(w)
    flush()
    # close tiny gaps so captions don't flicker between chunks
    for a, b in zip(chunks, chunks[1:], strict=False):
        if 0 < b["s"] - a["e"] < 0.35:
            a["e"] = b["s"]
    return chunks


def retime_chunk(chunk: dict) -> dict:
    """After a text edit, spread word timings evenly across the chunk span."""
    parts = chunk["text"].split()
    if [w["w"] for w in chunk.get("words", [])] == parts:
        return chunk
    s, e = chunk["s"], chunk["e"]
    total = sum(len(p) for p in parts) or 1
    t = s
    words = []
    for p in parts:
        d = (e - s) * len(p) / total
        words.append({"w": p, "s": round(t, 3), "e": round(t + d, 3)})
        t += d
    return {**chunk, "words": words}


# ----------------------------------------------------------------------------- ASS


def ass_color(hex_color: str, opacity: float = 1.0) -> str:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = h[0:2], h[2:4], h[4:6]
    a = f"{int(round((1 - max(0.0, min(1.0, opacity))) * 255)):02X}"
    return f"&H{a}{b}{g}{r}".upper()


def _alpha(opacity: float) -> str:
    return f"&H{int(round((1 - max(0.0, min(1.0, opacity))) * 255)):02X}&"


def ts(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", " ")


def build_ass(
    width: int,
    height: int,
    chunks: list[dict],
    style: dict[str, Any] | None,
    overlays: list[dict] | None = None,
    keywords: set[str] | None = None,
    duration: float | None = None,
    progress_bar: str | None = None,
) -> str:
    """Return a complete ASS document. ``style`` None disables captions (overlays only).
    ``progress_bar`` is a hex colour for a bar that fills along the bottom edge (None = off)."""
    k = width / 1080
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "YCbCr Matrix: TV.709",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
        "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding",
    ]
    events: list[str] = []
    if style:
        align, mfrac = POSITIONS.get(style["position"], POSITIONS["bottom"])
        margin_v = int(height * mfrac)
        size = int(style["size"] * k)
        if style["animation"] == "karaoke":
            primary, secondary = ass_color(style["highlight"]), ass_color(style["color"])
        else:
            primary, secondary = ass_color(style["color"]), ass_color(style["highlight"])
        border_style = 3 if style["box"] else 1
        outline = max(6, int(size * 0.18)) if style["box"] else style["outline"] * k
        back = ass_color(style["box_color"], style["box_opacity"]) if style["box"] else ass_color("#000000", 0.6)
        out_col = (
            ass_color(style["box_color"], style["box_opacity"]) if style["box"] else ass_color(style["outline_color"])
        )
        family, bold, italic = _ASS_FONT.get(style["font"], (style["font"], 0, 0))
        lines.append(
            f"Style: Cap,{family},{size},{primary},{secondary},{out_col},{back},{bold},{italic},0,0,100,100,0,0,"
            f"{border_style},{outline:.1f},{style['shadow'] * k:.1f},{align},{int(70 * k)},{int(70 * k)},{margin_v},1"
        )
        anchor = (width // 2, {8: margin_v, 5: height // 2}.get(align, height - margin_v), align)
        events += _caption_events(chunks, style, keywords or set(), k, anchor)
    lines.append(
        f"Style: Over,Poppins ExtraBold,{int(64 * k)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,"
        f"100,100,0,0,3,{14 * k:.1f},0,8,{int(80 * k)},{int(80 * k)},{int(height * 0.07)},1"
    )
    lines.append(
        f"Style: Mark,Poppins SemiBold,{int(34 * k)},&H59FFFFFF,&H59FFFFFF,&H80000000,&H00000000,0,0,0,0,"
        f"100,100,0,0,1,{1.5 * k:.1f},0,9,{int(40 * k)},{int(40 * k)},{int(40 * k)},1"
    )
    lines.append(
        "Style: Bar,Poppins Medium,10,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1"
    )
    for ov in overlays or []:
        text = _esc(str(ov.get("text", "")).strip())
        if not text:
            continue
        s = float(ov.get("start", 0))
        e = float(ov.get("end", duration or 9999))
        if ov.get("kind") == "watermark":
            events.append(f"Dialogue: 2,{ts(s)},{ts(e)},Mark,,0,0,0,,{text}")
        else:
            col = ass_color(ov.get("color", "#FFFFFF"))
            bg = ass_color(ov.get("bg", "#7C3AED"), 0.92)
            events.append(f"Dialogue: 1,{ts(s)},{ts(e)},Over,,0,0,0,,{{\\1c{col}\\3c{bg}\\fad(200,200)}}{text}")
    if progress_bar and duration:
        # A full-width rectangle revealed left to right by an animated clip: a retention bar.
        bh = max(4, int(10 * k))
        y0 = height - bh
        col = ass_color(progress_bar)
        ms = int(duration * 1000)
        events.append(
            f"Dialogue: 3,{ts(0)},{ts(duration)},Bar,,0,0,0,,"
            f"{{\\pos(0,{y0})\\1c{col}\\bord0\\shad0\\clip(0,{y0},1,{height})\\t(0,{ms},\\clip(0,{y0},{width},{height}))\\p1}}"
            f"m 0 0 l {width} 0 {width} {bh} 0 {bh}{{\\p0}}"
        )
    lines += ["", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    lines += events
    return "\n".join(lines) + "\n"


def _word_text(w: str, style: dict, keywords: set[str]) -> tuple[str, bool]:
    t = w.upper() if style["uppercase"] else w
    is_kw = style.get("emphasis") and re.sub(r"[^a-z0-9]", "", w.lower()) in keywords
    return _esc(t), bool(is_kw)


def _enter(style: dict, k: float, anchor: tuple[int, int, int], first: bool, ci: int) -> str:
    """Override tags that open an event: entrance transition (first event of a chunk), effects."""
    x, y, align = anchor
    tags = f"\\an{align}"
    tr = style.get("transition", "none")
    d = int(46 * k)
    if first and tr.startswith("fade_"):
        dx, dy = {"fade_up": (0, d), "fade_down": (0, -d), "fade_left": (d, 0), "fade_right": (-d, 0)}[tr]
        tags += f"\\move({x + dx},{y + dy},{x},{y},0,170)\\fad(170,0)"
    else:
        tags += f"\\pos({x},{y})"
        if first and tr == "bounce":
            tags += "\\fscx55\\fscy55\\t(0,120,\\fscx114\\fscy114)\\t(120,220,\\fscx100\\fscy100)"
    eff = style.get("effect", "none")
    if eff == "shadow3d":
        tags += f"\\shad{max(3, int(7 * k))}\\4c{ass_color(style['highlight'] if style['highlight'] != style['color'] else '#7C3AED')}\\4a&H00&"
    elif eff == "tilt":
        tags += f"\\frz{(-3, 2.5, -2, 3)[ci % 4]}"
    if style.get("opacity", 1.0) < 1:
        tags += f"\\1a{_alpha(style['opacity'])}"
    return "{" + tags + "}"


def _glow_layer(text_tags: str, style: dict, k: float) -> str:
    """Same text drawn behind, fill hidden, thick blurred border: a soft halo."""
    radius = style.get("glow") or 10
    col = ass_color(style.get("glow_color") if style.get("glow") else style["highlight"])
    return (
        f"{{\\1a&HFF&\\3c{col}\\bord{(style['outline'] + radius * 0.7) * k:.1f}\\blur{radius * k:.1f}\\shad0}}"
        + text_tags
    )


def _caption_events(
    chunks: list[dict], style: dict, keywords: set[str], k: float = 1.0, anchor: tuple[int, int, int] = (540, 1460, 2)
) -> list[str]:
    ev: list[str] = []
    anim = style["animation"]
    hi = ass_color(style["highlight"])
    emph = ass_color(style.get("emphasis_color", style["highlight"]))
    base = ass_color(style["color"])
    eff = style.get("effect", "none")
    glow = eff == "glow" or bool(style.get("glow"))
    hidden = "{\\alpha&HFF&}"

    def emit(s: float, e: float, body: str, first: bool, ci: int) -> None:
        head = _enter(style, k, anchor, first, ci)
        if glow and not style["box"]:
            ev.append(f"Dialogue: 0,{ts(s)},{ts(e)},Cap,,0,0,0,,{head}{_glow_layer(body, style, k)}")
        ev.append(f"Dialogue: 1,{ts(s)},{ts(e)},Cap,,0,0,0,,{head}{body}")

    for ci, ch in enumerate(chunks):
        words = ch.get("words") or []
        if not words:
            continue
        s, e = ch["s"], max(ch["e"], ch["s"] + 0.2)
        if anim == "karaoke" and eff != "typewriter":
            parts = []
            for i, w in enumerate(words):
                nxt = words[i + 1]["s"] if i + 1 < len(words) else e
                dur_cs = max(1, int(round((nxt - w["s"]) * 100)))
                txt, _ = _word_text(w["w"], style, keywords)
                parts.append(f"{{\\kf{dur_cs}}}{txt}")
            lead = max(0, int(round((words[0]["s"] - s) * 100)))
            emit(s, e, f"{{\\k{lead}}}" + " ".join(parts), True, ci)
        elif anim in ("highlight", "pop", "karaoke") or eff == "typewriter":
            # one event per active word: chunk laid out in full, active word coloured (and popped);
            # typewriter hides the words that haven't been spoken yet (keeps the layout steady)
            first = True
            for i, w in enumerate(words):
                ws = s if i == 0 else w["s"]
                we = words[i + 1]["s"] if i + 1 < len(words) else e
                if we - ws <= 0.01:
                    continue
                parts = []
                for j, x in enumerate(words):
                    txt, kw = _word_text(x["w"], style, keywords)
                    if eff == "typewriter" and j > i:
                        parts.append(f"{hidden}{txt}")
                    elif j == i and anim in ("highlight", "pop", "karaoke"):
                        pop = "\\fscx112\\fscy112" if anim == "pop" else ""
                        parts.append(f"{{\\1c{hi}{pop}}}{txt}{{\\1c{base}\\fscx100\\fscy100}}")
                    elif kw:
                        parts.append(f"{{\\1c{emph}}}{txt}{{\\1c{base}}}")
                    else:
                        parts.append(txt)
                emit(ws, we, " ".join(parts), first, ci)
                first = False
        else:
            parts = []
            for x in words:
                txt, kw = _word_text(x["w"], style, keywords)
                parts.append(f"{{\\1c{emph}}}{txt}{{\\1c{base}}}" if kw else txt)
            fade = "{\\fad(180,180)}" if anim == "fade" else ""
            emit(s, e, fade + " ".join(parts), True, ci)
    return ev


# ----------------------------------------------------------------------------- SRT


def build_srt(chunks: list[dict], uppercase: bool = False) -> str:
    def t(x: float) -> str:
        x = max(0.0, x)
        ms = int(round(x * 1000))
        return f"{ms // 3600000:02d}:{ms % 3600000 // 60000:02d}:{ms % 60000 // 1000:02d},{ms % 1000:03d}"

    out = []
    for i, c in enumerate(chunks, 1):
        text = c["text"].upper() if uppercase else c["text"]
        out.append(f"{i}\n{t(c['s'])} --> {t(max(c['e'], c['s'] + 0.2))}\n{text}\n")
    return "\n".join(out)
