"""Pengelola model AI: satu model besar di VRAM pada satu waktu, pelepasan eksplisit, mode CPU.

Aturan (VRAM 12 GB): sebelum memuat model ke GPU, bandingkan perkiraan kebutuhan VRAM dengan VRAM bebas dikurangi
cadangan. Bila tidak cukup, model lain yang sedang ada di GPU dilepas dulu; bila masih tidak cukup, GPU ditolak
(atau jatuh ke CPU pada mode `auto`).
"""
from __future__ import annotations

import gc
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from . import gpu_monitor

log = logging.getLogger("asf.models")


@dataclass
class LoadedModel:
    key: str
    device: str  # cuda | cpu
    est_vram_mb: int
    obj: Any
    loaded_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    unloader: Callable[[Any], None] | None = None


def cuda_available() -> bool:
    """CUDA untuk CTranslate2/faster-whisper benar-benar dapat dipakai (bukan sekadar ada nvidia-smi)."""
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:  # noqa: BLE001
        return False


def resolve_device(compute_mode: str) -> tuple[str, str | None]:
    """Kembalikan (device, alasan). compute_mode: auto | gpu | cpu."""
    if compute_mode == "cpu":
        return "cpu", "Mode CPU dipilih pengguna"
    if cuda_available():
        return "cuda", None
    reason = "CUDA tidak tersedia untuk CTranslate2 (driver NVIDIA/CUDA 12 + cuDNN 9 belum lengkap, atau tidak ada GPU)"
    if compute_mode == "gpu":
        return "unavailable", reason
    return "cpu", reason


class ModelManager:
    def __init__(self) -> None:
        self._models: dict[str, LoadedModel] = {}
        self._lock = threading.RLock()

    # ---- util ----------------------------------------------------------------
    @staticmethod
    def _free_vram_mb() -> int | None:
        g = gpu_monitor.query_gpus()
        if not g["available"] or not g["gpus"]:
            return None
        return int(g["gpus"][0]["vram_free_mb"])

    def status(self) -> list[dict[str, Any]]:
        with self._lock:
            return [{"key": m.key, "device": m.device, "est_vram_mb": m.est_vram_mb if m.device == "cuda" else 0,
                     "loaded_at": m.loaded_at, "last_used": m.last_used} for m in self._models.values()]

    def is_loaded(self, key: str) -> bool:
        with self._lock:
            return key in self._models

    # ---- operasi ------------------------------------------------------------
    def acquire(self, key: str, *, device: str, est_vram_mb: int, vram_reserve_mb: int,
                factory: Callable[[], Any], unloader: Callable[[Any], None] | None = None) -> LoadedModel:
        """Kembalikan model yang sudah dimuat (device sama) atau muat baru dengan aturan VRAM."""
        with self._lock:
            cur = self._models.get(key)
            if cur and cur.device == device:
                cur.last_used = time.time()
                return cur
            if cur:  # device berbeda -> muat ulang
                self._unload_locked(key)
            if device == "cuda":
                free = self._free_vram_mb()
                need = est_vram_mb + vram_reserve_mb
                if free is not None and free < need:
                    for k in [k for k, m in self._models.items() if m.device == "cuda"]:
                        log.info("Melepas model %s dari VRAM untuk memberi ruang %s", k, key)
                        self._unload_locked(k)
                    free = self._free_vram_mb()
                    if free is not None and free < need:
                        raise MemoryError(f"VRAM bebas {free} MB < kebutuhan {need} MB (model {est_vram_mb} MB + cadangan {vram_reserve_mb} MB)")
            obj = factory()
            lm = LoadedModel(key=key, device=device, est_vram_mb=est_vram_mb, obj=obj, unloader=unloader)
            self._models[key] = lm
            log.info("Model %s dimuat di %s", key, device)
            return lm

    def _unload_locked(self, key: str) -> bool:
        m = self._models.pop(key, None)
        if not m:
            return False
        try:
            if m.unloader:
                m.unloader(m.obj)
        finally:
            del m
            gc.collect()
        log.info("Model %s dilepas dari memori", key)
        return True

    def unload(self, key: str) -> bool:
        with self._lock:
            return self._unload_locked(key)

    def unload_all(self) -> int:
        with self._lock:
            keys = list(self._models)
            for k in keys:
                self._unload_locked(k)
            return len(keys)


manager = ModelManager()
