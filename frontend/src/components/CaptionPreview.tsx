"use client";

import type { CaptionStyle, Chunk, Effect, Overlay, Transition } from "@/lib/types";

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
  if (style.shadow) shadows.push(`${style.shadow * scale}px ${style.shadow * scale}px 0 rgba(0,0,0,0.6)`);
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
}) {
  const scale = width / 1080;
  const chunk = enabled ? chunks.find((c) => t >= c.s && t < Math.max(c.e, c.s + 0.2)) : undefined;
  const kw = new Set((keywords ?? []).map((k) => k.toLowerCase()));
  const onSeam = seam != null && style.position !== "top";
  const pos = onSeam ? { top: `${seam * 100}%`, center: true } : POS[style.position] ?? POS.bottom;
  const ts = textStyle(style, scale, effect);
  const chunkIndex = chunk ? chunks.indexOf(chunk) : -1;
  const titleOv = (overlays ?? []).filter((o) => o.kind === "title" && o.text && t >= (o.start ?? 0) && t < (o.end ?? 1e9));
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
      {progressBar && duration ? (
        <div className="absolute bottom-0 left-0" style={{ height: Math.max(3, 10 * scale), width: `${Math.min(100, (t / duration) * 100)}%`, background: progressBar }} />
      ) : null}
      {titleOv.map((o, i) => (
        <div key={i} className="absolute inset-x-0 flex justify-center" style={{ top: "7%", padding: `0 ${80 * scale}px` }}>
          <span
            style={{
              fontFamily: '"HS Poppins ExtraBold", sans-serif',
              fontSize: (64 * scale) / 1.762,
              color: o.color ?? "#0B0F14",
              background: o.bg ?? "#C6F432",
              padding: `${6 * scale}px ${16 * scale}px`,
              lineHeight: 1.25,
              textAlign: "center",
              boxDecorationBreak: "clone",
              WebkitBoxDecorationBreak: "clone",
            }}
          >
            {o.text}
          </span>
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
      {content && (
        <div
          className="absolute inset-x-0 flex justify-center text-center"
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
              rotate: effect === "tilt" ? `${[-3, 2.5, -2, 3][chunkIndex % 4]}deg` : undefined,
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
