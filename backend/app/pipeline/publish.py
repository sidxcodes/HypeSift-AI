"""Platform-specific publishing packages (titles, captions, descriptions, hashtags).

Primary engine: the local LLM (Ollama). Fallback: a transparent template engine
built from the clip's own transcript key phrases. Every package records its
``engine`` so the UI can label it honestly. Neither engine promises reach or SEO.
"""

from __future__ import annotations

import logging
import re
from collections import Counter

from . import llm
from .genres import STOPWORDS

log = logging.getLogger("hypesift.publish")

PLATFORMS = ["youtube", "instagram", "tiktok", "linkedin", "facebook", "x"]
TONES = ["compelling", "professional", "funny", "energetic", "educational", "storytelling"]

GENRE_TAGS = {
    "gaming": ["gaming", "gamer", "gameplay", "twitchclips"],
    "podcast": ["podcast", "podcastclips", "interview"],
    "education": ["learnontiktok", "education", "didyouknow"],
    "tutorial": ["tutorial", "howto", "tips"],
    "entertainment": ["funny", "entertainment"],
    "vlog": ["vlog", "dayinmylife"],
    "review": ["review", "tech", "honestreview"],
}

PLATFORM_RULES = {
    "youtube": "YouTube Shorts: 3 title options under 70 chars, a 2-3 sentence description, 5-8 search terms, "
               "3-6 hashtags including #Shorts, and one pinned-comment idea that invites discussion.",
    "instagram": "Instagram Reels: an engaging caption (2-4 short lines), a call to action, 8-15 relevant "
                 "hashtags, and one alternate caption in a different tone.",
    "tiktok": "TikTok: a concise hook-style description under 150 chars and 3-6 relevant hashtags.",
    "linkedin": "LinkedIn: a professional 3-5 sentence post with a takeaway and 2-4 hashtags; no slang.",
    "facebook": "Facebook: a friendly 2-3 sentence post with a question to spark comments and 1-3 hashtags.",
    "x": "X (Twitter): one post under 260 characters including at most 2 hashtags.",
}

SYSTEM = (
    "You write social media publishing copy for short video clips. Write only claims supported by the transcript. "
    "Never use misleading clickbait, never promise views, virality, rankings or SEO results. Keep emojis restrained "
    "(0-2 per field). Reply with JSON only."
)


def keyphrases(text: str, k: int = 6) -> list[str]:
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z0-9']+", text)]
    low = [w.lower().strip("'") for w in words]
    uni = Counter(w for w in low if w not in STOPWORDS and len(w) > 3)
    bi = Counter(
        f"{a} {b}" for a, b in zip(low, low[1:], strict=False)
        if a not in STOPWORDS and b not in STOPWORDS and len(a) > 2 and len(b) > 2
    )
    phrases = [p for p, c in bi.most_common(k) if c > 1] + [w for w, _ in uni.most_common(k * 2)]
    out: list[str] = []
    for p in phrases:
        if not any(p in o or o in p for o in out):
            out.append(p)
        if len(out) >= k:
            break
    return out


def _tag(s: str) -> str:
    return "#" + re.sub(r"[^A-Za-z0-9]", "", s.title() if " " in s else s.lower())


