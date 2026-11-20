"""Optional local LLM via Ollama (free, runs on your machine).

Everything that calls this module has a non-LLM fallback, and results always record
which engine produced them, so the UI never presents template text as "AI".
"""

from __future__ import annotations

import json
import logging
import time

import httpx

from ..config import get_settings

log = logging.getLogger("hypesift.llm")

_status_cache: tuple[float, dict] | None = None
_no_think: set[str] = set()  # models that reject the "think" switch

# Best first. The configured model is used when it's installed; otherwise the best one that is.
PREFERRED = ["qwen3.5:9b", "qwen3:8b", "qwen3.5:4b", "gemma3:4b"]
# Copywriting and chat commands: quick jobs where a 4B model is ~8x faster on a 6 GB GPU.
FAST = ["qwen3.5:4b", "gemma3:4b"]


def status(force: bool = False) -> dict:
    """{'available': bool, 'model': str, 'reason': str} cached for 30s."""
    global _status_cache
    s = get_settings()
    if not s.llm_enabled:
        return {"available": False, "model": s.ollama_model, "reason": "LLM disabled in settings"}
    if _status_cache and not force and time.time() - _status_cache[0] < 30:
        return _status_cache[1]
    try:
        r = httpx.get(f"{s.ollama_url}/api/tags", timeout=2.5)
        names = [m.get("name", "") for m in r.json().get("models", [])]

        def have(m: str) -> bool:
            return any(n == m or n == f"{m}:latest" for n in names)

        model = next((m for m in [s.ollama_model, *PREFERRED] if have(m)), None)
        fast = next((m for m in [s.ollama_fast_model, *FAST] if m and have(m)), None)
        out = {
            "available": model is not None,
            "model": model or s.ollama_model,
            "fast_model": fast or model or s.ollama_model,
            "reason": "" if model else f"No model pulled (run: ollama pull {s.ollama_model})",
        }
    except (httpx.HTTPError, ValueError):
        out = {"available": False, "model": s.ollama_model, "reason": "Ollama is not running"}
    _status_cache = (time.time(), out)
    return out


def model(fast: bool = False) -> str:
    st = status()
    return st.get("fast_model", st["model"]) if fast else st["model"]


def _chat(messages: list[dict], options: dict, fmt: str | None = "json", fast: bool = False) -> str:
    """One Ollama chat call. Reasoning ("think") is switched off: answers are short JSON and the
    smaller budget keeps a 9B model fast. The model is released after a minute so the GPU is free
    for speech-to-text and encoding."""
    s = get_settings()
    m = model(fast)
    body: dict = {
        "model": m,
        "stream": False,
        "options": {"num_ctx": 8192, **options},
        "messages": messages,
        "keep_alive": "60s",
    }
    if fmt:
        body["format"] = fmt
    if m not in _no_think:
        body["think"] = False
    r = httpx.post(f"{s.ollama_url}/api/chat", json=body, timeout=s.llm_timeout_seconds)
    if r.status_code == 400 and "think" in r.text.lower():
        _no_think.add(m)
        body.pop("think", None)
        r = httpx.post(f"{s.ollama_url}/api/chat", json=body, timeout=s.llm_timeout_seconds)
    r.raise_for_status()
    return r.json().get("message", {}).get("content", "")


def unload() -> None:
    """Free the model's GPU memory now (before Whisper runs)."""
    if not status()["available"]:
        return
    import contextlib

    for m in {model(), model(fast=True)}:
        with contextlib.suppress(httpx.HTTPError):
            httpx.post(f"{get_settings().ollama_url}/api/generate", json={"model": m, "keep_alive": 0}, timeout=10)


def chat_json(
    system: str, user: str, temperature: float = 0.4, max_tokens: int = 1200, fast: bool = False
) -> dict | list:
    """fast=True uses the quick model (copywriting, chat commands); the default is the best model."""
    content = _chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        {"temperature": temperature, "num_predict": max_tokens},
        fast=fast,
    )
    return _parse(content)


