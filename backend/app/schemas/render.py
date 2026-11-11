"""Konfigurasi edit/render satu klip (disimpan di ClipEdit.edit_config_json)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class CamRect(BaseModel):
    """Area kamera/pembicara pada frame sumber (pecahan 0..1) untuk layout split."""

    x: float = Field(default=0.0, ge=0, le=1)
    y: float = Field(default=0.0, ge=0, le=1)
    w: float = Field(default=1.0, gt=0, le=1)
    h: float = Field(default=0.5, gt=0, le=1)


class CaptionSpec(BaseModel):
    enabled: bool = True
    preset: str = "pop_yellow"
    words_per_line: int = Field(default=3, ge=1, le=8)
    font: str = Field(default="Arial", max_length=60)
    size: int = Field(default=84, ge=24, le=200)
    y: float = Field(default=0.78, ge=0.1, le=0.95)  # posisi vertikal (pecahan tinggi frame)

    @field_validator("font")
    @classmethod
    def _font(cls, v: str) -> str:
        if any(c in v for c in ",\\{}\n\r:"):
            raise ValueError("Nama font mengandung karakter tidak diizinkan")
        return v


class RenderSpec(BaseModel):
    layout: Literal["fill", "letterbox", "split"] = "fill"
    crop_mode: Literal["face", "center", "manual"] = "face"
    manual_x: float = Field(default=0.5, ge=0, le=1)  # pusat crop (0..1) bila crop_mode=manual
    background: Literal["blur", "black"] = "blur"  # untuk letterbox
    split_top_ratio: float = Field(default=0.5, ge=0.2, le=0.8)
    cam_rect: CamRect = CamRect()
    codec: Literal["h264", "h265"] = "h264"
    crf: int = Field(default=18, ge=14, le=32)
    loudnorm: bool = False
    captions: CaptionSpec = CaptionSpec()
    title_overlay: str | None = Field(default=None, max_length=120)
    title_seconds: float = Field(default=3.0, ge=0, le=30)
