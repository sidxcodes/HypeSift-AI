"""Streamer layout: find the webcam overlay, put it on top, the game below, captions on the seam."""

from __future__ import annotations

import numpy as np
import pytest

from app.pipeline import captions, ffmpeg, reframe, render


def _frames(n=16, h=540, w=960, seed=0):
    """Fake stream: moving "game" everywhere, a bordered webcam box at the left with a live face,
    and a static face-like poster in the middle (game art)."""
    rng = np.random.default_rng(seed)
    frames = []
    for i in range(n):
        f = (rng.random((h, w)) * 60 + 40 + 20 * np.sin(i)).astype(np.uint8)  # busy, changing game
        f[60:300, 20:270] = 120  # webcam overlay
        f[58:62, 18:272] = 255  # top border
        f[298:302, 18:272] = 255  # bottom border
        f[58:302, 18:22] = 255  # left border
        f[58:302, 268:272] = 255  # right border
        f[130:210, 110:180] = (rng.random((80, 70)) * 120 + 60).astype(np.uint8)  # live face (changes)
        f[200:270, 600:660] = 200  # static poster face
        frames.append(f)
    return np.stack(frames)


@pytest.fixture
def fake_stream(monkeypatch):
    frames = _frames()
    monkeypatch.setattr(ffmpeg, "read_frames", lambda *a, **k: (frames, 2.0))

    class Det:
        def detectMultiScale(self, g, **kw):  # noqa: N802 - OpenCV's name
            return [(110, 130, 70, 80), (600, 200, 60, 70)]

    monkeypatch.setattr(reframe, "_front", Det())
    return frames


def test_detects_live_webcam_and_snaps_to_its_border(fake_stream):
    r = reframe.detect_facecam("x.mp4", 0, 30)
    assert r is not None and r["snapped"]
    x, y, w, h = r["box"]
    W, H = 960, 540
    # within a few pixels of the drawn overlay border (18..272 x 58..302)
    assert abs(x * W - 18) < 8 and abs((x + w) * W - 272) < 8
    assert abs(y * H - 58) < 8 and abs((y + h) * H - 302) < 8
    assert abs(r["face"][0] * W - 145) < 5  # the live face, not the static poster at x≈630


def test_static_faces_are_not_a_webcam(monkeypatch):
    frames = np.stack([np.full((540, 960), 90, np.uint8)] * 12)
    monkeypatch.setattr(ffmpeg, "read_frames", lambda *a, **k: (frames, 2.0))

    class Det:
        def detectMultiScale(self, g, **kw):  # noqa: N802
            return [(600, 200, 60, 70)]

    monkeypatch.setattr(reframe, "_front", Det())
    assert reframe.detect_facecam("x.mp4", 0, 30) is None


def test_big_faces_are_left_to_normal_reframing(monkeypatch):
    frames = _frames()
    monkeypatch.setattr(ffmpeg, "read_frames", lambda *a, **k: (frames, 2.0))

    class Det:
        def detectMultiScale(self, g, **kw):  # noqa: N802
            return [(300, 100, 200, 220)]  # a talking head filling the frame

    monkeypatch.setattr(reframe, "_front", Det())
    assert reframe.detect_facecam("x.mp4", 0, 30) is None


def test_gameplay_layout_filter_and_seam():
    probe = ffmpeg.Probe(
        duration=30, width=1280, height=720, fps=30, has_audio=True, video_codec="h264", audio_codec="aac", size_bytes=1
    )
    rf = {"facecam": {"box": [0.02, 0.07, 0.26, 0.44]}}
    edits = render.merged_edits({"aspect": "9:16", "crop": {"mode": "facecam"}})
    chain = render.build_video_chain(probe, edits, rf, 1080, 1920)
    assert "vstack=2" in chain and "scale=1080:768" in chain and "scale=1080:1152" in chain
    # the game crop starts right of the webcam (cam ends at 0.28*1280 ≈ 358 px)
    game_x = int(chain.split("[ga]crop=")[1].split(",")[0].split(":")[2])
    assert game_x >= 356
    assert render.layout_seam(edits, rf) == 0.4
    assert render.layout_seam(render.merged_edits({"crop": {"mode": "auto"}}), rf) is None
    assert render.layout_seam(edits, {}) is None  # no webcam found → normal crop, no seam


def test_captions_sit_on_the_seam():
    chunk = [
        {"s": 0, "e": 1, "text": "no way", "words": [{"w": "no", "s": 0, "e": 0.5}, {"w": "way", "s": 0.5, "e": 1}]}
    ]
    style = captions.style_for({"preset": "heat"})
    ass = captions.build_ass(1080, 1920, chunk, style, duration=2, seam=0.4)
    assert "\\an5\\pos(540,768)" in ass
    assert "\\an2\\pos(540," in captions.build_ass(1080, 1920, chunk, style, duration=2)