def vision_json(prompt: str, images: list[bytes], max_tokens: int = 200) -> dict:
    """Ask the local multimodal model about JPEG images; returns parsed JSON."""
    import base64

    content = _chat(
        [{"role": "user", "content": prompt, "images": [base64.b64encode(i).decode() for i in images]}],
        {"temperature": 0.1, "num_predict": max_tokens},
    )
    out = _parse(content)
    return out if isinstance(out, dict) else {}


def _parse(content: str) -> dict | list:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        a, b = content.find("{"), content.rfind("}")
        if a >= 0 and b > a:
            return json.loads(content[a : b + 1])
        raise


def engine_label(fast: bool = False) -> str:
    return f"local LLM ({model(fast)} via Ollama)"


# ----------------------------------------------------------------------------- ranking

RANK_SYSTEM = (
    "You are a senior short-form video editor. You judge transcript excerpts for how well they would work as a "
    "standalone 15-60s vertical short. Be strict and honest; most excerpts are average. Never invent content "
    "that is not in the excerpt. Reply with JSON only."
)


def _rating(row: dict, key: str) -> float:
    """A 0-10 rating from the model, clamped; missing/garbled values count as neutral."""
    try:
        return max(0.0, min(10.0, float(row.get(key, 5))))
    except (TypeError, ValueError):
        return 5.0


def _letter(n: int) -> str:
    return chr(65 + n) if n < 26 else str(n)


def _index(v, letters: bool = True) -> int | None:
    """Excerpt letter ("B", "Excerpt B", "clip b") or plain number -> 0-based index."""
    import re

    t = str(v).strip()
    if letters:
        m = re.fullmatch(r"(?:excerpt|clip)?\s*([A-Za-z])", t, re.I)
        if m:
            return ord(m.group(1).upper()) - 65
    m = re.search(r"\d+", t)
    return int(m.group()) if m else None


def _numbered(c, ctx) -> tuple[str, int, int]:
    """The excerpt as numbered sentences, with one sentence of context on each side.
    Returns (text, first_index, last_index) in ctx.sentences."""
    ss = getattr(ctx, "sentences", None) or []
    if c.s0 < 0 or not ss:
        return c.text[:1100], -1, -1
    lo, hi = max(0, c.s0 - 1), min(len(ss) - 1, c.s1 + 1)
    lines = []
    for k in range(lo, hi + 1):
        tag = "before" if k < c.s0 else "after" if k > c.s1 else "in"
        lines.append(f"  {k - lo} ({tag}) {ss[k].text}")
    return "\n".join(lines)[:1600], lo, hi


