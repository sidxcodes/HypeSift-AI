"use client";

import { AlignCenter, AlignLeft, AlignRight, RotateCcw } from "lucide-react";
import { useState } from "react";
import { balanceInto, resolveTitle, TITLE_ACCENTS, titleLines, wordColors, type TitleAnimation, type TitleSpec } from "@/lib/title";
import type { Overlay, TitleStyle } from "@/lib/types";
import { PositionPicker, TitleStylePicker } from "../Pickers";
import { cx, Switch } from "../ui";

export const TITLE_FONTS = [
  "Luckiest Guy",
  "Anton",
  "Bebas Neue",
  "Bangers",
  "Archivo Black",
  "Bungee",
  "Poppins ExtraBold",
  "Poppins SemiBold",
  "Permanent Marker",
  "DM Serif Display",
  "DM Serif Display Italic",
  "Courier Prime",
];
const SWATCHES = ["#FFFFFF", "#000000", ...TITLE_ACCENTS, "#FF7A59", "#B26BFF", "#FF4FA3"];
const ANIMS: { id: TitleAnimation; label: string }[] = [
  { id: "pop", label: "Pop" },
  { id: "slam", label: "Slam" },
  { id: "fade", label: "Fade" },
  { id: "slide_up", label: "Slide up" },
  { id: "flicker", label: "Flicker" },
  { id: "typewriter", label: "Typewriter" },
  { id: "none", label: "None" },
];

type Ov = Overlay & Partial<TitleSpec>;

export function Group({ title, children, action }: { title: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <section className="space-y-2.5 border-t border-border pt-4 first:border-0 first:pt-0">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-muted">{title}</h4>
        {action}
      </div>
      {children}
    </section>
  );
}

export function Slider({ label, value, min, max, step = 1, unit = "", onChange }: { label: string; value: number; min: number; max: number; step?: number; unit?: string; onChange: (v: number) => void }) {
  return (
    <label className="block text-[13px]">
      <span className="flex justify-between">
        <span>{label}</span>
        <span className="tabular-nums text-muted">
          {Math.round(value * 100) / 100}
          {unit}
        </span>
      </span>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} className="mt-1 w-full" aria-label={label} />
    </label>
  );
}

export function Color({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-24 shrink-0 text-[13px]">{label}</span>
      <div className="flex flex-wrap items-center gap-1.5">
        {SWATCHES.map((c) => (
          <button
            key={c}
            type="button"
            title={c}
            aria-label={`${label}: ${c}`}
            onClick={() => onChange(c)}
            className={cx("size-6 rounded-full border cursor-pointer", value.toLowerCase() === c.toLowerCase() ? "ring-2 ring-primary ring-offset-2 ring-offset-surface" : "border-border")}
            style={{ background: c }}
          />
        ))}
        <input type="color" value={value} onChange={(e) => onChange(e.target.value)} className="size-7 cursor-pointer rounded-md border border-border bg-surface" aria-label={`${label}: custom colour`} />
      </div>
    </div>
  );
}

/** Canva-style control over the hook title: text and lines, design, font, colours per word,
 * outline / shadow / glow / box, spacing, rotation, animation, timing and position. */
