"""Google Gemini as the moment finder (free tier, optional).

Gemini watches the video (frames + audio) *and* reads the timestamped transcript, then picks the
best standalone moments by transcript line, so cut points land exactly on sentence boundaries.

- The key lives in ``data/ai_settings.json`` (gitignored, local only); nothing is sent anywhere
  except to Google's Gemini API, and only when the user has added a key and chosen Gemini.
- Free-tier models are tried best first; on a quota/availability error the next one is tried,
  and the caller falls back to the local pipeline when every one fails.
- Video input: public YouTube links are passed as a URL (no upload); other videos up to
  ``VIDEO_UPLOAD_MAX_MIN`` minutes are uploaded as a small 360p proxy and deleted afterwards;
  longer videos are judged from the transcript alone (token limits).
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from ..config import BACKEND_DIR
from . import ffmpeg

log = logging.getLogger("hypesift.gemini")

SETTINGS_FILE = BACKEND_DIR / "data" / "ai_settings.json"
# Free-tier models, strongest first (Google AI Studio pricing page, Nov 2026).
MODELS = ["gemini-4-hydrogen", "gemini-3.8-flash", "gemini-2.5-pro", "gemini-3.6-flash", "gemini-2.5-flash"]
VIDEO_UPLOAD_MAX_MIN = 30  # ~100 tokens per second of video at low resolution
YOUTUBE_MAX_MIN = 60
TRANSCRIPT_MAX_LINES = 2500

_last_error = ""
_last_model = ""


# --------------------------------------------------------------------------- settings


def load_settings() -> dict:
    try:
        d = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(**changes: Any) -> dict:
    d = {**load_settings(), **{k: v for k, v in changes.items() if v is not None}}
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(d), encoding="utf-8")
    return d


def provider() -> str:
    """ "gemini" when chosen and a key is set, else "local"."""
    s = load_settings()
    return "gemini" if s.get("provider", "gemini") == "gemini" and s.get("gemini_api_key") else "local"


def public_settings() -> dict:
    s = load_settings()
    key = s.get("gemini_api_key") or ""
    return {
        "provider": s.get("provider", "gemini" if key else "local"),
        "active": provider(),
        "has_key": bool(key),
        "key_hint": f"…{key[-4:]}" if len(key) >= 8 else "",
        "model": s.get("gemini_model", "auto"),
        "models": MODELS,
        "last_model": _last_model,
        "last_error": _last_error,
    }


def _client():
    from google import genai

    key = load_settings().get("gemini_api_key")
    if not key:
        raise RuntimeError("No Gemini API key")
    return genai.Client(api_key=key)


def _models() -> list[str]:
    chosen = load_settings().get("gemini_model", "auto")
    return [chosen, *[m for m in MODELS if m != chosen]] if chosen in MODELS else list(MODELS)


def test_key(key: str) -> tuple[bool, str]:
    """Check a key by asking the cheapest model for a one-word reply."""
    from google import genai

    try:
        c = genai.Client(api_key=key)
        for m in reversed(MODELS):
            try:
                r = c.models.generate_content(model=m, contents="Reply with the single word: ok")
                return True, f"Key works ({m} replied “{(r.text or '').strip()[:20]}”)."
            except Exception as e:  # noqa: BLE001
                if _retryable(e):
                    continue
                raise
        return False, "The key is valid but every free model is over its quota right now."
    except Exception as e:  # noqa: BLE001
        return False, _friendly(e)


def _retryable(e: Exception) -> bool:
    t = str(e)
    return any(x in t for x in ("429", "RESOURCE_EXHAUSTED", "404", "NOT_FOUND", "503", "UNAVAILABLE", "500"))


def _friendly(e: Exception) -> str:
    t = str(e)
    if "API_KEY_INVALID" in t or "API key not valid" in t:
        return "Google says this API key isn't valid."
    if "PERMISSION_DENIED" in t:
        return "This key isn't allowed to use the Gemini API (check it in Google AI Studio)."
    if "429" in t or "RESOURCE_EXHAUSTED" in t:
        return "Free daily limit reached on every Gemini model; it resets at midnight Pacific time."
    return t.splitlines()[0][:200] if t else type(e).__name__


# --------------------------------------------------------------------------- video input


def _youtube_id(url: str | None) -> str | None:
    m = re.search(r"(?:youtube\.com/(?:watch\?v=|shorts/|live/)|youtu\.be/)([\w-]{11})", url or "")
    return m.group(1) if m else None


def _proxy(src: Path, out: Path, duration: float) -> Path:
    """A small 360p copy for upload (Gemini samples ~1 frame per second anyway)."""
    args = [
        ffmpeg.ffmpeg_bin(), "-y", "-v", "error", "-i", str(src),
        "-vf", "scale=-2:360,fps=4", "-c:v", "libx264", "-preset", "veryfast", "-crf", "32",
        "-c:a", "aac", "-b:a", "48k", "-ac", "1", "-movflags", "+faststart", str(out),
    ]  # fmt: skip
    subprocess.run(args, check=True, timeout=max(120, duration))
    return out


def _upload(client, path: Path, cancelled=None):
    f = client.files.upload(file=str(path))
    t0 = time.time()
    while getattr(f.state, "name", str(f.state)) not in ("ACTIVE", "FAILED"):
        if time.time() - t0 > 600 or (cancelled and cancelled()):
            raise TimeoutError("Gemini took too long to process the video")
        time.sleep(3)
        f = client.files.get(name=f.name)
    if getattr(f.state, "name", "") == "FAILED":
        raise RuntimeError("Gemini couldn't process the video file")
    return f


# --------------------------------------------------------------------------- moment finding


def _mmss(t: float) -> str:
    return f"{int(t // 60):02d}:{t % 60:04.1f}"


SYSTEM = (
    "You are the best short-form video editor in the world. You find the moments in long videos that become "
    "viral YouTube Shorts / TikToks / Reels: an opening line or visual that stops the scroll in the first 2 "
    "seconds, a complete standalone story, and a payoff (punchline, answer, reveal, reaction, twist) before the "
    "end. You watch the picture and listen to the audio (laughter, shouting, music drops, action), not just the "
    "words. You never pick filler, greetings, sponsor reads, intros/outros, or moments that need earlier context. "
    "You are strict: you only return moments you'd bet on. Reply with JSON only."
)


COMPARE_RULE = (
    "\nALSO decide whether this is a COMPARISON video: the same action/scene shown in two or more versions "
    "(different games, sequels, years, remasters, phones, products, before/after) so viewers can compare them. "
    "A normal video that merely mentions two things is NOT a comparison. If it is, list each compared scenario "
    "(e.g. 'opening a car door') with the exact time range where EACH version shows that action, one after "
    "another in the video (layout 'sequential'). If the versions are shown side by side in the same frame, use "
    "layout 'split_screen' and give one time range per scenario (version 'both'). Add to the JSON: "
    '"comparison": {"is_comparison": <true|false>, "layout": "sequential"|"split_screen"|"none", "versions": '
    '["<name>", ...], "scenarios": [{"title": "<what happens, max 40 chars>", "virality": <0-100>, "parts": '
    '[{"version": "<name>", "start": <seconds>, "end": <seconds>}]}]}'
)


def find_moments(**kw) -> list[dict] | None:
    return analyze_video(**kw)["moments"]


def analyze_video(
    *,
    sentences: list,
    duration: float,
    prefs,
    count: int,
    src: Path | None = None,
    url: str | None = None,
    title: str = "",
    work_dir: Path | None = None,
    cancelled=None,
    progress=None,
    want_comparison: bool = False,
) -> dict:
    """Ask Gemini for the best moments (and, optionally, whether this is a comparison video).

    Returns {"moments": [{"s0", "s1"} | {"start", "end"}, + "score" 0-100, "title", "why", "hook"] best
    first, or None; "comparison": parsed comparison dict, or None when Gemini didn't answer}. Moments are
    None when Gemini isn't configured or every model failed (the caller falls back)."""
    global _last_error, _last_model
    empty: dict = {"moments": None, "comparison": None}
    if provider() != "gemini":
        return empty
    from google.genai import types

    try:
        client = _client()
    except Exception as e:  # noqa: BLE001
        _last_error = _friendly(e)
        return empty

    # ---- what Gemini will look at
    video_part = None
    uploaded = None
    yt = _youtube_id(url)
    try:
        if yt and duration <= YOUTUBE_MAX_MIN * 60:
            video_part = types.Part(file_data=types.FileData(file_uri=f"https://www.youtube.com/watch?v={yt}"))
        elif src and src.exists() and duration <= VIDEO_UPLOAD_MAX_MIN * 60:
            if progress:
                progress(0.05, "Sending a small preview of the video to Gemini")
            proxy = _proxy(src, (work_dir or src.parent) / "gemini_proxy.mp4", duration)
            uploaded = _upload(client, proxy, cancelled)
            proxy.unlink(missing_ok=True)
            video_part = types.Part(file_data=types.FileData(file_uri=uploaded.uri, mime_type=uploaded.mime_type))
    except Exception as e:  # noqa: BLE001 - fall back to transcript-only judging
        log.warning("Gemini video input unavailable (%s); judging from the transcript", e)
        video_part = None

    lines = [f"L{i} [{_mmss(s.start)}-{_mmss(s.end)}] {s.text}" for i, s in enumerate(sentences)]
    if len(lines) > TRANSCRIPT_MAX_LINES:  # very long: keep every line but trim text
        lines = [ln[:160] for ln in lines]
    lo, hi = prefs.min_dur, prefs.max_dur
    target = getattr(prefs, "target_dur", None) or (lo + hi) / 2
    asks = []
    if prefs.instructions:
        asks.append(f"The creator's request (most important): {prefs.instructions[:600]}")
    if prefs.mood not in ("any", ""):
        asks.append(f"Preferred mood: {prefs.mood}.")
    if getattr(prefs, "query", None):
        asks.append("Focus on: " + " ".join(prefs.query))
    if prefs.position != "any":
        asks.append(f"Prefer moments from the {prefs.position} of the video.")
    n = max(count + 3, int(count * 1.6))
    has_speech = bool(sentences)
    pick_rule = (
        "Pick each moment as a range of transcript lines: start_line is the line where the hook begins, end_line "
        "is the line where the payoff lands. "
        if has_speech
        else "There is little or no speech: pick each moment by time in seconds (start, end). "
    )
    prompt = (
        f"Video: {title or 'untitled'} ({duration / 60:.1f} min).\n"
        + ("You can watch the video above. " if video_part else "Judge from the transcript. ")
        + f"Find the {n} best moments for vertical Shorts, best first. Every moment MUST be between {lo:.0f} and "
        f"{hi:.0f} seconds long (aim for about {target:.0f}s); a moment that is shorter is not acceptable, so "
        "include the setup and the full payoff. Moments must not overlap. "
        + pick_rule
        + " ".join(asks)
        + "\nFor each moment give: virality (0-100, be strict: 50 = average, 85+ = would go viral), title (max 60 "
        "chars, specific, curiosity-driven, no emojis), hook (the first thing viewers hear/see, max 12 words), why "
        "(one concrete sentence).\n"
        + (
            'Return {"moments": [{"start_line": <int>, "end_line": <int>, "virality": <int>, "title": "<text>", '
            '"hook": "<text>", "why": "<text>"}]}'
            if has_speech
            else 'Return {"moments": [{"start": <seconds>, "end": <seconds>, "virality": <int>, "title": "<text>", '
            '"hook": "<text>", "why": "<text>"}]}'
        )
        + (COMPARE_RULE if want_comparison and video_part else "")
        + ("\n\nTranscript (line id, start-end time, text):\n" + "\n".join(lines) if lines else "")
    )
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM,
        response_mime_type="application/json",
        temperature=0.3,
        media_resolution=types.MediaResolution.MEDIA_RESOLUTION_LOW,
    )
    out: dict = dict(empty)
    try:
        models = _models()
        k = 0
        while k < len(models):
            m = models[k]
            if cancelled and cancelled():
                return out
            if progress:
                what = "watching the video" if video_part else "reading the transcript"
                progress(0.3, f"Gemini ({m}) is {what} for the best moments")
            contents = [video_part, prompt] if video_part else [prompt.replace(COMPARE_RULE, "")]
            try:
                r = client.models.generate_content(model=m, contents=contents, config=config)
                moments = _parse(r.text or "", len(sentences), duration)
                if moments:
                    _last_model, _last_error = m, ""
                    log.info("Gemini %s proposed %d moments", m, len(moments))
                    out = {
                        "moments": moments,
                        "comparison": _parse_comparison(r.text or "", duration)
                        if want_comparison and video_part
                        else None,
                    }
                    break
                k += 1
            except Exception as e:  # noqa: BLE001
                _last_error = _friendly(e)
                log.warning("Gemini %s failed: %s", m, _last_error)
                low = str(e).lower()
                if video_part is not None and any(x in low for x in ("video", "file", "youtube", "url", "media")):
                    video_part = None  # the video itself was the problem: same model, transcript only
                    continue
                if not _retryable(e):
                    break
                k += 1
    finally:
        if uploaded is not None:
            with contextlib.suppress(Exception):
                client.files.delete(name=uploaded.name)
    return out


