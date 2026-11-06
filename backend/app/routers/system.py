from __future__ import annotations

import importlib.util
import platform
import sys
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import __version__
from ..config import get_settings
from ..database import get_db
from ..models import ActivityLog, Clip, Project, RenderJob, Video
from ..services import gpu_monitor
from ..services import model_manager as mm
from ..services import runtime_settings as rs
from ..services.capabilities import capabilities
from ..utils.errors import not_found

router = APIRouter(tags=["system"])


def _ollama_status() -> dict[str, Any]:
    s = get_settings()
    try:
        r = httpx.get(f"{s.ollama_url.rstrip('/')}/api/tags", timeout=1.5)
        r.raise_for_status()
        models = [m.get("name", "") for m in r.json().get("models", [])]
        want = s.ollama_model
        return {"running": True, "url": s.ollama_url, "models": models, "model_ready": any(m == want or m.startswith(want.split(":")[0] + ":" + want.split(":")[-1]) for m in models) if ":" in want else want in models,
                "wanted_model": want, "reason": None}
    except Exception as e:  # noqa: BLE001
        return {"running": False, "url": s.ollama_url, "models": [], "model_ready": False, "wanted_model": s.ollama_model,
                "reason": f"Ollama tidak dapat dihubungi ({type(e).__name__}). Pasang/jalankan Ollama untuk fitur AI lokal (Fase 3)."}


def _module_installed(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


@router.get("/system/health")
def health(db: Session = Depends(get_db)) -> dict[str, Any]:
    s = get_settings()
    ff = gpu_monitor.ffmpeg_info()
    nv = gpu_monitor.nvenc_status()
    gpu = gpu_monitor.query_gpus()
    ollama = _ollama_status()
    checks = [
        {"key": "ffmpeg", "label": "FFmpeg", "ok": ff["ffmpeg"]["found"], "detail": ff["ffmpeg"]["version"] or "tidak ditemukan", "required": True},
        {"key": "ffprobe", "label": "FFprobe", "ok": ff["ffprobe"]["found"], "detail": ff["ffprobe"]["version"] or "tidak ditemukan", "required": True},
        {"key": "gpu", "label": "GPU NVIDIA", "ok": gpu["available"],
         "detail": (gpu["gpus"][0]["name"] if gpu["available"] else gpu["reason"]), "required": False},
        {"key": "nvenc", "label": "NVENC (h264)", "ok": nv["available"], "detail": "uji encode berhasil" if nv["available"] else nv["reason"], "required": False},
        {"key": "faster_whisper", "label": "faster-whisper", "ok": _module_installed("faster_whisper"),
         "detail": "terpasang" if _module_installed("faster_whisper") else "belum terpasang (Fase 2)", "required": False},
        {"key": "opencv", "label": "OpenCV", "ok": _module_installed("cv2"),
         "detail": "terpasang" if _module_installed("cv2") else "belum terpasang (Fase 4)", "required": False},
        {"key": "ollama", "label": "Ollama", "ok": ollama["running"], "detail": "berjalan" if ollama["running"] else ollama["reason"], "required": False},
    ]
    required_ok = all(c["ok"] for c in checks if c["required"])
    status = "ok" if required_ok else "degraded"
    return {
        "status": status, "version": __version__, "python": sys.version.split()[0], "platform": platform.platform(),
        "bind": f"{s.host}:{s.port}", "checks": checks, "ffmpeg": ff, "nvenc": nv, "ollama": ollama,
        "storage_dir": str(s.storage_dir), "models_dir": str(s.models_dir),
        "limits": {**rs.get_limits(db), "max_upload_mb": s.max_upload_mb},
        "cuda": gpu_monitor.cuda_compatibility(),
        "models_loaded": mm.manager.status(),
        "capabilities": capabilities(),
    }


@router.get("/system/gpu")
def gpu(refresh_nvenc: bool = Query(default=False)) -> dict[str, Any]:
    info = gpu_monitor.query_gpus()
    info["nvenc"] = gpu_monitor.nvenc_status(force=refresh_nvenc)
    return info


@router.get("/system/resources")
def resources() -> dict[str, Any]:
    return gpu_monitor.resource_snapshot()


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)) -> dict[str, Any]:
    def count(stmt) -> int:
        return db.scalar(stmt) or 0

    jobs_by_status = dict(db.execute(select(RenderJob.status, func.count()).group_by(RenderJob.status)).all())
    recent_projects = db.scalars(select(Project).order_by(Project.updated_at.desc()).limit(5)).all()
    activity = db.scalars(select(ActivityLog).order_by(ActivityLog.id.desc()).limit(12)).all()
    queue = db.scalars(select(RenderJob).where(RenderJob.status.in_(["queued", "running", "paused"])).order_by(RenderJob.created_at).limit(20)).all()
    pcount = {pid: c for pid, c in db.execute(select(Video.project_id, func.count()).group_by(Video.project_id)).all()}
    return {
        "totals": {
            "projects": count(select(func.count()).select_from(Project)),
            "videos": count(select(func.count()).select_from(Video)),
            "clips": count(select(func.count()).select_from(Clip)),
            "renders_done": jobs_by_status.get("done", 0),
            "renders_failed": jobs_by_status.get("failed", 0),
            "jobs_running": jobs_by_status.get("running", 0),
            "jobs_queued": jobs_by_status.get("queued", 0),
        },
        "recent_projects": [
            {"id": p.id, "name": p.name, "status": p.status, "updated_at": p.updated_at, "video_count": pcount.get(p.id, 0)}
            for p in recent_projects
        ],
        "activity": [{"id": a.id, "kind": a.kind, "message": a.message, "created_at": a.created_at} for a in activity],
        "queue": [{"id": j.id, "status": j.status, "progress": j.progress, "clip_id": j.clip_id} for j in queue],
    }


@router.get("/system/limits")
def get_limits(db: Session = Depends(get_db)) -> dict[str, Any]:
    lim = rs.get_limits(db)
    device, reason = mm.resolve_device(lim["compute_mode"])
    return {**lim, "effective_device": device, "device_reason": reason}


@router.put("/system/limits")
def put_limits(body: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
    lim = rs.set_limits(db, body)
    device, reason = mm.resolve_device(lim["compute_mode"])
    return {**lim, "effective_device": device, "device_reason": reason}


@router.get("/system/models")
def models_loaded() -> list[dict[str, Any]]:
    return mm.manager.status()


@router.post("/system/models/{key}/unload")
def unload_model(key: str) -> dict[str, Any]:
    if not mm.manager.unload(key):
        raise not_found("Model yang sedang dimuat")
    return {"unloaded": key}


@router.post("/system/models/unload-all")
def unload_all() -> dict[str, Any]:
    return {"unloaded": mm.manager.unload_all()}
