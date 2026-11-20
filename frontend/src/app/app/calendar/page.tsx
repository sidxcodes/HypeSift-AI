"use client";

import { PageHeader } from "@/components/AppShell";
import { CalendarDays, CheckCircle2, ChevronLeft, ChevronRight, Clock } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { PlatformIcon } from "@/components/PostDrawer";
import { Button, cx, EmptyState, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import type { Clip } from "@/lib/types";

function when(c: Clip): Date | null {
  const t = c.post?.status === "posted" ? c.post.posted_at : c.post?.scheduled_at;
  return t ? new Date(t) : null;
}

export default function CalendarPage() {
  const [posts, setPosts] = useState<Clip[] | null>(null);
  const [month, setMonth] = useState(() => {
    const d = new Date();
    return new Date(d.getFullYear(), d.getMonth(), 1);
  });

  useEffect(() => {
    api.posts().then(setPosts).catch(() => setPosts([]));
  }, []);

  const byDay = useMemo(() => {
    const m = new Map<string, Clip[]>();
    for (const c of posts ?? []) {
      const d = when(c);
      if (!d) continue;
      const k = d.toDateString();
      m.set(k, [...(m.get(k) ?? []), c].sort((a, b) => when(a)!.getTime() - when(b)!.getTime()));
    }
    return m;
  }, [posts]);

  const upcoming = (posts ?? [])
    .filter((c) => c.post?.status === "scheduled" && when(c)!.getTime() > Date.now() - 3600_000)
    .sort((a, b) => when(a)!.getTime() - when(b)!.getTime());

  const first = (month.getDay() + 6) % 7;
  const days = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
  const cells = [...Array(first).fill(null), ...Array.from({ length: days }, (_, i) => i + 1)];
  while (cells.length % 7) cells.push(null);
  const today = new Date().toDateString();

  return (
    <div className="space-y-5">
      <PageHeader
        title="Calendar"
        subtitle="Scheduled and posted clips. HypeSift reminds you when a post is due."
        actions={
        <div className="flex items-center gap-1 text-white">
          <Button variant="onHero" size="sm" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))} aria-label="Previous month">
            <ChevronLeft className="size-4" />
          </Button>
          <div className="w-40 text-center font-medium">{month.toLocaleDateString(undefined, { month: "long", year: "numeric" })}</div>
          <Button variant="onHero" size="sm" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))} aria-label="Next month">
            <ChevronRight className="size-4" />
          </Button>
          <Button
            variant="accent"
            size="sm"
            onClick={() => {
              const d = new Date();
              setMonth(new Date(d.getFullYear(), d.getMonth(), 1));
            }}
          >
            Today
          </Button>
        </div>
        }
      />

      {!posts ? (
        <Skeleton className="h-[520px]" />
      ) : (
        <div className="grid gap-5 xl:grid-cols-[1fr_280px]">
          <div className="overflow-hidden rounded-2xl border border-border">
            <div className="grid grid-cols-7 border-b border-border bg-surface-2 text-center text-xs text-muted">
              {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => (
                <div key={d} className="py-2">
                  {d}
                </div>
              ))}
            </div>
            <div className="grid grid-cols-7">
              {cells.map((d, i) => {
                const date = d ? new Date(month.getFullYear(), month.getMonth(), d) : null;
                const items = date ? byDay.get(date.toDateString()) ?? [] : [];
                return (
                  <div key={i} className={cx("min-h-28 border-b border-r border-border p-1.5", !d && "bg-surface-2/50", (i + 1) % 7 === 0 && "border-r-0")}>
                    {d && (
                      <div className={cx("mb-1 grid size-6 place-items-center rounded-full text-xs", date!.toDateString() === today ? "bg-primary font-semibold text-on-primary" : "text-muted")}>
                        {d}
                      </div>
                    )}
                    <div className="space-y-1">
                      {items.slice(0, 3).map((c) => (
                        <Link
                          key={c.id}
                          href={`/app/projects/${c.project_id}`}
                          title={c.title}
                          className={cx(
                            "flex items-center gap-1 truncate rounded-md px-1.5 py-1 text-[11px]",
                            c.post?.status === "posted" ? "bg-success/10 text-success" : "bg-primary-soft text-primary",
                          )}
                        >
                          {c.post?.status === "posted" ? <CheckCircle2 className="size-3 shrink-0" /> : <Clock className="size-3 shrink-0" />}
                          <span className="shrink-0 tabular-nums">{when(c)!.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}</span>
                          <span className="truncate">{c.title}</span>
                        </Link>
                      ))}
                      {items.length > 3 && <div className="px-1.5 text-[11px] text-muted">+{items.length - 3} more</div>}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div>
            <h2 className="mb-2 text-sm font-medium">Up next</h2>
            {upcoming.length === 0 ? (
              <div className="rounded-2xl border border-border">
                <EmptyState icon={<CalendarDays className="size-6" />} title="Nothing scheduled" body="Open a project and use “Post or schedule” on a clip." />
              </div>
            ) : (
              <div className="space-y-2">
                {upcoming.map((c) => (
                  <Link key={c.id} href={`/app/projects/${c.project_id}`} className="flex gap-3 rounded-xl border border-border p-2 hover:bg-surface-2">
                    {c.thumb_url ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={c.thumb_url} alt="" className="aspect-[9/16] w-12 shrink-0 rounded-lg object-cover" />
                    ) : (
                      <div className="aspect-[9/16] w-12 shrink-0 rounded-lg bg-surface-2" />
                    )}
                    <div className="min-w-0">
                      <div className="line-clamp-2 text-sm font-medium">{c.title}</div>
                      <div className="mt-0.5 text-xs text-muted">
                        {when(c)!.toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}
                      </div>
                      <div className="mt-1 flex gap-1">
                        {Object.entries(c.post?.platforms ?? {})
                          .filter(([, f]) => (f as { include?: boolean }).include)
                          .map(([pl]) => (
                            <PlatformIcon key={pl} p={pl} className="size-5 text-[9px]" />
                          ))}
                      </div>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