def semantic_rank(cands, ctx, batch: int = 4) -> None:
    """The AI editor: rates each excerpt, tightens its cut points, then ranks the best head to head.

    Fills ``semantic`` (0-100), ``title`` and ``llm_note`` on each candidate in place, and may move a
    candidate's start/end to better sentence boundaries (strong opening line, ends on the payoff)."""
    if not status()["available"]:
        return
    from . import highlights

    ask = ctx.prefs.instructions
    for i in range(0, len(cands), batch):
        group = cands[i : i + batch]
        blocks, spans = [], []
        for n, c in enumerate(group):
            text, lo, hi = _numbered(c, ctx)
            spans.append((lo, hi))
            blocks.append(f"Excerpt {_letter(n)} ({c.duration:.0f}s)\n{text}")
        fit_rule = f"fit (0-10: how well it matches the creator's request: {ask[:400]!r}), " if ask else ""
        fit_example = '"fit": <0-10>, ' if ask else ""
        user = (
            f"Content type: {ctx.genre}. Requested mood: {ctx.prefs.mood}. Target length {ctx.prefs.min_dur:.0f}-"
            f"{ctx.prefs.max_dur:.0f}s.\n"
            "Each excerpt (A, B, ...) is a list of numbered sentences: (in) sentences are in the clip now, (before) "
            "and (after) are the sentences around it. Return one item for EVERY excerpt: id (the excerpt letter); "
            "start and end (sentence numbers within that excerpt): where the BEST "
            "standalone clip should begin and end. Start on the line that grabs attention (skip filler, greetings and "
            "half-thoughts); end right after the payoff (the answer, punchline or reaction), not mid-thought. Keep the "
            f"original numbers if they're already right. Then rate that best version: {fit_rule}hook (0-10: would the "
            "first sentence stop someone scrolling YouTube Shorts), payoff (0-10: a satisfying point, punchline or "
            "reaction), standalone (0-10: makes sense without the rest of the video), mood_fit (0-10), title (max 60 "
            "chars, accurate, specific, no clickbait, no emojis), why (ONE sentence, max 18 words, concrete).\n"
            "Every rating is a whole number where 0 = terrible, 5 = average, 10 = exceptional; it must agree with "
            "your why. Judge each excerpt on its own words; don't reuse numbers from this instruction.\n"
            f'Return {{"items": [{{"id": "<letter>", "start": <n>, "end": <n>, {fit_example}"hook": <0-10>, '
            f'"payoff": <0-10>, "standalone": <0-10>, "mood_fit": <0-10>, "title": "<text>", "why": "<text>"}}]}}\n\n'
            + "\n\n".join(blocks)
        )
        try:
            data = chat_json(RANK_SYSTEM, user, temperature=0.2, max_tokens=900)
        except Exception as e:  # noqa: BLE001
            log.warning("semantic rank failed: %s", e)
            return
        rows = data.get("items", []) if isinstance(data, dict) else data
        for row in rows if isinstance(rows, list) else []:
            k = _index(row.get("id"))
            if k is None or k >= len(group):
                continue
            c = group[k]
            _refine(c, row, spans[k], ctx, highlights)
            mood_w = 0.15 if ctx.prefs.mood not in ("any", "") else 0.0
            fit_w = 0.4 if ask else 0.0
            rest = 1 - mood_w - fit_w
            sem = (
                rest * 0.32 * _rating(row, "hook")
                + rest * 0.34 * _rating(row, "payoff")
                + rest * 0.34 * _rating(row, "standalone")
                + mood_w * _rating(row, "mood_fit")
                + fit_w * _rating(row, "fit")
            )
            if ask:
                c.dims["fit"] = round(_rating(row, "fit") * 10, 1)
            c.semantic = round(sem * 10, 1)
            c.dims["semantic"] = c.semantic
            t = str(row.get("title") or "").strip().strip('"')
            if 4 <= len(t) <= 90:
                c.title = t
            why = str(row.get("why") or "").strip()
            if why:
                c.llm_note = "AI editor: " + why.rstrip(".") + "."
    vision_rank(cands, ctx)
    head_to_head(cands, ctx)


def _refine(c, row: dict, span: tuple[int, int], ctx, highlights) -> None:
    """Move the clip to the sentence range the editor chose, if it's a sensible length."""
    lo, hi = span
    if lo < 0:
        return
    sa, sb = _index(row.get("start"), letters=False), _index(row.get("end"), letters=False)
    if sa is None or sb is None:
        return
    a, b = lo + sa, lo + sb
    if not (lo <= a <= b <= hi) or (a, b) == (c.s0, c.s1):
        return
    start, end = highlights._padded(ctx, a, b)
    p = ctx.prefs
    if not (max(4.0, p.min_dur - 1.0) <= end - start <= p.max_dur + 2):  # the creator's length range is a promise
        return
    if any(start + 0.3 < x < end - 0.3 for x in getattr(p, "barriers", [])):
        return
    old = (round(c.start, 1), round(c.end, 1))
    c.s0, c.s1, c.start, c.end = a, b, start, end
    keep = (c.semantic, c.title, c.llm_note)
    highlights.score(c, ctx)  # signals, hook, context ... for the new range
    c.semantic, c.title, c.llm_note = keep
    c.evidence.setdefault("hook", []).insert(0, f"AI editor tightened the cut (was {old[0]}-{old[1]}s)")


