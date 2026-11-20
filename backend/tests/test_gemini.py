from app.pipeline import gemini, highlights
from app.pipeline.highlights import Prefs

from .conftest import fake_words
from .test_highlights import _signals


def test_no_key_means_local(tmp_path, monkeypatch):
    monkeypatch.setattr(gemini, "SETTINGS_FILE", tmp_path / "ai.json")
    assert gemini.provider() == "local"
    assert gemini.find_moments(sentences=[], duration=10, prefs=Prefs(), count=3) is None
    gemini.save_settings(provider="gemini", gemini_api_key="AIzaFAKEKEY123")
    assert gemini.provider() == "gemini"
    pub = gemini.public_settings()
    assert pub["has_key"] and pub["key_hint"] == "…Y123" and "AIza" not in str(pub)
    gemini.save_settings(provider="local")
    assert gemini.provider() == "local"


def test_parse_lines_and_times():
    out = gemini._parse(
        '```json\n{"moments": [{"start_line": 2, "end_line": 5, "virality": "88", "title": "T", "why": "w"},'
        '{"start_line": 9, "end_line": 3}, {"start": 4.5, "end": 30, "virality": 70}]}\n```',
        n_lines=8,
        duration=40,
    )
    assert out[0] == {"score": 88.0, "title": "T", "hook": "", "why": "w", "s0": 2, "s1": 5}
    assert out[1]["start"] == 4.5 and out[1]["score"] == 70
    assert len(out) == 2  # the reversed line range is dropped
    assert gemini._youtube_id("https://youtube.com/shorts/sGRJKDANzIE?si=x") == "sGRJKDANzIE"


def test_proposals_lead_and_respect_length():
    words = fake_words()
    prefs = Prefs(count=2, min_dur=12, max_dur=20)
    calls = []

    def proposer(ctx):
        calls.append(len(ctx.sentences))
        # one single-sentence pick (too short: must be grown) and one huge one (must be trimmed)
        return [
            {"s0": 1, "s1": 1, "score": 92, "title": "Best one", "why": "great hook"},
            {"s0": 0, "s1": len(ctx.sentences) - 1, "score": 70, "title": "Second"},
        ]

    cands, ctx = highlights.discover(words, _signals(), prefs, proposer=proposer)
    assert calls
    assert cands and cands[0].title == "Best one"
    assert cands[0].llm_note.startswith("Gemini")
    for c in cands:
        assert 12 - 1 <= c.duration <= 20 + 1.6, c.duration


def test_proposer_failure_falls_back():
    words = fake_words()

    def boom(ctx):
        raise RuntimeError("quota")

    cands, _ = highlights.discover(words, _signals(), Prefs(count=2, min_dur=8, max_dur=20), proposer=boom)
    assert cands and not any(c.llm_note.startswith("Gemini") for c in cands)
