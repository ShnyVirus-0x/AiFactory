"""Katalog model Whisper (faster-whisper/CTranslate2), status terpasang, dan unduhan dengan persetujuan + progres.

Model TIDAK pernah diunduh diam-diam: unduhan hanya berjalan lewat permintaan eksplisit dengan `confirm=true`,
setelah ukuran dan ruang disk diperiksa. Unduhan memakai folder sementara lalu dipindah atomik, sehingga model
setengah-jadi tidak pernah dianggap terpasang dan model yang sudah ada tidak pernah ditimpa.
"""
from __future__ import annotations

import logging
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..utils.events import hub

log = logging.getLogger("asf.whisper_models")


@dataclass(frozen=True)
class WhisperSpec:
    name: str
    repo: str
    approx_mb: int  # perkiraan ukuran unduhan
    vram_mb: int  # perkiraan VRAM (fp16)
    note: str


CATALOG: dict[str, WhisperSpec] = {s.name: s for s in [
    WhisperSpec("tiny", "Systran/faster-whisper-tiny", 75, 400, "Sangat cepat, akurasi rendah (uji/CPU lemah)"),
    WhisperSpec("base", "Systran/faster-whisper-base", 145, 500, "Cepat, akurasi dasar"),
    WhisperSpec("small", "Systran/faster-whisper-small", 484, 1000, "Seimbang untuk CPU"),
    WhisperSpec("medium", "Systran/faster-whisper-medium", 1530, 2600, "Akurat, lebih lambat"),
    WhisperSpec("large-v3-turbo", "mobiuslabsgmbh/faster-whisper-large-v3-turbo", 1620, 3200, "Bawaan: akurasi tinggi, cepat di GPU"),
]}
REQUIRED_FILES = ("config.json", "model.bin")
DOWNLOAD_PATTERNS = ["config.json", "preprocessor_config.json", "model.bin", "tokenizer.json", "vocabulary.*"]


def model_dir(name: str) -> Path:
    return get_settings().whisper_dir / name


def is_installed(name: str) -> bool:
    d = model_dir(name)
    return all((d / f).is_file() for f in REQUIRED_FILES)


def installed_size_mb(name: str) -> float | None:
    d = model_dir(name)
    if not is_installed(name):
        return None
    return round(sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) / 1_048_576, 1)


def list_models() -> list[dict[str, Any]]:
    free = shutil.disk_usage(get_settings().models_dir).free
    out = []
    for spec in CATALOG.values():
        out.append({"name": spec.name, "repo": spec.repo, "approx_size_mb": spec.approx_mb, "size_is_estimate": True,
                    "vram_mb": spec.vram_mb, "note": spec.note, "installed": is_installed(spec.name),
                    "installed_size_mb": installed_size_mb(spec.name), "path": str(model_dir(spec.name)),
                    "default": spec.name == get_settings().whisper_model,
                    "enough_disk": free > spec.approx_mb * 1_048_576 * 1.2, "download": downloads.state(spec.name)})
    return out


def _dir_bytes(d: Path) -> int:
    total = 0
    if d.exists():
        for f in d.rglob("*"):
            try:
                if f.is_file():
                    total += f.stat().st_size
            except OSError:
                pass
    return total


class DownloadManager:
    def __init__(self) -> None:
        self._state: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def state(self, name: str) -> dict[str, Any] | None:
        with self._lock:
            s = self._state.get(name)
            return dict(s) if s else None

    def start(self, name: str, downloader=None) -> dict[str, Any]:
        spec = CATALOG[name]
        if is_installed(name):
            raise FileExistsError("Model sudah terpasang")
        free = shutil.disk_usage(get_settings().models_dir).free
        need = int(spec.approx_mb * 1_048_576 * 1.2)
        if free < need:
            raise OSError(f"Ruang disk tidak cukup: tersedia {free // 1_048_576} MB, dibutuhkan ±{need // 1_048_576} MB")
        with self._lock:
            cur = self._state.get(name)
            if cur and cur["status"] == "downloading":
                raise RuntimeError("Unduhan model ini sedang berjalan")
            self._state[name] = {"status": "downloading", "downloaded_mb": 0.0, "total_mb": float(spec.approx_mb), "error": None, "started": time.time()}
        threading.Thread(target=self._run, args=(name, downloader), daemon=True, name=f"dl-{name}").start()
        return self.state(name) or {}

    def _set(self, name: str, **kw: Any) -> None:
        with self._lock:
            self._state[name].update(kw)
            snap = {"model": name, **self._state[name]}
        hub.publish("model.download", snap)

    def _run(self, name: str, downloader) -> None:
        spec = CATALOG[name]
        final = model_dir(name)
        partial = final.with_name(final.name + ".partial")
        stop = threading.Event()

        def poll() -> None:
            while not stop.wait(0.5):
                self._set(name, downloaded_mb=round(_dir_bytes(partial) / 1_048_576, 1))

        t = threading.Thread(target=poll, daemon=True)
        t.start()
        try:
            partial.mkdir(parents=True, exist_ok=True)
            if downloader is None:
                from huggingface_hub import snapshot_download

                def downloader(repo: str, dest: Path) -> None:  # noqa: F811
                    snapshot_download(repo_id=repo, local_dir=str(dest), allow_patterns=DOWNLOAD_PATTERNS)

            downloader(spec.repo, partial)
            if not all((partial / f).is_file() for f in REQUIRED_FILES):
                raise RuntimeError("Unduhan tidak lengkap (config.json/model.bin tidak ada)")
            if final.exists():
                raise FileExistsError("Folder model sudah ada; tidak ditimpa")
            partial.rename(final)
            stop.set()
            self._set(name, status="done", downloaded_mb=round(_dir_bytes(final) / 1_048_576, 1), total_mb=round(_dir_bytes(final) / 1_048_576, 1))
            log.info("Model Whisper %s terpasang", name)
        except Exception as e:  # noqa: BLE001
            stop.set()
            shutil.rmtree(partial, ignore_errors=True)
            log.warning("Unduhan model %s gagal: %s", name, type(e).__name__)
            self._set(name, status="failed", error=f"{type(e).__name__}: {str(e)[:300]}")
        finally:
            stop.set()


downloads = DownloadManager()
