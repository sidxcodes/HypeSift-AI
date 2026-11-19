"""Comparison videos: names from titles, layout detection, clip pairing and stacked rendering."""

from __future__ import annotations

import numpy as np
import pytest

from app.pipeline import captions, compare, ffmpeg, render


@pytest.mark.parametrize(
    "title,names",
    [
        (
            "GTA 6 vs Cyberpunk 2077 - ULTIMATE Comparison! Attention to Detail & Graphics! 4K",
            ["GTA 6", "Cyberpunk 2077"],
        ),
        ("GTA 6 VS GTA 5 - Car Jacking Comparison", ["GTA 6", "GTA 5"]),
        ("iPhone 17 versus Pixel 10 camera test", ["iPhone 17", "Pixel 10 camera test"]),
        ("My trip to Goa", []),
    ],
)
def test_names_from_title(title, names):
    assert compare.names_from_title(title) == names


def _frame(split: bool, badge: tuple[int, int, int] | None) -> np.ndarray:
    rng = np.random.default_rng()
    f = (rng.random((180, 320, 3)) * 80 + 60).astype(np.uint8)
    if split:
        f[:, :160] = (f[:, :160] * 0.5).astype(np.uint8)
        f[:, 158:162] = 255
    if badge:
        f[3:19, 141:178] = 245
        f[7:15, 150:170] = badge
    return f


def test_split_screens_are_detected():
    frames = np.stack([_frame(True, None)] * 8 + [_frame(False, None)] * 8)
    s = compare.split_scores(frames)
    assert s[:8].min() > 6 > s[8:].max()


def test_alternating_blocks_are_found(monkeypatch, tmp_path):
    a, b = (220, 220, 40), (230, 60, 200)  # yellow badge vs pink badge
    seq = [a] * 20 + [b] * 20 + [a] * 20 + [b] * 20
    frames = np.stack([_frame(False, c) for c in seq])
    monkeypatch.setattr(compare, "read_rgb", lambda *a, **k: frames)
    monkeypatch.setattr(compare, "ask_which", lambda *a, **k: None)
    comp = compare.analyze(tmp_path / "x.mp4", 40, "Game A vs Game B comparison")
    assert comp and len(comp["blocks"]) == 4 and comp["names"] == ["Game A", "Game B"]
    cands = compare.candidates(comp, 5, 60)
    assert cands and all(c["mode"] == "pair" for c in cands)
    assert all(c["top"] == "Game A" for c in cands)  # the first-named version goes on top


def test_not_a_comparison(monkeypatch, tmp_path):
    frames = np.stack([_frame(False, None) for _ in range(40)])
    monkeypatch.setattr(compare, "read_rgb", lambda *a, **k: frames)
    assert compare.analyze(tmp_path / "x.mp4", 20, "My vlog") is None


def _probe():
    return ffmpeg.Probe(
        duration=60, width=1280, height=720, fps=30, has_audio=True, video_codec="h264", audio_codec="aac", size_bytes=1
    )


def test_stacked_chains():
    e = render.merged_edits({"aspect": "9:16", "crop": {"mode": "compare"}, "compare": {"swap": True}})
    chain = render.build_video_chain(_probe(), e, {}, 1080, 1920)
    assert (
        "vstack=2" in chain
        and "drawbox" in chain
        and chain.index("crop=636:720:644:0") < chain.index("crop=636:720:0:0")
    )
    e = render.merged_edits({"aspect": "9:16", "crop": {"mode": "pair"}, "pair": {"b_start": 3}})
    chain = render.build_video_chain(_probe(), e, {}, 1080, 1920, pair_input=1)
    assert "[1:v]" in chain and "vstack=2" in chain
    assert render.layout_seam(e, {}) == 0.5


def test_labels_drawn_on_both_panels():
    ass = captions.build_ass(1080, 1920, [], None, duration=10, seam=0.5, labels={"top": "GTA 6", "bottom": "GTA 5"})
    assert "GTA 6" in ass and "GTA 5" in ass and "\\pos(34,994)" in ass


def test_pair_render(sample_video, tmp_path):
    probe = ffmpeg.probe(sample_video)
    edits = {
        "aspect": "9:16",
        "quality": "draft",
        "crop": {"mode": "pair"},
        "pair": {"b_start": 22},
        "labels": {"top": "A", "bottom": "B"},
        "captions": {"enabled": False},
    }
    info = render.render(sample_video, probe, 2, 10, edits, {}, [], tmp_path / "o.mp4", tmp_path / "w")
    p = ffmpeg.probe(tmp_path / "o.mp4")
    assert (p.width, p.height) == (info["width"], info["height"]) and abs(p.duration - 8) < 0.3
