"use client";

import { Moon, Sun } from "lucide-react";
import Link from "next/link";
import { useEffect, useId, useState } from "react";

export function LogoMark({ className = "size-8" }: { className?: string }) {
  // "Play-face bot": the HypeSift robot whose face is a play button (same art as desktop/hypesift-icon.svg).
  const id = useId().replace(/:/g, "");
  return (
    <svg viewBox="0 0 64 64" className={className} aria-hidden>
      <defs>
        <linearGradient id={`${id}bg`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#6470a6" />
          <stop offset="1" stopColor="#3f4877" />
        </linearGradient>
        <linearGradient id={`${id}gl`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#fff" stopOpacity=".10" />
          <stop offset=".5" stopColor="#fff" stopOpacity="0" />
        </linearGradient>
        <linearGradient id={`${id}hd`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#fff" />
          <stop offset="1" stopColor="#e3e6f6" />
        </linearGradient>
        <linearGradient id={`${id}pl`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#ffb199" />
          <stop offset="1" stopColor="#ff6a45" />
        </linearGradient>
      </defs>
      <rect width="64" height="64" rx="15" fill={`url(#${id}bg)`} />
      <rect width="64" height="64" rx="15" fill={`url(#${id}gl)`} />
      <path d="M32 14V9" stroke="#d9e2ea" strokeWidth="2" />
      <circle cx="32" cy="7" r="2.4" fill="#ff7a59" />
      <rect x="6.5" y="25" width="5" height="13" rx="2.5" fill="#ff7a59" />
      <rect x="52.5" y="25" width="5" height="13" rx="2.5" fill="#ff7a59" />
      <rect x="10" y="14" width="44" height="36" rx="14" fill={`url(#${id}hd)`} />
      <rect x="16" y="20" width="32" height="24" rx="9" fill="#2b3160" />
      <path d="M28 25v14l12-7z" fill={`url(#${id}pl)`} stroke={`url(#${id}pl)`} strokeWidth="2.2" strokeLinejoin="round" />
      <path d="M26 54h12" stroke="#ff7a59" strokeWidth="3" strokeLinecap="round" />
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
      localStorage.setItem("hs-theme2", next ? "dark" : "light");
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
