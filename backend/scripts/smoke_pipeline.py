"""Run the whole AI pipeline on one file without the API (debugging aid).

python scripts/smoke_pipeline.py path/to/video.mp4 [--llm] [--render N]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.pipeline import ffmpeg, highlights, llm, publish, reframe, render, signals, transcribe  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--render", type=int, default=1)
    ap.add_argument("--out", default="smoke_out")
    a = ap.parse_args()
    src = Path(a.video).resolve()
    out = Path(a.out).resolve()
    out.mkdir(exist_ok=True)
    t = time.time()
    pr = ffmpeg.probe(src)
    print("probe", pr)
    wav = out / "audio.wav"
    ffmpeg.extract_audio(src, wav)
    tr = transcribe.transcribe(wav, None, pr.duration)
    print(f"transcribe: {len(tr.words)} words, lang={tr.language}, {tr.engine}, {time.time() - t:.1f}s")
    sig = signals.compute(src, wav, pr.duration)
    print(f"signals: cuts={len(sig.cuts)} loud={sig.loudness.size} motion={sig.motion.size}  {time.time() - t:.1f}s")
    prefs = highlights.Prefs(count=4, min_dur=15, max_dur=45)
    cands, ctx = highlights.discover(tr.words, sig, prefs, semantic=llm.semantic_rank if a.llm else None)
    print(f"genre={ctx.genre} speech={ctx.speech} {time.time() - t:.1f}s")
    for c in cands:
        print(f"  {c.score:3d} [{c.start:6.1f}-{c.end:6.1f}] {c.title!r}\n      dims={c.dims}\n      why={c.reasons}")
    for i, c in enumerate(cands[: a.render]):
        rf = reframe.analyze(src, c.start, c.end)
        print("reframe", rf["source"], len(rf["path"]), rf["split"])
        edits = {
            "overlays": [{"kind": "title", "text": c.title, "start": 0, "end": 3}],
            "captions": {"preset": ["bold_creator", "karaoke", "clean_minimal"][i % 3]},
            "silence_removal": True,
        }
        info = render.render(
            src,
            pr,
            c.start,
            c.end,
            edits,
            rf,
            tr.words,
            out / f"clip{i}.mp4",
            out / f"work{i}",
            set(),
            on_progress=None,
        )
        print("rendered", info["duration"], info["width"], info["height"], info["segments"][:3])
        ffmpeg.thumbnail(out / f"clip{i}.mp4", 2.0, out / f"clip{i}.jpg", 540)
        pkg = publish.generate(c.title, c.hook, c.text, ctx.genre, ["youtube", "tiktok"], allow_llm=a.llm)
        print("publish", pkg["engine"], pkg["platforms"]["youtube"].get("titles"))
    print(f"total {time.time() - t:.1f}s")


if __name__ == "__main__":
    main()
