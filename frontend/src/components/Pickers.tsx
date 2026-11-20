"use client";

import type { ComparePlay, GenerateSettings, Pos, TitleStyle } from "@/lib/types";
import { TitleCard } from "./CaptionPreview";
import { cx } from "./ui";

// ----------------------------------------------------------------------------- clip length

export const LENGTHS: { id: string; label: string; hint: string; min: number; max: number; target: number | null }[] = [
  { id: "auto", label: "Auto", hint: "15–60 s, the AI decides", min: 15, max: 60, target: null },
  { id: "30", label: "~30 s", hint: "25–35 s", min: 25, max: 35, target: 30 },
  { id: "45", label: "~45 s", hint: "38–52 s", min: 38, max: 52, target: 45 },
  { id: "60", label: "~60 s", hint: "52–65 s", min: 52, max: 65, target: 60 },
  { id: "90", label: "~90 s", hint: "78–98 s", min: 78, max: 98, target: 90 },
];

export function lengthId(s: GenerateSettings): string {
  return LENGTHS.find((l) => l.min === s.min_dur && l.max === s.max_dur)?.id ?? "custom";
}

export function LengthPicker({ s, onChange }: { s: GenerateSettings; onChange: (p: Partial<GenerateSettings>) => void }) {
  const id = lengthId(s);
  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {[...LENGTHS, { id: "custom", label: "Custom", hint: "", min: 0, max: 0, target: null }].map((l) => (
          <button
            key={l.id}
            type="button"
            aria-pressed={id === l.id}
            onClick={() =>
              l.id === "custom"
                ? onChange({ min_dur: Math.round(s.max_dur * 0.8), target_dur: s.max_dur })
                : onChange({ min_dur: l.min, max_dur: l.max, target_dur: l.target })
            }
            className={cx(
              "rounded-xl border px-3.5 py-2 text-left transition cursor-pointer",
              id === l.id ? "border-primary bg-primary text-on-primary" : "border-border bg-surface hover:border-primary/40",
            )}
          >
            <div className="text-sm font-semibold">{l.label}</div>
            {l.hint && <div className={cx("text-[11px]", id === l.id ? "text-on-primary/75" : "text-muted")}>{l.hint}</div>}
          </button>
        ))}
      </div>
      {id === "custom" && (
        <label className="mt-3 flex items-center gap-3 text-sm">
          <span className="w-24 shrink-0 font-medium">≈ {s.target_dur ?? s.max_dur} s</span>
          <input
            type="range"
            min={15}
            max={180}
            step={5}
            value={s.target_dur ?? s.max_dur}
            aria-label="Clip length in seconds"
            onChange={(e) => {
              const v = Number(e.target.value);
              onChange({ target_dur: v, min_dur: Math.max(8, Math.round(v * 0.85)), max_dur: Math.round(v * 1.1) });
            }}
            className="flex-1"
          />
        </label>
      )}
    </div>
  );
}

// ----------------------------------------------------------------------------- title designs

export const TITLE_STYLES: { id: TitleStyle; label: string }[] = [
  { id: "impact", label: "Impact pop" },
  { id: "box", label: "Bold box" },
  { id: "neon", label: "Neon glow" },
  { id: "minimal", label: "Minimal" },
];

export function TitleStylePicker({ value, onChange, bg }: { value: TitleStyle; onChange: (v: TitleStyle) => void; bg?: string | null }) {
  return (
    <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
      {TITLE_STYLES.map((t) => (
        <button
          key={t.id}
          type="button"
          aria-pressed={value === t.id}
          onClick={() => onChange(t.id)}
          className={cx(
            "overflow-hidden rounded-xl border-2 text-left transition cursor-pointer",
            value === t.id ? "border-primary" : "border-transparent hover:border-primary/30",
          )}
        >
          <div
            className="relative grid h-24 place-items-center overflow-hidden bg-[#2b2f45] bg-cover bg-center px-2 text-center"
            style={bg ? { backgroundImage: `linear-gradient(rgba(0,0,0,.25),rgba(0,0,0,.25)),url(${bg})` } : undefined}
          >
            <TitleCard ov={{ text: "GTA 5 vs GTA 6 physics", style: t.id, start: 0, end: 99 }} scale={0.21} />
          </div>
          <div className={cx("px-2.5 py-1.5 text-xs font-medium", value === t.id ? "bg-primary text-on-primary" : "bg-surface-2")}>{t.label}</div>
        </button>
      ))}
    </div>
  );
}

// ----------------------------------------------------------------------------- positions

const GRID: { x: number; y: number; name: string }[] = [0.12, 0.5, 0.86].flatMap((y, r) =>
  [0.15, 0.5, 0.85].map((x, c) => ({ x, y, name: `${["Top", "Middle", "Bottom"][r]} ${["left", "centre", "right"][c]}` })),
);

