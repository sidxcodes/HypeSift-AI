"use client";

import { Check, Loader2, X } from "lucide-react";
import { useEffect, useState } from "react";
import type { Job } from "@/lib/types";
import { Button, Card, cx, Progress } from "./ui";

export const STAGE_LABELS: Record<string, string> = {
  ingest: "Import video",
  prepare: "Read video details",
  transcribe: "Transcribe speech",
  analyze: "Analyze audio & visuals",
  rank: "Find & rank highlights",
  render: "Render clips",
  publish: "Write titles & hashtags",
};

function elapsed(from: string | null) {
  if (!from) return "";
  const s = Math.max(0, Math.round((Date.now() - new Date(from).getTime()) / 1000));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
}

export function JobProgress({ job, onCancel }: { job: Job; onCancel?: () => void }) {
  const [, tick] = useState(0);
  useEffect(() => {
    const i = setInterval(() => tick((x) => x + 1), 1000);
    return () => clearInterval(i);
  }, []);
  const active = job.status === "running" || job.status === "queued";
  return (
    <Card className="p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-lg font-semibold">
            {job.status === "queued"
              ? "Waiting in queue…"
              : job.status === "running"
                ? job.kind === "discover"
                  ? `Assistant: ${job.payload?.summary ?? "finding clips"}`
                  : "AI is generating your clips"
                : job.status === "failed"
                  ? "Generation failed"
                  : job.status === "cancelled"
                    ? "Cancelled"
                    : "Done"}
          </h2>
          <p className="mt-0.5 text-sm text-muted" aria-live="polite">
            {job.status === "failed" ? job.error : job.message || "Starting…"}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {job.started_at && active && <span className="text-sm tabular-nums text-muted">{elapsed(job.started_at)}</span>}
          {active && onCancel && (
            <Button variant="secondary" size="sm" onClick={onCancel}>
              Cancel
            </Button>
          )}
        </div>
      </div>
      <div className="mt-4 flex items-center gap-3">
        <Progress value={job.progress} className="flex-1" />
        <span className="w-10 text-right text-sm tabular-nums text-muted">{Math.round(job.progress * 100)}%</span>
      </div>
      {job.stages.length > 0 && (
        <ol className="mt-5 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {job.stages.map((s) => (
            <li
              key={s.key}
              className={cx(
                "flex items-center gap-2 rounded-xl px-3 py-2 text-sm",
                s.status === "running" ? "bg-primary-soft text-primary" : "bg-surface-2",
                s.status === "pending" && "text-muted",
              )}
            >
              {s.status === "done" && <Check className="size-4 text-success" />}
              {s.status === "running" && <Loader2 className="size-4 animate-spin" />}
              {s.status === "failed" && <X className="size-4 text-danger" />}
              {s.status === "pending" && <span className="size-4 rounded-full border-2 border-border" />}
              {STAGE_LABELS[s.key] ?? s.key}
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}
