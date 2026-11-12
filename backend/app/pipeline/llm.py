"""Optional local LLM via Ollama (free, runs on your machine).

Everything that calls this module has a non-LLM fallback, and results always record
which engine produced them, so the UI never presents template text as "AI".
"""

from __future__ import annotations

import json
import logging
import time
from functools import lru_cache

import httpx

from ..config import get_settings

log = logging.getLogger("hypesift.llm")

_status_cache: tuple[float, dict] | None = None


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
        ok = any(n == s.ollama_model or n.split(":")[0] == s.ollama_model for n in names)
        out = {
            "available": ok,
            "model": s.ollama_model,
            "reason": "" if ok else f"Model '{s.ollama_model}' is not pulled (run: ollama pull {s.ollama_model})",
        }
    except (httpx.HTTPError, ValueError):
        out = {"available": False, "model": s.ollama_model, "reason": "Ollama is not running"}
    _status_cache = (time.time(), out)
    return out


def chat_json(system: str, user: str, temperature: float = 0.4, max_tokens: int = 1200) -> dict | list:
    s = get_settings()
    r = httpx.post(
        f"{s.ollama_url}/api/chat",
        json={
            "model": s.ollama_model,
            "stream": False,
            "format": "json",
            "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": 8192},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        },
        timeout=s.llm_timeout_seconds,
    )
    r.raise_for_status()
    content = r.json().get("message", {}).get("content", "")
    return _parse(content)


def _parse(content: str) -> dict | list:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        a, b = content.find("{"), content.rfind("}")
        if a >= 0 and b > a:
            return json.loads(content[a : b + 1])
        raise


@lru_cache(maxsize=1)
def engine_label() -> str:
    return f"local LLM ({get_settings().ollama_model} via Ollama)"


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


def semantic_rank(cands, ctx, batch: int = 5) -> None:
    """Fill ``semantic`` (0-100), ``title`` and ``llm_note`` on each candidate in place."""
    if not status()["available"]:
        return
    for i in range(0, len(cands), batch):
        group = cands[i : i + batch]
        items = "\n\n".join(f"[{n}] ({c.duration:.0f}s) {c.text[:1100]}" for n, c in enumerate(group))
        user = (
            f"Content type: {ctx.genre}. Requested mood: {ctx.prefs.mood}.\n"
            f"Rate each excerpt. For each return: id, hook (0-10: do the first seconds grab attention), "
            f"payoff (0-10: does it deliver a satisfying point/punchline/reaction), standalone (0-10: understandable "
            f"without the rest of the video), mood_fit (0-10), title (max 60 chars, accurate, no clickbait, no emojis), "
            f"why (max 18 words, concrete).\n"
            f'Return {{"items": [{{"id": 0, "hook": 7, "payoff": 6, "standalone": 8, "mood_fit": 5, '
            f'"title": "...", "why": "..."}}]}}\n\n{items}'
        )
        try:
            data = chat_json(RANK_SYSTEM, user, temperature=0.2)
        except Exception as e:  # noqa: BLE001
            log.warning("semantic rank failed: %s", e)
            return
        rows = data.get("items", []) if isinstance(data, dict) else data
        for row in rows if isinstance(rows, list) else []:
            try:
                c = group[int(row.get("id"))]
            except (TypeError, ValueError, IndexError):
                continue

            mood_w = 0.15 if ctx.prefs.mood not in ("any", "") else 0.0
            sem = (
                (0.32 - mood_w / 3) * _rating(row, "hook")
                + (0.34 - mood_w / 3) * _rating(row, "payoff")
                + (0.34 - mood_w / 3) * _rating(row, "standalone")
                + mood_w * _rating(row, "mood_fit")
            )
            c.semantic = round(sem * 10, 1)
            c.dims["semantic"] = c.semantic
            t = str(row.get("title") or "").strip().strip('"')
            if 4 <= len(t) <= 90:
                c.title = t
            why = str(row.get("why") or "").strip()
            if why:
                c.llm_note = "AI editor: " + why.rstrip(".") + "."
