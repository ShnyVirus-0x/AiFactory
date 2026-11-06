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
  limits: Limits & { max_upload_mb: number };
  cuda: { gpu_present: boolean; driver_cuda: string | null; driver_version: string | null; required: string; ctranslate2_cuda_devices: number | null; ok: boolean; reason: string | null };
  models_loaded: LoadedModel[];
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

export interface Limits {
  ai_workers: number;
  gpu_render_workers: number;
  cpu_workers: number;
  vram_reserve_mb: number;
  compute_mode: "auto" | "gpu" | "cpu";
}
export interface LimitsInfo extends Limits {
  effective_device: "cuda" | "cpu" | "unavailable";
  device_reason: string | null;
}
export interface LoadedModel {
  key: string;
  device: string;
  est_vram_mb: number;
  loaded_at: number;
  last_used: number;
}

export interface DownloadState {
  status: "downloading" | "done" | "failed";
  downloaded_mb: number;
  total_mb: number;
  error: string | null;
}
export interface WhisperModel {
  name: string;
  repo: string;
  approx_size_mb: number;
  size_is_estimate: boolean;
  vram_mb: number;
  note: string;
  installed: boolean;
  installed_size_mb: number | null;
  path: string;
  default: boolean;
  enough_disk: boolean;
  download: DownloadState | null;
}
export interface TranscriptionJob {
  id: string;
  video_id: string;
  transcript_id: string | null;
  status: "queued" | "running" | "done" | "failed" | "cancelled";
  progress: number;
  language: string;
  model: string;
  device: string;
  audio_track: number;
  error_message: string | null;
  created_at: string;
}
export interface TranscriptInfo {
  id: string;
  video_id: string;
  language: string;
  model: string;
  duration: number;
  language_probability: number | null;
  source: string;
  segment_count: number;
  created_at: string;
}
export interface Segment {
  id: number;
  start_time: number;
  end_time: number;
  text: string;
  edited: boolean;
  words_estimated: boolean;
  word_count: number;
  words: string[];
}
export interface TranscriptFull extends TranscriptInfo {
  total_matches: number;
  segments: Segment[];
}

export interface Clip {
  id: string;
  project_id: string;
  video_id: string;
  title: string;
  start_time: number;
  end_time: number;
  duration: number;
  transcript: string;
  approved: boolean;
  category: string;
}
export interface CaptionSpec {
  enabled: boolean;
  preset: string;
  words_per_line: number;
  font: string;
  size: number;
  y: number;
}
export interface RenderSpec {
  layout: "fill" | "letterbox" | "split";
  crop_mode: "face" | "center" | "manual";
  manual_x: number;
  background: "blur" | "black";
  split_top_ratio: number;
  cam_rect: { x: number; y: number; w: number; h: number };
  codec: "h264" | "h265";
  crf: number;
  loudnorm: boolean;
  captions: CaptionSpec;
  title_overlay: string | null;
  title_seconds: number;
}
export interface CropAnalysis {
  available: boolean;
  reason: string | null;
  note: string;
  samples?: number;
  frames_with_face?: number;
  max_faces?: number;
  travel?: number;
  static?: boolean;
  track: { t: number; x: number }[];
}
export interface RenderJob {
  id: string;
  clip_id: string;
  status: "queued" | "running" | "done" | "failed" | "cancelled";
  progress: number;
  has_output: boolean;
  download_url: string | null;
  error_message: string | null;
  encoder: string;
  uses_gpu: boolean;
  output_info: { width: number; height: number; fps: number; video_codec: string; has_audio: boolean; duration: number; size: number; crop_note?: string } | null;
}
