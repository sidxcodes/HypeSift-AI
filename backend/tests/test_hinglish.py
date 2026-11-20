from app.pipeline import hinglish


def h(text: str) -> str:
    return " ".join(hinglish.word(w) for w in text.split())


def test_common_speech_reads_naturally():
    assert h("कपड़े तो मैंने पहन लिए बट एक सेकंड।") == "kapde to maine pahan liye but ek second."
    assert h("यार नहाएगा कौन?") == "yaar nahayega kaun?"
    assert h("मैंने अभी तक चेक नहीं करा") == "maine abhi tak check nahi kara"
    assert h("और यह है भाई अपना वाशरूम") == "aur yeh hai bhai apna washroom"


def test_schwa_deletion_and_rules():
    assert hinglish.word("समझना") == "samajhna"
    assert hinglish.word("करना") == "karna"
    assert hinglish.word("लड़का") == "ladka"
    assert hinglish.word("समय") == "samay"
    assert hinglish.word("काम") == "kaam"
    assert hinglish.word("बताया") == "bataya"
    assert hinglish.word("ज़िंदगी") == "zindagi"


def test_latin_and_numbers_pass_through():
    assert hinglish.word("GTA") == "GTA"
    assert hinglish.word("2026,") == "2026,"


def test_english_inside_hindi_speech():
    from app.pipeline.transcribe import Word

    ws = [
        Word(w, i, i + 0.4, 0.9)
        for i, w in enumerate(["आई", "थिंक", "इट्स", "पॉसिबल", "बिकॉज़", "मैंने", "मैराथन", "स्ट्रीम्स", "देखे"])
    ]
    assert " ".join(w.w for w in hinglish.words(ws)) == "I think it's possible because maine marathon streams dekhe"
    assert hinglish.word("ज़ाम") == hinglish.word("ज़ाम")  # decomposed and precomposed nukta agree
    assert hinglish.word("मित्र") == "mitra" and hinglish.word("दोस्त") == "dost"
