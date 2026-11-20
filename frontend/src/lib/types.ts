export type User = { id: string; email: string; name: string; brand_kit: BrandKit };
export type BrandKit = {
  caption_preset?: string | null;
  caption_style?: Partial<CaptionStyle>;
  watermark?: string;
  socials?: Record<string, string>;
  timezone?: string | null;
};

export type JobStage = { key: string; status: "pending" | "running" | "done" | "failed"; started_at?: string };
export type Job = {
  id: string;
  kind: "generate" | "render" | "publish" | "discover";
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  stage: string;
  progress: number;
  message: string;
  error: string | null;
  stages: JobStage[];
  project_id: string | null;
  clip_id: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  payload?: { summary?: string };
};

export type GenerateSettings = {
  count: number;
  min_dur: number;
  target_dur?: number | null;
  max_dur: number;
  genre: string;
  mood: string;
  position: string;
  aspect: "9:16" | "1:1" | "4:5" | "16:9";
  crop_mode: "auto" | "center" | "fit" | "facecam";
  captions: boolean;
  caption_preset: string;
  caption_transition: Transition;
  caption_effect: Effect;
  keyword_emphasis: boolean;
  instructions: string;
  zoom_start: boolean;
  zoom_key_phrases: boolean;
  progress_bar: boolean;
  logo_key: string | null;
  logo_position: LogoSpot;
  logo_pos?: Pos | null;
  caption_pos?: Pos | null;
  title_style?: TitleStyle;
  title_pos?: Pos | null;
  progress_position?: "top" | "bottom";
  music_key: string | null;
  music_volume: number;
  transcript_only: boolean;
  comparison: boolean;
  compare_play?: ComparePlay;
  compare_audio?: "active" | "a" | "mix";
  language: string;
  caption_language: "original" | "english";
  quality: "draft" | "standard" | "high";
  silence_removal: boolean;
  context_padding: boolean;
  hook_title: boolean;
  platforms: string[];
  tone: string;
  use_llm: boolean;
};

export type Transition = "none" | "fade_up" | "fade_down" | "fade_left" | "fade_right" | "bounce";
export type Effect = "none" | "glow" | "shadow3d" | "typewriter" | "tilt";

export type CaptionStyle = {
  pos?: Pos | null;
  label: string;
  font: string;
  size: number;
  color: string;
  highlight: string;
  outline: number;
  outline_color: string;
  shadow: number;
  box: boolean;
  box_color: string;
  box_opacity: number;
  uppercase: boolean;
  max_words: number;
  position: "top" | "middle" | "lower" | "bottom";
  animation: "none" | "pop" | "highlight" | "fade" | "karaoke";
  emphasis: boolean;
  emphasis_color: string;
  glow?: number;
  glow_color?: string;
  opacity?: number;
  size_scale?: number;
};

export type Chunk = { s: number; e: number; text: string; words: { w: string; s: number; e: number }[] };
export type Overlay = { kind: "title" | "watermark"; text: string; start: number; end?: number; color?: string; bg?: string
  style?: TitleStyle;
  pos?: Pos | null;
};

export type Edits = {
  aspect: "9:16" | "1:1" | "4:5" | "16:9";
  crop: { mode: "auto" | "manual" | "center" | "split" | "fit" | "facecam" | "compare" | "pair" | "multi"; x: number; y: number; zoom: number };
  multi?: { parts: { start: number; end: number; label?: string; crop?: string }[]; play: ComparePlay; audio?: string };
  pair?: { b_start: number };
  compare?: { swap: boolean };
  labels?: { top?: string; bottom?: string; enabled?: boolean };
  captions: {
    enabled: boolean;
    preset: string;
    style: Partial<CaptionStyle>;
    chunks: Chunk[] | null;
    keywords?: string[];
    transition?: Transition;
    effect?: Effect;
  };
  overlays: Overlay[];
  silence_removal: boolean;
  audio?: { gain_db: number; normalize: boolean; fade_in: number; fade_out: number };
  video?: { fade_in: number; fade_out: number };
  quality: "draft" | "standard" | "high";
  zoom?: { start: boolean; key_phrases: boolean };
  logo?: { key: string | null; position?: string; size?: number; opacity?: number };
  music?: { key: string | null; volume?: number };
  progress_bar?: { enabled: boolean; color?: string };
};

export type PostPlan = {
  status?: "draft" | "scheduled" | "posted";
  scheduled_at?: string | null;
  timezone?: string | null;
  posted_at?: string;
  platforms?: Record<string, Record<string, unknown>>;
};

