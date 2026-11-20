"use client";

import { cx } from "./ui";
import { resolveTitle, titleLines, wordColors } from "@/lib/title";
import type { CaptionStyle, Chunk, Effect, Overlay, Pos, Transition } from "@/lib/types";

// libass sizes text by the font's (winAscent + winDescent); CSS sizes by the em box.
// Dividing by this ratio makes the browser preview match the burned-in export.
const EM_RATIO: Record<string, number> = {
  "Poppins Medium": 1.762,
  "Poppins SemiBold": 1.762,
  "Poppins ExtraBold": 1.762,
  Anton: 1.733,
  "Bebas Neue": 1.3,
  Bangers: 1.757,
  "DM Serif Display": 1.371,
  "DM Serif Display Italic": 1.371,
  "Archivo Black": 1.347,
  "Permanent Marker": 1.427,
  "Luckiest Guy": 1.226,
  Bungee: 2.574,
  "Courier Prime": 1.318,
};

const POS: Record<CaptionStyle["position"], { top?: string; bottom?: string; center?: boolean }> = {
  top: { top: "12%" },
  middle: { center: true },
  lower: { bottom: "24%" },
  bottom: { bottom: "12%" },
};

function rgba(hex: string, a: number) {
  const h = hex.replace("#", "");
  const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

export function textStyle(style: CaptionStyle, scale: number, effect: Effect = "none"): React.CSSProperties {
  const px = (style.size * (style.size_scale ?? 1) * scale) / (EM_RATIO[style.font] ?? 1.5);
  const outline = style.box ? 0 : style.outline * scale;
  const shadows: string[] = [];
  if (style.shadow) shadows.push(`${style.shadow * scale}px ${style.shadow * scale}px 0 ${style.box ? "rgba(0,0,0,0.6)" : rgba(style.shadow_color ?? "#000000", 0.85)}`);
  const glow = style.glow || (effect === "glow" ? 10 : 0);
  if (glow && !style.box) {
    const c = style.glow ? (style.glow_color ?? "#000") : style.highlight;
    shadows.push(`0 0 ${glow * scale * 1.6}px ${c}`, `0 0 ${glow * scale * 0.8}px ${c}`);
  }
  if (effect === "shadow3d") {
    const c = style.highlight !== style.color ? style.highlight : "#C6F432";
    shadows.push(`${7 * scale}px ${7 * scale}px 0 ${c}`);
  }
  return {
    fontFamily: `"HS ${style.font}", sans-serif`,
    fontSize: px,
    lineHeight: 1.15,
    letterSpacing: (style.letter_spacing ?? 0) * scale,
    color: style.color,
    textTransform: style.uppercase ? "uppercase" : "none",
    WebkitTextStroke: outline ? `${outline * 2}px ${style.outline_color}` : undefined,
    paintOrder: "stroke fill",
    textShadow: shadows.length ? shadows.join(", ") : undefined,
    opacity: style.opacity ?? 1,
    background: style.box ? rgba(style.box_color, style.box_opacity) : undefined,
    padding: style.box ? `${0.12 * px}px ${0.35 * px}px` : undefined,
    borderRadius: style.box ? 0.15 * px : undefined,
    boxDecorationBreak: "clone",
    WebkitBoxDecorationBreak: "clone",
  };
}

/** Anchor a free {x,y} like the renderer: left/right thirds hug that edge. */
export function posStyle(pos: Pos, margin: number): React.CSSProperties {
  const x = pos.x * 100;
  const y = `${pos.y * 100}%`;
  if (pos.x < 0.38) return { left: `max(${margin}px, ${x}%)`, top: y, transform: "translateY(-50%)", textAlign: "left" };
  if (pos.x > 0.62) return { right: `max(${margin}px, ${100 - x}%)`, top: y, transform: "translateY(-50%)", textAlign: "right" };
  return { left: `${x}%`, top: y, transform: "translate(-50%, -50%)", textAlign: "center" };
}

function rgbaHex(hex: string, a: number) {
  const n = parseInt(hex.replace("#", ""), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

/** The hook title, laid out exactly like the export (captions.title_events): one line per row,
 * the design's defaults plus every override from the editor. */
export function TitleCard({
  ov,
  scale,
  age = 1,
}: {
  ov: Partial<Overlay> & { text: string };
  scale: number;
  age?: number;
}) {
  const spec = resolveTitle(ov as Partial<Overlay> & Record<string, unknown>);
  const lines = titleLines(ov.text, spec);
  const colors = wordColors(lines, spec);
  const dur = Math.max(0.3, (ov.end ?? 3) - (ov.start ?? 0));
  const fs = spec.size * scale;
  const lineH = fs * spec.line_spacing;
  // entrance / exit
  let k = 1;
  let op = 1;
  let dy = 0;
  const a = spec.animation;
  const exit = a === "fade" || a === "slide_up" ? Math.min(1, (dur - age) / 0.25) : a === "typewriter" ? Math.min(1, (dur - age) / 0.2) : a === "none" ? 1 : Math.min(1, (dur - age) / 0.22);
  if (a === "pop") k = age < 0.17 ? 1.22 * (age / 0.17) : age < 0.3 ? 1.22 - 0.22 * ((age - 0.17) / 0.13) : 1;
  if (a === "slam") {
    k = age < 0.14 ? 1.6 - 0.64 * (age / 0.14) : age < 0.24 ? 0.96 + 0.04 * ((age - 0.14) / 0.1) : 1;
    op = Math.min(1, age / 0.14);
  }
  if (a === "fade") op = Math.min(1, age / 0.25);
  if (a === "slide_up") {
    op = Math.min(1, age / 0.2);
    dy = 56 * scale * Math.max(0, 1 - age / 0.26);
  }
  if (a === "flicker") op = age < 0.06 ? age / 0.06 : age < 0.11 ? 0.44 : age < 0.19 ? 0.44 + 0.56 * ((age - 0.11) / 0.08) : 1;
  op *= Math.max(0, exit);
  const shadows: string[] = [];
  if (spec.shadow) shadows.push(`${spec.shadow * scale}px ${spec.shadow * scale}px 0 ${spec.box ? "rgba(0,0,0,.38)" : spec.shadow_color}`);
  if (spec.glow && !spec.box) {
    const g = spec.glow * scale;
    shadows.push(`0 0 ${g * 0.5}px ${spec.glow_color}`, `0 0 ${g}px ${spec.glow_color}`, `0 0 ${g * 2}px ${spec.glow_color}`);
  }
  let wi = 0;
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: spec.align === "left" ? "flex-start" : spec.align === "right" ? "flex-end" : "center",
        transform: `translateY(${dy}px) rotate(${spec.rotation}deg) scale(${Math.max(0, k)})`,
        opacity: op,
        whiteSpace: "pre",
      }}
    >
      {lines.map((line, li) => (
        <div key={li} style={{ height: lineH, display: "flex", alignItems: "center" }}>
          <span
            style={{
              fontFamily: `"HS ${spec.font}", sans-serif`,
              fontSize: fs / (EM_RATIO[spec.font] ?? 1.5),
              lineHeight: 1,
              color: spec.color,
              letterSpacing: spec.letter_spacing * scale,
              WebkitTextStroke: !spec.box && spec.outline ? `${spec.outline * 2 * scale}px ${spec.outline_color}` : undefined,
              paintOrder: "stroke fill",
              textShadow: shadows.length ? shadows.join(", ") : undefined,
              background: spec.box ? rgbaHex(spec.box_color, spec.box_opacity) : undefined,
              padding: spec.box ? `${spec.box_pad * scale}px` : undefined,
            }}
          >
            {line.split(" ").map((w, j, arr) => {
              const idx = wi++;
              const hidden = a === "typewriter" && age < Math.min(dur * 0.6, idx * 0.11);
              return (
                <span key={j} style={{ color: colors[idx], visibility: hidden ? "hidden" : undefined }}>
                  {w}
                  {j < arr.length - 1 ? " " : ""}
                </span>
              );
            })}
          </span>
        </div>
      ))}
    </div>
  );
}

