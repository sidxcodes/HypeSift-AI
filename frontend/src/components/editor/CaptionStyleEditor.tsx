"use client";

import { RotateCcw } from "lucide-react";
import type { CaptionStyle, Effect, Pos, Transition } from "@/lib/types";
import { CaptionSample } from "../CaptionPreview";
import { PositionPicker } from "../Pickers";
import { cx, Switch } from "../ui";
import { Color, Group, Slider, TITLE_FONTS } from "./TitleEditor";

const ANIMS: [CaptionStyle["animation"], string][] = [
  ["highlight", "Word colour"],
  ["pop", "Word pop"],
  ["karaoke", "Karaoke fill"],
  ["fade", "Fade"],
  ["none", "None"],
];
const SPOTS: [CaptionStyle["position"], string][] = [
  ["top", "Top"],
  ["middle", "Middle"],
  ["lower", "Lower third"],
  ["bottom", "Bottom"],
];

function Chips<T extends string>({ value, options, onChange }: { value: T; options: [T, string][]; onChange: (v: T) => void }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map(([v, label]) => (
        <button
          key={v}
          type="button"
          aria-pressed={value === v}
          onClick={() => onChange(v)}
          className={cx("h-8 rounded-full border px-3 text-xs cursor-pointer", value === v ? "border-primary bg-primary text-on-primary" : "border-border hover:border-primary/50")}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

/** Canva-style control over the burned-in captions (same building blocks as the title editor). */
export function CaptionStyleEditor({
  style,
  preset,
  presets,
  transition,
  effect,
  transitions,
  effects,
  thumb,
  setStyle,
  setPreset,
  setCaptions,
  setMaxWords,
  resetStyle,
}: {
  style: CaptionStyle;
  preset: string;
  presets: Record<string, CaptionStyle>;
  transition: Transition;
  effect: Effect;
  transitions: Record<string, string>;
  effects: Record<string, string>;
  thumb?: string | null;
  setStyle: (patch: Partial<CaptionStyle>) => void;
  setPreset: (key: string) => void;
  setCaptions: (patch: { transition?: Transition; effect?: Effect }) => void;
  setMaxWords: (n: number) => void;
  resetStyle: () => void;
}) {
  return (
    <div className="space-y-4">
      <Group
        title="Style"
        action={
          <button type="button" onClick={resetStyle} className="inline-flex items-center gap-1 text-xs text-primary hover:underline cursor-pointer">
            <RotateCcw className="size-3" /> Reset to style
          </button>
        }
      >
        <div className="grid max-h-56 grid-cols-3 gap-2 overflow-y-auto pr-1 scrollbar-thin">
          {Object.entries(presets).map(([k, st]) => (
            <button
              key={k}
              type="button"
              aria-pressed={preset === k}
              onClick={() => setPreset(k)}
              className={cx("overflow-hidden rounded-lg border-2 text-left cursor-pointer", preset === k ? "border-primary" : "border-transparent hover:border-primary/30")}
            >
              <div
                className="grid h-12 place-items-center bg-[#2b2f45] bg-cover bg-center"
                style={thumb ? { backgroundImage: `linear-gradient(rgba(0,0,0,.35),rgba(0,0,0,.35)),url(${thumb})` } : undefined}
              >
                <CaptionSample style={st} scale={0.16} />
              </div>
              <div className={cx("truncate px-1.5 py-1 text-[11px] font-medium", preset === k ? "bg-primary text-on-primary" : "bg-surface-2")}>{st.label}</div>
            </button>
          ))}
        </div>
      </Group>

      <Group title="Font">
        <select
          value={style.font}
          onChange={(e) => setStyle({ font: e.target.value })}
          className="h-10 w-full rounded-xl border border-border bg-surface px-3 text-[15px] cursor-pointer"
          style={{ fontFamily: `"HS ${style.font}"` }}
          aria-label="Caption font"
        >
          {TITLE_FONTS.concat(["Poppins Medium"]).map((f) => (
            <option key={f} value={f} style={{ fontFamily: `"HS ${f}"` }}>
              {f}
            </option>
          ))}
        </select>
        <Slider label="Size" value={style.size} min={30} max={160} onChange={(v) => setStyle({ size: v })} />
        <div className="grid grid-cols-2 gap-3">
          <Slider label="Letter spacing" value={style.letter_spacing ?? 0} min={-4} max={24} onChange={(v) => setStyle({ letter_spacing: v })} />
          <Slider label="Words per caption" value={style.max_words ?? 3} min={1} max={7} onChange={(v) => setMaxWords(v)} />
        </div>
        <Switch checked={style.uppercase} onChange={(v) => setStyle({ uppercase: v })} label="UPPERCASE" />
      </Group>

      <Group title="Colours">
        <Color label="Text" value={style.color} onChange={(v) => setStyle({ color: v })} />
        <Color label="Spoken word" value={style.highlight} onChange={(v) => setStyle({ highlight: v })} />
        <Switch checked={!!style.emphasis} onChange={(v) => setStyle({ emphasis: v })} label="Colour key words" />
        {style.emphasis && <Color label="Key words" value={style.emphasis_color ?? style.highlight} onChange={(v) => setStyle({ emphasis_color: v })} />}
      </Group>

      <Group title="Effects">
        <Switch checked={style.box} onChange={(v) => setStyle({ box: v, box_opacity: v ? Math.max(0.5, style.box_opacity || 0) : 0 })} label="Background box" />
        {style.box ? (
          <>
            <Color label="Box colour" value={style.box_color} onChange={(v) => setStyle({ box_color: v })} />
            <Slider label="Box opacity" value={style.box_opacity} min={0.1} max={1} step={0.05} onChange={(v) => setStyle({ box_opacity: v })} />
          </>
        ) : (
          <>
            <Slider label="Outline" value={style.outline} min={0} max={16} onChange={(v) => setStyle({ outline: v })} />
            {style.outline > 0 && <Color label="Outline colour" value={style.outline_color} onChange={(v) => setStyle({ outline_color: v })} />}
            <Slider label="Glow" value={style.glow ?? 0} min={0} max={30} onChange={(v) => setStyle({ glow: v })} />
            {(style.glow ?? 0) > 0 && <Color label="Glow colour" value={style.glow_color ?? "#000000"} onChange={(v) => setStyle({ glow_color: v })} />}
            <Slider label="Shadow" value={style.shadow} min={0} max={16} onChange={(v) => setStyle({ shadow: v })} />
            {style.shadow > 0 && <Color label="Shadow colour" value={style.shadow_color ?? "#000000"} onChange={(v) => setStyle({ shadow_color: v })} />}
          </>
        )}
        <div className="grid grid-cols-2 gap-3">
          <Slider label="Opacity" value={style.opacity ?? 1} min={0.2} max={1} step={0.05} onChange={(v) => setStyle({ opacity: v })} />
          <Slider label="Rotation" value={style.rotation ?? 0} min={-20} max={20} unit="°" onChange={(v) => setStyle({ rotation: v })} />
        </div>
      </Group>

      <Group title="Animation">
        <div className="text-[13px]">Spoken word</div>
        <Chips value={style.animation} options={ANIMS} onChange={(v) => setStyle({ animation: v })} />
        <div className="text-[13px]">Each caption enters with</div>
        <Chips value={transition} options={Object.entries(transitions) as [Transition, string][]} onChange={(v) => setCaptions({ transition: v })} />
        <div className="text-[13px]">Extra effect</div>
        <Chips value={effect} options={Object.entries(effects) as [Effect, string][]} onChange={(v) => setCaptions({ effect: v })} />
      </Group>

      <Group title="Position">
        <Chips value={style.pos ? ("" as CaptionStyle["position"]) : style.position} options={SPOTS} onChange={(v) => setStyle({ position: v, pos: null })} />
        <PositionPicker label="Caption position" value={style.pos ?? null} onChange={(p: Pos | null) => setStyle({ pos: p })} />
        <p className="text-[11px] text-muted">Or drag the captions on the video.</p>
      </Group>
    </div>
  );
}
