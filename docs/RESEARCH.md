# Research notes, differentiation and roadmap

## References

The three `share.google` links in the brief redirect to a Google page that needs JavaScript and a
signed-in browser, so they **could not be read**. Nothing below is claimed to come from them.

The comparison below is based on the publicly documented feature sets of these tools (product pages and
docs as generally known). It records observed categories of features, not internal details, and no code,
branding or visual design was copied.

| Tool | Input | Highlight detection | Score | Captions | Reframe | Editing |
|---|---|---|---|---|---|---|
| OpusClip | links + upload | AI clip finder | single "virality" number | animated templates | AI reframe | timeline editor |
| Vizard | links + upload | AI clipping | score | templates | auto-reframe | text-based editing |
| Klap | links + upload | AI shorts | — | styled captions | auto-reframe | light editing |
| VEED | upload | — (editor-first) | — | auto subtitles | resize presets | full editor |
| Submagic | upload | short-form focus | — | strong caption styles, emoji, B-roll | — | caption-centric |
| CapCut | upload | auto-cut features | — | auto captions | resize | full NLE |
| Descript | upload | transcript-based | — | captions | layouts | edit-by-transcript |

## Gaps HypeSift targets

1. **Explainable scoring.** Competitors tend to show one opaque number. HypeSift shows seven dimensions,
   the weight of each for your genre, and the evidence behind it ("opens with a question", "+1.4σ
   louder than average").
2. **Genre- and mood-aware ranking.** Weight profiles per content type; moods shift them.
3. **An assistant that does real work.** Commands become validated jobs, and unsupported requests are
   reported plainly instead of faked.
4. **Publishing packages alongside the export,** for six platforms, with the engine labelled.
5. **Runs free and private.** Local Whisper, local LLM, self-hosted, no per-minute fees.
6. **Human in the loop.** Every AI decision (range, title, crop, captions, copy) is editable, and feedback
   tunes future rankings.

## Roadmap (ordered by user impact ÷ (complexity × running cost))

| # | Item | Impact | Complexity | Cost | Status |
|---|---|---|---|---|---|
| 1 | Transcript search with jump-to-time | high | low | none | partly (clip search) |
| 2 | Duplicate / overlap detection | high | low | none | done |
| 3 | Brand kits | high | low | none | done (preset, colour, watermark) |
| 4 | AI cover frame | medium | low | none | done (sharpness + faces) |
| 5 | Real processing notifications | medium | low | none | in-app progress; browser notifications next |
| 6 | Creator feedback → ranking | high | medium | none | done (weight nudges) |
| 7 | Hook improvement suggestions | high | medium | LLM | next |
| 8 | Chapter detection | medium | medium | none | next |
| 9 | Side-by-side variant comparison | medium | medium | renders | planned |
| 10 | Batch processing | medium | medium | compute | planned (queue already supports it) |
| 11 | Subtitle translation | medium | medium | LLM | planned |
| 12 | Learned laughter/applause classifier | medium | high | none | planned |
| 13 | Opt-in performance analytics | high | high | API work | planned (authorized APIs only) |
| 14 | Licensed music / SFX | low | high | licensing | later |
| 15 | Authorized social publishing | high | high | API review | later |
