"""Fix with AI: correct a clip by describing the problem in plain words.

"start 2 seconds earlier", "it ends mid-sentence", "cut the first sentence", "make the title
funnier", "bigger captions", "the captions say 'gonna' but he said 'Goa'", "zoom in more" ...

A request becomes a list of small, validated edit operations. Common requests are understood by
fast rules; anything else goes to the local LLM, which sees the clip's transcript with timings
and returns the same operations. Boundaries are then snapped like a human editor would: never
mid-word, preferring the start/end of a sentence nearby.
"""

from __future__ import annotations

import copy
import logging
import re
from typing import Any

from . import captions, llm
from .highlights import build_sentences
from .transcribe import Word

log = logging.getLogger("hypesift.clipfix")

NUM = r"(\d+(?:\.\d+)?)"
WORDNUM = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "a few": 3,
    "a couple of": 2,
    "a bit": 1.5,
    "half a": 0.5,
}


def _num(text: str) -> str:
    t = text.lower()
    for w, n in WORDNUM.items():
        t = re.sub(rf"\b{w}\b", str(n), t)
    return t


# --------------------------------------------------------------------------- rules


def rule_ops(request: str) -> list[dict[str, Any]]:
    t = _num(request.lower().strip())
    ops: list[dict[str, Any]] = []
    # boundaries
    if m := re.search(rf"start(?:s|ing)?\s+(?:it\s+)?{NUM}\s*(?:s|sec|secs|seconds?)\s+(earlier|before|sooner)", t):
        ops.append({"op": "shift_start", "by": -float(m.group(1))})
    elif m := re.search(rf"start(?:s|ing)?\s+(?:it\s+)?{NUM}\s*(?:s|sec|secs|seconds?)\s+(later|after)", t):
        ops.append({"op": "shift_start", "by": float(m.group(1))})
    if m := re.search(rf"end(?:s|ing)?\s+(?:it\s+)?{NUM}\s*(?:s|sec|secs|seconds?)\s+(later|after|longer)", t):
        ops.append({"op": "shift_end", "by": float(m.group(1))})
    elif m := re.search(rf"end(?:s|ing)?\s+(?:it\s+)?{NUM}\s*(?:s|sec|secs|seconds?)\s+(earlier|sooner|before)", t):
        ops.append({"op": "shift_end", "by": -float(m.group(1))})
    if re.search(
        r"(ends?|cuts?|stops?)\s+(off\s+)?(mid|in the middle|abruptly|too early|too soon)|cut off at the end", t
    ):
        ops.append({"op": "end_at_sentence", "direction": "later"})
    if re.search(r"(starts?|begins?)\s+(mid|in the middle|abruptly|too late)", t):
        ops.append({"op": "start_at_sentence", "direction": "earlier"})
    if re.search(r"(remove|cut|drop|skip)\s+(the\s+)?first\s+(sentence|line|part)", t):
        ops.append({"op": "drop_first_sentence"})
    if re.search(r"(remove|cut|drop|skip)\s+(the\s+)?last\s+(sentence|line|part)", t):
        ops.append({"op": "drop_last_sentence"})
    if m := re.search(rf"(?:make it|keep it|max(?:imum)?|only)\s+{NUM}\s*(?:s|sec|secs|seconds?)", t):
        ops.append({"op": "set_length", "seconds": float(m.group(1))})
    elif re.search(r"\b(shorter|too long)\b", t):
        ops.append({"op": "drop_last_sentence"})
    elif re.search(r"\b(longer|too short)\b", t):
        ops.append({"op": "end_at_sentence", "direction": "later"})
    # title
    if m := re.search(r"title\s*(?:to|should be|=|:)\s*[\"“']?(.+?)[\"”']?\s*$", request, re.I):
        ops.append({"op": "set_title", "text": m.group(1).strip()[:100]})
    # captions
    if re.search(
        r"(bigger|larger|increase).{0,20}(caption|subtitle|text)|(caption|subtitle)s?.{0,15}(bigger|larger)", t
    ):
        ops.append({"op": "caption_size", "scale": 1.2})
    if re.search(r"(smaller|reduce).{0,20}(caption|subtitle|text)|(caption|subtitle)s?.{0,15}smaller", t):
        ops.append({"op": "caption_size", "scale": 0.83})
    if re.search(r"(remove|turn off|no|hide|disable)\s+(the\s+)?(captions|subtitles)", t):
        ops.append({"op": "captions", "enabled": False})
    elif re.search(r"(add|turn on|show|enable)\s+(the\s+)?(captions|subtitles)", t):
        ops.append({"op": "captions", "enabled": True})
    for pos in ("top", "middle", "bottom"):
        if re.search(rf"(caption|subtitle)s?.{{0,20}}\b(to|at|on)\s+the\s+{pos}", t):
            ops.append({"op": "caption_position", "value": pos})
    for key, st in captions.PRESETS.items():
        if re.search(
            rf"\b{re.escape(st['label'].lower())}\b.{{0,12}}(style|caption)|(style|caption).{{0,20}}\b{re.escape(st['label'].lower())}\b",
            t,
        ):
            ops.append({"op": "caption_preset", "value": key})
            break
    if m := re.search(
        r"(?:says?|shows?|wrote|written|spelled)\s+[\"“']?([\w'-]+)[\"”']?\s+(?:but|instead of|should be|it should be|not)\s+[\"“']?([\w' -]+?)[\"”']?\s*(?:$|[,.;!]|\s+and\s)",
        request,
        re.I,
    ):
        right = re.sub(
            r"^(?:but\s+)?(?:it\s*'?s|it\s+is|it\s+should\s+be|should\s+be|is|was)\s+",
            "",
            m.group(2).strip(),
            flags=re.I,
        )
        ops.append({"op": "fix_word", "wrong": m.group(1), "right": right})
    # look
    if re.search(r"(make it|switch to|change to)\s+(vertical|portrait|9:16)", t):
        ops.append({"op": "aspect", "value": "9:16"})
    if re.search(r"(make it|switch to|change to)\s+(square|1:1)", t):
        ops.append({"op": "aspect", "value": "1:1"})
    if re.search(r"(make it|switch to|change to)\s+(landscape|horizontal|16:9)", t):
        ops.append({"op": "aspect", "value": "16:9"})
    if re.search(r"(no|remove|turn off|stop)\s+(the\s+)?zoom", t):
        ops.append({"op": "zoom", "start": False, "key_phrases": False})
    elif re.search(r"(add|more|turn on)\s+zoom|zoom in more", t):
        ops.append({"op": "zoom", "start": True, "key_phrases": True})
    if re.search(r"(remove|cut)\s+(the\s+)?(silence|pauses|gaps)", t):
        ops.append({"op": "silence_removal", "enabled": True})
    if re.search(r"progress bar", t):
        ops.append(
            {"op": "progress_bar", "enabled": not re.search(r"(no|remove|turn off|hide)\s+(the\s+)?progress", t)}
        )
    if re.search(r"(show|whole|full|entire)\s+(the\s+)?(frame|picture|screen)|don'?t crop|not cropped", t):
        ops.append({"op": "crop_mode", "value": "fit"})
    if re.search(r"(follow|focus on|track)\s+(the\s+)?(face|speaker|person)", t):
        ops.append({"op": "crop_mode", "value": "auto"})
    return ops


