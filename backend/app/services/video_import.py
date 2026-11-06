"""Impor video dari komputer pengguna: validasi, simpan streaming, probe (ffprobe), dan thumbnail lokal."""
from __future__ import annotations

import json
import logging
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

from ..config import get_settings
from ..utils.files import sanitize_filename, sha256_stream_copy

log = logging.getLogger("asf.import")

ALLOWED_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi"}


class ImportError_(Exception):
    """Kesalahan validasi/impor yang aman ditampilkan ke pengguna."""


@dataclass
class MediaInfo:
    duration: float
    width: int
    height: int
    fps: float
    video_codec: str
    audio_tracks: int


def check_extension(filename: str) -> str:
    ext = Path(sanitize_filename(filename)).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise ImportError_(f"Format {ext or '(tanpa ekstensi)'} tidak didukung. Gunakan: {', '.join(sorted(ALLOWED_EXT))}")
    return ext


def _parse_rate(r: str) -> float:
    try:
        if "/" in r:
            a, b = r.split("/")
            return float(a) / float(b) if float(b) else 0.0
        return float(r)
    except (ValueError, ZeroDivisionError):
        return 0.0


def probe(path: Path) -> MediaInfo:
    s = get_settings()
    cmd = [s.ffprobe_bin, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, shell=False)  # noqa: S603
    except FileNotFoundError as e:
        raise ImportError_("ffprobe tidak ditemukan. Pasang FFmpeg dan pastikan ada di PATH.") from e
    except subprocess.TimeoutExpired as e:
        raise ImportError_("ffprobe melebihi batas waktu") from e
    if proc.returncode != 0:
        raise ImportError_("File bukan video yang valid atau rusak")
    data = json.loads(proc.stdout or "{}")
    streams = data.get("streams", [])
    video = next((x for x in streams if x.get("codec_type") == "video" and x.get("disposition", {}).get("attached_pic") != 1), None)
    if not video:
        raise ImportError_("Tidak ada track video pada file")
    duration = float(data.get("format", {}).get("duration") or video.get("duration") or 0)
    if duration <= 0:
        raise ImportError_("Durasi video tidak terbaca")
    return MediaInfo(
        duration=round(duration, 3),
        width=int(video.get("width") or 0),
        height=int(video.get("height") or 0),
        fps=round(_parse_rate(video.get("avg_frame_rate") or video.get("r_frame_rate") or "0"), 3),
        video_codec=str(video.get("codec_name") or ""),
        audio_tracks=sum(1 for x in streams if x.get("codec_type") == "audio"),
    )


def make_thumbnail(src: Path, dest: Path, at: float, width: int = 480) -> bool:
    s = get_settings()
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [s.ffmpeg_bin, "-hide_banner", "-v", "error", "-y", "-nostdin", "-ss", f"{max(0.0, at):.2f}", "-i", str(src),
           "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "4", str(dest)]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=60, shell=False)  # noqa: S603
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0 and dest.is_file() and dest.stat().st_size > 0


@dataclass
class Imported:
    path: Path
    size: int
    sha256: str
    info: MediaInfo
    thumbnail: Path | None
    display_name: str


def import_stream(fileobj, original_name: str) -> Imported:
    """Simpan upload ke storage/uploads dengan nama acak (aman), validasi isi dengan ffprobe, buat thumbnail."""
    s = get_settings()
    ext = check_extension(original_name)
    display = sanitize_filename(original_name)
    vid = uuid.uuid4().hex
    dest = s.uploads_dir / f"{vid}{ext}"
    try:
        size, digest = sha256_stream_copy(fileobj, dest, s.max_upload_mb * 1024 * 1024)
    except ValueError as e:
        raise ImportError_(str(e)) from e
    try:
        info = probe(dest)
    except ImportError_:
        dest.unlink(missing_ok=True)
        raise
    thumb = s.thumbnails_dir / f"{vid}.jpg"
    ok = make_thumbnail(dest, thumb, at=min(info.duration * 0.1, 10.0))
    return Imported(path=dest, size=size, sha256=digest, info=info, thumbnail=thumb if ok else None, display_name=display)
