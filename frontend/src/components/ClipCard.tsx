"use client";

import { AlertTriangle, Captions, Download, Loader2, Pencil, Play, Star } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";
import { fmtTime } from "@/lib/api";
import type { Clip } from "@/lib/types";
import { Badge, Button, Card, cx, scoreTone } from "./ui";

export function ClipCard({ clip, index, onOpen, onFavorite }: { clip: Clip; index: number; onOpen: () => void; onFavorite: () => void }) {
  const ref = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);
  const rendered = clip.render_status === "rendered" && clip.video_url;
  const aspect = clip.edits?.aspect ?? "9:16";
  const aspectClass = { "9:16": "aspect-[9/16]", "1:1": "aspect-square", "4:5": "aspect-[4/5]", "16:9": "aspect-video" }[aspect];

  const toggle = () => {
    const v = ref.current;
    if (!v) return;
    if (v.paused) {
      v.play();
      setPlaying(true);
    } else {
      v.pause();
      setPlaying(false);
    }
  };

  return (
    <Card className="group flex flex-col overflow-hidden">
      <div className={cx("relative overflow-hidden bg-black", aspect === "16:9" ? "aspect-video" : "aspect-[9/14]")}>
        {rendered ? (
          <>
            <video
              ref={ref}
              src={clip.video_url!}
              poster={clip.thumb_url ?? undefined}
              className={cx("absolute inset-0 m-auto h-full", aspectClass, "object-contain")}
              playsInline
              preload="none"
              onEnded={() => setPlaying(false)}
              onClick={toggle}
            />
            {!playing && (
              <button
                onClick={toggle}
                className="absolute inset-0 grid place-items-center bg-black/10 transition hover:bg-black/25 cursor-pointer"
                aria-label={`Play ${clip.title}`}
              >
                <span className="grid size-12 place-items-center rounded-full bg-white/90 text-black shadow">
                  <Play className="size-5 translate-x-0.5" fill="currentColor" />
                </span>
              </button>
            )}
          </>
        ) : (
          <div className="absolute inset-0 grid place-items-center text-center text-sm text-white/80">
            {clip.render_status === "failed" ? (
              <div className="px-4">
                <AlertTriangle className="mx-auto mb-2 size-6 text-warning" />
                Render failed
              </div>
            ) : (
              <div>
                <Loader2 className="mx-auto mb-2 size-6 animate-spin" />
                {clip.render_status === "rendering" ? "Rendering…" : "Queued for render"}
              </div>
            )}
          </div>
        )}
        <div className="absolute left-2 top-2 flex gap-1.5">
          <Badge tone={scoreTone(clip.score)} className="backdrop-blur bg-surface/90 shadow-sm">
            {clip.score}/100
          </Badge>
        </div>
        <button
          onClick={onFavorite}
          className="absolute right-2 top-2 grid size-8 place-items-center rounded-full bg-black/40 text-white backdrop-blur transition hover:bg-black/60 cursor-pointer"
          aria-label={clip.favorite ? "Remove from favorites" : "Add to favorites"}
          aria-pressed={clip.favorite}
        >
          <Star className="size-4" fill={clip.favorite ? "#facc15" : "none"} color={clip.favorite ? "#facc15" : "white"} />
        </button>
      </div>
      <div className="flex flex-1 flex-col p-4">
        <div className="text-xs text-muted">
          Clip {String(index + 1).padStart(2, "0")} · {fmtTime(clip.output_duration ?? clip.duration)} · source {fmtTime(clip.start)}–{fmtTime(clip.end)}
        </div>
        <button onClick={onOpen} className="mt-1 text-left font-semibold leading-snug hover:text-primary cursor-pointer line-clamp-2">
          {clip.title}
        </button>
        <p className="mt-2 text-sm text-muted line-clamp-2">{clip.reasons[0]}</p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {clip.edits?.captions?.enabled !== false && (
            <Badge>
              <Captions className="size-3" /> Captions
            </Badge>
          )}
          <Badge>{aspect}</Badge>
          {clip.score_breakdown?.request && <Badge tone="accent">Assistant</Badge>}
        </div>
        <div className="mt-auto flex gap-2 pt-4">
          <Button variant="secondary" size="sm" className="flex-1" onClick={onOpen}>
            Details
          </Button>
          <Link href={`/app/clips/${clip.id}`} className="flex-1">
            <Button variant="secondary" size="sm" className="w-full">
              <Pencil className="size-3.5" /> Edit
            </Button>
          </Link>
          {clip.download_url && (
            <a href={clip.download_url} download aria-label={`Download ${clip.title}`}>
              <Button size="sm">
                <Download className="size-4" />
              </Button>
            </a>
          )}
        </div>
      </div>
    </Card>
  );
}