# --------------------------------------------------------------------------- LLM

SCHEMA = """Operations (use only these, times in seconds relative to the clip's current start):
{"op":"shift_start","by":-2.0}  {"op":"shift_end","by":3.0}  {"op":"set_start","t":-4.2}  {"op":"set_end","t":31.0}
{"op":"start_at_sentence","direction":"earlier|later"}  {"op":"end_at_sentence","direction":"earlier|later"}
{"op":"drop_first_sentence"}  {"op":"drop_last_sentence"}  {"op":"set_length","seconds":30}
{"op":"set_title","text":"..."}  {"op":"caption_preset","value":"<one of PRESETS>"}  {"op":"caption_size","scale":1.2}
{"op":"captions","enabled":true}  {"op":"caption_position","value":"top|middle|lower|bottom"}
{"op":"caption_transition","value":"<one of TRANSITIONS>"}  {"op":"caption_effect","value":"<one of EFFECTS>"}
{"op":"fix_word","wrong":"gonna","right":"Goa"}  {"op":"aspect","value":"9:16|1:1|4:5|16:9"}
{"op":"crop_mode","value":"auto|center|fit|facecam"}  {"op":"zoom","start":true,"key_phrases":true}
{"op":"silence_removal","enabled":true}  {"op":"progress_bar","enabled":true}  {"op":"hook_title","text":"... or null"}"""


