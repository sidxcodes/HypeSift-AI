"""End-to-end through the HTTP API: sign up → chunked upload → AI Generate → rendered clips → download.

Speech-to-text is replaced with deterministic word timings (the real model is exercised
by scripts/smoke_pipeline.py); everything else — ffmpeg, signals, ranking, reframing,
caption burn-in, publishing copy, jobs, storage and auth — runs for real.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app import jobs, tasks
from app.main import app
from app.pipeline import ffmpeg, transcribe

from .conftest import fake_words


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _signup(client, email):
    r = client.post("/api/auth/signup", json={"email": email, "password": "test-password-1", "name": "T"})
    assert r.status_code == 200, r.text
    return r


def _run_queued():
    while jid := jobs._claim():
        jobs.run_job(jid)


def test_full_generate_flow(client, sample_video, monkeypatch):
    monkeypatch.setattr(
        transcribe,
        "transcribe",
        lambda *a, **k: transcribe.Transcript(language="en", words=fake_words(), engine="fake"),
    )
    monkeypatch.setattr(
        tasks.transcribe,
        "transcribe",
        lambda *a, **k: transcribe.Transcript(language="en", words=fake_words(), engine="fake"),
    )
    _signup(client, "creator@example.com")
    assert client.get("/api/auth/me").json()["email"] == "creator@example.com"

    data = sample_video.read_bytes()
    up = client.post("/api/uploads", json={"filename": "talk.mp4", "size": len(data)}).json()
    half = len(data) // 2
    r = client.put(f"/api/uploads/{up['id']}?offset=0", content=data[:half])
    assert r.json()["received"] == half
    # wrong offset is refused (resumable protocol)
    assert client.put(f"/api/uploads/{up['id']}?offset=5", content=b"x").status_code == 409
    client.put(f"/api/uploads/{up['id']}?offset={half}", content=data[half:])
    done = client.post(f"/api/uploads/{up['id']}/complete").json()
    assert done["status"] == "complete" and done["probe"]["duration"] > 39

    settings = {
        "count": 2,
        "min_dur": 8,
        "max_dur": 16,
        "aspect": "9:16",
        "quality": "draft",
        "caption_preset": "karaoke",
        "silence_removal": True,
        "platforms": ["youtube", "tiktok"],
    }
    p = client.post("/api/projects", json={"upload_id": up["id"], "settings": settings}).json()
    assert p["status"] == "queued" and p["job"]["kind"] == "generate"

    _run_queued()
    proj = client.get(f"/api/projects/{p['id']}").json()
    assert proj["status"] == "ready", proj["error"]
    assert proj["job"]["status"] == "succeeded" and proj["job"]["progress"] == 1.0
    assert 1 <= len(proj["clips"]) <= 2
    clip = proj["clips"][0]
    assert clip["render_status"] == "rendered"
    assert 0 <= clip["score"] <= 100 and clip["reasons"]
    assert set(clip["score_breakdown"]["dims"]) >= {
        "hook",
        "context",
        "pacing",
        "novelty",
        "emotion",
        "visual",
        "relevance",
    }
    assert clip["publish"]["platforms"]["youtube"]["titles"]
    assert "template" in clip["publish"]["engine"]  # LLM disabled in tests → honest label

    # the exported file is a real vertical video
    key = parse_qs(urlparse(clip["video_url"]).query)["key"][0]
    from app.storage import storage

    pr = ffmpeg.probe(storage.path(key))
    assert (pr.width, pr.height) == (720, 1280) and pr.has_audio

    # signed download works, tampered signature doesn't
    dl = client.get(clip["download_url"])
    assert dl.status_code == 200 and dl.headers["content-type"] == "video/mp4"
    assert "attachment" in dl.headers.get("content-disposition", "")
    assert client.get(clip["video_url"].replace("sig=", "sig=00")).status_code == 403
    assert client.get(clip["srt_url"]).text.startswith("1\n")

    # edit + re-render through the editor endpoint
    r = client.patch(
        f"/api/clips/{clip['id']}",
        json={
            "start": clip["start"] + 0.5,
            "title": "New title",
            "edits": {"aspect": "1:1", "captions": {"preset": "clean_minimal"}},
        },
    )
    assert r.status_code == 200 and r.json()["job"]["kind"] == "render"
    _run_queued()
    c2 = client.get(f"/api/clips/{clip['id']}").json()["clip"]
    assert c2["title"] == "New title" and c2["edits"]["aspect"] == "1:1"
    key2 = parse_qs(urlparse(c2["video_url"]).query)["key"][0]
    assert ffmpeg.probe(storage.path(key2)).width == 720  # 1:1 draft = 720x720

    # assistant maps a request to a real job
    a = client.post("/api/assistant", json={"project_id": p["id"], "text": "make it square"}).json()
    assert a["executed"] and a["action"]["type"] == "set_aspect"
    u = client.post("/api/assistant", json={"project_id": p["id"], "text": "add background music"}).json()
    assert not u["executed"] and "music" in u["message"].lower()

    # another account can't see this project or its clips
    client.post("/api/auth/logout")
    _signup(client, "other@example.com")
    assert client.get(f"/api/projects/{p['id']}").status_code == 404
    assert client.get(f"/api/clips/{clip['id']}").status_code == 404
    client.post("/api/auth/logout")
    assert client.get("/api/projects").status_code == 401


def test_bad_upload_is_rejected(client):
    _signup(client, "bad@example.com")
    payload = b"this is not a video" * 10
    up = client.post("/api/uploads", json={"filename": "fake.mp4", "size": len(payload)}).json()
    client.put(f"/api/uploads/{up['id']}?offset=0", content=payload)
    r = client.post(f"/api/uploads/{up['id']}/complete")
    assert r.status_code == 422
    assert client.post("/api/uploads", json={"filename": "x.exe", "size": 10}).status_code == 422
