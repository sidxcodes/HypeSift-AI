"use client";

import { Clapperboard, FolderOpen, LayoutDashboard, LogOut, Menu, Plus, Settings, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Meta, User } from "@/lib/types";
import { Logo, ThemeToggle } from "./brand";
import { Button, cx, Skeleton } from "./ui";

type Session = { user: User; setUser: (u: User) => void; meta: Meta | null };
const SessionCtx = createContext<Session | null>(null);

export function useSession(): Session {
  const s = useContext(SessionCtx);
  if (!s) throw new Error("useSession outside AppShell");
  return s;
}

const NAV = [
  { href: "/app", label: "Overview", icon: LayoutDashboard, exact: true },
  { href: "/app/new", label: "New project", icon: Plus },
  { href: "/app/projects", label: "Projects", icon: FolderOpen },
  { href: "/app/library", label: "Clips & exports", icon: Clapperboard },
  { href: "/app/settings", label: "Settings", icon: Settings },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const path = usePathname();
  const [user, setUser] = useState<User | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    api
      .me()
      .then(setUser)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) router.replace(`/login?next=${encodeURIComponent(path)}`);
      });
    api.meta().then(setMeta).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => setOpen(false), [path]);

  if (!user) {
    return (
      <div className="flex min-h-screen">
        <div className="hidden w-64 border-r border-border p-4 lg:block">
          <Skeleton className="h-8 w-36" />
        </div>
        <div className="flex-1 p-8 space-y-4">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-40 w-full" />
        </div>
      </div>
    );
  }

  const logout = async () => {
    await api.logout().catch(() => {});
    router.replace("/login");
  };

  const sidebar = (
    <div className="flex h-full flex-col">
      <div className="flex h-16 items-center justify-between px-4">
        <Logo href="/app" />
        <button className="lg:hidden p-2 text-muted" onClick={() => setOpen(false)} aria-label="Close menu">
          <X className="size-5" />
        </button>
      </div>
      <nav className="flex-1 space-y-1 px-3 py-2">
        {NAV.map((n) => {
          const active = n.exact ? path === n.href : path.startsWith(n.href);
          return (
            <Link
              key={n.href}
              href={n.href}
              className={cx(
                "flex items-center gap-3 rounded-xl px-3 h-10 text-sm font-medium transition",
                active ? "bg-primary-soft text-primary" : "text-muted hover:text-text hover:bg-surface-2",
              )}
            >
              <n.icon className="size-[18px]" />
              {n.label}
            </Link>
          );
        })}
      </nav>
      <div className="border-t border-border p-3">
        {meta && (
          <div className="mb-3 rounded-xl bg-surface-2 px-3 py-2 text-xs text-muted">
            <div className="flex items-center gap-2">
              <span className={cx("size-2 rounded-full", meta.llm.available ? "bg-success" : "bg-warning")} />
              {meta.llm.available ? `AI editor: ${meta.llm.model}` : "AI editor offline"}
            </div>
            <div className="mt-1">Speech: whisper-{meta.whisper_model} · Encoder: {meta.encoder}</div>
          </div>
        )}
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <div className="truncate text-sm font-medium">{user.name}</div>
            <div className="truncate text-xs text-muted">{user.email}</div>
          </div>
          <div className="flex">
            <ThemeToggle />
            <button
              onClick={logout}
              className="grid size-9 place-items-center rounded-xl text-muted hover:text-text hover:bg-surface-2 cursor-pointer"
              aria-label="Sign out"
            >
              <LogOut className="size-[18px]" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );

  return (
    <SessionCtx.Provider value={{ user, setUser, meta }}>
      <div className="flex min-h-screen">
        <aside className="sticky top-0 hidden h-screen w-64 shrink-0 border-r border-border bg-surface lg:block">{sidebar}</aside>
        {open && (
          <div className="fixed inset-0 z-50 lg:hidden">
            <div className="absolute inset-0 bg-black/40" onClick={() => setOpen(false)} />
            <aside className="absolute inset-y-0 left-0 w-72 bg-surface shadow-xl">{sidebar}</aside>
          </div>
        )}
        <div className="min-w-0 flex-1">
          <div className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-border bg-bg/85 px-4 backdrop-blur lg:hidden">
            <button onClick={() => setOpen(true)} className="p-2 -ml-2 text-muted" aria-label="Open menu">
              <Menu className="size-5" />
            </button>
            <Logo href="/app" />
            <Link href="/app/new">
              <Button size="sm">
                <Plus className="size-4" />
              </Button>
            </Link>
          </div>
          <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">{children}</main>
        </div>
      </div>
    </SessionCtx.Provider>
  );
}
