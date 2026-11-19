"use client";

import { Download, FileText, Pencil, ThumbsDown, ThumbsUp, Trash2, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, fmtTime } from "@/lib/api";
import type { Clip } from "@/lib/types";
import { FixWithAI } from "./FixWithAI";
import { PublishPanel } from "./PublishPanel";
import { ThumbnailsPanel } from "./ThumbnailsPanel";
import { ScoreBreakdown } from "./ScoreBreakdown";
import { useToast } from "./toast";
import { Button, cx, Segmented } from "./ui";

export type DrawerTab = "fix" | "thumbs" | "publish" | "score" | "transcript";

export function ClipDrawer({
  clip,
  onClose,
  onChange,
  initialTab = "fix",
}: {
  clip: Clip | null;
  onClose: () => void;
  onChange: () => void;
  initialTab?: DrawerTab;
}) {
  const toast = useToast();
  const [tab, setTab] = useState<DrawerTab>(initialTab);
  useEffect(() => setTab(initialTab), [initialTab, clip?.id]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const rate = async (r: -1 | 1) => {
    if (!clip) return;
    await api.feedback(clip.id, clip.feedback === r ? 0 : r);
    onChange();
    toast("info", "Thanks — your ratings tune future rankings for your account.");
  };
  const remove = async () => {
    if (!clip || !confirm("Delete this clip and its export? This can't be undone.")) return;
    await api.deleteClip(clip.id);
    onClose();
    onChange();
  };

  return (
    <AnimatePresence>
      {clip && (
        <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label={clip.title}>
          <motion.div className="absolute inset-0 bg-black/45" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} />
          <motion.aside
            initial={{ x: 40, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 40, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="absolute inset-y-0 right-0 flex w-full max-w-4xl flex-col overflow-hidden bg-bg shadow-2xl sm:rounded-l-2xl"
          >
            <div className="flex items-center justify-between gap-3 border-b border-border px-5 h-14">
              <div className="min-w-0 truncate font-display font-semibold">{clip.title}</div>
              <button onClick={onClose} className="p-2 text-muted hover:text-text cursor-pointer" aria-label="Close">
                <X className="size-5" />
              </button>
            </div>
            <div className="grid flex-1 gap-6 overflow-y-auto p-5 scrollbar-thin md:grid-cols-[280px_1fr]">
              <div>
                <div className="overflow-hidden rounded-2xl bg-black">
                  {clip.video_url ? (
                    <video src={clip.video_url} poster={clip.thumb_url ?? undefined} controls playsInline className="max-h-[60vh] w-full" />
                  ) : (
                    <div className="grid aspect-[9/16] place-items-center text-sm text-white/70">Not rendered yet</div>
                  )}
                </div>
                <div className="mt-3 text-xs text-muted">
                  Source {fmtTime(clip.start)}–{fmtTime(clip.end)} · output {fmtTime(clip.output_duration ?? clip.duration)}
                </div>
                <div className="mt-4 grid gap-2">
                  {clip.download_url && (
                    <a href={clip.download_url} download>
                      <Button className="w-full">
                        <Download className="size-4" /> Download MP4
                      </Button>
                    </a>
                  )}
                  {clip.srt_url && (
                    <a href={clip.srt_url} download>
                      <Button variant="secondary" className="w-full">
                        <FileText className="size-4" /> Download captions (.srt)
                      </Button>
                    </a>
                  )}
                  <Link href={`/app/clips/${clip.id}`}>
                    <Button variant="secondary" className="w-full">
                      <Pencil className="size-4" /> Open in editor
                    </Button>
                  </Link>
                </div>
                <div className="mt-4 flex items-center gap-2">
                  <span className="text-xs text-muted">Good pick?</span>
                  <button
                    onClick={() => rate(1)}
                    className={cx("grid size-8 place-items-center rounded-lg border border-border cursor-pointer", clip.feedback === 1 ? "bg-success/15 text-success" : "text-muted hover:text-text")}
                    aria-label="Good clip"
                    aria-pressed={clip.feedback === 1}
                  >
                    <ThumbsUp className="size-4" />
                  </button>
                  <button
                    onClick={() => rate(-1)}
                    className={cx("grid size-8 place-items-center rounded-lg border border-border cursor-pointer", clip.feedback === -1 ? "bg-danger/15 text-danger" : "text-muted hover:text-text")}
                    aria-label="Bad clip"
                    aria-pressed={clip.feedback === -1}
                  >
                    <ThumbsDown className="size-4" />
                  </button>
                  <button onClick={remove} className="ml-auto grid size-8 place-items-center rounded-lg text-muted hover:text-danger cursor-pointer" aria-label="Delete clip">
                    <Trash2 className="size-4" />
                  </button>
                </div>
              </div>
              <div className="min-w-0">
                <Segmented
                  value={tab}
                  onChange={setTab}
                  options={[
                    { value: "fix", label: "Fix with AI" },
                    { value: "thumbs", label: "Thumbnails" },
                    { value: "publish", label: "Copy" },
                    { value: "score", label: "Why this clip" },
                    { value: "transcript", label: "Transcript" },
                  ]}
                  className="flex-wrap"
                />
                <div className="mt-5">
                  {tab === "fix" && <FixWithAI clip={clip} onChange={onChange} />}
                  {tab === "thumbs" && <ThumbnailsPanel clip={clip} onChange={onChange} />}
                  {tab === "publish" && <PublishPanel clip={clip} onChange={onChange} />}
                  {tab === "score" && <ScoreBreakdown clip={clip} />}
                  {tab === "transcript" && <p className="whitespace-pre-wrap text-sm leading-relaxed">{clip.text || "No speech in this clip."}</p>}
                </div>
              </div>
            </div>
          </motion.aside>
        </div>
      )}
    </AnimatePresence>
  );
}
