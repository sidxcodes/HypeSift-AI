import type { Asset, Clip, ClipDetail, GenerateSettings, Job, Meta, PostPlan, Project, StorageUsage, UrlInfo, User } from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...init,
    credentials: "same-origin",
    headers: init.body instanceof Blob ? init.headers : { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      if (typeof data.detail === "string") msg = data.detail;
      else if (Array.isArray(data.detail)) msg = data.detail.map((d: { msg: string }) => d.msg.replace(/^Value error, /, "")).join(" ");
    } catch {}
    throw new ApiError(res.status, msg);
  }
  return res.json() as Promise<T>;
}

const json = (body: unknown) => JSON.stringify(body);

export const api = {
  me: () => req<User>("/api/auth/me"),
  login: (email: string, password: string) => req<User>("/api/auth/login", { method: "POST", body: json({ email, password }) }),
  signup: (email: string, password: string, name: string) =>
    req<User>("/api/auth/signup", { method: "POST", body: json({ email, password, name }) }),
  logout: () => req("/api/auth/logout", { method: "POST" }),
  saveBrandKit: (body: Record<string, unknown>) => req<User>("/api/auth/brand-kit", { method: "PUT", body: json(body) }),

  meta: () => req<Meta>("/api/meta"),
  checkUrl: (url: string) => req<UrlInfo>("/api/url/check", { method: "POST", body: json({ url }) }),

  projects: () => req<Project[]>("/api/projects"),
  project: (id: string) => req<Project>(`/api/projects/${id}`),
  createProject: (body: { name?: string; upload_id?: string; url?: string; settings: GenerateSettings }) =>
    req<Project>("/api/projects", { method: "POST", body: json({ ...body, start: true }) }),
  regenerate: (id: string, settings: GenerateSettings) =>
    req<Project>(`/api/projects/${id}/generate`, { method: "POST", body: json(settings) }),
  renameProject: (id: string, name: string) => req<Project>(`/api/projects/${id}`, { method: "PATCH", body: json({ name }) }),
  deleteProject: (id: string) => req(`/api/projects/${id}`, { method: "DELETE" }),
  transcript: (id: string) =>
    req<{ language: string; engine: string; segments: { s: number; e: number; t: string }[] }>(`/api/projects/${id}/transcript`),

  clips: (q: { favorite?: boolean; rendered?: boolean } = {}) =>
    req<Clip[]>(`/api/clips?favorite=${!!q.favorite}&rendered=${!!q.rendered}`),
  clip: (id: string) => req<ClipDetail>(`/api/clips/${id}`),
  updateClip: (id: string, body: Record<string, unknown>) =>
    req<{ clip: Clip; job: Job | null }>(`/api/clips/${id}`, { method: "PATCH", body: json(body) }),
  publish: (id: string, platforms: string[], tone: string) =>
    req<{ job: Job }>(`/api/clips/${id}/publish`, { method: "POST", body: json({ platforms, tone }) }),
  savePublish: (id: string, publish: unknown) => req<Clip>(`/api/clips/${id}/publish`, { method: "PUT", body: json({ publish }) }),
  feedback: (id: string, rating: -1 | 0 | 1) => req<Clip>(`/api/clips/${id}/feedback`, { method: "POST", body: json({ rating }) }),
  favorite: (id: string, favorite: boolean) => req<Clip>(`/api/clips/${id}/favorite`, { method: "POST", body: json({ favorite }) }),
  deleteClip: (id: string) => req(`/api/clips/${id}`, { method: "DELETE" }),

  jobs: (q: { project_id?: string; active?: boolean } = {}) =>
    req<Job[]>(`/api/jobs?${q.project_id ? `project_id=${q.project_id}&` : ""}active=${!!q.active}`),
  job: (id: string) => req<Job>(`/api/jobs/${id}`),
  cancelJob: (id: string) => req<Job>(`/api/jobs/${id}/cancel`, { method: "POST" }),

  uploadAsset: (kind: "logo" | "music", file: File) =>
    req<Asset>(`/api/assets?kind=${kind}&name=${encodeURIComponent(file.name)}`, {
      method: "POST",
      body: file,
      headers: { "Content-Type": "application/octet-stream" },
    }),
  setPost: (id: string, plan: { status: NonNullable<PostPlan["status"]>; scheduled_at?: string | null; timezone?: string; platforms?: PostPlan["platforms"] }) =>
    req<Clip>(`/api/clips/${id}/post`, { method: "PUT", body: json(plan) }),
  posts: () => req<Clip[]>("/api/posts"),
  fixClip: (id: string, text: string) =>
    req<{ applied: boolean; reply: string; changes: string[]; engine: string; clip: Clip; job: Job | null }>(`/api/clips/${id}/fix`, {
      method: "POST",
      body: json({ text }),
    }),
  regenThumbnails: (id: string, text?: string) =>
    req<{ job: Job }>(`/api/clips/${id}/thumbnails`, { method: "POST", body: json({ text: text || null }) }),
  storage: () => req<StorageUsage>("/api/storage"),

  assistant: (project_id: string, text: string, clip_id?: string) =>
    req<{ action: Record<string, unknown>; executed: boolean; message: string; jobs: Job[] }>("/api/assistant", {
      method: "POST",
      body: json({ project_id, text, clip_id }),
    }),
};

