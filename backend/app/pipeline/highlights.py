"""Highlight discovery: candidate windows + explainable, genre-aware scoring.

The pipeline is deliberately multi-signal (not keyword matching):

1. Words from speech-to-text are grouped into sentences (punctuation + pauses).
2. Candidate windows start and end on sentence boundaries, so each clip is a
   complete thought; videos without speech fall back to audio/scene windows.
3. Every candidate is scored on seven 0–100 dimensions from transcript structure,
   audio energy, sound events, motion and scene cuts, then weighted by the genre
   profile and the requested mood.
4. Overlapping / near-duplicate windows are suppressed (temporal IoU + text
   similarity), keeping the best of each group.
5. An optional local LLM pass (``llm.py``) re-reads the shortlist for semantic
   quality and blends in; the breakdown always shows what was used.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from .genres import (
    DANGLING,
    DIMENSIONS,
    FILLERS,
    GENRE_HINTS,
    HOOK_OPENERS,
    INTENSIFIERS,
    MOODS,
    PROFILES,
    STOPWORDS,
)
from .signals import Signals
from .transcribe import Word

_TOKEN = re.compile(r"[a-z0-9']+")


_PUNCT = "\"'.,!?;:()[]{}<>-–—…।॥¿¡“”‘’"


def tokens(text: str) -> list[str]:
    if text.isascii():
        return [t.strip("'") for t in _TOKEN.findall(text.lower()) if t.strip("'")]
    # Any other script (Hindi, Arabic, Japanese ...): whitespace words without punctuation, so the
    # scorer's novelty / relevance / repetition signals still work on non-English transcripts.
    return [w for w in (t.strip(_PUNCT) for t in text.lower().split()) if w]


def content_tokens(text: str) -> list[str]:
    return [t for t in tokens(text) if t not in STOPWORDS and len(t) > 2]


def stem(t: str) -> str:
    """Tiny suffix stripper so "mentioned" matches "mention" and "advice" matches "advices"."""
    for suf in ("ingly", "edly", "ing", "ers", "ies", "ied", "ed", "es", "er", "ly", "s"):
        if t.endswith(suf) and len(t) - len(suf) >= 4:
            return t[: -len(suf)] + ("y" if suf in ("ies", "ied") else "")
    return t


# Words that describe the request itself rather than the topic ("find the moments when …").
_REQUEST_WORDS = {
    "find",
    "moments",
    "moment",
    "clips",
    "clip",
    "parts",
    "part",
    "times",
    "time",
    "when",
    "where",
    "mentioned",
    "mentions",
    "mention",
    "talks",
    "talked",
    "talking",
    "about",
    "shared",
    "shares",
    "share",
    "says",
    "said",
    "speaker",
    "video",
    "show",
    "shows",
    "give",
    "gives",
    "want",
    "looking",
    "focus",
    "anything",
    "everything",
    "things",
    "thing",
    "stuff",
    "some",
    "best",
    "good",
    "great",
    "make",
    "made",
    "also",
    "like",
    "please",
}


def instruction_terms(text: str, k: int = 12) -> list[str]:
    """Topic words from the creator's custom instructions (request words removed)."""
    out: list[str] = []
    for t in content_tokens(text):
        if t not in _REQUEST_WORDS and t not in out:
            out.append(t)
    return out[:k]


@dataclass
class Sentence:
    start: float
    end: float
    text: str
    w0: int  # first word index
    w1: int  # last word index (inclusive)
    gap_before: float = 0.0
    gap_after: float = 0.0


def build_sentences(words: list[Word], max_gap: float = 0.85, max_words: int = 40) -> list[Sentence]:
    out: list[Sentence] = []
    if not words:
        return out
    start = 0
    for i, w in enumerate(words):
        last = i == len(words) - 1
        gap = (words[i + 1].s - w.e) if not last else 0.0
        ends = w.w.rstrip("\"')").endswith((".", "?", "!")) or gap > max_gap or (i - start + 1) >= max_words
        if ends or last:
            seg = words[start : i + 1]
            out.append(Sentence(seg[0].s, seg[-1].e, " ".join(x.w for x in seg).strip(), start, i))
            start = i + 1
    for j, s in enumerate(out):
        s.gap_before = s.start - out[j - 1].end if j else s.start
        s.gap_after = out[j + 1].start - s.end if j + 1 < len(out) else 2.0
    return out


