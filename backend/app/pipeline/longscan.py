"""Scan a long online video and choose which sections to download.

Streams and VODs can run for hours (tens of GB). Instead of downloading everything, HypeSift:

1. reads the site's captions: a timed transcript of the whole video in seconds. Videos
   without captions fall back to an audio-only download (small) transcribed in chunks
   with a fast speech model;
2. reads YouTube's "Most replayed" graph when the video has one: where real viewers
   rewatched;
3. ranks candidate moments on the transcript with the normal highlight scorer (plus the
   creator's custom instructions), boosted by the replay graph;
4. returns a few padded sections around the best ones. Only those are downloaded; the full
   pipeline (precise speech-to-text, signals, the LLM editor, reframing) then runs on them.
"""

from __future__ import annotations

import copy
import logging
import shutil
from collections.abc import Callable
from pathlib import Path

import numpy as np

from . import ffmpeg, highlights, sites, transcribe
from .signals import Signals

log = logging.getLogger("hypesift.longscan")

PAD = 6.0  # seconds kept around each chosen moment, so the final pass can refine boundaries
AUDIO_CHUNK = 1200.0  # transcribe caption-less audio 20 minutes at a time (bounded memory)
SCAN_MODEL = "base"  # the scan only needs the gist; the chosen sections get the full model


def heat_at(heat: list[tuple[float, float, float]], start: float, end: float) -> float:
    vals = [v for a, b, v in heat if b > start and a < end]
    return float(max(vals)) if vals else 0.0


def choose_sections(
    candidates: list[highlights.Candidate],
    heat: list[tuple[float, float, float]],
    want: int,
    duration: float,
) -> list[tuple[float, float]]:
    """Best non-overlapping candidates (score + replay boost) → padded, merged, time-ordered ranges."""
    if heat:
        typical = float(np.median([v for _, _, v in heat]))
        for c in candidates:
            c.score = int(round(c.score + 30 * (heat_at(heat, c.start, c.end) - typical)))
    picked: list[highlights.Candidate] = []
    for c in sorted(candidates, key=lambda c: -c.score):
        if all(highlights.overlap(c, o) < 0.2 for o in picked):
            picked.append(c)
        if len(picked) >= want:
            break
    ranges = sorted((max(0.0, c.start - PAD), min(duration, c.end + PAD)) for c in picked)
    merged: list[list[float]] = []
    for a, b in ranges:
        if merged and a <= merged[-1][1] + 2:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [(round(a, 2), round(b, 2)) for a, b in merged]


