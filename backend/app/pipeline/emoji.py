"""Colour emoji in burned-in titles.

libass can only draw emoji as black-and-white outlines. So the title text is still drawn by libass
with each emoji turned invisible (it keeps its exact width in the line), and a full-colour image of
the emoji (drawn with Pillow from the system's colour emoji font) is laid over that gap.
Positions are measured with the same font files and the same size rule libass uses
((winAscent + winDescent) of the font == the ASS font size).
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

FONTS_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
EMOJI_FAMILY = "Segoe UI Emoji"
_CANDIDATES = [
    Path(r"C:\Windows\Fonts\seguiemj.ttf"),
    Path("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"),
    Path("/usr/share/fonts/noto/NotoColorEmoji.ttf"),
    Path("/System/Library/Fonts/Apple Color Emoji.ttc"),
]
_E = (
    r"(?:[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\u2300-\u23FF\u2190-\u21FF\u3297\u3299\u00A9\u00AE\u203C\u2049]"
    r"[\uFE0F\U0001F3FB-\U0001F3FF]*)"
)
EMOJI_RE = re.compile(rf"{_E}(?:\u200D{_E})*")


@lru_cache(maxsize=1)
def emoji_font() -> Path | None:
    return next((p for p in _CANDIDATES if p.exists()), None)


def available() -> bool:
    return emoji_font() is not None


def has_emoji(text: str) -> bool:
    return bool(EMOJI_RE.search(text or ""))


def runs(text: str) -> list[tuple[bool, str]]:
    """'GOT ANGRY😮!' -> [(False, 'GOT ANGRY'), (True, '😮'), (False, '!')]"""
    out, i = [], 0
    for m in EMOJI_RE.finditer(text):
        if m.start() > i:
            out.append((False, text[i : m.start()]))
        out.append((True, m.group()))
        i = m.end()
    if i < len(text):
        out.append((False, text[i:]))
    return out


@lru_cache(maxsize=32)
def _ratio(path: str) -> float:
    """ASS font size / em size for a font file (libass sizes by winAscent + winDescent)."""
    from fontTools.ttLib import TTFont

    f = TTFont(path, fontNumber=0, lazy=True)
    os2, upm = f["OS/2"], f["head"].unitsPerEm
    h = (os2.usWinAscent + os2.usWinDescent) or (f["hhea"].ascent - f["hhea"].descent)
    return max(0.5, h / upm)


@lru_cache(maxsize=64)
def _font(path: str, em: float):
    from PIL import ImageFont

    return ImageFont.truetype(path, size=max(1.0, em))


def text_width(font_path: Path, fs: float, text: str) -> float:
    em = fs / _ratio(str(font_path))
    return float(_font(str(font_path), round(em, 1)).getlength(text))


def emoji_width(fs: float, e: str) -> float:
    return text_width(emoji_font(), fs, e)


def render_png(e: str, fs: float, out: Path) -> tuple[int, int]:
    """Draw one emoji in colour at the size libass would give it; returns the image size."""
    from PIL import Image, ImageDraw

    fp = emoji_font()
    em = fs / _ratio(str(fp))
    font = _font(str(fp), round(em, 1))
    side = int(em * 1.6) + 8
    im = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((4, 4), e, font=font, embedded_color=True)
    box = im.getbbox() or (0, 0, 1, 1)
    im = im.crop(box)
    im.save(out)
    return im.size