@dataclass
class Prefs:
    count: int = 6
    min_dur: float = 20.0
    max_dur: float = 60.0
    genre: str = "auto"
    mood: str = "any"
    position: str = "any"  # any | start | middle | end
    query: list[str] = field(default_factory=list)
    instructions: str = ""  # free text, also given to the LLM editor
    # joins between separately downloaded sections of a long video: no clip may cross one
    barriers: list[float] = field(default_factory=list)
    # the video file, so the vision model can look at moments that have little or no speech
    media_src: str = ""
    pad_before: float = 0.25
    pad_after: float = 0.45
    target_dur: float | None = None  # preferred length; defaults to the middle of min/max


@dataclass
class Candidate:
    start: float
    end: float
    s0: int = -1
    s1: int = -1
    text: str = ""
    hook: str = ""
    dims: dict[str, float] = field(default_factory=dict)
    evidence: dict[str, list[str]] = field(default_factory=dict)
    heuristic: float = 0.0
    semantic: float | None = None
    score: int = 0
    reasons: list[str] = field(default_factory=list)
    title: str = ""
    llm_note: str = ""
    semantic_weight: float | None = None  # how much the AI score counts (Gemini > local model)

    @property
    def duration(self) -> float:
        return self.end - self.start


# --------------------------------------------------------------------------- context


@dataclass
class Context:
    sentences: list[Sentence]
    words: list[Word]
    signals: Signals
    prefs: Prefs
    genre: str
    weights: dict[str, float]
    idf: dict[str, float]
    idf_mean: float
    idf_std: float
    speech: bool


def detect_genre(words: list[Word], signals: Signals) -> tuple[str, dict[str, float]]:
    """Cheap genre guess from vocabulary, speech density and motion."""
    toks = Counter(tokens(" ".join(w.w for w in words)))
    total = sum(toks.values()) or 1
    hits = {g: sum(toks[t] for t in hints) for g, hints in GENRE_HINTS.items()}
    scores = {g: h / total * 1000 for g, h in hits.items()}
    dur = signals.duration or 1
    wpm = len(words) / dur * 60
    motion = float(np.mean(signals.motion)) if signals.motion.size else 0.0
    if motion < 7:  # talking heads and static shots are rarely gameplay
        scores["gaming"] *= 0.5
    best = max(scores, key=lambda g: scores[g])
    # Vocabulary only decides when the evidence is real (several distinct hits).
    if hits[best] >= 4 and scores[best] >= 6:
        return best, {k: round(v, 2) for k, v in scores.items()}
    if wpm >= 60:
        fallback = "podcast"  # speech-led content: interviews, talks, commentary
    elif motion > 9:
        fallback = "gaming"
    else:
        fallback = "entertainment"
    return fallback, {k: round(v, 2) for k, v in scores.items()}


def make_context(
    words: list[Word], signals: Signals, prefs: Prefs, weight_bias: dict[str, float] | None = None
) -> Context:
    sentences = build_sentences(words)
    genre = prefs.genre if prefs.genre in PROFILES else detect_genre(words, signals)[0]
    weights = dict(PROFILES[genre])
    mood_shift = {
        "funny": {"emotion": 0.06, "hook": 0.02, "novelty": -0.03, "context": -0.03},
        "emotional": {"emotion": 0.08, "context": 0.02, "visual": -0.04, "pacing": -0.02},
        "intense": {"emotion": 0.07, "visual": 0.04, "context": -0.05},
        "informative": {"novelty": 0.06, "context": 0.05, "emotion": -0.06},
        "inspiring": {"emotion": 0.04, "hook": 0.03, "novelty": 0.02, "visual": -0.03},
    }.get(prefs.mood, {})
    for k, v in mood_shift.items():
        weights[k] = max(0.01, weights[k] + v)
    for k, v in (weight_bias or {}).items():
        if k in weights:
            weights[k] = max(0.01, weights[k] * (1 + v))
    total = sum(weights.values())
    weights = {k: v / total for k, v in weights.items()}

    docs = [set(content_tokens(s.text)) for s in sentences] or [set()]
    df: Counter[str] = Counter()
    for d in docs:
        df.update(d)
    n = len(docs)
    idf = {t: math.log((1 + n) / (1 + c)) + 1 for t, c in df.items()}
    vals = np.array(list(idf.values())) if idf else np.array([1.0])
    speech = len(words) >= max(12, signals.duration / 30)
    return Context(
        sentences, words, signals, prefs, genre, weights, idf, float(vals.mean()), float(vals.std()) or 1.0, speech
    )


