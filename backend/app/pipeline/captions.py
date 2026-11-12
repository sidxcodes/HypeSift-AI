"""Caption chunking, style presets, ASS (burn-in) and SRT generation.

The same preset table is served to the browser (``/api/meta``) so the editor's live
preview uses identical fonts, sizes, colours and timing to the exported video.
Sizes are defined for a 1080-px-wide frame and scaled to the output.
"""

from __future__ import annotations

import copy
import re
from typing import Any

FONT_FILES = {
    "Poppins Medium": "Poppins-Medium.ttf",
    "Poppins SemiBold": "Poppins-SemiBold.ttf",
    "Poppins ExtraBold": "Poppins-ExtraBold.ttf",
    "Anton": "Anton-Regular.ttf",
    "Bebas Neue": "BebasNeue-Regular.ttf",
    "Bangers": "Bangers-Regular.ttf",
    "DM Serif Display": "DMSerifDisplay-Regular.ttf",
}

PRESETS: dict[str, dict[str, Any]] = {
    "clean_minimal": {
        "label": "Clean Minimal", "font": "Poppins Medium", "size": 58, "color": "#FFFFFF",
        "highlight": "#FFFFFF", "outline": 0, "outline_color": "#000000", "shadow": 0,
        "box": True, "box_color": "#000000", "box_opacity": 0.55, "uppercase": False, "max_words": 6,
        "position": "bottom", "animation": "none", "emphasis": False, "emphasis_color": "#C4B5FD",
    },
    "bold_creator": {
        "label": "Bold Creator", "font": "Poppins ExtraBold", "size": 84, "color": "#FFFFFF",
        "highlight": "#FFE14D", "outline": 6, "outline_color": "#000000", "shadow": 2,
        "box": False, "box_color": "#000000", "box_opacity": 0.0, "uppercase": True, "max_words": 3,
        "position": "middle", "animation": "pop", "emphasis": True, "emphasis_color": "#FFE14D",
    },
    "gaming_energy": {
        "label": "Gaming Energy", "font": "Bangers", "size": 104, "color": "#FFFFFF",
        "highlight": "#7CFF4F", "outline": 7, "outline_color": "#0B0B12", "shadow": 3,
        "box": False, "box_color": "#000000", "box_opacity": 0.0, "uppercase": True, "max_words": 2,
        "position": "middle", "animation": "pop", "emphasis": True, "emphasis_color": "#FF4FD8",
    },
    "podcast": {
        "label": "Podcast", "font": "Poppins SemiBold", "size": 66, "color": "#FFFFFF",
        "highlight": "#A78BFA", "outline": 4, "outline_color": "#111111", "shadow": 0,
        "box": False, "box_color": "#000000", "box_opacity": 0.0, "uppercase": False, "max_words": 4,
        "position": "lower", "animation": "highlight", "emphasis": False, "emphasis_color": "#A78BFA",
    },
    "cinematic": {
        "label": "Cinematic", "font": "DM Serif Display", "size": 64, "color": "#F5EBDD",
        "highlight": "#F5EBDD", "outline": 0, "outline_color": "#000000", "shadow": 3,
        "box": False, "box_color": "#000000", "box_opacity": 0.0, "uppercase": False, "max_words": 7,
        "position": "bottom", "animation": "fade", "emphasis": False, "emphasis_color": "#E8C07D",
    },
    "karaoke": {
        "label": "Karaoke Highlight", "font": "Poppins ExtraBold", "size": 76, "color": "#FFFFFF",
        "highlight": "#22D3EE", "outline": 5, "outline_color": "#000000", "shadow": 0,
        "box": False, "box_color": "#000000", "box_opacity": 0.0, "uppercase": True, "max_words": 4,
        "position": "middle", "animation": "karaoke", "emphasis": False, "emphasis_color": "#22D3EE",
    },
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
    return base


# ----------------------------------------------------------------------------- chunking


def chunk_words(words: list[dict], max_words: int = 3, max_chars: int = 28, max_gap: float = 0.55) -> list[dict]:
    """words: [{w,s,e}] with times relative to the clip. Returns caption chunks."""
    chunks: list[dict] = []
    cur: list[dict] = []

    def flush() -> None:
        if cur:
            chunks.append({"s": cur[0]["s"], "e": cur[-1]["e"], "text": " ".join(x["w"] for x in cur),
                           "words": [dict(x) for x in cur]})
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


def ts(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", " ")


def build_ass(width: int, height: int, chunks: list[dict], style: dict[str, Any] | None,
              overlays: list[dict] | None = None, keywords: set[str] | None = None,
              duration: float | None = None) -> str:
    """Return a complete ASS document. ``style`` None disables captions (overlays only)."""
    k = width / 1080
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "YCbCr Matrix: TV.709", "",
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
        outline = (max(6, int(size * 0.18)) if style["box"] else style["outline"] * k)
        back = ass_color(style["box_color"], style["box_opacity"]) if style["box"] else ass_color("#000000", 0.6)
        out_col = ass_color(style["box_color"], style["box_opacity"]) if style["box"] else ass_color(style["outline_color"])
        lines.append(
            f"Style: Cap,{style['font']},{size},{primary},{secondary},{out_col},{back},0,0,0,0,100,100,0,0,"
            f"{border_style},{outline:.1f},{style['shadow'] * k:.1f},{align},{int(70 * k)},{int(70 * k)},{margin_v},1"
        )
        events += _caption_events(chunks, style, keywords or set())
    lines.append(f"Style: Over,Poppins ExtraBold,{int(58 * k)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,"
                 f"100,100,0,0,3,{14 * k:.1f},0,8,{int(80 * k)},{int(80 * k)},{int(height * 0.07)},1")
    lines.append(f"Style: Mark,Poppins SemiBold,{int(34 * k)},&H59FFFFFF,&H59FFFFFF,&H80000000,&H00000000,0,0,0,0,"
                 f"100,100,0,0,1,{1.5 * k:.1f},0,9,{int(40 * k)},{int(40 * k)},{int(40 * k)},1")
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
    lines += ["", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    lines += events
    return "\n".join(lines) + "\n"


def _word_text(w: str, style: dict, keywords: set[str]) -> tuple[str, bool]:
    t = w.upper() if style["uppercase"] else w
    is_kw = style.get("emphasis") and re.sub(r"[^a-z0-9]", "", w.lower()) in keywords
    return _esc(t), bool(is_kw)


def _caption_events(chunks: list[dict], style: dict, keywords: set[str]) -> list[str]:
    ev: list[str] = []
    anim = style["animation"]
    hi = ass_color(style["highlight"])
    emph = ass_color(style.get("emphasis_color", style["highlight"]))
    base = ass_color(style["color"])
    for ch in chunks:
        words = ch.get("words") or []
        if not words:
            continue
        s, e = ch["s"], max(ch["e"], ch["s"] + 0.2)
        if anim == "karaoke":
            parts = []
            for i, w in enumerate(words):
                nxt = words[i + 1]["s"] if i + 1 < len(words) else e
                dur_cs = max(1, int(round((nxt - w["s"]) * 100)))
                txt, _ = _word_text(w["w"], style, keywords)
                parts.append(f"{{\\kf{dur_cs}}}{txt}")
            lead = max(0, int(round((words[0]["s"] - s) * 100)))
            ev.append(f"Dialogue: 0,{ts(s)},{ts(e)},Cap,,0,0,0,,{{\\k{lead}}}" + " ".join(parts))
        elif anim in ("highlight", "pop"):
            # one event per active word: whole chunk visible, active word coloured (and popped)
            for i, w in enumerate(words):
                ws = s if i == 0 else w["s"]
                we = words[i + 1]["s"] if i + 1 < len(words) else e
                if we - ws <= 0.01:
                    continue
                parts = []
                for j, x in enumerate(words):
                    txt, kw = _word_text(x["w"], style, keywords)
                    if j == i:
                        pop = "\\fscx110\\fscy110" if anim == "pop" else ""
                        parts.append(f"{{\\1c{hi}{pop}}}{txt}{{\\1c{base}\\fscx100\\fscy100}}")
                    elif kw:
                        parts.append(f"{{\\1c{emph}}}{txt}{{\\1c{base}}}")
                    else:
                        parts.append(txt)
                ev.append(f"Dialogue: 0,{ts(ws)},{ts(we)},Cap,,0,0,0,,{' '.join(parts)}")
        else:
            parts = []
            for x in words:
                txt, kw = _word_text(x["w"], style, keywords)
                parts.append(f"{{\\1c{emph}}}{txt}{{\\1c{base}}}" if kw else txt)
            fade = "{\\fad(180,180)}" if anim == "fade" else ""
            ev.append(f"Dialogue: 0,{ts(s)},{ts(e)},Cap,,0,0,0,,{fade}{' '.join(parts)}")
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
