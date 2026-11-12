"use client";

import { useState } from "react";
import { useSession } from "@/components/AppShell";
import { CaptionSample } from "@/components/CaptionPreview";
import { useToast } from "@/components/toast";
import { Button, Card, cx, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";

export default function SettingsPage() {
  const { user, setUser, meta } = useSession();
  const toast = useToast();
  const [name, setName] = useState(user.name);
  const [preset, setPreset] = useState(user.brand_kit?.caption_preset ?? "");
  const [highlight, setHighlight] = useState(user.brand_kit?.caption_style?.highlight ?? "");
  const [watermark, setWatermark] = useState(user.brand_kit?.watermark ?? "");
  const [busy, setBusy] = useState(false);

  const save = async () => {
    setBusy(true);
    try {
      const u = await api.saveBrandKit({
        name,
        caption_preset: preset,
        watermark,
        caption_style: highlight ? { highlight, emphasis_color: highlight } : {},
      });
      setUser(u);
      toast("success", "Settings saved. New clips will use your brand kit.");
    } catch (e) {
      toast("error", (e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="max-w-3xl space-y-6">
      <h1 className="font-display text-2xl font-bold tracking-tight">Settings</h1>
      <Card className="p-6">
        <h2 className="font-semibold">Account</h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <Field label="Name">
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="Email">
            <Input value={user.email} disabled />
          </Field>
        </div>
      </Card>
      <Card className="p-6">
        <h2 className="font-semibold">Brand kit</h2>
        <p className="mt-1 text-sm text-muted">Applied automatically to every clip AI Generate creates.</p>
        <div className="mt-5 text-xs font-medium uppercase tracking-wide text-muted">Default caption style</div>
        <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3">
          {Object.entries(meta?.caption_presets ?? {}).map(([k, st]) => (
            <button
              key={k}
              onClick={() => setPreset(k)}
              className={cx("overflow-hidden rounded-xl border text-left cursor-pointer", preset === k ? "border-primary ring-2 ring-primary/30" : "border-border")}
              aria-pressed={preset === k}
            >
              <div className="grid h-16 place-items-center bg-[#1c1a26]">
                <CaptionSample style={highlight ? { ...st, highlight } : st} />
              </div>
              <div className="px-2.5 py-1.5 text-xs font-medium">{st.label}</div>
            </button>
          ))}
        </div>
        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          <Field label="Brand highlight colour" hint="Overrides the preset's highlight colour.">
            <div className="flex gap-2">
              <input type="color" value={highlight || "#ffe14d"} onChange={(e) => setHighlight(e.target.value)} className="h-10 w-12 cursor-pointer rounded-lg border border-border bg-surface" aria-label="Highlight colour" />
              <Input value={highlight} onChange={(e) => setHighlight(e.target.value)} placeholder="Preset default" />
            </div>
          </Field>
          <Field label="Watermark text" hint="Shown small in the top-right corner, e.g. @yourhandle.">
            <Input value={watermark} onChange={(e) => setWatermark(e.target.value)} maxLength={60} placeholder="@yourhandle" />
          </Field>
        </div>
        <Button className="mt-6" onClick={save} loading={busy}>
          Save settings
        </Button>
      </Card>
      {meta && (
        <Card className="p-6 text-sm">
          <h2 className="font-semibold">Processing engine</h2>
          <ul className="mt-3 space-y-1.5 text-muted">
            <li>Speech-to-text: faster-whisper “{meta.whisper_model}” (runs locally)</li>
            <li>Video encoder: {meta.encoder}</li>
            <li>AI editor: {meta.llm.available ? `${meta.llm.model} via Ollama (local, free)` : `offline — ${meta.llm.reason}`}</li>
            <li>Limits: {meta.limits.max_duration_minutes} min per video, {meta.limits.max_clips} clips per run</li>
          </ul>
        </Card>
      )}
    </div>
  );
}
