"use client";

import type { CaptionStyle, Chunk, Overlay } from "@/lib/types";

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

export function textStyle(style: CaptionStyle, scale: number): React.CSSProperties {
  const px = (style.size * (style.size_scale ?? 1) * scale) / (EM_RATIO[style.font] ?? 1.5);
  const outline = style.box ? 0 : style.outline * scale;
  return {
    fontFamily: `"HS ${style.font}", sans-serif`,
    fontSize: px,
    lineHeight: 1.15,
    color: style.color,
    textTransform: style.uppercase ? "uppercase" : "none",
    WebkitTextStroke: outline ? `${outline * 2}px ${style.outline_color}` : undefined,
    paintOrder: "stroke fill",
    textShadow: style.shadow ? `${style.shadow * scale}px ${style.shadow * scale}px 0 rgba(0,0,0,0.6)` : undefined,
    background: style.box ? rgba(style.box_color, style.box_opacity) : undefined,
    padding: style.box ? `${0.12 * px}px ${0.35 * px}px` : undefined,
    borderRadius: style.box ? 0.15 * px : undefined,
    boxDecorationBreak: "clone",
    WebkitBoxDecorationBreak: "clone",
  };
}

/** Static sample for the style picker. */
export function CaptionSample({ style }: { style: CaptionStyle }) {
  const words = ["FIND", "THE", "HYPE"];
  return (
    <span style={{ ...textStyle(style, 0.24), textAlign: "center" }} className="whitespace-nowrap">
      {words.map((w, i) => (
        <span key={i} style={{ color: i === 1 && style.animation !== "none" && style.animation !== "fade" ? style.highlight : undefined }}>
          {style.uppercase ? w : w.toLowerCase()}
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
}: {
  chunks: Chunk[];
  style: CaptionStyle;
  t: number;
  width: number;
  keywords?: string[];
  overlays?: Overlay[];
  enabled: boolean;
}) {
  const scale = width / 1080;
  const chunk = enabled ? chunks.find((c) => t >= c.s && t < Math.max(c.e, c.s + 0.2)) : undefined;
  const kw = new Set((keywords ?? []).map((k) => k.toLowerCase()));
  const pos = POS[style.position] ?? POS.bottom;
  const ts = textStyle(style, scale);
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
      return (
        <span key={i}>
          <span style={{ color, display: "inline-block", transform, position: "relative" }}>
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
      {titleOv.map((o, i) => (
        <div key={i} className="absolute inset-x-0 flex justify-center" style={{ top: "7%", padding: `0 ${80 * scale}px` }}>
          <span
            style={{
              fontFamily: '"HS Poppins ExtraBold", sans-serif',
              fontSize: (64 * scale) / 1.762,
              color: o.color ?? "#fff",
              background: o.bg ?? "#7C3AED",
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
            top: pos.center ? "50%" : pos.top,
            bottom: pos.bottom,
            transform: pos.center ? "translateY(-50%)" : undefined,
            padding: `0 ${70 * scale}px`,
          }}
        >
          <span
            style={{
              ...ts,
              opacity: style.animation === "fade" && chunk ? Math.min(1, (t - chunk.s) / 0.18, (chunk.e - t) / 0.18) : 1,
            }}
          >
            {content}
          </span>
        </div>
      )}
    </div>
  );
}
