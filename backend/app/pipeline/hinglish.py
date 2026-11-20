"""Hinglish captions: Hindi speech written in everyday Latin letters ("kapde to maine pahan liye").

Free and offline. Works word by word (so caption timing is untouched): a dictionary of very common
words and English loanwords spelled the way people text them, then a Devanagari -> casual-Latin
transliteration with schwa deletion (कपड़े -> kapde, समझना -> samajhna, अपना -> apna).
Words that are already Latin (GTA, OK, 2026) pass through unchanged.
"""

from __future__ import annotations

import re
import unicodedata

COMMON = {
    # everyday Hindi, spelled the usual chat way
    "है": "hai",
    "हैं": "hain",
    "हूँ": "hoon",
    "हूं": "hoon",
    "हो": "ho",
    "था": "tha",
    "थी": "thi",
    "थे": "the",
    "में": "mein",
    "मैं": "main",
    "मैंने": "maine",
    "नहीं": "nahi",
    "नही": "nahi",
    "क्या": "kya",
    "क्यों": "kyun",
    "तो": "to",
    "यह": "yeh",
    "ये": "ye",
    "वह": "woh",
    "वो": "wo",
    "और": "aur",
    "कौन": "kaun",
    "हाँ": "haan",
    "हां": "haan",
    "भी": "bhi",
    "ही": "hi",
    "जी": "ji",
    "की": "ki",
    "का": "ka",
    "के": "ke",
    "को": "ko",
    "से": "se",
    "पर": "par",
    "यार": "yaar",
    "अच्छा": "accha",
    "कुछ": "kuch",
    "मुझे": "mujhe",
    "तुम": "tum",
    "तुम्हें": "tumhe",
    "आप": "aap",
    "हम": "hum",
    "भाई": "bhai",
    "भाइयों": "bhaiyon",
    "बहुत": "bahut",
    "अभी": "abhi",
    "कभी": "kabhi",
    "सब": "sab",
    "एक": "ek",
    "दो": "do",
    "तीन": "teen",
    "चार": "chaar",
    "पांच": "paanch",
    "क्योंकि": "kyunki",
    "लेकिन": "lekin",
    "मतलब": "matlab",
    "बोल": "bol",
    "बोला": "bola",
    "देख": "dekh",
    "देखो": "dekho",
    "चल": "chal",
    "चलो": "chalo",
    "अरे": "arre",
    "ओए": "oye",
    "ओह": "oh",
    "हैलो": "hello",
    "हेलो": "hello",
    "ठीक": "theek",
    "पैसे": "paise",
    "पैसा": "paisa",
    "गाड़ी": "gaadi",
    "मेरा": "mera",
    "मेरी": "meri",
    "मेरे": "mere",
    "तेरा": "tera",
    "तेरी": "teri",
    "तेरे": "tere",
    "अपना": "apna",
    "अपनी": "apni",
    "अपने": "apne",
    "कहाँ": "kahan",
    "कहां": "kahan",
    "यहाँ": "yahan",
    "यहां": "yahan",
    "वहाँ": "wahan",
    "वहां": "wahan",
    "कैसे": "kaise",
    "ऐसे": "aise",
    "जैसे": "jaise",
    "पहले": "pehle",
    "बाद": "baad",
    "साथ": "saath",
    "रहा": "raha",
    "रही": "rahi",
    "रहे": "rahe",
    "गया": "gaya",
    "गई": "gayi",
    "गए": "gaye",
    "करो": "karo",
    "करना": "karna",
    "किया": "kiya",
    "दिया": "diya",
    "लिया": "liya",
    "लिए": "liye",
    "चाहिए": "chahiye",
    "सही": "sahi",
    "बस": "bas",
    "फिर": "phir",
    "जल्दी": "jaldi",
    "नया": "naya",
    # English loanwords as Hindi speakers write them in Devanagari
    "बट": "but",
    "सेकंड": "second",
    "चेक": "check",
    "वाशरूम": "washroom",
    "बाथरूम": "bathroom",
    "गेम": "game",
    "गेमिंग": "gaming",
    "वीडियो": "video",
    "लाइक": "like",
    "सब्सक्राइब": "subscribe",
    "चैनल": "channel",
    "ओके": "ok",
    "सॉरी": "sorry",
    "थैंक्यू": "thank you",
    "ब्रो": "bro",
    "कार": "car",
    "मिशन": "mission",
    "प्लेयर": "player",
    "स्ट्रीम": "stream",
    "लाइव": "live",
    "फ्रेंड्स": "friends",
    "गाइज़": "guys",
    "गाइज": "guys",
    "बैंक": "bank",
    "पुलिस": "police",
    "मनी": "money",
    "शॉप": "shop",
    "रेंट": "rent",
    "जॉब": "job",
    "ब्रांड": "brand",
    "पेंट": "paint",
    "रिपेयर": "repair",
    "फॉल्ट": "fault",
    "सिटी": "city",
    "वाइस": "vice",
    "मैप": "map",
    "वेट": "wait",
    "स्टार्ट": "start",
    "नेक्स्ट": "next",
    "बेस्ट": "best",
    "टाइम": "time",
    "लेवल": "level",
    "मोड": "mode",
    "ग्राफिक्स": "graphics",
    "डिटेल": "detail",
    "ओपन": "open",
    "डोर": "door",
    "टॉयलेट": "toilet",
    "फोन": "phone",
    "कॉल": "call",
    "मैसेज": "message",
    "ऑनलाइन": "online",
    "सर्वर": "server",
    "प्रॉब्लम": "problem",
    "बग": "bug",
    "एक्चुअली": "actually",
    "बेसिकली": "basically",
    "लिटरली": "literally",
    "सीरियसली": "seriously",
    "फास्ट": "fast",
    "स्लो": "slow",
    "स्पीड": "speed",
    "गन": "gun",
    "शूट": "shoot",
    "किल": "kill",
    "डेड": "dead",
    "फायर": "fire",
    "सेव": "save",
    "अपडेट": "update",
    "ट्रेलर": "trailer",
    "हाय": "hi",
    "बाय": "bye",
    "प्लीज़": "please",
    "प्लीज": "please",
    "ऑफ": "off",
    "ऑन": "on",
    "टीम": "team",
    "चैट": "chat",
    "डोनेशन": "donation",
    "बॉस": "boss",
    "पॉसिबल": "possible",
    "इम्पॉसिबल": "impossible",
    "बिकॉज़": "because",
    "बिकॉज": "because",
    "थिंक": "think",
    "इट्स": "it's",
    "इट": "it",
    "मैराथन": "marathon",
    "मैराथॉन": "marathon",
    "मैरथन": "marathon",
    "स्ट्रीम्स": "streams",
    "स्ट्रीमर": "streamer",
    "स्ट्रीमिंग": "streaming",
    "कंटेंट": "content",
    "ऑडियंस": "audience",
    "कमेंट": "comment",
    "कमेंट्स": "comments",
    "लाइक्स": "likes",
    "व्यूज": "views",
    "व्यूज़": "views",
    "फॉलो": "follow",
    "इंस्टाग्राम": "instagram",
    "यूट्यूब": "youtube",
    "शॉर्ट्स": "shorts",
    "रील": "reel",
    "रील्स": "reels",
    "गेमप्ले": "gameplay",
    "मैच": "match",
    "राउंड": "round",
    "विन": "win",
    "फन": "fun",
    "फनी": "funny",
    "क्रेजी": "crazy",
    "क्रेज़ी": "crazy",
    "अमेजिंग": "amazing",
    "अमेज़िंग": "amazing",
    "ऑसम": "awesome",
    "नाइस": "nice",
    "कूल": "cool",
    "गॉड": "god",
    "मेबी": "maybe",
    "एनीवे": "anyway",
    "एग्जैक्टली": "exactly",
    "ऑब्वियसली": "obviously",
    "डेफिनेटली": "definitely",
    "प्रॉपर": "proper",
    "सिंपल": "simple",
    "नॉर्मल": "normal",
    "स्पेशल": "special",
    "वीक": "week",
    "मंथ": "month",
    "ईयर": "year",
    "डे": "day",
    "नाइट": "night",
    "मॉर्निंग": "morning",
    "लाइफ": "life",
    "रियल": "real",
    "रियली": "really",
    "सपोर्ट": "support",
    "शेयर": "share",
    "लिंक": "link",
    "थैंक्स": "thanks",
    "वेलकम": "welcome",
    "पीपल": "people",
    "एवरीवन": "everyone",
    "एवरीथिंग": "everything",
    "समथिंग": "something",
    "नथिंग": "nothing",
    "मैन": "man",
    "डूड": "dude",
    "गेम्स": "games",
    "प्लान": "plan",
    "आइडिया": "idea",
    "मूड": "mood",
    "सीन": "scene",
    "हैप्पी": "happy",
    "सैड": "sad",
    "लव": "love",
    "हेट": "hate",
    "वांट": "want",
    "नीड": "need",
    "नो": "no",
    "यस": "yes",
    "येस": "yes",
    "ओनली": "only",
    "जस्ट": "just",
    "स्टिल": "still",
    "अगेन": "again",
    "डन": "done",
    "रेडी": "ready",
    "हेल्प": "help",
    "फ्री": "free",
    "प्राइस": "price",
    "बाइक": "bike",
    "ट्रक": "truck",
    "हेलीकॉप्टर": "helicopter",
    "प्लेन": "plane",
    "बोट": "boat",
    "बीच": "beach",
    "होटल": "hotel",
    "हाउस": "house",
    "रूम": "room",
    "क्लॉथ्स": "clothes",
    "ड्रेस": "dress",
    "शूज": "shoes",
    "हेयर": "hair",
    "स्टाइल": "style",
}

