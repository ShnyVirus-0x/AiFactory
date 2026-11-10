"""Endpoint antrean, ekspor, dan template. Antrean/ekspor membaca DB nyata (kosong sampai Fase 6)."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..config import get_settings
from ..models import ActivityLog, Clip, Project, RenderJob, Template
from ..utils.errors import AppError, not_found
from ..utils.events import hub
from ..utils.files import is_within
from ..workers import render_worker

router = APIRouter(tags=["jobs"])


def _job(j: RenderJob) -> dict:
    # path lokal server tidak diekspos; unduhan hanya lewat /exports/{id}/file (dibatasi ke folder output aplikasi)
    return {"id": j.id, "clip_id": j.clip_id, "status": j.status, "progress": j.progress, "has_output": bool(j.output_path and j.status == "done"),
            "download_url": f"/api/exports/{j.id}/file" if j.output_path and j.status == "done" else None, "error_message": j.error_message,
            "encoder": j.encoder, "uses_gpu": j.uses_gpu, "output_info": j.output_info, "created_at": j.created_at, "updated_at": j.updated_at,
            "clip_title": j.clip.title if j.clip else ""}


class BatchRenderIn(BaseModel):
    clip_ids: list[str] = Field(min_length=1, max_length=500)

    @field_validator("clip_ids")
    @classmethod
    def unique_clip_ids(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("Daftar klip tidak boleh berisi duplikat")
        return value


def _active_job(db: Session, clip_id: str) -> RenderJob | None:
    return db.scalar(select(RenderJob).where(RenderJob.clip_id == clip_id, RenderJob.status.in_(["queued", "running"])))


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


@router.post("/jobs/{job_id}/retry", status_code=202)
def retry_job(job_id: str, db: Session = Depends(get_db)) -> dict:
    previous = db.get(RenderJob, job_id)
    if not previous:
        raise not_found("Job")
    if previous.status != "failed":
        raise AppError(409, "not_retryable", "Hanya job gagal yang dapat dicoba ulang")
    if not db.get(Clip, previous.clip_id):
        raise not_found("Klip")
    active = _active_job(db, previous.clip_id)
    if active:
        raise AppError(409, "already_running", "Klip ini sedang/akan dirender", {"job_id": active.id})
    job = RenderJob(clip_id=previous.clip_id, status="queued")
    db.add(job)
    db.add(ActivityLog(kind="render", message=f"Render dicoba ulang: {previous.clip.title}", project_id=previous.clip.project_id))
    db.commit()
    hub.publish("data.changed", {"kind": "render"})
    render_worker.submit(job.id)
    return _job(job)


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


@router.post("/projects/{project_id}/render", status_code=202)
def render_project(project_id: str, body: BatchRenderIn, db: Session = Depends(get_db)) -> dict:
    if not db.get(Project, project_id):
        raise not_found("Proyek")
    clips = {c.id: c for c in db.scalars(select(Clip).where(Clip.project_id == project_id, Clip.id.in_(body.clip_ids)))}
    missing = [clip_id for clip_id in body.clip_ids if clip_id not in clips]
    if missing:
        raise AppError(422, "validation_error", "Satu atau lebih klip tidak ditemukan di proyek ini", {"clip_ids": missing})

    jobs: list[RenderJob] = []
    skipped: list[dict[str, str]] = []
    for clip_id in body.clip_ids:
        clip = clips[clip_id]
        if _active_job(db, clip_id):
            skipped.append({"clip_id": clip_id, "reason": "already_running"})
            continue
        job = RenderJob(clip_id=clip_id, status="queued")
        db.add(job)
        db.add(ActivityLog(kind="render", message=f"Render dimulai: {clip.title}", project_id=project_id))
        jobs.append(job)

    db.commit()
    if jobs:
        hub.publish("data.changed", {"kind": "render"})
    for job in jobs:
        render_worker.submit(job.id)
    return {"jobs": [_job(job) for job in jobs], "skipped": skipped}


@router.get("/templates")
def list_templates(db: Session = Depends(get_db)) -> list[dict]:
    return [{"id": t.id, "name": t.name, "template_type": t.template_type, "config_json": t.config_json}
            for t in db.scalars(select(Template).order_by(Template.name))]


@router.post("/templates", status_code=501)
def create_template() -> None:
    raise not_available("Editor template", 5)
