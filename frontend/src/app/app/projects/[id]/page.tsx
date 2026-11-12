"use client";

import { ArrowLeft, Clapperboard, RefreshCw, Search, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Assistant } from "@/components/Assistant";
import { ClipCard } from "@/components/ClipCard";
import { ClipDrawer } from "@/components/ClipDrawer";
import { JobProgress } from "@/components/JobProgress";
import { useToast } from "@/components/toast";
import { Badge, Button, Card, EmptyState, Input, Segmented, Skeleton } from "@/components/ui";
import { api, fmtTime } from "@/lib/api";
import type { Clip, Job, Project } from "@/lib/types";

type Sort = "score" | "time" | "length";

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const toast = useToast();
  const [p, setP] = useState<Project | null>(null);
  const [error, setError] = useState("");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [sort, setSort] = useState<Sort>("score");
  const [filter, setFilter] = useState("all");
  const [q, setQ] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);

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

  const clips = useMemo(() => {
    let cs = [...(p?.clips ?? [])];
    if (filter === "favorites") cs = cs.filter((c) => c.favorite);
    if (filter === "short") cs = cs.filter((c) => (c.output_duration ?? c.duration) <= 30);
    if (filter === "long") cs = cs.filter((c) => (c.output_duration ?? c.duration) > 30);
    if (q.trim()) {
      const t = q.toLowerCase();
      cs = cs.filter((c) => c.title.toLowerCase().includes(t) || c.text.toLowerCase().includes(t));
    }
    cs.sort((a, b) => (sort === "score" ? b.score - a.score : sort === "time" ? a.start - b.start : (a.output_duration ?? a.duration) - (b.output_duration ?? b.duration)));
    return cs;
  }, [p, sort, filter, q]);

  if (error) return <EmptyState icon={<Clapperboard className="size-6" />} title="Project unavailable" body={error} action={<Link href="/app/projects"><Button variant="secondary">Back to projects</Button></Link>} />;
  if (!p) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-72" />
        <Skeleton className="h-32" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-96" />)}</div>
      </div>
    );
  }

  const genJob = p.job;
  const openClip = p.clips?.find((c) => c.id === openId) ?? null;
  const discoverJobs = jobs.filter((j) => j.kind === "discover");
  const a = p.analysis as Record<string, string | number | boolean | undefined>;

  const regenerate = async () => {
    try {
      await api.regenerate(p.id, p.settings);
      toast("info", "Re-running AI Generate with the same settings.");
      load();
    } catch (e) {
      toast("error", (e as Error).message);
    }
  };
  const remove = async () => {
    if (!confirm(`Delete “${p.name}” and all its clips? This can't be undone.`)) return;
    await api.deleteProject(p.id);
    router.replace("/app/projects");
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <Link href="/app/projects" className="inline-flex items-center gap-1 text-sm text-muted hover:text-text">
            <ArrowLeft className="size-4" /> Projects
          </Link>
          <h1 className="mt-1 truncate font-display text-2xl font-bold tracking-tight">{p.name}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted">
            {p.duration != null && <span>{fmtTime(p.duration)} source</span>}
            {p.width && <span>{p.width}×{p.height}</span>}
            {a.genre && <span>Detected: {String(a.genre)}</span>}
            {a.language && a.language !== "none" && <span>Language: {String(a.language)}</span>}
            {a.seconds && <span>Processed in {Math.round(Number(a.seconds))}s</span>}
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" onClick={regenerate} disabled={busy}>
            <RefreshCw className="size-4" /> Regenerate
          </Button>
          <Button variant="danger" size="sm" onClick={remove} aria-label="Delete project">
            <Trash2 className="size-4" />
          </Button>
        </div>
      </div>

      {genJob && genJob.kind === "generate" && (genJob.status === "running" || genJob.status === "queued" || genJob.status === "failed") && (
        <JobProgress job={genJob} onCancel={() => api.cancelJob(genJob.id).then(load)} />
      )}
      {discoverJobs.map((j) => (
        <JobProgress key={j.id} job={j} onCancel={() => api.cancelJob(j.id).then(load)} />
      ))}

      {p.status === "ready" && (
        <Card className="flex flex-wrap items-center gap-x-6 gap-y-2 px-5 py-3 text-sm">
          <span className="font-medium">{p.clips?.length ?? 0} clips</span>
          <span className="text-muted">Speech: {String(a.stt_engine ?? "–")}</span>
          <span className="text-muted">Ranking: {String(a.ranking_engine ?? "–")}</span>
          <span className="text-muted">{Number(a.words ?? 0).toLocaleString()} words · {String(a.scene_cuts ?? 0)} scene cuts</span>
        </Card>
      )}

      <Assistant projectId={p.id} onAction={load} disabled={p.status !== "ready"} />

      {(p.clips?.length ?? 0) > 0 && (
        <div className="flex flex-wrap items-center gap-3">
          <Segmented value={sort} onChange={setSort} options={[{ value: "score", label: "Top score" }, { value: "time", label: "Timeline" }, { value: "length", label: "Length" }]} />
          <Segmented value={filter} onChange={setFilter} options={[{ value: "all", label: "All" }, { value: "short", label: "≤30s" }, { value: "long", label: ">30s" }, { value: "favorites", label: "★" }]} />
          <div className="relative ml-auto w-full sm:w-64">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search clip transcripts" className="pl-9" aria-label="Search clips" />
          </div>
        </div>
      )}

      {clips.length > 0 ? (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
          {clips.map((c: Clip) => (
            <ClipCard
              key={c.id}
              clip={c}
              index={(p.clips ?? []).indexOf(c)}
              onOpen={() => setOpenId(c.id)}
              onFavorite={() => api.favorite(c.id, !c.favorite).then(load)}
            />
          ))}
        </div>
      ) : p.status === "ready" ? (
        <EmptyState icon={<Search className="size-6" />} title="No clips match" body="Try a different filter or search." />
      ) : p.status === "failed" ? (
        <EmptyState
          icon={<Clapperboard className="size-6" />}
          title="This project didn't finish"
          body={p.error ?? "Something went wrong."}
          action={<Button onClick={regenerate}>Try again</Button>}
        />
      ) : (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Card key={i} className="overflow-hidden">
              <Skeleton className="aspect-[9/14] rounded-none" />
              <div className="space-y-2 p-4">
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-3 w-1/2" />
              </div>
            </Card>
          ))}
          <p className="text-sm text-muted sm:col-span-2 lg:col-span-3">
            <Badge tone="primary">Working</Badge> Clips appear here as soon as they are rendered.
          </p>
        </div>
      )}

      <ClipDrawer clip={openClip} onClose={() => setOpenId(null)} onChange={load} />
    </div>
  );
}
