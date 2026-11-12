"""URL import with honest, rights-aware rules.

Supported:
  * Direct links to a media file (``.mp4``, ``.mov``, ``.webm`` … or any URL that
    answers with a ``video/*`` content type) on a public host, e.g. your own cloud
    bucket, a CDN, Wikimedia Commons, archive.org.
  * YouTube / Vimeo / TikTok / Instagram links: we read **public metadata only**
    (official oEmbed endpoints). Their terms don't allow third-party apps to
    download the media, so we ask for an upload of the creator's own file instead
    (e.g. the original export, or YouTube Studio's "Download").

Private / loopback / link-local addresses are refused (SSRF guard).
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx

from .ffmpeg import MediaError

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}

PLATFORMS: dict[str, tuple[tuple[str, ...], str | None]] = {
    "youtube": (("youtube.com", "youtu.be", "youtube-nocookie.com"), "https://www.youtube.com/oembed?format=json&url={url}"),
    "vimeo": (("vimeo.com",), "https://vimeo.com/api/oembed.json?url={url}"),
    "tiktok": (("tiktok.com",), "https://www.tiktok.com/oembed?url={url}"),
    "instagram": (("instagram.com",), None),
    "twitch": (("twitch.tv",), None),
    "x": (("twitter.com", "x.com"), None),
    "facebook": (("facebook.com", "fb.watch"), None),
}

_UA = "HypeSiftAI/1.0 (+self-hosted video repurposing tool)"


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


def inspect_url(url: str, client: httpx.Client | None = None) -> UrlInfo:
    url = normalize(url)
    host = (urlparse(url).hostname or "").lower()
    own = client is None
    client = client or httpx.Client(timeout=15, follow_redirects=True, headers={"User-Agent": _UA})
    try:
        for name, (domains, oembed) in PLATFORMS.items():
            if _host_matches(host, domains):
                return _platform_info(url, name, oembed, client)
        assert_public_host(host)
        return _direct_info(url, client)
    finally:
        if own:
            client.close()


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
    if r.status_code in (401, 403):
        raise MediaError("The link requires a login or is restricted, so it can't be imported.")
    if r.status_code == 404:
        raise MediaError("Nothing was found at that link (404).")
    if r.status_code >= 400:
        raise MediaError(f"The server answered with HTTP {r.status_code}.")
    ctype = (r.headers.get("content-type") or "").split(";")[0].strip().lower()
    size = r.headers.get("content-length")
    if r.status_code == 206 and "content-range" in r.headers:
        size = r.headers["content-range"].split("/")[-1]
    ext = Path(urlparse(str(r.url)).path).suffix.lower()
    is_video = ctype.startswith("video/") or (ctype in ("application/octet-stream", "binary/octet-stream", "") and ext in VIDEO_EXTS)
    if not is_video:
        if ctype.startswith("text/html"):
            raise MediaError(
                "That link opens a web page, not a video file. Paste a direct link to the video file "
                "(ending in .mp4, .mov, .webm …) or upload the file."
            )
        raise MediaError(f"That link isn't a video file (content type '{ctype or 'unknown'}').")
    info.importable = True
    info.content_type = ctype
    info.size_bytes = int(size) if size and size.isdigit() else None
    info.title = Path(urlparse(str(r.url)).path).stem.replace("_", " ").replace("-", " ")[:120] or "Imported video"
    info.message = "Direct video file — ready to import."
    return info


def download(url: str, dst: Path, max_bytes: int, on_progress: Callable[[float], None] | None = None,
             should_cancel: Callable[[], bool] | None = None) -> None:
    url = normalize(url)
    assert_public_host(urlparse(url).hostname or "")
    with httpx.Client(timeout=httpx.Timeout(30, read=120), follow_redirects=True, headers={"User-Agent": _UA}) as c:
        with c.stream("GET", url) as r:
            if r.status_code >= 400:
                raise MediaError(f"Download failed with HTTP {r.status_code}.")
            # Re-check the final host after redirects.
            assert_public_host(r.url.host)
            total = int(r.headers.get("content-length") or 0)
            if total and total > max_bytes:
                raise MediaError(f"The file is larger than the {max_bytes // 2**20} MB limit.")
            got = 0
            with open(dst, "wb") as f:
                for chunk in r.iter_bytes(1 << 20):
                    got += len(chunk)
                    if got > max_bytes:
                        raise MediaError(f"The file is larger than the {max_bytes // 2**20} MB limit.")
                    f.write(chunk)
                    if on_progress and total:
                        on_progress(got / total)
                    if should_cancel and should_cancel():
                        from .ffmpeg import Cancelled

                        raise Cancelled("cancelled")