# English "I" before a verb ("आई थिंक" = "I think"); otherwise आई is Hindi "aayi" (came)
_I_NEXT = {"थिंक", "मीन", "नो", "लव", "एम", "विल", "डोंट", "हैव", "वांट", "गेस", "होप", "नीड", "लाइक", "कैन"}  # fmt: skip

_INDEP = {"अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo", "ऋ": "ri", "ए": "e", "ऐ": "ai", "ओ": "o",
          "औ": "au", "ऑ": "o", "ऍ": "e"}  # fmt: skip
_MATRA = {"ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "ृ": "ri", "े": "e", "ै": "ai", "ो": "o", "ौ": "au",
          "ॉ": "o", "ॅ": "e"}  # fmt: skip
_CONS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh",
    "ष": "sh", "स": "s", "ह": "h", "ळ": "l",
}  # fmt: skip
_NUKTA = {"क": "q", "ख": "kh", "ग": "gh", "ज": "z", "फ": "f", "ड": "d", "ढ": "dh"}
_DEVA = re.compile(r"[ऀ-ॿ]")
_LABIAL = ("p", "b", "m")


def _aksharas(word: str) -> list[dict]:
    out: list[dict] = []
    i, n = 0, len(word)
    while i < n:
        ch = word[i]
        if ch in _CONS:
            cons: list[str] = []
            while i < n and word[i] in _CONS:
                c = word[i]
                if i + 1 < n and word[i + 1] == "़":  # nukta
                    cons.append(_NUKTA.get(c, _CONS[c]))
                    i += 2
                else:
                    cons.append(_CONS[c])
                    i += 1
                if i < n and word[i] == "्":  # virama: cluster continues
                    i += 1
                    if i < n and word[i] in _CONS:
                        continue
                    out.append({"cons": cons, "v": "", "inh": False, "nas": "", "ind": False})
                    cons = []
                    break
                break
            if not cons:
                continue
            ak = {"cons": cons, "v": "a", "inh": True, "nas": "", "ind": False}
            if i < n and word[i] in _MATRA:
                ak.update(v=_MATRA[word[i]], inh=False, m=word[i])
                i += 1
            out.append(ak)
        elif ch in _INDEP:
            out.append({"cons": [], "v": _INDEP[ch], "inh": False, "nas": "", "ind": True, "m": ch})
            i += 1
        elif ch in "ंँ":  # anusvara / chandrabindu
            if out:
                out[-1]["nas"] = "n"
            i += 1
        elif ch == "ः":  # visarga
            if out:
                out[-1]["nas"] += "h"
            i += 1
        else:
            out.append({"raw": ch})
            i += 1
    return out


