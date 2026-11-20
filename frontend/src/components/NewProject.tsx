"use client";

import {
  ArrowLeft,
  ArrowRight,
  Ban,
  Check,
  ChevronDown,
  FileVideo,
  Info,
  Lightbulb,
  Loader2,
  Music,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, DEFAULT_SETTINGS, fmtBytes, fmtTime, uploadFile } from "@/lib/api";
import { chunkWords } from "@/lib/captions";
import type { Asset, CaptionStyle, Effect, GenerateSettings, Transition, UrlInfo } from "@/lib/types";
import { PageHeader, useSession } from "./AppShell";
import { CaptionOverlay, CaptionSample } from "./CaptionPreview";
import { useToast } from "./toast";
import { Button, cx, Input, Select, Switch } from "./ui";
import { ComparePlayPicker, LengthPicker, PositionPicker, TitleStylePicker } from "./Pickers";

const LANGS: [string, string][] = [
  ["auto", "Auto-detect"], ["en", "English"], ["hi", "Hindi"], ["es", "Spanish"], ["fr", "French"], ["de", "German"],
  ["pt", "Portuguese"], ["it", "Italian"], ["ja", "Japanese"], ["ko", "Korean"], ["zh", "Chinese"], ["ar", "Arabic"],
  ["ru", "Russian"], ["tr", "Turkish"], ["id", "Indonesian"], ["bn", "Bengali"], ["ta", "Tamil"], ["te", "Telugu"],
  ["mr", "Marathi"], ["ur", "Urdu"],
];

const SIZES: { value: GenerateSettings["aspect"]; label: string }[] = [
  { value: "9:16", label: "Portrait (9:16) · Shorts, Reels, TikTok" },
  { value: "1:1", label: "Square (1:1)" },
  { value: "4:5", label: "Vertical (4:5) · Feed" },
  { value: "16:9", label: "Landscape (16:9)" },
];

const PLATFORM_LABELS: Record<string, string> = {
  youtube: "YouTube Shorts",
  instagram: "Instagram Reels",
  tiktok: "TikTok",
  linkedin: "LinkedIn",
  facebook: "Facebook",
  x: "X",
};

const SAMPLE = "This is how your captions will look on every clip".split(" ");

export function youtubeId(url: string): string | null {
  const m = url.match(/(?:youtu\.be\/|youtube(?:-nocookie)?\.com\/(?:watch\?(?:.*&)?v=|shorts\/|embed\/|live\/))([A-Za-z0-9_-]{11})/);
  return m ? m[1] : null;
}

type LocalMeta = { duration: number; width: number; height: number; thumb: string | null };

// ----------------------------------------------------------------------------- small building blocks

function Section({ title, info, children, className }: { title: string; info?: string; children: React.ReactNode; className?: string }) {
  return (
    <section className={cx("py-4", className)}>
      <h3 className="mb-2 flex items-center gap-1.5 text-sm font-medium">
        {title}
        {info && (
          <span title={info} className="text-muted cursor-help">
            <Info className="size-3.5" />
          </span>
        )}
      </h3>
      {children}
    </section>
  );
}

