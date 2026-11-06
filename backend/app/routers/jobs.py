"""Endpoint antrean, ekspor, dan template. Antrean/ekspor membaca DB nyata (kosong sampai Fase 6)."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..config import get_settings
from ..models import Clip, RenderJob, Template
from ..utils.errors import AppError, not_available, not_found
from ..utils.files import is_within
from ..workers import render_worker

router = APIRouter(tags=["jobs"])


def _job(j: RenderJob) -> dict:
    # path lokal server tidak diekspos; unduhan hanya lewat /exports/{id}/file (dibatasi ke folder output aplikasi)
    return {"id": j.id, "clip_id": j.clip_id, "status": j.status, "progress": j.progress, "has_output": bool(j.output_path and j.status == "done"),
            "download_url": f"/api/exports/{j.id}/file" if j.output_path and j.status == "done" else None, "error_message": j.error_message,
            "encoder": j.encoder, "uses_gpu": j.uses_gpu, "output_info": j.output_info, "created_at": j.created_at, "updated_at": j.updated_at}


@router.get("/jobs")
def list_jobs(db: Session = Depends(get_db)) -> list[dict]:
    return [_job(j) for j in db.scalars(select(RenderJob).order_by(RenderJob.created_at.desc()).limit(200))]


@router.get("/exports")
def list_exports(db: Session = Depends(get_db)) -> list[dict]:
    return [_job(j) for j in db.scalars(select(RenderJob).where(RenderJob.status == "done").order_by(RenderJob.updated_at.desc()).limit(200))]


@router.get("/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)) -> dict:
    j = db.get(RenderJob, job_id)
    if not j:
        raise not_found("Job")
    return _job(j)


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, db: Session = Depends(get_db)) -> dict:
    j = db.get(RenderJob, job_id)
    if not j:
        raise not_found("Job")
    if j.status not in ("queued", "running"):
        raise AppError(409, "not_cancellable", f"Job berstatus '{j.status}'")
    render_worker.request_cancel(job_id)
    if j.status == "queued":
        j.status = "cancelled"
        db.commit()
    return _job(j)


@router.get("/exports/{job_id}/file")
def download_export(job_id: str, db: Session = Depends(get_db)) -> Response:
    """Unduh hasil render. Hanya file di dalam folder output aplikasi yang boleh disajikan."""
    j = db.get(RenderJob, job_id)
    if not j or j.status != "done" or not j.output_path:
        raise not_found("Hasil render")
    p = Path(j.output_path)
    if not is_within(p, get_settings().outputs_dir) or not p.is_file():
        raise not_found("File hasil render")
    clip = db.get(Clip, j.clip_id)
    from ..utils.files import sanitize_filename

    name = sanitize_filename((clip.title if clip else "klip") or "klip", default="klip") + ".mp4"
    return FileResponse(p, media_type="video/mp4", filename=name)


@router.post("/projects/{project_id}/render", status_code=501)
def render_project(project_id: str) -> None:  # noqa: ARG001
    raise not_available("Rendering batch", 6)


@router.get("/templates")
def list_templates(db: Session = Depends(get_db)) -> list[dict]:
    return [{"id": t.id, "name": t.name, "template_type": t.template_type, "config_json": t.config_json}
            for t in db.scalars(select(Template).order_by(Template.name))]


@router.post("/templates", status_code=501)
def create_template() -> None:
    raise not_available("Editor template", 5)