def _translit(word: str) -> str:
    aks = _aksharas(word)
    sy = [a for a in aks if "raw" not in a]
    # schwa deletion, right to left (Ohala): final, and V C(a) C V in the middle
    for idx in range(len(sy) - 1, -1, -1):
        a = sy[idx]
        if not a["inh"] or a["nas"]:
            continue
        if idx == len(sy) - 1:
            if len(sy) > 1 and (len(a["cons"]) == 1 or a["cons"][-1] not in ("r", "y", "v")):
                a["v"] = ""
        elif idx > 0 and sy[idx - 1]["v"] and not sy[idx - 1]["nas"] and sy[idx + 1]["v"] and len(a["cons"]) == 1:
            # (not after a nasal: ज़िंदगी -> zindagi, बंदर -> bandar)
            a["v"] = ""
    res = []
    for a in aks:
        if "raw" in a:
            res.append("." if a["raw"] in "।॥" else a["raw"])
            continue
        si = sy.index(a)
        last = si == len(sy) - 1
        nxt = sy[si + 1] if not last else None
        v = a["v"]
        mark = a.get("m")
        if mark in ("ा", "आ") and not (a["ind"] and si == 0):
            # long aa only in a stressed first syllable ("kaam", "aap"), else "a" ("gaya", "bhai")
            v = "aa" if si == 0 and not last and not (nxt and nxt["ind"]) else "a"
        elif mark in ("ी", "ई"):
            v = "ee" if si == 0 and not last else "i"
        elif mark in ("ू", "ऊ"):
            v = "oo" if not last else "u"
        if a["ind"] and si > 0 and sy[si - 1]["v"] and mark == "ए":
            v = "ye"  # लिए -> liye, गए -> gaye
        nas = a["nas"]
        if nas.startswith("n") and nxt and nxt["cons"] and nxt["cons"][0].startswith(_LABIAL):
            nas = "m" + nas[1:]
        res.append("".join(a["cons"]) + v + nas)
    return "".join(res)


