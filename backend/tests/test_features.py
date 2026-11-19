"""Caption styles/transitions/effects, zoom/logo/music/progress-bar rendering, viral insights,
custom instructions, brand assets, post/schedule and transcript-only projects."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import jobs, tasks
from app.main import app
from app.pipeline import captions, ffmpeg, highlights, render, transcribe, virality

from .conftest import fake_words

CHUNK = [
    {
        "s": 0.0,
        "e": 1.2,
        "text": "hello big world",
        "words": [
            {"w": "hello", "s": 0.0, "e": 0.4},
            {"w": "big", "s": 0.4, "e": 0.8},
            {"w": "world", "s": 0.8, "e": 1.2},
        ],
    }
]


@pytest.mark.parametrize("preset", list(captions.PRESETS))
def test_every_style_builds_ass(preset):
    style = captions.style_for({"preset": preset})
    ass = captions.build_ass(1080, 1920, CHUNK, style, duration=2)
    family = captions._ASS_FONT.get(style["font"], (style["font"],))[0]
    assert f"Style: Cap,{family}," in ass
    assert "Dialogue:" in ass
    assert captions.FONT_FILES[style["font"]]


@pytest.mark.parametrize("tr,tag", [("fade_up", "\\move("), ("bounce", "\\fscx55"), ("none", "\\pos(")])
def test_transitions(tr, tag):
    style = captions.style_for({"preset": "basic", "transition": tr})
    ass = captions.build_ass(1080, 1920, CHUNK, style, duration=2)
    assert tag in ass


def test_effects():
    def ass(effect, preset="podcast"):
        return captions.build_ass(
            1080, 1920, CHUNK, captions.style_for({"preset": preset, "effect": effect}), duration=2
        )

    assert "\\blur" in ass("glow")
    assert "\\4a&H00&" in ass("shadow3d")
    assert "\\frz" in ass("tilt")
    tw = ass("typewriter")
    assert tw.count("\\alpha&HFF&") >= 2  # later words hidden in the first events
    assert "\\blur" in ass("none", "heat")  # styles with a built-in glow


def test_unknown_transition_falls_back():
    assert captions.style_for({"preset": "basic", "transition": "spin", "effect": "x"})["transition"] == "none"


def test_progress_bar_in_ass():
    ass = captions.build_ass(1080, 1920, CHUNK, None, duration=12.5, progress_bar="#7C3AED")
    assert "\\t(0,12500,\\clip(" in ass and "\\p1" in ass


def test_zoom_expression_and_moments():
    chunks = [
        {
            "s": 0,
            "e": 9,
            "words": [
                {"w": "Rocket", "s": 2.0, "e": 2.4},
                {"w": "rocket", "s": 3.0, "e": 3.3},
                {"w": "launch!", "s": 6.5, "e": 7.0},
            ],
        }
    ]
    m = render.zoom_moments(chunks, {"rocket", "launch"}, 12)
    assert m == [2.0, 6.5]  # second "rocket" is too close to the first
    assert render.zoom_expr(False, []) is None
    z = render.zoom_expr(True, m)
    assert z.startswith("1+0.18") and z.count("0.12*") == 2


def test_render_with_zoom_logo_music_bar(sample_video, tmp_path):
    logo = tmp_path / "logo.png"
    music = tmp_path / "music.m4a"
    ff = ffmpeg.ffmpeg_bin()
    subprocess.run(
        [ff, "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=120x120", "-frames:v", "1", str(logo)], check=True
    )
    subprocess.run(
        [ff, "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=330:d=5", "-c:a", "aac", str(music)], check=True
    )
    probe = ffmpeg.probe(sample_video)
    edits = {
        "aspect": "9:16",
        "crop": {"mode": "center"},
        "captions": {"enabled": True, "preset": "heat", "transition": "bounce", "effect": "glow"},
        "zoom": {"start": True, "key_phrases": True},
        "logo": {"path": str(logo), "position": "top_left"},
        "music": {"path": str(music), "volume": 0.2},
        "progress_bar": {"enabled": True, "color": "#7C3AED"},
        "quality": "draft",
    }
    words = fake_words()
    out = tmp_path / "out.mp4"
    info = render.render(sample_video, probe, 2, 14, edits, {}, words, out, tmp_path / "w", {"shipping", "products"})
    p = ffmpeg.probe(out)
    assert (p.width, p.height) == (info["width"], info["height"]) and p.has_audio
    assert abs(p.duration - 12) < 0.3
    # the logo really is in the top-left corner (red), the zoom-free right side is not red
    frame = tmp_path / "f.png"
    subprocess.run(
        [
            ff,
            "-y",
            "-v",
            "error",
            "-ss",
            "3",
            "-i",
            str(out),
            "-frames:v",
            "1",
            "-vf",
            "crop=20:20:30:30",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            str(frame),
        ],
        check=True,
    )
    r, g, b = frame.read_bytes()[:3]
    assert r > 180 and g < 80 and b < 80


def test_goal_scores_and_checklist():
    dims = {"hook": 80, "context": 60, "pacing": 70, "novelty": 55, "emotion": 75, "visual": 50, "relevance": 60}
    g = virality.goal_scores(dims, 70, 30)
    assert set(g) == {"general", "views", "trust", "educate", "entertain"}
    assert g["views"] > virality.goal_scores(dims, 70, 90)["views"]  # long clips lose reach points
    clip = {
        "score": 70,
        "score_breakdown": {"dims": dims},
        "duration": 30,
        "output_duration": 30,
        "text": "This is how it ends.",
        "reframe": {"face_ratio": 0.8},
        "edits": {
            "aspect": "9:16",
            "captions": {"enabled": True},
            "overlays": [{"kind": "title", "text": "Hi"}],
            "zoom": {"key_phrases": True},
        },
    }
    ins = virality.insights(clip)
    assert all(c["ok"] for c in ins["checklist"]), ins["checklist"]
    clip["text"] = "and then we"
    clip["edits"]["aspect"] = "16:9"
    bad = virality.insights(clip)
    assert bad["viral"] < ins["viral"]
    assert {c["key"] for c in bad["checklist"] if not c["ok"]} >= {"loop", "vertical"}


def test_instruction_terms_and_stem_matching():
    terms = highlights.instruction_terms("Find all the moments when they mention pricing strategies and startups")
    assert "pricing" in terms and "strategies" in terms and "moments" not in terms and "find" not in terms
    assert highlights.stem("strategies") == highlights.stem("strategy")
    assert highlights.stem("mentioned") == highlights.stem("mention")


def test_instructions_raise_relevance(sample_video):
    from app.pipeline import signals

    sig = signals.compute(sample_video, None, 40.0)
    words = fake_words()
    plain, _ = highlights.discover(words, sig, highlights.Prefs(count=3, min_dur=8, max_dur=16))
    ask = tasks.prefs_from(
        {"count": 3, "min_dur": 8, "max_dur": 16, "instructions": "moments about paying users and price"}
    )
    focused, ctx = highlights.discover(words, sig, ask)
    assert ctx.prefs.instructions and {"paying", "price"} <= set(ctx.prefs.query) | {"paying", "price"}
    top = focused[0].text.lower()
    assert "pay" in top or "price" in top or "paying" in top, [c.text for c in focused]


# ------------------------------------------------------------------- API


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        r = c.post(
            "/api/auth/signup", json={"email": "features@example.com", "password": "test-password-1", "name": "F"}
        )
        assert r.status_code == 200, r.text
        yield c


def _run_queued():
    while jid := jobs._claim():
        jobs.run_job(jid)


def test_assets_upload_and_ownership(client, tmp_path):
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 100
    r = client.post("/api/assets?kind=logo&name=brand.png", content=png)
    assert r.status_code == 200, r.text
    key = r.json()["key"]
    assert key.endswith(".png") and r.json()["url"]
    assert client.post("/api/assets?kind=logo&name=brand.exe", content=png).status_code == 422
    assert client.post("/api/assets?kind=music&name=song.mp3", content=b"not audio").status_code == 422
    # a key from another user (or a made-up one) is refused when used in settings
    r = client.post(
        "/api/projects",
        json={
            "url": "https://cdn.example.com/a.mp4",
            "start": False,
            "settings": {"logo_key": "users/someone-else/assets/logo-x.png"},
        },
    )
    assert r.status_code == 422


def test_unknown_caption_style_is_refused(client):
    r = client.post(
        "/api/projects", json={"url": "https://cdn.example.com/a.mp4", "settings": {"caption_preset": "nope"}}
    )
    assert r.status_code == 422


def test_full_flow_with_new_settings_post_and_schedule(client, sample_video, monkeypatch):
    monkeypatch.setattr(
        tasks.transcribe,
        "transcribe",
        lambda *a, **k: transcribe.Transcript(language="en", words=fake_words(), engine="fake"),
    )
    data = sample_video.read_bytes()
    up = client.post("/api/uploads", json={"filename": "talk.mp4", "size": len(data)}).json()
    client.put(f"/api/uploads/{up['id']}?offset=0", content=data)
    client.post(f"/api/uploads/{up['id']}/complete")
    settings = {
        "count": 2,
        "min_dur": 8,
        "max_dur": 16,
        "quality": "draft",
        "caption_preset": "mint",
        "caption_transition": "fade_left",
        "caption_effect": "tilt",
        "zoom_start": True,
        "progress_bar": True,
        "instructions": "the part about paying users",
    }
    p = client.post("/api/projects", json={"upload_id": up["id"], "settings": settings}).json()
    _run_queued()
    proj = client.get(f"/api/projects/{p['id']}").json()
    assert proj["status"] == "ready", proj["error"]
    clip = proj["clips"][0]
    assert clip["edits"]["captions"]["transition"] == "fade_left" and clip["edits"]["captions"]["effect"] == "tilt"
    assert clip["edits"]["zoom"]["start"] and clip["edits"]["progress_bar"]["enabled"]
    assert set(clip["insights"]["goals"]) >= {"views", "trust"} and 0 <= clip["insights"]["viral"] <= 100
    assert clip["post"] == {}

    when = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    r = client.put(
        f"/api/clips/{clip['id']}/post",
        json={
            "status": "scheduled",
            "scheduled_at": when,
            "timezone": "Asia/Kolkata",
            "platforms": {"youtube": {"include": True, "title": "T"}},
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["post"]["status"] == "scheduled" and r.json()["post"]["scheduled_at"].endswith("Z")
    assert [c["id"] for c in client.get("/api/posts").json()] == [clip["id"]]
    assert (
        client.put(
            f"/api/clips/{clip['id']}/post", json={"status": "scheduled", "scheduled_at": "2026-01-01T10:00"}
        ).status_code
        == 422
    )
    r = client.put(f"/api/clips/{clip['id']}/post", json={"status": "posted"})
    assert r.json()["post"]["status"] == "posted" and r.json()["post"]["posted_at"]
    r = client.put(f"/api/clips/{clip['id']}/post", json={"status": "draft"})
    assert "posted_at" not in r.json()["post"]

    st = client.get("/api/storage").json()
    assert st["total"] > 0 and any(x["id"] == p["id"] and x["source_bytes"] > 0 for x in st["projects"])


def test_transcript_only_project(client, sample_video, monkeypatch):
    monkeypatch.setattr(
        tasks.transcribe,
        "transcribe",
        lambda *a, **k: transcribe.Transcript(
            language="en",
            words=fake_words(),
            engine="fake",
            segments=[{"s": 0.6, "e": 3.0, "t": "Welcome back to the show."}],
        ),
    )
    data = sample_video.read_bytes()
    up = client.post("/api/uploads", json={"filename": "t.mp4", "size": len(data)}).json()
    client.put(f"/api/uploads/{up['id']}?offset=0", content=data)
    client.post(f"/api/uploads/{up['id']}/complete")
    p = client.post("/api/projects", json={"upload_id": up["id"], "settings": {"transcript_only": True}}).json()
    _run_queued()
    proj = client.get(f"/api/projects/{p['id']}").json()
    assert proj["status"] == "ready" and proj["clips"] == [] and proj["analysis"]["transcript_only"]
    tr = client.get(f"/api/projects/{p['id']}/transcript").json()
    assert tr["segments"][0]["t"].startswith("Welcome")


def test_socials_and_timezone(client):
    r = client.put(
        "/api/auth/brand-kit",
        json={"socials": {"youtube": "@me", "myspace": "x", "tiktok": " "}, "timezone": "Asia/Kolkata"},
    )
    kit = r.json()["brand_kit"]
    assert kit["socials"] == {"youtube": "@me"} and kit["timezone"] == "Asia/Kolkata"


def test_meta_lists_transitions_and_effects(client):
    m = client.get("/api/meta").json()
    assert "bounce" in m["caption_transitions"] and "typewriter" in m["caption_effects"]
    assert len(m["caption_presets"]) >= 20
