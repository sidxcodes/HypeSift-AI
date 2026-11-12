"use client";

import { FolderOpen, Plus, Video } from "lucide-react";
import Link from "next/link";
import { fmtTime } from "@/lib/api";
import type { Project } from "@/lib/types";
import { STAGE_LABELS } from "./JobProgress";
import { Badge, Button, Card, EmptyState, Progress } from "./ui";

const STATUS: Record<Project["status"], { label: string; tone: "neutral" | "primary" | "success" | "danger" | "warning" }> = {
  draft: { label: "Draft", tone: "neutral" },
  queued: { label: "Queued", tone: "warning" },
  processing: { label: "Processing", tone: "primary" },
  ready: { label: "Ready", tone: "success" },
  failed: { label: "Failed", tone: "danger" },
};

export function ProjectList({ projects }: { projects: Project[] }) {
  if (!projects.length) {
    return (
      <Card>
        <EmptyState
          icon={<FolderOpen className="size-6" />}
          title="No projects yet"
          body="Upload a long video or paste a direct link, then hit AI Generate to get ready-to-post shorts."
          action={
            <Link href="/app/new">
              <Button>
                <Plus className="size-4" /> New project
              </Button>
            </Link>
          }
        />
      </Card>
    );
  }
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {projects.map((p) => {
        const st = STATUS[p.status];
        const running = p.job && (p.job.status === "running" || p.job.status === "queued");
        return (
          <Link key={p.id} href={`/app/projects/${p.id}`} className="group">
            <Card className="overflow-hidden transition group-hover:border-primary/50">
              <div className="relative aspect-video bg-surface-2">
                {p.thumb_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={p.thumb_url} alt="" className="h-full w-full object-cover" />
                ) : (
                  <Video className="absolute inset-0 m-auto size-8 text-muted" />
                )}
                {p.duration != null && (
                  <span className="absolute bottom-2 right-2 rounded-md bg-black/70 px-1.5 py-0.5 text-xs text-white">{fmtTime(p.duration)}</span>
                )}
              </div>
              <div className="p-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 truncate font-medium">{p.name}</div>
                  <Badge tone={st.tone}>{st.label}</Badge>
                </div>
                <div className="mt-1 text-sm text-muted">
                  {p.clip_count} clip{p.clip_count === 1 ? "" : "s"} · {new Date(p.created_at).toLocaleDateString()}
                </div>
                {running && p.job && (
                  <div className="mt-3">
                    <Progress value={p.job.progress} />
                    <div className="mt-1 text-xs text-muted">{STAGE_LABELS[p.job.stage] ?? p.job.message}</div>
                  </div>
                )}
                {p.status === "failed" && p.error && <div className="mt-2 line-clamp-2 text-xs text-danger">{p.error}</div>}
              </div>
            </Card>
          </Link>
        );
      })}
    </div>
  );
}
