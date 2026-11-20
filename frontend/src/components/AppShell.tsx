"use client";

import {
  CalendarDays,
  Clapperboard,
  FileText,
  FolderOpen,
  Gauge,
  HardDrive,
  LifeBuoy,
  Menu,
  Plus,
  Power,
  Settings,
  Share2,
  Sparkles,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Meta, User } from "@/lib/types";
import { LogoMark, ThemeToggle } from "./brand";
import { DueReminder } from "./DueReminder";
import { cx, Skeleton } from "./ui";

type Session = { user: User; setUser: (u: User) => void; meta: Meta | null; refreshMeta: () => void };
const SessionCtx = createContext<Session | null>(null);

export function useSession(): Session {
  const s = useContext(SessionCtx);
  if (!s) throw new Error("useSession outside AppShell");
  return s;
}

const NAV: { href: string; label: string; icon: typeof FolderOpen }[] = [
  { href: "/app/projects", label: "Projects", icon: Gauge },
  { href: "/app/new", label: "New project", icon: Plus },
  { href: "/app/library", label: "All clips", icon: Clapperboard },
  { href: "/app/calendar", label: "Calendar", icon: CalendarDays },
  { href: "/app/socials", label: "Social profiles", icon: Share2 },
  { href: "/app/storage", label: "Storage", icon: HardDrive },
  { href: "/app/transcripts", label: "Transcript generator", icon: FileText },
  { href: "/app/settings", label: "Settings & AI model", icon: Settings },
];

function RailLink({ href, label, icon: Icon, active }: { href: string; label: string; icon: typeof FolderOpen; active: boolean }) {
  return (
    <Link
      href={href}
      title={label}
      aria-label={label}
      aria-current={active ? "page" : undefined}
      className={cx(
        "group relative grid size-11 place-items-center rounded-xl transition",
        active ? "bg-primary text-on-primary shadow-[0_8px_18px_-8px_var(--primary)]" : "text-muted hover:bg-primary-soft hover:text-primary",
      )}
    >
      <Icon className="size-[19px]" strokeWidth={1.8} />
      <span className="pointer-events-none absolute left-full z-50 ml-3 whitespace-nowrap rounded-lg bg-text px-2.5 py-1 text-xs font-medium text-surface opacity-0 shadow-lg transition group-hover:opacity-100">
        {label}
      </span>
    </Link>
  );
}

function MobileLink({ href, label, icon: Icon, active }: { href: string; label: string; icon: typeof FolderOpen; active: boolean }) {
  return (
    <Link
      href={href}
      className={cx(
        "flex h-11 items-center gap-3 rounded-xl px-3 text-sm transition",
        active ? "bg-primary text-on-primary" : "text-text hover:bg-primary-soft",
      )}
    >
      <Icon className="size-[18px]" strokeWidth={1.8} />
      {label}
    </Link>
  );
}

