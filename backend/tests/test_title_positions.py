import re

from app.pipeline import captions, render


def _title(style, **kw):
    ov = {"kind": "title", "text": "I lost 100k in eleven minutes", "start": 0, "end": 3, "style": style, **kw}
    return captions.build_ass(1080, 1920, [], None, [ov], duration=10)


def _lines(doc: str) -> list[str]:
    return [ln for ln in doc.splitlines() if ln.startswith("Dialogue: 5,")]


def test_every_title_design_renders():
    for name in captions.TITLE_STYLES:
        assert _lines(_title(name)), name
    impact = _title("impact")
    assert "\\fscx0\\fscy0" in impact and len(_lines(impact)) == 2  # pops in, two balanced lines
    assert "100K" in impact.split("Dialogue: 5,")[1]  # numbers are coloured key words
    assert "\\blur" in _title("neon")


def test_manual_line_breaks_alignment_and_one_line():
    doc = _title("impact", text="Techno Gamer\nGot angry?", align="left", pos={"x": 0.1, "y": 0.5})
    lines = _lines(doc)
    assert len(lines) == 2 and "TECHNO" in lines[0] and "GAMER" in lines[0]
    assert "GOT" in lines[1] and "\\an4" in lines[0]
    ys = [int(re.search(r"\\pos\(\d+,(\d+)\)", ln).group(1)) for ln in lines]
    assert ys[0] < 960 < ys[1]  # centred on the chosen y
    one = _lines(_title("impact", text="Techno gamer got angry", wrap="one"))
    assert len(one) == 1


def test_overrides_and_word_colours():
    doc = _title(
        "minimal",
        font="Anton",
        size=120,
        color="#FF0000",
        word_colors={"0": "#00FF00"},
        animation="slide_up",
        rotation=5,
    )
    line = _lines(doc)[0]
    assert "\\fnAnton" in line and "\\fs120" in line and "\\move(" in line and "\\frz-5.0" in line
    assert "\\1c&H0000FF00}I" in line.replace("{", "}")  # first word green
    bad = captions.resolve_title({"style": "impact", "font": "Comic Sans", "color": "red", "size": 9999})
    assert bad["font"] == "Luckiest Guy" and bad["color"] == "#FFFFFF" and bad["size"] == 240


def test_title_and_caption_positions():
    doc = _title("impact", text="Short title", pos={"x": 0.5, "y": 0.8})
    assert "\\an5\\pos(540,1536)" in doc
    style = captions.style_for({"preset": "bold_creator"})
    style["pos"] = {"x": 0.9, "y": 0.5}
    words = [{"w": "hello", "s": 0, "e": 0.5}]
    doc = captions.build_ass(1080, 1920, captions.chunk_words(words), style)
    assert "\\an6" in doc


def test_caption_position_from_saved_edits_reaches_the_render():
    # exactly what the editor saves: style overrides inside edits.captions, on a stacked layout
    st = captions.style_for(
        {"preset": "bold_creator", "style": {"pos": {"x": 0.5, "y": 0.777}, "letter_spacing": 3, "rotation": 2}}
    )
    doc = captions.build_ass(1080, 1920, captions.chunk_words([{"w": "hi", "s": 0, "e": 0.5}]), st, seam=0.28)
    line = next(ln for ln in doc.splitlines() if ln.startswith("Dialogue: 1,"))
    assert "\\pos(540,1491)" in line or "\\move(" in line and ",1491," in line  # not on the seam (y=537)
    assert "\\frz-2.0" in line


def test_every_editor_caption_field_survives_style_for():
    fields = {
        "font": "Anton", "size": 99, "color": "#112233", "highlight": "#445566", "outline": 7,
        "outline_color": "#778899", "shadow": 3, "shadow_color": "#AABBCC", "box": True, "box_color": "#DDEEFF",
        "box_opacity": 0.5, "uppercase": True, "max_words": 2, "position": "top", "animation": "pop",
        "emphasis": True, "emphasis_color": "#010203", "glow": 4, "glow_color": "#040506", "opacity": 0.9,
        "letter_spacing": 2, "rotation": 3, "pos": {"x": 0.2, "y": 0.3},
    }  # fmt: skip
    st = captions.style_for({"preset": "basic", "style": fields})
    for k, v in fields.items():
        assert st[k] == v, k


def test_logo_and_progress_positions():
    assert render.logo_xy({"position": "bottom_center"}, 36) == "36+(W-w-72)*0.500:36+(H-h-72)*1.000"
    assert render.logo_xy({"x": 0.2, "y": 0.3}, 36).endswith("*0.300")
    top = captions.build_ass(1080, 1920, [], None, [], duration=5, progress_bar="#FF7A59", progress_pos="top")
    assert "\\pos(0,0)" in top
