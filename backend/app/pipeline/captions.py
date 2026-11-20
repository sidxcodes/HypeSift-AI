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
    "shadow_color": "#000000",
    "letter_spacing": 0,  # px at 1080 wide
    "rotation": 0,  # degrees, + = clockwise
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

# Hook title designs (first ~3 s of every clip). A design is just a set of defaults: every field
# below can be overridden per title from the editor (Canva-style), and the browser preview uses the
# same rules (frontend/src/lib/title.ts) so what you see is what gets exported.
TITLE_STYLES = {
    "impact": "Impact pop",  # chunky comic font, coloured key words, thick outline, pops in
    "box": "Bold box",  # brand-colour box, black text, slight tilt, slams in
    "neon": "Neon glow",  # white text with a coloured glow, flickers on
    "minimal": "Minimal",  # clean text on a soft dark box
}
TITLE_ACCENTS = ["#FFD60A", "#FF3B30", "#34C759", "#3FA9FF"]
TITLE_ANIMATIONS = ["pop", "slam", "fade", "slide_up", "flicker", "typewriter", "none"]
TITLE_BASE: dict[str, Any] = {
    "font": "Poppins ExtraBold",
    "size": 90,  # px at 1080 wide
    "color": "#FFFFFF",
    "uppercase": False,
    "outline": 0,
    "outline_color": "#000000",
    "shadow": 0,
    "shadow_color": "#000000",
    "box": False,
    "box_color": "#000000",
    "box_opacity": 0.7,
    "box_pad": 16,
    "glow": 0,
    "glow_color": "#3FA9FF",
    "animation": "pop",
    "rotation": 0.0,
    "line_spacing": 1.0,
    "letter_spacing": 0.0,
    "align": "center",
    "auto_colors": False,
    "word_colors": None,  # {"word index": "#hex"}; None = automatic
    "wrap": "auto",  # auto | one (manual line breaks always win)
}
TITLE_PRESETS: dict[str, dict[str, Any]] = {
    "impact": {"font": "Luckiest Guy", "size": 104, "uppercase": True, "outline": 11, "shadow": 5, "auto_colors": True},
    "box": {
        "font": "Archivo Black", "size": 76, "color": "#101010", "uppercase": True, "shadow": 8, "box": True,
        "box_color": "#FFD60A", "box_opacity": 1.0, "box_pad": 20, "animation": "slam", "rotation": -2.0,
        "line_spacing": 1.25,
    },
    "neon": {
        "size": 100, "uppercase": True, "outline": 3, "outline_color": "#3FA9FF", "glow": 22, "animation": "flicker",
        "line_spacing": 1.1,
    },
    "minimal": {"size": 92, "box": True, "box_opacity": 0.69, "box_pad": 18, "animation": "fade", "line_spacing": 1.3},
}  # fmt: skip
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def resolve_title(ov: dict) -> dict[str, Any]:
    """Design defaults + the creator's overrides, clamped to sane values."""
    design = ov.get("style") if ov.get("style") in TITLE_STYLES else "impact"
    spec = {**TITLE_BASE, **TITLE_PRESETS[design]}
    for k in TITLE_BASE:
        if ov.get(k) is not None:
            spec[k] = ov[k]
    if ov.get("size_scale"):  # older titles
        spec["size"] = spec["size"] * max(0.5, min(2.0, float(ov["size_scale"])))
    legacy = ov.get("bg")
    if (
        legacy
        and _HEX.match(str(legacy))
        and str(legacy).upper() != "#C6F432"
        and ov.get("box_color") is None
        and spec["box"]
    ):
        spec["box_color"] = legacy
    for c in ("color", "outline_color", "shadow_color", "box_color", "glow_color"):
        if not _HEX.match(str(spec[c])):
            spec[c] = TITLE_BASE[c] if c != "box_color" else "#000000"
    if spec["font"] not in FONT_FILES:
        spec["font"] = TITLE_PRESETS[design].get("font", TITLE_BASE["font"])
    num = lambda k, lo, hi: max(lo, min(hi, float(spec[k] or 0)))  # noqa: E731
    spec.update(
        size=num("size", 24, 240), outline=num("outline", 0, 40), shadow=num("shadow", 0, 40), glow=num("glow", 0, 60),
        box_pad=num("box_pad", 0, 60), box_opacity=num("box_opacity", 0, 1), rotation=num("rotation", -45, 45),
        line_spacing=num("line_spacing", 0.6, 2.5), letter_spacing=num("letter_spacing", -10, 40),
    )  # fmt: skip
    if spec["align"] not in ("left", "center", "right"):
        spec["align"] = "center"
    if spec["animation"] not in TITLE_ANIMATIONS:
        spec["animation"] = "pop"
    spec["design"] = design
    return spec


