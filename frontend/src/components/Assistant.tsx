"use client";

import { Send, Sparkles } from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import { useToast } from "./toast";
import { Button, cx } from "./ui";

const EXAMPLES = [
  "Find the funniest 30-second moment",
  "Make three emotional clips near the end",
  "Use bold yellow captions",
  "Write an Instagram caption",
  "Remove silences",
];

type Entry = { q: string; a: string; ok: boolean };

export function Assistant({ projectId, clipId, onAction, disabled }: { projectId: string; clipId?: string; onAction: () => void; disabled?: boolean }) {
  const toast = useToast();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [log, setLog] = useState<Entry[]>([]);

  const send = async (q: string) => {
    if (!q.trim() || busy) return;
    setBusy(true);
    try {
      const r = await api.assistant(projectId, q, clipId);
      setLog((l) => [{ q, a: r.message, ok: r.executed }, ...l].slice(0, 5));
      if (r.executed) onAction();
      setText("");
      // Follow search / copy jobs to completion and report their real outcome.
      for (const job of r.jobs.filter((j) => j.kind === "discover" || j.kind === "publish")) {
        void (async () => {
          for (let i = 0; i < 600; i++) {
            await new Promise((res) => setTimeout(res, 1500));
            const j = await api.job(job.id).catch(() => null);
            if (!j || j.status === "queued" || j.status === "running") continue;
            const ok = j.status === "succeeded";
            const msg = ok
              ? j.kind === "discover"
                ? "Done — new clips added below."
                : "Done — publishing copy updated."
              : (j.error ?? "That didn't work.");
            setLog((l) => l.map((e) => (e.q === q ? { ...e, a: `${e.a} → ${msg}`, ok } : e)));
            toast(ok ? "success" : "info", msg);
            onAction();
            break;
          }
        })();
      }
    } catch (e) {
      toast("error", (e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-2xl border border-border bg-surface p-4">
      <div className="flex items-center gap-2 text-sm font-medium">
        <Sparkles className="size-4 text-primary" /> Creator assistant
        <span className="text-xs font-normal text-muted">— commands run real edits{clipId ? " on this clip" : ""}</span>
      </div>
      <form
        className="mt-3 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          send(text);
        }}
      >
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={disabled || busy}
          placeholder={disabled ? "Available once the first analysis finishes" : "e.g. Find an emotional reaction near the end"}
          className="h-10 flex-1 rounded-xl border border-border bg-surface-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring/40"
          aria-label="Assistant command"
        />
        <Button type="submit" loading={busy} disabled={disabled || !text.trim()} aria-label="Send">
          {!busy && <Send className="size-4" />}
        </Button>
      </form>
      {!log.length && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {EXAMPLES.map((e) => (
            <button
              key={e}
              onClick={() => send(e)}
              disabled={disabled || busy}
              className="rounded-full border border-border px-2.5 h-7 text-xs text-muted hover:text-text hover:border-primary/50 disabled:opacity-50 cursor-pointer"
            >
              {e}
            </button>
          ))}
        </div>
      )}
      {log.length > 0 && (
        <ul className="mt-3 space-y-2 text-sm">
          {log.map((e, i) => (
            <li key={i} className="rounded-xl bg-surface-2 px-3 py-2">
              <div className="text-muted">“{e.q}”</div>
              <div className={cx("mt-0.5", !e.ok && "text-warning")}>{e.a}</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