# --------------------------------------------------------------------------- candidates


def generate(ctx: Context) -> list[Candidate]:
    return _speech_candidates(ctx) if ctx.speech else _signal_candidates(ctx)


def _speech_candidates(ctx: Context) -> list[Candidate]:
    p, ss = ctx.prefs, ctx.sentences
    out: list[Candidate] = []
    for i, s0 in enumerate(ss):
        first_tok = (tokens(s0.text) or [""])[0]
        if first_tok in FILLERS and len(tokens(s0.text)) <= 2:
            continue  # a lone "So." / "Yeah." is never a good opener
        produced = 0
        for j in range(i, len(ss)):
            start, end = _padded(ctx, i, j)
            dur = end - start
            if dur > p.max_dur + 1.5:
                break
            if dur >= p.min_dur - 0.5:
                out.append(Candidate(start=start, end=end, s0=i, s1=j))
                produced += 1
                if produced >= 4:
                    break
    if not out and ss:  # video shorter than min_dur or sparse speech
        start, end = _padded(ctx, 0, len(ss) - 1)
        out.append(Candidate(start=start, end=min(end, start + p.max_dur), s0=0, s1=len(ss) - 1))
    return out


def _padded(ctx: Context, i: int, j: int) -> tuple[float, float]:
    ss, p = ctx.sentences, ctx.prefs
    start = ss[i].start - min(p.pad_before, max(0.0, ss[i].gap_before - 0.05))
    end = ss[j].end + min(p.pad_after, max(0.0, ss[j].gap_after - 0.05))
    return max(0.0, start), min(ctx.signals.duration, end)


def _signal_candidates(ctx: Context) -> list[Candidate]:
    """No usable speech: slide windows and snap them to scene cuts / quiet points."""
    p, sig = ctx.prefs, ctx.signals
    dur = sig.duration
    lengths = sorted({round(p.min_dur), round((p.min_dur + p.max_dur) / 2), round(p.max_dur)})
    out: list[Candidate] = []
    step = 2.0
    t = 0.0
    while t < dur - p.min_dur * 0.8:
        for L in lengths:
            s, e = _snap(sig, t), _snap(sig, min(dur, t + L))
            if p.min_dur - 1 <= e - s <= p.max_dur + 1:
                out.append(Candidate(start=s, end=e))
        t += step
    if not out:
        out.append(Candidate(start=0.0, end=min(dur, p.max_dur)))
    return out


def _snap(sig: Signals, t: float, radius: float = 1.5) -> float:
    near = [c for c in sig.cuts if abs(c - t) <= radius]
    if near:
        return min(near, key=lambda c: abs(c - t))
    if sig.loudness.size:
        a, b = max(0, int((t - radius) * 10)), min(sig.loudness.size, int((t + radius) * 10) + 1)
        if b > a:
            return (a + int(np.argmin(sig.loudness[a:b]))) / 10
    return t


# --------------------------------------------------------------------------- scoring


def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _short(text: str, n: int = 70) -> str:
    text = text.strip()
    return text if len(text) <= n else text[: n - 1].rsplit(" ", 1)[0] + "…"


