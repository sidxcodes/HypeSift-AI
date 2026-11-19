"use client";

import { Copy, Download, FileText, Loader2, Search, Upload } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useToast } from "@/components/toast";
import { Badge, Button, cx, EmptyState, Input, Progress, Skeleton } from "@/components/ui";
import { api, DEFAULT_SETTINGS, fmtTime, uploadFile } from "@/lib/api";
import type { Project } from "@/lib/types";

type Seg = { s: number; e: number; t: string };

function srtTime(x: number) {
  const ms = Math.round(x * 1000);
  const p = (n: number, l = 2) => String(n).padStart(l, "0");
  return `${p(Math.floor(ms / 3600000))}:${p(Math.floor((ms % 3600000) / 60000))}:${p(Math.floor((ms % 60000) / 1000))},${p(ms % 1000, 3)}`;
}

function save(name: string, text: string) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

export default function TranscriptsPage() {
  const toast = useToast();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [tr, setTr] = useState<{ language: string; engine: string; segments: Seg[] } | null>(null);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(() => api.projects().then(setProjects).catch(() => setProjects([])), []);
  useEffect(() => {
    load();
  }, [load]);
  const working = (projects ?? []).some((p) => p.status === "processing" || p.status === "queued");
  useEffect(() => {
    if (!working) return;
    const i = setInterval(load, 2000);
    return () => clearInterval(i);
  }, [working, load]);

  useEffect(() => {
    setTr(null);
    if (sel) api.transcript(sel).then(setTr).catch((e) => toast("error", e.message));
  }, [sel, toast]);

  const start = async (body: { url?: string; upload_id?: string; name?: string }) => {
    const p = await api.createProject({ ...body, settings: { ...DEFAULT_SETTINGS, transcript_only: true, use_llm: false } });
    setUrl("");
    await load();
    setSel(p.id);
    toast("info", "Transcribing… this takes about a tenth of the video's length on a GPU.");
  };
  const fromLink = async () => {
    setBusy(true);
    try {
      const info = await api.checkUrl(url.trim());
      if (!info.importable) throw new Error(info.message);
      await start({ url: info.url, name: info.title ?? undefined });
    } catch (e) {
      toast("error", (e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const fromFile = async (f?: File | null) => {
    if (!f) return;
    setBusy(true);
    try {
      const up = await uploadFile(f, () => {});
      await start({ upload_id: up.id, name: f.name.replace(/\.[^.]+$/, "") });
    } catch (e) {
      toast("error", (e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const list = (projects ?? []).filter((p) => p.status !== "draft");
  const current = list.find((p) => p.id === sel);
  const segs = useMemo(() => (tr?.segments ?? []).filter((s) => !q || s.t.toLowerCase().includes(q.toLowerCase())), [tr, q]);
  const name = (current?.name ?? "transcript").replace(/[^\w-]+/g, "-").slice(0, 60);
  const txt = (tr?.segments ?? []).map((s) => s.t.trim()).join(" ");

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Transcript generator</h1>
        <p className="mt-1 text-sm text-muted">Turn any video or YouTube link into a timestamped transcript, on your own computer.</p>
      </div>

      <div className="flex flex-wrap gap-2 rounded-2xl border border-border p-4">
        <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="Paste a YouTube or video link" className="min-w-64 flex-1" aria-label="Video link" />
        <Button onClick={fromLink} disabled={!url.trim() || busy} loading={busy}>
          <FileText className="size-4" /> Transcribe
        </Button>
        <Button variant="secondary" onClick={() => fileRef.current?.click()} disabled={busy}>
          <Upload className="size-4" /> Upload a file
        </Button>
        <input ref={fileRef} type="file" accept="video/*,.mkv" className="hidden" onChange={(e) => fromFile(e.target.files?.[0])} />
      </div>

      <div className="grid gap-5 lg:grid-cols-[280px_1fr]">
        <div className="space-y-1">
          {!projects ? (
            <Skeleton className="h-40" />
          ) : list.length === 0 ? (
            <p className="text-sm text-muted">No videos yet.</p>
          ) : (
            list.map((p) => (
              <button
                key={p.id}
                onClick={() => setSel(p.id)}
                className={cx("w-full rounded-xl px-3 py-2 text-left transition cursor-pointer", sel === p.id ? "bg-primary-soft" : "hover:bg-surface-2")}
              >
                <div className="truncate text-sm font-medium">{p.name}</div>
                <div className="flex items-center gap-2 text-xs text-muted">
                  {p.duration ? fmtTime(p.duration) : "–"}
                  {p.settings?.transcript_only && <Badge>Transcript only</Badge>}
                  {(p.status === "processing" || p.status === "queued") && <Loader2 className="size-3 animate-spin" />}
                  {p.status === "failed" && <span className="text-danger">failed</span>}
                </div>
              </button>
            ))
          )}
        </div>

        <div className="min-w-0 rounded-2xl border border-border">
          {!current ? (
            <EmptyState icon={<FileText className="size-6" />} title="Pick a video" body="Choose a video on the left, or transcribe a new one." />
          ) : current.status !== "ready" ? (
            <div className="p-6">
              <div className="text-sm font-medium">{current.status === "failed" ? current.error : current.job?.message || "Waiting to start…"}</div>
              {current.job && current.status !== "failed" && <Progress value={current.job.progress} className="mt-3" />}
            </div>
          ) : !tr ? (
            <Skeleton className="m-4 h-64" />
          ) : (
            <div>
              <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-3">
                <div className="relative min-w-48 flex-1">
                  <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
                  <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search the transcript" className="h-9 pl-9" />
                </div>
                <span className="text-xs text-muted">
                  {tr.language} · {tr.engine}
                </span>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={async () => {
                    await navigator.clipboard.writeText(txt);
                    toast("success", "Transcript copied.");
                  }}
                >
                  <Copy className="size-4" /> Copy
                </Button>
                <Button variant="secondary" size="sm" onClick={() => save(`${name}.txt`, (tr.segments ?? []).map((s) => `[${fmtTime(s.s)}] ${s.t.trim()}`).join("\n"))}>
                  <Download className="size-4" /> TXT
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => save(`${name}.srt`, tr.segments.map((s, i) => `${i + 1}\n${srtTime(s.s)} --> ${srtTime(s.e)}\n${s.t.trim()}\n`).join("\n"))}
                >
                  <Download className="size-4" /> SRT
                </Button>
              </div>
              <div className="max-h-[60vh] space-y-2 overflow-y-auto p-4 scrollbar-thin">
                {segs.length === 0 ? (
                  <p className="text-sm text-muted">{q ? "No matches." : "No speech found."}</p>
                ) : (
                  segs.map((s, i) => (
                    <p key={i} className="flex gap-3 text-sm leading-relaxed">
                      <span className="w-12 shrink-0 pt-px text-xs tabular-nums text-muted">{fmtTime(s.s)}</span>
                      <span>{s.t.trim()}</span>
                    </p>
                  ))
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
