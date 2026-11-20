"use client";

import { Check, Cpu, Eye, ExternalLink, KeyRound, ShieldCheck, Sparkles, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { AiSettings } from "@/lib/types";
import { useSession } from "./AppShell";
import { useToast } from "./toast";
import { Badge, Button, Card, cx, Input, Select } from "./ui";

const MODEL_LABELS: Record<string, string> = {
  auto: "Best available (recommended)",
  "gemini-4-hydrogen": "Gemini 4 Hydrogen (smartest free model)",
  "gemini-3.8-flash": "Gemini 3.8 Flash (fast)",
  "gemini-2.5-pro": "Gemini 2.5 Pro (deep reasoning)",
  "gemini-3.6-flash": "Gemini 3.6 Flash",
  "gemini-2.5-flash": "Gemini 2.5 Flash (highest free limits)",
};

export function AiModelCard() {
  const toast = useToast();
  const { refreshMeta } = useSession();
  const [ai, setAi] = useState<AiSettings | null>(null);
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.ai().then(setAi).catch(() => {});
  }, []);

  const save = async (body: Parameters<typeof api.saveAi>[0], ok: string) => {
    setBusy(true);
    try {
      const r = await api.saveAi(body);
      setAi(r);
      setKey("");
      refreshMeta();
      toast("success", ok);
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Couldn't save.");
    } finally {
      setBusy(false);
    }
  };

  if (!ai) return <Card className="h-64 p-6" />;
  const choice = ai.provider;

  return (
    <Card className="p-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">AI model: who picks your best moments</h2>
          <p className="mt-1 text-sm text-muted">Pick the brain behind clip selection. You can switch any time.</p>
        </div>
        <Badge tone={ai.active === "gemini" ? "success" : "primary"}>
          {ai.active === "gemini" ? "Gemini active" : "Local active"}
        </Badge>
      </div>

      <div className="mt-5 grid gap-3 md:grid-cols-2">
        {[
          {
            id: "gemini" as const,
            icon: <Eye className="size-5" />,
            title: "Google Gemini (free)",
            tag: "Recommended",
            points: [
              "Watches the video: faces, action, reactions, not just the words",
              "Picks moments that match your clip length and request",
              "Detects comparison videos (A vs B vs C) by itself",
              "Free tier, no card. Needs a free key and internet",
            ],
          },
          {
            id: "local" as const,
            icon: <Cpu className="size-5" />,
            title: `On this PC (${ai.local.model})`,
            tag: "Private",
            points: [
              "Nothing leaves your computer, works offline",
              "Reads the transcript only (can't see the video)",
              "Limited by your 6 GB graphics card",
              "Always the automatic backup when Gemini is unavailable",
            ],
          },
        ].map((o) => (
          <button
            key={o.id}
            type="button"
            onClick={() => save({ provider: o.id }, o.id === "gemini" ? "Gemini selected." : "Local model selected.")}
            className={cx(
              "rounded-2xl border-2 p-4 text-left transition cursor-pointer",
              choice === o.id ? "border-primary bg-primary-soft" : "border-border hover:border-primary/40",
            )}
            aria-pressed={choice === o.id}
          >
            <div className="flex items-center gap-2">
              <span className={cx("grid size-9 place-items-center rounded-xl", choice === o.id ? "bg-primary text-on-primary" : "bg-surface-2 text-primary")}>
                {o.icon}
              </span>
              <span className="font-semibold">{o.title}</span>
              <Badge tone={o.id === "gemini" ? "accent" : "neutral"} className="ml-auto">
                {o.tag}
              </Badge>
            </div>
            <ul className="mt-3 space-y-1.5 text-[13px]">
              {o.points.map((p) => (
                <li key={p} className="flex gap-2">
                  <Check className="mt-0.5 size-3.5 shrink-0 text-success" /> {p}
                </li>
              ))}
            </ul>
          </button>
        ))}
      </div>

      {choice === "gemini" && (
        <div className="mt-5 rounded-2xl bg-surface-2 p-4">
          {ai.has_key ? (
            <div className="flex flex-wrap items-center gap-3">
              <KeyRound className="size-4 text-primary" />
              <span className="text-sm">
                Key saved <span className="font-mono text-muted">{ai.key_hint}</span>
              </span>
              <Button
                variant="ghost"
                size="sm"
                className="ml-auto"
                onClick={async () => {
                  setAi(await api.removeAiKey());
                  refreshMeta();
                }}
              >
                <Trash2 className="size-4" /> Remove key
              </Button>
            </div>
          ) : (
            <>
              <div className="text-sm font-medium">Add your free Gemini API key</div>
              <ol className="mt-2 list-decimal space-y-1 pl-5 text-[13px] text-muted">
                <li>
                  Open{" "}
                  <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener" className="inline-flex items-center gap-1 font-medium text-primary hover:underline">
                    Google AI Studio → API keys <ExternalLink className="size-3" />
                  </a>{" "}
                  and sign in with your Google account.
                </li>
                <li>Click “Create API key” (free, no card), copy it, paste it here.</li>
              </ol>
              <div className="mt-3 flex gap-2">
                <Input
                  type="password"
                  autoComplete="off"
                  value={key}
                  onChange={(e) => setKey(e.target.value)}
                  placeholder="Paste your Gemini API key"
                  aria-label="Gemini API key"
                />
                <Button onClick={() => save({ provider: "gemini", gemini_api_key: key }, "Key works. Gemini will pick your moments.")} loading={busy} disabled={key.trim().length < 20}>
                  Test &amp; save
                </Button>
              </div>
            </>
          )}
          <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
            <label className="block">
              <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-muted">Gemini model</span>
              <Select
                value={ai.model}
                onChange={(v) => save({ gemini_model: v }, "Model saved.")}
                options={["auto", ...ai.models].map((m) => ({ value: m, label: MODEL_LABELS[m] ?? m }))}
              />
            </label>
            {ai.last_model && (
              <span className="inline-flex items-center gap-1.5 text-xs text-muted">
                <Sparkles className="size-3.5 text-accent" /> Last used: {ai.last_model}
              </span>
            )}
          </div>
          {ai.last_error && <p className="mt-3 text-xs text-warning">Last problem: {ai.last_error} (the local model was used instead).</p>}
          <p className="mt-3 flex gap-2 text-xs text-muted">
            <ShieldCheck className="mt-0.5 size-3.5 shrink-0" />
            The key stays on this PC. To pick moments, a small low-resolution copy of your video (or the YouTube link) and its
            transcript are sent to Google, then the copy is deleted. On the free tier Google may use this data to improve its
            products. Free limits reset daily; when they run out, the local model takes over automatically.
          </p>
        </div>
      )}
    </Card>
  );
}
