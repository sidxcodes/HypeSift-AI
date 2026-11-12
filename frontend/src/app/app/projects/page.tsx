"use client";

import { Plus } from "lucide-react";
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
        <h1 className="font-display text-2xl font-bold tracking-tight">Projects</h1>
        <Link href="/app/new">
          <Button>
            <Plus className="size-4" /> New project
          </Button>
        </Link>
      </div>
      <div className="mt-6">
        {projects ? <ProjectList projects={projects} /> : <div className="grid gap-4 sm:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-56" />)}</div>}
      </div>
    </div>
  );
}