def llm_ops(request: str, ctx: dict) -> tuple[list[dict], str]:
    lines = "\n".join(f"[{s:+.1f}s → {e:+.1f}s] {txt}" for s, e, txt in ctx["sentences"])
    system = (
        "You are a careful senior video editor fixing one short clip for a creator. Understand what they mean, "
        "like a human editor would, and express the fix ONLY as the JSON operations listed. Keep changes minimal: "
        "change only what the request is about (e.g. moving the start must not move the end). "
        "Never invent words that aren't in the transcript. Reply JSON only."
    )
    user = (
        f"{SCHEMA.replace('<one of PRESETS>', '|'.join(captions.PRESETS)).replace('<one of TRANSITIONS>', '|'.join(captions.TRANSITIONS)).replace('<one of EFFECTS>', '|'.join(captions.EFFECTS))}\n\n"
        f'Clip now: {ctx["duration"]:.1f}s long, title "{ctx["title"]}", captions {ctx["captions"]}, aspect {ctx["aspect"]}.\n'
        f"Transcript around the clip (0s = clip start, clip ends at {ctx['duration']:.1f}s; negative = before it):\n{lines}\n\n"
        f'Creator\'s request: "{request}"\n'
        'Return {"ops": [...], "reply": "one friendly sentence saying what you changed"}'
    )
    d = llm.chat_json(system, user, temperature=0.2, max_tokens=500)
    if not isinstance(d, dict):
        return [], ""
    ops = [o for o in d.get("ops") or [] if isinstance(o, dict) and "op" in o]
    return ops, str(d.get("reply") or "").strip()


def rewrite_title(request: str, title: str, text: str) -> str | None:
    if not llm.status()["available"]:
        return None
    try:
        d = llm.chat_json(
            "You write titles for short videos. Truthful, under 60 characters, no emojis. Reply JSON only.",
            f'Current title: "{title}"\nWhat is said: """{text[:1500]}"""\nCreator asks: "{request}"\nReturn {{"title": "..."}}',
            temperature=0.7,
            max_tokens=80,
        )
        t = str(d.get("title", "")).strip().strip('"')
        return t[:100] if len(t) >= 3 else None
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- apply


def _snap_start(t: float, words: list[Word], sentences, prefer: str = "nearest") -> float:
    starts = [s.start for s in sentences]
    near = [s for s in starts if abs(s - t) <= 1.5]
    if near:
        return min(near, key=lambda s: abs(s - t))
    ws = [w.s for w in words if abs(w.s - t) <= 1.0]
    return min(ws, key=lambda s: abs(s - t)) - 0.12 if ws else t


def _snap_end(t: float, words: list[Word], sentences) -> float:
    ends = [s.end for s in sentences]
    near = [e for e in ends if abs(e - t) <= 1.5]
    if near:
        return min(near, key=lambda e: abs(e - t)) + 0.3
    ws = [w.e for w in words if abs(w.e - t) <= 1.0]
    return min(ws, key=lambda e: abs(e - t)) + 0.2 if ws else t


