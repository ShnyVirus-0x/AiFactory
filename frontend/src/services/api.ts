import type { ApiErrorBody, Dashboard, GpuReport, Health, Project, Resources, UploadResult, Video } from "../types";

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