/** Resumable chunked upload with real byte progress. */
export async function uploadFile(
  file: File,
  onProgress: (sent: number, total: number) => void,
  signal?: AbortSignal,
): Promise<{ id: string; probe: { duration: number; width: number; height: number } }> {
  const init = await req<{ id: string; chunk_size: number; received: number }>("/api/uploads", {
    method: "POST",
    body: json({ filename: file.name, size: file.size }),
  });
  let offset = init.received;
  const size = init.chunk_size;
  let failures = 0;
  while (offset < file.size) {
    if (signal?.aborted) throw new ApiError(0, "Upload cancelled.");
    const blob = file.slice(offset, Math.min(file.size, offset + size));
    try {
      const r = await req<{ received: number }>(`/api/uploads/${init.id}?offset=${offset}`, {
        method: "PUT",
        body: blob,
        headers: { "Content-Type": "application/octet-stream" },
        signal,
      });
      offset = r.received;
      failures = 0;
      onProgress(offset, file.size);
    } catch (e) {
      if (signal?.aborted) throw new ApiError(0, "Upload cancelled.");
      failures += 1;
      if (failures > 4) throw e;
      await new Promise((r) => setTimeout(r, 800 * failures));
      // resume from what the server actually has
      const st = await req<{ received: number }>(`/api/uploads/${init.id}`);
      offset = st.received;
    }
  }
  return req(`/api/uploads/${init.id}/complete`, { method: "POST" });
}

export const DEFAULT_SETTINGS: GenerateSettings = {
  count: 6,
  min_dur: 20,
  max_dur: 60,
  genre: "auto",
  mood: "any",
  position: "any",
  aspect: "9:16",
  crop_mode: "auto",
  captions: true,
  caption_preset: "bold_creator",
  caption_transition: "fade_up",
  caption_effect: "none",
  keyword_emphasis: true,
  instructions: "",
  zoom_start: false,
  zoom_key_phrases: true,
  progress_bar: false,
  logo_key: null,
  logo_position: "top_right",
  music_key: null,
  music_volume: 0.16,
  transcript_only: false,
  comparison: true,
  language: "auto",
  caption_language: "original",
  quality: "standard",
  silence_removal: false,
  context_padding: true,
  hook_title: true,
  platforms: ["youtube", "instagram", "tiktok"],
  tone: "compelling",
  use_llm: true,
};

export function fmtTime(s: number | null | undefined): string {
  if (s == null || !isFinite(s)) return "–";
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  if (m >= 60) return `${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  return `${m}:${String(sec).padStart(2, "0")}`;
}

export function fmtBytes(b: number): string {
  if (b < 1024 ** 2) return `${(b / 1024).toFixed(0)} KB`;
  if (b < 1024 ** 3) return `${(b / 1024 ** 2).toFixed(1)} MB`;
  return `${(b / 1024 ** 3).toFixed(2)} GB`;
}
