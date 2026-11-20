from app.pipeline import render
from app.pipeline.ffmpeg import Probe

RF = {"facecam": {"box": [0.02, 0.05, 0.25, 0.3]}}


def test_defaults_follow_the_detected_cam():
    L = render.facecam_layout(1920, 1080, 1080, 1920, RF, None)
    assert L["cam_h"] == 768 and L["game_h"] == 1152 and not L["swap"]
    cx, cy, cw, ch = L["cam"]
    box_l, box_r = 0.02 * 1920, 0.27 * 1920
    assert box_l <= cx and cx + cw <= box_r and abs(cw / ch - 1080 / 768) < 0.05  # cover-crop inside the box
    gx, gy, gw, gh = L["game"]
    assert gx >= 0.27 * 1920 - 2  # the game panel slides past the webcam


def test_manual_overrides_split_zoom_and_swap():
    lay = {"split": 0.3, "cam": {"x": 0.5, "y": 0.5, "w": 0.2}, "game": {"w": 0.4}, "swap": True}
    L = render.facecam_layout(1920, 1080, 1080, 1920, {}, lay)  # no cam detected: placed by hand
    assert L["cam_h"] == 576 and L["swap"] and abs(L["seam"] - 0.7) < 1e-9
    cx, cy, cw, ch = L["cam"]
    assert abs(cw - 384) <= 2 and abs(cx + cw / 2 - 960) <= 2
    chain = render.build_video_chain(
        Probe(
            duration=10,
            width=1920,
            height=1080,
            fps=30,
            has_audio=True,
            video_codec="h264",
            audio_codec="aac",
            size_bytes=1,
        ),
        render.merged_edits({"crop": {"mode": "facecam"}, "layout": lay}),
        {},
        1080,
        1920,
    )
    assert "[pg][pc]vstack" in chain  # cam at the bottom
    assert render.layout_seam({"crop": {"mode": "facecam"}, "aspect": "9:16", "layout": lay}, {}) == 0.7
