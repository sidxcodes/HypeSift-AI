from app.pipeline import highlights, llm
from app.pipeline.highlights import Prefs

from .conftest import fake_words
from .test_highlights import _signals


def test_ai_editor_tightens_cuts_and_ranks(monkeypatch):
    words = fake_words()
    cands, ctx = highlights.discover(words, _signals(), Prefs(count=3, min_dur=6, max_dur=20))
    assert cands
    calls = []

    def fake_chat(system, user, temperature=0.4, max_tokens=1200):
        calls.append(user)
        if '"order"' in user:
            return {"order": [2, 0, 1]}
        # editor: drop the first context line; keep the clip's last sentence
        return {
            "items": [
                {"id": n, "start": 1, "end": 1, "hook": 8, "payoff": 7, "standalone": 9, "title": f"Clip {n}"}
                for n in range(4)
            ]
        }

    monkeypatch.setattr(llm, "status", lambda force=False: {"available": True, "model": "x", "reason": ""})
    monkeypatch.setattr(llm, "chat_json", fake_chat)
    monkeypatch.setattr(llm, "vision_rank", lambda c, x: None)
    pool = list(ctx.__dict__.get("pool", [])) or cands
    llm.semantic_rank(pool, ctx)
    assert calls, "editor was called"
    for c in pool:
        assert c.semantic is not None
        assert c.title.startswith("Clip")
        assert c.start < c.end
        assert c.s0 <= c.s1
    assert any(any("tightened" in e for e in c.evidence.get("hook", [])) for c in pool)
    # bounded: a sentence-level re-cut only applies when the length still fits
    assert all(c.duration <= ctx.prefs.max_dur + 4 for c in pool)


def test_ai_editor_ignores_out_of_range_cuts(monkeypatch):
    words = fake_words()
    cands, ctx = highlights.discover(words, _signals(), Prefs(count=2, min_dur=6, max_dur=20))
    before = [(c.start, c.end) for c in cands]
    monkeypatch.setattr(llm, "status", lambda force=False: {"available": True, "model": "x", "reason": ""})
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: {"items": [{"id": 0, "start": 50, "end": 99}]})
    monkeypatch.setattr(llm, "vision_rank", lambda c, x: None)
    llm.semantic_rank(cands, ctx)
    assert (cands[0].start, cands[0].end) == before[0]