/** The navy band at the top of every page (reference: "My Personal Wallet" header). */
export function PageHeader({
  title,
  subtitle,
  actions,
  children,
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
  children?: React.ReactNode;
}) {
  const s = useContext(SessionCtx);
  const user = s?.user;
  const ai = s?.meta;
  return (
    <div className="hero-band -mx-4 -mt-5 mb-7 rounded-b-[32px] px-5 pb-8 pt-5 sm:-mx-6 sm:px-8 lg:-mx-10 lg:px-10">
      <div className="mb-5 hidden items-center justify-end gap-3 lg:flex">
        {ai && (
          <Link
            href="/app/settings"
            className="inline-flex h-8 items-center gap-2 rounded-full bg-white/10 px-3 text-xs text-white/90 hover:bg-white/15"
            title="Which AI picks your moments"
          >
            <Sparkles className="size-3.5" />
            {ai.ai_provider === "gemini" ? "AI: Gemini (watches video)" : ai.llm.available ? `AI: local · ${ai.llm.model}` : "AI: offline"}
          </Link>
        )}
        {user && (
          <div className="flex items-center gap-2.5">
            <div className="grid size-10 place-items-center rounded-full border-2 border-white/80 bg-accent text-sm font-semibold text-white">
              {(user.name || user.email).slice(0, 1).toUpperCase()}
            </div>
            <span className="text-[15px] text-white">{user.name || "My studio"}</span>
          </div>
        )}
      </div>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-[26px] font-semibold leading-tight tracking-tight text-white sm:text-[30px]">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-white/70">{subtitle}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {children && <div className="mt-6">{children}</div>}
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const path = usePathname();
  const [user, setUser] = useState<User | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [open, setOpen] = useState(false);

  const refreshMeta = () => api.meta().then(setMeta).catch(() => {});
  useEffect(() => {
    api
      .me()
      .then(setUser)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) router.replace(`/login?next=${encodeURIComponent(path)}`);
      });
    refreshMeta();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => setOpen(false), [path]);

  if (!user) {
    return (
      <div className="flex min-h-screen">
        <div className="hidden w-[92px] bg-surface lg:block" />
        <div className="flex-1">
          <div className="hero-band h-48 rounded-b-[32px]" />
          <div className="space-y-4 p-8">
            <Skeleton className="h-40 w-full" />
          </div>
        </div>
      </div>
    );
  }

  const logout = async () => {
    await api.logout().catch(() => {});
    router.replace("/login");
  };
  const isActive = (href: string) => (href === "/app/projects" ? path.startsWith("/app/projects") : path.startsWith(href));

  return (
    <SessionCtx.Provider value={{ user, setUser, meta, refreshMeta }}>
      <div className="flex min-h-screen">
        {/* icon rail (desktop) */}
        <aside className="sticky top-0 hidden h-screen w-[92px] shrink-0 flex-col items-center bg-surface py-5 shadow-[1px_0_0_var(--border)] lg:flex">
          <Link href="/app/projects" aria-label="HypeSift AI home" className="mb-7">
            <LogoMark className="size-11" />
          </Link>
          <nav className="flex flex-1 flex-col items-center gap-2.5">
            {NAV.map((n) => (
              <RailLink key={n.href} {...n} active={isActive(n.href)} />
            ))}
          </nav>
          <div className="flex flex-col items-center gap-2">
            <a
              href="https://github.com/sidxcodes/HypeSift-AI#readme"
              target="_blank"
              rel="noopener"
              title="Help"
              aria-label="Help"
              className="grid size-11 place-items-center rounded-xl text-muted hover:bg-primary-soft hover:text-primary"
            >
              <LifeBuoy className="size-[19px]" strokeWidth={1.8} />
            </a>
            <ThemeToggle />
            <button
              onClick={logout}
              title="Sign out"
              aria-label="Sign out"
              className="grid size-11 place-items-center rounded-xl text-text hover:bg-primary-soft cursor-pointer"
            >
              <Power className="size-[19px]" strokeWidth={1.8} />
            </button>
          </div>
        </aside>

        {/* mobile drawer */}
        {open && (
          <div className="fixed inset-0 z-50 lg:hidden">
            <div className="absolute inset-0 bg-black/40" onClick={() => setOpen(false)} />
            <aside className="absolute inset-y-0 left-0 flex w-72 flex-col bg-surface p-4 shadow-xl">
              <div className="mb-4 flex items-center justify-between">
                <span className="flex items-center gap-2 font-semibold">
                  <LogoMark className="size-9" /> HypeSift <span className="text-accent">AI</span>
                </span>
                <button className="p-2 text-muted" onClick={() => setOpen(false)} aria-label="Close menu">
                  <X className="size-5" />
                </button>
              </div>
              <nav className="flex-1 space-y-1">
                {NAV.map((n) => (
                  <MobileLink key={n.href} {...n} active={isActive(n.href)} />
                ))}
              </nav>
              <div className="flex items-center justify-between border-t border-border pt-3">
                <ThemeToggle />
                <button onClick={logout} className="flex items-center gap-2 text-sm text-muted cursor-pointer">
                  <Power className="size-4" /> Sign out
                </button>
              </div>
            </aside>
          </div>
        )}

        <div className="min-w-0 flex-1">
          <div className="hero-band sticky top-0 z-30 flex h-14 items-center justify-between px-4 lg:hidden">
            <button onClick={() => setOpen(true)} className="-ml-2 p-2 text-white" aria-label="Open menu">
              <Menu className="size-5" />
            </button>
            <Link href="/app/projects" className="flex items-center gap-2 font-semibold text-white">
              <LogoMark className="size-8" /> HypeSift
            </Link>
            <Link href="/app/new" aria-label="New project" className="grid size-9 place-items-center rounded-lg bg-accent text-white">
              <Plus className="size-4" />
            </Link>
          </div>
          <main className="px-4 py-5 sm:px-6 lg:px-10">
            {children}
            <div className="fixed bottom-4 right-4 z-40 w-[min(380px,calc(100vw-2rem))] [&:empty]:hidden">
              <DueReminder />
            </div>
          </main>
        </div>
      </div>
    </SessionCtx.Provider>
  );
}
