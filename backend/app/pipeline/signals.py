"""Low-level audio and visual signals sampled on a fixed time grid.

Audio (10 Hz): loudness (dB RMS), spectral flux (onsets / reactions) and spectral
flatness (noise-like sound such as applause, cheering or laughter bursts).
Video (2 Hz): frame-difference motion and histogram-based scene cuts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import ffmpeg

AUDIO_HOP = 0.1  # seconds
VIDEO_FPS = 2.0


@dataclass
class Signals:
    duration: float
    loudness: np.ndarray = field(default_factory=lambda: np.zeros(0))  # dB, per AUDIO_HOP
    flux: np.ndarray = field(default_factory=lambda: np.zeros(0))
    flatness: np.ndarray = field(default_factory=lambda: np.zeros(0))
    motion: np.ndarray = field(default_factory=lambda: np.zeros(0))  # per 1/VIDEO_FPS
    cuts: list[float] = field(default_factory=list)

    # --- helpers ---------------------------------------------------------
    def _slice(self, arr: np.ndarray, start: float, end: float, rate: float) -> np.ndarray:
        a, b = int(start * rate), max(int(end * rate), int(start * rate) + 1)
        return arr[a:b]

    def loud_z(self, start: float, end: float) -> float:
        """Mean loudness of a window relative to the whole video, in std units."""
        if self.loudness.size == 0:
            return 0.0
        voiced = self.loudness[self.loudness > -50]
        ref = voiced if voiced.size > 10 else self.loudness
        mu, sd = float(np.mean(ref)), float(np.std(ref)) or 1.0
        w = self._slice(self.loudness, start, end, 1 / AUDIO_HOP)
        w = w[w > -50] if (w > -50).sum() > 3 else w
        return (float(np.mean(w)) - mu) / sd if w.size else 0.0

    def peak_z(self, start: float, end: float) -> float:
        if self.flux.size == 0:
            return 0.0
        mu, sd = float(np.mean(self.flux)), float(np.std(self.flux)) or 1.0
        w = self._slice(self.flux, start, end, 1 / AUDIO_HOP)
        return (float(np.percentile(w, 95)) - mu) / sd if w.size else 0.0

    def loudness_range(self, start: float, end: float) -> float:
        w = self._slice(self.loudness, start, end, 1 / AUDIO_HOP)
        w = w[w > -50]
        return float(np.percentile(w, 90) - np.percentile(w, 10)) if w.size > 5 else 0.0

    def noisy_burst_seconds(self, start: float, end: float) -> float:
        """Seconds of loud, noise-like sound (applause / cheering / laughter proxy)."""
        if self.flatness.size == 0:
            return 0.0
        f = self._slice(self.flatness, start, end, 1 / AUDIO_HOP)
        lo = self._slice(self.loudness, start, end, 1 / AUDIO_HOP)
        n = min(f.size, lo.size)
        if n == 0:
            return 0.0
        thr = float(np.percentile(self.loudness, 60))
        return float(np.sum((f[:n] > 0.35) & (lo[:n] > thr)) * AUDIO_HOP)

    def silence_ratio(self, start: float, end: float) -> float:
        w = self._slice(self.loudness, start, end, 1 / AUDIO_HOP)
        return float(np.mean(w < -45)) if w.size else 0.0

    def motion_z(self, start: float, end: float) -> float:
        if self.motion.size == 0:
            return 0.0
        mu, sd = float(np.mean(self.motion)), float(np.std(self.motion)) or 1.0
        w = self._slice(self.motion, start, end, VIDEO_FPS)
        return (float(np.mean(w)) - mu) / sd if w.size else 0.0

    def cuts_in(self, start: float, end: float) -> int:
        return sum(1 for c in self.cuts if start < c < end)

    def to_json(self) -> dict:
        def ds(a: np.ndarray, step: int) -> list[float]:
            return [round(float(x), 2) for x in a[::step]]

        return {
            "duration": self.duration,
            "loudness_2hz": ds(self.loudness, 5),
            "motion_2hz": ds(self.motion, 1),
            "cuts": [round(c, 2) for c in self.cuts],
        }


def audio_signals(wav: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    data, sr = ffmpeg.read_wav_mono(wav)
    hop = int(sr * AUDIO_HOP)
    win = 1024
    n = max(0, (len(data) - win) // hop + 1)
    if n == 0:
        return np.zeros(0), np.zeros(0), np.zeros(0)
    idx = np.arange(win)[None, :] + hop * np.arange(n)[:, None]
    frames = data[idx] * np.hanning(win)[None, :]
    rms = np.sqrt(np.mean(frames**2, axis=1) + 1e-10)
    loud = 20 * np.log10(rms + 1e-10)
    spec = np.abs(np.fft.rfft(frames, axis=1)) + 1e-10
    flux = np.concatenate([[0.0], np.sum(np.maximum(0, np.diff(np.log(spec), axis=0)), axis=1)])
    flat = np.exp(np.mean(np.log(spec), axis=1)) / np.mean(spec, axis=1)
    return loud.astype(np.float32), flux.astype(np.float32), flat.astype(np.float32)


def video_signals(src: Path, duration: float) -> tuple[np.ndarray, list[float]]:
    frames, _ = ffmpeg.read_frames(src, 0, duration, VIDEO_FPS, 128)
    if len(frames) < 2:
        return np.zeros(len(frames)), []
    f = frames.astype(np.int16)
    motion = np.concatenate([[0.0], np.mean(np.abs(np.diff(f, axis=0)), axis=(1, 2))]).astype(np.float32)
    hists = np.stack([np.histogram(fr, bins=32, range=(0, 255))[0] for fr in frames]).astype(np.float32)
    hists /= hists.sum(axis=1, keepdims=True) + 1e-9
    hd = np.concatenate([[0.0], 0.5 * np.sum(np.abs(np.diff(hists, axis=0)), axis=1)])
    cuts: list[float] = []
    thr = max(0.35, float(np.mean(hd) + 3 * np.std(hd)))
    for i in np.where(hd > thr)[0]:
        t = i / VIDEO_FPS
        if not cuts or t - cuts[-1] > 1.0:
            cuts.append(round(float(t), 2))
    return motion, cuts


def compute(src: Path, wav: Path | None, duration: float) -> Signals:
    s = Signals(duration=duration)
    if wav and wav.exists():
        s.loudness, s.flux, s.flatness = audio_signals(wav)
    s.motion, s.cuts = video_signals(src, duration)
    return s
