"""Natural-language commands → real, validated editing actions.

A deterministic parser handles the common phrasings; when it can't, the local LLM
(if running) maps the request onto the same small action schema. Anything outside
the schema gets an honest "not supported yet" answer instead of a fake success.
"""

from __future__ import annotations

import re
from typing import Any

from . import llm
from .captions import PRESETS

NUM_WORDS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "the": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "a couple of": 2,
    "a few": 3,
    "several": 4,
}

MOOD_WORDS = {
    "funny": ["funny", "funniest", "hilarious", "humor", "humour", "laugh", "joke", "comedic"],
    "emotional": ["emotional", "touching", "sad", "heartfelt", "moving", "vulnerable"],
    "intense": ["intense", "hype", "hyped", "epic", "insane", "crazy", "exciting", "reaction", "clutch", "action"],
    "informative": ["informative", "educational", "insight", "insightful", "useful", "lesson", "tips", "explain"],
    "inspiring": ["inspiring", "inspirational", "motivational", "motivating", "uplifting"],
}
GENRE_WORDS = {
    "gaming": ["gaming", "game", "gameplay"],
    "podcast": ["podcast", "interview"],
    "education": ["education", "lecture", "class"],
    "tutorial": ["tutorial", "how-to", "howto"],
    "vlog": ["vlog"],
    "review": ["review", "unboxing"],
    "entertainment": ["entertainment"],
}
COLORS = {
    "yellow": "#FFE14D",
    "red": "#FF4D4D",
    "green": "#7CFF4F",
    "lime": "#7CFF4F",
    "blue": "#4DA3FF",
    "cyan": "#22D3EE",
    "purple": "#A78BFA",
    "violet": "#8B5CF6",
    "pink": "#FF4FD8",
    "orange": "#FF9F1C",
    "white": "#FFFFFF",
    "black": "#000000",
    "gold": "#FFC94D",
}
PLATFORM_WORDS = {
    "youtube": ["youtube", "shorts", "yt"],
    "instagram": ["instagram", "insta", "reel", "reels", "ig"],
    "tiktok": ["tiktok", "tik tok"],
    "linkedin": ["linkedin"],
    "facebook": ["facebook", "fb"],
    "x": ["twitter", " x ", "tweet"],
}
TONE_WORDS = {
    "funny": ["funny", "witty"],
    "professional": ["professional", "formal"],
    "energetic": ["energetic", "hype", "exciting"],
    "educational": ["educational", "informative"],
    "storytelling": ["story", "storytelling"],
    "compelling": ["compelling", "catchy", "engaging"],
}
UNSUPPORTED = {
    ("music", "song", "soundtrack"): "Adding music isn't supported yet — licensed music is on the roadmap.",
    ("translate", "translation", "spanish", "hindi", "french"): "Subtitle translation isn't available yet. You "
    "can transcribe in another language by setting the project language before generating.",
    ("b-roll", "broll", "stock footage"): "Automatic B-roll isn't supported.",
    ("post it", "upload to", "publish to", "schedule"): "Direct posting to social platforms isn't connected. "
    "Download the clip and copy the generated text into the app.",
    ("voice", "dub", "voiceover"): "Voice-over and dubbing aren't supported.",
}


def _has(text: str, words: list[str]) -> bool:
    return any(re.search(rf"(?<![a-z]){re.escape(w.strip())}(?![a-z])", text) for w in words)


def _count(t: str) -> int | None:
    m = re.search(r"\b(\d{1,2})\s+(?:\w+\s+){0,3}(?:clips?|moments?|highlights?|shorts?|videos?)", t)
    if m:
        return int(m.group(1))
    for w, n in sorted(NUM_WORDS.items(), key=lambda kv: -len(kv[0])):
        if re.search(rf"\b{w}\s+(?:\w+[\s-]+){{0,4}}(?:clips?|moments?|highlights?|shorts?|part)\b", t):
            return n
    return None


def _duration(t: str) -> tuple[float, float] | None:
    m = re.search(r"(\d{1,3})\s*(?:-|to)\s*(\d{1,3})\s*(?:s|sec|secs|second|seconds)\b", t)
    if m:
        a, b = sorted((int(m.group(1)), int(m.group(2))))
        return float(a), float(b)
    m = re.search(r"(under|less than|max|at most|below)\s+(\d{1,3})\s*(?:-\s*)?(?:s|sec|secs|second|seconds)\b", t)
    if m:
        b = float(m.group(2))
        return max(8.0, b * 0.5), b
    m = re.search(r"(\d{1,3})\s*(?:-\s*)?(?:s|sec|secs|second|seconds)\b", t)
    if m:
        d = float(m.group(1))
        return max(5.0, d - 6), d + 6
    m = re.search(r"(\d|one|a|two)\s*(?:-\s*)?(?:min|minute)s?\b", t)
    if m:
        d = {"one": 1, "a": 1, "two": 2}.get(m.group(1), None) or int(m.group(1))
        return d * 60 - 12.0, d * 60 + 5.0
    return None


