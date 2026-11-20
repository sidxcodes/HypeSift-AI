from app.pipeline import captions, reframe, render
from app.pipeline.transcribe import Word


def _w(spec):
    return [{"w": w, "s": s, "e": e} for w, s, e in spec]


def test_chunking_respects_word_limit_and_sentence_end():
    words = _w([("one", 0, 0.3), ("two", 0.35, 0.6), ("three.", 0.65, 1.0), ("four", 1.1, 1.3), ("five", 1.35, 1.6)])
    ch = captions.chunk_words(words, max_words=4)
    assert ch[0]["text"] == "one two three."
    assert ch[1]["text"] == "four five"


def test_chunking_breaks_on_long_gap():
    ch = captions.chunk_words(_w([("a", 0, 0.2), ("b", 2.0, 2.2)]), max_words=5)
    assert len(ch) == 2


def test_retime_spreads_edited_words():
    ch = captions.retime_chunk({"s": 1.0, "e": 3.0, "text": "hello big world", "words": _w([("hi", 1, 3)])})
    assert [w["w"] for w in ch["words"]] == ["hello", "big", "world"]
    assert ch["words"][0]["s"] == 1.0 and abs(ch["words"][-1]["e"] - 3.0) < 1e-6


def test_ass_color_is_bgr_with_alpha():
    assert captions.ass_color("#FF8800") == "&H000088FF"
    assert captions.ass_color("#000000", 0.0) == "&HFF000000"


def test_build_ass_karaoke_and_overlays():
    ch = captions.chunk_words(_w([("hello", 0, 0.4), ("world", 0.5, 0.9)]), max_words=3)
    style = captions.style_for({"preset": "karaoke"})
    doc = captions.build_ass(1080, 1920, ch, style, [{"kind": "title", "text": "My Title", "start": 0, "end": 2}])
    assert "PlayResX: 1080" in doc and "Style: Cap,Poppins ExtraBold" in doc
    assert "\\kf" in doc
    assert "MY {" in doc and "TITLE" in doc  # impact design: upper case, key word coloured


def test_style_overrides_and_size_scale():
    s = captions.style_for({"preset": "bold_creator", "style": {"highlight": "#00FF00", "size_scale": 1.2}})
    assert s["highlight"] == "#00FF00"
    assert s["size"] == int(captions.PRESETS["bold_creator"]["size"] * 1.2)


def test_srt_format():
    srt = captions.build_srt([{"s": 0, "e": 1.5, "text": "hi there"}, {"s": 61.25, "e": 62, "text": "bye"}])
    assert "00:00:00,000 --> 00:00:01,500" in srt
    assert "00:01:01,250 --> 00:01:02,000" in srt


def test_keep_segments_and_time_mapping():
    words = [Word("a", 10.0, 10.4), Word("b", 10.5, 10.9), Word("c", 13.0, 13.4), Word("d", 13.5, 14.0)]
    segs = render.keep_segments(words, 9.8, 14.5, enabled=True)
    assert len(segs) == 2  # the 2.1 s pause is cut
    f = render.time_mapper(segs)
    assert f(0.0) == 0.0
    # a word after the cut lands earlier in the output than in the source
    assert f(13.0 - 9.8) < 13.0 - 9.8
    assert render.keep_segments(words, 9.8, 14.5, enabled=False)[0].e == 14.5 - 9.8


def test_piecewise_crop_expression_is_clamped():
    expr = reframe.piecewise_expr([[0, 0.0, 0.5], [2, 1.0, 0.5]], 1, 1920, 607)
    assert expr.startswith("if(")
    assert "1313" in expr  # max offset = 1920 - 607
    assert reframe.piecewise_expr([[0, 0.5, 0.5]], 1, 1920, 1920) == "0"


def test_crop_box_aspects():
    assert reframe.crop_box(1920, 1080, "9:16") == (606, 1080)
    assert reframe.crop_box(1080, 1920, "16:9") == (1080, 606)