def score(c: Candidate, ctx: Context) -> Candidate:
    sig, p = ctx.signals, ctx.prefs
    ev: dict[str, list[str]] = {k: [] for k in DIMENSIONS}
    if ctx.speech and c.s0 >= 0:
        sents = ctx.sentences[c.s0 : c.s1 + 1]
        words = ctx.words[sents[0].w0 : sents[-1].w1 + 1]
        c.text = " ".join(s.text for s in sents)
        first = sents[0].text
        c.hook = _short(first, 120)
    else:
        sents = []
        words = [w for w in ctx.words if c.start <= w.s < c.end]
        c.text = " ".join(w.w for w in words)
        first = c.text[:120]
        c.hook = _short(first, 120) if first else ""
    toks = tokens(c.text)
    ftoks = tokens(first)
    dur = max(c.duration, 0.1)

    # ---- hook ---------------------------------------------------------------
    hook = 42.0
    fl = first.lower()
    if ctx.speech:
        if first.rstrip().endswith("?"):
            hook += 16
            ev["hook"].append(f"Opens with a question: “{_short(first, 60)}”")
        opener = next((h for h in HOOK_OPENERS if fl.startswith(h) or f" {h} " in f" {fl[:40]} "), None)
        if opener:
            hook += 13
            ev["hook"].append(f"Strong opener (“{opener}…”)")
        if {"you", "your", "you're"} & set(ftoks):
            hook += 6
            ev["hook"].append("Speaks directly to the viewer")
        if re.search(r"\d", first):
            hook += 6
            ev["hook"].append("Concrete number in the first line")
        if 3 <= len(ftoks) <= 12:
            hook += 6
        elif len(ftoks) > 25:
            hook -= 8
            ev["hook"].append("First sentence is long before it lands")
        if ftoks and ftoks[0] in FILLERS:
            hook -= 14
            ev["hook"].append(f"Starts with a filler word (“{ftoks[0]}”)")
        lead = (words[0].s - c.start) if words else 0
        if lead > 1.0:
            hook -= 10
            ev["hook"].append(f"{lead:.1f}s of silence before the first word")
    lz = sig.loud_z(c.start, min(c.end, c.start + 3.5))
    hook += _clip(lz * 6, -8, 12)
    if lz > 0.8:
        ev["hook"].append(f"Energetic delivery in the first seconds (+{lz:.1f}σ loudness)")
    if sig.cuts_in(c.start, c.start + 3) and not ctx.speech:
        hook += 8
        ev["hook"].append("Visual change right at the start")

    # ---- context ------------------------------------------------------------
    ctxs = 55.0
    if ctx.speech and sents:
        if sents[0].gap_before >= 0.45:
            ctxs += 10
            ev["context"].append("Starts at a natural pause")
        last_txt = sents[-1].text.rstrip()
        if last_txt.endswith((".", "!")):
            ctxs += 14
            ev["context"].append("Ends on a finished sentence")
        elif last_txt.endswith("?"):
            ctxs -= 8
            ev["context"].append("Ends on an unanswered question")
        else:
            ctxs -= 6
        if sents[-1].gap_after >= 0.5:
            ctxs += 8
        if ftoks and ftoks[0] in DANGLING | {"and", "but", "because", "so"}:
            ctxs -= 16
            ev["context"].append(f"Opens with “{ftoks[0]}”, which may need earlier context")
        if len(sents) >= 3:
            ctxs += 6
            ev["context"].append(f"Develops a full thought across {len(sents)} sentences")
        elif len(toks) < 15:
            ctxs -= 10
    else:
        if any(abs(cu - c.start) < 0.6 for cu in sig.cuts):
            ctxs += 10
            ev["context"].append("Starts on a scene change")
        if any(abs(cu - c.end) < 0.6 for cu in sig.cuts):
            ctxs += 8
            ev["context"].append("Ends on a scene change")

    # ---- pacing -------------------------------------------------------------
    pace = 70.0
    if ctx.speech:
        wps = len(words) / dur
        if 2.2 <= wps <= 3.8:
            pace += 14
            ev["pacing"].append(f"Comfortable speech rate ({wps:.1f} words/s)")
        else:
            off = (2.2 - wps) if wps < 2.2 else (wps - 3.8)
            pace -= _clip(off * 18, 0, 35)
            ev["pacing"].append(f"{'Slow' if wps < 2.2 else 'Very fast'} delivery ({wps:.1f} words/s)")
        gaps = [b.s - a.e for a, b in zip(words, words[1:], strict=False)]
        long_gaps = sum(1 for g in gaps if g > 1.2)
        if long_gaps:
            pace -= min(long_gaps * 7, 28)
            ev["pacing"].append(f"{long_gaps} long pause{'s' if long_gaps > 1 else ''} (silence removal will help)")
    sil = sig.silence_ratio(c.start, c.end)
    pace -= sil * 45
    cut_rate = sig.cuts_in(c.start, c.end) / dur * 10
    if cut_rate >= 1:
        pace += min(cut_rate * 4, 12)
        ev["pacing"].append(f"{sig.cuts_in(c.start, c.end)} scene cuts keep it moving")

    # ---- novelty ------------------------------------------------------------
    nov = 50.0
    ct = content_tokens(c.text)
    if ct:
        mean_idf = float(np.mean([ctx.idf.get(t, ctx.idf_mean) for t in ct]))
        z = (mean_idf - ctx.idf_mean) / ctx.idf_std
        nov += _clip(z * 18, -20, 25)
        distinct = sorted(set(ct), key=lambda t: -ctx.idf.get(t, 0))[:3]
        if z > 0.3 and distinct:
            ev["novelty"].append("Distinctive topic words: " + ", ".join(distinct))
        rep = 1 - len(set(ct)) / len(ct)
        if rep > 0.45:
            nov -= 12
            ev["novelty"].append("Repetitive wording")
    nums = len(re.findall(r"\b\d[\d,.%]*\b", c.text))
    if nums:
        nov += min(nums * 4, 12)
        ev["novelty"].append(f"{nums} specific figure{'s' if nums > 1 else ''}")
    proper = len(re.findall(r"(?<![.?!]\s)(?<!^)\b[A-Z][a-z]{2,}", c.text))
    nov += min(proper * 2, 8)

    # ---- emotion ------------------------------------------------------------
    emo = 45.0
    lzw = sig.loud_z(c.start, c.end)
    pz = sig.peak_z(c.start, c.end)
    emo += _clip(lzw * 10, -15, 22) + _clip(pz * 5, 0, 12)
    if lzw > 0.6:
        ev["emotion"].append(f"Louder than the video average (+{lzw:.1f}σ)")
    lr = sig.loudness_range(c.start, c.end)
    if lr > 1.25:
        emo += 6
        ev["emotion"].append("Big swings in vocal intensity")
    burst = sig.noisy_burst_seconds(c.start, c.end)
    if burst >= 0.8:
        emo += min(burst * 5, 15)
        ev["emotion"].append(f"Laughter/applause-like audio for {burst:.1f}s")
    tokset = Counter(toks)
    lex = {m: sum(tokset[t] for t in MOODS[m]) for m in MOODS}
    hits = lex["emotional"] + lex["intense"] + lex["funny"]
    if hits:
        emo += min(hits * 3.5, 16)
        top = max(("emotional", "intense", "funny"), key=lambda m: lex[m])
        ev["emotion"].append(f"{top.capitalize()} language ({lex[top]} cue{'s' if lex[top] != 1 else ''})")
    excl = c.text.count("!")
    if excl:
        emo += min(excl * 4, 12)
    emo += min(sum(tokset[t] for t in INTENSIFIERS) * 2, 8)

    # ---- visual ---------------------------------------------------------------
    vis = 50.0
    mz = sig.motion_z(c.start, c.end)
    vis += _clip(mz * 12, -18, 28)
    if mz > 0.5:
        ev["visual"].append(f"High on-screen motion (+{mz:.1f}σ)")
    elif mz < -0.8:
        ev["visual"].append("Mostly static shot")
    vis += min(cut_rate * 6, 18)

    # ---- relevance --------------------------------------------------------------
    rel = 50.0
    ghits = sum(tokset[t] for t in GENRE_HINTS.get(ctx.genre, set()))
    if ghits:
        rel += min(ghits * 3, 15)
        ev["relevance"].append(f"On-topic for {ctx.genre} audiences")
    if p.mood in MOODS:
        mh = lex[p.mood]
        rel += min(mh * 6, 30) - (8 if mh == 0 else 0)
        if mh:
            ev["relevance"].append(f"Matches the “{p.mood}” mood ({mh} cue{'s' if mh != 1 else ''})")
    if p.query:
        stems = Counter(stem(t) for t in tokset.elements())
        hit_terms = [t for t in dict.fromkeys(p.query) if stems[stem(t)]]
        qh = sum(stems[stem(t)] for t in dict.fromkeys(p.query))
        cover = len(hit_terms) / max(1, len(set(p.query)))
        rel += min(qh * 8, 26) + 20 * cover - (14 if qh == 0 else 0)
        if hit_terms:
            ev["relevance"].append("Mentions what you asked for: " + ", ".join(hit_terms[:5]))
    target = p.target_dur or (p.min_dur + p.max_dur) / 2
    off = abs(dur - target) / max(1.0, p.max_dur - p.min_dur)
    rel += 8 - min(16.0, off * 24)

    c.dims = {
        k: round(_clip(v), 1)
        for k, v in {
            "hook": hook,
            "context": ctxs,
            "pacing": pace,
            "novelty": nov,
            "emotion": emo,
            "visual": vis,
            "relevance": rel,
        }.items()
    }
    c.evidence = ev
    raw = sum(ctx.weights[k] * c.dims[k] for k in c.dims)
    c.heuristic = round(_clip(50 + (raw - 50) * 1.6), 1)  # stretch so differences are readable
    c.score = round(c.heuristic)
    return c


