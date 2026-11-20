from app.pipeline import compare, multicompare
from app.pipeline.transcribe import Word

PARTS = [{"start": 10, "end": 14, "label": "GTA IV"}, {"start": 30, "end": 33, "label": "GTA V"}]


def test_turns_plan_and_audio_follow_the_playing_version():
    segs = multicompare.plan(PARTS, "turns")
    assert [(s["t0"], s["t1"], s["active"]) for s in segs] == [(0.0, 4, 0), (4, 7, 1)]
    g = "\n".join(multicompare.build_graph(PARTS, "turns", "active", 1080, 1920, 30, True))
    assert "tpad=stop_duration=3.000:stop_mode=clone" in g  # first one freezes while the second plays
    assert "tpad=start_duration=4.000:start_mode=clone" in g
    assert "concat=n=2:v=0:a=1" in g and "amix" not in g  # one voice at a time, never mixed


def test_together_uses_one_soundtrack_unless_mix():
    g = "\n".join(multicompare.build_graph(PARTS, "together", "active", 1080, 1920, 30, True))
    assert "[0:a]atrim=0:3.000" in g and "amix" not in g
    assert "amix" in "\n".join(multicompare.build_graph(PARTS, "together", "mix", 1080, 1920, 30, True))


def test_grid_then_single_and_three_versions():
    three = PARTS + [{"start": 50, "end": 55, "label": "GTA VI"}]
    segs = multicompare.plan(three, "grid_then_single")
    assert segs[0]["kind"] == "stack" and segs[0]["t1"] == 3.0
    assert [s["active"] for s in segs[1:]] == [0, 1, 2]
    g = "\n".join(multicompare.build_graph(three, "grid_then_single", "active", 1080, 1920, 30, True))
    assert "vstack=inputs=3" in g and "concat=n=4:v=1:a=0" in g


def test_words_and_fit():
    words = [Word("hello", 10.5, 11.0, 0.9), Word("there", 30.2, 30.6, 0.9), Word("skip", 20.0, 20.5, 0.9)]
    tw = multicompare.timeline_words(PARTS, "turns", words)
    assert [(w["w"], w["s"]) for w in tw] == [("hello", 0.5), ("there", 4.2)]
    fit = multicompare.fit_parts([{"start": 0, "end": 60}, {"start": 100, "end": 160}], "turns", 40)
    assert all(p["end"] - p["start"] == 20 for p in fit)


def test_from_gemini_and_not_a_comparison():
    gc = {
        "is_comparison": True,
        "layout": "sequential",
        "versions": ["GTA IV", "GTA V", "GTA VI"],
        "scenarios": [
            {
                "title": "Opening a car door",
                "score": 88,
                "parts": [
                    {"label": "GTA IV", "start": 2, "end": 7},
                    {"label": "GTA V", "start": 8, "end": 12},
                    {"label": "GTA VI", "start": 13, "end": 18},
                ],
            }
        ],
    }
    out = compare.from_gemini(gc, None, [7.9], 15, 60)
    assert out and out[0]["mode"] == "multi" and len(out[0]["parts"]) == 3
    assert out[0]["parts"][1]["start"] == 7.9  # snapped to the scene cut
    assert compare.from_gemini({"is_comparison": False}, {"splits": [[0, 20]]}, [], 15, 60) == []
