"""Video-site import (YouTube, Vimeo, TikTok, Instagram, X, Twitch, Facebook and the
other sites yt-dlp supports) built on the free, open-source yt-dlp.

* ``probe`` reads a link without downloading: title, channel, duration, thumbnail and
  whether it can be imported (live streams, playlists and over-long videos are refused
  with a clear reason).
* ``download`` fetches the best H.264 + AAC streams up to ``ytdlp_max_height`` (1080p by
  default, so browsers can preview it without a proxy) and merges them with FFmpeg,
  reporting real byte progress and honouring cancellation.

Only import videos you own or have permission to use: downloading from a platform can
conflict with its terms of service. HypeSift does not bypass DRM or log in to accounts,
unless you opt in to using your own browser's cookies (``HYPESIFT_YTDLP_COOKIES_BROWSER``).
"""

from __future__ import annotations

import contextlib
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..config import get_settings
from .ffmpeg import Cancelled, MediaError, ffmpeg_bin

log = logging.getLogger("hypesift.sites")

PRETTY = {
    "Youtube": "YouTube",
    "YoutubeTab": "YouTube",
    "Vimeo": "Vimeo",
    "TikTok": "TikTok",
    "Instagram": "Instagram",
    "Twitter": "X",
    "TwitchVod": "Twitch",
    "TwitchClips": "Twitch",
    "Facebook": "Facebook",
    "Reddit": "Reddit",
    "Dailymotion": "Dailymotion",
    "Generic": "Web page",
}

# (substring in yt-dlp's message, what the creator should read)
_ERRORS: list[tuple[str, str]] = [
    ("private video", "This video is private. Only public or unlisted videos can be imported — or upload the file."),
    (
        "confirm your age",
        "This video is age-restricted. Upload the file, or let HypeSift use your browser's YouTube "
        "login by setting HYPESIFT_YTDLP_COOKIES_BROWSER=edge in backend/.env.",
    ),
    (
        "inappropriate for some users",
        "This video is age-restricted. Upload the file, or set "
        "HYPESIFT_YTDLP_COOKIES_BROWSER=edge in backend/.env to use your own login.",
    ),
    (
        "not a bot",
        "YouTube asked to confirm this isn't a bot. Wait a few minutes and try again, update yt-dlp "
        "(run desktop\\install.ps1), or set HYPESIFT_YTDLP_COOKIES_BROWSER=edge in backend/.env.",
    ),
    ("members-only", "This video is for channel members only, so it can't be imported. Upload the file instead."),
    ("join this channel", "This video is for channel members only, so it can't be imported. Upload the file instead."),
    ("in your country", "This video is blocked in your region. Upload the file instead."),
    ("geo restrict", "This video is blocked in your region. Upload the file instead."),
    ("premieres in", "This video hasn't premiered yet. Try again after it's published."),
    ("live event will begin", "This live stream hasn't started yet."),
    ("drm", "This video is DRM-protected, so it can't be imported."),
    ("http error 429", "The site is rate-limiting downloads right now. Try again in a few minutes."),
    ("requested format is not available", "No downloadable video format was offered for this link."),
    ("max-filesize", "The video is larger than the upload limit."),
    (
        "unsupported url",
        "That link isn't a video page HypeSift can read. Paste a video link (YouTube, Vimeo, "
        "TikTok …) or a direct .mp4 link, or upload the file.",
    ),
    ("unable to extract", "The site changed its page format. Update yt-dlp (run desktop\\install.ps1) and try again."),
    ("playlist does not exist", "That playlist doesn't exist or is private. Paste a link to a single video."),
    ("video unavailable", "This video is unavailable — it may have been removed or made private."),
    ("is unavailable", "This video is unavailable — it may have been removed or made private."),
    (
        "logged-in",
        "This site only shares this video with signed-in users. Upload the file, or set "
        "HYPESIFT_YTDLP_COOKIES_BROWSER=edge in backend/.env to use your own browser login.",
    ),
    (
        "--cookies",
        "This site only shares this video with signed-in users. Upload the file, or set "
        "HYPESIFT_YTDLP_COOKIES_BROWSER=edge in backend/.env to use your own browser login.",
    ),
    (
        "sign in",
        "This video needs a signed-in account. Upload the file, or set "
        "HYPESIFT_YTDLP_COOKIES_BROWSER=edge in backend/.env to use your own browser login.",
    ),
    ("has been removed", "This video has been removed."),
    ("not found", "Nothing was found at that link."),
]


def friendly_error(exc: BaseException | str) -> str:
    msg = str(exc).lower()
    for needle, text in _ERRORS:
        if needle in msg:
            return text
    return "The video couldn't be read from that link. Check the link, or upload the file instead."


def _base_opts() -> dict[str, Any]:
    s = get_settings()
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        # A playlist/channel link is refused without paging through every video in it.
        "extract_flat": "in_playlist",
        "playlistend": 1,
        "socket_timeout": 30,
        "retries": 5,
        "fragment_retries": 5,
        "concurrent_fragment_downloads": 4,
        "logger": _QuietLogger(),
    }
    if s.ytdlp_cookies_browser:
        opts["cookiesfrombrowser"] = (s.ytdlp_cookies_browser,)
    return opts


class _QuietLogger:
    def debug(self, msg: str) -> None:
        pass

    def info(self, msg: str) -> None:
        pass

    def warning(self, msg: str) -> None:
        log.debug("yt-dlp: %s", msg)

    def error(self, msg: str) -> None:
        log.info("yt-dlp: %s", msg)


