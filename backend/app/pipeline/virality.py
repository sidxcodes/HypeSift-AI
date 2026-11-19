"""Goal scores and a Shorts readiness checklist for a clip.

These are explainable estimates built from the clip's own scores and edit settings.
They describe what the clip does well for each goal; they are not view predictions.

Goals (what the "Sort by" menu ranks on):
  views     - stops the scroll and holds attention: hook, emotion, pace, novelty, visuals
  trust     - shows expertise clearly: context, insight, relevance
  educate   - teaches something in one go: insight, clarity, pace
  entertain - feeling and energy: emotion, hook, visuals

Checklist: practices commonly recommended for YouTube Shorts retention (strong first
seconds, vertical, captions, a face on screen, 15-45 s, a clean loop, on-screen motion).
"""

from __future__ import annotations

import re
from typing import Any

GOALS = {
    "views": {"hook": 0.32, "emotion": 0.22, "pacing": 0.18, "novelty": 0.14, "visual": 0.14},
    "trust": {"context": 0.34, "novelty": 0.26, "relevance": 0.2, "semantic": 0.2},
    "educate": {"novelty": 0.4, "context": 0.35, "pacing": 0.25},
    "entertain": {"emotion": 0.4, "hook": 0.3, "visual": 0.3},
}

GOAL_LABELS = {
    "general": "General mix",
    "views": "More views",
    "trust": "Build trust",
    "educate": "Teach something",
    "entertain": "Entertain",
}


def _clip(x: float) -> int:
    return int(round(max(0.0, min(100.0, x))))


def goal_scores(dims: dict[str, float], score: float, duration: float) -> dict[str, int]:
    d = {**dims}
    d.setdefault("semantic", score)
    out = {"general": _clip(score)}
    for goal, w in GOALS.items():
        v = sum(wt * float(d.get(k, 50)) for k, wt in w.items())
        out[goal] = v
    # Length matters most for reach: 15-45 s holds viewers to the end best.
    if 15 <= duration <= 45:
        out["views"] += 4
    elif duration > 60:
        out["views"] -= 8
    elif duration < 10:
        out["views"] -= 6
    return {k: _clip(v) for k, v in out.items()}


def checklist(clip: dict[str, Any]) -> list[dict[str, Any]]:
    dims = (clip.get("score_breakdown") or {}).get("dims") or {}
    edits = clip.get("edits") or {}
    dur = float(clip.get("output_duration") or clip.get("duration") or 0)
    items: list[dict[str, Any]] = []

    def add(key: str, ok: bool | None, label: str, tip: str = "") -> None:
        items.append({"key": key, "ok": ok, "label": label, "tip": tip if not ok else ""})

    hook = float(dims.get("hook", 50))
    add(
        "hook",
        hook >= 60,
        "Strong opening line" if hook >= 60 else "Slow opening",
        "Trim the start in the editor so the first sentence grabs attention within 2 seconds.",
    )
    titled = any(o.get("kind") == "title" and o.get("text") for o in edits.get("overlays") or [])
    add(
        "title_card", titled, "Hook text on screen" if titled else "No hook text", "Add a title card for the first 3 s."
    )
    if 15 <= dur <= 45:
        add("length", True, f"{dur:.0f} s: the sweet spot for Shorts")
    elif 45 < dur <= 60:
        add("length", None, f"{dur:.0f} s: fine", "15-45 s usually keeps more viewers to the end.")
    elif dur > 60:
        add("length", False, f"{dur:.0f} s: long for a Short", "Shorts can run 3 min, but under 60 s holds viewers.")
    else:
        add("length", False, f"{dur:.0f} s: very short", "Give the moment a little context (15 s+).")
    add("vertical", edits.get("aspect", "9:16") == "9:16", "Vertical 9:16", "Switch the size to Portrait 9:16.")
    caps = (edits.get("captions") or {}).get("enabled", True)
    add("captions", bool(caps), "Captions on" if caps else "Captions off", "Most people watch Shorts muted.")
    face = (clip.get("reframe") or {}).get("face_ratio")
    if face is not None:
        add(
            "face",
            face >= 0.4,
            "Face on screen" if face >= 0.4 else "Face rarely on screen",
            "Clips with a visible speaker tend to hold attention better.",
        )
    text = (clip.get("text") or "").strip()
    loop = bool(re.search(r"[.!?][\"')\]]*$", text))
    add(
        "loop",
        loop,
        "Ends on a complete thought" if loop else "Ends mid-sentence",
        "Extend the end slightly so it finishes the thought and loops cleanly.",
    )
    zm = edits.get("zoom") or {}
    motion = bool(zm.get("start") or zm.get("key_phrases") or (edits.get("progress_bar") or {}).get("enabled"))
    add(
        "motion",
        motion,
        "Zoom punch-ins / progress bar" if motion else "No zoom or progress bar",
        "Turn on zoom at key phrases or the progress bar to keep eyes on screen.",
    )
    return items


def insights(clip: dict[str, Any]) -> dict[str, Any]:
    sb = clip.get("score_breakdown") or {}
    dur = float(clip.get("output_duration") or clip.get("duration") or 0)
    goals = goal_scores(sb.get("dims") or {}, float(clip.get("score") or 0), dur)
    checks = checklist(clip)
    passed = sum(1 for c in checks if c["ok"]) + 0.5 * sum(1 for c in checks if c["ok"] is None)
    ready = passed / max(1, len(checks))
    return {
        "goals": goals,
        "checklist": checks,
        "viral": _clip(0.72 * goals["views"] + 28 * ready),
    }