/** Where the title block sits: pos is the anchor (centre / left edge / right edge by alignment). */
export function titleAnchorStyle(ov: Partial<Overlay>, seam?: number | null): React.CSSProperties {
  const spec = resolveTitle(ov as Partial<Overlay> & Record<string, unknown>);
  const dx = spec.align === "left" ? 0.07 : spec.align === "right" ? 0.93 : 0.5;
  const x = ov.pos?.x ?? dx;
  const y = ov.pos?.y ?? (seam == null ? 0.2 : seam > 0.3 ? seam - 0.11 : seam + 0.11); // mirrors title_events
  const tx = spec.align === "left" ? "0" : spec.align === "right" ? "-100%" : "-50%";
  return { left: `${x * 100}%`, top: `${y * 100}%`, transform: `translate(${tx}, -50%)` };
}

/** Static sample for the style picker ("Hey there," with the active word highlighted). */
export function CaptionSample({ style, scale = 0.24, effect = "none" }: { style: CaptionStyle; scale?: number; effect?: Effect }) {
  const words = ["Hey", "there,"];
  return (
    <span style={{ ...textStyle(style, scale, effect), textAlign: "center" }} className="whitespace-nowrap">
      {words.map((w, i) => (
        <span key={i} style={{ color: i === 0 && style.animation !== "none" && style.animation !== "fade" ? style.highlight : undefined }}>
          {style.uppercase ? w.toUpperCase() : w}
          {i < words.length - 1 ? " " : ""}
        </span>
      ))}
    </span>
  );
}

