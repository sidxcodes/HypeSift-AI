"""Fix with AI (rules + snapping + API) and AI thumbnails (designs, fitting, API)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import jobs, tasks
from app.main import app
from app.pipeline import clipfix, ffmpeg, thumbnail, transcribe

from .conftest import fake_words


@pytest.mark.parametrize(
    "req,op",
    [
        ("start 2 seconds earlier", {"op": "shift_start", "by": -2.0}),
        ("Start it three seconds later", {"op": "shift_start", "by": 3.0}),
        ("end 1.5 sec later please", {"op": "shift_end", "by": 1.5}),
        ("it ends mid sentence", {"op": "end_at_sentence", "direction": "later"}),
        ("remove the first sentence", {"op": "drop_first_sentence"}),
        ("make it 20 seconds", {"op": "set_length", "seconds": 20.0}),
        ("bigger captions", {"op": "caption_size", "scale": 1.2}),
        ("turn off the captions", {"op": "captions", "enabled": False}),
        ("use the heat style", {"op": "caption_preset", "value": "heat"}),
        ("the captions say gonna but it should be Goa", {"op": "fix_word", "wrong": "gonna", "right": "Goa"}),
        ("make it square", {"op": "aspect", "value": "1:1"}),
        ("show the whole frame, don't crop", {"op": "crop_mode", "value": "fit"}),
        ("change the title to Why most startups fail", {"op": "set_title", "text": "Why most startups fail"}),
    ],
)
def test_rules_understand_common_requests(req, op):
    assert op in clipfix.rule_ops(req)


def test_boundaries_snap_to_sentences():
    words = fake_words()
    clip = {"start": 5.0, "end": 20.0, "title": "t", "text": "", "edits": {}}
    res = clipfix.apply([{"op": "end_at_sentence", "direction": "later"}], clip, words, 40)
    ends = [w.e for w in words if w.w.endswith((".", "?", "!"))]
    assert any(abs(res["end"] - (e + 0.3)) < 0.01 for e in ends) and res["end"] >= 20.0
    res = clipfix.apply([{"op": "shift_start", "by": -1.9}], clip, words, 40)
    assert res["start"] < 5.0 and res["changes"] and res["edits"]["captions"]["chunks"] is None


def test_fix_word_in_chunks():
    ch = [{"s": 0, "e": 1, "text": "we are gonna win", "words": [{"w": "gonna", "s": 0, "e": 1}]}]
    out = clipfix.fix_words_in_chunks(ch, [["gonna", "going to"]])
    assert out[0]["text"] == "we are going to win" and out[0]["words"][0]["w"] == "going to"


def test_thumbnail_text_fits_and_highlights():
    ass = thumbnail._ass("INCREDIBLEWORDTHATISLONG HEADLINE|HEADLINE", thumbnail.DESIGNS["bold"], 1080, 1920)
    size = int(ass.split("Style: T,Anton,")[1].split(",")[0])
    assert size < thumbnail.DESIGNS["bold"]["size"]  # shrunk to fit
    assert "\\1c" in ass  # one word highlighted


def test_make_thumbnails(sample_video, tmp_path, monkeypatch):
    monkeypatch.setattr(thumbnail.llm, "status", lambda *a, **k: {"available": False, "model": "", "reason": ""})
    probe = ffmpeg.probe(sample_video)
    res = thumbnail.make_thumbnails(
        sample_video,
        probe,
        2,
        12,
        {"aspect": "9:16", "crop": {"mode": "center"}},
        {},
        "Shipping products fast",
        "Most people never launch.",
        tmp_path / "out",
        tmp_path / "w",
    )
    assert set(res["files"]) == {"bold", "pop", "clean"}
    for by in res["files"].values():
        v, w = ffmpeg.probe(by["vertical"]), ffmpeg.probe(by["wide"])
        assert (v.width, v.height) == (1080, 1920) and (w.width, w.height) == (1280, 720)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        assert (
            c.post(
                "/api/auth/signup", json={"email": "fix@example.com", "password": "test-password-1", "name": "F"}
            ).status_code
            == 200
        )
        yield c


def test_fix_and_thumbnail_api(client, sample_video, monkeypatch):
    monkeypatch.setattr(
        tasks.transcribe,
        "transcribe",
        lambda *a, **k: transcribe.Transcript(language="en", words=fake_words(), engine="fake"),
    )
    monkeypatch.setattr(thumbnail.llm, "status", lambda *a, **k: {"available": False, "model": "", "reason": ""})
    data = sample_video.read_bytes()
    up = client.post("/api/uploads", json={"filename": "talk.mp4", "size": len(data)}).json()
    client.put(f"/api/uploads/{up['id']}?offset=0", content=data)
    client.post(f"/api/uploads/{up['id']}/complete")
    p = client.post(
        "/api/projects",
        json={
            "upload_id": up["id"],
            "settings": {"count": 1, "min_dur": 8, "max_dur": 16, "quality": "draft", "use_llm": False},
        },
    ).json()
    while jid := jobs._claim():
        jobs.run_job(jid)
    clip = client.get(f"/api/projects/{p['id']}").json()["clips"][0]
    assert clip["thumbnails"] and len(clip["thumbnails"]["designs"]) == 3  # made automatically

    r = client.post(
        f"/api/clips/{clip['id']}/fix", json={"text": "start 2 seconds earlier and use the mint style"}
    ).json()
    assert (
        r["applied"]
        and r["job"]
        and any("earlier" in c for c in r["changes"])
        and r["clip"]["edits"]["captions"]["preset"] == "mint"
    )
    r = client.post(f"/api/clips/{clip['id']}/fix", json={"text": "blah blah"}).json()
    assert not r["applied"]
    while jid := jobs._claim():
        jobs.run_job(jid)
    r = client.post(f"/api/clips/{clip['id']}/thumbnails", json={"text": "MY OWN TEXT"})
    assert r.status_code == 200
    while jid := jobs._claim():
        jobs.run_job(jid)
    clip = client.get(f"/api/clips/{clip['id']}").json()["clip"]
    assert clip["thumbnails"]["text"] == "MY OWN TEXT"