def parse(text: str, has_clip: bool = False) -> dict[str, Any]:
    raw = text.strip()
    t = " " + raw.lower() + " "
    if not raw:
        return {"type": "unsupported", "message": "Type a request, e.g. “Find the funniest 30-second moment”."}

    for keys, msg in UNSUPPORTED.items():
        if any(k in t for k in keys) and not (("caption" in t or "description" in t) and "translate" not in t):
            return {"type": "unsupported", "message": msg}

    # ---- publishing copy -----------------------------------------------------
    plats = [p for p, ws in PLATFORM_WORDS.items() if _has(t, ws)]
    wants_copy = _has(
        t, ["description", "title", "titles", "hashtag", "hashtags", "post", "copy", "write", "tweet"]
    ) or (
        plats
        and _has(t, ["caption", "captions"])
        and not _has(t, ["style", "color", "colour", "font", "bold", "yellow"])
    )
    if wants_copy and (plats or _has(t, ["description", "hashtag", "title"])):
        tone = next((k for k, ws in TONE_WORDS.items() if _has(t, ws)), "compelling")
        return {
            "type": "generate_publish",
            "platforms": plats or ["youtube", "instagram", "tiktok"],
            "tone": tone,
            "requires_clip": True,
            "summary": f"Write {', '.join(plats or ['YouTube', 'Instagram', 'TikTok'])} copy ({tone})",
        }

    # ---- caption styling -------------------------------------------------------
    if _has(t, ["caption", "captions", "subtitle", "subtitles", "text"]) and not _has(
        t, ["find", "make five", "clips"]
    ):
        if _has(t, ["no captions", "remove captions", "turn off captions", "disable captions", "hide captions"]):
            return {"type": "set_captions", "enabled": False, "summary": "Turn captions off"}
        style: dict[str, Any] = {}
        preset = None
        for key, p in PRESETS.items():
            if p["label"].lower() in t or key.replace("_", " ") in t:
                preset = key
        if not preset:
            if _has(t, ["karaoke"]):
                preset = "karaoke"
            elif _has(t, ["gaming", "gamer"]):
                preset = "gaming_energy"
            elif _has(t, ["minimal", "clean", "simple"]):
                preset = "clean_minimal"
            elif _has(t, ["cinematic", "movie", "film"]):
                preset = "cinematic"
            elif _has(t, ["podcast"]):
                preset = "podcast"
            elif _has(t, ["bold"]):
                preset = "bold_creator"
        color = next((c for c in COLORS if _has(t, [c])), None)
        if color:
            style["highlight"] = COLORS[color]
            style["emphasis_color"] = COLORS[color]
            if _has(t, [f"{color} text", f"{color} words", f"{color} font"]) and not _has(t, ["highlight"]):
                style["color"] = COLORS[color]
        for pos in ("top", "middle", "bottom"):
            if _has(t, [f"at the {pos}", f"to the {pos}", f"{pos} of", pos]):
                style["position"] = pos
                break
        if _has(t, ["bigger", "larger", "huge"]):
            style["size_scale"] = 1.2
        elif _has(t, ["smaller", "subtle", "tiny"]):
            style["size_scale"] = 0.82
        if _has(t, ["uppercase", "all caps", "caps"]):
            style["uppercase"] = True
        if preset or style:
            return {
                "type": "set_captions",
                "enabled": True,
                "preset": preset,
                "style": style,
                "summary": "Update caption style" + (f" → {PRESETS[preset]['label']}" if preset else ""),
            }

    # ---- format edits -----------------------------------------------------------------
    for k, aspect in (
        ("square", "1:1"),
        ("1:1", "1:1"),
        ("vertical", "9:16"),
        ("9:16", "9:16"),
        ("portrait", "4:5"),
        ("4:5", "4:5"),
        ("landscape", "16:9"),
        ("16:9", "16:9"),
        ("horizontal", "16:9"),
    ):
        if _has(t, [k]) and _has(t, ["make", "convert", "switch", "change", "format", "version", "aspect", "it", "to"]):
            return {"type": "set_aspect", "aspect": aspect, "summary": f"Change aspect ratio to {aspect}"}
    if _has(t, ["silence", "silences", "pauses", "dead air"]):
        on = not _has(t, ["keep", "don't remove", "dont remove", "restore"])
        return {
            "type": "set_silence_removal",
            "enabled": on,
            "summary": ("Remove" if on else "Keep") + " silent pauses",
        }

    # ---- find clips ---------------------------------------------------------------
    if _has(
        t,
        [
            "find",
            "make",
            "create",
            "get",
            "give",
            "generate",
            "show",
            "clip",
            "clips",
            "moment",
            "moments",
            "highlight",
            "highlights",
            "funniest",
            "best",
        ],
    ):
        mood = next((m for m, ws in MOOD_WORDS.items() if _has(t, ws)), "any")
        genre = next((g for g, ws in GENRE_WORDS.items() if _has(t, ws)), None)
        position = (
            "end"
            if _has(t, ["near the end", "at the end", "towards the end", "last part", "ending", "end"])
            else "start"
            if _has(t, ["beginning", "start", "intro", "first part", "opening"])
            else "middle"
            if _has(t, ["middle"])
            else "any"
        )
        about = re.search(
            r"\b(?:about|on|mentioning|where .* talks? about)\s+([a-z0-9' -]{3,40}?)(?:[.?!,]|\s+(?:near|at|in|under|with)\b|$)",
            t,
        )
        query = [w for w in re.findall(r"[a-z0-9']+", about.group(1)) if len(w) > 2] if about else []
        dur = _duration(t)
        count = _count(t) or (1 if _has(t, ["funniest", "best", "the most", "single"]) else 3)
        action = {
            "type": "find_clips",
            "count": max(1, min(count, 10)),
            "mood": mood,
            "genre": genre,
            "position": position,
            "query": query,
        }
        if dur:
            action["min_dur"], action["max_dur"] = dur
        bits = [f"{action['count']} clip{'s' if action['count'] > 1 else ''}"]
        if mood != "any":
            bits.append(mood)
        if genre:
            bits.append(genre)
        if dur:
            bits.append(f"{dur[0]:.0f}–{dur[1]:.0f}s")
        if position != "any":
            bits.append(f"near the {position}")
        if query:
            bits.append("about " + " ".join(query))
        action["summary"] = "Find " + ", ".join(bits)
        return action

    return _llm_fallback(raw, has_clip)


