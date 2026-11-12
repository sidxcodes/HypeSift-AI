"""Genre-aware scoring profiles and small curated lexicons.

Weights say how much each explainable dimension matters for a content type. They
are hand-tuned starting points (documented, not learned) and are adjusted by
creator feedback in ``feedback.py``.
"""

from __future__ import annotations

DIMENSIONS = {
    "hook": "Hook strength",
    "context": "Context clarity",
    "pacing": "Pacing",
    "novelty": "Novelty",
    "emotion": "Emotional intensity",
    "visual": "Visual interest",
    "relevance": "Audience relevance",
}

PROFILES: dict[str, dict[str, float]] = {
    "podcast": {"hook": .20, "context": .18, "pacing": .12, "novelty": .17, "emotion": .15, "visual": .03, "relevance": .15},
    "gaming": {"hook": .15, "context": .07, "pacing": .10, "novelty": .08, "emotion": .27, "visual": .22, "relevance": .11},
    "education": {"hook": .15, "context": .22, "pacing": .13, "novelty": .22, "emotion": .05, "visual": .05, "relevance": .18},
    "tutorial": {"hook": .14, "context": .24, "pacing": .14, "novelty": .18, "emotion": .03, "visual": .09, "relevance": .18},
    "entertainment": {"hook": .20, "context": .12, "pacing": .14, "novelty": .12, "emotion": .22, "visual": .10, "relevance": .10},
    "vlog": {"hook": .18, "context": .14, "pacing": .14, "novelty": .12, "emotion": .18, "visual": .14, "relevance": .10},
    "review": {"hook": .17, "context": .18, "pacing": .13, "novelty": .18, "emotion": .10, "visual": .08, "relevance": .16},
}

GENRE_LABELS = {
    "auto": "Auto-detect",
    "podcast": "Podcast / interview",
    "gaming": "Gaming",
    "education": "Education",
    "tutorial": "Tutorial",
    "entertainment": "Entertainment",
    "vlog": "Vlog",
    "review": "Product review",
}

MOODS: dict[str, set[str]] = {
    "funny": {"haha", "hahaha", "lol", "funny", "laugh", "laughing", "joke", "joking", "hilarious", "ridiculous",
              "weird", "stupid", "dumb", "silly", "embarrassing", "awkward", "kidding", "(laughs)", "[laughter]"},
    "emotional": {"love", "cry", "cried", "crying", "tears", "heart", "miss", "sorry", "proud", "grateful", "family",
                  "lost", "died", "death", "hard", "struggle", "struggled", "alone", "afraid", "scared", "hope",
                  "dream", "mom", "dad", "mother", "father", "thank", "beautiful", "pain", "hurt"},
    "intense": {"insane", "crazy", "unbelievable", "wow", "whoa", "clutch", "kill", "killed", "win", "won", "lose",
                "lost", "fight", "go", "run", "dead", "help", "watch", "look", "omg", "huge", "massive", "epic",
                "destroyed", "never", "biggest", "worst", "best"},
    "informative": {"because", "means", "how", "why", "step", "tip", "tips", "learn", "important", "key", "reason",
                    "actually", "data", "percent", "research", "study", "example", "strategy", "framework",
                    "mistake", "secret", "lesson", "rule", "works", "result", "results"},
    "inspiring": {"believe", "dream", "goal", "goals", "never", "give", "up", "success", "failure", "failed",
                  "start", "started", "journey", "possible", "change", "future", "growth", "discipline"},
}

GENRE_HINTS: dict[str, set[str]] = {
    "gaming": {"game", "level", "boss", "kill", "spawn", "loot", "ranked", "match", "team", "enemy", "gg", "clutch",
               "stream", "chat", "headshot", "map", "squad", "lobby", "respawn", "build"},
    "education": {"learn", "concept", "example", "lesson", "theory", "means", "definition", "equation", "history",
                  "science", "students", "understand", "explain", "chapter"},
    "tutorial": {"click", "step", "install", "open", "select", "settings", "menu", "button", "first", "next",
                 "then", "tool", "code", "file", "create"},
    "podcast": {"guest", "episode", "podcast", "interview", "story", "think", "believe", "honestly", "conversation",
                "listen", "question", "experience"},
    "review": {"review", "price", "battery", "camera", "quality", "worth", "buy", "unboxing", "features", "compared",
               "specs", "performance", "design", "verdict"},
    "vlog": {"today", "went", "trip", "morning", "day", "city", "hotel", "food", "guys", "vlog", "friends", "travel"},
    "entertainment": {"crazy", "funny", "challenge", "prank", "show", "reaction", "laugh", "insane", "story"},
}

HOOK_OPENERS = (
    "here's", "here is", "the secret", "the truth", "nobody", "no one", "never", "stop", "why", "how", "what if",
    "the biggest", "the worst", "the best", "the reason", "the problem", "the mistake", "i was", "i never",
    "you won't", "you need", "you have to", "did you know", "imagine", "listen", "watch this", "look at",
    "this is", "the one thing", "most people", "everyone", "if you", "what happens", "let me tell you",
)

FILLERS = {"um", "uh", "uhm", "erm", "hmm", "like", "so", "and", "but", "okay", "ok", "yeah", "right", "well",
           "anyway", "mm", "mhm"}
DANGLING = {"that", "it", "this", "he", "she", "they", "them", "which", "those", "these", "there", "also"}

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "so", "to", "of", "in", "on", "at", "for", "with", "is",
    "are", "was", "were", "be", "been", "being", "it", "its", "this", "that", "these", "those", "i", "you", "he",
    "she", "we", "they", "me", "him", "her", "us", "them", "my", "your", "his", "our", "their", "do", "does",
    "did", "have", "has", "had", "not", "no", "yes", "just", "like", "um", "uh", "yeah", "okay", "ok", "what",
    "when", "where", "who", "how", "why", "there", "here", "all", "can", "will", "would", "could", "should",
    "about", "from", "up", "out", "as", "by", "really", "very", "get", "got", "go", "going", "know", "think",
    "mean", "kind", "sort", "thing", "things", "gonna", "wanna", "one", "some", "more", "also", "than", "too",
    "right", "well", "oh", "into", "over", "because", "actually", "now", "even", "much", "lot", "say", "said",
    "im", "dont", "its", "thats", "youre", "were", "theyre", "ive", "id", "ill", "cant", "didnt", "doesnt",
}

INTENSIFIERS = {"so", "really", "super", "extremely", "absolutely", "totally", "literally", "completely",
                "incredibly", "insanely", "honestly", "seriously", "definitely"}
