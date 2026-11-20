"use client";

import {
  ArrowLeft,
  AudioLines,
  Captions,
  Crop,
  Download,
  Loader2,
  Redo2,
  Scissors,
  Send,
  Type,
  Undo2,
} from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Assistant } from "@/components/Assistant";
import { useSession } from "@/components/AppShell";
import { Preview, type PreviewHandle } from "@/components/editor/Preview";
import { Timeline } from "@/components/editor/Timeline";
import { LayoutControls } from "@/components/editor/LayoutControls";
import { TitleEditor } from "@/components/editor/TitleEditor";
import { PublishPanel } from "@/components/PublishPanel";
import { useToast } from "@/components/toast";
import { Badge, Button, Card, cx, Field, Input, Progress, Segmented, Select, Skeleton, Switch } from "@/components/ui";
import { api, fmtTime } from "@/lib/api";
import { chunkWords, retime } from "@/lib/captions";
import type { CaptionLanguage, CaptionStyle, Chunk, ClipDetail, Edits, Job } from "@/lib/types";

const LANG_NAMES: Record<string, string> = { hi: "हिन्दी", ur: "اردو", bn: "বাংলা", ta: "தமிழ்", te: "తెలుగు", mr: "मराठी", gu: "ગુજરાતી", pa: "ਪੰਜਾਬੀ", es: "Español", fr: "Français", de: "Deutsch", pt: "Português", ar: "العربية", ja: "日本語", ko: "한국어", ru: "Русский" };

type State = { start: number; end: number; title: string; edits: Edits; chunks: Chunk[]; chunksEdited: boolean };
type Tool = "trim" | "captions" | "format" | "text" | "audio" | "publish";

const TOOLS: { key: Tool; label: string; icon: typeof Scissors }[] = [
  { key: "trim", label: "Trim", icon: Scissors },
  { key: "captions", label: "Captions", icon: Captions },
  { key: "format", label: "Format", icon: Crop },
  { key: "text", label: "Text", icon: Type },
  { key: "audio", label: "Audio", icon: AudioLines },
  { key: "publish", label: "Publish", icon: Send },
];

const DEFAULT_EDITS: Edits = {
  aspect: "9:16",
  crop: { mode: "auto", x: 0.5, y: 0.5, zoom: 1 },
  captions: { enabled: true, preset: "bold_creator", style: {}, chunks: null },
  overlays: [],
  silence_removal: false,
  audio: { gain_db: 0, normalize: true, fade_in: 0.15, fade_out: 0.4 },
  video: { fade_in: 0, fade_out: 0.25 },
  quality: "standard",
};

