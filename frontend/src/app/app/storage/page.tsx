"use client";

import { HardDrive, Trash2, Video } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useToast } from "@/components/toast";
import { Button, EmptyState, Progress, Skeleton } from "@/components/ui";
import { api, fmtBytes } from "@/lib/api";
import type { StorageUsage } from "@/lib/types";

export default function StoragePage() {
  const toast = useToast();
  const [u, setU] = useState<StorageUsage | null>(null);
  const load = useCallback(() => api.storage().then(setU).catch((e) => toast("error", e.message)), [toast]);
  useEffect(() => {
    load();
  }, [load]);

  const remove = async (id: string, name: string) => {
    if (!confirm(`Delete “${name}”, its source video and all its clips? This can't be undone.`)) return;
    await api.deleteProject(id);
    toast("success", "Project deleted.");
    load();
  };

  return (
    <div className="max-w-3xl space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Storage</h1>
        <p className="mt-1 text-sm text-muted">Everything is stored on this computer. Delete old projects to free space.</p>
      </div>
      {!u ? (
        <Skeleton className="h-64" />
      ) : (
        <>
          <div className="rounded-2xl border border-border p-5">
            <div className="flex items-baseline justify-between">
              <div className="text-sm text-muted">Used by HypeSift</div>
              <div className="text-2xl font-semibold">{fmtBytes(u.total)}</div>
            </div>
            <Progress value={u.total / Math.max(1, u.total + u.disk_free)} className="mt-3" />
            <div className="mt-2 text-xs text-muted">
              {fmtBytes(u.disk_free)} free on this drive · {fmtBytes(u.assets_bytes)} in logos and music
            </div>
          </div>
          {u.projects.length === 0 ? (
            <EmptyState icon={<HardDrive className="size-6" />} title="Nothing stored yet" body="Projects you create appear here with their size." />
          ) : (
            <div className="divide-y divide-border rounded-2xl border border-border">
              {u.projects
                .slice()
                .sort((a, b) => b.total - a.total)
                .map((p) => (
                  <div key={p.id} className="flex items-center gap-3 px-4 py-3">
                    {p.thumb_url ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={p.thumb_url} alt="" className="aspect-video w-20 shrink-0 rounded-lg object-cover" />
                    ) : (
                      <div className="grid aspect-video w-20 shrink-0 place-items-center rounded-lg bg-surface-2">
                        <Video className="size-4 text-muted" />
                      </div>
                    )}
                    <div className="min-w-0 flex-1">
                      <Link href={`/app/projects/${p.id}`} className="block truncate text-sm font-medium hover:text-primary">
                        {p.name}
                      </Link>
                      <div className="text-xs text-muted">
                        Source {fmtBytes(p.source_bytes)} · {p.clips} clip{p.clips === 1 ? "" : "s"} {fmtBytes(p.clip_bytes)}
                      </div>
                    </div>
                    <div className="w-20 text-right text-sm font-medium tabular-nums">{fmtBytes(p.total)}</div>
                    <Button variant="ghost" size="sm" onClick={() => remove(p.id, p.name)} aria-label={`Delete ${p.name}`}>
                      <Trash2 className="size-4" />
                    </Button>
                  </div>
                ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