def finalize(c: Candidate, ctx: Context) -> Candidate:
    """Combine heuristic + optional semantic score; write human reasons."""
    if c.semantic is not None:
        # The LLM reads meaning (and the creator's instructions); give it more say when asked.
        w = c.semantic_weight if c.semantic_weight is not None else 0.5 if ctx.prefs.instructions else 0.4
        c.score = round(_clip((1 - w) * c.heuristic + w * c.semantic))
    else:
        c.score = round(c.heuristic)
    dims = [k for k in DIMENSIONS if k in c.dims]
    ranked = sorted(dims, key=lambda k: -ctx.weights[k] * (c.dims[k] - 50))
    reasons: list[str] = []
    for k in ranked[:3]:
        if c.dims[k] >= 55 and c.evidence.get(k):
            reasons.append(c.evidence[k][0])
    weakest = min(dims, key=lambda k: c.dims[k])
    if c.dims[weakest] < 45 and c.evidence.get(weakest):
        reasons.append("Weaker: " + c.evidence[weakest][0][0].lower() + c.evidence[weakest][0][1:])
    if c.llm_note:
        reasons.insert(0, c.llm_note)
    c.reasons = reasons[:4] or ["Balanced segment with no standout signal"]
    if not c.title:
        c.title = heuristic_title(c)
    return c


