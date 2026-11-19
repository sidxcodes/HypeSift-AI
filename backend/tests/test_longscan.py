"""Long videos: scan captions / replay graph, pick sections, download only those (site faked)."""

from __future__ import annotations

import pytest

from app.pipeline import highlights, longscan, sites
from app.pipeline.transcribe import Word
from app.tasks import prefs_from

from .conftest import SCRIPT


def test_choose_sections_pads_merges_and_uses_replay_graph():
    c = [
        highlights.Candidate(start=100, end=130, score=60),
        highlights.Candidate(start=135, end=160, score=58),  # close to the first: merged into one range
        highlights.Candidate(start=5000, end=5030, score=55),
        highlights.Candidate(start=9000, end=9030, score=50),  # weak, but the most replayed moment
    ]
    heat = [(0, 1000, 0.1), (4000, 6000, 0.2), (8990, 9040, 1.0)]
    ranges = longscan.choose_sections(c, heat, 3, 10000)
    assert ranges[-1][0] == 9000 - longscan.PAD  # the replay boost pulled it in
    assert all(b - a >= 30 for a, b in ranges)
    assert ranges == sorted(ranges)


def test_json3_caption_words():
    data = {
        "events": [
            {
                "tStartMs": 1000,
                "dDurationMs": 3000,
                "segs": [{"utf8": "hello"}, {"utf8": " big", "tOffsetMs": 500}, {"utf8": " world", "tOffsetMs": 900}],
            },
            {"tStartMs": 4000, "dDurationMs": 2000, "segs": [{"utf8": "\n"}]},
        ]
        + [{"tStartMs": 5000 + i * 300, "dDurationMs": 300, "segs": [{"utf8": f"w{i}"}]} for i in range(25)]
    }
    words = sites._json3_words(data)
    assert [w.w for w in words[:3]] == ["hello", "big", "world"]
    assert (words[0].s, words[1].s) == (1.0, 1.5) and words[0].e == 1.5


def test_caption_track_order_prefers_spoken_language_then_english():
    info = {
        "language": "hi",
        "subtitles": {},
        "automatic_captions": {"hi-orig": [{"ext": "json3"}], "en": [{"ext": "json3"}], "fr": [{"ext": "json3"}]},
    }
    assert [k for _, k, _ in sites._caption_track(info)] == ["hi-orig", "en"]
    info["subtitles"] = {"en": [{"ext": "json3"}]}
    assert [k for _, k, _ in sites._caption_track(info)][0] == "en"  # manual captions win


def test_map_words_onto_joined_timeline():
    words = [Word("a", 10.0, 10.4), Word("b", 500.0, 500.3), Word("c", 2000.5, 2000.9)]
    sections = [
        {"orig_start": 495, "orig_end": 530, "start": 0, "end": 35},
        {"orig_start": 1990, "orig_end": 2020, "start": 35, "end": 65},
    ]
    assert longscan.map_words(words, sections) == [["b", 5.0, 5.3], ["c", 45.5, 45.9]]


def test_clips_never_cross_a_section_join(sample_video):
    from app.pipeline import signals

    sig = signals.compute(sample_video, None, 40.0)
    words, t = [], 0.6
    for tok in SCRIPT.split():
        words.append(Word(tok, round(t, 3), round(t + 0.3, 3)))
        t += 0.4 + (0.5 if tok.endswith(".") else 0)
    prefs = highlights.Prefs(count=4, min_dur=8, max_dur=16, barriers=[20.0])
    cands, _ = highlights.discover(words, sig, prefs)
    assert cands and all(not (c.start + 0.3 < 20.0 < c.end - 0.3) for c in cands)


def test_plan_with_captions(monkeypatch, tmp_path):
    words = []
    t = 0.0
    for _ in range(200):  # a 2-hour "stream" with a talkative stretch every so often
        for tok in SCRIPT.split():
            words.append(Word(tok, round(t, 2), round(t + 0.3, 2)))
            t += 0.4
        t += 30
    monkeypatch.setattr(sites, "scan_info", lambda url: {"duration": t + 10, "heatmap": []})
    monkeypatch.setattr(sites, "caption_words", lambda url, info, work: (words, "en"))
    prefs = prefs_from({"count": 3, "min_dur": 15, "max_dur": 45})
    ranges, scan_words, meta = longscan.plan("https://youtu.be/x", prefs, tmp_path / "scan", progress=lambda *a: None)
    assert 3 <= len(ranges) <= 10 and meta["source"] == "captions (en)" and meta["language"] == "en"
    assert meta["downloaded_seconds"] < (t + 10) * 0.05  # a tiny fraction of the video
    assert scan_words is words


def test_plan_without_speech_spreads_sections(monkeypatch, tmp_path):
    monkeypatch.setattr(sites, "scan_info", lambda url: {"duration": 7200, "heatmap": []})
    monkeypatch.setattr(sites, "caption_words", lambda url, info, work: None)
    monkeypatch.setattr(longscan, "_audio_words", lambda *a, **k: ([], []))
    ranges, _, meta = longscan.plan("https://youtu.be/x", prefs_from({"count": 2}), tmp_path, progress=lambda *a: None)
    assert ranges and meta["source"].startswith("audio")


@pytest.mark.parametrize("text", ["यह बहुत अच्छा है।", "hello world"])
def test_tokens_any_script(text):
    toks = highlights.tokens(text)
    assert toks and all(t and not t.endswith("।") for t in toks)


def test_exciting_windows_skip_stream_intro_and_find_loud_parts():
    import numpy as np

    loud = np.full(4 * 3600, -35.0, dtype=np.float32)
    loud[30:170] = -5  # loud intro song
    loud[5000:5060] = -8  # a hype moment
    loud[9000:9050] = -10  # another
    w = longscan.exciting_windows(loud, 2)
    assert len(w) == 2 and all(a > 180 for a, _ in w)
    assert any(a <= 5030 <= b for a, b in w) and any(a <= 9025 <= b for a, b in w)


def test_audio_fallback_transcribes_only_the_exciting_windows(monkeypatch, tmp_path):
    import numpy as np

    from app.pipeline import ffmpeg, transcribe

    audio = tmp_path / "a.webm"
    audio.write_bytes(b"x")
    monkeypatch.setattr(sites, "download_audio", lambda *a, **k: audio)
    loud = np.full(7200, -35.0, dtype=np.float32)
    loud[3000:3060] = -6
    monkeypatch.setattr(longscan, "loudness_per_second", lambda *a, **k: loud)
    calls = []

    def fake_run(args, timeout=None):
        (tmp_path / "chunk.wav").write_bytes(b"0" * 4000)

    monkeypatch.setattr(ffmpeg, "run", fake_run)

    def fake_tr(path, lang, dur, **k):
        calls.append(dur)
        return transcribe.Transcript(language="en", words=[Word("wow", 1.0, 1.4), Word("insane", 2.0, 2.5)])

    monkeypatch.setattr(transcribe, "transcribe", fake_tr)
    words, joins = longscan._audio_words("u", tmp_path, None, 7200, 4, lambda *a: None, None)
    assert len(calls) == 12 and sum(calls) <= 12 * 75 + 1  # 12 windows, not 2 hours of audio
    assert words and len(joins) == 11
