import type { ApiErrorBody, Clip, ClipSuggestions, CropAnalysis, RenderJob, RenderSpec, Dashboard, GpuReport, Health, LimitsInfo, Limits, LoadedModel, Project, Resources, Segment, TranscriptFull, TranscriptInfo, TranscriptionJob, UploadResult, Video, WhisperModel } from "../types";

export class ApiError extends Error {
  code: string;
  status: number;
  constructor(message: string, code: string, status: number) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

async function toError(res: Response): Promise<ApiError> {
  try {
    const body = (await res.json()) as ApiErrorBody;
    return new ApiError(body.error?.message ?? `HTTP ${res.status}`, body.error?.code ?? "http_error", res.status);
  } catch {
    return new ApiError(`HTTP ${res.status}`, "http_error", res.status);
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, init);
  } catch {
    throw new ApiError("Tidak dapat terhubung ke backend. Pastikan aplikasi berjalan.", "network", 0);
  }
  if (!res.ok) throw await toError(res);
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: body === undefined ? undefined : JSON.stringify(body),
});

export interface VideoQuery {
  project_id?: string;
  q?: string;
  sort?: string;
  min_duration?: number;
  min_height?: number;
  has_audio?: boolean;
}

export const api = {
  dashboard: () => req<Dashboard>("/dashboard"),
  health: () => req<Health>("/system/health"),
  gpu: (refreshNvenc = false) => req<GpuReport & { nvenc: Health["nvenc"] }>(`/system/gpu?refresh_nvenc=${refreshNvenc}`),
  resources: () => req<Resources>("/system/resources"),

  projects: (params: { status?: string; q?: string } = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][]).toString();
    return req<Project[]>(`/projects${qs ? `?${qs}` : ""}`);
  },
  createProject: (name: string, description = "") => req<Project>("/projects", json("POST", { name, description })),
  updateProject: (id: string, body: Partial<Pick<Project, "name" | "description" | "status">>) => req<Project>(`/projects/${id}`, json("PATCH", body)),
  deleteProject: (id: string) => req<void>(`/projects/${id}`, { method: "DELETE" }),

  videos: (q: VideoQuery = {}) => {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(q)) if (v !== undefined && v !== "" && v !== null) qs.set(k, String(v));
    return req<Video[]>(`/videos${qs.toString() ? `?${qs}` : ""}`);
  },
  renameVideo: (id: string, filename: string) => req<Video>(`/videos/${id}`, json("PATCH", { filename })),
  deleteVideo: (id: string) => req<void>(`/videos/${id}`, { method: "DELETE" }),
  limits: () => req<LimitsInfo>("/system/limits"),
  setLimits: (b: Partial<Limits>) => req<LimitsInfo>("/system/limits", json("PUT", b)),
  loadedModels: () => req<LoadedModel[]>("/system/models"),
  unloadModel: (key: string) => req<{ unloaded: string }>(`/system/models/${encodeURIComponent(key)}/unload`, { method: "POST" }),
  unloadAll: () => req<{ unloaded: number }>("/system/models/unload-all", { method: "POST" }),

  whisperModels: () => req<WhisperModel[]>("/transcription/models"),
  downloadWhisper: (name: string) => req<unknown>(`/transcription/models/${name}/download`, json("POST", { confirm: true })),
  transcribe: (videoId: string, b: { language: string; model: string; audio_track: number }) => req<TranscriptionJob>(`/videos/${videoId}/transcribe`, json("POST", b)),
  asrJobs: (videoId?: string) => req<TranscriptionJob[]>(`/transcription/jobs${videoId ? `?video_id=${videoId}` : ""}`),
  cancelAsr: (id: string) => req<TranscriptionJob>(`/transcription/jobs/${id}/cancel`, { method: "POST" }),
  transcripts: (videoId: string) => req<TranscriptInfo[]>(`/videos/${videoId}/transcripts`),
  transcript: (id: string, q = "") => req<TranscriptFull>(`/transcripts/${id}${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  deleteTranscript: (id: string) => req<void>(`/transcripts/${id}`, { method: "DELETE" }),
  patchSegment: (id: number, b: { text?: string; start_time?: number; end_time?: number }) => req<Segment>(`/transcripts/segments/${id}`, json("PATCH", b)),
  splitSegment: (id: number, wordIndex: number) => req<Segment[]>(`/transcripts/segments/${id}/split`, json("POST", { word_index: wordIndex })),
  mergeNext: (id: number) => req<Segment>(`/transcripts/segments/${id}/merge-next`, { method: "POST" }),
  deleteSegment: (id: number) => req<void>(`/transcripts/segments/${id}`, { method: "DELETE" }),
  replaceAll: (id: string, b: { find: string; replace: string; case_sensitive: boolean; whole_word: boolean }) => req<{ replaced: number }>(`/transcripts/${id}/replace`, json("POST", b)),
  exportUrl: (id: string, fmt: "srt" | "vtt" | "txt") => `/api/transcripts/${id}/export?format=${fmt}`,
  clips: (videoId: string) => req<Clip[]>(`/clips?video_id=${videoId}`),
  projectClips: (projectId: string) => req<Clip[]>(`/clips?project_id=${projectId}`),
  createClip: (videoId: string, b: { start_time: number; end_time: number; title: string; hook?: string; score?: number; category?: string }) => req<Clip>(`/videos/${videoId}/clips`, json("POST", b)),
  suggestClips: (videoId: string, max_candidates = 12) => req<ClipSuggestions>(`/videos/${videoId}/suggest-clips`, json("POST", { max_candidates })),
  patchClip: (id: string, b: Partial<Pick<Clip, "title" | "start_time" | "end_time" | "approved">>) => req<Clip>(`/clips/${id}`, json("PATCH", b)),
  deleteClip: (id: string) => req<void>(`/clips/${id}`, { method: "DELETE" }),
  getEdit: (id: string) => req<RenderSpec>(`/clips/${id}/edit`),
  putEdit: (id: string, spec: RenderSpec) => req<RenderSpec>(`/clips/${id}/edit`, json("PUT", spec)),
  analyzeCrop: (id: string) => req<CropAnalysis>(`/clips/${id}/analyze-crop`, { method: "POST" }),
  previewUrl: (id: string, t: number, nonce: number) => `/api/clips/${id}/preview?t=${t.toFixed(2)}&width=360&n=${nonce}`,
  renderClip: (id: string) => req<{ id: string; status: string }>(`/clips/${id}/render`, { method: "POST" }),
  renderProject: (projectId: string, clip_ids: string[]) => req<{ jobs: RenderJob[]; skipped: { clip_id: string; reason: string }[] }>(`/projects/${projectId}/render`, json("POST", { clip_ids })),
  jobs: () => req<RenderJob[]>("/jobs"),
  renderJob: (id: string) => req<RenderJob>(`/jobs/${id}`),
  cancelRender: (id: string) => req<RenderJob>(`/jobs/${id}/cancel`, { method: "POST" }),
  retryRender: (id: string) => req<RenderJob>(`/jobs/${id}/retry`, { method: "POST" }),
  exports: () => req<RenderJob[]>("/exports"),
  thumbUrl: (id: string) => `/api/videos/${id}/thumbnail`,
  streamUrl: (id: string) => `/api/videos/${id}/stream`,
};

/** Unggah banyak file dengan progres nyata dari XHR. */
export function uploadVideos(projectId: string, files: File[], onProgress: (pct: number) => void): Promise<UploadResult> {
  return new Promise((resolve, reject) => {
    const fd = new FormData();
    fd.append("project_id", projectId);
    for (const f of files) fd.append("files", f);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/videos/upload");
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress((e.loaded / e.total) * 100);
    xhr.onerror = () => reject(new ApiError("Tidak dapat terhubung ke backend", "network", 0));
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        /* bukan JSON */
      }
      if (xhr.status >= 200 && xhr.status < 300) return resolve(body as UploadResult);
      const e = (body as ApiErrorBody | null)?.error;
      reject(new ApiError(e?.message ?? `HTTP ${xhr.status}`, e?.code ?? "http_error", xhr.status));
    };
    xhr.send(fd);
  });
}

export const errMsg = (e: unknown): string => (e instanceof Error ? e.message : String(e));
