from app.pipeline import captions, render


def _title(style, **kw):
    ov = {"kind": "title", "text": "I lost 100k in eleven minutes", "start": 0, "end": 3, "style": style, **kw}
    return captions.build_ass(1080, 1920, [], None, [ov], duration=10)


def test_every_title_design_renders():
    for name in captions.TITLE_STYLES:
        doc = _title(name)
        assert "Dialogue: 5," in doc, name
    impact = _title("impact")
    assert "\\fscx0\\fscy0" in impact and "\\N" in impact  # pops in, two lines
    assert "100K" in impact.split("Dialogue: 5,")[1]  # numbers are coloured key words
    assert "\\blur" in _title("neon")


def test_title_and_caption_positions():
    doc = _title("impact", pos={"x": 0.5, "y": 0.8})
    assert "\\an5\\pos(540,1536)" in doc
    left = _title("minimal", pos={"x": 0.1, "y": 0.3})
    assert "\\an4" in left  # left side anchors on its left edge
    style = captions.style_for({"preset": "bold_creator"})
    style["pos"] = {"x": 0.9, "y": 0.5}
    words = [{"w": "hello", "s": 0, "e": 0.5}]
    doc = captions.build_ass(1080, 1920, captions.chunk_words(words), style)
    assert "\\an6" in doc


def test_logo_and_progress_positions():
    assert render.logo_xy({"position": "bottom_center"}, 36) == "36+(W-w-72)*0.500:36+(H-h-72)*1.000"
    assert render.logo_xy({"x": 0.2, "y": 0.3}, 36).endswith("*0.300")
    top = captions.build_ass(1080, 1920, [], None, [], duration=5, progress_bar="#FF7A59", progress_pos="top")
    assert "\\pos(0,0)" in top
