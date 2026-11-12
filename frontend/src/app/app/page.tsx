"use client";

import { Clapperboard, Download, FolderOpen, Link2, Plus, Upload, Wand2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useSession } from "@/components/AppShell";
import { ProjectList } from "@/components/ProjectList";
import { Button, Card, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import type { Clip, Project } from "@/lib/types";

export default function Overview() {
  const { user } = useSession();
  const router = useRouter();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [clips, setClips] = useState<Clip[]>([]);
  const [url, setUrl] = useState("");

  useEffect(() => {
    const load = () => {
      api.projects().then(setProjects).catch(() => setProjects([]));
      api.clips({ rendered: true }).then(setClips).catch(() => {});
    };
    load();
    const i = setInterval(load, 5000);
    return () => clearInterval(i);
  }, []);

  const active = projects?.filter((p) => p.status === "processing" || p.status === "queued").length ?? 0;
  const stats = [
    { label: "Projects", value: projects?.length ?? "–", icon: FolderOpen },
    { label: "Clips ready", value: clips.length, icon: Clapperboard },
    { label: "Processing now", value: active, icon: Wand2 },
    { label: "Favorites", value: clips.filter((c) => c.favorite).length, icon: Download },
  ];

  return (
    <div className="space-y-8">
      <div>
        <h1 className="font-display text-2xl font-bold tracking-tight">Hi {user.name.split(" ")[0]} 👋</h1>
        <p className="mt-1 text-sm text-muted">Turn your next long video into a week of shorts.</p>
      </div>

      <Card className="p-5 sm:p-6">
        <div className="grid gap-5 lg:grid-cols-[1fr_auto] lg:items-end">
          <div>
            <h2 className="font-display text-lg font-semibold">Start a new project</h2>
            <form
              className="mt-4 flex flex-col gap-2 sm:flex-row"
              onSubmit={(e) => {
                e.preventDefault();
                router.push(url.trim() ? `/app/new?url=${encodeURIComponent(url.trim())}` : "/app/new");
              }}
            >
              <div className="relative flex-1">
                <Link2 className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted" />
                <input
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="Paste a direct video link"
                  aria-label="Video link"
                  className="h-11 w-full rounded-xl border border-border bg-surface pl-10 pr-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring/40"
                />
              </div>
              <Button size="lg" type="submit" className="h-11">
                <Wand2 className="size-4" /> Continue
              </Button>
            </form>
          </div>
          <Link href="/app/new">
            <Button variant="secondary" size="lg" className="h-11 w-full">
              <Upload className="size-4" /> Upload a file
            </Button>
          </Link>
        </div>
      </Card>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {stats.map((s) => (
          <Card key={s.label} className="p-4">
            <s.icon className="size-4 text-primary" />
            <div className="mt-3 font-display text-2xl font-bold tabular-nums">{s.value}</div>
            <div className="text-sm text-muted">{s.label}</div>
          </Card>
        ))}
      </div>

      <div>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-display text-lg font-semibold">Recent projects</h2>
          <Link href="/app/projects" className="text-sm font-medium text-primary hover:underline">View all</Link>
        </div>
        {projects ? (
          <ProjectList projects={projects.slice(0, 6)} />
        ) : (
          <div className="grid gap-4 sm:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-56" />)}</div>
        )}
      </div>

      {projects && projects.length === 0 && (
        <div className="flex justify-center">
          <Link href="/app/new">
            <Button size="lg">
              <Plus className="size-4" /> Create your first project
            </Button>
          </Link>
        </div>
      )}
    </div>
  );
}
