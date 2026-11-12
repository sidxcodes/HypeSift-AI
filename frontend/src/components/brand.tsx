"use client";

import { Moon, Sun } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

export function LogoMark({ className = "size-8" }: { className?: string }) {
  // A sieve: long video in, the bright moment passes through.
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <rect width="32" height="32" rx="9" fill="var(--primary)" />
      <path d="M7 10h18M9.5 15h13M12.5 20h7" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" />
      <circle cx="16" cy="25" r="1.9" fill="#67e8f9" />
    </svg>
  );
}

export function Logo({ href = "/" }: { href?: string }) {
  return (
    <Link href={href} className="flex items-center gap-2.5 font-display font-semibold text-[17px] tracking-tight">
      <LogoMark />
      <span>
        HypeSift <span className="text-primary">AI</span>
      </span>
    </Link>
  );
}

export function ThemeToggle() {
  const [dark, setDark] = useState(false);
  useEffect(() => setDark(document.documentElement.classList.contains("dark")), []);
  const toggle = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("hs-theme", next ? "dark" : "light");
    } catch {}
  };
  return (
    <button
      onClick={toggle}
      className="grid size-9 place-items-center rounded-xl text-muted hover:text-text hover:bg-surface-2 transition cursor-pointer"
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
    >
      {dark ? <Sun className="size-[18px]" /> : <Moon className="size-[18px]" />}
    </button>
  );
}
