"use client";

import { CalendarClock, Check, ChevronLeft, ChevronRight, Copy, ExternalLink, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { Clip, PublishPackage } from "@/lib/types";
import { useSession } from "./AppShell";
import { useToast } from "./toast";
import { Button, cx, Input, Select, Textarea } from "./ui";

export const PLATFORM_META: Record<string, { label: string; color: string; upload: string; letter: string }> = {
  youtube: { label: "YouTube", color: "#FF0033", upload: "https://www.youtube.com/upload", letter: "▶" },
  tiktok: { label: "TikTok", color: "#111111", upload: "https://www.tiktok.com/tiktokstudio/upload", letter: "♪" },
  instagram: { label: "Instagram", color: "#D62976", upload: "https://www.instagram.com/", letter: "◎" },
  linkedin: { label: "LinkedIn", color: "#0A66C2", upload: "https://www.linkedin.com/feed/?shareActive=true", letter: "in" },
  facebook: { label: "Facebook", color: "#1877F2", upload: "https://www.facebook.com/reels/create", letter: "f" },
  x: { label: "X", color: "#000000", upload: "https://x.com/compose/post", letter: "𝕏" },
};

const YT_CATEGORIES = [
  "People & Blogs", "Education", "Entertainment", "Science & Technology", "Howto & Style", "Gaming", "Comedy",
  "News & Politics", "Sports", "Music", "Film & Animation", "Travel & Events", "Nonprofits & Activism",
];

type Fields = Record<string, string | boolean>;

export function PlatformIcon({ p, className }: { p: string; className?: string }) {
  const m = PLATFORM_META[p] ?? { color: "#666", letter: "?" };
  return (
    <span className={cx("grid shrink-0 place-items-center rounded-full text-[11px] font-bold text-white ring-1 ring-white/20", className ?? "size-8")} style={{ background: m.color }}>
      {m.letter}
    </span>
  );
}

const str = (v: unknown) => (Array.isArray(v) ? v.join(" ") : typeof v === "string" ? v : "");

/** Starting text for each platform, from the AI-written publishing package. */
function initialFields(clip: Clip): Record<string, Fields> {
  const pkg = (clip.publish as PublishPackage)?.platforms ?? {};
  const saved = (clip.post?.platforms ?? {}) as Record<string, Fields>;
  const out: Record<string, Fields> = {};
  for (const p of Object.keys(PLATFORM_META)) {
    const b = pkg[p];
    if (!b && !saved[p]) continue;
    const tags = str(b?.hashtags);
    let f: Fields;
    if (p === "youtube") {
      f = {
        title: str((b?.titles as string[] | undefined)?.[0]) || clip.title,
        caption: [str(b?.description), tags].filter(Boolean).join("\n\n"),
        category: "People & Blogs",
        visibility: "public",
      };
    } else if (p === "tiktok") {
      f = { caption: [str(b?.description), tags].filter(Boolean).join(" "), who: "everyone", comment: true, duet: true, stitch: true };
    } else if (p === "instagram") {
      f = { caption: [str(b?.caption), tags].filter(Boolean).join("\n\n") };
    } else {
      f = { caption: [str(b?.post), tags].filter(Boolean).join("\n\n") };
    }
    out[p] = { include: true, ...f, ...(saved[p] ?? {}) };
  }
  return out;
}

function localParts(d: Date) {
  return { y: d.getFullYear(), m: d.getMonth(), day: d.getDate(), h: d.getHours(), min: d.getMinutes() };
}

function MiniCalendar({ value, onChange }: { value: Date; onChange: (d: Date) => void }) {
  const [view, setView] = useState(new Date(value.getFullYear(), value.getMonth(), 1));
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const first = (view.getDay() + 6) % 7; // Monday first
  const days = new Date(view.getFullYear(), view.getMonth() + 1, 0).getDate();
  const cells = [...Array(first).fill(null), ...Array.from({ length: days }, (_, i) => i + 1)];
  return (
    <div className="rounded-xl border border-border p-3">
      <div className="mb-2 flex items-center justify-between">
        <button type="button" onClick={() => setView(new Date(view.getFullYear(), view.getMonth() - 1, 1))} className="p-1 text-muted hover:text-text cursor-pointer" aria-label="Previous month">
          <ChevronLeft className="size-4" />
        </button>
        <div className="text-sm font-medium">{view.toLocaleDateString(undefined, { month: "long", year: "numeric" })}</div>
        <button type="button" onClick={() => setView(new Date(view.getFullYear(), view.getMonth() + 1, 1))} className="p-1 text-muted hover:text-text cursor-pointer" aria-label="Next month">
          <ChevronRight className="size-4" />
        </button>
      </div>
      <div className="grid grid-cols-7 gap-y-1 text-center text-xs">
        {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => (
          <div key={d} className="py-1 text-muted">
            {d}
          </div>
        ))}
        {cells.map((d, i) => {
          if (!d) return <div key={i} />;
          const date = new Date(view.getFullYear(), view.getMonth(), d);
          const past = date < today;
          const sel = date.toDateString() === value.toDateString();
          return (
            <button
              key={i}
              type="button"
              disabled={past}
              onClick={() => onChange(new Date(view.getFullYear(), view.getMonth(), d, value.getHours(), value.getMinutes()))}
              className={cx(
                "mx-auto grid size-8 place-items-center rounded-lg transition cursor-pointer disabled:cursor-default disabled:opacity-30",
                sel ? "bg-primary font-semibold text-on-primary" : "hover:bg-surface-2",
              )}
            >
              {d}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function PostDrawer({ clip, onClose, onChange }: { clip: Clip | null; onClose: () => void; onChange: () => void }) {
  const toast = useToast();
  const { user } = useSession();
  const socials = user.brand_kit?.socials ?? {};
  const [mode, setMode] = useState<"now" | "schedule">("now");
  const [fields, setFields] = useState<Record<string, Fields>>({});
  const [when, setWhen] = useState<Date>(() => {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    d.setHours(18, 30, 0, 0);
    return d;
  });
  const tz = useMemo(() => user.brand_kit?.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone, [user.brand_kit?.timezone]);
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (!clip) return;
    setFields(initialFields(clip));
    setDone({});
    if (clip.post?.status === "scheduled" && clip.post.scheduled_at) {
      setMode("schedule");
      setWhen(new Date(clip.post.scheduled_at));
    } else setMode("now");
  }, [clip]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const setF = (p: string, k: string, v: string | boolean) => setFields((f) => ({ ...f, [p]: { ...f[p], [k]: v } }));
  const included = Object.entries(fields).filter(([, f]) => f.include);

  const postTo = async (p: string) => {
    if (!clip) return;
    const f = fields[p];
    const text = p === "youtube" ? `${f.title}\n\n${f.caption}` : String(f.caption ?? "");
    try {
      await navigator.clipboard.writeText(text);
    } catch {}
    if (clip.download_url) {
      const a = document.createElement("a");
      a.href = clip.download_url;
      a.download = "";
      document.body.appendChild(a);
      a.click();
      a.remove();
    }
    window.open(PLATFORM_META[p].upload, "_blank", "noopener");
    setDone((d) => ({ ...d, [p]: true }));
    toast("info", `${PLATFORM_META[p].label}: the video is downloading and the ${p === "youtube" ? "title and description are" : "caption is"} copied — paste it in the upload page.`);
  };

  const save = async (status: "scheduled" | "posted" | "draft") => {
    if (!clip) return;
    if (status === "scheduled" && when.getTime() < Date.now() + 60_000) {
      toast("error", "Pick a time in the future.");
      return;
    }
    setSaving(true);
    try {
      await api.setPost(clip.id, {
        status,
        scheduled_at: status === "scheduled" ? when.toISOString() : null,
        timezone: tz,
        platforms: fields,
      });
      if (status === "scheduled" && typeof Notification !== "undefined" && Notification.permission === "default") {
        Notification.requestPermission().catch(() => {});
      }
      toast(
        "success",
        status === "scheduled"
          ? `Scheduled for ${when.toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}. HypeSift will remind you when it's time.`
          : status === "posted"
            ? "Marked as posted."
            : "Schedule removed.",
      );
      onChange();
      onClose();
    } catch (e) {
      toast("error", (e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const lp = localParts(when);
  const hour12 = lp.h % 12 || 12;
  const pm = lp.h >= 12;
  const setTime = (h12: number, min: number, isPm: boolean) => {
    const d = new Date(when);
    d.setHours((h12 % 12) + (isPm ? 12 : 0), min, 0, 0);
    setWhen(d);
  };
  const quick = (label: string, dayOffset: number, h: number, m = 0) => {
    const d = new Date();
    d.setDate(d.getDate() + dayOffset);
    d.setHours(h, m, 0, 0);
    return { label, d };
  };
  const sat = (6 - new Date().getDay() + 7) % 7 || 7;
  const quicks = [quick("Today 7 PM", 0, 19), quick("Tomorrow 12:30 PM", 1, 12, 30), quick("Tomorrow 7 PM", 1, 19), quick("Saturday 10 AM", sat, 10)].filter(
    (q) => q.d.getTime() > Date.now() + 15 * 60_000,
  );

  return (
    <AnimatePresence>
      {clip && (
        <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label="Post to your socials">
          <motion.div className="absolute inset-0 bg-black/55" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} />
          <motion.aside
            initial={{ x: 60, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 60, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="absolute inset-y-0 right-0 flex w-full max-w-[520px] flex-col bg-surface shadow-2xl"
          >
            <div className="flex items-start justify-between gap-3 px-6 pt-5">
              <div>
                <h2 className="text-lg font-semibold">{mode === "now" ? "Post to your socials" : "Schedule your posts"}</h2>
                <p className="mt-0.5 text-xs text-muted">
                  {mode === "now"
                    ? "Post now downloads the clip, copies the text and opens each platform's upload page."
                    : "Set up your post for a scheduled time. HypeSift puts it on your calendar and reminds you when it's due."}
                </p>
              </div>
              <button onClick={onClose} className="p-1.5 text-muted hover:text-text cursor-pointer" aria-label="Close">
                <X className="size-5" />
              </button>
            </div>

            <div className="flex-1 space-y-5 overflow-y-auto px-6 py-4 scrollbar-thin">
              <div>
                <div className="mb-1.5 text-sm font-medium">Post setting:</div>
                {(["now", "schedule"] as const).map((m) => (
                  <label key={m} className={cx("mb-1.5 flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm cursor-pointer", mode === m ? "bg-surface-2" : "hover:bg-surface-2/60")}>
                    <input type="radio" name="post-mode" checked={mode === m} onChange={() => setMode(m)} className="accent-[var(--primary)]" />
                    {m === "now" ? "Post now" : "Schedule for later"}
                  </label>
                ))}
              </div>

              {mode === "schedule" && (
                <div className="space-y-3">
                  <div className="text-sm font-medium">Pick a time and day:</div>
                  <MiniCalendar value={when} onChange={setWhen} />
                  <div className="grid grid-cols-3 gap-2">
                    <label className="text-xs text-muted">
                      Hour
                      <Select value={String(hour12)} onChange={(v) => setTime(Number(v), lp.min, pm)} options={Array.from({ length: 12 }, (_, i) => ({ value: String(i + 1), label: String(i + 1) }))} />
                    </label>
                    <label className="text-xs text-muted">
                      Minutes
                      <Select
                        value={String(lp.min - (lp.min % 5))}
                        onChange={(v) => setTime(hour12, Number(v), pm)}
                        options={Array.from({ length: 12 }, (_, i) => ({ value: String(i * 5), label: String(i * 5).padStart(2, "0") }))}
                      />
                    </label>
                    <label className="text-xs text-muted">
                      &nbsp;
                      <Select value={pm ? "PM" : "AM"} onChange={(v) => setTime(hour12, lp.min, v === "PM")} options={[{ value: "AM", label: "AM" }, { value: "PM", label: "PM" }]} />
                    </label>
                  </div>
                  <div className="text-xs text-muted">Timezone: {tz}</div>
                  {quicks.length > 0 && (
                    <div>
                      <div className="mb-1.5 flex items-center gap-1.5 text-xs text-muted">
                        <CalendarClock className="size-3.5" /> Popular times for Shorts (check your own audience in YouTube Studio → Analytics)
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {quicks.map((q) => (
                          <button
                            key={q.label}
                            type="button"
                            onClick={() => setWhen(q.d)}
                            className="h-7 rounded-full border border-border px-2.5 text-xs hover:border-primary hover:text-primary cursor-pointer"
                          >
                            {q.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                  <div className="text-sm font-medium">Your content:</div>
                </div>
              )}

              {Object.keys(fields).length === 0 && <p className="text-sm text-muted">No publishing copy yet — it&apos;s written right after the clip renders.</p>}

              {Object.entries(fields).map(([p, f]) => (
                <div key={p} className={cx("rounded-2xl border border-border", !f.include && "opacity-60")}>
                  <div className="flex items-center gap-2.5 px-4 py-3">
                    <PlatformIcon p={p} />
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium">{PLATFORM_META[p].label}</div>
                      <div className="truncate text-xs text-muted">{socials[p] || "Add your handle in Social profiles"}</div>
                    </div>
                    <label className="flex items-center gap-1.5 text-xs text-muted cursor-pointer">
                      <input type="checkbox" checked={!!f.include} onChange={(e) => setF(p, "include", e.target.checked)} className="accent-[var(--primary)]" /> Include
                    </label>
                  </div>
                  {f.include && (
                    <div className="grid gap-3 border-t border-border p-4 sm:grid-cols-[110px_1fr]">
                      <div className="self-start overflow-hidden rounded-xl bg-black">
                        {clip.video_url ? (
                          <video src={clip.video_url} poster={clip.thumb_url ?? undefined} controls playsInline preload="none" className="aspect-[9/16] w-full object-cover" />
                        ) : (
                          <div className="aspect-[9/16]" />
                        )}
                      </div>
                      <div className="min-w-0 space-y-2.5">
                        {p === "youtube" && (
                          <label className="block text-xs font-medium">
                            Title <span className="font-normal text-muted">({String(f.title ?? "").length}/100)</span>
                            <Input value={String(f.title ?? "")} maxLength={100} onChange={(e) => setF(p, "title", e.target.value)} className="mt-1 h-9" />
                          </label>
                        )}
                        <label className="block text-xs font-medium">
                          {p === "youtube" ? "Description" : "Caption"}
                          <Textarea value={String(f.caption ?? "")} onChange={(e) => setF(p, "caption", e.target.value)} rows={5} className="mt-1 text-[13px]" />
                        </label>
                        {p === "youtube" && (
                          <div className="grid grid-cols-2 gap-2">
                            <label className="block text-xs font-medium">
                              Category
                              <Select value={String(f.category)} onChange={(v) => setF(p, "category", v)} options={YT_CATEGORIES.map((c) => ({ value: c, label: c }))} className="mt-1 h-9" />
                            </label>
                            <label className="block text-xs font-medium">
                              Visibility
                              <Select value={String(f.visibility)} onChange={(v) => setF(p, "visibility", v)} options={[["public", "Public"], ["unlisted", "Unlisted"], ["private", "Private"]].map(([value, label]) => ({ value, label }))} className="mt-1 h-9" />
                            </label>
                          </div>
                        )}
                        {p === "tiktok" && (
                          <>
                            <label className="block text-xs font-medium">
                              Who can view this video
                              <Select value={String(f.who)} onChange={(v) => setF(p, "who", v)} options={[["everyone", "Everyone"], ["followers", "Followers"], ["only_me", "Only me"]].map(([value, label]) => ({ value, label }))} className="mt-1 h-9" />
                            </label>
                            <div className="text-xs font-medium">
                              Allow users to
                              <div className="mt-1 flex gap-4 font-normal">
                                {["comment", "duet", "stitch"].map((k) => (
                                  <label key={k} className="flex items-center gap-1.5 capitalize cursor-pointer">
                                    <input type="checkbox" checked={!!f[k]} onChange={(e) => setF(p, k, e.target.checked)} className="accent-[var(--primary)]" /> {k}
                                  </label>
                                ))}
                              </div>
                            </div>
                          </>
                        )}
                        {mode === "now" && (
                          <div className="flex flex-wrap gap-2 pt-1">
                            <Button size="sm" onClick={() => postTo(p)}>
                              {done[p] ? <Check className="size-4" /> : <ExternalLink className="size-4" />} {done[p] ? "Opened" : "Post now"}
                            </Button>
                            <Button
                              size="sm"
                              variant="secondary"
                              onClick={async () => {
                                await navigator.clipboard.writeText(p === "youtube" ? `${f.title}\n\n${f.caption}` : String(f.caption ?? ""));
                                toast("success", "Copied.");
                              }}
                            >
                              <Copy className="size-4" /> Copy text
                            </Button>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>

            <div className="flex items-center justify-between gap-2 border-t border-border px-6 py-4">
              {clip.post?.status === "scheduled" || clip.post?.status === "posted" ? (
                <Button variant="ghost" size="sm" onClick={() => save("draft")} disabled={saving}>
                  {clip.post.status === "scheduled" ? "Remove schedule" : "Mark as not posted"}
                </Button>
              ) : (
                <span />
              )}
              {mode === "schedule" ? (
                <Button onClick={() => save("scheduled")} loading={saving} disabled={!included.length}>
                  <CalendarClock className="size-4" /> Schedule
                </Button>
              ) : (
                <Button onClick={() => save("posted")} loading={saving} variant={Object.keys(done).length ? "primary" : "secondary"}>
                  <Check className="size-4" /> Mark as posted
                </Button>
              )}
            </div>
          </motion.aside>
        </div>
      )}
    </AnimatePresence>
  );
}