export default function EditorPage() {
  const { id } = useParams<{ id: string }>();
  const toast = useToast();
  const { meta } = useSession();
  const [detail, setDetail] = useState<ClipDetail | null>(null);
  const [error, setError] = useState("");
  const [hist, setHist] = useState<{ past: State[]; now: State | null; future: State[] }>({ past: [], now: null, future: [] });
  const [tool, setTool] = useState<Tool>("captions");
  const [time, setTime] = useState(0);
  const [job, setJob] = useState<Job | null>(null);
  const [dirty, setDirty] = useState(false);
  const preview = useRef<PreviewHandle>(null);
  const lastPush = useRef<{ key: string; at: number }>({ key: "", at: 0 });

  const load = useCallback(async () => {
    try {
      const d = await api.clip(id);
      setDetail(d);
      return d;
    } catch (e) {
      setError((e as Error).message);
    }
  }, [id]);

  useEffect(() => {
    load().then((d) => {
      if (!d) return;
      const e: Edits = { ...DEFAULT_EDITS, ...d.clip.edits, captions: { ...DEFAULT_EDITS.captions, ...d.clip.edits.captions } };
      setHist({
        past: [],
        future: [],
        now: { start: d.clip.start, end: d.clip.end, title: d.clip.title, edits: e, chunks: d.chunks, chunksEdited: !!d.clip.edits.captions?.chunks },
      });
      setTime(d.clip.start);
      if (d.job && (d.job.status === "queued" || d.job.status === "running")) setJob(d.job);
    });
  }, [load]);

  // Poll the render job (real status from the worker).
  useEffect(() => {
    if (!job || job.status === "succeeded" || job.status === "failed" || job.status === "cancelled") return;
    const i = setInterval(async () => {
      const j = await api.job(job.id);
      setJob(j);
      if (j.status === "succeeded") {
        toast("success", "Render finished — your clip is ready to download.");
        load();
      } else if (j.status === "failed") toast("error", j.error ?? "Render failed.");
    }, 1000);
    return () => clearInterval(i);
  }, [job, load, toast]);

  const s = hist.now;
  const words = useMemo(() => detail?.words ?? [], [detail]);

  const update = useCallback(
    (patch: Partial<State> | ((st: State) => Partial<State>), key = "misc") => {
      setHist((h) => {
        if (!h.now) return h;
        const p = typeof patch === "function" ? patch(h.now) : patch;
        let next = { ...h.now, ...p };
        // re-derive captions from the transcript when timing or chunking changes (unless hand-edited)
        if (("start" in p || "end" in p || "rechunk" in (p as object)) && !next.chunksEdited) {
          const maxWords = (meta?.caption_presets[next.edits.captions.preset]?.max_words ?? 3) as number;
          const rel = words.filter(([, ws, we]) => we > next.start && ws < next.end).map(([w, ws, we]) => ({ w, s: +(ws - next.start).toFixed(3), e: +(we - next.start).toFixed(3) }));
          next = { ...next, chunks: chunkWords(rel, maxWords) };
        } else if (("start" in p) && next.chunksEdited) {
          const d = h.now.start - next.start;
          next = { ...next, chunks: next.chunks.map((c) => ({ ...c, s: c.s + d, e: c.e + d, words: c.words.map((w) => ({ ...w, s: w.s + d, e: w.e + d })) })).filter((c) => c.e > 0 && c.s < next.end - next.start) };
        }
        const now = Date.now();
        const coalesce = lastPush.current.key === key && now - lastPush.current.at < 700;
        lastPush.current = { key, at: now };
        return { past: coalesce ? h.past : [...h.past.slice(-50), h.now], now: next, future: [] };
      });
      setDirty(true);
    },
    [meta, words],
  );

  const setEdits = (fn: (e: Edits) => Edits, key: string) => update((st) => ({ edits: fn(st.edits) }), key);
  const undo = () => setHist((h) => (h.past.length && h.now ? { past: h.past.slice(0, -1), now: h.past[h.past.length - 1], future: [h.now, ...h.future] } : h));
  const redo = () => setHist((h) => (h.future.length && h.now ? { past: [...h.past, h.now], now: h.future[0], future: h.future.slice(1) } : h));

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
        e.preventDefault();
        if (e.shiftKey) redo();
        else undo();
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y") {
        e.preventDefault();
        redo();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const style: CaptionStyle | null = useMemo(() => {
    if (!s || !meta) return null;
    const base = meta.caption_presets[s.edits.captions.preset] ?? meta.caption_presets.bold_creator;
    return { ...base, ...s.edits.captions.style } as CaptionStyle;
  }, [s, meta]);

  const onTime = useCallback((t: number) => setTime(t), []);

  const switchLanguage = async (lang: CaptionLanguage) => {
    if (!s || !meta) return;
    try {
      const r = await api.clipWords(id, lang);
      setDetail((d) => (d ? { ...d, words: r.words, caption_language: lang } : d));
      const maxWords = (meta.caption_presets[s.edits.captions.preset]?.max_words ?? 3) as number;
      const rel = r.words
        .filter(([, ws, we]) => we > s.start && ws < s.end)
        .map(([w, ws, we]) => ({ w, s: +(ws - s.start).toFixed(3), e: +(we - s.start).toFixed(3) }));
      update({ edits: { ...s.edits, captions: { ...s.edits.captions, language: lang } as Edits["captions"] }, chunks: chunkWords(rel, maxWords), chunksEdited: false }, "lang");
    } catch (e) {
      toast("error", (e as Error).message);
    }
  };

  const exportClip = async (render: boolean) => {
    if (!s) return;
    try {
      const edits: Edits = { ...s.edits, captions: { ...s.edits.captions, chunks: s.chunksEdited ? s.chunks : null } };
      const r = await api.updateClip(id, { start: s.start, end: s.end, title: s.title, edits, render });
      setDirty(false);
      if (r.job) setJob(r.job);
      else toast("success", "Draft saved.");
      if (!render) load();
    } catch (e) {
      toast("error", (e as Error).message);
    }
  };

  if (error) return <Card className="p-8 text-center text-sm text-muted">{error}</Card>;
  if (!detail || !s || !style || !meta) {
    return (
      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <Skeleton className="h-[70vh]" />
        <Skeleton className="h-[70vh]" />
      </div>
    );
  }
  const clip = detail.clip;
  const rendering = job && (job.status === "queued" || job.status === "running");
  const src = detail.project.source_video_url;
  const presetEntries = Object.entries(meta.caption_presets);

  return (
    <div className="space-y-4">
      {/* Top bar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <Link href={`/app/projects/${clip.project_id}`} className="grid size-9 place-items-center rounded-xl text-muted hover:bg-surface-2 hover:text-text" aria-label="Back to project">
            <ArrowLeft className="size-5" />
          </Link>
          <div className="min-w-0">
            <input
              value={s.title}
              onChange={(e) => update({ title: e.target.value }, "title")}
              className="w-full min-w-0 bg-transparent font-display text-lg font-semibold outline-none focus:underline sm:w-[28rem]"
              aria-label="Clip title"
            />
            <div className="text-xs text-muted">
              {detail.project.name} · score {clip.score}/100 · {fmtTime(s.end - s.start)}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={undo} disabled={!hist.past.length} aria-label="Undo">
            <Undo2 className="size-4" />
          </Button>
          <Button variant="ghost" size="sm" onClick={redo} disabled={!hist.future.length} aria-label="Redo">
            <Redo2 className="size-4" />
          </Button>
          <Button variant="secondary" size="sm" onClick={() => exportClip(false)} disabled={!dirty || !!rendering}>
            Save draft
          </Button>
          <Button size="sm" onClick={() => exportClip(true)} loading={!!rendering}>
            {rendering ? "Rendering…" : "Render & export"}
          </Button>
        </div>
      </div>

      {rendering && job && (
        <Card className="flex items-center gap-3 px-4 py-3">
          <Loader2 className="size-4 animate-spin text-primary" />
          <span className="text-sm">{job.message || "Rendering"}</span>
          <Progress value={job.progress} className="flex-1" />
          <span className="w-10 text-right text-sm tabular-nums text-muted">{Math.round(job.progress * 100)}%</span>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-[64px_1fr_360px]">
        {/* Left: tools */}
        <Card className="flex gap-1 overflow-x-auto p-1.5 lg:flex-col lg:overflow-visible">
          {TOOLS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTool(t.key)}
              className={cx(
                "flex min-w-14 flex-col items-center gap-1 rounded-xl px-1 py-2 text-[11px] font-medium transition cursor-pointer lg:min-w-0",
                tool === t.key ? "bg-primary-soft text-primary" : "text-muted hover:bg-surface-2 hover:text-text",
              )}
              aria-pressed={tool === t.key}
            >
              <t.icon className="size-5" />
              {t.label}
            </button>
          ))}
        </Card>

        {/* Center: preview */}
        <Card className="flex min-h-[520px] flex-col p-4 lg:h-[calc(100vh-15rem)]">
          {src ? (
            <Preview
              ref={preview}
              src={src}
              start={s.start}
              end={s.end}
              edits={s.edits}
              reframe={clip.reframe}
              chunks={s.chunks}
              style={style}
              onTime={onTime}
              onCropDrag={(x, y) => setEdits((e) => ({ ...e, crop: { ...e.crop, x, y } }), "crop-drag")}
              onLayoutDrag={
                tool === "format"
                  ? (panel, adj) => setEdits((e) => ({ ...e, layout: { ...(e.layout ?? {}), [panel]: adj } }), `drag-${panel}`)
                  : undefined
              }
              onTitleMove={
                tool === "text" && s.edits.overlays.some((o) => o.kind === "title")
                  ? (pos) =>
                      setEdits(
                        (e) => ({ ...e, overlays: e.overlays.map((o) => (o.kind === "title" ? { ...o, pos } : o)) }),
                        "title-drag",
                      )
                  : undefined
              }
            />
          ) : (
            <div className="grid flex-1 place-items-center text-sm text-muted">Source preview unavailable.</div>
          )}
          <p className="mt-2 text-center text-[11px] text-muted">
            Live preview of framing, captions and text. {s.edits.silence_removal && "Silence removal, "}fades and audio levelling are applied in the export.
          </p>
        </Card>

        {/* Right: contextual config */}
        <Card className="max-h-[calc(100vh-15rem)] min-h-[520px] overflow-y-auto p-5 scrollbar-thin">
          {tool === "trim" && (
            <div className="space-y-4">
              <h3 className="font-semibold">Trim</h3>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Start (s)">
                  <Input type="number" step={0.1} value={s.start.toFixed(2)} onChange={(e) => update({ start: Math.max(0, Math.min(Number(e.target.value), s.end - 1)) }, "start")} />
                </Field>
                <Field label="End (s)">
                  <Input type="number" step={0.1} value={s.end.toFixed(2)} onChange={(e) => update({ end: Math.max(s.start + 1, Math.min(Number(e.target.value), detail.project.duration ?? 1e9)) }, "end")} />
                </Field>
              </div>
              <div className="flex flex-wrap gap-2">
                {[-1, -0.25, 0.25, 1].map((d) => (
                  <Button key={`s${d}`} variant="secondary" size="sm" onClick={() => update({ start: Math.max(0, s.start + d) }, "start")}>
                    Start {d > 0 ? "+" : ""}{d}s
                  </Button>
                ))}
                {[-1, -0.25, 0.25, 1].map((d) => (
                  <Button key={`e${d}`} variant="secondary" size="sm" onClick={() => update({ end: Math.max(s.start + 1, s.end + d) }, "end")}>
                    End {d > 0 ? "+" : ""}{d}s
                  </Button>
                ))}
              </div>
              <div className="flex gap-2">
                <Button variant="secondary" size="sm" onClick={() => update({ start: Math.min(time, s.end - 1) }, "start")}>Set start at playhead</Button>
                <Button variant="secondary" size="sm" onClick={() => update({ end: Math.max(time, s.start + 1) }, "end")}>Set end at playhead</Button>
              </div>
              <Switch checked={s.edits.silence_removal} onChange={(v) => setEdits((e) => ({ ...e, silence_removal: v }), "silence")} label="Remove silent pauses" hint="Cuts gaps over 0.7s between words in the export" />
              <p className="text-xs text-muted">Drag the handles on the timeline below; they snap to word boundaries. The AI picked {fmtTime(clip.start)}–{fmtTime(clip.end)}.</p>
            </div>
          )}

          {tool === "captions" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold">Captions</h3>
                <Switch checked={s.edits.captions.enabled} onChange={(v) => setEdits((e) => ({ ...e, captions: { ...e.captions, enabled: v } }), "cap-on")} label="" />
              </div>
              {detail.spoken_language && !detail.spoken_language.startsWith("en") && (
                <Field label="Caption language">
                  <Segmented
                    value={(s.edits.captions as { language?: CaptionLanguage }).language ?? detail.caption_language ?? "english"}
                    onChange={(v) => switchLanguage(v as CaptionLanguage)}
                    options={[
                      { value: "english", label: "English" },
                      { value: "hinglish", label: "Hinglish" },
                      { value: "original", label: LANG_NAMES[detail.spoken_language.split("-")[0]] ?? "Original" },
                    ]}
                  />
                  <span className="mt-1 block text-[11px] text-muted">
                    English = translated · Hinglish = {LANG_NAMES[detail.spoken_language.split("-")[0]] === "हिन्दी" ? "Hindi" : "the spoken words"} in English letters (“kapde to maine…”) · then Render &amp; export
                  </span>
                </Field>
              )}
              <Field label="Style">
                <Select
                  value={s.edits.captions.preset}
                  onChange={(v) => update((st) => ({ edits: { ...st.edits, captions: { ...st.edits.captions, preset: v, style: {} } }, ...({ rechunk: true } as object) }), "preset")}
                  options={presetEntries.map(([k, p]) => ({ value: k, label: p.label }))}
                />
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Font">
                  <Select value={style.font} onChange={(v) => setEdits((e) => ({ ...e, captions: { ...e.captions, style: { ...e.captions.style, font: v } } }), "font")} options={Object.keys(meta.fonts).map((f) => ({ value: f, label: f }))} />
                </Field>
                <Field label="Position">
                  <Select value={style.position} onChange={(v) => setEdits((e) => ({ ...e, captions: { ...e.captions, style: { ...e.captions.style, position: v as CaptionStyle["position"] } } }), "pos")} options={[["top", "Top"], ["middle", "Middle"], ["lower", "Lower third"], ["bottom", "Bottom"]].map(([value, label]) => ({ value, label }))} />
                </Field>
                <Field label="Text colour">
                  <input type="color" value={style.color} onChange={(e) => setEdits((x) => ({ ...x, captions: { ...x.captions, style: { ...x.captions.style, color: e.target.value } } }), "color")} className="h-10 w-full cursor-pointer rounded-xl border border-border bg-surface" aria-label="Text colour" />
                </Field>
                <Field label="Highlight colour">
                  <input type="color" value={style.highlight} onChange={(e) => setEdits((x) => ({ ...x, captions: { ...x.captions, style: { ...x.captions.style, highlight: e.target.value, emphasis_color: e.target.value } } }), "hl")} className="h-10 w-full cursor-pointer rounded-xl border border-border bg-surface" aria-label="Highlight colour" />
                </Field>
              </div>
              <Field label={`Size · ${style.size}`}>
                <input type="range" min={36} max={140} value={style.size} onChange={(e) => setEdits((x) => ({ ...x, captions: { ...x.captions, style: { ...x.captions.style, size: Number(e.target.value) } } }), "size")} className="w-full" aria-label="Caption size" />
              </Field>
              <Field label={`Outline · ${style.outline}`}>
                <input type="range" min={0} max={12} value={style.outline} onChange={(e) => setEdits((x) => ({ ...x, captions: { ...x.captions, style: { ...x.captions.style, outline: Number(e.target.value) } } }), "outline")} className="w-full" aria-label="Outline width" />
              </Field>
              <Field label="Animation">
                <Select value={style.animation} onChange={(v) => setEdits((x) => ({ ...x, captions: { ...x.captions, style: { ...x.captions.style, animation: v as CaptionStyle["animation"] } } }), "anim")} options={[["none", "None"], ["highlight", "Active word colour"], ["pop", "Active word pop"], ["karaoke", "Karaoke fill"], ["fade", "Fade"]].map(([value, label]) => ({ value, label }))} />
              </Field>
              <div className="grid grid-cols-1 gap-1">
                <Switch checked={style.uppercase} onChange={(v) => setEdits((x) => ({ ...x, captions: { ...x.captions, style: { ...x.captions.style, uppercase: v } } }), "upper")} label="Uppercase" />
                <Switch checked={style.box} onChange={(v) => setEdits((x) => ({ ...x, captions: { ...x.captions, style: { ...x.captions.style, box: v, box_opacity: v ? 0.6 : 0 } } }), "box")} label="Background box" />
                <Switch checked={style.emphasis} onChange={(v) => setEdits((x) => ({ ...x, captions: { ...x.captions, style: { ...x.captions.style, emphasis: v } } }), "emph")} label="Highlight key words" hint={(s.edits.captions.keywords ?? []).join(", ") || undefined} />
              </div>
              <div>
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-xs font-medium uppercase tracking-wide text-muted">Caption text</span>
                  {s.chunksEdited && (
                    <button className="text-xs text-primary hover:underline cursor-pointer" onClick={() => update({ chunksEdited: false, ...({ rechunk: true } as object) }, "reset-chunks")}>
                      Reset to transcript
                    </button>
                  )}
                </div>
                <div className="space-y-1.5">
                  {s.chunks.map((c, i) => {
                    const active = time - s.start >= c.s && time - s.start < c.e;
                    return (
                      <div key={i} className={cx("flex items-center gap-2 rounded-lg", active && "bg-primary-soft")}>
                        <button className="w-11 shrink-0 text-right text-[11px] tabular-nums text-muted hover:text-primary cursor-pointer" onClick={() => preview.current?.seek(s.start + c.s + 0.01)}>
                          {fmtTime(c.s)}
                        </button>
                        <input
                          value={c.text}
                          onChange={(e) =>
                            update((st) => ({ chunksEdited: true, chunks: st.chunks.map((x, j) => (j === i ? retime({ ...x, text: e.target.value }) : x)) }), `chunk-${i}`)
                          }
                          className="h-8 flex-1 rounded-lg border border-transparent bg-transparent px-2 text-sm hover:border-border focus:border-primary focus:outline-none"
                          aria-label={`Caption at ${fmtTime(c.s)}`}
                        />
                      </div>
                    );
                  })}
                </div>
                <p className="mt-2 text-xs text-muted">Emoji aren&apos;t burned into video (the renderer can&apos;t draw colour emoji) — add them in your post text instead.</p>
              </div>
            </div>
          )}

          {tool === "format" && (
            <div className="space-y-4">
              <h3 className="font-semibold">Format & framing</h3>
              <Field label="Aspect ratio">
                <Segmented value={s.edits.aspect} onChange={(v) => setEdits((e) => ({ ...e, aspect: v }), "aspect")} options={(["9:16", "1:1", "4:5", "16:9"] as const).map((a) => ({ value: a, label: a }))} />
              </Field>
              <Field label="Framing">
                <Select
                  value={s.edits.crop.mode}
                  onChange={(v) => setEdits((e) => ({ ...e, crop: { ...e.crop, mode: v as Edits["crop"]["mode"] } }), "mode")}
                  options={[
                    { value: "auto", label: `Smart — follows ${clip.reframe.source === "faces" ? "faces" : clip.reframe.source === "motion" ? "action" : "the centre"}` },
                    { value: "manual", label: "Manual position" },
                    { value: "center", label: "Centre crop" },
                    ...(clip.reframe.split ? [{ value: "split", label: "Two speakers stacked" }] : []),
                    ...(s.edits.aspect === "9:16" || s.edits.aspect === "4:5"
                      ? [{ value: "facecam", label: clip.reframe.facecam ? "Gameplay: cam + game (cam detected)" : "Gameplay: cam + game (place the cam yourself)" }]
                      : []),
                    { value: "fit", label: "Fit whole frame (blurred fill)" },
                  ]}
                />
              </Field>
              {clip.reframe.source && (
                <div className="flex flex-wrap gap-1.5">
                  <Badge tone="primary">Subject: {clip.reframe.source}</Badge>
                  {clip.reframe.face_ratio != null && <Badge>Faces in {Math.round(clip.reframe.face_ratio * 100)}% of frames</Badge>}
                  {clip.reframe.split && <Badge tone="accent">2 speakers detected</Badge>}
                </div>
              )}
              {s.edits.crop.mode === "facecam" && (s.edits.aspect === "9:16" || s.edits.aspect === "4:5") && (
                <LayoutControls
                  layout={s.edits.layout}
                  box={clip.reframe.facecam?.box}
                  sw={detail.project.width ?? 1920}
                  sh={detail.project.height ?? 1080}
                  W={s.edits.aspect === "4:5" ? 1080 : 1080}
                  H={s.edits.aspect === "4:5" ? 1350 : 1920}
                  onChange={(l) => setEdits((e) => ({ ...e, layout: l }), "layout")}
                />
              )}
              {s.edits.crop.mode === "manual" && (
                <>
                  <Field label="Horizontal position">
                    <input type="range" min={0} max={1} step={0.005} value={s.edits.crop.x} onChange={(e) => setEdits((x) => ({ ...x, crop: { ...x.crop, x: Number(e.target.value) } }), "cx")} className="w-full" aria-label="Horizontal crop position" />
                  </Field>
                  <Field label="Vertical position">
                    <input type="range" min={0} max={1} step={0.005} value={s.edits.crop.y} onChange={(e) => setEdits((x) => ({ ...x, crop: { ...x.crop, y: Number(e.target.value) } }), "cy")} className="w-full" aria-label="Vertical crop position" />
                  </Field>
                  <p className="text-xs text-muted">Tip: drag the preview to reposition.</p>
                </>
              )}
              {(s.edits.crop.mode === "manual" || s.edits.crop.mode === "auto" || s.edits.crop.mode === "center") && (
                <Field label={`Zoom · ${s.edits.crop.zoom.toFixed(2)}×`}>
                  <input type="range" min={1} max={2.5} step={0.05} value={s.edits.crop.zoom} onChange={(e) => setEdits((x) => ({ ...x, crop: { ...x.crop, zoom: Number(e.target.value) } }), "zoom")} className="w-full" aria-label="Zoom" />
                </Field>
              )}
              <Field label="Export quality">
                <Select value={s.edits.quality} onChange={(v) => setEdits((e) => ({ ...e, quality: v as Edits["quality"] }), "q")} options={[["draft", "Draft (720p)"], ["standard", "Standard (1080p)"], ["high", "High (1080p, best)"]].map(([value, label]) => ({ value, label }))} />
              </Field>
            </div>
          )}

          {tool === "text" && (
            <div className="space-y-4">
              <h3 className="font-semibold">Text & branding</h3>
              {(() => {
                const title = s.edits.overlays.find((o) => o.kind === "title");
                const mark = s.edits.overlays.find((o) => o.kind === "watermark");
                const setOv = (kind: "title" | "watermark", patch: Record<string, unknown> | null) =>
                  setEdits((e) => {
                    const rest = e.overlays.filter((o) => o.kind !== kind);
                    if (!patch) return { ...e, overlays: rest };
                    const cur = e.overlays.find((o) => o.kind === kind) ?? { kind, text: "", start: 0, ...(kind === "title" ? { end: 3.2 } : {}) };
                    return { ...e, overlays: [...rest, { ...cur, ...patch } as Edits["overlays"][number]] };
                  }, `ov-${kind}`);
                return (
                  <>
                    <Switch
                      checked={!!title}
                      onChange={(v) => setOv("title", v ? { text: s.title, style: "impact", start: 0, end: 3 } : null)}
                      label="Hook title"
                    />
                    {title && (
                      <TitleEditor
                        ov={title}
                        clipLength={s.end - s.start}
                        thumb={clip.thumb_url}
                        onChange={(patch) => setOv("title", patch as Record<string, unknown>)}
                      />
                    )}
                    <Switch checked={!!mark} onChange={(v) => setOv("watermark", v ? { text: "@yourhandle" } : null)} label="Watermark" />
                    {mark && (
                      <Field label="Watermark text">
                        <Input value={mark.text} onChange={(e) => setOv("watermark", { text: e.target.value })} maxLength={60} />
                      </Field>
                    )}
                  </>
                );
              })()}
            </div>
          )}

          {tool === "audio" && s.edits.audio && s.edits.video && (
            <div className="space-y-4">
              <h3 className="font-semibold">Audio & transitions</h3>
              <Field label={`Volume · ${s.edits.audio.gain_db > 0 ? "+" : ""}${s.edits.audio.gain_db} dB`}>
                <input type="range" min={-12} max={12} step={1} value={s.edits.audio.gain_db} onChange={(e) => setEdits((x) => ({ ...x, audio: { ...x.audio!, gain_db: Number(e.target.value) } }), "gain")} className="w-full" aria-label="Volume" />
              </Field>
              <Switch checked={s.edits.audio.normalize} onChange={(v) => setEdits((x) => ({ ...x, audio: { ...x.audio!, normalize: v } }), "norm")} label="Level loudness for social (−14 LUFS)" />
              <div className="grid grid-cols-2 gap-3">
                <Field label={`Audio fade in · ${s.edits.audio.fade_in}s`}>
                  <input type="range" min={0} max={2} step={0.05} value={s.edits.audio.fade_in} onChange={(e) => setEdits((x) => ({ ...x, audio: { ...x.audio!, fade_in: Number(e.target.value) } }), "afi")} className="w-full" aria-label="Audio fade in" />
                </Field>
                <Field label={`Audio fade out · ${s.edits.audio.fade_out}s`}>
                  <input type="range" min={0} max={2} step={0.05} value={s.edits.audio.fade_out} onChange={(e) => setEdits((x) => ({ ...x, audio: { ...x.audio!, fade_out: Number(e.target.value) } }), "afo")} className="w-full" aria-label="Audio fade out" />
                </Field>
                <Field label={`Video fade in · ${s.edits.video.fade_in}s`}>
                  <input type="range" min={0} max={1.5} step={0.05} value={s.edits.video.fade_in} onChange={(e) => setEdits((x) => ({ ...x, video: { ...x.video!, fade_in: Number(e.target.value) } }), "vfi")} className="w-full" aria-label="Video fade in" />
                </Field>
                <Field label={`Video fade out · ${s.edits.video.fade_out}s`}>
                  <input type="range" min={0} max={1.5} step={0.05} value={s.edits.video.fade_out} onChange={(e) => setEdits((x) => ({ ...x, video: { ...x.video!, fade_out: Number(e.target.value) } }), "vfo")} className="w-full" aria-label="Video fade out" />
                </Field>
              </div>
            </div>
          )}

          {tool === "publish" && (
            <div className="space-y-4">
              <h3 className="font-semibold">Publishing copy</h3>
              <PublishPanel clip={clip} onChange={load} />
            </div>
          )}
        </Card>
      </div>

      {/* Bottom: timeline */}
      <Card className="p-4">
        <Timeline
          duration={detail.project.duration ?? s.end + 30}
          start={s.start}
          end={s.end}
          time={time}
          words={words}
          envelope={detail.envelope}
          onChange={(a, b) => update({ start: +a.toFixed(2), end: +b.toFixed(2) }, "trim-drag")}
          onSeek={(t) => preview.current?.seek(t)}
        />
      </Card>

      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <Assistant projectId={clip.project_id} clipId={clip.id} onAction={() => load().then(() => toast("info", "Reload the editor to see assistant changes once the render finishes."))} />
        <Card className="p-4">
          <div className="text-sm font-medium">Last export</div>
          {clip.video_url ? (
            <div className="mt-3 flex gap-3">
              <video src={clip.video_url} poster={clip.thumb_url ?? undefined} controls className="h-40 rounded-lg bg-black" />
              <div className="flex flex-col gap-2">
                <a href={clip.download_url!} download>
                  <Button size="sm"><Download className="size-4" /> MP4</Button>
                </a>
                {clip.srt_url && (
                  <a href={clip.srt_url} download>
                    <Button variant="secondary" size="sm">SRT</Button>
                  </a>
                )}
                {clip.rendered_at && <span className="text-xs text-muted">{new Date(clip.rendered_at).toLocaleTimeString()}</span>}
              </div>
            </div>
          ) : (
            <p className="mt-2 text-sm text-muted">Not rendered yet.</p>
          )}
        </Card>
      </div>
    </div>
  );
}
