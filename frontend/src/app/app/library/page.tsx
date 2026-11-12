"use client";

import { Clapperboard } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ClipCard } from "@/components/ClipCard";
import { ClipDrawer } from "@/components/ClipDrawer";
import { Button, Card, EmptyState, Segmented, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import type { Clip } from "@/lib/types";

export default function LibraryPage() {
  const [tab, setTab] = useState<"exports" | "favorites" | "all">("exports");
  const [clips, setClips] = useState<Clip[] | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .clips({ favorite: tab === "favorites", rendered: tab === "exports" })
      .then(setClips)
      .catch(() => setClips([]));
  }, [tab]);
  useEffect(() => {
    setClips(null);
    load();
  }, [load]);

  return (
    <div>
      <h1 className="font-display text-2xl font-bold tracking-tight">Clips & exports</h1>
      <p className="mt-1 text-sm text-muted">Every clip across your projects — download, edit or grab its publishing copy.</p>
      <Segmented
        className="mt-5"
        value={tab}
        onChange={setTab}
        options={[
          { value: "exports", label: "Rendered" },
          { value: "favorites", label: "Favorites" },
          { value: "all", label: "All clips" },
        ]}
      />
      <div className="mt-6">
        {!clips ? (
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-96" />)}</div>
        ) : clips.length === 0 ? (
          <Card>
            <EmptyState
              icon={<Clapperboard className="size-6" />}
              title={tab === "favorites" ? "No favorites yet" : "No clips yet"}
              body={tab === "favorites" ? "Star clips in a project to collect them here." : "Run AI Generate on a video and your clips will show up here."}
              action={<Link href="/app/new"><Button>New project</Button></Link>}
            />
          </Card>
        ) : (
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
            {clips.map((c, i) => (
              <div key={c.id}>
                <div className="mb-1.5 truncate text-xs text-muted">{c.project_name}</div>
                <ClipCard clip={c} index={i} onOpen={() => setOpenId(c.id)} onFavorite={() => api.favorite(c.id, !c.favorite).then(load)} />
              </div>
            ))}
          </div>
        )}
      </div>
      <ClipDrawer clip={clips?.find((c) => c.id === openId) ?? null} onClose={() => setOpenId(null)} onChange={load} />
    </div>
  );
}
