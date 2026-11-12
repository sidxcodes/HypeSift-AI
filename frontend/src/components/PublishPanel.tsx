"use client";

import { Check, Copy, RefreshCw, Save } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Clip, PublishPackage } from "@/lib/types";
import { useSession } from "./AppShell";
import { useToast } from "./toast";
import { Badge, Button, cx, Input, Segmented, Select, Textarea } from "./ui";

const LABELS: Record<string, string> = {
  youtube: "YouTube",
  instagram: "Instagram",
  tiktok: "TikTok",
  linkedin: "LinkedIn",
  facebook: "Facebook",
  x: "X",
};
const FIELD_LABELS: Record<string, string> = {
  titles: "Title options",
  description: "Description",
  search_terms: "Search terms",
  hashtags: "Hashtags",
  pinned_comment: "Pinned comment idea",
  caption: "Caption",
  cta: "Call to action",
  alt_caption: "Alternate caption",
  post: "Post",
};

function CopyBtn({ text }: { text: string }) {
  const [ok, setOk] = useState(false);
  return (
    <button
      onClick={async () => {
        await navigator.clipboard.writeText(text);
        setOk(true);
        setTimeout(() => setOk(false), 1500);
      }}
      className="inline-flex items-center gap-1 rounded-lg px-2 h-7 text-xs text-muted hover:text-text hover:bg-surface-2 cursor-pointer"
      aria-label="Copy"
    >
      {ok ? <Check className="size-3.5 text-success" /> : <Copy className="size-3.5" />} {ok ? "Copied" : "Copy"}
    </button>
  );
}

export function PublishPanel({ clip, onChange, busy }: { clip: Clip; onChange: () => void; busy?: boolean }) {
  const toast = useToast();
  const { meta } = useSession();
  const pkg = clip.publish as PublishPackage;
  const available = Object.keys(pkg?.platforms ?? {});
  const [platform, setPlatform] = useState(available[0] ?? "youtube");
  const [draft, setDraft] = useState<PublishPackage | null>(null);
  const [tone, setTone] = useState(pkg?.tone ?? "compelling");
  const [regen, setRegen] = useState(false);

  useEffect(() => {
    setDraft(pkg?.platforms ? (JSON.parse(JSON.stringify(pkg)) as PublishPackage) : null);
    if (pkg?.platforms && !pkg.platforms[platform]) setPlatform(Object.keys(pkg.platforms)[0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clip.publish]);

  const regenerate = async (platforms: string[]) => {
    setRegen(true);
    try {
      const { job } = await api.publish(clip.id, platforms, tone);
      // wait for the job (real status, no fake progress)
      for (let i = 0; i < 180; i++) {
        await new Promise((r) => setTimeout(r, 1000));
        const j = await api.job(job.id);
        if (j.status === "succeeded") break;
        if (j.status === "failed" || j.status === "cancelled") throw new Error(j.error ?? "Failed");
      }
      onChange();
      toast("success", "Publishing copy updated.");
    } catch (e) {
      toast("error", (e as Error).message);
    } finally {
      setRegen(false);
    }
  };

  const save = async () => {
    if (!draft) return;
    try {
      await api.savePublish(clip.id, draft);
      toast("success", "Saved your edits.");
      onChange();
    } catch (e) {
      toast("error", (e as Error).message);
    }
  };

  if (!draft || !available.length) {
    return (
      <div className="text-sm text-muted">
        {busy ? "Publishing copy is being written…" : "No publishing copy yet."}
        {!busy && (
          <Button size="sm" className="mt-3" onClick={() => regenerate(["youtube", "instagram", "tiktok"])} loading={regen}>
            Generate copy
          </Button>
        )}
      </div>
    );
  }

  const block = draft.platforms[platform] ?? {};
  const setField = (k: string, v: string | string[]) =>
    setDraft((d) => (d ? { ...d, platforms: { ...d.platforms, [platform]: { ...d.platforms[platform], [k]: v } } } : d));
  const missing = (meta?.platforms ?? []).filter((p) => !available.includes(p));
  const allText = Object.entries(block)
    .map(([k, v]) => `${FIELD_LABELS[k] ?? k}:\n${Array.isArray(v) ? (k === "hashtags" ? v.join(" ") : v.join("\n")) : v}`)
    .join("\n\n");

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        <Segmented
          value={platform}
          onChange={setPlatform}
          options={available.map((p) => ({ value: p, label: LABELS[p] ?? p }))}
          className="flex-wrap"
        />
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted">
        <Badge tone={draft.engine.startsWith("local LLM") ? "primary" : "neutral"}>{draft.engine}</Badge>
        {draft.edited && <Badge>edited by you</Badge>}
        {draft.note && <span>{draft.note}</span>}
      </div>
      <div className="mt-4 space-y-4">
        {Object.entries(block).map(([k, v]) => (
          <div key={k}>
            <div className="mb-1 flex items-center justify-between">
              <span className="text-xs font-medium uppercase tracking-wide text-muted">{FIELD_LABELS[k] ?? k}</span>
              <CopyBtn text={Array.isArray(v) ? (k === "hashtags" ? v.join(" ") : v.join("\n")) : String(v)} />
            </div>
            {Array.isArray(v) && k === "titles" ? (
              <div className="space-y-1.5">
                {v.map((t, i) => (
                  <div key={i} className="flex items-center gap-1">
                    <Input
                      value={t}
                      onChange={(e) => setField(k, v.map((x, j) => (j === i ? e.target.value : x)))}
                      aria-label={`Title option ${i + 1}`}
                    />
                    <CopyBtn text={t} />
                  </div>
                ))}
              </div>
            ) : Array.isArray(v) ? (
              <Input
                value={v.join(k === "hashtags" ? " " : ", ")}
                onChange={(e) => setField(k, e.target.value.split(k === "hashtags" ? /\s+/ : /\s*,\s*/).filter(Boolean))}
              />
            ) : (
              <Textarea rows={String(v).length > 120 ? 4 : 2} value={String(v)} onChange={(e) => setField(k, e.target.value)} />
            )}
          </div>
        ))}
      </div>
      <div className={cx("mt-5 flex flex-wrap items-center gap-2")}>
        <Button size="sm" onClick={save}>
          <Save className="size-4" /> Save edits
        </Button>
        <CopyBtn text={allText} />
        <div className="ml-auto flex items-center gap-2">
          <Select
            value={tone}
            onChange={setTone}
            options={(meta?.tones ?? []).map((t) => ({ value: t, label: t[0].toUpperCase() + t.slice(1) }))}
            className="h-8 w-36 text-xs"
            aria-label="Tone"
          />
          <Button variant="secondary" size="sm" onClick={() => regenerate([platform])} loading={regen}>
            <RefreshCw className="size-3.5" /> Rewrite
          </Button>
        </div>
      </div>
      {missing.length > 0 && (
        <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-muted">
          Add:
          {missing.map((p) => (
            <button key={p} onClick={() => regenerate([p])} className="rounded-full border border-border px-2.5 h-7 hover:text-text cursor-pointer" disabled={regen}>
              + {LABELS[p]}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