def _format_selector(max_height: int) -> str:
    h = max_height
    # Prefer H.264 + AAC (plays in every browser, no proxy needed), then anything up to h, then best.
    return (
        f"bv*[height<={h}][vcodec^=avc1]+ba[ext=m4a]/bv*[height<={h}]+ba/"
        f"b[height<={h}][vcodec^=avc1]/b[height<={h}]/bv*+ba/b"
    )


def _extract(url: str, opts: dict[str, Any]) -> dict[str, Any]:
    import yt_dlp

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as e:
        raise MediaError(friendly_error(e)) from e
    if not info:
        raise MediaError("Nothing was found at that link.")
    if info.get("_type") == "playlist":
        raise MediaError("That's a playlist or channel. Open one video and paste its link.")
    return info


def summarize(info: dict[str, Any]) -> dict[str, Any]:
    """The fields the UI needs, plus a reason when the video can't be imported."""
    s = get_settings()
    duration = info.get("duration")
    reason = None
    live = info.get("live_status") or ("is_live" if info.get("is_live") else None)
    if live in ("is_live", "is_upcoming", "post_live"):
        reason = (
            "Live streams can't be clipped while they're live. Try again once the stream has ended "
            "and the replay is processed."
        )
    elif duration and duration > s.max_duration_minutes * 60:
        reason = (
            f"This video is {duration / 60:.0f} minutes long; videos up to "
            f"{s.max_duration_minutes} minutes are supported."
        )
    fmts = info.get("requested_formats") or [info]
    size = sum(int(f.get("filesize") or f.get("filesize_approx") or 0) for f in fmts) or None
    site = PRETTY.get(info.get("extractor_key") or "", info.get("extractor_key") or "Video site")
    thumb = info.get("thumbnail")
    if site == "YouTube" and info.get("id"):
        thumb = f"https://i.ytimg.com/vi/{info['id']}/mqdefault.jpg"  # 320x180: light, 16:9, always present
    return {
        "title": info.get("title"),
        "author": info.get("uploader") or info.get("channel"),
        "thumbnail": thumb,
        "duration": duration,
        "size_bytes": size,
        "site": site,
        "webpage_url": info.get("webpage_url") or info.get("original_url"),
        "importable": reason is None,
        "reason": reason,
    }


def probe(url: str) -> dict[str, Any]:
    s = get_settings()
    opts = _base_opts() | {"skip_download": True, "format": _format_selector(s.ytdlp_max_height)}
    return summarize(_extract(url, opts))


def download(
    url: str,
    dst: Path,
    max_bytes: int,
    on_progress: Callable[[float], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> Path:
    """Download into ``dst``'s folder as ``<dst stem>.<ext>`` (normally .mp4) and return the file path."""
    import yt_dlp

    s = get_settings()
    dst.parent.mkdir(parents=True, exist_ok=True)
    files: dict[str, tuple[int, int]] = {}
    best = [0.0]
    expected = [0]

    def hook(d: dict[str, Any]) -> None:
        if should_cancel and should_cancel():
            raise Cancelled("cancelled")
        if d.get("status") not in ("downloading", "finished"):
            return
        total = int(d.get("total_bytes") or d.get("total_bytes_estimate") or 0)
        got = d.get("downloaded_bytes")
        got = int(got) if got is not None else (total if d["status"] == "finished" else 0)
        files[d.get("filename") or "?"] = (got, total)
        done = sum(g for g, _ in files.values())
        whole = max(sum(t for _, t in files.values()), expected[0])
        if on_progress and whole:
            frac = min(1.0, done / whole)
            if frac > best[0]:
                best[0] = frac
                on_progress(frac * 0.97)  # the last few % is the FFmpeg merge

    opts = _base_opts() | {
        "format": _format_selector(s.ytdlp_max_height),
        "merge_output_format": "mp4",
        "outtmpl": str(dst.parent / f"{dst.stem}.%(ext)s"),
        "ffmpeg_location": os.path.dirname(ffmpeg_bin()),
        "max_filesize": max_bytes,
        "progress_hooks": [hook],
        "overwrites": True,
        # A single-file format (no merge) can be WebM/FLV: remux it so the source is always .mp4.
        "postprocessors": [{"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}],
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info or info.get("_type") == "playlist":
                raise MediaError("That's a playlist or channel. Open one video and paste its link.")
            summary = summarize(info)
            if not summary["importable"]:
                raise MediaError(summary["reason"])
            if summary["size_bytes"] and summary["size_bytes"] > max_bytes:
                raise MediaError(f"The video is larger than the {max_bytes // 2**20} MB limit.")
            expected[0] = summary["size_bytes"] or 0
            info = ydl.process_ie_result(info, download=True)
    except Cancelled:
        _cleanup(dst)
        raise
    except yt_dlp.utils.DownloadError as e:
        _cleanup(dst)
        if should_cancel and should_cancel():
            raise Cancelled("cancelled") from e
        raise MediaError(friendly_error(e)) from e
    except MediaError:
        _cleanup(dst)
        raise
    downloads = (info or {}).get("requested_downloads") or []
    path = Path(downloads[0]["filepath"]) if downloads and downloads[0].get("filepath") else dst
    if not path.exists():
        candidates = sorted(dst.parent.glob(f"{dst.stem}.*"), key=lambda p: p.stat().st_size, reverse=True)
        candidates = [c for c in candidates if c.suffix not in (".part", ".ytdl")]
        if not candidates:
            raise MediaError("No video file was produced. It may be larger than the size limit — try a shorter video.")
        path = candidates[0]
    if on_progress:
        on_progress(1.0)
    return path


def _cleanup(dst: Path) -> None:
    for f in dst.parent.glob(f"{dst.stem}.*"):
        with contextlib.suppress(OSError):
            f.unlink()
