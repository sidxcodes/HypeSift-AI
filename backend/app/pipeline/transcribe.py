"""Local speech-to-text with word timestamps (faster-whisper, free, offline).

GPU (CUDA) is used when ctranslate2 can load it; otherwise we fall back to CPU int8.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..config import get_settings

log = logging.getLogger("hypesift.stt")

_models: dict[tuple[str, str, str], object] = {}
_lock = threading.Lock()


def _add_nvidia_dll_dirs() -> None:
    """pip-installed CUDA libs (nvidia-cublas-cu12 …) live in site-packages/nvidia/*/bin."""
    if os.name != "nt":
        return
    for base in sys.path:
        root = Path(base) / "nvidia"
        if root.is_dir():
            for b in root.glob("*/bin"):
                try:
                    os.add_dll_directory(str(b))
                    os.environ["PATH"] = str(b) + os.pathsep + os.environ.get("PATH", "")
                except OSError:
                    pass


@dataclass
class Word:
    w: str
    s: float
    e: float
    p: float = 1.0


@dataclass
class Transcript:
    language: str
    words: list[Word] = field(default_factory=list)
    segments: list[dict] = field(default_factory=list)
    engine: str = ""

    def to_json(self) -> dict:
        return {
            "language": self.language,
            "engine": self.engine,
            "words": [[w.w, round(w.s, 3), round(w.e, 3), round(w.p, 3)] for w in self.words],
            "segments": self.segments,
        }

    @classmethod
    def from_json(cls, d: dict) -> Transcript:
        return cls(
            language=d.get("language", "en"),
            engine=d.get("engine", ""),
            words=[Word(w[0], w[1], w[2], w[3] if len(w) > 3 else 1.0) for w in d.get("words", [])],
            segments=d.get("segments", []),
        )


def _load(model: str, device: str, compute: str):
    from faster_whisper import WhisperModel

    key = (model, device, compute)
    with _lock:
        if key not in _models:
            log.info("loading whisper %s on %s/%s", model, device, compute)
            _models[key] = WhisperModel(model, device=device, compute_type=compute)
        return _models[key]


def _candidates() -> list[tuple[str, str]]:
    s = get_settings()
    dev = s.whisper_device
    if dev == "cpu":
        return [("cpu", s.whisper_compute_type if s.whisper_compute_type != "auto" else "int8")]
    gpu = ("cuda", s.whisper_compute_type if s.whisper_compute_type != "auto" else "float16")
    cpu = ("cpu", "int8")
    return [gpu] if dev == "cuda" else [gpu, cpu]


def transcribe(audio: Path, language: str | None = None, total_seconds: float = 0,
               on_progress: Callable[[float], None] | None = None,
               should_cancel: Callable[[], bool] | None = None) -> Transcript:
    _add_nvidia_dll_dirs()
    s = get_settings()
    last_err: Exception | None = None
    for device, compute in _candidates():
        try:
            model = _load(s.whisper_model, device, compute)
            segments, info = model.transcribe(  # type: ignore[attr-defined]
                str(audio),
                language=None if not language or language == "auto" else language,
                word_timestamps=True,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 400},
                beam_size=5 if device == "cuda" else 1,
                condition_on_previous_text=False,
            )
            out = Transcript(language=info.language, engine=f"faster-whisper/{s.whisper_model} ({device})")
            for seg in segments:
                if should_cancel and should_cancel():
                    from .ffmpeg import Cancelled

                    raise Cancelled("cancelled")
                out.segments.append({"s": round(seg.start, 3), "e": round(seg.end, 3), "t": seg.text.strip()})
                for w in seg.words or []:
                    txt = w.word.strip()
                    if txt:
                        out.words.append(Word(txt, float(w.start), float(w.end), float(w.probability)))
                if on_progress and total_seconds:
                    on_progress(min(1.0, seg.end / total_seconds))
            return out
        except Exception as e:  # noqa: BLE001 - try the next device
            from .ffmpeg import Cancelled

            if isinstance(e, Cancelled):
                raise
            log.warning("whisper on %s failed: %s", device, e)
            last_err = e
            with _lock:
                _models.pop((s.whisper_model, device, compute), None)
    raise RuntimeError(f"Transcription failed: {last_err}")
