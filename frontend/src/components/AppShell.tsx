"use client";

import {
  CalendarDays,
  Clapperboard,
  ExternalLink,
  FileText,
  FolderOpen,
  HardDrive,
  LifeBuoy,
  LogOut,
  Menu,
  Settings,
  Share2,
  Upload,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Meta, User } from "@/lib/types";
import { Logo, ThemeToggle } from "./brand";
import { DueReminder } from "./DueReminder";
import { Button, cx, Skeleton } from "./ui";

type Session = { user: User; setUser: (u: User) => void; meta: Meta | null };
const SessionCtx = createContext<Session | null>(null);

export function useSession(): Session {
  const s = useContext(SessionCtx);
  if (!s) throw new Error("useSession outside AppShell");
  return s;
}

const NAV: { section: string; items: { href: string; label: string; icon: typeof FolderOpen; exact?: boolean }[] }[] = [
  {
    section: "Content",
    items: [
      { href: "/app/projects", label: "Projects", icon: FolderOpen },
      { href: "/app/library", label: "All clips", icon: Clapperboard },
      { href: "/app/calendar", label: "Calendar", icon: CalendarDays },
    ],
  },
  {
    section: "Manage",
    items: [
      { href: "/app/socials", label: "Social profiles", icon: Share2 },
      { href: "/app/storage", label: "Storage", icon: HardDrive },
    ],
  },
  { section: "Tools", items: [{ href: "/app/transcripts", label: "Transcript generator", icon: FileText }] },
];

function NavLink({ href, label, icon: Icon, active }: { href: string; label: string; icon: typeof FolderOpen; active: boolean }) {
  return (
    <Link
      href={href}
      className={cx(
        "flex items-center gap-2.5 rounded-lg px-2.5 h-8 text-[13.5px] transition",
        active ? "bg-surface-2 font-medium text-text" : "text-text/80 hover:bg-surface-2 hover:text-text",
      )}
    >
      <Icon className="size-4 text-muted" />
      {label}
    </Link>
  );
}

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
      <div className="flex h-14 items-center justify-between px-4">
        <Logo href="/app/projects" />
        <div className="flex items-center">
          <ThemeToggle />
          <button className="lg:hidden p-2 text-muted" onClick={() => setOpen(false)} aria-label="Close menu">
            <X className="size-5" />
          </button>
        </div>
      </div>
      <div className="px-3 pb-2">
        <Link href="/app/new">
          <Button className="w-full">
            <Upload className="size-4" /> Upload a video
          </Button>
        </Link>
      </div>
      <nav className="flex-1 overflow-y-auto px-3 py-2">
        {NAV.map((g) => (
          <div key={g.section} className="mb-4">
            <div className="px-2.5 pb-1 text-xs text-muted">{g.section}</div>
            <div className="space-y-0.5">
              {g.items.map((n) => (
                <NavLink key={n.href} {...n} active={n.exact ? path === n.href : path.startsWith(n.href)} />
              ))}
            </div>
          </div>
        ))}
      </nav>
      <div className="px-3 pb-2 space-y-0.5">
        <NavLink href="/app/settings" label="Settings" icon={Settings} active={path.startsWith("/app/settings")} />
        <a
          href="https://github.com/sidxcodes/HypeSift-AI#readme"
          target="_blank"
          rel="noopener"
          className="flex items-center gap-2.5 rounded-lg px-2.5 h-8 text-[13.5px] text-text/80 hover:bg-surface-2"
        >
          <LifeBuoy className="size-4 text-muted" /> Help <ExternalLink className="ml-auto size-3.5 text-muted" />
        </a>
        {meta && (
          <div className="flex items-center gap-2 px-2.5 py-1.5 text-xs text-muted" title={meta.llm.reason || undefined}>
            <span className={cx("size-2 rounded-full", meta.llm.available ? "bg-success" : "bg-warning")} />
            {meta.llm.available ? `AI editor on · ${meta.llm.model}` : "AI editor offline"}
          </div>
        )}
      </div>
      <div className="border-t border-border p-3">
        <div className="flex items-center gap-2.5">
          <div className="grid size-8 shrink-0 place-items-center rounded-full bg-primary text-sm font-semibold text-on-primary">
            {(user.name || user.email).slice(0, 1).toUpperCase()}
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium">{user.name || "My studio"}</div>
            <div className="truncate text-xs text-muted">{user.email}</div>
          </div>
          <button
            onClick={logout}
            className="grid size-8 place-items-center rounded-lg text-muted hover:text-text hover:bg-surface-2 cursor-pointer"
            aria-label="Sign out"
          >
            <LogOut className="size-4" />
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <SessionCtx.Provider value={{ user, setUser, meta }}>
      <div className="flex min-h-screen">
        <aside className="sticky top-0 hidden h-screen w-60 shrink-0 border-r border-border bg-surface lg:block">{sidebar}</aside>
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
            <Logo href="/app/projects" />
            <Link href="/app/new">
              <Button size="sm" aria-label="Upload a video">
                <Upload className="size-4" />
              </Button>
            </Link>
          </div>
          <main className="mx-auto max-w-6xl px-4 py-5 sm:px-6 lg:px-8">
            <DueReminder />
            {children}
          </main>
        </div>
      </div>
    </SessionCtx.Provider>
  );
}
