"""Daftar kemampuan aplikasi dan statusnya. Fitur yang belum dibuat DITAMPILKAN sebagai belum tersedia."""
from __future__ import annotations

# key, label, phase, tersedia
MODULES: list[tuple[str, str, int, bool]] = [
    ("dashboard", "Dashboard", 1, True),
    ("projects", "Manajemen Proyek (dasar)", 1, True),
    ("library", "Perpustakaan Video", 1, True),
    ("diagnostics", "Diagnostik GPU / sumber daya", 1, True),
    ("transcription", "Mesin Transkripsi AI", 2, True),
    ("clip_detection", "Saran Klip dari Transkrip (Ollama lokal)", 3, True),
    ("clip_editor", "Editor Klip dasar (trim & timeline)", 4, True),
    ("face_tracking", "Smart Face Tracking / Smart Crop", 4, True),
    ("split_screen", "Studio Split Screen (dasar: kamera atas + layar bawah dari 1 sumber)", 4, True),
    ("subtitle_studio", "Studio Subtitle Dinamis", 5, False),
    ("templates", "Studio Template", 5, False),
    ("batch_renderer", "Batch Renderer (dasar: antrean, batal, retry)", 6, True),
    ("export_center", "Export Center (dasar: pratinjau & unduhan)", 6, True),
    ("diarization", "Speaker Diarization", 7, False),
    ("thumbnails", "Studio Thumbnail", 7, False),
    ("content_ai", "Generator Konten AI", 7, False),
    ("audio_enhance", "Peningkatan Audio", 7, False),
]


def capabilities() -> list[dict]:
    return [{"key": k, "label": label, "phase": ph, "available": ok} for k, label, ph, ok in MODULES]