export type Goal = "general" | "views" | "trust" | "educate" | "entertain";
export type Insights = {
  goals: Record<Goal, number>;
  checklist: { key: string; ok: boolean | null; label: string; tip: string }[];
  viral: number;
};

export type Reframe = {
  source?: "faces" | "motion" | "center";
  path?: [number, number, number][];
  face_ratio?: number;
  split?: { left: number; right: number } | null;
  facecam?: { box: [number, number, number, number]; face: [number, number, number]; snapped: boolean } | null;
  range?: [number, number];
};

export type PublishPackage = {
  engine: string;
  tone: string;
  note?: string;
  edited?: boolean;
  platforms: Record<string, Record<string, string | string[]>>;
};

export type Clip = {
  id: string;
  project_id: string;
  rank: number;
  start: number;
  end: number;
  duration: number;
  output_duration: number | null;
  title: string;
  hook: string;
  text: string;
  content_type: string;
  score: number;
  score_breakdown: {
    dims?: Record<string, number>;
    weights?: Record<string, number>;
    heuristic?: number;
    semantic?: number | null;
    evidence?: Record<string, string[]>;
    engine?: string;
    request?: string;
  };
  reasons: string[];
  edits: Edits;
  reframe: Reframe;
  publish: PublishPackage | Record<string, never>;
  render_status: "pending" | "rendering" | "rendered" | "failed";
  render_error: string | null;
  rendered_at: string | null;
  favorite: boolean;
  feedback: -1 | 0 | 1;
  created_at: string;
  video_url: string | null;
  download_url: string | null;
  thumb_url: string | null;
  srt_url: string | null;
  project_name: string | null;
  post: PostPlan;
  insights: Insights;
  original_start: number | null;
};

export type Project = {
  id: string;
  name: string;
  source_type: "upload" | "url";
  source_url: string | null;
  status: "draft" | "queued" | "processing" | "ready" | "failed";
  error: string | null;
  settings: GenerateSettings;
  created_at: string;
  updated_at: string;
  duration: number | null;
  width: number | null;
  height: number | null;
  has_audio: boolean | null;
  thumb_url: string | null;
  source_video_url: string | null;
  analysis: Record<string, unknown>;
  clip_count: number;
  job: Job | null;
  clips?: Clip[];
  signals?: { loudness_2hz: number[]; motion_2hz: number[]; cuts: number[]; duration: number } | null;
};

export type Meta = {
  caption_presets: Record<string, CaptionStyle>;
  caption_transitions: Record<Transition, string>;
  caption_effects: Record<Effect, string>;
  fonts: Record<string, string>;
  dimensions: Record<string, string>;
  genres: Record<string, string>;
  moods: string[];
  platforms: string[];
  tones: string[];
  aspects: string[];
  llm: { available: boolean; model: string; reason: string };
  ai_provider?: "gemini" | "local";
  encoder: string;
  whisper_model: string;
  limits: { max_upload_mb: number; max_duration_minutes: number; max_clips: number };
};

export type UrlInfo = {
  url: string;
  kind: "direct" | "platform" | "page";
  platform: string | null;
  importable: boolean;
  title: string | null;
  author: string | null;
  thumbnail: string | null;
  duration: number | null;
  size_bytes: number | null;
  content_type: string | null;
  message: string;
  warnings: string[];
  scan?: boolean;
};

export type ClipDetail = {
  clip: Clip;
  project: Project;
  words: [string, number, number][];
  chunks: Chunk[];
  envelope: { start: number; hop: number; loudness: number[] } | null;
  job: Job | null;
};

export type Asset = { key: string; name: string; kind: "logo" | "music"; size: number; url: string | null };

export type StorageUsage = {
  projects: { id: string; name: string; clips: number; source_bytes: number; clip_bytes: number; total: number; thumb_url: string | null }[];
  assets_bytes: number;
  total: number;
  disk_free: number;
  disk_total: number;
};

export type Pos = { x: number; y: number };
export type TitleStyle = "impact" | "box" | "neon" | "minimal";
export type ComparePlay = "turns" | "together" | "grid_then_single";
export type LogoSpot =
  | "top_left"
  | "top_center"
  | "top_right"
  | "middle_left"
  | "center"
  | "middle_right"
  | "bottom_left"
  | "bottom_center"
  | "bottom_right";

export type AiSettings = {
  provider: "gemini" | "local";
  active: "gemini" | "local";
  has_key: boolean;
  key_hint: string;
  model: string;
  models: string[];
  last_model: string;
  last_error: string;
  local: { available: boolean; model: string; reason: string };
};
