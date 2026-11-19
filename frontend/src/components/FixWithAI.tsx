"use client";

import { CheckCircle2, Loader2, Send, Sparkles } from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import type { Clip } from "@/lib/types";
import { Button, cx, Textarea } from "./ui";

const SUGGESTIONS = [
  "Start 2 seconds earlier",
  "It ends mid-sentence",
  "Remove the first sentence",
  "Make it 30 seconds",
  "Make the title funnier",
  "Bigger captions",
  "Use the Heat caption style",
  "Show the whole frame, don't crop",
  "Zoom in on key moments",
];

type Turn = { you: string; reply: string; changes: string[]; applied: boolean; engine: string };

export function FixWithAI({ clip, onChange }: { clip: Clip; onChange: () => void }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);

  const send = async (t: string) => {
    const req = t.trim();
    if (!req || busy) return;
    setBusy(true);
    try {
      const r = await api.fixClip(clip.id, req);
      setTurns((x) => [{ you: req, reply: r.reply, changes: r.changes, applied: r.applied, engine: r.engine }, ...x].slice(0, 6));
      setText("");
      if (r.applied) onChange();
    } catch (e) {
      setTurns((x) => [{ you: req, reply: (e as Error).message, changes: [], applied: false, engine: "" }, ...x]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <div className="flex items-center gap-2 text-sm font-medium">
          <Sparkles className="size-4 text-primary" /> Tell the AI what to fix
        </div>
        <p className="mt-0.5 text-xs text-muted">
          Like you would tell a human editor: timing, the title, captions, framing, a misheard word… The clip is
          changed and re-rendered.
        </p>
      </div>
      <div className="relative">
        <Textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(text);
            }
          }}
          rows={3}
          placeholder="e.g. The start is boring, begin where he talks about the price — and the captions say “gonna” but he said “Goa”"
          className="pr-12"
          aria-label="What should change"
        />
        <Button size="sm" className="absolute bottom-2 right-2 h-8 w-8 px-0" onClick={() => send(text)} disabled={!text.trim() || busy} aria-label="Fix">
          {busy ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
        </Button>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => send(s)}
            disabled={busy}
            className="h-7 rounded-full border border-border px-2.5 text-xs text-muted hover:border-primary hover:text-primary cursor-pointer disabled:opacity-50"
          >
            {s}
          </button>
        ))}
      </div>
      {turns.length > 0 && (
        <div className="space-y-3">
          {turns.map((t, i) => (
            <div key={i} className="rounded-xl border border-border p-3 text-sm">
              <div className="text-xs text-muted">You: {t.you}</div>
              <div className={cx("mt-1.5", t.applied ? "text-text" : "text-warning")}>{t.reply}</div>
              {t.changes.length > 0 && (
                <ul className="mt-2 space-y-1">
                  {t.changes.map((c) => (
                    <li key={c} className="flex gap-1.5 text-xs">
                      <CheckCircle2 className="mt-px size-3.5 shrink-0 text-success" /> {c}
                    </li>
                  ))}
                </ul>
              )}
              {t.engine && t.applied && <div className="mt-2 text-[11px] text-muted">Understood by: {t.engine}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
