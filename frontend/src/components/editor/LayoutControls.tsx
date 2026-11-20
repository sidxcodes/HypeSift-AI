"use client";

import { ArrowDownUp, RotateCcw } from "lucide-react";
import { facecamLayout, type GameLayout, type PanelAdj } from "@/lib/layout";
import { cx } from "../ui";

function Row({ label, value, min, max, step, fmt, onChange }: { label: string; value: number; min: number; max: number; step: number; fmt: (v: number) => string; onChange: (v: number) => void }) {
  return (
    <label className="block text-[13px]">
      <span className="flex justify-between">
        <span>{label}</span>
        <span className="tabular-nums text-muted">{fmt(value)}</span>
      </span>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} className="mt-1 w-full" aria-label={label} />
    </label>
  );
}

/** Manual control of the gameplay layout: cam size, cam/game zoom and position, order. */
export function LayoutControls({
  layout,
  box,
  sw,
  sh,
  W,
  H,
  onChange,
}: {
  layout: GameLayout | undefined;
  box: number[] | null | undefined;
  sw: number;
  sh: number;
  W: number;
  H: number;
  onChange: (l: GameLayout) => void;
}) {
  const lay = layout ?? {};
  const L = facecamLayout(sw, sh, W, H, box, lay);
  const def = facecamLayout(sw, sh, W, H, box, { split: lay.split });
  const set = (patch: GameLayout) => onChange({ ...lay, ...patch });
  const panel = (name: "cam" | "game", title: string) => {
    const cur = L[name];
    const base = def[name];
    const zoom = base.w / cur.w;
    const put = (p: Partial<PanelAdj>) => set({ [name]: { ...cur, ...p } } as GameLayout);
    return (
      <div className="space-y-2.5 rounded-xl bg-surface-2 p-3">
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold">{title}</span>
          <button type="button" onClick={() => set({ [name]: undefined } as GameLayout)} className="inline-flex items-center gap-1 text-xs text-primary hover:underline cursor-pointer">
            <RotateCcw className="size-3" /> Reset
          </button>
        </div>
        <Row label="Zoom" value={+zoom.toFixed(2)} min={0.4} max={4} step={0.05} fmt={(v) => `${v.toFixed(2)}×`} onChange={(v) => put({ w: Math.min(1, base.w / v) })} />
        <Row label="Left ↔ right" value={cur.x} min={0} max={1} step={0.005} fmt={(v) => `${Math.round(v * 100)}%`} onChange={(v) => put({ x: v })} />
        <Row label="Up ↕ down" value={cur.y} min={0} max={1} step={0.005} fmt={(v) => `${Math.round(v * 100)}%`} onChange={(v) => put({ y: v })} />
      </div>
    );
  };
  return (
    <div className="space-y-3">
      <Row
        label="Cam size (share of the frame)"
        value={L.split}
        min={0.2}
        max={0.7}
        step={0.01}
        fmt={(v) => `${Math.round(v * 100)}%`}
        onChange={(v) => set({ split: v })}
      />
      <button
        type="button"
        onClick={() => set({ swap: !lay.swap })}
        aria-pressed={!!lay.swap}
        className={cx(
          "inline-flex h-9 items-center gap-2 rounded-xl border px-3 text-sm cursor-pointer",
          lay.swap ? "border-primary bg-primary-soft text-primary" : "border-border hover:border-primary/50",
        )}
      >
        <ArrowDownUp className="size-4" /> {lay.swap ? "Cam at the bottom" : "Cam on top"}
      </button>
      {panel("cam", "Cam video")}
      {panel("game", "Game / main video")}
      <p className="text-[11px] text-muted">Tip: drag the cam or the game directly on the preview to move it.</p>
      <button type="button" onClick={() => onChange({})} className="text-xs text-primary hover:underline cursor-pointer">
        Reset whole layout
      </button>
    </div>
  );
}
