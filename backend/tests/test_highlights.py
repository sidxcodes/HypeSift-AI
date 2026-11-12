import numpy as np

from app.pipeline import highlights
from app.pipeline.highlights import Candidate, Prefs
from app.pipeline.signals import Signals

from .conftest import fake_words


def _signals(duration=40.0, loud_peak=None):
    n = int(duration * 10)
    loud = np.full(n, -25.0, dtype=np.float32)
    if loud_peak:
        a, b = loud_peak
        loud[int(a * 10) : int(b * 10)] = -12.0
    rng = np.random.default_rng(0)
    return Signals(
        duration=duration,
        loudness=loud,
        flux=rng.random(n).astype(np.float32),
        flatness=np.full(n, 0.1, dtype=np.float32),
        motion=np.full(int(duration * 2), 3.0, dtype=np.float32),
        cuts=[20.0],
    )


def test_sentences_split_on_punctuation_and_pauses():
    words = fake_words()
    ss = highlights.build_sentences(words)
    assert ss[0].text.startswith("Welcome back")
    assert ss[0].text.endswith(".")
    assert any(s.text.endswith("?") for s in ss)
    assert all(s.w0 <= s.w1 for s in ss)


def test_candidates_start_and_end_on_sentence_boundaries():
    words = fake_words()
    cands, ctx = highlights.discover(words, _signals(), Prefs(count=3, min_dur=8, max_dur=20))
    assert cands
    starts = {round(s.start, 2) for s in ctx.sentences}
    for c in cands:
        assert 7 <= c.duration <= 22
        assert any(abs(c.start - s) < 0.5 for s in starts)
        assert 0 <= c.score <= 100
        assert c.reasons and c.title


def test_question_hook_is_explained():
    words = fake_words()
    cands, _ = highlights.discover(words, _signals(), Prefs(count=6, min_dur=6, max_dur=20))
    q = [c for c in cands if c.hook.rstrip().endswith("?")]
    assert q, "expected a candidate opening with the question"
    assert any("question" in e.lower() for e in q[0].evidence["hook"])


def test_louder_section_scores_higher_emotion():
    words = fake_words()
    win = Candidate(start=15.0, end=25.0)

    def emotion(sig):
        ctx = highlights.make_context(words, sig, Prefs(min_dur=6, max_dur=15))
        return highlights.score(Candidate(start=win.start, end=win.end), ctx).dims["emotion"]

    assert emotion(_signals(loud_peak=(14, 26))) > emotion(_signals())


def test_suppression_removes_overlaps():
    a = Candidate(start=0, end=20, text="alpha beta gamma", score=90)
    b = Candidate(start=2, end=21, text="alpha beta delta", score=80)
    c = Candidate(start=30, end=45, text="other words here", score=70)
    kept = highlights.suppress([a, b, c], 3)
    assert [k.score for k in kept] == [90, 70]


def test_position_filter_prefers_end():
    cs = [Candidate(start=0, end=10), Candidate(start=80, end=95)]
    assert highlights.position_filter(cs, "end", 100)[0].start == 80


def test_no_speech_falls_back_to_signal_windows():
    cands, ctx = highlights.discover([], _signals(), Prefs(count=2, min_dur=8, max_dur=15))
    assert not ctx.speech
    assert cands and all(8 - 2 <= c.duration <= 17 for c in cands)


def test_genre_detection_uses_speech_density_when_vocab_is_weak():
    genre, _ = highlights.detect_genre(fake_words(), _signals())
    assert genre == "podcast"


def test_feedback_bias_shifts_weights():
    ctx_plain = highlights.make_context(fake_words(), _signals(), Prefs())
    ctx_bias = highlights.make_context(fake_words(), _signals(), Prefs(), {"emotion": 0.3})
    assert ctx_bias.weights["emotion"] > ctx_plain.weights["emotion"]
    assert abs(sum(ctx_bias.weights.values()) - 1) < 1e-6
