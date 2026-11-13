"use client";

import { AlertTriangle, CheckCircle2, FileVideo, Link2, Loader2, Settings2, Upload, Wand2, X } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, DEFAULT_SETTINGS, fmtBytes, fmtTime, uploadFile } from "@/lib/api";
import type { GenerateSettings, UrlInfo } from "@/lib/types";
import { useSession } from "./AppShell";
import { CaptionSample } from "./CaptionPreview";
import { useToast } from "./toast";
import { Badge, Button, Card, cx, Field, Input, Progress, Segmented, Select, Switch } from "./ui";

const LENGTHS = [
  { key: "short", label: "15–30s", min: 15, max: 30 },
  { key: "standard", label: "20–60s", min: 20, max: 60 },
  { key: "long", label: "45–90s", min: 45, max: 90 },
  { key: "custom", label: "Custom", min: 0, max: 0 },
] as const;

const PLATFORM_LABELS: Record<string, string> = {
  youtube: "YouTube Shorts",
  instagram: "Instagram Reels",
  tiktok: "TikTok",
  linkedin: "LinkedIn",
  facebook: "Facebook",
  x: "X",
};

type LocalMeta = { duration: number; width: number; height: number; thumb: string | null };

export function NewProject() {
  const router = useRouter();
  const params = useSearchParams();
  const toast = useToast();
  const { meta, user } = useSession();
  const [mode, setMode] = useState<"upload" | "url">(params.get("url") ? "url" : "upload");
  const [url, setUrl] = useState(params.get("url") ?? "");
  const [urlInfo, setUrlInfo] = useState<UrlInfo | null>(null);
  const [urlError, setUrlError] = useState("");
  const [checking, setChecking] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [local, setLocal] = useState<LocalMeta | null>(null);
  const [fileError, setFileError] = useState("");
  const [drag, setDrag] = useState(false);
  const [name, setName] = useState("");
  const [s, setS] = useState<GenerateSettings>(() => ({
    ...DEFAULT_SETTINGS,
    caption_preset: user.brand_kit?.caption_preset || DEFAULT_SETTINGS.caption_preset,
  }));
  const [lengthKey, setLengthKey] = useState<string>("standard");
  const [advanced, setAdvanced] = useState(false);
  const [phase, setPhase] = useState<"idle" | "uploading" | "creating">("idle");
  const [sent, setSent] = useState(0);
  const abort = useRef<AbortController | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const set = <K extends keyof GenerateSettings>(k: K, v: GenerateSettings[K]) => setS((p) => ({ ...p, [k]: v }));

  // Validate links as the user types (debounced).
  useEffect(() => {
    if (mode !== "url" || !url.trim()) {
      setUrlInfo(null);
      setUrlError("");
      return;
    }
    const t = setTimeout(async () => {
      setChecking(true);
      setUrlError("");
      try {
        const info = await api.checkUrl(url.trim());
        setUrlInfo(info);
        if (info.title && !name) setName(info.title);
      } catch (e) {
        setUrlInfo(null);
        setUrlError((e as Error).message);
      } finally {
        setChecking(false);
      }
    }, 600);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, mode]);

  const pickFile = (f: File | undefined | null) => {
    setFileError("");
    setLocal(null);
    if (!f) return;
    const okExt = /\.(mp4|mov|mkv|webm|m4v|avi)$/i.test(f.name);
    if (!okExt) {
      setFileError("Supported formats: MP4, MOV, MKV, WEBM, M4V, AVI.");
      return;
    }
    const limit = (meta?.limits.max_upload_mb ?? 4096) * 1024 * 1024;
    if (f.size > limit) {
      setFileError(`This file is ${fmtBytes(f.size)}; the limit is ${fmtBytes(limit)}.`);
      return;
    }
    setFile(f);
    setName((n) => n || f.name.replace(/\.[^.]+$/, ""));
    // Local preview metadata + thumbnail (the server re-validates with ffprobe).
    const v = document.createElement("video");
    const src = URL.createObjectURL(f);
    v.preload = "metadata";
    v.muted = true;
    v.src = src;
    v.onloadedmetadata = () => {
      const m: LocalMeta = { duration: v.duration, width: v.videoWidth, height: v.videoHeight, thumb: null };
      setLocal(m);
      v.currentTime = Math.min(5, v.duration / 3);
    };
    v.onseeked = () => {
      try {
        const c = document.createElement("canvas");
        c.width = 320;
        c.height = Math.round((320 * v.videoHeight) / Math.max(1, v.videoWidth));
        c.getContext("2d")!.drawImage(v, 0, 0, c.width, c.height);
        const thumb = c.toDataURL("image/jpeg", 0.75);
        setLocal((m) => (m ? { ...m, thumb } : m));
      } catch {}
      URL.revokeObjectURL(src);
    };
    v.onerror = () => {
      // Browser can't decode (e.g. some MKV/HEVC) — the server will still try.
      setLocal({ duration: NaN, width: 0, height: 0, thumb: null });
      URL.revokeObjectURL(src);
    };
  };

  const ready = mode === "upload" ? !!file && !fileError : !!urlInfo?.importable;
  const busy = phase !== "idle";

  const generate = async () => {
    if (!ready || busy) return;
    try {
      let upload_id: string | undefined;
      if (mode === "upload" && file) {
        setPhase("uploading");
        abort.current = new AbortController();
        const up = await uploadFile(file, (n) => setSent(n), abort.current.signal);
        upload_id = up.id;
      }
      setPhase("creating");
      const p = await api.createProject({
        name: name.trim() || undefined,
        upload_id,
        url: mode === "url" ? urlInfo!.url : undefined,
        settings: s,
      });
      toast("success", "AI Generate started — your clips are being made.");
      router.push(`/app/projects/${p.id}`);
    } catch (e) {
      toast("error", (e as Error).message);
      setPhase("idle");
    }
  };

  const presets = meta?.caption_presets ?? {};

  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_400px]">
      {/* Source */}
      <div className="space-y-6">
        <Card className="p-5 sm:p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="font-display text-lg font-semibold">1. Add your video</h2>
            <Segmented
              value={mode}
              onChange={(m) => !busy && setMode(m)}
              options={[
                { value: "upload", label: <><Upload className="size-4" /> Upload</> },
                { value: "url", label: <><Link2 className="size-4" /> Paste link</> },
              ]}
            />
          </div>

          {mode === "upload" ? (
            <div className="mt-5">
              {!file ? (
                <button
                  type="button"
                  onClick={() => inputRef.current?.click()}
                  onDragOver={(e) => {
                    e.preventDefault();
                    setDrag(true);
                  }}
                  onDragLeave={() => setDrag(false)}
                  onDrop={(e) => {
                    e.preventDefault();
                    setDrag(false);
                    pickFile(e.dataTransfer.files?.[0]);
                  }}
                  className={cx(
                    "flex w-full flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-14 text-center transition cursor-pointer",
                    drag ? "border-primary bg-primary-soft" : "border-border hover:border-primary/60 hover:bg-surface-2",
                  )}
                >
                  <div className="grid size-12 place-items-center rounded-2xl bg-primary-soft text-primary">
                    <Upload className="size-6" />
                  </div>
                  <div className="mt-4 font-medium">Drop a video here or click to browse</div>
                  <div className="mt-1 text-sm text-muted">
                    MP4, MOV, MKV, WEBM · up to {fmtBytes((meta?.limits.max_upload_mb ?? 4096) * 1024 * 1024)} ·{" "}
                    {meta?.limits.max_duration_minutes ?? 180} min
                  </div>
                </button>
              ) : (
                <div className="flex gap-4 rounded-2xl border border-border p-3">
                  <div className="relative aspect-video w-40 shrink-0 overflow-hidden rounded-xl bg-surface-2">
                    {local?.thumb ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={local.thumb} alt="" className="h-full w-full object-cover" />
                    ) : (
                      <FileVideo className="absolute inset-0 m-auto size-8 text-muted" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium">{file.name}</div>
                    <div className="mt-1 flex flex-wrap gap-x-3 text-sm text-muted">
                      <span>{fmtBytes(file.size)}</span>
                      {local && isFinite(local.duration) && <span>{fmtTime(local.duration)}</span>}
                      {local && local.width > 0 && <span>{local.width}×{local.height}</span>}
                      {local && !isFinite(local.duration) && <span>Preview unavailable in this browser</span>}
                    </div>
                    {phase === "uploading" && (
                      <div className="mt-3">
                        <Progress value={sent / file.size} />
                        <div className="mt-1 text-xs text-muted">
                          Uploading {fmtBytes(sent)} of {fmtBytes(file.size)}
                        </div>
                      </div>
                    )}
                  </div>
                  {!busy && (
                    <button
                      onClick={() => {
                        setFile(null);
                        setLocal(null);
                      }}
                      className="self-start p-1 text-muted hover:text-text cursor-pointer"
                      aria-label="Remove file"
                    >
                      <X className="size-4" />
                    </button>
                  )}
                </div>
              )}
              <input
                ref={inputRef}
                type="file"
                accept="video/*,.mkv"
                className="hidden"
                onChange={(e) => pickFile(e.target.files?.[0])}
              />
              {fileError && <p className="mt-3 text-sm text-danger">{fileError}</p>}
            </div>
          ) : (
            <div className="mt-5 space-y-3">
              <div className="relative">
                <Link2 className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted" />
                <Input
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://www.youtube.com/watch?v=…  ·  youtu.be  ·  Shorts  ·  TikTok  ·  .mp4"
                  className="h-12 pl-10"
                  aria-label="Video link"
                  disabled={busy}
                />
                {checking && <Loader2 className="absolute right-3 top-1/2 size-4 -translate-y-1/2 animate-spin text-muted" />}
              </div>
              {urlError && (
                <div className="flex gap-2 rounded-xl bg-danger/10 px-3 py-2.5 text-sm text-danger">
                  <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                  {urlError}
                </div>
              )}
              {urlInfo && (
                <div
                  className={cx(
                    "flex gap-4 rounded-2xl border p-3",
                    urlInfo.importable ? "border-success/40" : "border-warning/40",
                  )}
                >
                  {urlInfo.thumbnail && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={urlInfo.thumbnail} alt="" className="aspect-video w-36 shrink-0 rounded-xl object-cover" />
                  )}
                  <div className="min-w-0 text-sm">
                    <div className="flex items-center gap-2">
                      {urlInfo.importable ? (
                        <CheckCircle2 className="size-4 text-success" />
                      ) : (
                        <AlertTriangle className="size-4 text-warning" />
                      )}
                      <span className="truncate font-medium">{urlInfo.title || urlInfo.url}</span>
                    </div>
                    {urlInfo.author && <div className="mt-0.5 text-muted">by {urlInfo.author}</div>}
                    <div className="mt-0.5 flex flex-wrap gap-x-3 text-muted">
                      {urlInfo.platform && urlInfo.kind !== "direct" && <span>{urlInfo.platform}</span>}
                      {urlInfo.duration ? <span>{fmtTime(urlInfo.duration)}</span> : null}
                      {urlInfo.size_bytes ? <span>≈ {fmtBytes(urlInfo.size_bytes)}</span> : null}
                    </div>
                    <p className="mt-2 text-muted">{urlInfo.message}</p>
                    {urlInfo.warnings.map((w) => (
                      <p key={w} className="mt-1 text-warning">{w}</p>
                    ))}
                    {!urlInfo.importable && (
                      <Button variant="secondary" size="sm" className="mt-3" onClick={() => setMode("upload")}>
                        <Upload className="size-4" /> Upload the file instead
                      </Button>
                    )}
                  </div>
                </div>
              )}
              {!urlInfo && !urlError && (
                <p className="text-sm text-muted">
                  Paste a YouTube link (videos, Shorts, youtu.be), or one from TikTok, Instagram, X, Reddit, Vimeo,
                  Twitch, Facebook and 1,800+ other sites, or a direct .mp4 link. HypeSift downloads it in up to
                  1080p, then the AI finds the moments and edits the clips. Only use videos you own or have
                  permission to use.
                </p>
              )}
            </div>
          )}
          <div className="mt-5">
            <Field label="Project name">
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="My episode" disabled={busy} />
            </Field>
          </div>
        </Card>

        {/* Preferences */}
        <Card className="p-5 sm:p-6">
          <h2 className="font-display text-lg font-semibold">2. Choose clip preferences</h2>
          <div className="mt-5 grid gap-5 sm:grid-cols-2">
            <Field label={`Number of clips · ${s.count}`}>
              <input
                type="range"
                min={1}
                max={meta?.limits.max_clips ?? 20}
                value={s.count}
                onChange={(e) => set("count", Number(e.target.value))}
                className="w-full"
                aria-label="Number of clips"
              />
            </Field>
            <Field label="Clip length">
              <Segmented
                value={lengthKey}
                onChange={(k) => {
                  setLengthKey(k);
                  const p = LENGTHS.find((l) => l.key === k)!;
                  if (p.min) setS((x) => ({ ...x, min_dur: p.min, max_dur: p.max }));
                }}
                options={LENGTHS.map((l) => ({ value: l.key, label: l.label }))}
                className="flex-wrap"
              />
            </Field>
            {lengthKey === "custom" && (
              <div className="grid grid-cols-2 gap-3 sm:col-span-2">
                <Field label="Min seconds">
                  <Input type="number" min={5} max={170} value={s.min_dur} onChange={(e) => set("min_dur", Number(e.target.value))} />
                </Field>
                <Field label="Max seconds">
                  <Input type="number" min={8} max={180} value={s.max_dur} onChange={(e) => set("max_dur", Number(e.target.value))} />
                </Field>
              </div>
            )}
            <Field label="Content type">
              <Select
                value={s.genre}
                onChange={(v) => set("genre", v)}
                options={Object.entries(meta?.genres ?? { auto: "Auto-detect" }).map(([value, label]) => ({ value, label }))}
              />
            </Field>
            <Field label="Mood">
              <Select
                value={s.mood}
                onChange={(v) => set("mood", v)}
                options={(meta?.moods ?? ["any"]).map((m) => ({ value: m, label: m === "any" ? "Best overall" : m[0].toUpperCase() + m.slice(1) }))}
              />
            </Field>
            <Field label="Format">
              <Segmented
                value={s.aspect}
                onChange={(v) => set("aspect", v)}
                options={(["9:16", "1:1", "4:5", "16:9"] as const).map((a) => ({ value: a, label: a }))}
              />
            </Field>
            <Field label="Framing">
              <Select
                value={s.crop_mode}
                onChange={(v) => set("crop_mode", v as GenerateSettings["crop_mode"])}
                options={[
                  { value: "auto", label: "Smart (follow faces & action)" },
                  { value: "center", label: "Center crop" },
                  { value: "fit", label: "Fit whole frame (blurred fill)" },
                ]}
              />
            </Field>
          </div>

          <div className="mt-6">
            <div className="flex items-center justify-between">
              <div className="text-xs font-medium uppercase tracking-wide text-muted">Caption style</div>
              <Switch checked={s.captions} onChange={(v) => set("captions", v)} label="" />
            </div>
            <div className={cx("mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3", !s.captions && "opacity-40 pointer-events-none")}>
              {Object.entries(presets).map(([key, st]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => set("caption_preset", key)}
                  className={cx(
                    "overflow-hidden rounded-xl border text-left transition cursor-pointer",
                    s.caption_preset === key ? "border-primary ring-2 ring-primary/30" : "border-border hover:border-primary/50",
                  )}
                  aria-pressed={s.caption_preset === key}
                >
                  <div className="grid h-16 place-items-center bg-[#1c1a26] px-2">
                    <CaptionSample style={st} />
                  </div>
                  <div className="px-2.5 py-1.5 text-xs font-medium">{st.label}</div>
                </button>
              ))}
            </div>
          </div>

          <div className="mt-6">
            <div className="text-xs font-medium uppercase tracking-wide text-muted">Publishing copy for</div>
            <div className="mt-3 flex flex-wrap gap-2">
              {Object.entries(PLATFORM_LABELS).map(([p, label]) => {
                const on = s.platforms.includes(p);
                return (
                  <button
                    key={p}
                    type="button"
                    onClick={() => set("platforms", on ? s.platforms.filter((x) => x !== p) : [...s.platforms, p])}
                    className={cx(
                      "rounded-full border px-3 h-8 text-sm transition cursor-pointer",
                      on ? "border-primary bg-primary-soft text-primary" : "border-border text-muted hover:text-text",
                    )}
                    aria-pressed={on}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </div>

          <button
            type="button"
            onClick={() => setAdvanced((a) => !a)}
            className="mt-6 inline-flex items-center gap-2 text-sm font-medium text-muted hover:text-text cursor-pointer"
            aria-expanded={advanced}
          >
            <Settings2 className="size-4" /> {advanced ? "Hide" : "Show"} advanced options
          </button>
          {advanced && (
            <div className="mt-4 grid gap-x-8 gap-y-2 sm:grid-cols-2">
              <Field label="Copy tone">
                <Select value={s.tone} onChange={(v) => set("tone", v)} options={(meta?.tones ?? ["compelling"]).map((t) => ({ value: t, label: t === "compelling" ? "Compelling but truthful" : t[0].toUpperCase() + t.slice(1) }))} />
              </Field>
              <Field label="Spoken language">
                <Select
                  value={s.language}
                  onChange={(v) => set("language", v)}
                  options={[
                    ["auto", "Auto-detect"], ["en", "English"], ["hi", "Hindi"], ["es", "Spanish"], ["fr", "French"],
                    ["de", "German"], ["pt", "Portuguese"], ["ja", "Japanese"], ["ko", "Korean"], ["ar", "Arabic"],
                  ].map(([value, label]) => ({ value, label }))}
                />
              </Field>
              <Field label="Look for moments">
                <Select value={s.position} onChange={(v) => set("position", v)} options={[["any", "Anywhere"], ["start", "Near the start"], ["middle", "In the middle"], ["end", "Near the end"]].map(([value, label]) => ({ value, label }))} />
              </Field>
              <Field label="Export quality">
                <Select value={s.quality} onChange={(v) => set("quality", v as GenerateSettings["quality"])} options={[["draft", "Draft (720p, fastest)"], ["standard", "Standard (1080p)"], ["high", "High (1080p, best)"]].map(([value, label]) => ({ value, label }))} />
              </Field>
              <div className="sm:col-span-2 mt-2 grid gap-x-8 sm:grid-cols-2">
                <Switch checked={s.silence_removal} onChange={(v) => set("silence_removal", v)} label="Remove silent pauses" hint="Cuts gaps longer than 0.7s" />
                <Switch checked={s.context_padding} onChange={(v) => set("context_padding", v)} label="Context padding" hint="Small lead-in and tail around each clip" />
                <Switch checked={s.hook_title} onChange={(v) => set("hook_title", v)} label="Hook title overlay" hint="Clip title on screen for the first 3s" />
                <Switch checked={s.keyword_emphasis} onChange={(v) => set("keyword_emphasis", v)} label="Highlight key words" />
                <Switch
                  checked={s.use_llm}
                  onChange={(v) => set("use_llm", v)}
                  label="Use local AI editor"
                  hint={meta?.llm.available ? `${meta.llm.model} re-ranks clips and writes copy` : meta?.llm.reason ?? "Unavailable"}
                />
              </div>
            </div>
          )}
        </Card>
      </div>

      {/* Generate */}
      <div className="xl:sticky xl:top-8 xl:self-start">
        <Card className="p-5 sm:p-6">
          <h2 className="font-display text-lg font-semibold">3. Generate</h2>
          <ul className="mt-4 space-y-2 text-sm text-muted">
            <li className="flex justify-between"><span>Clips</span><span className="text-text">{s.count}</span></li>
            <li className="flex justify-between"><span>Length</span><span className="text-text">{s.min_dur}–{s.max_dur}s</span></li>
            <li className="flex justify-between"><span>Format</span><span className="text-text">{s.aspect} · {s.crop_mode === "auto" ? "smart crop" : s.crop_mode}</span></li>
            <li className="flex justify-between"><span>Captions</span><span className="text-text">{s.captions ? presets[s.caption_preset]?.label ?? s.caption_preset : "Off"}</span></li>
            <li className="flex justify-between"><span>Copy for</span><span className="text-text">{s.platforms.length} platform{s.platforms.length === 1 ? "" : "s"}</span></li>
            <li className="flex justify-between">
              <span>AI editor</span>
              <span className="text-text">{s.use_llm && meta?.llm.available ? meta.llm.model : "Signals only"}</span>
            </li>
          </ul>
          <Button size="lg" className="mt-6 w-full" disabled={!ready} loading={busy} onClick={generate}>
            {!busy && <Wand2 className="size-5" />}
            {phase === "uploading" ? `Uploading… ${file ? Math.round((sent / file.size) * 100) : 0}%` : phase === "creating" ? "Starting…" : "AI Generate"}
          </Button>
          {phase === "uploading" && (
            <Button variant="ghost" size="sm" className="mt-2 w-full" onClick={() => abort.current?.abort()}>
              Cancel upload
            </Button>
          )}
          <p className="mt-4 text-xs text-muted">
            HypeSift transcribes, finds and ranks moments, then renders every clip with captions and framing, and
            writes titles, descriptions and hashtags. You can edit everything afterwards.
          </p>
          {!ready && !busy && (
            <Badge tone="neutral" className="mt-3">
              {mode === "upload" ? "Choose a video file to continue" : "Paste a direct video link to continue"}
            </Badge>
          )}
          <p className="mt-4 text-[11px] text-muted">Only upload videos you own or have permission to use.</p>
        </Card>
      </div>
    </div>
  );
}
