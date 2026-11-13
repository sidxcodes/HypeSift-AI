import httpx
import pytest

from app.pipeline import assistant, ingest
from app.pipeline.ffmpeg import MediaError


@pytest.mark.parametrize(
    "text,expect",
    [
        ("Find the funniest 30-second moment", {"type": "find_clips", "count": 1, "mood": "funny"}),
        ("Make five gaming highlight clips", {"type": "find_clips", "count": 5, "genre": "gaming"}),
        ("Find an emotional reaction near the end", {"type": "find_clips", "mood": "emotional", "position": "end"}),
        ("Use bold yellow captions", {"type": "set_captions", "preset": "bold_creator"}),
        ("Generate an Instagram caption for this clip", {"type": "generate_publish", "platforms": ["instagram"]}),
        ("make it square", {"type": "set_aspect", "aspect": "1:1"}),
        ("remove silences", {"type": "set_silence_removal", "enabled": True}),
        ("add some background music", {"type": "unsupported"}),
    ],
)
def test_assistant_parses_spec_examples(text, expect):
    a = assistant.parse(text)
    for k, v in expect.items():
        assert a.get(k) == v, (text, a)


def test_assistant_duration_and_colour():
    a = assistant.parse("Find the funniest 30-second moment")
    assert a["min_dur"] < 30 < a["max_dur"]
    c = assistant.parse("Use bold yellow captions")
    assert c["style"]["highlight"] == "#FFE14D"


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_html_page_is_rejected(monkeypatch):
    monkeypatch.setattr(ingest, "assert_public_host", lambda h: None)

    def no_video(url):
        raise MediaError("That link isn't a video page HypeSift can read.")

    monkeypatch.setattr(ingest.sites, "probe", no_video)

    def handler(req):
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<html>")

    with pytest.raises(MediaError, match="web page"):
        ingest.inspect_url("https://example.com/page", client=_client(handler))


def test_direct_video_is_importable(monkeypatch):
    monkeypatch.setattr(ingest, "assert_public_host", lambda h: None)

    def handler(req):
        return httpx.Response(200, headers={"content-type": "video/mp4", "content-length": "1234"})

    info = ingest.inspect_url("https://cdn.example.com/my_talk.mp4", client=_client(handler))
    assert info.importable and info.size_bytes == 1234 and info.title == "my talk"


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "10.0.0.5", "169.254.169.254"])
def test_private_hosts_are_blocked(host):
    with pytest.raises(MediaError):
        ingest.assert_public_host(host)