def loudness_per_second(audio: Path, duration: float, progress, cancelled) -> np.ndarray:
    """dB RMS for every second of a (possibly 10-hour) audio file, decoded as a stream at 8 kHz.
    Memory stays small: one minute of samples at a time."""
    import subprocess

    rate = 8000
    proc = subprocess.Popen(
        [ffmpeg.ffmpeg_bin(), "-v", "error", "-i", str(audio), "-ac", "1", "-ar", str(rate), "-f", "s16le", "-"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    out: list[float] = []
    block = rate * 2 * 60
    try:
        while True:
            if cancelled and cancelled():
                raise ffmpeg.Cancelled("cancelled")
            buf = proc.stdout.read(block) if proc.stdout else b""
            if not buf:
                break
            x = np.frombuffer(buf[: len(buf) // 2 * 2], dtype=np.int16).astype(np.float32) / 32768
            n = len(x) // rate
            if n:
                sec = x[: n * rate].reshape(n, rate)
                out += list(20 * np.log10(np.sqrt(np.mean(sec**2, axis=1)) + 1e-6))
            if duration:
                progress(
                    min(1.0, len(out) / duration),
                    f"Measuring the excitement across the video ({len(out) // 60} of {duration / 60:.0f} min)",
                )
    finally:
        proc.kill() if proc.poll() is None else None
    return np.array(out, dtype=np.float32)


def exciting_windows(loud: np.ndarray, count: int, length: int = 75) -> list[tuple[float, float]]:
    """The loudest, most animated stretches (shouting, laughing, reactions) as (start, end) seconds."""
    if loud.size < 30:
        return [(0.0, float(loud.size))] if loud.size else []
    voiced = loud > np.percentile(loud, 20)
    ref = loud[voiced] if voiced.sum() > 30 else loud
    z = (loud - np.median(ref)) / (np.std(ref) or 1.0)
    k = np.ones(15) / 15
    level = np.convolve(z, k, mode="same")  # sustained loudness over ~15 s
    swing = np.convolve(np.abs(np.diff(z, prepend=z[0])), k, mode="same")  # animated delivery
    score = level + 0.8 * swing
    if loud.size > 3600:
        # Long streams usually open with an intro song / "starting soon" screen: loud, but not a moment.
        score[:180] = -np.inf
        score[180:600] -= 0.8
    picked: list[int] = []
    for i in np.argsort(-score):
        if all(abs(i - j) > length for j in picked):
            picked.append(int(i))
        if len(picked) >= count:
            break
    return sorted((max(0.0, i - length / 2), min(float(loud.size), i + length / 2)) for i in picked)


def _audio_words(
    url: str,
    work: Path,
    language: str | None,
    duration: float,
    want: int,
    progress: Callable[[float, str], None],
    cancelled,
) -> tuple[list[transcribe.Word], list[float]]:
    """No captions: rank the whole audio by excitement, then transcribe only the best windows.
    A 10-hour stream takes a few minutes instead of an hour. Returns (words, window joins)."""
    progress(0.05, "No captions: downloading the audio only")
    audio = sites.download_audio(url, work, should_cancel=cancelled)
    words: list[transcribe.Word] = []
    try:
        loud = loudness_per_second(audio, duration, lambda f, m: progress(0.1 + 0.4 * f, m), cancelled)
        windows = exciting_windows(loud, min(max(want * 3, 12), 40))
        chunk = work / "chunk.wav"
        for n, (a, b) in enumerate(windows):
            if cancelled and cancelled():
                raise ffmpeg.Cancelled("cancelled")
            ffmpeg.run(
                [
                    ffmpeg.ffmpeg_bin(),
                    "-y",
                    "-v",
                    "error",
                    "-ss",
                    f"{a:.2f}",
                    "-t",
                    f"{b - a:.2f}",
                    "-i",
                    str(audio),
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    str(chunk),
                ]
            )
            if not chunk.exists() or chunk.stat().st_size < 1000:
                continue
            tr = transcribe.transcribe(chunk, language, b - a, model=SCAN_MODEL)
            words += [transcribe.Word(w.w, w.s + a, w.e + a, w.p) for w in tr.words if w.s + a < b]
            progress(
                0.5 + 0.4 * (n + 1) / len(windows),
                f"Listening to the {len(windows)} most exciting parts ({n + 1}/{len(windows)})",
            )
        return words, [b for _, b in windows[:-1]]
    finally:
        audio.unlink(missing_ok=True)
        (work / "chunk.wav").unlink(missing_ok=True)


def map_words(words: list, sections: list[dict]) -> list[list]:
    """Scan words that fall inside the downloaded sections, moved onto the joined video's timeline."""
    out = []
    for w in words:
        for s in sections:
            if s["orig_start"] <= w.s < s["orig_end"]:
                d = s["start"] - s["orig_start"]
                out.append([w.w, round(w.s + d, 3), round(min(w.e, s["orig_end"]) + d, 3)])
                break
    return out


def plan(
    url: str,
    prefs: highlights.Prefs,
    work: Path,
    progress: Callable[[float, str], None],
    cancelled: Callable[[], bool] | None = None,
    language: str | None = None,
) -> tuple[list[tuple[float, float]], dict]:
    """Returns (ranges to download, scan words, scan summary)."""
    lang = None
    joins: list[float] = []
    want = min(max(prefs.count * 2, prefs.count + 4), 30)
    work.mkdir(parents=True, exist_ok=True)
    try:
        progress(0.02, "Reading the video's captions and replay graph")
        info = sites.scan_info(url)
        duration = float(info.get("duration") or 0)
        heat = sites.heatmap(info)
        got = sites.caption_words(url, info, work / "subs")
        if got:
            words, lang = got
            source = f"captions ({lang})"
        else:
            words, joins = _audio_words(url, work, language, duration, want, progress, cancelled)
            source = "audio (loudest parts, speech model)"
        if cancelled and cancelled():
            raise ffmpeg.Cancelled("cancelled")
        progress(0.9, "Picking the best moments")
        p = copy.copy(prefs)
        p.count = want * 2
        p.barriers = list(prefs.barriers) + joins
        sig = Signals(duration=duration)
        cands, _ = highlights.discover(words, sig, p) if words else ([], None)
        if not cands and heat:  # no speech at all: follow the replay graph
            top = sorted(heat, key=lambda h: -h[2])[:want]
            cands = [
                highlights.Candidate(start=a, end=min(duration, a + prefs.max_dur), score=int(v * 100))
                for a, _, v in top
            ]
        if not cands:
            # nothing to go on: spread sections evenly through the video
            step = duration / (want + 1)
            cands = [
                highlights.Candidate(start=step * (i + 1), end=step * (i + 1) + prefs.max_dur, score=50)
                for i in range(want)
            ]
        ranges = choose_sections(cands, heat, want, duration)
        return (
            ranges,
            words,
            {
                "source": source,
                "language": lang if got else None,
                "replay_graph": bool(heat),
                "words": len(words),
                "duration": duration,
                "sections": len(ranges),
                "downloaded_seconds": round(sum(b - a for a, b in ranges), 1),
            },
        )
    finally:
        shutil.rmtree(work, ignore_errors=True)
