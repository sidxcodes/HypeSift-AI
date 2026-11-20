"use client";

import type { CaptionStyle, Chunk, Effect, Overlay, Pos, TitleStyle, Transition } from "@/lib/types";

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

const ACCENTS = ["#FFD60A", "#FF3B30", "#34C759", "#3FA9FF"];
const STOP = new Set(
  "a an the and or but so to of in on at for with is are was were be been it its this that i you he she we they my your our their me him her us them do does did have has had not no just very really what how why when who where which than then there here about from into over out up down as by if".split(" "),
);

/** Which words the impact title colours: numbers and long words (mirrors captions.py _key_words). */
function keyIdx(words: string[]): Set<number> {
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
  return new Set([...pick].sort((a, b) => a - b).slice(0, 3));
}

/** Anchor a free {x,y} like the renderer: left/right thirds hug that edge. */
export function posStyle(pos: Pos, margin: number): React.CSSProperties {
  const x = pos.x * 100;
  const y = `${pos.y * 100}%`;
  if (pos.x < 0.38) return { left: `max(${margin}px, ${x}%)`, top: y, transform: "translateY(-50%)", textAlign: "left" };
  if (pos.x > 0.62) return { right: `max(${margin}px, ${100 - x}%)`, top: y, transform: "translateY(-50%)", textAlign: "right" };
  return { left: `${x}%`, top: y, transform: "translate(-50%, -50%)", textAlign: "center" };
}

/** The hook title card, drawn like the export (impact / box / neon / minimal). */
export function TitleCard({ text, design = "impact", scale, age = 1, accent }: { text: string; design?: TitleStyle; scale: number; age?: number; accent?: string }) {
  const pop = Math.min(1, age / 0.3);
  if (design === "impact") {
    const words = text.toUpperCase().split(/\s+/);
    const keys = keyIdx(words);
    let ci = 0;
    const s = age < 0.17 ? 1.22 * (age / 0.17) : age < 0.3 ? 1.22 - 0.22 * ((age - 0.17) / 0.13) : 1;
    return (
      <span
        style={{
          fontFamily: '"HS Luckiest Guy", sans-serif',
          fontSize: (104 * scale) / 1.226,
          lineHeight: 1.05,
          color: "#fff",
          WebkitTextStroke: `${22 * scale}px #000`,
          paintOrder: "stroke fill",
          textShadow: `${5 * scale}px ${5 * scale}px 0 #000`,
          display: "inline-block",
          transform: `scale(${s}) rotate(${-2 * (1 - pop)}deg)`,
          maxWidth: 820 * scale,
        }}
      >
        {words.map((w, i) => (
          <span key={i} style={{ color: keys.has(i) ? (accent ? [accent, ...ACCENTS] : ACCENTS)[ci++ % 4] : undefined }}>
            {w}
            {i < words.length - 1 ? " " : ""}
          </span>
        ))}
      </span>
    );
  }
  if (design === "box") {
    return (
      <span
        style={{
          fontFamily: '"HS Archivo Black", sans-serif',
          fontSize: (76 * scale) / 1.347,
          lineHeight: 1.3,
          color: "#101010",
          background: accent ?? "#FFD60A",
          padding: `${10 * scale}px ${22 * scale}px`,
          textTransform: "uppercase",
          display: "inline-block",
          boxShadow: `${8 * scale}px ${8 * scale}px 0 rgba(0,0,0,.4)`,
          transform: `rotate(${-2}deg) scale(${age < 0.14 ? 1.6 - 0.64 * (age / 0.14) : 1})`,
          opacity: Math.min(1, age / 0.14),
          maxWidth: 860 * scale,
        }}
      >
        {text}
      </span>
    );
  }
  if (design === "neon") {
    const c = accent ?? "#3FA9FF";
    const flick = age < 0.06 || (age > 0.06 && age < 0.11) ? 0.4 : 1;
    return (
      <span
        style={{
          fontFamily: '"HS Poppins ExtraBold", sans-serif',
          fontSize: (100 * scale) / 1.762,
          lineHeight: 1.15,
          color: "#fff",
          textTransform: "uppercase",
          textShadow: `0 0 ${8 * scale}px ${c}, 0 0 ${22 * scale}px ${c}, 0 0 ${44 * scale}px ${c}`,
          opacity: flick,
          display: "inline-block",
          maxWidth: 860 * scale,
        }}
      >
        {text}
      </span>
    );
  }
  return (
    <span
      style={{
        fontFamily: '"HS Poppins ExtraBold", sans-serif',
        fontSize: (92 * scale) / 1.762,
        lineHeight: 1.3,
        color: "#fff",
        background: "rgba(0,0,0,.69)",
        padding: `${8 * scale}px ${20 * scale}px`,
        display: "inline-block",
        opacity: Math.min(1, age / 0.25),
        maxWidth: 860 * scale,
      }}
    >
      {text}
    </span>
  );
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
  labels,
  progressPos = "bottom",
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
        <div key={i} className="absolute" style={posStyle(o.pos ?? { x: 0.5, y: seam ?? 0.2 }, 50 * scale)}>
          <TitleCard text={o.text} design={o.style ?? "impact"} scale={scale} age={t - (o.start ?? 0)} />
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
        <div className="absolute" style={{ ...posStyle(style.pos, 56 * scale), maxWidth: "88%" }}>
          <span key={chunkIndex} style={{ ...ts, display: "inline-block" }}>
            {content}
          </span>
        </div>
      )}
      {content && !style.pos && (
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
