"""Thin, testable wrappers around ffmpeg / ffprobe."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from ..config import get_settings

log = logging.getLogger("hypesift.ffmpeg")

_NO_WINDOW = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW


class MediaError(RuntimeError):
    """Raised for unreadable / unsupported media, with a user-facing message."""


class Cancelled(RuntimeError):
    pass


@lru_cache
def _resolve(name: str) -> str:
    configured = getattr(get_settings(), f"{name}_bin")
    found = shutil.which(configured)
    if found:
        return found
    # winget installs ffmpeg outside PATH until a new shell starts; look there too.
    local = os.environ.get("LOCALAPPDATA")
    if local:
        for p in Path(local, "Microsoft", "WinGet").rglob(f"{name}.exe"):
            return str(p)
    raise MediaError(f"{name} was not found. Install FFmpeg and make sure it is on PATH.")


def ffmpeg_bin() -> str:
    return _resolve("ffmpeg")


def ffprobe_bin() -> str:
    return _resolve("ffprobe")


def run(args: list[str], timeout: float | None = None) -> subprocess.CompletedProcess:
    log.debug("exec %s", " ".join(args[:12]))
    return subprocess.run(
        args, capture_output=True, timeout=timeout, creationflags=_NO_WINDOW, check=False
    )


@dataclass
class Probe:
    duration: float
    width: int
    height: int
    fps: float
    has_audio: bool
    video_codec: str
    audio_codec: str | None
    size_bytes: int
    rotation: int = 0

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def probe(path: Path) -> Probe:
    r = run(
        [ffprobe_bin(), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        timeout=60,
    )
    if r.returncode != 0:
        raise MediaError("This file could not be read as a video. It may be corrupt or an unsupported format.")
    info = json.loads(r.stdout or b"{}")
    streams = info.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not v:
        raise MediaError("No video stream was found in this file.")
    try:
        num, den = (v.get("avg_frame_rate") or v.get("r_frame_rate") or "30/1").split("/")
        fps = float(num) / float(den) if float(den) else 30.0
    except (ValueError, ZeroDivisionError):
        fps = 30.0
    duration = float(info.get("format", {}).get("duration") or v.get("duration") or 0)
    rotation = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rotation = int(sd["rotation"])
    w, h = int(v.get("width", 0)), int(v.get("height", 0))
    if abs(rotation) in (90, 270):
        w, h = h, w
    if duration <= 0 or w <= 0 or h <= 0:
        raise MediaError("The video has no readable duration or dimensions.")
    return Probe(
        duration=duration,
        width=w,
        height=h,
        fps=round(fps, 3) if 1 <= fps <= 240 else 30.0,
        has_audio=a is not None,
        video_codec=v.get("codec_name", "?"),
        audio_codec=a.get("codec_name") if a else None,
        size_bytes=int(info.get("format", {}).get("size") or path.stat().st_size),
        rotation=rotation,
    )


def extract_audio(src: Path, dst: Path, sample_rate: int = 16000) -> None:
    r = run([ffmpeg_bin(), "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", str(sample_rate),
             "-c:a", "pcm_s16le", str(dst)], timeout=3600)
    if r.returncode != 0:
        raise MediaError("Audio could not be extracted: " + _tail(r.stderr))


def read_wav_mono(path: Path) -> tuple[np.ndarray, int]:
    import wave

    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    return data, sr


def thumbnail(src: Path, t: float, dst: Path, width: int = 640) -> None:
    r = run([ffmpeg_bin(), "-y", "-v", "error", "-ss", f"{max(t, 0):.3f}", "-i", str(src), "-frames:v", "1",
             "-vf", f"scale={width}:-2", "-q:v", "3", str(dst)], timeout=120)
    if r.returncode != 0 or not dst.exists():
        raise MediaError("Thumbnail extraction failed: " + _tail(r.stderr))


def read_frames(src: Path, start: float, end: float, fps: float, width: int) -> tuple[np.ndarray, float]:
    """Decode a low-res grey frame stack for analysis. Returns (frames[N,H,W], scale)."""
    p = probe(src)
    height = int(round(p.height * width / p.width / 2) * 2)
    r = run([ffmpeg_bin(), "-v", "error", "-ss", f"{start:.3f}", "-t", f"{max(end - start, 0.1):.3f}",
             "-i", str(src), "-vf", f"fps={fps},scale={width}:{height}", "-pix_fmt", "gray",
             "-f", "rawvideo", "-"], timeout=1800)
    if r.returncode != 0:
        raise MediaError("Frame decoding failed: " + _tail(r.stderr))
    frame_size = width * height
    n = len(r.stdout) // frame_size
    frames = np.frombuffer(r.stdout[: n * frame_size], dtype=np.uint8).reshape(n, height, width)
    return frames, p.width / width


@lru_cache
def video_encoder() -> str:
    """Pick NVENC when the GPU can actually encode, otherwise libx264."""
    pref = get_settings().video_encoder
    if pref != "auto":
        return pref
    try:
        r = run([ffmpeg_bin(), "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.2",
                 "-c:v", "h264_nvenc", "-f", "null", "-"], timeout=30)
        if r.returncode == 0:
            return "h264_nvenc"
    except Exception:  # noqa: BLE001
        pass
    return "libx264"


def encoder_args(quality: str = "high") -> list[str]:
    enc = video_encoder()
    if enc == "h264_nvenc":
        cq = {"draft": "30", "standard": "25", "high": "21"}.get(quality, "23")
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", cq, "-b:v", "0", "-pix_fmt", "yuv420p"]
    crf = {"draft": "28", "standard": "23", "high": "19"}.get(quality, "21")
    preset = {"draft": "ultrafast", "standard": "veryfast", "high": "medium"}.get(quality, "veryfast")
    return ["-c:v", "libx264", "-preset", preset, "-crf", crf, "-pix_fmt", "yuv420p"]


_TIME_RE = re.compile(rb"out_time_us=(\d+)")


def run_with_progress(
    args: list[str],
    total_seconds: float,
    on_progress: Callable[[float], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    cwd: Path | None = None,
) -> None:
    """Run ffmpeg, reporting real progress parsed from ``-progress pipe:1``."""
    full = [args[0], "-progress", "pipe:1", "-nostats", *args[1:]]
    proc = subprocess.Popen(full, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(cwd) if cwd else None,
                            creationflags=_NO_WINDOW)
    stderr_chunks: list[bytes] = []

    import threading

    def _drain() -> None:
        assert proc.stderr
        for line in proc.stderr:
            stderr_chunks.append(line)
            if len(stderr_chunks) > 400:
                del stderr_chunks[:200]

    t = threading.Thread(target=_drain, daemon=True)
    t.start()
    assert proc.stdout
    for line in proc.stdout:
        m = _TIME_RE.search(line)
        if m and on_progress and total_seconds > 0:
            on_progress(min(1.0, int(m.group(1)) / 1e6 / total_seconds))
        if should_cancel and should_cancel():
            proc.kill()
            proc.wait()
            raise Cancelled("cancelled")
    proc.wait()
    t.join(timeout=2)
    if proc.returncode != 0:
        raise MediaError("Rendering failed: " + _tail(b"".join(stderr_chunks)))


def _tail(stderr: bytes | None, n: int = 600) -> str:
    s = (stderr or b"").decode("utf-8", "replace").strip()
    return s[-n:] if s else "unknown ffmpeg error"
