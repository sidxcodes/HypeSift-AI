"use client";

import { ArrowRight, Columns2, Link2, Plus, Search, Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { PageHeader, useSession } from "@/components/AppShell";
import { ProjectList } from "@/components/ProjectList";
import { useToast } from "@/components/toast";
import { Button, Card, HeroChips, Input, Skeleton } from "@/components/ui";
import { api, ApiError, DEFAULT_SETTINGS } from "@/lib/api";
import type { Project } from "@/lib/types";

type Filter = "all" | "processing" | "ready" | "failed";

function lastDays(projects: Project[], days = 30): number[] {
  const out = new Array(days).fill(0);
  const now = new Date();
  now.setHours(23, 59, 59, 999);
  for (const p of projects) {
    const d = Math.floor((now.getTime() - new Date(p.created_at).getTime()) / 86400000);
    if (d >= 0 && d < days) out[days - 1 - d] += p.clip_count;
  }
  return out;
}

function Bars({ values }: { values: number[] }) {
  const max = Math.max(1, ...values);
  return (
    <div className="flex h-14 items-end gap-[5px]" aria-label="Clips made per day, last 30 days">
      {values.map((v, i) => (
        <div key={i} className="relative w-[3px] rounded-full bg-white/90" style={{ height: `${10 + (v / max) * 90}%`, opacity: v ? 1 : 0.35 }}>
          {i === values.length - 1 && <span className="absolute -left-[4px] -top-1 size-[11px] rounded-full border-2 border-white bg-hero" />}
        </div>
      ))}
    </div>
  );
}

function QuickGenerate() {
  const router = useRouter();
  const toast = useToast();
  const [url, setUrl] = useState("");
  const [count, setCount] = useState(6);
  const [busy, setBusy] = useState(false);
  const go = async () => {
    if (!url.trim()) return;
    setBusy(true);
    try {
      const p = await api.createProject({ url: url.trim(), settings: { ...DEFAULT_SETTINGS, count } });
      router.push(`/app/projects/${p.id}`);
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Couldn't start that link.");
      setBusy(false);
    }
  };
  return (
    <Card className="p-6 lg:-mt-[120px] lg:rounded-tl-[32px] lg:rounded-tr-none lg:rounded-b-none lg:min-h-[calc(100%+120px)]">
      <h2 className="text-xl font-semibold">Quick generate</h2>
      <p className="mt-1 text-sm text-muted">Paste a YouTube (or any video) link and get clips with your default settings.</p>
      <div className="mt-5 grid grid-cols-[1fr_92px] gap-3">
        <label className="rounded-xl bg-surface p-3 shadow-card">
          <span className="sr-only">Video link</span>
          <div className="flex items-center gap-2">
            <Link2 className="size-4 text-muted" />
            <input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && go()}
              placeholder="https://youtu.be/…"
              className="w-full bg-transparent text-[15px] font-medium outline-none placeholder:font-normal placeholder:text-muted"
            />
          </div>
        </label>
        <label className="rounded-xl bg-surface p-3 shadow-card">
          <span className="block text-[11px] text-muted">Clips</span>
          <select value={count} onChange={(e) => setCount(Number(e.target.value))} className="w-full bg-transparent text-[15px] font-medium outline-none cursor-pointer">
            {[3, 4, 5, 6, 8, 10, 12].map((n) => (
              <option key={n}>{n}</option>
            ))}
          </select>
        </label>
      </div>
      <div className="mt-5 flex items-center gap-5">
        <Button size="lg" className="px-8" onClick={go} loading={busy} disabled={!url.trim()}>
          Generate
        </Button>
        <Link href="/app/new" className="text-sm font-medium text-primary hover:underline">
          More options
        </Link>
      </div>
      <div className="mt-9 flex items-center justify-between">
        <h3 className="text-lg font-semibold">Tips for viral clips</h3>
      </div>
      <ul className="mt-3 space-y-3 text-sm">
        {[
          ["Pick a clip length", "Choose ~30, 45 or 60 s in More options: clips land right on it."],
          ["Tell the AI what you want", "“the funniest reactions”, “her best advice”…"],
          ["Comparisons", "“X vs Y” videos become stacked clips that take turns."],
        ].map(([t, b]) => (
          <li key={t} className="rounded-xl bg-surface-2 p-3">
            <div className="font-medium">{t}</div>
            <div className="text-xs text-muted">{b}</div>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export default function ProjectsPage() {
  const { meta } = useSession();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [q, setQ] = useState("");
  useEffect(() => {
    const load = () => api.projects().then(setProjects).catch(() => setProjects([]));
    load();
    const i = setInterval(load, 4000);
    return () => clearInterval(i);
  }, []);

  const all = projects ?? [];
  const shown = useMemo(
    () =>
      all.filter(
        (p) =>
          (filter === "all" ||
            (filter === "processing" ? p.status === "processing" || p.status === "queued" : p.status === filter)) &&
          (!q || p.name.toLowerCase().includes(q.toLowerCase())),
      ),
    [all, filter, q],
  );
  const month = all.filter((p) => Date.now() - new Date(p.created_at).getTime() < 30 * 86400000);
  const clipsMonth = month.reduce((n, p) => n + p.clip_count, 0);
  const minutes = all.reduce((n, p) => n + (p.duration ?? 0), 0) / 60;
  const gemini = meta?.ai_provider === "gemini";

  return (
    <div>
      <PageHeader
        title="My Projects"
        actions={
          <Link href="/app/new">
            <Button variant="accent" size="lg" className="px-6">
              <Plus className="size-4" /> New project
            </Button>
          </Link>
        }
      >
        <div className="flex flex-wrap items-center gap-3">
          <HeroChips
            value={filter}
            onChange={setFilter}
            options={[
              { value: "all", label: "All" },
              { value: "processing", label: "Processing" },
              { value: "ready", label: "Ready" },
              { value: "failed", label: "Failed" },
            ]}
          />
          <label className="flex h-12 items-center gap-2 rounded-xl bg-white/8 px-3 text-white">
            <Search className="size-4 text-white/70" />
            <span className="sr-only">Search projects</span>
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search projects"
              className="w-40 bg-transparent text-sm text-white outline-none placeholder:text-white/60"
            />
          </label>
        </div>
        <div className="mt-6 flex flex-wrap items-end justify-between gap-6 lg:max-w-[calc(100%-380px)]">
          <div>
            <div className="mb-3 text-lg font-semibold text-white">Last 30 days</div>
            <Bars values={lastDays(all)} />
          </div>
          <div className="text-right">
            <div className="text-sm text-white/85">This month’s clips and footage</div>
            <div className="mt-1 text-[32px] font-semibold leading-none text-white">
              {clipsMonth} <span className="text-white/45">/ {Math.round(minutes)} min</span>
            </div>
            <div className="mt-1 flex justify-end gap-10 pr-1 text-[11px] text-white/80">
              <span>Clips</span>
              <span className="text-white/50">Footage</span>
            </div>
          </div>
        </div>
      </PageHeader>

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_350px]">
        <div className="min-w-0 space-y-8">
          <div className="grid gap-5 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)]">
            <div>
              <div className="text-[15px] text-muted">Clips made</div>
              <div className="text-[26px] font-semibold">{all.reduce((n, p) => n + p.clip_count, 0)}</div>
              <div className="mt-3 text-[15px] text-muted">Projects</div>
              <div className="text-[26px] font-semibold text-muted">{all.length}</div>
            </div>
            <Link
              href="/app/settings"
              className="group relative flex min-h-[190px] flex-col justify-between overflow-hidden rounded-2xl bg-primary-soft p-5 transition hover:-translate-y-0.5"
            >
              <span className="absolute -right-6 top-14 size-20 rounded-full border-[14px] border-primary/10" />
              <span className="absolute right-12 top-10 size-4 rounded-full border-4 border-primary/15" />
              <div className="text-sm font-semibold text-primary">AI model</div>
              <div>
                <div className="text-xl font-semibold leading-snug">
                  {gemini ? "Gemini is watching your videos" : "Smarter picks with Gemini"}
                </div>
                <div className="mt-1 inline-flex items-center gap-1 text-xs text-primary">
                  {gemini ? "Change model" : "Free setup, 2 min"} <ArrowRight className="size-3 transition group-hover:translate-x-0.5" />
                </div>
              </div>
            </Link>
            <Link
              href="/app/new"
              className="group relative flex min-h-[190px] flex-col justify-between overflow-hidden rounded-2xl bg-accent-soft p-5 transition hover:-translate-y-0.5"
            >
              <span className="absolute right-4 top-3 size-7 rotate-45 rounded-md border-2 border-accent/30" />
              <span className="absolute bottom-3 right-6 size-7 rotate-45 rounded-md border-2 border-accent/30" />
              <div className="text-sm font-semibold text-text">Comparisons</div>
              <div>
                <div className="flex items-center gap-2 text-xl font-semibold leading-snug">
                  <Columns2 className="size-5 text-accent" /> A vs B, 3 ways
                </div>
                <div className="mt-1 text-xs text-muted">Take turns · together · all, then one by one</div>
              </div>
            </Link>
          </div>

          <section>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-xl font-semibold">Latest projects</h2>
              {!gemini && (
                <Link href="/app/settings" className="hidden items-center gap-1.5 text-sm text-primary hover:underline sm:inline-flex">
                  <Sparkles className="size-4" /> Turn on Gemini
                </Link>
              )}
            </div>
            {projects ? (
              <ProjectList projects={shown} />
            ) : (
              <div className="grid gap-4 sm:grid-cols-2">{[0, 1].map((i) => <Skeleton key={i} className="h-56" />)}</div>
            )}
          </section>
        </div>
        <QuickGenerate />
      </div>
    </div>
  );
}
