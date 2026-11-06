"""Konfigurasi aplikasi. Semua nilai dapat di-override lewat environment (prefix ASF_) atau file .env."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ASF_", env_file=str(ROOT_DIR / ".env"), extra="ignore")

    # --- Jaringan: hanya lokal secara bawaan -----------------------------
    host: str = "127.0.0.1"
    port: int = 8000
    allowed_origins: str = "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:8000,http://localhost:8000"

    # --- Penyimpanan -----------------------------------------------------
    storage_dir: Path = ROOT_DIR / "storage"
    models_dir: Path = ROOT_DIR / "models"
    database_url: str = ""  # kosong = sqlite di storage_dir/asf.db
    frontend_dist: Path = ROOT_DIR / "frontend" / "dist"

    # --- Batas ------------------------------------------------------------
    max_upload_mb: int = Field(default=16384, ge=1)  # 16 GB
    max_files_per_upload: int = Field(default=20, ge=1, le=100)

    # --- Binary -----------------------------------------------------------
    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"

    # --- Layanan lokal opsional -------------------------------------------
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b-instruct"
    whisper_model: str = "large-v3-turbo"

    # --- Batas sumber daya (dipakai pengelola model / worker pada fase berikutnya) ---
    ai_workers: int = Field(default=1, ge=1, le=4)
    gpu_render_workers: int = Field(default=1, ge=1, le=4)
    cpu_workers: int = Field(default=2, ge=1, le=16)
    vram_reserve_mb: int = Field(default=1024, ge=0)

    # --- WebSocket --------------------------------------------------------
    stats_push_seconds: float = Field(default=2.0, ge=0.5, le=60)

    @property
    def logs_dir(self) -> Path:
        return self.storage_dir / "logs"

    @property
    def whisper_dir(self) -> Path:
        return self.models_dir / "whisper"

    @property
    def uploads_dir(self) -> Path:
        return self.storage_dir / "uploads"

    @property
    def outputs_dir(self) -> Path:
        return self.storage_dir / "outputs"

    @property
    def thumbnails_dir(self) -> Path:
        return self.storage_dir / "thumbnails"

    @property
    def transcripts_dir(self) -> Path:
        return self.storage_dir / "transcripts"

    @property
    def cache_dir(self) -> Path:
        return self.storage_dir / "cache"

    @property
    def db_url(self) -> str:
        if self.database_url:
            return self.database_url
        return "sqlite:///" + (self.storage_dir / "asf.db").resolve().as_posix()

    @property
    def origins(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.allowed_origins.split(",") if o.strip()]

    def ensure_dirs(self) -> None:
        for d in (self.storage_dir, self.uploads_dir, self.outputs_dir, self.thumbnails_dir,
                  self.transcripts_dir, self.cache_dir, self.models_dir, self.logs_dir, self.whisper_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s
