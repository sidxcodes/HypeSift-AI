"use client";

import { Download, ImageIcon, Loader2, RefreshCw } from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import type { Clip } from "@/lib/types";
import { useToast } from "./toast";
import { Button, cx, Input, Segmented } from "./ui";

export function ThumbnailsPanel({ clip, onChange }: { clip: Clip; onChange: () => void }) {
  const toast = useToast();
  const th = clip.thumbnails;
  const [size, setSize] = useState<"vertical" | "wide">("vertical");
  const [text, setText] = useState(th?.text ?? "");
  const [busy, setBusy] = useState(false);

  const regen = async (custom?: string) => {
    setBusy(true);
    try {
      await api.regenThumbnails(clip.id, custom);
      toast("info", "Designing new thumbnails — they appear here in a few seconds.");
      setTimeout(onChange, 6000);
      setTimeout(onChange, 15000);
      setTimeout(() => setBusy(false), 15000);
    } catch (e) {
      toast("error", (e as Error).message);
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-sm font-medium">AI thumbnails</div>
          <p className="text-xs text-muted">The AI picks the most eye-catching frame and writes the text. Vertical for Shorts / Reels, wide for YouTube.</p>
        </div>
        <Segmented
          value={size}
          onChange={setSize}
          options={[
            { value: "vertical", label: "9:16" },
            { value: "wide", label: "16:9" },
          ]}
        />
      </div>
      {!th ? (
        <div className="grid place-items-center gap-3 rounded-2xl border border-dashed border-border p-8 text-center text-sm text-muted">
          <ImageIcon className="size-6" />
          No thumbnails yet.
          <Button size="sm" onClick={() => regen()} loading={busy} disabled={clip.render_status !== "rendered"}>
            Create thumbnails
          </Button>
        </div>
      ) : (
        <div className={cx("grid gap-3", size === "vertical" ? "grid-cols-3" : "grid-cols-1 sm:grid-cols-2")}>
          {th.designs.map((d) => (
            <div key={d.design} className="overflow-hidden rounded-xl border border-border">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={d[size] ?? ""} alt={`${d.label} thumbnail`} className={cx("w-full object-cover", size === "vertical" ? "aspect-[9/16]" : "aspect-video")} />
              <div className="flex items-center justify-between px-2.5 py-2 text-xs">
                <span className="font-medium">{d.label}</span>
                {d[`${size}_download`] && (
                  <a href={d[`${size}_download`] ?? undefined} download className="inline-flex items-center gap-1 text-primary hover:underline">
                    <Download className="size-3.5" /> Download
                  </a>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
      {th && (
        <div className="flex flex-wrap gap-2">
          <Input value={text} onChange={(e) => setText(e.target.value.slice(0, 40))} placeholder="Your own thumbnail text" className="h-9 min-w-48 flex-1" aria-label="Thumbnail text" />
          <Button size="sm" variant="secondary" onClick={() => regen(text)} disabled={busy || !text.trim()}>
            {busy ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw className="size-4" />} Use my text
          </Button>
          <Button size="sm" variant="ghost" onClick={() => regen()} disabled={busy}>
            New AI ideas
          </Button>
        </div>
      )}
    </div>
  );
}