def apply(ops: list[dict], clip: dict, words: list[Word], source_duration: float, request: str = "") -> dict:
    """clip: {start, end, title, text, edits}. Returns {start, end, title, edits, changes, needs_render}."""
    start, end = float(clip["start"]), float(clip["end"])
    edits = copy.deepcopy(clip.get("edits") or {})
    title = clip.get("title", "")
    changes: list[str] = []
    timing = False
    sentences = build_sentences([w for w in words if start - 60 <= w.s <= end + 60])
    for op in ops:
        kind = op.get("op")
        try:
            if kind == "shift_start":
                start = _snap_start(start + float(op["by"]), words, sentences)
                timing = True
            elif kind == "shift_end":
                end = _snap_end(end + float(op["by"]), words, sentences)
                timing = True
            elif kind == "set_start":
                start = _snap_start(clip["start"] + float(op["t"]), words, sentences)
                timing = True
            elif kind == "set_end":
                end = _snap_end(clip["start"] + float(op["t"]), words, sentences)
                timing = True
            elif kind == "start_at_sentence":
                if op.get("direction") == "later":
                    nxt = [s.start for s in sentences if s.start > start + 0.3]
                    start = (nxt[0] - 0.12) if nxt else start
                else:
                    prev = [s.start for s in sentences if s.start <= start + 0.3]
                    start = (prev[-1] - 0.12) if prev else start
                timing = True
            elif kind == "end_at_sentence":
                if op.get("direction") == "earlier":
                    prev = [s.end for s in sentences if s.end < end - 0.3]
                    end = (prev[-1] + 0.3) if prev else end
                else:
                    cur = [s.end for s in sentences if s.end >= end - 0.3]
                    end = (cur[0] + 0.3) if cur else end
                timing = True
            elif kind == "drop_first_sentence":
                inside = [s for s in sentences if s.start >= start - 0.3 and s.end <= end + 0.3]
                if len(inside) > 1:
                    start = inside[1].start - 0.12
                    timing = True
            elif kind == "drop_last_sentence":
                inside = [s for s in sentences if s.start >= start - 0.3 and s.end <= end + 0.3]
                if len(inside) > 1:
                    end = inside[-2].end + 0.3
                    timing = True
            elif kind == "set_length":
                target = max(5.0, float(op["seconds"]))
                end = _snap_end(start + target, words, sentences)
                timing = True
            elif kind == "set_title":
                text = str(op.get("text") or "").strip()
                if text in ("", "funnier", "better") or len(text) < 3:
                    text = rewrite_title(request, title, clip.get("text", "")) or title
                if text and text != title:
                    title = text[:100]
                    changes.append(f"Title: “{title}”")
            elif kind == "caption_preset" and op.get("value") in captions.PRESETS:
                ce = dict(edits.get("captions") or {})
                ce.update({"preset": op["value"], "chunks": None, "enabled": True})
                edits["captions"] = ce
                changes.append(f"Caption style: {captions.PRESETS[op['value']]['label']}")
            elif kind == "caption_size":
                ce = dict(edits.get("captions") or {})
                st = dict(ce.get("style") or {})
                st["size_scale"] = round(max(0.5, min(2.0, float(st.get("size_scale") or 1) * float(op["scale"]))), 2)
                ce["style"] = st
                edits["captions"] = ce
                changes.append(f"Captions {'bigger' if float(op['scale']) > 1 else 'smaller'} ({st['size_scale']:.0%})")
            elif kind == "captions":
                ce = dict(edits.get("captions") or {})
                ce["enabled"] = bool(op.get("enabled"))
                edits["captions"] = ce
                changes.append("Captions on" if ce["enabled"] else "Captions off")
            elif kind == "caption_position" and op.get("value") in captions.POSITIONS:
                ce = dict(edits.get("captions") or {})
                ce["style"] = {**(ce.get("style") or {}), "position": op["value"]}
                edits["captions"] = ce
                changes.append(f"Captions moved to the {op['value']}")
            elif kind in ("caption_transition", "caption_effect"):
                table = captions.TRANSITIONS if kind == "caption_transition" else captions.EFFECTS
                if op.get("value") in table:
                    ce = dict(edits.get("captions") or {})
                    ce[kind.split("_")[1]] = op["value"]
                    edits["captions"] = ce
                    changes.append(f"Caption {kind.split('_')[1]}: {table[op['value']]}")
            elif kind == "fix_word":
                wrong, right = str(op.get("wrong", "")).strip(), str(op.get("right", "")).strip()
                if wrong and right:
                    edits["_fix_words"] = [*(edits.get("_fix_words") or []), [wrong, right]]
                    changes.append(f"Captions: “{wrong}” → “{right}”")
            elif kind == "aspect" and op.get("value") in ("9:16", "1:1", "4:5", "16:9"):
                edits["aspect"] = op["value"]
                changes.append(f"Size: {op['value']}")
            elif kind == "crop_mode" and op.get("value") in ("auto", "center", "fit", "facecam", "manual"):
                edits["crop"] = {**(edits.get("crop") or {}), "mode": op["value"]}
                edits["crop_locked"] = True
                changes.append(
                    {
                        "auto": "Framing follows the speaker",
                        "fit": "Whole frame shown",
                        "center": "Centre crop",
                        "facecam": "Facecam on top, game below",
                        "manual": "Manual framing",
                    }[op["value"]]
                )
            elif kind == "zoom":
                edits["zoom"] = {"start": bool(op.get("start")), "key_phrases": bool(op.get("key_phrases"))}
                changes.append("Zoom punch-ins on" if any(edits["zoom"].values()) else "Zoom off")
            elif kind == "silence_removal":
                edits["silence_removal"] = bool(op.get("enabled"))
                changes.append("Silent pauses removed" if edits["silence_removal"] else "Pauses kept")
            elif kind == "progress_bar":
                edits["progress_bar"] = {**(edits.get("progress_bar") or {}), "enabled": bool(op.get("enabled"))}
                changes.append("Progress bar on" if op.get("enabled") else "Progress bar off")
            elif kind == "hook_title":
                ovs = [o for o in edits.get("overlays") or [] if o.get("kind") != "title"]
                if op.get("text"):
                    ovs.insert(0, {"kind": "title", "text": str(op["text"])[:80], "start": 0, "end": 3.2})
                edits["overlays"] = ovs
                changes.append(f"Hook text: “{op['text']}”" if op.get("text") else "Hook text removed")
        except (KeyError, TypeError, ValueError) as e:
            log.info("skipped op %s: %s", op, e)
    start = max(0.0, start)
    end = min(source_duration, end)
    if end - start < 3:
        end = min(source_duration, start + 3)
    if timing:
        ds, de = start - float(clip["start"]), end - float(clip["end"])
        bits = []
        if abs(ds) >= 0.05:
            bits.append(f"start {abs(ds):.1f}s {'earlier' if ds < 0 else 'later'}")
        if abs(de) >= 0.05:
            bits.append(f"end {abs(de):.1f}s {'later' if de > 0 else 'earlier'}")
        if bits:
            changes.insert(
                0, "Moved the " + " and the ".join(bits) + f" (now {end - start:.1f}s, on sentence boundaries)"
            )
            ce = dict(edits.get("captions") or {})
            ce["chunks"] = None  # rebuild captions for the new range
            edits["captions"] = ce
    return {"start": round(start, 3), "end": round(end, 3), "title": title, "edits": edits, "changes": changes}