export function TitleEditor({ ov, clipLength, onChange, thumb }: { ov: Ov; clipLength: number; onChange: (patch: Partial<Ov>) => void; thumb?: string | null }) {
  const spec = resolveTitle(ov as Ov & Record<string, unknown>);
  const lines = titleLines(ov.text, spec);
  const colors = wordColors(lines, spec);
  const words = lines.flatMap((l) => l.split(" "));
  const [paint, setPaint] = useState<string>(TITLE_ACCENTS[0]);
  const set = (patch: Partial<Ov>) => onChange(patch);
  const lineCount = ov.text.includes("\n") ? ov.text.split("\n").filter((l) => l.trim()).length : spec.wrap === "one" ? 1 : 0;

  return (
    <div className="space-y-4">
      <Group title="Text">
        <textarea
          value={ov.text}
          onChange={(e) => set({ text: e.target.value.slice(0, 160) })}
          rows={3}
          className="w-full resize-y rounded-xl border border-border bg-surface px-3 py-2 text-sm focus:border-primary focus:outline-none"
          aria-label="Title text"
          placeholder="Type your title. Press Enter for a new line."
        />
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          <span className="text-muted">Lines:</span>
          {[
            { k: 0, label: "Auto", run: () => set({ text: ov.text.replace(/\s*\n\s*/g, " "), wrap: "auto" }) },
            { k: 1, label: "One line", run: () => set({ text: ov.text.replace(/\s*\n\s*/g, " "), wrap: "one" }) },
            { k: 2, label: "2 lines", run: () => set({ text: balanceInto(ov.text, 2), wrap: "auto" }) },
            { k: 3, label: "3 lines", run: () => set({ text: balanceInto(ov.text, 3), wrap: "auto" }) },
          ].map((b) => (
            <button
              key={b.k}
              type="button"
              onClick={b.run}
              className={cx("h-7 rounded-full border px-2.5 cursor-pointer", lineCount === b.k ? "border-primary bg-primary text-on-primary" : "border-border hover:border-primary/50")}
            >
              {b.label}
            </button>
          ))}
        </div>
        <p className="text-[11px] text-muted">Press Enter where you want a line to break, e.g. “TECHNO GAMER ⏎ GOT ANGRY?”.</p>
      </Group>

      <Group
        title="Design"
        action={
          <button
            type="button"
            onClick={() => set(Object.fromEntries(Object.keys(spec).map((k) => [k, undefined])) as Partial<Ov>)}
            className="inline-flex items-center gap-1 text-xs text-primary hover:underline cursor-pointer"
          >
            <RotateCcw className="size-3" /> Reset to design
          </button>
        }
      >
        <TitleStylePicker
          value={(ov.style as TitleStyle) ?? "impact"}
          onChange={(v) => set({ ...(Object.fromEntries(Object.keys(spec).map((k) => [k, undefined])) as Partial<Ov>), style: v })}
          bg={thumb}
        />
      </Group>

      <Group title="Font">
        <select
          value={spec.font}
          onChange={(e) => set({ font: e.target.value })}
          className="h-10 w-full rounded-xl border border-border bg-surface px-3 text-[15px] cursor-pointer"
          style={{ fontFamily: `"HS ${spec.font}"` }}
          aria-label="Font"
        >
          {TITLE_FONTS.map((f) => (
            <option key={f} value={f} style={{ fontFamily: `"HS ${f}"` }}>
              {f}
            </option>
          ))}
        </select>
        <Slider label="Size" value={spec.size} min={30} max={200} onChange={(v) => set({ size: v })} />
        <div className="flex flex-wrap items-center gap-3">
          <div className="inline-flex rounded-lg border border-border p-0.5" role="group" aria-label="Alignment">
            {([
              ["left", AlignLeft],
              ["center", AlignCenter],
              ["right", AlignRight],
            ] as const).map(([a, Icon]) => (
              <button
                key={a}
                type="button"
                aria-label={`Align ${a}`}
                aria-pressed={spec.align === a}
                onClick={() => set({ align: a })}
                className={cx("grid size-8 place-items-center rounded-md cursor-pointer", spec.align === a ? "bg-primary text-on-primary" : "text-muted hover:text-text")}
              >
                <Icon className="size-4" />
              </button>
            ))}
          </div>
          <div className="min-w-40 flex-1">
            <Switch checked={spec.uppercase} onChange={(v) => set({ uppercase: v })} label="UPPERCASE" />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Slider label="Letter spacing" value={spec.letter_spacing} min={-5} max={30} onChange={(v) => set({ letter_spacing: v })} />
          <Slider label="Line spacing" value={spec.line_spacing} min={0.7} max={2} step={0.05} onChange={(v) => set({ line_spacing: v })} />
        </div>
      </Group>

      <Group title="Colours">
        <Color label="Text" value={spec.color} onChange={(v) => set({ color: v })} />
        <div>
          <div className="mb-1.5 flex items-center justify-between text-[13px]">
            <span>Colour single words</span>
            <button
              type="button"
              onClick={() => set({ word_colors: null, auto_colors: !spec.auto_colors })}
              className="text-xs text-primary hover:underline cursor-pointer"
            >
              {spec.auto_colors && !spec.word_colors ? "Turn off auto colours" : "Auto-colour key words"}
            </button>
          </div>
          <div className="mb-2 flex items-center gap-1.5">
            <span className="text-[11px] text-muted">Brush:</span>
            {[...TITLE_ACCENTS, "#FF7A59", "#FFFFFF"].map((c) => (
              <button
                key={c}
                type="button"
                aria-label={`Brush colour ${c}`}
                onClick={() => setPaint(c)}
                className={cx("size-5 rounded-full border border-black/10 cursor-pointer", paint === c && "ring-2 ring-primary ring-offset-1")}
                style={{ background: c }}
              />
            ))}
            <input type="color" value={paint} onChange={(e) => setPaint(e.target.value)} className="size-6 cursor-pointer rounded border border-border" aria-label="Custom brush colour" />
          </div>
          <div className="flex flex-wrap gap-1.5">
            {words.map((w, i) => (
              <button
                key={i}
                type="button"
                title="Click to paint with the brush colour; click again to clear"
                onClick={() => {
                  const cur: Record<string, string> = Object.fromEntries(Object.entries(colors).map(([k, v]) => [String(k), v]));
                  if (cur[i] && cur[i].toLowerCase() === paint.toLowerCase()) delete cur[i];
                  else cur[i] = paint;
                  set({ word_colors: cur, auto_colors: false });
                }}
                className="rounded-md border border-border bg-[#2b2f45] px-2 py-1 text-xs font-semibold cursor-pointer hover:border-primary"
                style={{ color: colors[i] ?? spec.color }}
              >
                {w}
              </button>
            ))}
          </div>
        </div>
      </Group>

      <Group title="Effects">
        <Switch checked={spec.box} onChange={(v) => set({ box: v })} label="Background box" />
        {spec.box ? (
          <div className="space-y-2.5">
            <Color label="Box colour" value={spec.box_color} onChange={(v) => set({ box_color: v })} />
            <div className="grid grid-cols-2 gap-3">
              <Slider label="Box opacity" value={spec.box_opacity} min={0.1} max={1} step={0.05} onChange={(v) => set({ box_opacity: v })} />
              <Slider label="Box padding" value={spec.box_pad} min={0} max={50} onChange={(v) => set({ box_pad: v })} />
            </div>
          </div>
        ) : (
          <div className="space-y-2.5">
            <Slider label="Outline" value={spec.outline} min={0} max={30} onChange={(v) => set({ outline: v })} />
            {spec.outline > 0 && <Color label="Outline colour" value={spec.outline_color} onChange={(v) => set({ outline_color: v })} />}
            <Slider label="Glow" value={spec.glow} min={0} max={50} onChange={(v) => set({ glow: v })} />
            {spec.glow > 0 && <Color label="Glow colour" value={spec.glow_color} onChange={(v) => set({ glow_color: v })} />}
          </div>
        )}
        <Slider label="Shadow" value={spec.shadow} min={0} max={30} onChange={(v) => set({ shadow: v })} />
        {spec.shadow > 0 && !spec.box && <Color label="Shadow colour" value={spec.shadow_color} onChange={(v) => set({ shadow_color: v })} />}
        <Slider label="Rotation" value={spec.rotation} min={-30} max={30} unit="°" onChange={(v) => set({ rotation: v })} />
      </Group>

      <Group title="Animation & timing">
        <div className="flex flex-wrap gap-1.5">
          {ANIMS.map((a) => (
            <button
              key={a.id}
              type="button"
              aria-pressed={spec.animation === a.id}
              onClick={() => set({ animation: a.id })}
              className={cx("h-8 rounded-full border px-3 text-xs cursor-pointer", spec.animation === a.id ? "border-primary bg-primary text-on-primary" : "border-border hover:border-primary/50")}
            >
              {a.label}
            </button>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Slider
            label="Starts at"
            value={ov.start ?? 0}
            min={0}
            max={Math.max(0, clipLength - 1)}
            step={0.1}
            unit="s"
            onChange={(v) => set({ start: v, end: Math.min(clipLength, v + ((ov.end ?? 3) - (ov.start ?? 0))) })}
          />
          <Slider
            label="Shows for"
            value={+((ov.end ?? 3) - (ov.start ?? 0)).toFixed(1)}
            min={0.5}
            max={Math.max(1, clipLength - (ov.start ?? 0))}
            step={0.1}
            unit="s"
            onChange={(v) => set({ end: (ov.start ?? 0) + v })}
          />
        </div>
      </Group>

      <Group title="Position">
        <PositionPicker label="Title position" value={ov.pos ?? null} onChange={(p) => set({ pos: p })} />
        <p className="text-[11px] text-muted">Or drag the title on the video. It snaps to the centre.</p>
      </Group>
    </div>
  );
}
