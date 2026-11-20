// Hook-title layout shared by the live preview and the editor. Mirrors backend/app/pipeline/captions.py
// (resolve_title / title_lines / title_events), so the preview matches the export.
import type { Overlay, TitleStyle } from "./types";

export type TitleAnimation = "pop" | "slam" | "fade" | "slide_up" | "flicker" | "typewriter" | "none";
export type TitleSpec = {
  font: string;
  size: number;
  color: string;
  uppercase: boolean;
  outline: number;
  outline_color: string;
  shadow: number;
  shadow_color: string;
  box: boolean;
  box_color: string;
  box_opacity: number;
  box_pad: number;
  glow: number;
  glow_color: string;
  animation: TitleAnimation;
  rotation: number;
  line_spacing: number;
  letter_spacing: number;
  align: "left" | "center" | "right";
  auto_colors: boolean;
  word_colors: Record<string, string> | null;
  wrap: "auto" | "one";
};

export const TITLE_ACCENTS = ["#FFD60A", "#FF3B30", "#34C759", "#3FA9FF"];

export const TITLE_BASE: TitleSpec = {
  font: "Poppins ExtraBold",
  size: 90,
  color: "#FFFFFF",
  uppercase: false,
  outline: 0,
  outline_color: "#000000",
  shadow: 0,
  shadow_color: "#000000",
  box: false,
  box_color: "#000000",
  box_opacity: 0.7,
  box_pad: 16,
  glow: 0,
  glow_color: "#3FA9FF",
  animation: "pop",
  rotation: 0,
  line_spacing: 1,
  letter_spacing: 0,
  align: "center",
  auto_colors: false,
  word_colors: null,
  wrap: "auto",
};

export const TITLE_PRESETS: Record<TitleStyle, Partial<TitleSpec>> = {
  impact: { font: "Luckiest Guy", size: 104, uppercase: true, outline: 11, shadow: 5, auto_colors: true },
  box: {
    font: "Archivo Black",
    size: 76,
    color: "#101010",
    uppercase: true,
    shadow: 8,
    box: true,
    box_color: "#FFD60A",
    box_opacity: 1,
    box_pad: 20,
    animation: "slam",
    rotation: -2,
    line_spacing: 1.25,
  },
  neon: { size: 100, uppercase: true, outline: 3, outline_color: "#3FA9FF", glow: 22, animation: "flicker", line_spacing: 1.1 },
  minimal: { size: 92, box: true, box_opacity: 0.69, box_pad: 18, animation: "fade", line_spacing: 1.3 },
};

export const SPEC_KEYS = Object.keys(TITLE_BASE) as (keyof TitleSpec)[];

export function resolveTitle(ov: Partial<Overlay> & Record<string, unknown>): TitleSpec {
  const design = (ov.style && ov.style in TITLE_PRESETS ? ov.style : "impact") as TitleStyle;
  const spec = { ...TITLE_BASE, ...TITLE_PRESETS[design] } as TitleSpec;
  for (const k of SPEC_KEYS) {
    const v = ov[k];
    if (v !== undefined && v !== null) (spec as Record<string, unknown>)[k] = v;
  }
  return spec;
}

const STOP = new Set(
  "a an the and or but so to of in on at for with is are was were be been it its this that these those i you he she we they my your our their me him her us them do does did have has had not no yes just very really what how why when who where which than then there here about from into over out up down as by if".split(" "),
);

/** Indexes of the 1-3 words worth colouring: numbers, then the longest (mirrors _key_words). */
export function keyWords(words: string[]): number[] {
  const clean = words.map((w) => w.toLowerCase().replace(/[^a-z0-9$%]/g, ""));
  const pick = new Set(clean.flatMap((c, i) => (c && /\d/.test(c) && !STOP.has(c) ? [i] : [])));
  const rest = clean
    .map((c, i) => [c, i] as const)
    .filter(([c, i]) => c && !STOP.has(c) && !pick.has(i))
    .sort((a, b) => b[0].length - a[0].length);
  for (const [, i] of rest) {
    if (pick.size >= 2) break;
    pick.add(i);
  }
  return [...pick].sort((a, b) => a - b).slice(0, 3);
}

export function splitTitle(text: string, maxChars: number): string[] {
  const words = text.split(/\s+/).filter(Boolean);
  if (text.length <= maxChars || words.length < 2) return [text];
  let best = 1e9;
  let cut = 1;
  for (let i = 1; i < words.length; i++) {
    const d = Math.abs(words.slice(0, i).join(" ").length - words.slice(i).join(" ").length);
    if (d < best) {
      best = d;
      cut = i;
    }
  }
  let lines = [words.slice(0, cut).join(" "), words.slice(cut).join(" ")];
  if (Math.max(...lines.map((l) => l.length)) > maxChars * 1.6 && words.length >= 3) {
    const n = words.length;
    lines = [words.slice(0, Math.floor(n / 3)), words.slice(Math.floor(n / 3), Math.floor((2 * n) / 3)), words.slice(Math.floor((2 * n) / 3))].map((w) => w.join(" "));
  }
  return lines;
}

export function titleLines(text: string, spec: TitleSpec): string[] {
  let raw = (text ?? "").replace(/\r/g, "");
  if (spec.uppercase) raw = raw.toUpperCase();
  if (raw.includes("\n")) return raw.split("\n").map((l) => l.trim()).filter(Boolean);
  raw = raw.split(/\s+/).filter(Boolean).join(" ");
  if (!raw) return [];
  if (spec.wrap === "one") return [raw];
  return splitTitle(raw, Math.max(8, Math.min(40, Math.round(1600 / spec.size))));
}

/** Word colour map actually used (explicit, or automatic key words). */
export function wordColors(lines: string[], spec: TitleSpec): Record<number, string> {
  if (spec.word_colors) {
    const out: Record<number, string> = {};
    for (const [k, v] of Object.entries(spec.word_colors)) if (/^\d+$/.test(k)) out[Number(k)] = v;
    return out;
  }
  if (!spec.auto_colors) return {};
  const words = lines.flatMap((l) => l.split(" "));
  return Object.fromEntries(keyWords(words).map((wi, ci) => [wi, TITLE_ACCENTS[ci % TITLE_ACCENTS.length]]));
}

/** Split a title text into n balanced lines with explicit line breaks. */
export function balanceInto(text: string, n: number): string {
  const words = text.replace(/\n/g, " ").split(/\s+/).filter(Boolean);
  if (n <= 1 || words.length < 2) return words.join(" ");
  const total = words.join(" ").length;
  const out: string[][] = [[]];
  let len = 0;
  for (const w of words) {
    const cur = out[out.length - 1];
    if (cur.length && len + w.length / 2 > (total / n) * out.length && out.length < n) {
      out.push([w]);
    } else cur.push(w);
    len += w.length + 1;
  }
  return out.map((l) => l.join(" ")).join("\n");
}
