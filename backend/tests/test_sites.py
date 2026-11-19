"""Video-site links (YouTube & co) via yt-dlp. yt-dlp is replaced by a fake, so no network is used."""

from __future__ import annotations

from pathlib import Path

import pytest
import yt_dlp

from app.config import get_settings
from app.pipeline import ingest, sites
from app.pipeline.ffmpeg import Cancelled, MediaError

VIDEO = {
    "_type": "video",
    "id": "abc123",
    "title": "How we shipped in two weeks",
    "uploader": "Indie Hacker",
    "thumbnail": "https://i.ytimg.com/vi/abc123/hq.jpg",
    "duration": 312,
    "extractor_key": "Youtube",
    "webpage_url": "https://www.youtube.com/watch?v=abc123",
    "live_status": "not_live",
    "requested_formats": [{"filesize": 40_000_000}, {"filesize_approx": 4_000_000}],
}


class FakeYDL:
    """Stands in for yt_dlp.YoutubeDL: returns ``info`` and, on download, writes a file and reports progress."""

    info: dict = VIDEO
    error: str | None = None
    calls: list[dict] = []
    payload: Path | None = None  # a real video to "download"

    def __init__(self, opts):
        self.opts = opts
        FakeYDL.calls.append(opts)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        if FakeYDL.error:
            raise yt_dlp.utils.DownloadError(FakeYDL.error)
        return dict(FakeYDL.info)

    def process_ie_result(self, info, download=True):
        out = Path(self.opts["outtmpl"].replace("%(ext)s", "mp4"))
        total = 44_000_000
        for hook in self.opts["progress_hooks"]:
            for got in (0, 10_000_000, 25_000_000, 40_000_000):
                hook({"status": "downloading", "filename": "v.f137.mp4", "downloaded_bytes": got, "total_bytes": 40e6})
            hook({"status": "finished", "filename": "v.f137.mp4", "total_bytes": 40e6})
            hook({"status": "downloading", "filename": "v.f140.m4a", "downloaded_bytes": 2e6, "total_bytes": 4e6})
            hook({"status": "finished", "filename": "v.f140.m4a", "total_bytes": 4e6})
        out.write_bytes(FakeYDL.payload.read_bytes() if FakeYDL.payload else b"\0" * 64)
        return {**info, "requested_downloads": [{"filepath": str(out), "filesize": total}]}


@pytest.fixture
def fake_ytdlp(monkeypatch):
    FakeYDL.info, FakeYDL.error, FakeYDL.calls, FakeYDL.payload = dict(VIDEO), None, [], None
    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(sites, "ffmpeg_bin", lambda: "/usr/bin/ffmpeg")
    return FakeYDL


def test_youtube_link_is_importable(fake_ytdlp):
    info = ingest.inspect_url("https://www.youtube.com/watch?v=abc123&list=PLxyz&index=4&si=share")
    assert info.importable and info.kind == "platform" and info.platform == "YouTube"
    assert info.title == "How we shipped in two weeks" and info.author == "Indie Hacker"
    assert info.thumbnail == "https://i.ytimg.com/vi/abc123/mqdefault.jpg"
    assert info.duration == 312 and info.size_bytes == 44_000_000
    assert "AI Generate" in info.message
    assert any("permission" in w for w in info.warnings)
    opts = fake_ytdlp.calls[0]
    assert opts["noplaylist"] and opts["skip_download"] and "avc1" in opts["format"]


@pytest.mark.parametrize(
    "url",
    [
        "https://youtu.be/abc123",
        "https://www.youtube.com/shorts/abc123",
        "https://m.youtube.com/watch?v=abc123",
        "youtube.com/live/abc123",
        "https://www.tiktok.com/@someone/video/123",
        "https://vimeo.com/123456",
    ],
)
def test_site_link_forms(fake_ytdlp, url):
    assert ingest.inspect_url(url).importable


@pytest.mark.parametrize(
    "url,clean",
    [
        ("https://www.youtube.com/watch?v=abc&list=PL1&index=3&si=x&t=42", "https://www.youtube.com/watch?v=abc&t=42"),
        ("https://youtu.be/abc?si=share", "https://youtu.be/abc"),
        ("https://www.youtube.com/playlist?list=PL1", "https://www.youtube.com/playlist?list=PL1"),
        ("https://vimeo.com/1?share=copy", "https://vimeo.com/1?share=copy"),
    ],
)
def test_clean_site_url(url, clean):
    assert ingest.clean_site_url(url) == clean


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/@SomeChannel",
        "https://www.youtube.com/@SomeChannel/videos",
        "https://www.youtube.com/playlist?list=PL1",
        "https://www.youtube.com/channel/UC123",
        "https://www.youtube.com/results?search_query=cats",
    ],
)
def test_channels_and_playlists_are_refused_instantly(fake_ytdlp, url):
    with pytest.raises(MediaError, match="Open one video"):
        ingest.inspect_url(url)
    assert fake_ytdlp.calls == []  # refused before asking yt-dlp


def test_playlist_result_is_refused(fake_ytdlp):
    fake_ytdlp.info = {"_type": "playlist", "title": "Mix"}
    with pytest.raises(MediaError, match="playlist"):
        ingest.inspect_url("https://www.dailymotion.com/playlist/x1")