def heuristic_title(c: Candidate) -> str:
    base = c.hook or c.text or "Highlight"
    base = re.sub(
        r"^(?:(?:so|and|but|um|uh|like|okay|yeah|well|you know|i mean|look|listen|right)[, ]+)+", "", base, flags=re.I
    ).strip()
    base = base.rstrip(".,;:")
    return _short(base[:1].upper() + base[1:], 70) if base else "Highlight"


def overlap(a: Candidate, b: Candidate) -> float:
    inter = max(0.0, min(a.end, b.end) - max(a.start, b.start))
    return inter / max(1e-6, min(a.duration, b.duration))


def text_sim(a: Candidate, b: Candidate) -> float:
    x, y = set(content_tokens(a.text)), set(content_tokens(b.text))
    return len(x & y) / max(1, len(x | y)) if x and y else 0.0


def suppress(cands: list[Candidate], k: int, max_overlap: float = 0.35, max_sim: float = 0.6) -> list[Candidate]:
    keep: list[Candidate] = []
    for c in sorted(cands, key=lambda c: -c.score):
        if all(overlap(c, o) <= max_overlap and text_sim(c, o) <= max_sim for o in keep):
            keep.append(c)
        if len(keep) >= k:
            break
    return keep


def position_filter(cands: list[Candidate], position: str, duration: float) -> list[Candidate]:
    if position == "any":
        return cands
    lo, hi = {"start": (0, 0.35), "middle": (0.3, 0.7), "end": (0.65, 1.01)}.get(position, (0, 1.01))
    f = [c for c in cands if lo <= (c.start + c.end) / 2 / max(duration, 1) <= hi]
    return f or cands


def fit_length(ctx: Context, i: int, j: int) -> tuple[int, int]:
    """Grow/shrink a sentence range until its padded length is inside [min_dur, max_dur].
    Grows forward first (keeps the hook, adds the payoff), then backward; shrinks from the end."""
    p, n = ctx.prefs, len(ctx.sentences)
    target = p.target_dur or (p.min_dur + p.max_dur) / 2

    def dur(a: int, b: int) -> float:
        s, e = _padded(ctx, a, b)
        return e - s

    while dur(i, j) < p.min_dur and (j + 1 < n or i > 0):
        fwd = dur(i, j + 1) if j + 1 < n else None
        back = dur(i - 1, j) if i > 0 else None
        # take the side that lands closest to the target without overshooting the max
        opts = [(abs(d - target), k) for k, d in (("f", fwd), ("b", back)) if d is not None and d <= p.max_dur + 1.5]
        if not opts:
            break
        if min(opts)[1] == "f":
            j += 1
        else:
            i -= 1
    while dur(i, j) > p.max_dur + 1.5 and j > i:
        j -= 1
    return i, j


