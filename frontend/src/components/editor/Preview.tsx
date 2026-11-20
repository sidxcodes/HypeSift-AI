"use client";

import { Pause, Play, RotateCcw, Volume2, VolumeX } from "lucide-react";
import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import { fmtTime } from "@/lib/api";
import type { CaptionStyle, Chunk, Edits, Reframe } from "@/lib/types";
import { facecamLayout, type PanelAdj } from "@/lib/layout";
import { CaptionOverlay } from "../CaptionPreview";

const ASPECTS: Record<string, [number, number]> = { "9:16": [1080, 1920], "1:1": [1080, 1080], "4:5": [1080, 1350], "16:9": [1920, 1080] };

export type PreviewHandle = { seek: (absT: number) => void; play: () => void; pause: () => void };

function interp(path: [number, number, number][], t: number, idx: 1 | 2): number {
  if (!path.length) return 0.5;
  if (t <= path[0][0]) return path[0][idx];
  for (let i = 0; i + 1 < path.length; i++) {
    const [t0] = path[i];
    const [t1] = path[i + 1];
    if (t < t1) {
      if (t1 - t0 < 1e-3) return path[i][idx];
      return path[i][idx] + ((path[i + 1][idx] - path[i][idx]) * (t - t0)) / (t1 - t0);
    }
  }
  return path[path.length - 1][idx];
}

function cropBox(sw: number, sh: number, target: number, zoom: number) {
  if (sw / sh > target) {
    const ch = sh / zoom;
    return [ch * target, ch];
  }
  const cw = sw / zoom;
  return [cw, cw / target];
}

type Props = {
  src: string;
  start: number;
  end: number;
  edits: Edits;
  reframe: Reframe;
  chunks: Chunk[];
  style: CaptionStyle;
  onTime: (absT: number) => void;
  onCropDrag?: (x: number, y: number) => void;
  /** Text tool open: keep the title visible and let it be dragged. */
  onTitleMove?: (p: { x: number; y: number }) => void;
  /** Format tool on a gameplay clip: drag the cam / game panel to pan it. */
  onLayoutDrag?: (panel: "cam" | "game", adj: PanelAdj) => void;
};

