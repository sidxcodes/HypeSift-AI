"use client";

import {
  BarChart3,
  CalendarClock,
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  CircleDot,
  Download,
  Flame,
  Gauge,
  Heart,
  Loader2,
  MessageCircle,
  Pencil,
  Rows3,
  Send,
  Star,
  Trash2,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import type { Clip, Goal } from "@/lib/types";
import { cx } from "./ui";

const GOAL_DIM: Partial<Record<Goal, string>> = { views: "viral", trust: "context", educate: "context", entertain: "emotion" };

function Chip({ icon: Icon, value, label, active, tone }: { icon: typeof Flame; value: number; label: string; active?: boolean; tone: string }) {
  return (
    <span
      title={`${label}: ${value}/100`}
      className={cx(
        "inline-flex h-6 items-center gap-1 rounded-full border px-2 text-xs tabular-nums",
        active ? "border-orange-400 bg-orange-50 text-orange-700 dark:bg-orange-500/10 dark:text-orange-300" : "border-transparent text-muted",
      )}
    >
      <Icon className={cx("size-3.5", tone)} /> {value}
    </span>
  );
}

function sentences(text: string): string[] {
  return (text.match(/[^.!?]+[.!?]*["')]*\s*/g) ?? [text]).map((s) => s.trim()).filter(Boolean);
}

export function ClipRow({
  clip,
  goal,
  compact,
  onPost,
  onDetails,
  onFavorite,
  onDelete,
  selected,
  onSelect,
}: {
  clip: Clip;
  goal: Goal | "time" | "length";
  compact: boolean;
  onPost: () => void;
  onDetails: () => void;
  onFavorite: () => void;
  onDelete: () => void;
  selected: boolean;
  onSelect: (v: boolean) => void;
}) {
  const [showText, setShowText] = useState(!compact);
  const [showChecks, setShowChecks] = useState(false);
  const dims = clip.score_breakdown?.dims ?? {};
  const ins = clip.insights;
  const dur = Math.round(clip.output_duration ?? clip.duration);
  const edited = new Date(clip.rendered_at ?? clip.created_at);
  const rendering = clip.render_status === "rendering" || clip.render_status === "pending";
  const post = clip.post ?? {};
  const activeDim = goal in GOAL_DIM ? GOAL_DIM[goal as Goal] : goal === "general" ? "score" : null;
  const textVisible = showText;
  useEffect(() => setShowText(!compact), [compact]);

  return (
    <div className="group flex gap-3 border-b border-border py-5 last:border-0">
      <input
        type="checkbox"
        checked={selected}
        onChange={(e) => onSelect(e.target.checked)}
        className="mt-1 size-4 shrink-0 accent-[var(--primary)]"
        aria-label={`Select ${clip.title}`}
      />
      <div className={cx("relative shrink-0 self-start overflow-hidden rounded-xl bg-black", compact ? "w-[104px]" : "w-[150px]")}>
        {clip.video_url ? (
          <video src={clip.video_url} poster={clip.thumb_url ?? undefined} controls playsInline preload="none" className="aspect-[9/16] w-full object-cover" />
        ) : (
          <div className="grid aspect-[9/16] place-items-center text-xs text-white/70">
            {clip.render_status === "failed" ? "Render failed" : <Loader2 className="size-5 animate-spin" />}
          </div>
        )}
      </div>

      <div className="min-w-0 flex-1">
        <button onClick={onDetails} className="text-left text-[17px] font-semibold leading-snug hover:text-primary cursor-pointer">
          {clip.title}
        </button>
        <div className="mt-0.5 flex flex-wrap gap-x-3 text-xs text-muted">
          <span>{dur} seconds</span>
          <span>
            Edited: {edited.toLocaleDateString(undefined, { month: "short", day: "numeric" })} ·{" "}
            {edited.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}
          </span>
          {post.status === "scheduled" && post.scheduled_at && (
            <span className="inline-flex items-center gap-1 font-medium text-primary">
              <CalendarClock className="size-3.5" /> Scheduled {new Date(post.scheduled_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}
            </span>
          )}
          {post.status === "posted" && (
            <span className="inline-flex items-center gap-1 font-medium text-success">
              <CheckCircle2 className="size-3.5" /> Posted
            </span>
          )}
        </div>
        <div className="mt-1.5 flex flex-wrap gap-1">
          <button onClick={() => setShowChecks((v) => !v)} className="cursor-pointer" aria-expanded={showChecks}>
            <Chip icon={Flame} value={ins?.viral ?? clip.score} label="Viral potential" active={activeDim === "viral"} tone="text-orange-500" />
          </button>
          <Chip icon={Zap} value={Math.round(dims.hook ?? 50)} label="Hook" tone="text-amber-500" />
          <Chip icon={MessageCircle} value={Math.round(dims.context ?? 50)} label="Story / clarity" active={activeDim === "context"} tone="text-sky-500" />
          <Chip icon={Heart} value={Math.round(dims.emotion ?? 50)} label="Emotion" active={activeDim === "emotion"} tone="text-rose-500" />
          <Chip icon={Gauge} value={Math.round(dims.pacing ?? 50)} label="Pace" tone="text-emerald-500" />
          <Chip icon={CircleDot} value={clip.score} label="Overall score" active={activeDim === "score"} tone="text-primary" />
        </div>

        {showChecks && ins && (
          <div className="mt-2 max-w-xl rounded-xl border border-border p-3">
            <div className="mb-1.5 text-xs font-medium">
              Shorts checklist <span className="font-normal text-muted">· estimates from the clip itself, not view predictions</span>
            </div>
            <ul className="space-y-1">
              {ins.checklist.map((c) => (
                <li key={c.key} className="flex gap-2 text-xs">
                  {c.ok ? (
                    <CheckCircle2 className="mt-px size-3.5 shrink-0 text-success" />
                  ) : (
                    <CircleAlert className={cx("mt-px size-3.5 shrink-0", c.ok === null ? "text-muted" : "text-warning")} />
                  )}
                  <span>
                    {c.label}
                    {c.tip && <span className="text-muted"> — {c.tip}</span>}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Link
            href={`/app/clips/${clip.id}`}
            className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border px-3 text-sm hover:bg-surface-2"
          >
            <Pencil className="size-3.5" /> Edit clip
          </Link>
          {clip.download_url ? (
            <a href={clip.download_url} download className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border px-3 text-sm hover:bg-surface-2">
              <Download className="size-3.5" /> Download
            </a>
          ) : (
            <span className="inline-flex h-8 items-center rounded-lg border border-border px-3 text-sm text-muted opacity-60">Download</span>
          )}
          <button
            onClick={onPost}
            disabled={rendering || !clip.video_url}
            className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-primary px-3 text-sm font-medium text-on-primary hover:bg-primary-hover disabled:opacity-50 cursor-pointer disabled:cursor-not-allowed"
          >
            <Send className="size-3.5" /> Post or schedule
          </button>
        </div>

        {textVisible ? (
          <div className="mt-3 max-w-2xl rounded-xl bg-surface-2 px-4 py-3">
            <div className="max-h-32 space-y-2 overflow-y-auto pr-2 text-sm leading-relaxed text-text/75 scrollbar-thin">
              {clip.text ? sentences(clip.text).map((t, i) => <p key={i}>{t}</p>) : <p className="text-muted">No speech in this clip.</p>}
            </div>
          </div>
        ) : (
          <button onClick={() => setShowText(true)} className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-muted hover:text-text cursor-pointer">
            <ChevronDown className="size-3.5" /> View transcript
          </button>
        )}
      </div>

      <div className="flex shrink-0 flex-col gap-1">
        <button
          onClick={onFavorite}
          className={cx("grid size-8 place-items-center rounded-lg cursor-pointer", clip.favorite ? "text-amber-500" : "text-muted hover:text-text hover:bg-surface-2")}
          aria-label={clip.favorite ? "Remove from favourites" : "Add to favourites"}
          aria-pressed={clip.favorite}
        >
          <Star className={cx("size-4", clip.favorite && "fill-current")} />
        </button>
        <button onClick={() => setShowText((v) => !v)} className="grid size-8 place-items-center rounded-lg text-muted hover:text-text hover:bg-surface-2 cursor-pointer" aria-label="Show or hide transcript">
          <Rows3 className="size-4" />
        </button>
        <button onClick={onDetails} className="grid size-8 place-items-center rounded-lg text-muted hover:text-text hover:bg-surface-2 cursor-pointer" aria-label="Why this clip">
          <BarChart3 className="size-4" />
        </button>
        <button onClick={onDelete} className="grid size-8 place-items-center rounded-lg text-muted hover:text-danger hover:bg-surface-2 cursor-pointer" aria-label="Delete clip">
          <Trash2 className="size-4" />
        </button>
      </div>
    </div>
  );
}