def head_to_head(cands, ctx, top: int = 8) -> None:
    """Rank the best candidates against each other ("which gets the most views?"): comparative
    judgements are steadier than separate 0-10 scores. Adds up to +8 to the best ones."""
    rated = [c for c in cands if c.semantic is not None]
    if len(rated) < 3:
        return
    pool = sorted(rated, key=lambda c: -(0.6 * c.heuristic + 0.4 * c.semantic))[:top]
    items = "\n\n".join(f"Clip {_letter(n)} ({c.duration:.0f}s): {c.text[:500]}" for n, c in enumerate(pool))
    try:
        d = chat_json(
            RANK_SYSTEM,
            f"These {len(pool)} clips are candidates from the same video ({ctx.genre}). Order them from the one most "
            "likely to get views and watch-time as a YouTube Short to the least. Consider the opening line, the payoff "
            'and whether it stands alone. Return {"order": [clip letters, best first]}\n\n' + items,
            temperature=0.1,
            max_tokens=120,
        )
        order = [_index(x) for x in (d.get("order") or [])] if isinstance(d, dict) else []
    except Exception as e:  # noqa: BLE001
        log.info("head-to-head ranking failed: %s", e)
        return
    seen: list[int] = []
    for x in order:
        if x is not None and x < len(pool) and x not in seen:
            seen.append(x)
    for place, x in enumerate(seen):
        bonus = max(0.0, 8.0 - place * 8.0 / max(1, len(pool) - 1))
        c = pool[x]
        c.semantic = round(min(100.0, c.semantic + bonus), 1)
        c.dims["semantic"] = c.semantic
        if place == 0:
            c.llm_note = (c.llm_note + " " if c.llm_note else "") + "Ranked #1 head to head."


VISION_MAX = 10


def vision_rank(cands, ctx) -> None:
    """Moments with little or no speech (gameplay, sport, music, reactions) are judged by looking at
    them: the local vision model rates a frame from the middle of each for how striking it is."""
    src = getattr(ctx.prefs, "media_src", "")
    quiet = [c for c in cands if len(c.text.split()) < 15][:VISION_MAX]
    if not src or not quiet:
        return
    import subprocess

    from . import ffmpeg

    for c in quiet:
        try:
            img = subprocess.run(
                [
                    ffmpeg.ffmpeg_bin(),
                    "-v",
                    "error",
                    "-ss",
                    f"{(c.start + c.end) / 2:.2f}",
                    "-i",
                    src,
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale=640:-2",
                    "-f",
                    "image2",
                    "-c:v",
                    "mjpeg",
                    "-",
                ],
                capture_output=True,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ).stdout
            if not img:
                continue
            d = vision_json(
                "Rate this frame as the centre of a short vertical video. wow (0-10): how striking, exciting or "
                "funny it looks; clear (0-10): is the subject clear. Also a title (max 50 chars, accurate). "
                'Reply JSON {"wow": 7, "clear": 8, "title": "..."}',
                [img],
            )
        except Exception as e:  # noqa: BLE001 - optional
            log.info("vision rank failed: %s", e)
            return
        v = 10 * (0.7 * _rating(d, "wow") + 0.3 * _rating(d, "clear"))
        c.dims["visual"] = round(max(c.dims.get("visual", 50), v), 1)
        c.semantic = round(v if c.semantic is None else 0.5 * c.semantic + 0.5 * v, 1)
        t = str(d.get("title") or "").strip().strip('"')
        if not c.title and 4 <= len(t) <= 70:
            c.title = t
        if not c.llm_note:
            c.llm_note = "AI editor (looked at it): visually " + (
                "striking" if v >= 70 else "solid" if v >= 50 else "calm"
            )