def split_title(text: str, max_chars: int) -> list[str]:
    """Balanced 1-3 lines (same algorithm as the browser preview)."""
    words = text.split()
    if len(text) <= max_chars or len(words) < 2:
        return [text]
    best, cut = 1e9, 1
    for i in range(1, len(words)):
        d = abs(len(" ".join(words[:i])) - len(" ".join(words[i:])))
        if d < best:
            best, cut = d, i
    lines = [" ".join(words[:cut]), " ".join(words[cut:])]
    if max(len(x) for x in lines) > max_chars * 1.6 and len(words) >= 3:
        n = len(words)
        lines = [" ".join(words[: n // 3]), " ".join(words[n // 3 : 2 * n // 3]), " ".join(words[2 * n // 3 :])]
    return lines


def title_lines(ov: dict, spec: dict) -> list[str]:
    raw = str(ov.get("text", "")).replace("\r", "")
    if spec["uppercase"]:
        raw = raw.upper()
    if "\n" in raw:  # the creator's own line breaks
        return [ln.strip() for ln in raw.split("\n") if ln.strip()]
    raw = " ".join(raw.split())
    if spec["wrap"] == "one":
        return [raw] if raw else []
    return split_title(raw, max(8, min(40, round(1600 / spec["size"])))) if raw else []


_STOP = set(
    [
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "so",
        "to",
        "of",
        "in",
        "on",
        "at",
        "for",
        "with",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "it",
        "its",
        "this",
        "that",
        "these",
        "those",
        "i",
        "you",
        "he",
        "she",
        "we",
        "they",
        "my",
        "your",
        "our",
        "their",
        "me",
        "him",
        "her",
        "us",
        "them",
        "do",
        "does",
        "did",
        "have",
        "has",
        "had",
        "not",
        "no",
        "yes",
        "just",
        "very",
        "really",
        "what",
        "how",
        "why",
        "when",
        "who",
        "where",
        "which",
        "than",
        "then",
        "there",
        "here",
        "about",
        "from",
        "into",
        "over",
        "out",
        "up",
        "down",
        "as",
        "by",
        "if",
    ]
)


def anchor_for(pos: dict | None, width: int, height: int, default: tuple[int, int, int]) -> tuple[int, int, int]:
    """A free position {x, y} (0-1) -> ASS anchor. Left/right thirds anchor on that edge so long
    lines never run off the screen."""
    if not pos or pos.get("x") is None or pos.get("y") is None:
        return default
    x, y = max(0.0, min(1.0, float(pos["x"]))), max(0.04, min(0.96, float(pos["y"])))
    m = int(56 * width / 1080)
    if x < 0.38:
        return max(m, int(x * width)), int(y * height), 4
    if x > 0.62:
        return min(width - m, int(x * width)), int(y * height), 6
    return int(x * width), int(y * height), 5


def _key_words(words: list[str], keywords: set[str]) -> set[int]:
    """Indexes of the 1-3 words worth colouring: numbers, the clip's keywords, then the longest."""
    clean = [re.sub(r"[^a-z0-9$%]", "", w.lower()) for w in words]
    pick = {i for i, c in enumerate(clean) if c and (re.search(r"\d", c) or c in keywords) and c not in _STOP}
    if len(pick) < 2:
        rest = sorted(
            (i for i, c in enumerate(clean) if c and c not in _STOP and i not in pick), key=lambda i: -len(clean[i])
        )
        pick |= set(rest[: 2 - len(pick)])
    return set(sorted(pick)[:3])


def title_events(ov: dict, width: int, height: int, seam: float | None, keywords: set[str] | None = None) -> list[str]:
    """The hook title as ASS events: one event per line (so alignment, line spacing and per-word
    colours are exact), plus an optional glow layer."""
    spec = resolve_title(ov)
    lines = title_lines(ov, spec)
    if not lines:
        return []
    k = width / 1080
    s, e = float(ov.get("start", 0)), float(ov.get("end", 3.0))
    ms = max(1, int((e - s) * 1000))
    align = spec["align"]
    pos = ov.get("pos") or {}
    dx = {"left": 0.07, "center": 0.5, "right": 0.93}[align]
    x = int(max(0.0, min(1.0, float(pos.get("x", dx)))) * width)
    # default: just above the join of stacked panels (captions sit on the join), else the upper fifth
    dy = 0.2 if seam is None else (seam - 0.11 if seam > 0.3 else seam + 0.11)
    y0 = int(max(0.03, min(0.97, float(pos.get("y", dy)))) * height)
    an = {"left": 4, "center": 5, "right": 6}[align]
    fs = spec["size"] * k
    lineh = fs * spec["line_spacing"]
    n = len(lines)
    box = spec["box"]
    a3 = _alpha(spec["box_opacity"]) if box else "&H00&"
    a4 = "&H60&" if box else "&H00&"
    show = f"\\1a&H00&\\3a{a3}\\4a{a4}"
    hide = "\\alpha&HFF&"
    out_fade = f"\\t({max(1, ms - 220)},{ms},{hide})"
    anim = spec["animation"]

    # per-word colours (global word index across lines)
    words_all = [w for ln in lines for w in ln.split()]
    colors: dict[int, str] = {}
    if isinstance(spec["word_colors"], dict):
        for key, col in spec["word_colors"].items():
            if str(key).isdigit() and _HEX.match(str(col)):
                colors[int(key)] = str(col)
    elif spec["auto_colors"]:
        for ci, wi in enumerate(sorted(_key_words(words_all, keywords or set()))):
            colors[wi] = TITLE_ACCENTS[ci % len(TITLE_ACCENTS)]
    base_col = ass_color(spec["color"])
    style_name = "TitleBox" if box else "Title"
    out: list[str] = []
    wi = 0
    for i, line in enumerate(lines):
        y = int(y0 + (i - (n - 1) / 2) * lineh)
        parts = []
        for w in line.split():
            t = _esc(w)
            if anim == "typewriter":
                at = int(min(ms * 0.6, wi * 110))
                t = f"{{{hide}\\t({at},{at + 1},{show})}}{t}"
            if wi in colors:
                t = f"{{\\1c{ass_color(colors[wi])}}}{t}{{\\1c{base_col}}}"
            parts.append(t)
            wi += 1
        body = " ".join(parts)
        place = f"\\an{an}\\pos({x},{y})"
        if anim == "slide_up":
            place = f"\\an{an}\\move({x},{y + int(56 * k)},{x},{y},0,260)"
        common = (
            f"{place}\\org({x},{y0})\\fn{spec['font']}\\fs{fs:.0f}\\fsp{spec['letter_spacing'] * k:.1f}"
            f"\\frz{-spec['rotation']:.1f}\\1c{base_col}\\4c{ass_color(spec['shadow_color'])}"
        )
        if box:
            look = f"\\3c{ass_color(spec['box_color'])}\\bord{spec['box_pad'] * k:.1f}\\shad{spec['shadow'] * k:.1f}"
        else:
            look = (
                f"\\3c{ass_color(spec['outline_color'])}\\bord{spec['outline'] * k:.1f}\\shad{spec['shadow'] * k:.1f}"
            )
        if anim == "pop":
            mo = f"\\fscx0\\fscy0\\t(0,170,\\fscx122\\fscy122)\\t(170,300,\\fscx100\\fscy100){out_fade}"
        elif anim == "slam":
            mo = f"\\fscx160\\fscy160{hide}\\t(0,140,\\fscx96\\fscy96{show})\\t(140,240,\\fscx100\\fscy100){out_fade}"
        elif anim == "flicker":
            mo = f"{hide}\\t(0,60,{show})\\t(60,110,\\alpha&H90&)\\t(110,190,{show}){out_fade}"
        elif anim in ("fade", "slide_up"):
            mo = "\\fad(250,250)"
        elif anim == "typewriter":
            mo = "\\fad(0,200)"
        else:
            mo = ""
        out.append(f"Dialogue: 5,{ts(s)},{ts(e)},{style_name},,0,0,0,,{{{common}{look}{mo}}}{body}")
        if spec["glow"] > 0 and not box:
            g = spec["glow"] * k
            gmo = mo.replace(show, "\\1a&HFF&\\3a&H20&").replace("\\alpha&H90&", "\\3a&HB0&")
            plain = " ".join(_esc(w) for w in line.split())
            out.append(
                f"Dialogue: 4,{ts(s)},{ts(e)},Title,,0,0,0,,{{{common}\\1a&HFF&\\3c{ass_color(spec['glow_color'])}"
                f"\\3a&H20&\\bord{spec['outline'] * k + g * 0.7:.1f}\\blur{g:.1f}\\shad0{gmo}}}{plain}"
            )
    return out


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
    seam: float | None = None,
    labels: dict | None = None,
    progress_pos: str = "bottom",
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
        back = (
            ass_color(style["box_color"], style["box_opacity"])
            if style["box"]
            else ass_color(style.get("shadow_color") or "#000000", 0.85)
        )
        out_col = (
            ass_color(style["box_color"], style["box_opacity"]) if style["box"] else ass_color(style["outline_color"])
        )
        family, bold, italic = _ASS_FONT.get(style["font"], (style["font"], 0, 0))
        lines.append(
            f"Style: Cap,{family},{size},{primary},{secondary},{out_col},{back},{bold},{italic},0,0,100,100,"
            f"{float(style.get('letter_spacing') or 0) * k:.1f},0,"
            f"{border_style},{outline:.1f},{style['shadow'] * k:.1f},{align},{int(70 * k)},{int(70 * k)},{margin_v},1"
        )
        anchor = (width // 2, {8: margin_v, 5: height // 2}.get(align, height - margin_v), align)
        if seam is not None and style["position"] in ("lower", "bottom", "middle") and not style.get("pos"):
            # stacked layouts (facecam + game, two speakers): captions sit on the join between panels
            anchor = (width // 2, int(height * seam), 5)
        anchor = anchor_for(style.get("pos"), width, height, anchor)
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
        f"Style: Lab,Poppins ExtraBold,{int(44 * k)},&H00FFFFFF,&H00FFFFFF,&H260F0B0B,&H00000000,0,0,0,0,"
        f"100,100,0,0,3,{14 * k:.1f},0,7,0,0,0,1"
    )
    if labels and labels.get("enabled", True) and duration:
        # name badges on comparison panels ("GTA 6" on top, "Cyberpunk 2077" below)
        pad = int(34 * k)
        for key, y in (("top", pad), ("bottom", int(height * (seam or 0.5)) + pad)):
            text = _esc(str(labels.get(key) or "").strip())[:40]
            if text:
                events.append(f"Dialogue: 2,{ts(0)},{ts(duration)},Lab,,0,0,0,,{{\\pos({pad},{y})}}{text.upper()}")
    lines.append(
        f"Style: Title,Luckiest Guy,{int(100 * k)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,"
        f"100,100,1,0,1,{10 * k:.1f},{5 * k:.1f},5,{int(50 * k)},{int(50 * k)},0,1"
    )
    lines.append(
        f"Style: TitleBox,Archivo Black,{int(76 * k)},&H00101010,&H00101010,&H0014D6FF,&H00000000,0,0,0,0,"
        f"100,100,0,0,3,{20 * k:.1f},{8 * k:.1f},5,{int(60 * k)},{int(60 * k)},0,1"
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
        elif ov.get("kind") == "title":
            events += title_events({**ov, "start": s, "end": e}, width, height, seam, keywords)
        else:
            col = ass_color(ov.get("color", "#0B0F14"))
            bg = ass_color(ov.get("bg", "#C6F432"), 0.95)
            events.append(f"Dialogue: 1,{ts(s)},{ts(e)},Over,,0,0,0,,{{\\1c{col}\\3c{bg}\\fad(200,200)}}{text}")
    if progress_bar and duration:
        # A full-width rectangle revealed left to right by an animated clip: a retention bar.
        bh = max(4, int(10 * k))
        y0 = 0 if progress_pos == "top" else height - bh
        col = ass_color(progress_bar)
        ms = int(duration * 1000)
        events.append(
            f"Dialogue: 3,{ts(0)},{ts(duration)},Bar,,0,0,0,,"
            f"{{\\pos(0,{y0})\\1c{col}\\bord0\\shad0\\clip(0,{y0},1,{y0 + bh})\\t(0,{ms},\\clip(0,{y0},{width},{y0 + bh}))\\p1}}"
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
        tags += f"\\shad{max(3, int(7 * k))}\\4c{ass_color(style['highlight'] if style['highlight'] != style['color'] else '#C6F432')}\\4a&H00&"
    elif eff == "tilt":
        tags += f"\\frz{(-3, 2.5, -2, 3)[ci % 4]}"
    if eff != "tilt" and float(style.get("rotation") or 0):
        tags += f"\\frz{-max(-45.0, min(45.0, float(style['rotation']))):.1f}"
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