def from_proposals(ctx: Context, proposals: list[dict]) -> list[Candidate]:
    """Turn AI-picked moments (sentence ranges or times) into scored candidates of the right length."""
    p = ctx.prefs
    out: list[Candidate] = []
    for pr in proposals:
        if ctx.speech and "s0" in pr and ctx.sentences:
            i, j = fit_length(ctx, int(pr["s0"]), min(int(pr["s1"]), len(ctx.sentences) - 1))
            start, end = _padded(ctx, i, j)
            c = Candidate(start=start, end=end, s0=i, s1=j)
        elif "start" in pr:
            s, e = _snap(ctx.signals, pr["start"]), _snap(ctx.signals, pr["end"])
            if e - s < p.min_dur:
                e = min(ctx.signals.duration, s + (p.target_dur or (p.min_dur + p.max_dur) / 2))
            e = min(e, s + p.max_dur)
            if ctx.speech and ctx.sentences:  # times on a speech video: snap to sentence bounds
                i = min(range(len(ctx.sentences)), key=lambda k: abs(ctx.sentences[k].start - s))
                j = min(range(len(ctx.sentences)), key=lambda k: abs(ctx.sentences[k].end - e))
                i, j = fit_length(ctx, i, max(i, j))
                s, e = _padded(ctx, i, j)
                c = Candidate(start=s, end=e, s0=i, s1=j)
            else:
                c = Candidate(start=s, end=e)
        else:
            continue
        if c.duration < max(4.0, p.min_dur * 0.6):
            continue
        if p.barriers and any(c.start + 0.3 < b < c.end - 0.3 for b in p.barriers):
            continue
        score(c, ctx)
        c.semantic = float(pr.get("score", 60))
        c.semantic_weight = 0.75
        c.dims["semantic"] = c.semantic
        if pr.get("title"):
            c.title = pr["title"]
        if pr.get("why"):
            c.llm_note = "Gemini: " + pr["why"].rstrip(".") + "."
        out.append(c)
    return out


def discover(
    words: list[Word],
    signals: Signals,
    prefs: Prefs,
    weight_bias: dict[str, float] | None = None,
    semantic=None,
    proposer=None,
) -> tuple[list[Candidate], Context]:
    """Full ranking. ``semantic`` is an optional callable(list[Candidate], Context) that
    fills ``semantic`` / ``title`` / ``llm_note`` on a shortlist. ``proposer`` is an optional
    callable(Context) -> list[dict] | None (Gemini): when it returns moments they lead the ranking
    and the local semantic pass is skipped."""
    ctx = make_context(words, signals, prefs, weight_bias)
    proposed: list[Candidate] = []
    if proposer is not None:
        try:
            proposed = from_proposals(ctx, proposer(ctx) or [])
        except Exception:  # noqa: BLE001
            import logging

            logging.getLogger("hypesift.highlights").exception("AI proposer failed; using the local pipeline")
    if proposed:
        proposed = position_filter(proposed, prefs.position, signals.duration)
        final = [finalize(c, ctx) for c in proposed]
        final = suppress(final, prefs.count)
        if len(final) < prefs.count:  # top up from the signal ranking
            extra = [finalize(score(c, ctx), ctx) for c in generate(ctx)]
            extra = [
                c
                for c in extra
                if not (prefs.barriers and any(c.start + 0.3 < b < c.end - 0.3 for b in prefs.barriers))
            ]
            final = suppress(final + [c for c in suppress(extra, prefs.count * 2)], prefs.count)
        final.sort(key=lambda c: -c.score)
        return final, ctx
    cands = [score(c, ctx) for c in generate(ctx)]
    if prefs.barriers:
        cands = [c for c in cands if not any(c.start + 0.3 < b < c.end - 0.3 for b in prefs.barriers)]
    cands = position_filter(cands, prefs.position, signals.duration)
    # With custom instructions the LLM gets a wider shortlist, so it can find matches the
    # keyword pass missed.
    wide = 3 if prefs.instructions else 2
    shortlist = suppress(cands, max(prefs.count * wide, prefs.count + 4))
    if semantic is not None and shortlist:
        try:
            semantic(shortlist, ctx)
        except Exception:  # noqa: BLE001 - semantic pass is best-effort; heuristic scores stand
            import logging

            logging.getLogger("hypesift.highlights").exception("semantic re-rank failed; using signal scores")
    final = [finalize(c, ctx) for c in shortlist]
    final = suppress(final, prefs.count)
    final.sort(key=lambda c: -c.score)
    return final, ctx
