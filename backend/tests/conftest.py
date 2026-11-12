"""Test configuration: isolated temp database + storage, no embedded worker, no LLM."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="hypesift-test-"))
os.environ.update(
    {
        "HYPESIFT_DATABASE_URL": f"sqlite:///{(_TMP / 'test.db').as_posix()}",
        "HYPESIFT_STORAGE_DIR": str(_TMP / "storage"),
        "HYPESIFT_EMBEDDED_WORKER": "false",
        "HYPESIFT_LLM_ENABLED": "false",
        "HYPESIFT_VIDEO_ENCODER": "libx264",
        "HYPESIFT_SECRET_KEY": "test-secret",
    }
)

from app.pipeline import ffmpeg  # noqa: E402
from app.pipeline.transcribe import Word  # noqa: E402


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.fixture(scope="session")
def sample_video() -> Path:
    """A 40 s 640x360 clip with moving content, scene changes and a tone, built by ffmpeg."""
    out = _TMP / "sample.mp4"
    if not out.exists():
        src = (
            "testsrc2=s=640x360:r=25:d=20[a];color=c=0x553399:s=640x360:r=25:d=20,"
            "drawbox=x='100+80*sin(t)':y=120:w=120:h=120:color=white:t=fill[b];[a][b]concat=n=2:v=1:a=0[v]"
        )
        subprocess.run(
            [
                ffmpeg.ffmpeg_bin(),
                "-y",
                "-v",
                "error",
                "-filter_complex",
                src,
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:duration=40:sample_rate=16000",
                "-map",
                "[v]",
                "-map",
                "0:a",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-shortest",
                str(out),
            ],
            check=True,
        )
    return out


SCRIPT = (
    "Welcome back to the show. Today we talk about shipping products fast. "
    "Why do most side projects never launch? Here's the truth. Most people spend ninety percent of their "
    "time on features nobody asked for. They polish the logo and rewrite the backend twice. "
    "My first startup burned forty thousand dollars before one paying user. That was painful! "
    "So what would you do differently today? I would launch in two weeks, not two years. "
    "Write a landing page, put a price on it, and see if anyone pays. Thanks for listening."
)


def fake_words(duration: float = 40.0, script: str = SCRIPT) -> list[Word]:
    """Deterministic word timings (~2.6 words/s) with pauses after sentences."""
    words, t = [], 0.6
    for tok in script.split():
        d = 0.18 + 0.03 * len(tok)
        words.append(Word(tok, round(t, 3), round(t + d, 3), 0.95))
        t += d + (0.7 if tok.endswith((".", "?", "!")) else 0.08)
        if t > duration - 1:
            break
    return words
