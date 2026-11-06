from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Nama proyek wajib diisi")
        return v


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    status: str | None = Field(default=None, pattern="^(active|archived)$")


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    status: str
    created_at: datetime
    updated_at: datetime
    video_count: int = 0
    clip_count: int = 0


class VideoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    filename: str
    duration: float
    width: int
    height: int
    fps: float
    file_size: int
    video_codec: str
    audio_tracks: int
    has_thumbnail: bool = False
    created_at: datetime


class VideoUpdate(BaseModel):
    filename: str = Field(min_length=1, max_length=200)


class UploadItem(BaseModel):
    filename: str
    ok: bool
    video: VideoOut | None = None
    error: str | None = None
    duplicate_of: str | None = None


class UploadResult(BaseModel):
    items: list[UploadItem]
    succeeded: int
    failed: int