def _parse_comparison(text: str, duration: float) -> dict | None:
    """{"is_comparison": bool, "layout", "versions", "scenarios": [{title, score, parts: [{label, start, end}]}]}"""
    try:
        d = json.loads(re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M))
    except ValueError:
        return None
    c = d.get("comparison") if isinstance(d, dict) else None
    if not isinstance(c, dict):
        return None
    yes = c.get("is_comparison") in (True, "true", "yes")
    out = {"is_comparison": yes, "layout": str(c.get("layout") or "none"), "versions": [], "scenarios": []}
    if not yes:
        return out
    out["versions"] = [str(v)[:40] for v in (c.get("versions") or []) if str(v).strip()][:6]
    for sc in c.get("scenarios") or []:
        if not isinstance(sc, dict):
            continue
        parts = []
        for pt in sc.get("parts") or []:
            a, b = _num((pt or {}).get("start")), _num((pt or {}).get("end"))
            if a is not None and b is not None and 0 <= a < b <= duration + 1 and b - a >= 1.0:
                parts.append(
                    {"label": str(pt.get("version") or "")[:40], "start": float(a), "end": min(float(b), duration)}
                )
        need = 1 if out["layout"] == "split_screen" else 2
        if len(parts) >= need:
            out["scenarios"].append(
                {
                    "title": str(sc.get("title") or "")[:60],
                    "score": max(0.0, min(100.0, _num(sc.get("virality")) or 75)),
                    "parts": parts,
                }
            )
    return out


def _parse(text: str, n_lines: int, duration: float) -> list[dict] | None:
    try:
        d = json.loads(re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M))
    except ValueError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return None
        try:
            d = json.loads(m.group())
        except ValueError:
            return None
    rows = d.get("moments") if isinstance(d, dict) else d
    out = []
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        item: dict = {
            "score": max(0.0, min(100.0, float(_num(r.get("virality")) or 50))),
            "title": str(r.get("title") or "").strip()[:90],
            "hook": str(r.get("hook") or "").strip()[:120],
            "why": str(r.get("why") or "").strip()[:240],
        }
        a, b = _num(r.get("start_line")), _num(r.get("end_line"))
        if a is not None and b is not None and n_lines:
            a, b = int(a), int(b)
            if 0 <= a <= b < n_lines:
                out.append({**item, "s0": a, "s1": b})
            continue
        s, e = _num(r.get("start")), _num(r.get("end"))
        if s is not None and e is not None and 0 <= s < e <= duration + 1:
            out.append({**item, "start": float(s), "end": min(float(e), duration)})
    return out or None


def _num(v) -> float | None:
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"-?\d+(?:\.\d+)?", str(v or ""))
    return float(m.group()) if m else None
