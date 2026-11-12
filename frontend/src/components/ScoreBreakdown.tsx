"use client";

import type { Clip } from "@/lib/types";
import { useSession } from "./AppShell";
import { Badge, scoreTone } from "./ui";

export function ScoreBreakdown({ clip }: { clip: Clip }) {
  const { meta } = useSession();
  const dims = clip.score_breakdown?.dims ?? {};
  const weights = clip.score_breakdown?.weights ?? {};
  const evidence = clip.score_breakdown?.evidence ?? {};
  const labels = meta?.dimensions ?? {};
  const order = Object.keys(labels).sort((a, b) => (weights[b] ?? 0) - (weights[a] ?? 0));
  return (
    <div>
      <div className="flex items-end gap-3">
        <div className="font-display text-4xl font-bold tabular-nums">{clip.score}</div>
        <div className="pb-1.5 text-sm text-muted">/ 100 estimated potential</div>
        <Badge tone={scoreTone(clip.score)} className="mb-2 ml-auto">
          {clip.content_type || "auto"}
        </Badge>
      </div>
      <ul className="mt-3 space-y-1.5 text-sm">
        {clip.reasons.map((r) => (
          <li key={r} className="flex gap-2">
            <span className="text-primary">•</span>
            <span>{r}</span>
          </li>
        ))}
      </ul>
      <div className="mt-5 space-y-3">
        {order.map((k) => (
          <div key={k}>
            <div className="flex justify-between text-xs">
              <span className="font-medium">{labels[k]}</span>
              <span className="tabular-nums text-muted">
                {Math.round(dims[k] ?? 0)} · weight {Math.round((weights[k] ?? 0) * 100)}%
              </span>
            </div>
            <div className="mt-1 h-1.5 rounded-full bg-surface-2">
              <div className="h-full rounded-full bg-primary" style={{ width: `${dims[k] ?? 0}%`, opacity: 0.45 + (weights[k] ?? 0) * 2.5 }} />
            </div>
            {evidence[k]?.length > 0 && <div className="mt-1 text-xs text-muted">{evidence[k].join(" · ")}</div>}
          </div>
        ))}
        {dims.semantic != null && (
          <div>
            <div className="flex justify-between text-xs">
              <span className="font-medium">AI editor (semantic read)</span>
              <span className="tabular-nums text-muted">{Math.round(dims.semantic)} · 30% of final</span>
            </div>
            <div className="mt-1 h-1.5 rounded-full bg-surface-2">
              <div className="h-full rounded-full bg-accent" style={{ width: `${dims.semantic}%` }} />
            </div>
          </div>
        )}
      </div>
      <p className="mt-4 text-xs text-muted">
        Engine: {clip.score_breakdown?.engine ?? "signals"}. This is a heuristic estimate of how well the moment works as a
        standalone short — not a prediction of views, virality or revenue.
      </p>
    </div>
  );
}
