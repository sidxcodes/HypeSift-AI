"use client";

import { useRef } from "react";
import { fmtTime } from "@/lib/api";

type Props = {
  duration: number; // source duration
  start: number;
  end: number;
  time: number;
  words: [string, number, number][];
  envelope: { start: number; hop: number; loudness: number[] } | null;
  onChange: (start: number, end: number) => void;
  onSeek: (t: number) => void;
};

/** Source-time timeline: loudness envelope, word ticks, draggable trim handles, playhead. */
export function Timeline({ duration, start, end, time, words, envelope, onChange, onSeek }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const viewStart = Math.max(0, Math.min(start - 20, envelope?.start ?? start - 20));
  const viewEnd = Math.min(duration, Math.max(end + 20, viewStart + 40));
  const span = viewEnd - viewStart || 1;
  const pct = (t: number) => ((t - viewStart) / span) * 100;
  const drag = useRef<null | "start" | "end" | "move">(null);
  const origin = useRef({ x: 0, s: 0, e: 0 });

  const toTime = (clientX: number) => {
    const r = box.current!.getBoundingClientRect();
    return viewStart + ((clientX - r.left) / r.width) * span;
  };
  const snap = (t: number, edge: "start" | "end") => {
    // snap to nearby word boundaries (0.25s) so cuts don't clip syllables
    let best = t;
    let bd = 0.25;
    for (const [, s, e] of words) {
      const c = edge === "start" ? s : e;
      if (Math.abs(c - t) < bd) {
        bd = Math.abs(c - t);
        best = edge === "start" ? c - 0.08 : c + 0.12;
      }
    }
    return Math.max(0, Math.min(duration, best));
  };

  const onDown = (kind: "start" | "end" | "move") => (e: React.PointerEvent) => {
    e.stopPropagation();
    drag.current = kind;
    origin.current = { x: e.clientX, s: start, e: end };
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  };
  const onMove = (e: React.PointerEvent) => {
    if (!drag.current) return;
    const t = toTime(e.clientX);
    if (drag.current === "start") onChange(Math.min(snap(t, "start"), end - 1), end);
    else if (drag.current === "end") onChange(start, Math.max(snap(t, "end"), start + 1));
    else {
      const r = box.current!.getBoundingClientRect();
      const d = ((e.clientX - origin.current.x) / r.width) * span;
      const len = origin.current.e - origin.current.s;
      const s = Math.max(0, Math.min(duration - len, origin.current.s + d));
      onChange(+s.toFixed(2), +(s + len).toFixed(2));
    }
  };

  const bars = envelope?.loudness ?? [];
  const ticks = [];
  const step = span > 120 ? 30 : span > 60 ? 10 : 5;
  for (let t = Math.ceil(viewStart / step) * step; t <= viewEnd; t += step) ticks.push(t);

  return (
    <div className="select-none">
      <div
        ref={box}
        className="relative h-24 cursor-pointer overflow-hidden rounded-xl border border-border bg-surface-2"
        onPointerMove={onMove}
        onPointerUp={() => (drag.current = null)}
        onClick={(e) => !drag.current && onSeek(toTime(e.clientX))}
        role="slider"
        aria-label="Clip timeline"
        aria-valuemin={0}
        aria-valuemax={duration}
        aria-valuenow={time}
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "ArrowLeft") onChange(Math.max(0, start - 0.5), end);
          if (e.key === "ArrowRight") onChange(start, Math.min(duration, end + 0.5));
        }}
      >
        {/* envelope */}
        <svg className="absolute inset-0 h-full w-full" preserveAspectRatio="none" viewBox="0 0 1000 100" aria-hidden>
          {bars.map((db, i) => {
            const t = (envelope!.start ?? 0) + i * envelope!.hop;
            if (t < viewStart || t > viewEnd) return null;
            const h = Math.max(2, Math.min(90, (db + 60) * 1.6));
            const x = ((t - viewStart) / span) * 1000;
            return <rect key={i} x={x} y={50 - h / 2} width={Math.max(1, (envelope!.hop / span) * 1000 * 0.7)} height={h} fill="var(--muted)" opacity={0.35} />;
          })}
        </svg>
        {/* words */}
        {words.map(([w, s], i) =>
          s >= viewStart && s <= viewEnd ? (
            <div key={i} className="absolute bottom-0 h-2 w-px bg-muted/40" style={{ left: `${pct(s)}%` }} title={w} />
          ) : null,
        )}
        {/* selection */}
        <div
          className="absolute inset-y-0 border-y-2 border-primary bg-primary/15"
          style={{ left: `${pct(start)}%`, width: `${pct(end) - pct(start)}%` }}
          onPointerDown={onDown("move")}
        >
          <div
            className="absolute -left-1.5 inset-y-0 w-3 cursor-ew-resize rounded-l-md bg-primary"
            onPointerDown={onDown("start")}
            role="slider"
            aria-label="Clip start"
            aria-valuenow={start}
          />
          <div
            className="absolute -right-1.5 inset-y-0 w-3 cursor-ew-resize rounded-r-md bg-primary"
            onPointerDown={onDown("end")}
            role="slider"
            aria-label="Clip end"
            aria-valuenow={end}
          />
        </div>
        {/* playhead */}
        <div className="pointer-events-none absolute inset-y-0 w-0.5 bg-accent" style={{ left: `${pct(time)}%` }} />
      </div>
      <div className="relative mt-1 h-4 text-[10px] text-muted">
        {ticks.map((t) => (
          <span key={t} className="absolute -translate-x-1/2 tabular-nums" style={{ left: `${pct(t)}%` }}>
            {fmtTime(t)}
          </span>
        ))}
      </div>
    </div>
  );
}
