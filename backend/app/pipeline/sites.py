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
import copy
import logging
import os
import shutil
import time
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
    node = shutil.which("node")
    if node:  # YouTube needs a JavaScript runtime to unlock every format; Node.js is already installed
        opts["js_runtimes"] = {"node": {"path": node}}
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
    elif duration and duration > s.max_site_hours * 3600:
        reason = f"This video is {duration / 3600:.0f} hours long; links up to {s.max_site_hours} hours are supported."
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
        # long videos are scanned first and only the best sections are downloaded
        "scan": bool(duration and duration > s.scan_threshold_minutes * 60),
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


# ----------------------------------------------------------------------------- long videos
#
# For long videos (streams, VODs, hour-long podcasts) HypeSift doesn't download everything:
# it reads the site's own captions (a full timed transcript in seconds) and YouTube's
# "Most replayed" graph, picks the best moments, then downloads only those sections.


def scan_info(url: str) -> dict[str, Any]:
    """Full metadata for a link (captions list, heatmap, chapters) without downloading media."""
    import yt_dlp

    try:
        with yt_dlp.YoutubeDL(_base_opts() | {"skip_download": True}) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as e:
        raise MediaError(friendly_error(e)) from e
    if not info or info.get("_type") == "playlist":
        raise MediaError("That's a playlist or channel. Open one video and paste its link.")
    return info


def heatmap(info: dict[str, Any]) -> list[tuple[float, float, float]]:
    """YouTube's "Most replayed" graph as (start, end, 0-1) spans; empty when the video has none."""
    out = []
    for h in info.get("heatmap") or []:
        try:
            out.append((float(h["start_time"]), float(h["end_time"]), float(h["value"])))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _caption_track(info: dict[str, Any]) -> tuple[list[dict], str, bool] | None:
    """(formats, language, automatic) of the best caption track for scanning.

    Prefer English (our scoring and the local LLM read English best; YouTube's auto-translation
    keeps the original timing), then the video's own language, manual before automatic."""
    manual = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}
    lang = (info.get("language") or "").split("-")[0]
    orig = next((k for k in auto if k.endswith("-orig")), None)
    order: list[tuple[dict, str, bool]] = []
    # Manual captions first (best quality), then the auto captions in the spoken language. YouTube's
    # auto-translated English is tried last: it is rate-limited far more often, and HypeSift
    # translates the chosen parts itself anyway.
    for k in [k for k in manual if k.split("-")[0] in (lang, "en")]:
        order.append((manual, k, False))
    if orig:
        order.append((auto, orig, True))
    if lang in auto:
        order.append((auto, lang, True))
    if "en" in auto:
        order.append((auto, "en", True))
    order += [(manual, k, False) for k in manual]
    seen: set[str] = set()
    out = []
    for src, k, is_auto in order:
        if src.get(k) and k not in seen and any(f.get("ext") == "json3" for f in src[k]):
            seen.add(k)
            out.append((src[k], k, is_auto))
    return out


def caption_words(url: str, info: dict[str, Any], work: Path) -> tuple[list, str] | None:
    """Timed words from the site's captions (YouTube json3), or None when there are none.

    Tracks are fetched with yt-dlp's own subtitle downloader (it sends the parameters YouTube
    expects); auto-translated tracks are often rate-limited, so each candidate is tried in turn."""
    import json

    import yt_dlp

    work.mkdir(parents=True, exist_ok=True)
    data = None
    lang = ""
    for _formats, k, is_auto in _caption_track(info) or []:
        opts = _base_opts() | {
            "skip_download": True,
            "writeautomaticsub": is_auto,
            "writesubtitles": not is_auto,
            "subtitleslangs": [k],
            "subtitlesformat": "json3",
            "outtmpl": str(work / "subs.%(ext)s"),
        }
        for attempt in range(3):  # YouTube answers "429 Too Many Requests" in bursts: wait and retry
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.process_ie_result(copy.deepcopy(info), download=True)
                break
            except Exception as e:  # noqa: BLE001 - try again / the next track; the caller falls back to audio
                log.info("caption track %s failed (try %d): %s", k, attempt + 1, e)
                if "429" not in str(e) or attempt == 2:
                    break
                time.sleep(4 * (attempt + 1))
        f = work / f"subs.{k}.json3"
        if f.exists() and f.stat().st_size > 100:
            data, lang = json.loads(f.read_text(encoding="utf-8")), k
            break
    words = _json3_words(data) if data else []
    return (words, lang) if words else None


def _json3_words(data: dict) -> list:
    from .transcribe import Word

    words: list[Word] = []
    for ev in data.get("events") or []:
        segs = [s for s in ev.get("segs") or [] if (s.get("utf8") or "").strip()]
        if not segs:
            continue
        t0 = ev.get("tStartMs", 0) / 1000
        dur = (ev.get("dDurationMs") or 0) / 1000
        tokens = []
        for s in segs:
            parts = s["utf8"].split()
            off = (s.get("tOffsetMs") or 0) / 1000
            tokens += [(p, off) for p in parts]
        has_offsets = any(s.get("tOffsetMs") for s in segs)
        for i, (w, off) in enumerate(tokens):
            ws = t0 + (off if has_offsets else dur * i / max(1, len(tokens)))
            words.append(Word(w, round(ws, 3), round(ws + 0.3, 3), 0.8))
    words.sort(key=lambda w: w.s)
    for a, b in zip(words, words[1:], strict=False):  # end each word where the next begins
        a.e = round(max(a.s + 0.05, min(a.s + 1.2, b.s)), 3)
    return words if len(words) >= 20 else []


