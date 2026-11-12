# HypeSift AI — build status (2026-11-12)

## Done (backend pipeline modules, untested)
- config, db (SQLite, Postgres-ready), migrations, models (User, AuthSession, Upload, Project, Clip, Job), storage (local + signed links)
- pipeline: ffmpeg wrapper (probe, audio, frames, NVENC/libx264, progress), ingest (direct URLs + YouTube/Vimeo/TikTok oEmbed metadata only, SSRF guard),
  transcribe (faster-whisper, CUDA→CPU fallback), signals (loudness/flux/flatness, motion, scene cuts), genres, highlights (candidates + 7-dimension explainable score + NMS),
  llm (Ollama gemma3:4b semantic re-rank), captions (6 presets, ASS/SRT), reframe (face/motion camera path, dual-speaker split), render, publish (LLM + template fallback), assistant (NL → actions)
- Fonts (OFL) in backend/assets/fonts; venv at backend/.venv (Python 3.14, deps installed); ffmpeg 9 (winget), Ollama + gemma3:4b installed

## Left
1. FastAPI app: auth, chunked uploads, projects, clips, jobs, media/download endpoints, /api/meta
2. Worker (DB-backed job queue): "AI Generate" job = ingest → transcribe → signals → rank → reframe → render all clips → publish packages
3. Next.js frontend: landing, auth, dashboard, new project (URL/upload + AI Generate button), results workspace, editor, exports, settings
4. Tests (pytest + build/lint), end-to-end run on a real video, docs (README, ARCHITECTURE, RESEARCH, .env.example, docker-compose)
5. Push to GitHub (new repo) and add to portfolio (E:\MY PROJECTS\PERSONAL Project\portfolio — has other uncommitted edits)
