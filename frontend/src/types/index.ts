export interface Project {
  id: string;
  name: string;
  description: string;
  status: "active" | "archived";
  created_at: string;
  updated_at: string;
  video_count: number;
  clip_count: number;
}

export interface Video {
  id: string;
  project_id: string;
  filename: string;
  duration: number;
  width: number;
  height: number;
  fps: number;
  file_size: number;
  video_codec: string;
  audio_tracks: number;
  has_thumbnail: boolean;
  created_at: string;
}

export interface UploadItem {
  filename: string;
  ok: boolean;
  video: Video | null;
  error: string | null;
  duplicate_of: string | null;
}
export interface UploadResult {
  items: UploadItem[];
  succeeded: number;
  failed: number;
}

export interface Gpu {
  index: number;
  name: string;
  driver_version: string;
  vram_total_mb: number;
  vram_used_mb: number;
  vram_free_mb: number;
  utilization_percent: number | null;
  temperature_c: number | null;
  power_w: number | null;
}
export interface GpuReport {
  available: boolean;
  reason: string | null;
  gpus: Gpu[];
  cuda_version: string | null;
  driver_version: string | null;
}
export interface Resources {
  gpu: GpuReport;
  cpu: { name: string; percent: number; cores_physical: number | null; cores_logical: number | null; freq_mhz: number | null };
  ram: { total: number; used: number; available: number; percent: number };
  disk: { total: number; used: number; free: number; percent: number } | null;
  os: string;
  timestamp: number;
}

export interface Capability {
  key: string;
  label: string;
  phase: number;
  available: boolean;
}
export interface HealthCheck {
  key: string;
  label: string;
  ok: boolean;
  detail: string;
  required: boolean;
}
export interface Health {
  status: "ok" | "degraded";
  version: string;
  python: string;
  platform: string;
  bind: string;
  checks: HealthCheck[];
  nvenc: { available: boolean; h264: boolean; hevc: boolean; reason: string | null };
  ollama: { running: boolean; url: string; models: string[]; model_ready: boolean; wanted_model: string; reason: string | null };
  storage_dir: string;
  models_dir: string;
  limits: Record<string, number>;
  capabilities: Capability[];
}

export interface Dashboard {
  totals: {
    projects: number;
    videos: number;
    clips: number;
    renders_done: number;
    renders_failed: number;
    jobs_running: number;
    jobs_queued: number;
  };
  recent_projects: { id: string; name: string; status: string; updated_at: string; video_count: number }[];
  activity: { id: number; kind: string; message: string; created_at: string }[];
  queue: { id: string; status: string; progress: number; clip_id: string }[];
}

export interface ApiErrorBody {
  error: { code: string; message: string; details?: unknown };
}
