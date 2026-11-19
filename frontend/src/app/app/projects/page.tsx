"use client";

import { Upload } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ProjectList } from "@/components/ProjectList";
import { Button, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import type { Project } from "@/lib/types";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  useEffect(() => {
    const load = () => api.projects().then(setProjects).catch(() => setProjects([]));
    load();
    const i = setInterval(load, 4000);
    return () => clearInterval(i);
  }, []);
  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Projects</h1>
          <p className="text-sm text-muted">Every video you&apos;ve turned into clips.</p>
        </div>
        <Link href="/app/new">
          <Button>
            <Upload className="size-4" /> Upload a video
          </Button>
        </Link>
      </div>
      <div className="mt-6">
        {projects ? <ProjectList projects={projects} /> : <div className="grid gap-4 sm:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-56" />)}</div>}
      </div>
    </div>
  );
}
