"""Diagnostik perangkat keras NYATA: GPU NVIDIA (nvidia-smi), NVENC (uji encode), CPU/RAM/disk (psutil).

Tidak ada nilai palsu: bila GPU/driver tidak ada, hasilnya dinyatakan ``available: False`` beserta alasannya.
"""
from __future__ import annotations

import logging
import os
import platform
import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import psutil

from ..config import get_settings

log = logging.getLogger("asf.gpu")

_SMI_QUERY = "index,name,driver_version,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu,power.draw"
_WIN_SMI = (
    r"C:\Windows\System32\nvidia-smi.exe",
    r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
)


@dataclass
class GpuInfo:
    index: int
    name: str
    driver_version: str
    vram_total_mb: int
    vram_used_mb: int
    vram_free_mb: int
    utilization_percent: float | None
    temperature_c: float | None
    power_w: float | None


def find_nvidia_smi() -> str | None:
    found = shutil.which("nvidia-smi")
    if found:
        return found
    for cand in _WIN_SMI:
        if Path(cand).is_file():
            return cand
    return None


def _num(v: str) -> float | None:
    v = v.strip()
    if not v or v.lower() in ("n/a", "[n/a]", "[not supported]", "not supported"):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def parse_gpu_csv(text: str) -> list[GpuInfo]:
    """Parse keluaran ``nvidia-smi --query-gpu=... --format=csv,noheader,nounits``."""
    gpus: list[GpuInfo] = []
    for line in text.strip().splitlines():
        cols = [c.strip() for c in line.split(",")]
        if len(cols) < 8:
            continue
        idx, total, used, free = _num(cols[0]), _num(cols[3]), _num(cols[4]), _num(cols[5])
        if None in (idx, total, used, free):
            continue
        gpus.append(
            GpuInfo(
                index=int(idx), name=cols[1], driver_version=cols[2],
                vram_total_mb=int(total), vram_used_mb=int(used), vram_free_mb=int(free),
                utilization_percent=_num(cols[6]), temperature_c=_num(cols[7]),
                power_w=_num(cols[8]) if len(cols) > 8 else None,
            )
        )
    return gpus


def parse_cuda_version(smi_text: str) -> str | None:
    m = re.search(r"CUDA Version:\s*([0-9.]+)", smi_text)
    return m.group(1) if m else None


def _run(cmd: list[str], timeout: float = 8.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, shell=False)  # noqa: S603


_cuda_cache: dict[str, tuple[float, str | None]] = {}


def _cuda_version_cached(smi: str, ttl: float = 60.0) -> str | None:
    """Versi CUDA tidak berubah selama proses berjalan; jangan panggil nvidia-smi dua kali tiap polling."""
    now = time.time()
    hit = _cuda_cache.get(smi)
    if hit and now - hit[0] < ttl:
        return hit[1]
    plain = _run([smi])
    ver = parse_cuda_version(plain.stdout) if plain.returncode == 0 else None
    _cuda_cache[smi] = (now, ver)
    return ver


def query_gpus() -> dict[str, Any]:
    smi = find_nvidia_smi()
    if not smi:
        return {"available": False, "reason": "nvidia-smi tidak ditemukan. Driver NVIDIA belum terpasang atau tidak ada GPU NVIDIA.",
                "gpus": [], "cuda_version": None, "driver_version": None}
    try:
        q = _run([smi, f"--query-gpu={_SMI_QUERY}", "--format=csv,noheader,nounits"])
        if q.returncode != 0:
            return {"available": False, "reason": (q.stderr or q.stdout).strip()[:300] or "nvidia-smi gagal", "gpus": [],
                    "cuda_version": None, "driver_version": None}
        gpus = parse_gpu_csv(q.stdout)
        cuda = _cuda_version_cached(smi)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"available": False, "reason": f"nvidia-smi tidak dapat dijalankan: {e}", "gpus": [], "cuda_version": None, "driver_version": None}
    if not gpus:
        return {"available": False, "reason": "nvidia-smi tidak melaporkan GPU", "gpus": [], "cuda_version": cuda, "driver_version": None}
    return {"available": True, "reason": None, "gpus": [asdict(g) for g in gpus], "cuda_version": cuda,
            "driver_version": gpus[0].driver_version}


# --------------------------------------------------------------------------
# FFmpeg / NVENC
# --------------------------------------------------------------------------
_nvenc_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def ffmpeg_info() -> dict[str, Any]:
    s = get_settings()
    out: dict[str, Any] = {"ffmpeg": None, "ffprobe": None}
    for key, binary in (("ffmpeg", s.ffmpeg_bin), ("ffprobe", s.ffprobe_bin)):
        path = shutil.which(binary)
        if not path:
            out[key] = {"found": False, "version": None, "path": None}
            continue
        try:
            r = _run([path, "-version"], 8)
            first = (r.stdout or "").splitlines()[0] if r.stdout else ""
            m = re.search(r"version\s+(\S+)", first)
            out[key] = {"found": True, "version": m.group(1) if m else first[:60], "path": path}
        except (OSError, subprocess.TimeoutExpired):
            out[key] = {"found": False, "version": None, "path": path}
    return out


