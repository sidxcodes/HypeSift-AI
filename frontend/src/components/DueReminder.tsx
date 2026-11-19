"use client";

import { BellRing, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { Clip } from "@/lib/types";

/** Scheduled posts whose time has come: an in-app banner plus a desktop notification. */
export function DueReminder() {
  const [due, setDue] = useState<Clip[]>([]);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const notified = useRef<Set<string>>(new Set());

  useEffect(() => {
    let stop = false;
    const check = async () => {
      try {
        const posts = await api.posts();
        if (stop) return;
        const now = Date.now();
        const d = posts.filter((c) => c.post?.status === "scheduled" && c.post.scheduled_at && new Date(c.post.scheduled_at).getTime() <= now);
        setDue(d);
        for (const c of d) {
          if (notified.current.has(c.id)) continue;
          notified.current.add(c.id);
          if (typeof Notification !== "undefined" && Notification.permission === "granted") {
            new Notification("Time to post on HypeSift", { body: c.title, icon: "/icon-192.png" });
          }
        }
      } catch {}
    };
    check();
    const i = setInterval(check, 60_000);
    return () => {
      stop = true;
      clearInterval(i);
    };
  }, []);

  const show = due.filter((c) => !hidden.has(c.id));
  if (!show.length) return null;
  const c = show[0];
  return (
    <div className="mb-4 flex items-center gap-3 rounded-2xl border border-primary/30 bg-primary-soft px-4 py-3 text-sm">
      <BellRing className="size-5 shrink-0 text-primary" />
      <div className="min-w-0 flex-1">
        <span className="font-medium">Time to post:</span> <span className="truncate">{c.title}</span>
        {show.length > 1 && <span className="text-muted"> and {show.length - 1} more</span>}
      </div>
      <Link href={`/app/projects/${c.project_id}`} className="font-medium text-primary hover:underline">
        Open
      </Link>
      <button onClick={() => setHidden((h) => new Set(h).add(c.id))} className="p-1 text-muted hover:text-text cursor-pointer" aria-label="Dismiss">
        <X className="size-4" />
      </button>
    </div>
  );
}