def test_live_and_too_long_videos_are_not_importable(fake_ytdlp):
    fake_ytdlp.info = {**VIDEO, "live_status": "is_live"}
    info = ingest.inspect_url("https://youtu.be/abc123")
    assert not info.importable and "Live" in info.message

    # a 10-hour stream replay is fine: it's scanned, and only the best parts are downloaded
    fake_ytdlp.info = {**VIDEO, "duration": 10 * 3600, "live_status": "was_live"}
    info = ingest.inspect_url("https://youtu.be/abc123")
    assert info.importable and info.scan and "only the best parts" in info.message

    fake_ytdlp.info = {**VIDEO, "duration": (get_settings().max_site_hours + 1) * 3600}
    info = ingest.inspect_url("https://youtu.be/abc123")
    assert not info.importable and "hours" in info.message


@pytest.mark.parametrize(
    "raw,expect",
    [
        ("ERROR: [youtube] abc: Private video. Sign in if you've been granted access", "private"),
        ("ERROR: [youtube] abc: Sign in to confirm your age.", "age-restricted"),
        ("ERROR: [youtube] abc: Sign in to confirm you're not a bot.", "isn't a bot"),
        ("ERROR: [youtube] abc: This video is unavailable", "unavailable"),
        ("ERROR: [youtube] abc: The uploader has not made this video available in your country", "region"),
        ("ERROR: [youtube:tab] PL1: YouTube said: The playlist does not exist.", "playlist"),
        ("ERROR: [vimeo] 1: The web client only works when logged-in. Use --cookies", "signed-in"),
        ("ERROR: Unsupported URL: https://example.com/", "isn't a video page"),
        ("ERROR: something new and strange", "couldn't be read"),
    ],
)
def test_errors_are_explained(fake_ytdlp, raw, expect):
    fake_ytdlp.error = raw
    with pytest.raises(MediaError, match=expect):
        ingest.inspect_url("https://www.youtube.com/watch?v=abc")


def test_cookies_are_opt_in(fake_ytdlp, monkeypatch):
    ingest.inspect_url("https://youtu.be/abc123")
    assert "cookiesfrombrowser" not in fake_ytdlp.calls[-1]
    monkeypatch.setattr(get_settings(), "ytdlp_cookies_browser", "edge")
    ingest.inspect_url("https://youtu.be/abc123")
    assert fake_ytdlp.calls[-1]["cookiesfrombrowser"] == ("edge",)


def test_metadata_only_when_ytdlp_is_off(monkeypatch):
    import httpx

    monkeypatch.setattr(get_settings(), "ytdlp_enabled", False)

    def handler(req):
        assert "oembed" in str(req.url)
        return httpx.Response(200, json={"title": "My Talk", "author_name": "Me", "thumbnail_url": "https://i/x.jpg"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    info = ingest.inspect_url("https://www.youtube.com/watch?v=abc", client=client)
    assert info.platform == "youtube" and not info.importable and info.title == "My Talk"


def test_download_reports_progress_and_lands_at_dst(fake_ytdlp, tmp_path):
    dst = tmp_path / "source.mp4"
    marks: list[float] = []
    ingest.download("https://youtu.be/abc123", dst, 4 << 30, on_progress=marks.append)
    assert dst.exists()
    assert marks == sorted(marks) and marks[-1] == 1.0
    assert 0.15 < marks[0] < 0.3  # 10 of 44 MB, not "done" just because a stream started at 0 bytes
    opts = fake_ytdlp.calls[-1]
    assert opts["merge_output_format"] == "mp4" and opts["max_filesize"] == 4 << 30
    assert opts["ffmpeg_location"]


def test_download_refuses_files_over_the_limit(fake_ytdlp, tmp_path):
    with pytest.raises(MediaError, match="larger than"):
        ingest.download("https://youtu.be/abc123", tmp_path / "source.mp4", 10 << 20)
    assert list(tmp_path.iterdir()) == []


def test_download_can_be_cancelled(fake_ytdlp, tmp_path):
    with pytest.raises(Cancelled):
        ingest.download("https://youtu.be/abc123", tmp_path / "source.mp4", 4 << 30, should_cancel=lambda: True)
    assert list(tmp_path.iterdir()) == []


def test_youtube_link_to_clips_through_the_api(fake_ytdlp, sample_video, monkeypatch):
    """Paste a YouTube link → AI Generate → rendered clips (yt-dlp and speech-to-text faked, the rest real)."""
    from fastapi.testclient import TestClient

    from app import jobs, tasks
    from app.main import app
    from app.pipeline import transcribe

    from .conftest import fake_words

    fake_ytdlp.payload = sample_video
    fake_ytdlp.info = {**VIDEO, "duration": 40}
    monkeypatch.setattr(
        tasks.transcribe,
        "transcribe",
        lambda *a, **k: transcribe.Transcript(language="en", words=fake_words(), engine="fake"),
    )
    with TestClient(app) as c:
        r = c.post("/api/auth/signup", json={"email": "yt@example.com", "password": "test-password-1", "name": "Y"})
        assert r.status_code == 200, r.text
        r = c.post("/api/url/check", json={"url": "https://youtu.be/abc123?si=share"})
        assert r.status_code == 200 and r.json()["importable"], r.text
        settings = {"count": 1, "min_dur": 8, "max_dur": 16, "aspect": "9:16", "quality": "draft"}
        r = c.post("/api/projects", json={"url": "https://youtu.be/abc123?si=share", "settings": settings})
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["name"] == "How we shipped in two weeks" and p["status"] == "queued"
        while jid := jobs._claim():
            jobs.run_job(jid)
        proj = c.get(f"/api/projects/{p['id']}").json()
        assert proj["status"] == "ready", proj["error"]
        assert proj["clips"] and proj["clips"][0]["render_status"] == "rendered"
        assert proj["source_type"] == "url" if "source_type" in proj else True