def fix_words_in_chunks(chunks: list[dict], fixes: list[list[str]]) -> list[dict]:
    """Replace misheard words in caption chunks (case-insensitive, whole words)."""
    out = []
    for ch in chunks:
        ch = copy.deepcopy(ch)
        for wrong, right in fixes:
            pat = re.compile(rf"\b{re.escape(wrong)}\b", re.I)
            ch["text"] = pat.sub(right, ch["text"])
            for w in ch.get("words") or []:
                w["w"] = pat.sub(right, w["w"])
        out.append(ch)
    return out


def context(clip: dict, words: list[Word]) -> dict:
    s0, e0 = float(clip["start"]), float(clip["end"])
    near = [w for w in words if s0 - 20 <= w.s <= e0 + 20]
    sents = build_sentences(near)
    ce = (clip.get("edits") or {}).get("captions") or {}
    return {
        "duration": e0 - s0,
        "title": clip.get("title", ""),
        "aspect": (clip.get("edits") or {}).get("aspect", "9:16"),
        "captions": f"{'on' if ce.get('enabled', True) else 'off'}, style {ce.get('preset', 'bold_creator')}",
        "sentences": [(s.start - s0, s.end - s0, s.text) for s in sents][:60],
    }


def plan(request: str, clip: dict, words: list[Word], allow_llm: bool = True) -> tuple[list[dict], str, str]:
    """(ops, reply, engine). Rules first; the LLM handles anything the rules don't understand."""
    ops = rule_ops(request)
    wants_title = re.search(r"\btitle\b", request, re.I) and not any(o["op"] == "set_title" for o in ops)
    if wants_title:
        ops.append({"op": "set_title", "text": ""})
    if ops:
        return ops, "", "rules"
    if allow_llm and llm.status()["available"]:
        try:
            ops, reply = llm_ops(request, context(clip, words))
            if ops:
                return ops, reply, llm.engine_label()
        except Exception as e:  # noqa: BLE001
            log.warning("fix-with-AI LLM failed: %s", e)
    return [], "", "none"