def word(w: str) -> str:
    """One caption word (may carry punctuation) -> Hinglish."""
    if not _DEVA.search(w):
        return w
    m = re.match(r"^([^ऀ-ॿ]*)(.*?)([^ऀ-ॿ]*)$", w)
    lead, core, tail = m.groups() if m else ("", w, "")
    stripped = core.rstrip("।॥")
    tail, core = core[len(stripped) :] + tail, stripped
    core_clean = unicodedata.normalize("NFC", core.replace("\u200c", "").replace("\u200d", ""))
    if core_clean in COMMON:
        return lead + COMMON[core_clean] + tail.replace("।", ".").replace("॥", ".")
    # precomposed nukta letters (ज़ U+095B ...) -> base + nukta so the transliterator sees them
    core_clean = unicodedata.normalize("NFD", core_clean)
    out = COMMON.get(core_clean) or _translit(core_clean)
    return lead + out + tail.replace("।", ".").replace("॥", ".")


def words(ws: list) -> list:
    """Transcript Words -> the same words (same timings) in Hinglish."""
    from .transcribe import Word

    out = []
    for i, w in enumerate(ws):
        nxt = re.sub(r"[^\u0900-\u097F]", "", ws[i + 1].w) if i + 1 < len(ws) else ""
        core = re.sub(r"[^\u0900-\u097F]", "", w.w)
        text = w.w.replace(core, "I") if core == "आई" and nxt in _I_NEXT else word(w.w)
        out.append(Word(text, w.s, w.e, getattr(w, "p", 0.8)))
    return out