/** Drag inside the preview frame; snaps to the centre lines. */
function startDrag(e: React.PointerEvent<HTMLDivElement>, onMove: (p: Pos) => void) {
  const frame = (e.currentTarget.parentElement as HTMLElement).getBoundingClientRect();
  const el = e.currentTarget;
  el.setPointerCapture(e.pointerId);
  const box = el.getBoundingClientRect();
  // offset between the pointer and the block's anchor
  const ax = el.style.transform.includes("-100%") ? box.right : el.style.transform.includes("translate(0") ? box.left : box.left + box.width / 2;
  const offX = e.clientX - ax;
  const offY = e.clientY - (box.top + box.height / 2);
  const move = (ev: PointerEvent) => {
    let x = (ev.clientX - offX - frame.left) / frame.width;
    let y = (ev.clientY - offY - frame.top) / frame.height;
    if (Math.abs(x - 0.5) < 0.025) x = 0.5;
    if (Math.abs(y - 0.5) < 0.02) y = 0.5;
    onMove({ x: +Math.min(1, Math.max(0, x)).toFixed(3), y: +Math.min(0.97, Math.max(0.03, y)).toFixed(3) });
  };
  const up = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", up);
  e.preventDefault();
}

/** Live caption + overlay layer drawn over the preview at time t (seconds, clip-relative). */
export function CaptionOverlay({
  chunks,
  style,
  t,
  width,
  keywords,
  overlays,
  enabled,
  transition = "none",
  effect = "none",
  progressBar,
  duration,
  seam,
  labels,
  progressPos = "bottom",
  onCaptionMove,
  onTitleMove,
  forceTitle = false,
}: {
  chunks: Chunk[];
  style: CaptionStyle;
  t: number;
  width: number;
  keywords?: string[];
  overlays?: Overlay[];
  enabled: boolean;
  transition?: Transition;
  effect?: Effect;
  progressBar?: string | null;
  duration?: number;
  seam?: number | null;
  labels?: { top?: string; bottom?: string; enabled?: boolean } | null;
  progressPos?: "top" | "bottom";
  /** When set, the captions can be dragged (sets style.pos). */
  onCaptionMove?: (p: Pos) => void;
  /** When set, the title can be dragged; called with the new {x, y} (0-1). */
  onTitleMove?: (p: Pos) => void;
  /** Show the title even outside its time window (while editing it). */
  forceTitle?: boolean;
}) {
  const scale = width / 1080;
  const chunk = enabled ? chunks.find((c) => t >= c.s && t < Math.max(c.e, c.s + 0.2)) : undefined;
  const kw = new Set((keywords ?? []).map((k) => k.toLowerCase()));
  const onSeam = seam != null && style.position !== "top";
  const pos = onSeam ? { top: `${seam * 100}%`, center: true } : POS[style.position] ?? POS.bottom;
  const ts = textStyle(style, scale, effect);
  const chunkIndex = chunk ? chunks.indexOf(chunk) : -1;
  const titleOv = (overlays ?? []).filter((o) => o.kind === "title" && o.text && (forceTitle || (t >= (o.start ?? 0) && t < (o.end ?? 1e9))));
  const marks = (overlays ?? []).filter((o) => o.kind === "watermark" && o.text);

  let content: React.ReactNode = null;
  if (chunk) {
    const words = chunk.words?.length ? chunk.words : [{ w: chunk.text, s: chunk.s, e: chunk.e }];
    const active = words.findIndex((w, i) => t >= (i === 0 ? chunk.s : w.s) && t < (words[i + 1]?.s ?? Math.max(chunk.e, chunk.s + 0.2)));
    content = words.map((w, i) => {
      const isKw = style.emphasis && kw.has(w.w.toLowerCase().replace(/[^a-z0-9]/g, ""));
      let color: string | undefined = isKw ? style.emphasis_color : undefined;
      let transform: string | undefined;
      let fill = 0; // karaoke: fraction of the word already sung
      if (style.animation === "karaoke") {
        const end = words[i + 1]?.s ?? chunk.e;
        fill = t <= w.s ? 0 : t >= end ? 1 : (t - w.s) / Math.max(0.01, end - w.s);
        color = fill >= 1 ? style.highlight : undefined;
      } else if ((style.animation === "highlight" || style.animation === "pop") && i === active) {
        color = style.highlight;
        if (style.animation === "pop") transform = "scale(1.1)";
      }
      const hidden = effect === "typewriter" && i > Math.max(0, active);
      return (
        <span key={i}>
          <span style={{ color, display: "inline-block", transform, position: "relative", visibility: hidden ? "hidden" : undefined }}>
            {w.w}
            {fill > 0 && fill < 1 && (
              // Highlight copy clipped to the sung part (keeps the outline intact, like libass \kf).
              <span style={{ position: "absolute", left: 0, top: 0, color: style.highlight, clipPath: `inset(0 ${(1 - fill) * 100}% 0 0)` }}>
                {w.w}
              </span>
            )}
          </span>
          {i < words.length - 1 ? " " : ""}
        </span>
      );
    });
  }

  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
      {labels?.enabled !== false &&
        (["top", "bottom"] as const).map((k) =>
          labels?.[k] ? (
            <span
              key={k}
              className="absolute"
              style={{
                left: 34 * scale,
                top: (k === "top" ? 0 : (seam ?? 0.5) * (width * 16) / 9) + 34 * scale,
                fontFamily: '"HS Poppins ExtraBold", sans-serif',
                fontSize: (44 * scale) / 1.762,
                lineHeight: 1.3,
                color: "#fff",
                background: "rgba(11,15,20,0.85)",
                padding: `${6 * scale}px ${14 * scale}px`,
                textTransform: "uppercase",
              }}
            >
              {labels[k]}
            </span>
          ) : null,
        )}
      {progressBar && duration ? (
        <div className={progressPos === "top" ? "absolute top-0 left-0" : "absolute bottom-0 left-0"} style={{ height: Math.max(3, 10 * scale), width: `${Math.min(100, (t / duration) * 100)}%`, background: progressBar }} />
      ) : null}
      {titleOv.map((o, i) => (
        <div
          key={i}
          className={cx("absolute", onTitleMove && "pointer-events-auto cursor-move rounded outline-dashed outline-2 outline-transparent hover:outline-white/70")}
          style={titleAnchorStyle(o, seam)}
          onPointerDown={onTitleMove ? (e) => startDrag(e, onTitleMove) : undefined}
          title={onTitleMove ? "Drag to move the title" : undefined}
        >
          <TitleCard
            ov={o}
            scale={scale}
            age={forceTitle ? 0.4 : t - (o.start ?? 0)} /* while editing: always fully in */
          />
        </div>
      ))}
      {marks.map((o, i) => (
        <div
          key={`m${i}`}
          className="absolute"
          style={{
            top: 40 * scale,
            right: 40 * scale,
            fontFamily: '"HS Poppins SemiBold", sans-serif',
            fontSize: (34 * scale) / 1.762,
            color: "rgba(255,255,255,0.65)",
            WebkitTextStroke: `${3 * scale}px rgba(0,0,0,0.5)`,
            paintOrder: "stroke fill",
          }}
        >
          {o.text}
        </div>
      ))}
      {content && style.pos && (
        <div
          className={cx("absolute", onCaptionMove && "pointer-events-auto cursor-move rounded outline-dashed outline-2 outline-transparent hover:outline-white/70")}
          style={{ ...posStyle(style.pos, 56 * scale), maxWidth: "88%" }}
          onPointerDown={onCaptionMove ? (e) => startDrag(e, onCaptionMove) : undefined}
          title={onCaptionMove ? "Drag to move the captions" : undefined}
        >
          <span key={chunkIndex} style={{ ...ts, display: "inline-block", rotate: style.rotation && effect !== "tilt" ? `${style.rotation}deg` : undefined }}>
            {content}
          </span>
        </div>
      )}
      {content && !style.pos && (
        <div
          className={cx("absolute inset-x-0 flex justify-center text-center", onCaptionMove && "pointer-events-auto cursor-move")}
          onPointerDown={
            onCaptionMove
              ? (e) => {
                  // first drag of a preset position: switch to a free position at the pointer
                  const r = (e.currentTarget.parentElement as HTMLElement).getBoundingClientRect();
                  onCaptionMove({ x: 0.5, y: +((e.clientY - r.top) / r.height).toFixed(3) });
                }
              : undefined
          }
          style={{
            top: onSeam ? pos.top : pos.center ? "50%" : pos.top,
            bottom: pos.bottom,
            transform: pos.center ? "translateY(-50%)" : undefined,
            padding: `0 ${70 * scale}px`,
          }}
        >
          <span
            key={chunkIndex}
            style={{
              ...ts,
              display: "inline-block",
              opacity: (style.opacity ?? 1) * (style.animation === "fade" && chunk ? Math.min(1, (t - chunk.s) / 0.18, (chunk.e - t) / 0.18) : 1),
              rotate: effect === "tilt" ? `${[-3, 2.5, -2, 3][chunkIndex % 4]}deg` : style.rotation ? `${style.rotation}deg` : undefined,
              ["--cap-d" as string]: `${46 * scale}px`,
              animation: transition !== "none" ? `cap-${transition} ${transition === "bounce" ? 220 : 170}ms ease-out` : undefined,
            }}
          >
            {content}
          </span>
        </div>
      )}
    </div>
  );
}