export const Preview = forwardRef<PreviewHandle, Props>(function Preview(
  { src, start, end, edits, reframe, chunks, style, onTime, onCropDrag, onTitleMove, onLayoutDrag },
  ref,
) {
  const video = useRef<HTMLVideoElement>(null);
  const videoB = useRef<HTMLVideoElement>(null); // second moment for "pair" comparison clips
  const canvas = useRef<HTMLCanvasElement>(null);
  const wrap = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 300, h: 533 });
  const [t, setT] = useState(start);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(false);
  const [ready, setReady] = useState(false);
  const drag = useRef<{ x: number; y: number; cx: number; cy: number } | null>(null);
  const panelDrag = useRef<{ panel: "cam" | "game"; x: number; y: number; adj: PanelAdj; rect: number[]; ph: number } | null>(null);
  const live = useRef({ start, end, edits, reframe });
  live.current = { start, end, edits, reframe };

  const [OW, OH] = ASPECTS[edits.aspect] ?? ASPECTS["9:16"];

  useImperativeHandle(ref, () => ({
    seek: (abs: number) => {
      if (video.current) video.current.currentTime = abs;
    },
    play: () => video.current?.play(),
    pause: () => video.current?.pause(),
  }));

  // Fit the output frame inside the available area.
  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      const maxW = el.clientWidth;
      const maxH = Math.max(320, el.clientHeight);
      const ratio = OW / OH;
      let w = maxW;
      let h = w / ratio;
      if (h > maxH) {
        h = maxH;
        w = h * ratio;
      }
      setSize({ w: Math.floor(w), h: Math.floor(h) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [OW, OH]);

  const draw = useCallback(() => {
    const v = video.current;
    const c = canvas.current;
    if (!v || !c || !v.videoWidth) return;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    const { edits: e, reframe: rf } = live.current;
    const W = c.width;
    const H = c.height;
    const sw = v.videoWidth;
    const sh = v.videoHeight;
    ctx.filter = "none";
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, W, H);
    const mode = e.crop.mode;
    const cover = (el: HTMLVideoElement, x: number, y: number, w: number, h: number, dy: number, dh: number) => {
      const s = Math.max(W / w, dh / h);
      const vw = W / s;
      const vh = dh / s;
      ctx.drawImage(el, x + (w - vw) / 2, y + (h - vh) / 2, vw, vh, 0, dy, W, dh);
    };
    if ((mode === "compare" || mode === "pair") && (e.aspect === "9:16" || e.aspect === "4:5")) {
      const hh = Math.round(H / 2);
      if (mode === "pair" && e.pair) {
        cover(v, 0, 0, sw, sh, 0, hh);
        const b = videoB.current;
        if (b && b.readyState >= 2) {
          const want = e.pair.b_start + (v.currentTime - live.current.start);
          if (Math.abs(b.currentTime - want) > 0.3) b.currentTime = want;
          cover(b, 0, 0, sw, sh, hh, H - hh);
        }
      } else {
        const half = sw / 2;
        const [first, second] = e.compare?.swap ? [half + 2, 0] : [0, half + 2];
        cover(v, first, 0, half - 2, sh, 0, hh);
        cover(v, second, 0, half - 2, sh, hh, H - hh);
      }
      ctx.fillStyle = "rgba(11,15,20,0.9)";
      ctx.fillRect(0, hh - 2, W, 4);
      return;
    }
    if (mode === "fit") {
      const cover = Math.max(W / sw, H / sh);
      ctx.filter = "blur(18px) brightness(0.9)";
      ctx.drawImage(v, (W - sw * cover) / 2, (H - sh * cover) / 2, sw * cover, sh * cover);
      ctx.filter = "none";
      const fit = Math.min(W / sw, H / sh);
      ctx.drawImage(v, (W - sw * fit) / 2, (H - sh * fit) / 2, sw * fit, sh * fit);
      return;
    }
    if (mode === "facecam" && (rf.facecam || e.layout) && (e.aspect === "9:16" || e.aspect === "4:5")) {
      // gameplay layout: webcam panel + game panel (both adjustable in Format)
      const L = facecamLayout(sw, sh, W, H, rf.facecam?.box, e.layout);
      const camY = L.swap ? L.gameH : 0;
      const gameY = L.swap ? 0 : L.camH;
      ctx.drawImage(v, ...L.camRect, 0, camY, W, L.camH);
      ctx.drawImage(v, ...L.gameRect, 0, gameY, W, L.gameH);
      return;
    }
    if (mode === "split" && rf.split && e.aspect === "9:16") {
      const halfH = H / 2;
      const [cw, ch] = cropBox(sw, sh, W / halfH, 1);
      const y = (sh - ch) / 2;
      [rf.split.left, rf.split.right].forEach((cx, i) => {
        const x = Math.min(Math.max(cx * sw - cw / 2, 0), sw - cw);
        ctx.drawImage(v, x, y, cw, ch, 0, i * halfH, W, halfH);
      });
      return;
    }
    const zoom = Math.max(1, e.crop.zoom || 1);
    const [cw, ch] = cropBox(sw, sh, W / H, zoom);
    let cx = 0.5;
    let cy = 0.5;
    if (mode === "manual") {
      cx = e.crop.x;
      cy = e.crop.y;
    } else if (mode === "auto" && rf.path?.length) {
      const base = rf.range?.[0] ?? live.current.start;
      const rel = v.currentTime - base;
      cx = interp(rf.path, rel, 1);
      cy = interp(rf.path, rel, 2);
    }
    const x = Math.min(Math.max(cx * sw - cw / 2, 0), Math.max(0, sw - cw));
    const y = Math.min(Math.max(cy * sh - ch / 2, 0), Math.max(0, sh - ch));
    ctx.drawImage(v, x, y, cw, ch, 0, 0, W, H);
  }, []);

  // Render loop while playing; single redraws otherwise.
  useEffect(() => {
    let raf = 0;
    const loop = () => {
      const v = video.current;
      if (v) {
        if (v.currentTime >= live.current.end) {
          v.currentTime = live.current.start;
        }
        setT(v.currentTime);
        onTime(v.currentTime);
      }
      draw();
      raf = requestAnimationFrame(loop);
    };
    if (playing) raf = requestAnimationFrame(loop);
    else draw();
    return () => cancelAnimationFrame(raf);
  }, [playing, draw, onTime, edits, reframe, size]);

  useEffect(() => {
    const v = video.current;
    if (v && ready && (v.currentTime < start || v.currentTime > end)) v.currentTime = start;
  }, [start, end, ready]);

  const toggle = () => {
    const v = video.current;
    if (!v) return;
    if (v.paused) {
      if (v.currentTime < start || v.currentTime >= end - 0.05) v.currentTime = start;
      v.play();
    } else v.pause();
  };

  const gameplay = edits.crop.mode === "facecam" && (reframe.facecam || edits.layout) && (edits.aspect === "9:16" || edits.aspect === "4:5");
  const onPointerDown = (e: React.PointerEvent) => {
    const v = video.current;
    if (gameplay && onLayoutDrag && v?.videoWidth) {
      const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
      const L = facecamLayout(v.videoWidth, v.videoHeight, size.w, size.h, reframe.facecam?.box, edits.layout);
      const yFrac = (e.clientY - r.top) / r.height;
      const inCam = L.swap ? yFrac > 1 - L.split : yFrac < L.split;
      const panel = inCam ? "cam" : "game";
      panelDrag.current = {
        panel,
        x: e.clientX,
        y: e.clientY,
        adj: inCam ? L.cam : L.game,
        rect: [v.videoWidth, v.videoHeight, ...(inCam ? L.camRect : L.gameRect).slice(2)],
        ph: inCam ? L.camH : L.gameH,
      };
      (e.target as HTMLElement).setPointerCapture(e.pointerId);
      return;
    }
    if (edits.crop.mode !== "manual" || !onCropDrag) return;
    drag.current = { x: e.clientX, y: e.clientY, cx: edits.crop.x, cy: edits.crop.y };
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const pd = panelDrag.current;
    if (pd && onLayoutDrag) {
      const [sw, sh, cw, ch] = pd.rect;
      // dragging right shows more of the left: move the crop the other way, in source units
      const x = pd.adj.x - ((e.clientX - pd.x) / size.w) * (cw / sw);
      const y = pd.adj.y - ((e.clientY - pd.y) / pd.ph) * (ch / sh);
      onLayoutDrag(pd.panel, { ...pd.adj, x: +Math.min(1, Math.max(0, x)).toFixed(4), y: +Math.min(1, Math.max(0, y)).toFixed(4) });
      return;
    }
    if (!drag.current || !onCropDrag) return;
    const dx = (e.clientX - drag.current.x) / size.w;
    const dy = (e.clientY - drag.current.y) / size.h;
    onCropDrag(Math.min(1, Math.max(0, drag.current.cx - dx * 0.5)), Math.min(1, Math.max(0, drag.current.cy - dy * 0.5)));
  };

  return (
    <div className="flex h-full flex-col">
      <div ref={wrap} className="relative flex min-h-0 flex-1 items-center justify-center">
        <div className="relative overflow-hidden rounded-xl bg-black shadow-card" style={{ width: size.w, height: size.h }}>
          <canvas
            ref={canvas}
            width={Math.round(size.w * 1.5)}
            height={Math.round(size.h * 1.5)}
            style={{ width: size.w, height: size.h, cursor: edits.crop.mode === "manual" || (gameplay && onLayoutDrag) ? "grab" : "default" }}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={() => {
              drag.current = null;
              panelDrag.current = null;
            }}
            onClick={edits.crop.mode === "manual" || (gameplay && onLayoutDrag) ? undefined : toggle}
          />
          <CaptionOverlay
            chunks={chunks}
            style={style}
            t={t - start}
            width={size.w}
            keywords={edits.captions.keywords}
            overlays={edits.overlays}
            enabled={edits.captions.enabled}
            transition={edits.captions.transition}
            effect={edits.captions.effect}
            progressBar={edits.progress_bar?.enabled ? edits.progress_bar.color ?? "#FF7A59" : null}
            progressPos={(edits.progress_bar as { position?: "top" | "bottom" } | undefined)?.position ?? "bottom"}
            onTitleMove={onTitleMove}
            forceTitle={!!onTitleMove}
            duration={end - start}
            labels={edits.crop.mode === "compare" || edits.crop.mode === "pair" ? edits.labels : null}
            seam={
              edits.crop.mode === "compare" || edits.crop.mode === "pair"
                ? 0.5
                :
              gameplay
                ? facecamLayout(16, 9, 9, 16, reframe.facecam?.box, edits.layout).seam
                : edits.crop.mode === "split" && reframe.split && edits.aspect === "9:16"
                  ? 0.5
                  : null
            }
          />
          {edits.crop.mode === "pair" && edits.pair && (
            <video ref={videoB} src={src} className="hidden" preload="auto" muted playsInline onLoadedMetadata={(e) => (e.currentTarget.currentTime = edits.pair!.b_start)} />
          )}
          {!ready && <div className="absolute inset-0 grid place-items-center text-sm text-white/70">Loading source…</div>}
        </div>
        <video
          ref={video}
          src={src}
          className="hidden"
          preload="auto"
          muted={muted}
          playsInline
          onLoadedMetadata={(e) => {
            e.currentTarget.currentTime = start;
            setReady(true);
          }}
          onSeeked={() => {
            setT(video.current?.currentTime ?? start);
            draw();
          }}
          onTimeUpdate={(e) => {
            // Fallback for when requestAnimationFrame is throttled (background tab / hidden pane).
            const v = e.currentTarget;
            if (v.currentTime >= live.current.end) v.currentTime = live.current.start;
            setT(v.currentTime);
            onTime(v.currentTime);
            draw();
          }}
          onPlay={() => {
            setPlaying(true);
            videoB.current?.play().catch(() => {});
          }}
          onPause={() => {
            setPlaying(false);
            videoB.current?.pause();
          }}
        />
      </div>
      <div className="mt-3 flex items-center justify-center gap-3">
        <button
          onClick={() => {
            if (video.current) video.current.currentTime = start;
          }}
          className="grid size-9 place-items-center rounded-xl text-muted hover:bg-surface-2 hover:text-text cursor-pointer"
          aria-label="Back to clip start"
        >
          <RotateCcw className="size-4" />
        </button>
        <button onClick={toggle} className="grid size-11 place-items-center rounded-full bg-primary text-on-primary shadow cursor-pointer" aria-label={playing ? "Pause" : "Play"}>
          {playing ? <Pause className="size-5" fill="currentColor" /> : <Play className="size-5 translate-x-0.5" fill="currentColor" />}
        </button>
        <button onClick={() => setMuted((m) => !m)} className="grid size-9 place-items-center rounded-xl text-muted hover:bg-surface-2 hover:text-text cursor-pointer" aria-label={muted ? "Unmute" : "Mute"}>
          {muted ? <VolumeX className="size-4" /> : <Volume2 className="size-4" />}
        </button>
        <span className="w-24 text-sm tabular-nums text-muted">
          {fmtTime(Math.max(0, t - start))} / {fmtTime(end - start)}
        </span>
      </div>
    </div>
  );
});