def download_audio(url: str, dst_dir: Path, should_cancel: Callable[[], bool] | None = None) -> Path:
    """Smallest audio-only stream, for scanning long videos that have no captions."""
    import yt_dlp

    def hook(d: dict[str, Any]) -> None:
        if should_cancel and should_cancel():
            raise Cancelled("cancelled")

    dst_dir.mkdir(parents=True, exist_ok=True)
    opts = _base_opts() | {
        "format": "wa[acodec=opus]/wa/ba",
        "outtmpl": str(dst_dir / "scan-audio.%(ext)s"),
        "progress_hooks": [hook],
        "overwrites": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except yt_dlp.utils.DownloadError as e:
        raise MediaError(friendly_error(e)) from e
    got = (info or {}).get("requested_downloads") or []
    path = Path(got[0]["filepath"]) if got and got[0].get("filepath") else None
    if not path or not path.exists():
        cands = list(dst_dir.glob("scan-audio.*"))
        if not cands:
            raise MediaError("The audio couldn't be downloaded for scanning.")
        path = cands[0]
    return path


def download_sections(
    url: str,
    dst: Path,
    ranges: list[tuple[float, float]],
    on_progress: Callable[[float], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> list[dict[str, float]]:
    """Download only ``ranges`` (seconds in the original video) and join them into ``dst``.

    Returns the section map [{orig_start, orig_end, start, end}] (start/end = position in dst)."""
    import yt_dlp

    s = get_settings()
    work = dst.parent / "sections"
    work.mkdir(parents=True, exist_ok=True)
    parts: list[Path] = []
    opts = _base_opts() | {
        "format": _format_selector(s.ytdlp_max_height),
        "merge_output_format": "mp4",
        "outtmpl": str(work / "part.%(ext)s"),
        "ffmpeg_location": os.path.dirname(ffmpeg_bin()),
        "overwrites": True,
        "postprocessors": [{"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}],
    }
    from concurrent.futures import ThreadPoolExecutor, as_completed

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)  # read the page once
    except yt_dlp.utils.DownloadError as e:
        raise MediaError(friendly_error(e)) from e

    def fetch(i: int, a: float, b: float) -> Path:
        # Each range is fetched with stream copy (cut at the nearest keyframe; the join below
        # re-encodes once anyway). Seeking inside a huge remote file is slow, so parts run in parallel.
        if should_cancel and should_cancel():
            raise Cancelled("cancelled")
        part_opts = opts | {
            "outtmpl": str(work / f"part-{i:02d}.%(ext)s"),
            "download_ranges": yt_dlp.utils.download_range_func(None, [(a, b)]),
        }
        with yt_dlp.YoutubeDL(part_opts) as ydl:
            ydl.process_ie_result(copy.deepcopy(info), download=True)
        got = [p for p in work.glob(f"part-{i:02d}.*") if p.suffix == ".mp4"]
        if not got:
            raise MediaError("A section of the video couldn't be downloaded.")
        return got[0]

    found: dict[int, Path] = {}
    try:
        with ThreadPoolExecutor(max_workers=min(8, len(ranges))) as pool:
            futs = {pool.submit(fetch, i, a, b): i for i, (a, b) in enumerate(ranges)}
            for f in as_completed(futs):
                found[futs[f]] = f.result()
                if on_progress:
                    on_progress(len(found) / len(ranges) * 0.9)
    except yt_dlp.utils.DownloadError as e:
        raise MediaError(friendly_error(e)) from e
    parts = [found[i] for i in range(len(ranges))]
    # join: re-encode once so every part shares the same codec settings and timestamps start at 0
    from . import ffmpeg as ff

    sections, t = [], 0.0
    for (a, _b), p in zip(ranges, parts, strict=True):
        d = ff.probe(p).duration
        sections.append(
            {"orig_start": round(a, 3), "orig_end": round(a + d, 3), "start": round(t, 3), "end": round(t + d, 3)}
        )
        t += d
    probe0 = ff.probe(parts[0])
    W, H = probe0.width // 2 * 2, probe0.height // 2 * 2
    has_a = all(ff.probe(p).has_audio for p in parts)
    inputs: list[str] = []
    chains = []
    for i, p in enumerate(parts):
        inputs += ["-i", str(p)]
        chains.append(
            f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,"
            f"setsar=1,fps=30,format=yuv420p[v{i}]"
            + (f";[{i}:a]aresample=48000,aformat=channel_layouts=stereo[a{i}]" if has_a else "")
        )
    pairs = "".join(f"[v{i}][a{i}]" if has_a else f"[v{i}]" for i in range(len(parts)))
    graph = ";".join(chains) + f";{pairs}concat=n={len(parts)}:v=1:a={1 if has_a else 0}[v]" + ("[a]" if has_a else "")
    args = [ff.ffmpeg_bin(), "-y", "-v", "error", *inputs, "-filter_complex", graph, "-map", "[v]"]
    if has_a:
        args += ["-map", "[a]", "-c:a", "aac", "-b:a", "160k"]
    args += [*ff.encoder_args("high"), "-movflags", "+faststart", str(dst)]
    ff.run_with_progress(args, t, lambda f: on_progress and on_progress(0.9 + 0.1 * f), should_cancel)
    import shutil

    shutil.rmtree(work, ignore_errors=True)
    return sections


def _cleanup(dst: Path) -> None:
    for f in dst.parent.glob(f"{dst.stem}.*"):
        with contextlib.suppress(OSError):
            f.unlink()