def nvenc_status(force: bool = False, ttl: float = 120.0) -> dict[str, Any]:
    """NVENC dianggap tersedia hanya bila encoder terdaftar DAN uji encode sungguhan berhasil."""
    s = get_settings()
    key = s.ffmpeg_bin
    now = time.time()
    if not force and key in _nvenc_cache and now - _nvenc_cache[key][0] < ttl:
        return _nvenc_cache[key][1]
    path = shutil.which(s.ffmpeg_bin)
    res: dict[str, Any]
    if not path:
        res = {"available": False, "h264": False, "hevc": False, "reason": "FFmpeg tidak ditemukan"}
    else:
        try:
            enc = _run([path, "-hide_banner", "-encoders"], 15).stdout
            has_h264, has_hevc = "h264_nvenc" in enc, "hevc_nvenc" in enc
            if not has_h264:
                res = {"available": False, "h264": False, "hevc": has_hevc, "reason": "Build FFmpeg ini tidak menyertakan h264_nvenc"}
            else:
                t = _run([path, "-hide_banner", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.2",
                          "-c:v", "h264_nvenc", "-f", "null", "-"], 30)
                if t.returncode == 0:
                    res = {"available": True, "h264": True, "hevc": has_hevc, "reason": None}
                else:
                    res = {"available": False, "h264": False, "hevc": False,
                           "reason": "Uji encode NVENC gagal: " + (t.stderr.strip().splitlines() or ["tidak ada GPU NVIDIA / driver"])[-1][:200]}
        except (OSError, subprocess.TimeoutExpired) as e:
            res = {"available": False, "h264": False, "hevc": False, "reason": f"Uji NVENC gagal: {e}"}
    _nvenc_cache[key] = (now, res)
    return res


# --------------------------------------------------------------------------
# CPU / RAM / disk
# --------------------------------------------------------------------------
def cpu_name() -> str:
    name = platform.processor() or ""
    if platform.system() == "Linux":
        try:
            for line in Path("/proc/cpuinfo").read_text(errors="ignore").splitlines():
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
        except OSError:
            pass
    if platform.system() == "Windows":
        name = os.environ.get("PROCESSOR_IDENTIFIER", name)
    return name or "Tidak diketahui"


def system_resources() -> dict[str, Any]:
    s = get_settings()
    vm = psutil.virtual_memory()
    try:
        du = shutil.disk_usage(s.storage_dir)
        disk = {"total": du.total, "used": du.used, "free": du.free, "percent": round(du.used / du.total * 100, 1)}
    except OSError:
        disk = None
    freq = psutil.cpu_freq()
    return {
        "cpu": {
            "name": cpu_name(),
            "percent": psutil.cpu_percent(interval=None),
            "cores_physical": psutil.cpu_count(logical=False),
            "cores_logical": psutil.cpu_count(logical=True),
            "freq_mhz": round(freq.current) if freq else None,
        },
        "ram": {"total": vm.total, "used": vm.used, "available": vm.available, "percent": vm.percent},
        "disk": disk,
        "os": f"{platform.system()} {platform.release()}",
    }


def resource_snapshot() -> dict[str, Any]:
    """Snapshot ringan untuk dashboard (tanpa uji NVENC)."""
    return {"gpu": query_gpus(), **system_resources(), "timestamp": time.time()}


def cuda_compatibility() -> dict[str, Any]:
    """Periksa kompatibilitas CUDA untuk faster-whisper (CTranslate2 4.x membutuhkan CUDA 12 + cuDNN 9)."""
    g = query_gpus()
    out: dict[str, Any] = {"gpu_present": g["available"], "driver_cuda": g.get("cuda_version"), "driver_version": g.get("driver_version"),
                           "required": "CUDA 12.x + cuDNN 9 (CTranslate2 4.x)", "ctranslate2_cuda_devices": None, "ok": False, "reason": None}
    try:
        import ctranslate2

        out["ctranslate2_cuda_devices"] = ctranslate2.get_cuda_device_count()
    except Exception as e:  # noqa: BLE001
        out["reason"] = f"ctranslate2 belum terpasang ({type(e).__name__})"
    if not g["available"]:
        out["reason"] = out["reason"] or g["reason"]
        return out
    try:
        major = int(str(g.get("cuda_version") or "0").split(".")[0])
    except ValueError:
        major = 0
    if major < 12:
        out["reason"] = f"Driver melaporkan CUDA {g.get('cuda_version') or 'tidak diketahui'}; dibutuhkan 12 atau lebih baru. Perbarui driver NVIDIA."
    elif out["ctranslate2_cuda_devices"] == 0:
        out["reason"] = "Driver mendukung CUDA 12 tetapi CTranslate2 tidak melihat GPU (cuDNN 9 / CUDA runtime belum terpasang?)"
    elif out["ctranslate2_cuda_devices"] is None:
        pass
    else:
        out["ok"] = True
    return out
