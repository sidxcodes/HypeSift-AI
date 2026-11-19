"use client";

import {
  ArrowRight,
  AudioWaveform,
  Captions,
  Crop,
  Gamepad2,
  GraduationCap,
  Link2,
  Lock,
  Mic,
  MessageSquareText,
  Scale,
  Sparkles,
  Upload,
  Video,
  Wand2,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Logo, ThemeToggle } from "@/components/brand";
import { Badge, Button, Card } from "@/components/ui";

// Real values from the bundled sample (samples/sample_podcast.mp4) — not mock data.
const DEMO_DIMS: [string, number][] = [
  ["Hook strength", 78],
  ["Context clarity", 93],
  ["AI editor (semantic)", 73],
  ["Emotional intensity", 61],
  ["Novelty", 59],
];

export default function Landing() {
  const router = useRouter();
  const [url, setUrl] = useState("");

  const go = (e: React.FormEvent) => {
    e.preventDefault();
    router.push(url.trim() ? `/app/new?url=${encodeURIComponent(url.trim())}` : "/app/new");
  };

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-40 border-b border-border/60 bg-bg/80 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
          <Logo />
          <nav className="hidden md:flex items-center gap-7 text-sm text-muted">
            <a href="#how" className="hover:text-text">How it works</a>
            <a href="#features" className="hover:text-text">Features</a>
            <a href="#creators" className="hover:text-text">Creators</a>
            <a href="#trust" className="hover:text-text">Privacy</a>
          </nav>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <Link href="/login" className="hidden sm:block">
              <Button variant="ghost" size="sm">Sign in</Button>
            </Link>
            <Link href="/signup">
              <Button size="sm">Get started</Button>
            </Link>
          </div>
        </div>
      </header>

      <main>
        {/* Hero */}
        <section className="mx-auto grid max-w-6xl gap-12 px-4 sm:px-6 pt-16 pb-20 lg:grid-cols-[1.1fr_0.9fr] lg:pt-24">
          <div>
            <Badge tone="primary" className="mb-5">
              <Sparkles className="size-3.5" /> Find the Hype. Create the Highlight.
            </Badge>
            <h1 className="font-display text-4xl font-bold leading-[1.05] tracking-tight sm:text-6xl">
              Turn long videos into <span className="text-primary">scroll-stopping</span> shorts.
            </h1>
            <p className="mt-5 max-w-xl text-lg text-muted">
              Discover the best moments, generate polished clips, add dynamic captions, and create platform-ready
              content with AI — and see exactly why each clip was picked.
            </p>
            <form onSubmit={go} className="mt-8 flex max-w-xl flex-col gap-2 sm:flex-row">
              <div className="relative flex-1">
                <Link2 className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted" />
                <input
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="Paste a YouTube link (or TikTok, Vimeo, .mp4…)"
                  aria-label="Video link"
                  className="h-12 w-full rounded-xl border border-border bg-surface pl-10 pr-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring/40 focus:border-primary"
                />
              </div>
              <Button size="lg" type="submit">
                <Wand2 className="size-4" /> AI Generate
              </Button>
            </form>
            <div className="mt-3 flex items-center gap-2 text-sm text-muted">
              <Upload className="size-4" />
              or{" "}
              <Link href="/app/new?mode=upload" className="font-medium text-text underline-offset-4 hover:underline">
                upload a video file
              </Link>
              — MP4, MOV, MKV, WEBM
            </div>
          </div>

          {/* Real sample output */}
          <div className="relative">
            <Card className="overflow-hidden p-4">
              <div className="flex gap-4">
                <div className="relative aspect-[9/16] w-[44%] shrink-0 overflow-hidden rounded-xl bg-black">
                  <video
                    src="/demo/demo-clip.mp4"
                    poster="/demo/demo-cover.jpg"
                    className="h-full w-full object-cover"
                    autoPlay
                    muted
                    loop
                    playsInline
                  />
                </div>
                <div className="flex min-w-0 flex-1 flex-col">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-muted">Clip 01 · 0:29</span>
                    <Badge tone="primary">76 / 100</Badge>
                  </div>
                  <div className="mt-2 font-display font-semibold leading-snug">Startup Mistakes: The Feature Trap</div>
                  <div className="mt-4 space-y-2.5">
                    {DEMO_DIMS.map(([k, v]) => (
                      <div key={k}>
                        <div className="flex justify-between text-[11px] text-muted">
                          <span>{k}</span>
                          <span>{v}</span>
                        </div>
                        <div className="mt-1 h-1.5 rounded-full bg-surface-2">
                          <div className="h-full rounded-full bg-primary" style={{ width: `${v}%` }} />
                        </div>
                      </div>
                    ))}
                  </div>
                  <ul className="mt-4 space-y-1.5 text-xs text-muted">
                    <li>• AI editor: a common failure told through a relatable anecdote</li>
                    <li>• Opens with a question, starts at a natural pause</li>
                  </ul>
                </div>
              </div>
              <p className="mt-3 text-[11px] text-muted">
                Real HypeSift output from the bundled sample podcast (synthetic voices). Scores are estimates, not
                view predictions.
              </p>
            </Card>
          </div>
        </section>

        {/* How it works */}
        <section id="how" className="border-y border-border bg-surface">
          <div className="mx-auto max-w-6xl px-4 sm:px-6 py-20">
            <h2 className="font-display text-3xl font-bold tracking-tight">From long video to posted short in four steps</h2>
            <div className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
              {[
                [Upload, "Add your video", "Upload a file or paste a direct video link. We check it before anything runs."],
                [AudioWaveform, "AI analysis", "Speech-to-text with word timing, audio energy, motion and scene changes."],
                [Scale, "Ranked highlights", "Every clip gets a 0–100 estimate with the reasons behind it."],
                [Video, "Edit & export", "Captions, vertical reframing, titles and hashtags — download and post."],
              ].map(([Icon, t, b], i) => {
                const I = Icon as typeof Upload;
                return (
                  <div key={i} className="relative">
                    <div className="mb-4 flex items-center gap-3">
                      <div className="grid size-10 place-items-center rounded-xl bg-primary-soft text-primary">
                        <I className="size-5" />
                      </div>
                      <span className="text-sm font-medium text-muted">Step {i + 1}</span>
                    </div>
                    <h3 className="font-semibold">{t as string}</h3>
                    <p className="mt-1 text-sm text-muted">{b as string}</p>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        {/* Features */}
        <section id="features" className="mx-auto max-w-6xl px-4 sm:px-6 py-20">
          <h2 className="font-display text-3xl font-bold tracking-tight">Built for creators who want control</h2>
          <p className="mt-2 max-w-2xl text-muted">The AI does the heavy lifting; you make every final call.</p>
          <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[
              [Scale, "Explainable scores", "Seven dimensions — hook, context, pacing, novelty, emotion, visuals, relevance — with the evidence for each."],
              [Gamepad2, "Genre-aware", "Gaming, podcasts, education, tutorials, vlogs and reviews are weighted differently."],
              [Captions, "Six caption styles", "Word-timed captions from Clean Minimal to Karaoke Highlight, burned into the export."],
              [Crop, "Smart reframing", "Face- and motion-aware 9:16, 1:1, 4:5 and 16:9 crops, plus stacked two-speaker layouts."],
              [MessageSquareText, "Publishing packages", "Titles, descriptions and hashtags for YouTube, Instagram, TikTok, LinkedIn, Facebook and X."],
              [Wand2, "Creator assistant", "“Find the funniest 30-second moment” triggers a real search — and says so when it can't help."],
            ].map(([Icon, t, b]) => {
              const I = Icon as typeof Upload;
              return (
                <Card key={t as string} className="p-6">
                  <I className="size-5 text-primary" />
                  <h3 className="mt-4 font-semibold">{t as string}</h3>
                  <p className="mt-1 text-sm text-muted">{b as string}</p>
                </Card>
              );
            })}
          </div>
        </section>

        {/* Creators */}
        <section id="creators" className="border-y border-border bg-surface">
          <div className="mx-auto max-w-6xl px-4 sm:px-6 py-20">
            <h2 className="font-display text-3xl font-bold tracking-tight">Made for every kind of long video</h2>
            <div className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
              {[
                [Mic, "Podcasters", "Pull the sharpest answers and stories from hour-long conversations."],
                [Gamepad2, "Streamers & gamers", "Catch the loud reactions, clutch plays and chaotic moments."],
                [GraduationCap, "Educators", "Turn lectures and tutorials into clear, standalone lessons."],
                [Video, "YouTubers & teams", "Repurpose every upload into a week of shorts with copy ready to post."],
              ].map(([Icon, t, b]) => {
                const I = Icon as typeof Upload;
                return (
                  <div key={t as string}>
                    <I className="size-5 text-accent" />
                    <h3 className="mt-3 font-semibold">{t as string}</h3>
                    <p className="mt-1 text-sm text-muted">{b as string}</p>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        {/* Trust */}
        <section id="trust" className="mx-auto max-w-6xl px-4 sm:px-6 py-20">
          <Card className="grid gap-8 p-8 md:grid-cols-[auto_1fr] md:items-center">
            <div className="grid size-14 place-items-center rounded-2xl bg-primary-soft text-primary">
              <Lock className="size-6" />
            </div>
            <div>
              <h2 className="font-display text-2xl font-bold tracking-tight">Private, honest, rights-aware</h2>
              <ul className="mt-3 grid gap-2 text-sm text-muted sm:grid-cols-2">
                <li>• Self-hostable: transcription and AI run on your own machine.</li>
                <li>• Projects are private to your account; download links expire.</li>
                <li>• Paste a YouTube link and go — use videos you own or have permission to clip.</li>
                <li>• Scores are explained estimates — never promises of views or revenue.</li>
              </ul>
            </div>
          </Card>
          <div className="mt-16 text-center">
            <h2 className="font-display text-3xl font-bold tracking-tight">Ready to find your highlights?</h2>
            <Link href="/signup" className="mt-6 inline-block">
              <Button size="lg">
                Start for free <ArrowRight className="size-4" />
              </Button>
            </Link>
          </div>
        </section>
      </main>

      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-4 sm:px-6 py-8 text-sm text-muted sm:flex-row sm:items-center sm:justify-between">
          <Logo />
          <p>Find the Hype. Create the Highlight. · Only process videos you have the rights to.</p>
        </div>
      </footer>
    </div>
  );
}
