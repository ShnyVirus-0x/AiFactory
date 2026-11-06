"""Daftar kemampuan aplikasi dan statusnya. Fitur yang belum dibuat DITAMPILKAN sebagai belum tersedia."""
from __future__ import annotations

# key, label, phase, tersedia
MODULES: list[tuple[str, str, int, bool]] = [
    ("dashboard", "Dashboard", 1, True),
    ("projects", "Manajemen Proyek (dasar)", 1, True),
    ("library", "Perpustakaan Video", 1, True),
    ("diagnostics", "Diagnostik GPU / sumber daya", 1, True),
    ("transcription", "Mesin Transkripsi AI", 2, True),
    ("clip_detection", "Deteksi Klip Viral (Qwen lokal)", 3, False),
    ("clip_editor", "Editor Klip", 4, False),
    ("face_tracking", "Smart Face Tracking / Smart Crop", 4, False),
    ("split_screen", "Studio Split Screen", 4, False),
    ("subtitle_studio", "Studio Subtitle Dinamis", 5, False),
    ("templates", "Studio Template", 5, False),
    ("batch_renderer", "Batch Renderer (NVENC)", 6, False),
    ("export_center", "Export Center", 6, False),
    ("diarization", "Speaker Diarization", 7, False),
    ("thumbnails", "Studio Thumbnail", 7, False),
    ("content_ai", "Generator Konten AI", 7, False),
    ("audio_enhance", "Peningkatan Audio", 7, False),
]


def capabilities() -> list[dict]:
    return [{"key": k, "label": label, "phase": ph, "available": ok} for k, label, ph, ok in MODULES]
