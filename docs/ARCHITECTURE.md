# Architecture

```
Browser (Next.js)
  │  same-origin /api/* proxy (cookies + signed media links)
  ▼
FastAPI ── auth · uploads · projects · clips · jobs · assistant · media
  │  writes rows                                  ▲ reads progress
  ▼                                               │
SQLite/Postgres ◄────────── Worker (thread or `python -m app.worker`)
                                │
                                ├─ ingest      video-site link (yt-dlp) / direct file (SSRF-guarded) / upload
                                ├─ prepare     ffprobe, thumbnail, H.264 preview proxy if needed
                                ├─ transcribe  faster-whisper, word timestamps (CUDA → CPU)
                                ├─ analyze     loudness/flux/flatness @10 Hz, motion + cuts @2 Hz
                                ├─ rank        sentence windows → 7-dim score → NMS → optional LLM
                                ├─ render      reframe → silence cut → ASS captions → fades → encode
                                └─ publish     per-platform copy (LLM or template engine)
                                │
                          Local storage (S3-compatible interface)
```

## Why these choices

- **DB-backed job queue instead of Redis + Celery.** A single-node, zero-cost deployment already has a
  database with atomic updates. Jobs are rows with status, stage timeline, progress, attempts and a
  cancel flag. The worker claims a job with a conditional `UPDATE … WHERE status='queued'`, so several
  workers can share a database safely. Each handler maps 1:1 onto a Celery task if scale ever needs it.
- **SQLite by default, Postgres-ready.** One file, WAL mode, no service to run; set
  `HYPESIFT_DATABASE_URL` for Postgres. Small ordered migrations run at startup (`app/migrations.py`).
- **Local storage behind an interface.** Keys look like `projects/<id>/source.mp4`; replace `LocalStorage`
  with an S3 client for cloud deployments. Media is served through HMAC-signed links that expire.
- **No paid AI.** Whisper and the LLM run locally. Everything AI-dependent has a deterministic fallback
  and labels which engine produced it.

## Data model

| Table | Purpose |
|---|---|
| `users`, `auth_sessions` | scrypt password hashes; SHA-256 of session tokens only; brand kit JSON |
| `uploads` | resumable chunked uploads (`received` offset) |
| `projects` | source, generation settings, probe info, analysis summary, status/error |
| `clips` | source range, score + breakdown + reasons, edits (captions/crop/overlays/audio), reframe path, publishing package, render status and output keys, feedback |
| `jobs` | kind (`generate`, `discover`, `render`, `publish`), status, stage timeline, progress, attempts, cancel flag |

## API (all under `/api`)

| Method | Path | |
|---|---|---|
| POST | `/auth/signup`, `/auth/login`, `/auth/logout` · GET `/auth/me` · PUT `/auth/brand-kit` | accounts |
| POST | `/uploads` → PUT `/uploads/{id}?offset=` → POST `/uploads/{id}/complete` · GET `/uploads/{id}` | resumable upload |
| POST | `/url/check` | read a link: title, channel, length, size, importable or why not |
| POST/GET | `/projects` · GET/PATCH/DELETE `/projects/{id}` · POST `/projects/{id}/generate` · GET `/projects/{id}/transcript` | projects & AI Generate |
| GET | `/clips` · GET/PATCH/DELETE `/clips/{id}` · POST `/clips/{id}/render` | library, editor, re-render |
| POST/PUT | `/clips/{id}/publish` · POST `/clips/{id}/feedback`, `/clips/{id}/favorite` | copy, ratings |
| GET | `/jobs` · `/jobs/{id}` · POST `/jobs/{id}/cancel` | real progress |
| POST | `/assistant` | natural language → validated action → job |
| GET | `/media?key&exp&sig[&dl]` · `/meta` · `/health` · `/fonts/*` | signed files, presets, status |

## Scoring

For each candidate window the scorer computes seven 0–100 dimensions; `genres.py` holds the per-genre
weights, and the requested mood shifts them. The weighted mean is stretched around 50 for readability.
With the LLM on, it is blended as `0.7 × signals + 0.3 × semantic`. Creator 👍/👎 ratings nudge the
weights (±30% at most) toward the dimensions of the clips that creator liked. Every dimension keeps its
evidence strings, so the UI shows the reasons rather than only a number.

## Operational notes and risks

- **Large uploads:** 8 MB chunks, resumable; the limit is configurable (`HYPESIFT_MAX_UPLOAD_MB`). The
  proxy timeout is 5 minutes per request.
- **Codecs:** anything FFmpeg can decode is accepted. Sources a browser can't play (HEVC, MKV, AVI…)
  get a 720p H.264 preview proxy for the editor; exports always come from the original file.
- **Cost / throughput:** whisper `small` on an RTX 3050 runs at about 25× real time; CPU `base` at about
  15×. Renders use NVENC when available. One worker means one job at a time; raise
  `HYPESIFT_WORKER_CONCURRENCY` or run more worker processes on a shared database and storage.
- **Model limits:** a 4B local LLM sometimes invents proper nouns from mis-transcribed audio. Copy is
  always editable, and the model is told not to make claims the transcript doesn't support.
- **Failures:** handlers are idempotent; unexpected errors retry once; user-facing errors (unsupported
  media, too long, nothing found) fail fast with a clear message. Jobs left "running" by a crash are
  re-queued at startup.
- **Cleanup:** an hourly janitor removes stale work folders and abandoned uploads
  (`HYPESIFT_TEMP_FILE_TTL_HOURS`). Deleting a project or clip deletes its files.
- **Video-site links** (`app/pipeline/sites.py`): yt-dlp reads the page (no download) to show what will be
  imported, refusing playlists, channels, live streams and over-long videos up front. YouTube list pages
  are refused before any network call. The download picks H.264 + AAC up to 1080p
  (`HYPESIFT_YTDLP_MAX_HEIGHT`), merges with FFmpeg into `source.mp4`, reports byte progress across both
  streams, stops on cancel and cleans up partial files. yt-dlp error text is mapped to plain answers
  (private, age-restricted, bot check, region, members-only, removed, rate-limited). Cookies are only
  read from your browser if you set `HYPESIFT_YTDLP_COOKIES_BROWSER`; there is no DRM circumvention.
  Downloading can conflict with a platform's terms, so import only videos you own or may use.
  `HYPESIFT_YTDLP_ENABLED=false` falls back to oEmbed metadata only.
