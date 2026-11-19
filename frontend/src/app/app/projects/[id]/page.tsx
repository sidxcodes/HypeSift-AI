"use client";

import { ChevronRight, Clapperboard, Home, Loader2, RefreshCw, Rows3, Sparkles, Trash2, Upload, X } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Assistant } from "@/components/Assistant";
import { ClipDrawer } from "@/components/ClipDrawer";
import { ClipRow } from "@/components/ClipRow";
import { PostDrawer } from "@/components/PostDrawer";
import { useToast } from "@/components/toast";
import { Button, cx, EmptyState, Select, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import type { Clip, Goal, Job, Project } from "@/lib/types";

type Sort = Goal | "time" | "length";
const SORTS: { value: Sort; label: string }[] = [
  { value: "general", label: "✨ General mix" },
  { value: "views", label: "🔥 More views" },
  { value: "trust", label: "🤝 Build trust" },
  { value: "educate", label: "🎓 Teach something" },
  { value: "entertain", label: "😂 Entertain" },
  { value: "time", label: "Timeline order" },
  { value: "length", label: "Shortest first" },
];

const STEPS: { label: string; stages: string[] }[] = [
  { label: "Processing", stages: ["queued", "ingest", "prepare"] },
  { label: "Transcribing", stages: ["transcribe"] },
  { label: "Analyzing", stages: ["analyze", "rank"] },
  { label: "Generating clips", stages: ["render", "publish"] },
];

function Banner({ job, onCancel }: { job: Job; onCancel: () => void }) {
  const idx = Math.max(0, STEPS.findIndex((s) => s.stages.includes(job.stage)));
  return (
    <div className="flex flex-wrap items-center gap-4 rounded-2xl bg-banner px-5 py-3.5 text-white">
      <div className="relative grid size-9 shrink-0 place-items-center rounded-full bg-white/15">
        <Loader2 className="size-5 animate-spin" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-semibold">
          Your clips are being generated… <span className="font-normal opacity-80">{Math.round(job.progress * 100)}%</span>
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs">
          {STEPS.map((s, i) => (
            <span key={s.label} className="inline-flex items-center gap-1.5">
              <span className={cx(i < idx ? "opacity-70" : i === idx ? "font-semibold" : "opacity-45")}>{s.label}</span>
              {i < STEPS.length - 1 && <ChevronRight className="size-3 opacity-50" />}
            </span>
          ))}
          <span className="ml-1 truncate opacity-70">· {job.message}</span>
        </div>
      </div>
      <button onClick={onCancel} className="rounded-lg px-2 py-1.5 text-xs opacity-80 hover:bg-white/10 hover:opacity-100 cursor-pointer">
        Cancel
      </button>
      <Link href="/app/new" className="inline-flex h-9 items-center gap-1.5 rounded-xl bg-white px-3.5 text-sm font-medium text-banner hover:bg-white/90">
        <Upload className="size-4" /> Upload another video
      </Link>
    </div>
  );
}

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const toast = useToast();
  const [p, setP] = useState<Project | null>(null);
  const [error, setError] = useState("");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [tab, setTab] = useState<"all" | "scheduled" | "posted">("all");
  const [sort, setSort] = useState<Sort>("general");
  const [compact, setCompact] = useState(false);
  const [detailsId, setDetailsId] = useState<string | null>(null);
  const [postId, setPostId] = useState<string | null>(null);
  const [ask, setAsk] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const load = useCallback(async () => {
    try {
      const [proj, js] = await Promise.all([api.project(id), api.jobs({ project_id: id, active: true })]);
      setP(proj);
      setJobs(js);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const busy = jobs.length > 0 || p?.status === "processing" || p?.status === "queued" || p?.clips?.some((c) => c.render_status === "rendering");
  useEffect(() => {
    if (!busy) return;
    const i = setInterval(load, 1500);
    return () => clearInterval(i);
  }, [busy, load]);

  const all = p?.clips ?? [];
  const counts = {
    all: all.length,
    scheduled: all.filter((c) => c.post?.status === "scheduled").length,
    posted: all.filter((c) => c.post?.status === "posted").length,
  };
  const clips = useMemo(() => {
    let cs = [...all];
    if (tab !== "all") cs = cs.filter((c) => c.post?.status === tab);
    const g = (c: Clip, k: Goal) => (k === "views" ? c.insights?.viral : c.insights?.goals?.[k]) ?? c.score;
    cs.sort((a, b) =>
      sort === "time" ? a.start - b.start : sort === "length" ? (a.output_duration ?? a.duration) - (b.output_duration ?? b.duration) : g(b, sort) - g(a, sort),
    );
    return cs;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p, sort, tab]);

  if (error)
    return (
      <EmptyState
        icon={<Clapperboard className="size-6" />}
        title="Project unavailable"
        body={error}
        action={
          <Link href="/app/projects">
            <Button variant="secondary">Back to projects</Button>
          </Link>
        }
      />
    );
  if (!p) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-5 w-96" />
        <Skeleton className="h-16" />
        {[0, 1].map((i) => (
          <Skeleton key={i} className="h-64" />
        ))}
      </div>
    );
  }

  const genJob = p.job;
  const running = genJob && genJob.kind === "generate" && (genJob.status === "running" || genJob.status === "queued");
  const discoverJobs = jobs.filter((j) => j.kind === "discover");

  const regenerate = async () => {
    try {
      await api.regenerate(p.id, p.settings);
      toast("info", "Re-running AI Generate with the same settings.");
      load();
    } catch (e) {
      toast("error", (e as Error).message);
    }
  };
  const removeProject = async () => {
    if (!confirm(`Delete “${p.name}” and all its clips? This can't be undone.`)) return;
    await api.deleteProject(p.id);
    router.replace("/app/projects");
  };
  const removeClip = async (c: Clip) => {
    if (!confirm(`Delete “${c.title}”? This can't be undone.`)) return;
    await api.deleteClip(c.id);
    load();
  };
  const removeSelected = async () => {
    if (!confirm(`Delete ${selected.size} selected clip${selected.size === 1 ? "" : "s"}? This can't be undone.`)) return;
    await Promise.all([...selected].map((cid) => api.deleteClip(cid)));
    setSelected(new Set());
    load();
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <nav className="flex min-w-0 items-center gap-1.5 text-sm" aria-label="Breadcrumb">
          <Link href="/app/projects" className="inline-flex items-center gap-1.5 text-muted hover:text-text">
            <Home className="size-4" /> Projects
          </Link>
          <ChevronRight className="size-4 shrink-0 text-muted" />
          <span className="truncate font-medium">{p.name}</span>
        </nav>
        <div className="flex gap-1">
          <Button variant="ghost" size="sm" onClick={regenerate} disabled={!!busy} title="Run AI Generate again">
            <RefreshCw className="size-4" /> Regenerate
          </Button>
          <Button variant="ghost" size="sm" onClick={removeProject} aria-label="Delete project">
            <Trash2 className="size-4" />
          </Button>
        </div>
      </div>

      {running && genJob && <Banner job={genJob} onCancel={() => api.cancelJob(genJob.id).then(load)} />}
      {discoverJobs.map((j) => (
        <Banner key={j.id} job={j} onCancel={() => api.cancelJob(j.id).then(load)} />
      ))}
      {p.status === "failed" && (
        <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-danger/30 bg-danger/5 px-5 py-3.5 text-sm">
          <span className="flex-1 text-danger">{p.error ?? "This project didn't finish."}</span>
          <Button size="sm" onClick={regenerate}>
            Try again
          </Button>
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border">
        <div className="flex gap-1" role="tablist">
          {(["all", "scheduled", "posted"] as const).map((t) => (
            <button
              key={t}
              role="tab"
              aria-selected={tab === t}
              onClick={() => setTab(t)}
              className={cx(
                "-mb-px border-b-2 px-3 pb-2.5 pt-1 text-sm transition cursor-pointer",
                tab === t ? "border-primary font-medium text-text" : "border-transparent text-muted hover:text-text",
              )}
            >
              {t === "all" ? "All clips" : t === "scheduled" ? "Scheduled" : "Posted"}
              {counts[t] > 0 && <span className="ml-1.5 text-xs text-muted">{counts[t]}</span>}
            </button>
          ))}
        </div>
        <div className="mb-2 flex items-center gap-2">
          {selected.size > 0 && (
            <Button variant="danger" size="sm" onClick={removeSelected}>
              <Trash2 className="size-4" /> Delete {selected.size}
            </Button>
          )}
          <Button variant={ask ? "secondary" : "ghost"} size="sm" onClick={() => setAsk((a) => !a)} disabled={p.status !== "ready"}>
            {ask ? <X className="size-4" /> : <Sparkles className="size-4" />} Ask AI
          </Button>
          <button
            onClick={() => setCompact((c) => !c)}
            className={cx("grid size-8 place-items-center rounded-lg cursor-pointer", compact ? "bg-surface-2 text-text" : "text-muted hover:bg-surface-2")}
            aria-label="Compact view"
            aria-pressed={compact}
          >
            <Rows3 className="size-4" />
          </button>
          <span className="whitespace-nowrap text-xs text-muted">Sort by</span>
          <Select value={sort} onChange={(v) => setSort(v as Sort)} options={SORTS} className="h-8 w-44 text-xs" />
        </div>
      </div>

      {ask && <Assistant projectId={p.id} onAction={load} disabled={p.status !== "ready"} />}

      {clips.length > 0 ? (
        <div>
          {clips.map((c) => (
            <ClipRow
              key={c.id}
              clip={c}
              goal={sort}
              compact={compact}
              onPost={() => setPostId(c.id)}
              onDetails={() => setDetailsId(c.id)}
              onFavorite={() => api.favorite(c.id, !c.favorite).then(load)}
              onDelete={() => removeClip(c)}
              selected={selected.has(c.id)}
              onSelect={(v) =>
                setSelected((s) => {
                  const n = new Set(s);
                  if (v) n.add(c.id);
                  else n.delete(c.id);
                  return n;
                })
              }
            />
          ))}
        </div>
      ) : running || p.status === "queued" ? (
        <div>
          {[0, 1].map((i) => (
            <div key={i} className="flex gap-3 border-b border-border py-5">
              <Skeleton className="aspect-[9/16] w-[150px] shrink-0" />
              <div className="flex-1 space-y-3">
                <Skeleton className="h-5 w-2/3" />
                <Skeleton className="h-3 w-40" />
                <div className="flex gap-2 opacity-60">
                  <Skeleton className="h-8 w-24" />
                  <Skeleton className="h-8 w-24" />
                  <Skeleton className="h-8 w-32" />
                </div>
                <Skeleton className="h-24 max-w-2xl" />
              </div>
            </div>
          ))}
        </div>
      ) : p.status === "ready" && p.analysis?.transcript_only ? (
        <EmptyState
          icon={<Clapperboard className="size-6" />}
          title="Transcript ready"
          body="This project was made with the Transcript generator."
          action={
            <Link href="/app/transcripts">
              <Button variant="secondary">Open Transcript generator</Button>
            </Link>
          }
        />
      ) : p.status === "ready" ? (
        <EmptyState
          icon={<Clapperboard className="size-6" />}
          title={tab === "all" ? "No clips" : tab === "scheduled" ? "Nothing scheduled yet" : "Nothing posted yet"}
          body={tab === "all" ? "Ask AI to find more moments." : "Use “Post or schedule” on a clip."}
        />
      ) : null}

      <ClipDrawer clip={all.find((c) => c.id === detailsId) ?? null} onClose={() => setDetailsId(null)} onChange={load} />
      <PostDrawer clip={all.find((c) => c.id === postId) ?? null} onClose={() => setPostId(null)} onChange={load} />
    </div>
  );
}
