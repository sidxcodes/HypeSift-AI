"""URL import.

Supported:
  * Video-site links: YouTube (watch, youtu.be, Shorts, embed, live replays), Vimeo,
    TikTok, Instagram, X, Twitch, Facebook, Reddit, Dailymotion and the ~1,800 other
    sites the free, open-source yt-dlp understands (see ``sites.py``). Web pages that
    embed a video are tried the same way.
  * Direct links to a media file (``.mp4``, ``.mov``, ``.webm`` … or any URL that
    answers with a ``video/*`` content type) on a public host, e.g. your own cloud
    bucket, a CDN, Wikimedia Commons, archive.org.

Only import videos you own or have permission to use. If yt-dlp is switched off
(``HYPESIFT_YTDLP_ENABLED=false``) video-site links fall back to public metadata only.

Private / loopback / link-local addresses are refused (SSRF guard).
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlparse

import httpx

from . import sites
from .ffmpeg import MediaError

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}

PLATFORMS: dict[str, tuple[tuple[str, ...], str | None]] = {
    "youtube": (
        ("youtube.com", "youtu.be", "youtube-nocookie.com"),
        "https://www.youtube.com/oembed?format=json&url={url}",
    ),
    "vimeo": (("vimeo.com",), "https://vimeo.com/api/oembed.json?url={url}"),
    "tiktok": (("tiktok.com",), "https://www.tiktok.com/oembed?url={url}"),
    "instagram": (("instagram.com",), None),
    "twitch": (("twitch.tv",), None),
    "x": (("twitter.com", "x.com"), None),
    "facebook": (("facebook.com", "fb.watch"), None),
    "reddit": (("reddit.com", "redd.it"), None),
    "dailymotion": (("dailymotion.com", "dai.ly"), None),
}


def _ua() -> str:
    from ..config import get_settings

    return get_settings().http_user_agent


@dataclass
class UrlInfo:
    url: str
    kind: str  # direct | platform
    platform: str | None = None
    importable: bool = False
    title: str | None = None
    author: str | None = None
    thumbnail: str | None = None
    duration: float | None = None
    size_bytes: int | None = None
    content_type: str | None = None
    message: str = ""
    warnings: list[str] = field(default_factory=list)


def _host_matches(host: str, domains: tuple[str, ...]) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def assert_public_host(host: str) -> None:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise MediaError(f"Could not resolve host '{host}'.") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise MediaError("Links to private or local network addresses are not allowed.")


def normalize(url: str) -> str:
    url = url.strip()
    if not url:
        raise MediaError("Paste a video link first.")
    if "://" not in url:
        url = "https://" + url
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise MediaError("Only http(s) links are supported.")
    return url


def _ytdlp_on() -> bool:
    from ..config import get_settings

    return get_settings().ytdlp_enabled


def platform_of(url: str) -> str | None:
    host = (urlparse(url).hostname or "").lower()
    for name, (domains, _) in PLATFORMS.items():
        if _host_matches(host, domains):
            return name
    return None


def site_label(url: str) -> str | None:
    """A display name for a video-site link (None for direct file links)."""
    name = platform_of(url)
    return {"youtube": "YouTube", "tiktok": "TikTok", "x": "X"}.get(name, name.capitalize()) if name else None


def clean_site_url(url: str) -> str:
    """Drop playlist/radio parameters from YouTube links so only that one video is imported."""
    p = urlparse(url)
    host = (p.hostname or "").lower()
    if p.query and _host_matches(host, PLATFORMS["youtube"][0]) and p.path != "/playlist":
        keep = [(k, v) for k, v in parse_qsl(p.query) if k in ("v", "t", "start")]
        return p._replace(query=urlencode(keep)).geturl()
    return url


YOUTUBE_LISTS = ("/@", "/channel/", "/c/", "/user/", "/playlist", "/feed", "/results", "/hashtag/")


def refuse_lists(url: str) -> None:
    p = urlparse(url)
    if platform_of(url) == "youtube" and "v=" not in p.query and p.path.startswith(YOUTUBE_LISTS):
        raise MediaError("That's a YouTube channel, playlist or search page. Open one video and paste its link.")


def inspect_url(url: str, client: httpx.Client | None = None) -> UrlInfo:
    url = clean_site_url(normalize(url))
    refuse_lists(url)
    host = (urlparse(url).hostname or "").lower()
    own = client is None
    client = client or httpx.Client(timeout=15, follow_redirects=True, headers={"User-Agent": _ua()})
    try:
        name = platform_of(url)
        if name:
            if _ytdlp_on():
                return _site_info(url, site_label(url))
            return _platform_info(url, name, PLATFORMS[name][1], client)
        assert_public_host(host)
        try:
            return _direct_info(url, client)
        except WebPage:
            # Not a video file: maybe a page with an embedded video that yt-dlp can read.
            if _ytdlp_on():
                try:
                    info = _site_info(url, None)
                    info.kind = "page"
                    return info
                except MediaError as e:
                    if "playlist" in str(e) or "signed-in" in str(e):
                        raise
            raise MediaError(
                "That link opens a web page without a video HypeSift can read. Paste a video link "
                "(YouTube, Vimeo, TikTok …), a direct link to a video file, or upload the file."
            ) from None
    finally:
        if own:
            client.close()


def _site_info(url: str, label: str | None) -> UrlInfo:
    d = sites.probe(url)
    info = UrlInfo(
        url=url,
        kind="platform",
        platform=label or d["site"],
        importable=d["importable"],
        title=d["title"],
        author=d["author"],
        thumbnail=d["thumbnail"],
        duration=d["duration"],
        size_bytes=d["size_bytes"],
    )
    if d["importable"]:
        info.message = (
            f"{info.platform} video found. Press AI Generate and HypeSift downloads it, then makes the clips."
        )
        info.warnings.append("Only import videos you own or have permission to use.")
    else:
        info.message = d["reason"]
    return info


class WebPage(MediaError):
    """The link answered with an HTML page rather than a media file."""


def _platform_info(url: str, name: str, oembed: str | None, client: httpx.Client) -> UrlInfo:
    info = UrlInfo(url=url, kind="platform", platform=name, importable=False)
    if oembed:
        try:
            r = client.get(oembed.format(url=quote(url, safe="")))
            if r.status_code == 200:
                d = r.json()
                info.title = d.get("title")
                info.author = d.get("author_name")
                info.thumbnail = d.get("thumbnail_url")
            elif r.status_code in (401, 403, 404):
                info.warnings.append("This video looks private, removed or restricted.")
        except (httpx.HTTPError, ValueError):
            info.warnings.append("Public metadata could not be fetched right now.")
    pretty = {"youtube": "YouTube", "tiktok": "TikTok", "x": "X"}.get(name, name.capitalize())
    info.message = (
        f"{pretty} doesn't permit third-party apps to download its videos, so HypeSift won't fetch the media. "
        f"Upload your original file instead (for your own {pretty} videos you can download it from the "
        f"platform's creator tools) and the AI will take it from there."
    )
    return info


def _direct_info(url: str, client: httpx.Client) -> UrlInfo:
    info = UrlInfo(url=url, kind="direct")
    try:
        r = client.head(url)
        if r.status_code >= 400 or not r.headers.get("content-type"):
            r = client.get(url, headers={"Range": "bytes=0-0"})
    except httpx.HTTPError as e:
        raise MediaError(f"The link could not be reached ({type(e).__name__}).") from e
    if r.status_code == 401:
        raise MediaError("The link requires a login, so it can't be imported.")
    if r.status_code == 403:
        raise MediaError(
            "The server refused access (HTTP 403). The file may be private or the host may block "
            "automated downloads — upload the file instead."
        )
    if r.status_code == 404:
        raise MediaError("Nothing was found at that link (404).")
    if r.status_code >= 400:
        raise MediaError(f"The server answered with HTTP {r.status_code}.")
    ctype = (r.headers.get("content-type") or "").split(";")[0].strip().lower()
    size = r.headers.get("content-length")
    if r.status_code == 206 and "content-range" in r.headers:
        size = r.headers["content-range"].split("/")[-1]
    ext = Path(urlparse(str(r.url)).path).suffix.lower()
    is_video = ctype.startswith("video/") or (
        ctype in ("application/octet-stream", "binary/octet-stream", "") and ext in VIDEO_EXTS
    )
    if not is_video:
        if ctype.startswith("text/html"):
            raise WebPage("That link opens a web page, not a video file.")
        raise MediaError(f"That link isn't a video file (content type '{ctype or 'unknown'}').")
    info.importable = True
    info.content_type = ctype
    info.size_bytes = int(size) if size and size.isdigit() else None
    info.title = Path(urlparse(str(r.url)).path).stem.replace("_", " ").replace("-", " ")[:120] or "Imported video"
    info.message = "Direct video file — ready to import."
    return info


def download(
    url: str,
    dst: Path,
    max_bytes: int,
    on_progress: Callable[[float], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> None:
    """Fetch the video behind ``url`` into ``dst`` (an .mp4 path)."""
    url = clean_site_url(normalize(url))
    refuse_lists(url)
    if _ytdlp_on() and (platform_of(url) or not _looks_like_file(url)):
        try:
            _site_download(url, dst, max_bytes, on_progress, should_cancel)
            return
        except WebPage:
            pass  # no site extractor matched: treat it as a plain file link below
    _direct_download(url, dst, max_bytes, on_progress, should_cancel)


def _looks_like_file(url: str) -> bool:
    return Path(urlparse(url).path).suffix.lower() in VIDEO_EXTS


def _site_download(url: str, dst: Path, max_bytes: int, on_progress, should_cancel) -> None:
    generic = not platform_of(url)
    if generic:
        assert_public_host(urlparse(url).hostname or "")
    try:
        got = sites.download(url, dst, max_bytes, on_progress=on_progress, should_cancel=should_cancel)
    except MediaError as e:
        if generic and "isn't a video page" in str(e):
            raise WebPage(str(e)) from e
        raise
    if got != dst:
        got.replace(dst)


def _direct_download(url: str, dst: Path, max_bytes: int, on_progress, should_cancel) -> None:
    assert_public_host(urlparse(url).hostname or "")
    from .ffmpeg import Cancelled

    too_big = f"The file is larger than the {max_bytes // 2**20} MB limit."
    client = httpx.Client(timeout=httpx.Timeout(30, read=120), follow_redirects=True, headers={"User-Agent": _ua()})
    with client as c, c.stream("GET", url) as r:
        if r.status_code >= 400:
            raise MediaError(f"Download failed with HTTP {r.status_code}.")
        assert_public_host(r.url.host)  # re-check the final host after redirects
        total = int(r.headers.get("content-length") or 0)
        if total > max_bytes:
            raise MediaError(too_big)
        got = 0
        with open(dst, "wb") as f:
            for chunk in r.iter_bytes(1 << 20):
                got += len(chunk)
                if got > max_bytes:
                    raise MediaError(too_big)
                f.write(chunk)
                if on_progress and total:
                    on_progress(got / total)
                if should_cancel and should_cancel():
                    raise Cancelled("cancelled")
