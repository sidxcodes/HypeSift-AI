"""Environment-based configuration. Every value can be overridden with an env var
(prefix ``HYPESIFT_``) or a ``.env`` file in the backend folder."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HYPESIFT_", env_file=str(BACKEND_DIR / ".env"), extra="ignore")

    # --- core -------------------------------------------------------------
    env: str = "development"
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'data' / 'hypesift.db').as_posix()}"
    storage_dir: Path = BACKEND_DIR / "data" / "storage"
    secret_key: str = "change-me-in-production"  # used to sign download links
    cors_origins: str = "http://localhost:3000"
    cookie_secure: bool = False

    # --- worker -----------------------------------------------------------
    embedded_worker: bool = True  # run the job worker inside the API process
    worker_concurrency: int = 1
    worker_poll_seconds: float = 1.0
    job_max_attempts: int = 2

    # --- limits / quotas --------------------------------------------------
    max_upload_mb: int = 4096
    max_duration_minutes: int = 180
    max_clips: int = 20
    max_active_jobs_per_user: int = 3
    upload_chunk_mb: int = 8
    temp_file_ttl_hours: int = 24

    # Some hosts (e.g. Wikimedia) reject clients without a descriptive UA that includes a link.
    http_user_agent: str = "HypeSiftAI/1.0 (self-hosted video tool; +https://github.com/topics/video-editing)"

    # --- tools ------------------------------------------------------------
    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"
    video_encoder: str = "auto"  # auto | libx264 | h264_nvenc
    whisper_model: str = "small"
    whisper_device: str = "auto"  # auto | cpu | cuda
    whisper_compute_type: str = "auto"

    # --- video-site links (YouTube, Vimeo, TikTok …) via the free yt-dlp ---------------
    ytdlp_enabled: bool = True
    ytdlp_max_height: int = 1080
    # Optional: read cookies from your own browser ("edge", "chrome", "firefox") so videos that
    # need your login (age-restricted, "confirm you're not a bot") work. Empty = never.
    ytdlp_cookies_browser: str = ""

    # --- optional local LLM (free, via Ollama) ------------------------------
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "gemma3:4b"
    llm_enabled: bool = True
    llm_timeout_seconds: float = 120.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.storage_dir.mkdir(parents=True, exist_ok=True)
    if s.database_url.startswith("sqlite:///"):
        Path(s.database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    return s