ACTION_SCHEMA = (
    '{"type": "find_clips", "count": 1-10, "mood": "any|funny|emotional|intense|informative|inspiring", '
    '"position": "any|start|middle|end", "min_dur": seconds, "max_dur": seconds, "query": ["topic words"]} | '
    '{"type": "set_captions", "enabled": true, "preset": "' + "|".join(PRESETS) + '", "style": {"highlight": "#hex", '
    '"position": "top|middle|bottom"}} | {"type": "generate_publish", "platforms": ["youtube|instagram|tiktok|linkedin|'
    'facebook|x"], "tone": "compelling|professional|funny|energetic|educational|storytelling"} | '
    '{"type": "set_aspect", "aspect": "9:16|1:1|4:5|16:9"} | {"type": "set_silence_removal", "enabled": true} | '
    '{"type": "unsupported", "message": "why"}'
)


def _llm_fallback(raw: str, has_clip: bool) -> dict[str, Any]:
    if not llm.status()["available"]:
        return {
            "type": "unsupported",
            "message": "I couldn't map that to an editing action. Try “Find the "
            "funniest 30-second moment”, “Use bold yellow captions”, or “Write an Instagram caption”.",
        }
    try:
        data = llm.chat_json(
            "Map a video editor's request to exactly one JSON action. Only use the schema given. If the request "
            "can't be done with these actions, return the unsupported action.",
            f"Schema (one of): {ACTION_SCHEMA}\nRequest: {raw}",
            temperature=0.0,
            max_tokens=300,
        )
    except Exception:  # noqa: BLE001
        return {"type": "unsupported", "message": "I couldn't map that to an editing action."}
    if not isinstance(data, dict) or data.get("type") not in {
        "find_clips",
        "set_captions",
        "generate_publish",
        "set_aspect",
        "set_silence_removal",
        "unsupported",
    }:
        return {"type": "unsupported", "message": "I couldn't map that to an editing action."}
    data["summary"] = data.get("summary") or f"Interpreted by local LLM as: {data['type'].replace('_', ' ')}"
    data["via_llm"] = True
    return data