/** 3×3 spot picker (+ "Auto"); arrows nudge the chosen spot. Value null = the design's default. */
export function PositionPicker({ value, onChange, label }: { value: Pos | null | undefined; onChange: (p: Pos | null) => void; label: string }) {
  const nudge = (dx: number, dy: number) => {
    const p = value ?? { x: 0.5, y: 0.5 };
    onChange({ x: Math.min(1, Math.max(0, +(p.x + dx).toFixed(2))), y: Math.min(0.96, Math.max(0.04, +(p.y + dy).toFixed(2))) });
  };
  return (
    <div className="flex flex-wrap items-center gap-4" role="group" aria-label={label}>
      <div className="relative grid h-[104px] w-[62px] grid-cols-3 grid-rows-3 gap-1 rounded-lg bg-[#2b2f45] p-1.5">
        {GRID.map((g) => {
          const on = !!value && Math.abs(value.x - g.x) < 0.17 && Math.abs(value.y - g.y) < 0.2;
          return (
            <button
              key={g.name}
              type="button"
              title={g.name}
              aria-label={`${label}: ${g.name}`}
              aria-pressed={on}
              onClick={() => onChange({ x: g.x, y: g.y })}
              className={cx("rounded-[3px] transition cursor-pointer", on ? "bg-accent" : "bg-white/20 hover:bg-white/45")}
            />
          );
        })}
      </div>
      <div className="flex flex-col gap-2">
        <div className="flex gap-1">
          {(
            [
              ["↑", 0, -0.04, "Move up"],
              ["↓", 0, 0.04, "Move down"],
              ["←", -0.05, 0, "Move left"],
              ["→", 0.05, 0, "Move right"],
            ] as const
          ).map(([a, dx, dy, t]) => (
            <button
              key={t}
              type="button"
              title={t}
              aria-label={`${label}: ${t}`}
              onClick={() => nudge(dx, dy)}
              className="grid size-8 place-items-center rounded-lg border border-border bg-surface text-sm hover:border-primary cursor-pointer"
            >
              {a}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={() => onChange(null)}
          aria-pressed={!value}
          className={cx("h-8 rounded-lg border px-3 text-xs cursor-pointer", !value ? "border-primary bg-primary-soft text-primary" : "border-border text-muted hover:text-text")}
        >
          Auto position
        </button>
      </div>
      {value && (
        <span className="text-xs text-muted">
          {Math.round(value.x * 100)}% across · {Math.round(value.y * 100)}% down
        </span>
      )}
    </div>
  );
}

// ----------------------------------------------------------------------------- comparison play modes

function Diagram({ mode }: { mode: ComparePlay }) {
  const panel = (on: boolean, k: number) => (
    <div key={k} className={cx("flex-1 rounded-[3px]", on ? "bg-accent" : "bg-white/25")}>
      {!on && mode === "turns" && <div className="grid h-full place-items-center text-[8px] text-white/80">❚❚</div>}
    </div>
  );
  if (mode === "grid_then_single") {
    return (
      <div className="flex h-16 items-center gap-1.5">
        <div className="flex h-full w-9 flex-col gap-0.5 rounded-md bg-[#2b2f45] p-1">{[0, 1, 2].map((k) => panel(true, k))}</div>
        <span className="text-white/60">→</span>
        <div className="h-full w-9 rounded-md bg-[#2b2f45] p-1">{panel(true, 0)}</div>
      </div>
    );
  }
  return (
    <div className="flex h-16 items-center gap-1.5">
      <div className="flex h-full w-9 flex-col gap-0.5 rounded-md bg-[#2b2f45] p-1">{[0, 1].map((k) => panel(mode === "together" || k === 0, k))}</div>
      {mode === "turns" && (
        <>
          <span className="text-white/60">→</span>
          <div className="flex h-full w-9 flex-col gap-0.5 rounded-md bg-[#2b2f45] p-1">{[0, 1].map((k) => panel(k === 1, k))}</div>
        </>
      )}
    </div>
  );
}

export const PLAY_MODES: { id: ComparePlay; label: string; hint: string }[] = [
  { id: "turns", label: "Take turns", hint: "One plays, the other pauses; you hear only the one playing" },
  { id: "together", label: "Play together", hint: "Both play at once, one soundtrack" },
  { id: "grid_then_single", label: "All, then one by one", hint: "All in one frame first, then each full screen" },
];

export function ComparePlayPicker({ value, onChange }: { value: ComparePlay; onChange: (v: ComparePlay) => void }) {
  return (
    <div className="grid gap-2.5 sm:grid-cols-3">
      {PLAY_MODES.map((m) => (
        <button
          key={m.id}
          type="button"
          aria-pressed={value === m.id}
          onClick={() => onChange(m.id)}
          className={cx(
            "flex flex-col gap-2 rounded-xl border-2 p-3 text-left transition cursor-pointer",
            value === m.id ? "border-primary bg-primary-soft" : "border-border hover:border-primary/40",
          )}
        >
          <div className="w-fit rounded-lg bg-hero px-2 py-1.5">
            <Diagram mode={m.id} />
          </div>
          <div className="text-sm font-semibold">{m.label}</div>
          <div className="text-[11px] leading-snug text-muted">{m.hint}</div>
        </button>
      ))}
    </div>
  );
}