function Chips<T extends string>({ value, onChange, options }: { value: T; onChange: (v: T) => void; options: [T, string][] }) {
  return (
    <div className="flex flex-wrap gap-1 rounded-xl bg-surface-2 p-1.5">
      {options.map(([v, label]) => (
        <button
          key={v}
          type="button"
          onClick={() => onChange(v)}
          aria-pressed={value === v}
          className={cx(
            "h-8 rounded-lg px-3 text-xs font-medium transition cursor-pointer",
            value === v ? "bg-surface text-primary ring-1 ring-primary shadow-sm" : "text-muted hover:text-text",
          )}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function Tile({ selected, onClick, label, bg, children }: { selected: boolean; onClick: () => void; label: string; bg?: string | null; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick} aria-pressed={selected} aria-label={label} className="group text-center cursor-pointer">
      <div
        className={cx(
          "relative grid aspect-[16/11] place-items-center overflow-hidden rounded-xl border-2 transition",
          selected ? "border-primary" : "border-transparent group-hover:border-primary/40",
        )}
        style={{ background: bg ? `linear-gradient(rgba(0,0,0,.35),rgba(0,0,0,.35)), url(${bg}) center/cover` : "#3f3f46" }}
      >
        {children}
        {selected && (
          <span className="absolute right-1 top-1 grid size-4 place-items-center rounded-full bg-primary text-on-primary">
            <Check className="size-3" />
          </span>
        )}
      </div>
      <div className="mt-1 text-[11px] text-muted">{label}</div>
    </button>
  );
}

function AssetBox({
  kind,
  asset,
  onChange,
  children,
}: {
  kind: "logo" | "music";
  asset: Asset | null;
  onChange: (a: Asset | null) => void;
  children?: React.ReactNode;
}) {
  const toast = useToast();
  const ref = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const pick = async (f?: File | null) => {
    if (!f) return;
    setBusy(true);
    try {
      onChange(await api.uploadAsset(kind, f));
    } catch (e) {
      toast("error", (e as Error).message);
    } finally {
      setBusy(false);
      if (ref.current) ref.current.value = "";
    }
  };
  return (
    <div className="flex flex-wrap items-start gap-4">
      {asset ? (
        <div className="relative grid size-20 place-items-center overflow-hidden rounded-xl border border-border bg-surface-2">
          {kind === "logo" && asset.url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={asset.url} alt="" className="max-h-full max-w-full object-contain p-2" />
          ) : (
            <Music className="size-6 text-primary" />
          )}
          <button
            type="button"
            onClick={() => onChange(null)}
            className="absolute right-1 top-1 grid size-5 place-items-center rounded-full bg-black/60 text-white cursor-pointer"
            aria-label={`Remove ${kind}`}
          >
            <X className="size-3" />
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => ref.current?.click()}
          className="grid size-20 place-items-center rounded-xl border-2 border-dashed border-border text-muted hover:border-primary/60 hover:text-primary cursor-pointer"
          aria-label={`Upload ${kind}`}
        >
          {busy ? <Loader2 className="size-5 animate-spin" /> : <Upload className="size-5" />}
        </button>
      )}
      <div className="min-w-0 flex-1 space-y-2 text-xs text-muted">
        {asset ? <div className="truncate text-sm text-text">{asset.name}</div> : <div>{kind === "logo" ? "PNG, JPG or WEBP · transparent PNG looks best" : "MP3, M4A, WAV or OGG · use music you have the rights to"}</div>}
        {asset && children}
      </div>
      <input
        ref={ref}
        type="file"
        className="hidden"
        accept={kind === "logo" ? "image/png,image/jpeg,image/webp" : "audio/*"}
        onChange={(e) => pick(e.target.files?.[0])}
      />
    </div>
  );
}

// ----------------------------------------------------------------------------- live 9:16 preview

const LOGO_SPOTS: Record<string, { x: number; y: number }> = {
  top_left: { x: 0, y: 0 },
  top_center: { x: 0.5, y: 0 },
  top_right: { x: 1, y: 0 },
  middle_left: { x: 0, y: 0.5 },
  center: { x: 0.5, y: 0.5 },
  middle_right: { x: 1, y: 0.5 },
  bottom_left: { x: 0, y: 1 },
  bottom_center: { x: 0.5, y: 1 },
  bottom_right: { x: 1, y: 1 },
};

function LivePreview({
  s,
  style,
  ytid,
  fileUrl,
  thumb,
  logo,
  title,
}: {
  s: GenerateSettings;
  style: CaptionStyle | null;
  ytid: string | null;
  fileUrl: string | null;
  thumb: string | null;
  logo: Asset | null;
  title: string;
}) {
  const W = s.aspect === "16:9" ? 440 : s.aspect === "1:1" ? 340 : s.aspect === "4:5" ? 300 : 280;
  const H = Math.round(W * ({ "9:16": 16 / 9, "1:1": 1, "4:5": 5 / 4, "16:9": 9 / 16 } as const)[s.aspect]);
  const words = useMemo(() => SAMPLE.map((w, i) => ({ w, s: 0.6 + i * 0.36, e: 0.6 + i * 0.36 + 0.32 })), []);
  const chunks = useMemo(() => chunkWords(words, style?.max_words ?? 3), [words, style?.max_words]);
  const total = words[words.length - 1].e + 1.2;
  const [t, setT] = useState(0);
  useEffect(() => {
    let raf = 0;
    const t0 = performance.now();
    const tick = () => {
      setT(((performance.now() - t0) / 1000) % total);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [total]);
  const kwTime = words.find((w) => w.w === "captions")?.s ?? 2;
  let zoom = 1;
  if (s.zoom_start) zoom += 0.18 * Math.max(0, 1 - t / 1.1) ** 2;
  if (s.zoom_key_phrases) zoom += 0.12 * Math.min(1, Math.max(0, (t - kwTime + 0.08) / 0.14)) * Math.min(1, Math.max(0, (kwTime + 1.1 - t) / 0.3));
  // YouTube draws its title bar and controls over the top and bottom ~12% of the player:
  // make the player taller than the frame so those strips fall outside it.
  const ih = Math.max(H / 0.76, (W * 9) / 16 / 0.76);
  const iw = (ih * 16) / 9;
  return (
    <div className="relative mx-auto overflow-hidden rounded-2xl bg-black shadow-card" style={{ width: W, height: H }}>
      <div className="absolute inset-0" style={{ transform: `scale(${zoom})` }}>
        {fileUrl ? (
          <video src={fileUrl} className="h-full w-full object-cover" autoPlay muted loop playsInline />
        ) : ytid ? (
          <iframe
            title="Video preview"
            src={`https://www.youtube-nocookie.com/embed/${ytid}?autoplay=1&mute=1&controls=0&loop=1&playlist=${ytid}&playsinline=1&rel=0&modestbranding=1&cc_load_policy=0&iv_load_policy=3&fs=0&disablekb=1`}
            allow="autoplay; encrypted-media"
            tabIndex={-1}
            className="pointer-events-none absolute border-0"
            style={{ width: iw, height: ih, left: (W - iw) / 2, top: (H - ih) / 2 }}
          />
        ) : thumb ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={thumb} alt="" className="h-full w-full object-cover" />
        ) : (
          <div className="h-full w-full bg-gradient-to-b from-zinc-700 to-zinc-900" />
        )}
      </div>
      {logo?.url && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={logo.url}
          alt=""
          className="absolute object-contain"
          style={(() => {
            const m = W * 0.034;
            const lw = W * 0.16;
            const spot = s.logo_pos ?? LOGO_SPOTS[s.logo_position] ?? LOGO_SPOTS.top_right;
            return { width: lw, left: m + (W - lw - 2 * m) * spot.x, top: m + (H - lw - 2 * m) * spot.y };
          })()}
        />
      )}
      {style && (
        <CaptionOverlay
          chunks={chunks}
          style={{ ...style, emphasis: s.keyword_emphasis, pos: s.caption_pos ?? null }}
          keywords={["captions", "every"]}
          t={t}
          width={W}
          enabled={s.captions}
          transition={s.caption_transition}
          effect={s.caption_effect}
          overlays={
            s.hook_title
              ? [{ kind: "title", text: title || "Your hook title appears here", start: 0, end: 3, style: s.title_style ?? "impact", pos: s.title_pos ?? null }]
              : []
          }
          progressBar={s.progress_bar ? "#FF7A59" : null}
          progressPos={s.progress_position ?? "bottom"}
          duration={total}
        />
      )}
    </div>
  );
}

// ----------------------------------------------------------------------------- main

export function NewProject() {
  const router = useRouter();
  const params = useSearchParams();
  const toast = useToast();
  const { meta, user } = useSession();
  const [step, setStep] = useState<"import" | "customize">("import");
  const [mode, setMode] = useState<"url" | "upload">(params.get("mode") === "upload" ? "upload" : "url");
  const [url, setUrl] = useState(params.get("url") ?? "");
  const [urlInfo, setUrlInfo] = useState<UrlInfo | null>(null);
  const [urlError, setUrlError] = useState("");
  const [checking, setChecking] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [fileUrl, setFileUrl] = useState<string | null>(null);
  const [local, setLocal] = useState<LocalMeta | null>(null);
  const [fileError, setFileError] = useState("");
  const [drag, setDrag] = useState(false);
  const [s, setS] = useState<GenerateSettings>(() => ({
    ...DEFAULT_SETTINGS,
    caption_preset: user.brand_kit?.caption_preset || DEFAULT_SETTINGS.caption_preset,
  }));
  const [logo, setLogo] = useState<Asset | null>(null);
  const [music, setMusic] = useState<Asset | null>(null);
  const [more, setMore] = useState(false);
  const [phase, setPhase] = useState<"idle" | "uploading" | "creating">("idle");
  const [sent, setSent] = useState(0);
  const abort = useRef<AbortController | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const set = <K extends keyof GenerateSettings>(k: K, v: GenerateSettings[K]) => setS((p) => ({ ...p, [k]: v }));
  const presets = meta?.caption_presets ?? {};
  const style = presets[s.caption_preset] ?? null;
  const ytid = mode === "url" ? youtubeId(urlInfo?.url ?? url) : null;
  const thumb = mode === "url" ? urlInfo?.thumbnail ?? null : local?.thumb ?? null;
  const title = mode === "url" ? urlInfo?.title ?? "" : file?.name.replace(/\.[^.]+$/, "") ?? "";

  // Check links as they are pasted (debounced).
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
        setUrlInfo(await api.checkUrl(url.trim()));
      } catch (e) {
        setUrlInfo(null);
        setUrlError((e as Error).message);
      } finally {
        setChecking(false);
      }
    }, 500);
    return () => clearTimeout(t);
  }, [url, mode]);

  useEffect(() => () => void (fileUrl && URL.revokeObjectURL(fileUrl)), [fileUrl]);

  const pickFile = (f: File | undefined | null) => {
    setFileError("");
    setLocal(null);
    if (!f) return;
    if (!/\.(mp4|mov|mkv|webm|m4v|avi)$/i.test(f.name)) return setFileError("Supported formats: MP4, MOV, MKV, WEBM, M4V, AVI.");
    const limit = (meta?.limits.max_upload_mb ?? 4096) * 1024 * 1024;
    if (f.size > limit) return setFileError(`This file is ${fmtBytes(f.size)}; the limit is ${fmtBytes(limit)}.`);
    setFile(f);
    const src = URL.createObjectURL(f);
    setFileUrl(src);
    const v = document.createElement("video");
    v.preload = "metadata";
    v.muted = true;
    v.src = src;
    v.onloadedmetadata = () => {
      setLocal({ duration: v.duration, width: v.videoWidth, height: v.videoHeight, thumb: null });
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
    };
    v.onerror = () => setLocal({ duration: NaN, width: 0, height: 0, thumb: null });
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
        upload_id = (await uploadFile(file, (n) => setSent(n), abort.current.signal)).id;
      }
      setPhase("creating");
      const p = await api.createProject({
        name: title || undefined,
        upload_id,
        url: mode === "url" ? urlInfo!.url : undefined,
        settings: { ...s, logo_key: logo?.key ?? null, music_key: music?.key ?? null },
      });
      router.push(`/app/projects/${p.id}`);
    } catch (e) {
      toast("error", (e as Error).message);
      setPhase("idle");
    }
  };

  // --------------------------------------------------------------------------- step 1: import
  if (step === "import") {
    return (
      <div>
      <PageHeader title="New project" subtitle="Paste a link or upload a video. The AI finds the moments worth posting." />
      <div className="mx-auto max-w-lg rounded-2xl bg-surface p-6 shadow-card sm:p-8">
        <div className="mb-2 flex items-center justify-between">
          <label htmlFor="video-link" className="text-sm font-medium">
            {mode === "url" ? "Import from YouTube:" : "Upload a video:"}
          </label>
          <button
            type="button"
            onClick={() => setMode(mode === "url" ? "upload" : "url")}
            className="text-xs font-medium text-primary hover:underline cursor-pointer"
          >
            {mode === "url" ? "or upload a file" : "or paste a link"}
          </button>
        </div>

        {mode === "url" ? (
          <>
            <div className="relative">
              <svg viewBox="0 0 24 24" className="pointer-events-none absolute left-3 top-1/2 size-5 -translate-y-1/2" aria-hidden>
                <rect x="1.5" y="4.5" width="21" height="15" rx="4.5" fill="#FF0033" />
                <path d="M10 8.8v6.4l5.6-3.2z" fill="#fff" />
              </svg>
              <Input
                id="video-link"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="Or paste a YouTube, TikTok, Vimeo or .mp4 link"
                className="h-11 pl-10"
                autoFocus
              />
            </div>
            {checking && (
              <div className="mt-2 flex items-center gap-2 text-xs text-muted">
                <Loader2 className="size-3.5 animate-spin" /> Fetching video info…
              </div>
            )}
            {urlError && <p className="mt-2 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">{urlError}</p>}
            {urlInfo && (
              <div className={cx("mt-2 flex gap-3 rounded-xl border p-2", urlInfo.importable ? "border-border" : "border-warning/50")}>
                {urlInfo.thumbnail ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={urlInfo.thumbnail} alt="" className="aspect-video w-28 shrink-0 rounded-lg object-cover" />
                ) : (
                  <div className="grid aspect-video w-28 shrink-0 place-items-center rounded-lg bg-surface-2">
                    <FileVideo className="size-5 text-muted" />
                  </div>
                )}
                <div className="min-w-0 py-0.5">
                  <div className="truncate text-sm font-medium">{urlInfo.title || urlInfo.url}</div>
                  <div className="mt-0.5 text-xs text-muted">
                    {[urlInfo.author, urlInfo.duration ? fmtTime(urlInfo.duration) : null, urlInfo.platform].filter(Boolean).join(" · ")}
                  </div>
                  {!urlInfo.importable && <div className="mt-1 text-xs text-warning">{urlInfo.message}</div>}
                  {urlInfo.importable && urlInfo.scan && <div className="mt-1 text-xs text-primary">{urlInfo.message}</div>}
                </div>
              </div>
            )}
          </>
        ) : !file ? (
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
              "flex w-full flex-col items-center rounded-2xl border-2 border-dashed px-6 py-10 text-center transition cursor-pointer",
              drag ? "border-primary bg-primary-soft" : "border-border hover:border-primary/60",
            )}
          >
            <Upload className="size-6 text-primary" />
            <div className="mt-3 text-sm font-medium">Drop a video here or click to browse</div>
            <div className="mt-1 text-xs text-muted">
              MP4, MOV, MKV, WEBM · up to {fmtBytes((meta?.limits.max_upload_mb ?? 4096) * 1024 * 1024)}
            </div>
          </button>
        ) : (
          <div className="flex gap-3 rounded-xl border border-border p-2">
            <div className="grid aspect-video w-28 shrink-0 place-items-center overflow-hidden rounded-lg bg-surface-2">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              {local?.thumb ? <img src={local.thumb} alt="" className="h-full w-full object-cover" /> : <FileVideo className="size-5 text-muted" />}
            </div>
            <div className="min-w-0 flex-1 py-0.5">
              <div className="truncate text-sm font-medium">{file.name}</div>
              <div className="mt-0.5 text-xs text-muted">
                {fmtBytes(file.size)}
                {local && isFinite(local.duration) ? ` · ${fmtTime(local.duration)}` : ""}
              </div>
            </div>
            <button type="button" onClick={() => setFile(null)} className="self-start p-1 text-muted hover:text-text cursor-pointer" aria-label="Remove file">
              <X className="size-4" />
            </button>
          </div>
        )}
        <input ref={inputRef} type="file" accept="video/*,.mkv" className="hidden" onChange={(e) => pickFile(e.target.files?.[0])} />
        {fileError && <p className="mt-2 text-sm text-danger">{fileError}</p>}

        <div className="mt-6">
          <label htmlFor="instructions" className="flex items-center gap-1.5 text-sm font-medium">
            <Lightbulb className="size-4 text-warning" /> Add custom instructions <span className="font-normal text-muted">(optional)</span>
          </label>
          <p className="mt-0.5 text-xs text-muted">Describe what you&apos;re looking for in your own words — the AI focuses the clip selection on it.</p>
          <Input
            id="instructions"
            value={s.instructions}
            onChange={(e) => set("instructions", e.target.value.slice(0, 600))}
            placeholder="E.g. Find all the moments where they share tangible advice and funny stories…"
            className="mt-2"
          />
        </div>
        <div className="mt-5 flex justify-end">
          <Button onClick={() => setStep("customize")} disabled={!ready}>
            <Sparkles className="size-4" /> Generate clips
          </Button>
        </div>
        <p className="mt-10 text-center text-[11px] text-muted">Only import videos you own or have permission to use.</p>
      </div>
      </div>
    );
  }

  // --------------------------------------------------------------------------- step 2: customize
  const go = (
    <Button onClick={generate} loading={busy} disabled={!ready}>
      {phase === "uploading" ? `Uploading… ${file ? Math.round((sent / file.size) * 100) : 0}%` : phase === "creating" ? "Starting…" : "Continue, generate my clips"}
      {!busy && <ArrowRight className="size-4" />}
    </Button>
  );
  const effects = meta?.caption_effects ?? ({ none: "None" } as Record<Effect, string>);
  const transitions = meta?.caption_transitions ?? ({ none: "None" } as Record<Transition, string>);

  return (
    <div>
      <PageHeader title="Customize your clips" subtitle={title || undefined} />
      <div className="mb-4 flex items-center justify-between">
        <button
          type="button"
          onClick={() => !busy && setStep("import")}
          className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-text cursor-pointer"
        >
          <ArrowLeft className="size-4" /> Back
        </button>
        {go}
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="divide-y divide-border rounded-2xl bg-surface px-5 shadow-card">
          <div className="pt-5">
            <h2 className="text-lg font-semibold">Customize your video</h2>
            {title && <p className="mt-0.5 truncate text-sm text-muted">{title}</p>}
          </div>

          <div className="grid gap-x-6 sm:grid-cols-2">
            <Section title="Language spoken" info="Auto-detect works for most videos; pick it to skip detection.">
              <Select value={s.language} onChange={(v) => set("language", v)} options={LANGS.map(([value, label]) => ({ value, label }))} />
            </Section>
            <Section title="Size" info="Portrait 9:16 is the format for YouTube Shorts, Reels and TikTok.">
              <Select value={s.aspect} onChange={(v) => set("aspect", v as GenerateSettings["aspect"])} options={SIZES} />
            </Section>
            <Section
              title="Clip length"
              info="Every clip lands inside this range: the AI adds the setup or trims to the payoff to hit it."
              className="sm:col-span-2"
            >
              <LengthPicker s={s} onChange={(patch) => setS((x) => ({ ...x, ...patch }))} />
            </Section>
            <Section title="Number of clips">
              <div className="flex items-center gap-3">
                <div className="flex h-10 items-center rounded-xl border border-border px-3 text-sm font-medium">{s.count}</div>
                <input
                  type="range"
                  min={1}
                  max={meta?.limits.max_clips ?? 20}
                  value={s.count}
                  aria-label="Number of clips"
                  onChange={(e) => set("count", Number(e.target.value))}
                  className="flex-1"
                />
              </div>
            </Section>
            <Section title="Template" info="Tells the AI what kind of video this is, so it weighs the right signals.">
              <Select
                value={s.genre}
                onChange={(v) => set("genre", v)}
                options={Object.entries(meta?.genres ?? { auto: "Auto-detect" }).map(([value, label]) => ({ value, label: value === "auto" ? "Default style (auto-detect)" : label }))}
              />
            </Section>
            <Section title="Framing">
              <Select
                value={s.crop_mode}
                onChange={(v) => set("crop_mode", v as GenerateSettings["crop_mode"])}
                options={[
                  { value: "auto", label: "Smart: auto-pick the best layout" },
                  { value: "facecam", label: "Gameplay / stream: facecam on top" },
                  { value: "center", label: "Center crop" },
                  { value: "fit", label: "Fit whole frame (blurred fill)" },
                ]}
              />
            </Section>
          </div>

          <Section title="Caption settings" info="Captions are burned into the video; most Shorts are watched without sound.">
            <div className="mb-4 flex flex-wrap items-center gap-3">
              <span className="text-xs text-muted">Caption language</span>
              <Select
                value={s.caption_language}
                onChange={(v) => set("caption_language", v as GenerateSettings["caption_language"])}
                options={[
                  { value: "english", label: "English (translated if needed)" },
                  { value: "original", label: "Same language as the video" },
                ]}
                className="h-8 w-52 text-xs"
              />
            </div>
            <div className="text-xs text-muted">Caption transition</div>
            <div className="mt-1.5">
              <Chips value={s.caption_transition} onChange={(v) => set("caption_transition", v)} options={Object.entries(transitions) as [Transition, string][]} />
            </div>
            <div className="mt-4 text-xs text-muted">Caption style</div>
            <div className="mt-1.5 grid grid-cols-3 gap-2.5 rounded-xl bg-surface-2 p-2.5 sm:grid-cols-4 xl:grid-cols-6">
              <Tile selected={!s.captions} onClick={() => set("captions", false)} label="None" bg={null}>
                <Ban className="size-5 text-white/70" />
              </Tile>
              {Object.entries(presets).map(([key, st]) => (
                <Tile
                  key={key}
                  selected={s.captions && s.caption_preset === key}
                  onClick={() => setS((x) => ({ ...x, captions: true, caption_preset: key }))}
                  label={st.label}
                  bg={thumb}
                >
                  <CaptionSample style={st} scale={0.2} />
                </Tile>
              ))}
            </div>
            <div className="mt-4 text-xs text-muted">Caption position: pick a spot, then nudge it with the arrows</div>
            <div className="mt-1.5">
              <PositionPicker label="Caption position" value={s.caption_pos} onChange={(v) => set("caption_pos", v)} />
            </div>
            <div className="mt-4 text-xs text-muted">Caption effects</div>
            <div className="mt-1.5 grid grid-cols-3 gap-2.5 rounded-xl bg-surface-2 p-2.5 sm:grid-cols-5">
              {(Object.entries(effects) as [Effect, string][]).map(([key, label]) => (
                <Tile key={key} selected={s.caption_effect === key} onClick={() => set("caption_effect", key)} label={label} bg={thumb}>
                  {key === "none" ? <Ban className="size-5 text-white/70" /> : style ? <CaptionSample style={style} scale={0.2} effect={key} /> : null}
                </Tile>
              ))}
            </div>
          </Section>

          <Section title="Auto-highlight keywords" info="Colours the important words in each caption.">
            <Switch checked={s.keyword_emphasis} onChange={(v) => set("keyword_emphasis", v)} label="Enabled" />
          </Section>

          <Section title="Automatically zoom in" info="Quick punch-in zooms keep viewers' eyes on the screen.">
            <Switch checked={s.zoom_start} onChange={(v) => set("zoom_start", v)} label="At start" hint="A zoom-out reveal in the first second" />
            <Switch checked={s.zoom_key_phrases} onChange={(v) => set("zoom_key_phrases", v)} label="At key phrases" hint="Punch in when an important word is said" />
          </Section>

          <Section title="Viral boosters" info="Common practices that help Shorts hold viewers to the end.">
            <Switch checked={s.hook_title} onChange={(v) => set("hook_title", v)} label="Hook title for the first 3 seconds" hint="A designed title card that pops in, so viewers know why to stay" />
            {s.hook_title && (
              <div className="mb-3 mt-2 space-y-3 rounded-xl bg-surface-2 p-3">
                <TitleStylePicker value={s.title_style ?? "impact"} onChange={(v) => set("title_style", v)} bg={thumb} />
                <div>
                  <div className="mb-1.5 text-xs text-muted">Title position</div>
                  <PositionPicker label="Title position" value={s.title_pos} onChange={(v) => set("title_pos", v)} />
                </div>
              </div>
            )}
            <Switch checked={s.progress_bar} onChange={(v) => set("progress_bar", v)} label="Progress bar" hint="A thin bar that fills as the clip plays" />
            {s.progress_bar && (
              <div className="mb-2 ml-1">
                <Chips
                  value={s.progress_position ?? "bottom"}
                  onChange={(v) => set("progress_position", v)}
                  options={[
                    ["bottom", "Bottom edge"],
                    ["top", "Top edge"],
                  ]}
                />
              </div>
            )}
            <Switch checked={s.silence_removal} onChange={(v) => set("silence_removal", v)} label="Remove silent pauses" hint="Tighter pacing: cuts gaps longer than 0.7 s" />
            <Switch
              checked={s.comparison}
              onChange={(v) => set("comparison", v)}
              label="Detect comparison videos (A vs B vs C)"
              hint="Only used when the video really compares versions (same action in different games, years, products). Normal videos are never split."
            />
            {s.comparison && (
              <div className="mb-2 mt-2 space-y-3 rounded-xl bg-surface-2 p-3">
                <div className="text-xs text-muted">How the versions play</div>
                <ComparePlayPicker value={s.compare_play ?? "turns"} onChange={(v) => set("compare_play", v)} />
                {s.compare_play === "together" && (
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="text-xs text-muted">Sound</span>
                    <Chips
                      value={s.compare_audio ?? "active"}
                      onChange={(v) => set("compare_audio", v)}
                      options={[
                        ["active", "Top video only"],
                        ["mix", "Mix both"],
                      ]}
                    />
                  </div>
                )}
              </div>
            )}
          </Section>

          <Section title="Logo" info="Shown on every clip; Auto puts it in the top-right corner.">
            <AssetBox kind="logo" asset={logo} onChange={setLogo}>
              <PositionPicker label="Logo position" value={s.logo_pos} onChange={(v) => set("logo_pos", v)} />
            </AssetBox>
          </Section>

          <Section title="Music" info="Plays quietly under every clip and ducks automatically while people talk.">
            <AssetBox kind="music" asset={music} onChange={setMusic}>
              <label className="flex max-w-64 items-center gap-2">
                Volume
                <input
                  type="range"
                  min={0.04}
                  max={0.5}
                  step={0.02}
                  value={s.music_volume}
                  onChange={(e) => set("music_volume", Number(e.target.value))}
                  className="flex-1"
                />
              </label>
              {music?.url && <audio src={music.url} controls className="h-8 w-full max-w-64" />}
            </AssetBox>
          </Section>

          <div className="py-4">
            <button
              type="button"
              onClick={() => setMore((m) => !m)}
              className="inline-flex items-center gap-1.5 text-sm font-medium text-muted hover:text-text cursor-pointer"
              aria-expanded={more}
            >
              <ChevronDown className={cx("size-4 transition", more && "rotate-180")} /> More AI options
            </button>
            {more && (
              <div className="mt-3 grid gap-x-6 gap-y-3 sm:grid-cols-2">
                <label className="block text-sm">
                  <span className="text-xs text-muted">Mood</span>
                  <Select
                    value={s.mood}
                    onChange={(v) => set("mood", v)}
                    options={(meta?.moods ?? ["any"]).map((m) => ({ value: m, label: m === "any" ? "Best overall" : m[0].toUpperCase() + m.slice(1) }))}
                  />
                </label>
                <label className="block text-sm">
                  <span className="text-xs text-muted">Look for moments</span>
                  <Select value={s.position} onChange={(v) => set("position", v)} options={[["any", "Anywhere"], ["start", "Near the start"], ["middle", "In the middle"], ["end", "Near the end"]].map(([value, label]) => ({ value, label }))} />
                </label>
                <label className="block text-sm">
                  <span className="text-xs text-muted">Copy tone</span>
                  <Select value={s.tone} onChange={(v) => set("tone", v)} options={(meta?.tones ?? ["compelling"]).map((t) => ({ value: t, label: t === "compelling" ? "Compelling but truthful" : t[0].toUpperCase() + t.slice(1) }))} />
                </label>
                <label className="block text-sm">
                  <span className="text-xs text-muted">Export quality</span>
                  <Select value={s.quality} onChange={(v) => set("quality", v as GenerateSettings["quality"])} options={[["draft", "Draft (720p, fastest)"], ["standard", "Standard (1080p)"], ["high", "High (1080p, best)"]].map(([value, label]) => ({ value, label }))} />
                </label>
                <div className="sm:col-span-2">
                  <div className="text-xs text-muted">Write titles and captions for</div>
                  <div className="mt-1.5 flex flex-wrap gap-2">
                    {Object.entries(PLATFORM_LABELS).map(([p, label]) => {
                      const on = s.platforms.includes(p);
                      return (
                        <button
                          key={p}
                          type="button"
                          onClick={() => set("platforms", on ? s.platforms.filter((x) => x !== p) : [...s.platforms, p])}
                          className={cx("h-8 rounded-full border px-3 text-xs transition cursor-pointer", on ? "border-primary bg-primary-soft text-primary" : "border-border text-muted hover:text-text")}
                          aria-pressed={on}
                        >
                          {label}
                        </button>
                      );
                    })}
                  </div>
                </div>
                <Switch checked={s.context_padding} onChange={(v) => set("context_padding", v)} label="Context padding" hint="A short lead-in and tail around each clip" />
                <Switch
                  checked={s.use_llm}
                  onChange={(v) => set("use_llm", v)}
                  label="Local AI editor"
                  hint={meta?.llm.available ? `${meta.llm.model} re-reads the best moments and writes the copy` : meta?.llm.reason ?? "Unavailable"}
                />
              </div>
            )}
          </div>

          <div className="py-5">{go}</div>
        </div>

        <div className="lg:sticky lg:top-5 lg:self-start">
          <div className="rounded-2xl bg-surface p-5 shadow-card">
            <div className="mx-auto mb-1 w-fit rounded-xl bg-surface-2 p-1 text-sm font-medium">
              <span className="block rounded-lg bg-surface px-4 py-1 shadow-sm">Preview</span>
            </div>
            <p className="mb-4 text-center text-xs text-muted">This is a preview of how your video will look.</p>
            <LivePreview s={s} style={style} ytid={ytid} fileUrl={mode === "upload" ? fileUrl : null} thumb={thumb} logo={logo} title={title} />
            {s.instructions && (
              <p className="mt-4 rounded-xl bg-primary-soft px-3 py-2 text-xs text-primary">
                <Sparkles className="mr-1 inline size-3.5" />
                AI focus: {s.instructions}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