def template_package(title: str, hook: str, text: str, genre: str, platforms: list[str], tone: str) -> dict:
    kp = keyphrases(text)
    topic = kp[0] if kp else genre
    tags = [_tag(p) for p in kp[:5]] + ["#" + t for t in GENRE_TAGS.get(genre, [])]
    tags = list(dict.fromkeys(t for t in tags if len(t) > 2))
    quote = hook.strip().rstrip(".")
    quote = quote if len(quote) <= 110 else quote[:107].rsplit(" ", 1)[0] + "…"
    cta = {
        "funny": "Tag someone who needs to see this.",
        "educational": "Save this for later and follow for more.",
        "professional": "What's your take?",
        "energetic": "Follow for more moments like this!",
        "storytelling": "Watch to the end.",
    }.get(tone, "Would you agree? Let me know in the comments.")
    out: dict[str, dict] = {}
    for p in platforms:
        if p == "youtube":
            out[p] = {
                "titles": list(dict.fromkeys([title[:70], f"{topic.title()}: {quote}"[:70], quote[:70]])),
                "description": f"{quote}. {('A short clip about ' + ', '.join(kp[:3]) + '.') if kp else ''}".strip(),
                "search_terms": kp[:6],
                "hashtags": (["#Shorts"] + tags)[:6],
                "pinned_comment": f"What do you think about {topic}?",
            }
        elif p == "instagram":
            out[p] = {"caption": f"“{quote}”\n\n{cta}", "cta": cta, "hashtags": (tags + ["#reels"])[:12],
                      "alt_caption": f"{topic.title()} in under a minute. {cta}"}
        elif p == "tiktok":
            out[p] = {"description": f"{quote[:120]}", "hashtags": (tags + ["#fyp"])[:5]}
        elif p == "linkedin":
            out[p] = {"post": f"{quote}.\n\nA short takeaway on {', '.join(kp[:2]) or topic}. {cta}",
                      "hashtags": tags[:3]}
        elif p == "facebook":
            out[p] = {"post": f"{quote}. {cta}", "hashtags": tags[:2]}
        elif p == "x":
            body = f"“{quote}”"
            out[p] = {"post": (body[:230] + " " + " ".join(tags[:2])).strip()}
    return {"engine": "template engine (transcript key phrases)", "tone": tone, "platforms": out}


def llm_package(title: str, text: str, genre: str, platforms: list[str], tone: str) -> dict:
    rules = "\n".join(f"- {PLATFORM_RULES[p]}" for p in platforms)
    schema = {
        "youtube": {"titles": ["..."], "description": "...", "search_terms": ["..."], "hashtags": ["#Shorts"],
                    "pinned_comment": "..."},
        "instagram": {"caption": "...", "cta": "...", "hashtags": ["#..."], "alt_caption": "..."},
        "tiktok": {"description": "...", "hashtags": ["#..."]},
        "linkedin": {"post": "...", "hashtags": ["#..."]},
        "facebook": {"post": "...", "hashtags": ["#..."]},
        "x": {"post": "..."},
    }
    user = (
        f"Tone: {tone} (stay truthful). Content type: {genre}. Working title: {title}\n"
        f"Transcript of the clip:\n\"\"\"{text[:2500]}\"\"\"\n\nProduce:\n{rules}\n\n"
        f"Return JSON with exactly these keys: {{{', '.join(repr(p) for p in platforms)}}} shaped like "
        f"{ {p: schema[p] for p in platforms} }"
    )
    data = llm.chat_json(SYSTEM, user, temperature=0.6, max_tokens=1600)
    if not isinstance(data, dict):
        raise ValueError("LLM returned non-object")
    cleaned: dict[str, dict] = {}
    for p in platforms:
        block = data.get(p)
        if isinstance(block, dict) and block:
            if "hashtags" in block and isinstance(block["hashtags"], list):
                block["hashtags"] = [h if str(h).startswith("#") else f"#{h}" for h in block["hashtags"] if h][:15]
            cleaned[p] = block
    if not cleaned:
        raise ValueError("LLM package empty")
    return {"engine": llm.engine_label(), "tone": tone, "platforms": cleaned}


def generate(title: str, hook: str, text: str, genre: str, platforms: list[str] | None = None,
             tone: str = "compelling", allow_llm: bool = True) -> dict:
    platforms = [p for p in (platforms or PLATFORMS) if p in PLATFORMS]
    tone = tone if tone in TONES else "compelling"
    fallback = template_package(title, hook, text, genre, platforms, tone)
    if allow_llm and llm.status()["available"]:
        try:
            pkg = llm_package(title, text, genre, platforms, tone)
            for p in platforms:  # fill any platform the model skipped
                pkg["platforms"].setdefault(p, fallback["platforms"][p])
            return pkg
        except Exception as e:  # noqa: BLE001
            log.warning("LLM publish package failed, using template: %s", e)
            fallback["note"] = "The local LLM failed for this clip, so template copy was used."
    elif allow_llm:
        fallback["note"] = "Local LLM unavailable: " + llm.status()["reason"]
    return fallback
