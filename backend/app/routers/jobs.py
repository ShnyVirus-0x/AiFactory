"""Endpoint antrean, ekspor, dan template. Antrean/ekspor membaca DB nyata (kosong sampai Fase 6)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import RenderJob, Template
from ..utils.errors import not_available

router = APIRouter(tags=["jobs"])


def _job(j: RenderJob) -> dict:
    return {"id": j.id, "clip_id": j.clip_id, "status": j.status, "progress": j.progress, "output_path": j.output_path,
            "error_message": j.error_message, "created_at": j.created_at, "updated_at": j.updated_at}


@router.get("/jobs")
def list_jobs(db: Session = Depends(get_db)) -> list[dict]:
    return [_job(j) for j in db.scalars(select(RenderJob).order_by(RenderJob.created_at.desc()).limit(200))]


@router.get("/exports")
def list_exports(db: Session = Depends(get_db)) -> list[dict]:
    return [_job(j) for j in db.scalars(select(RenderJob).where(RenderJob.status == "done").order_by(RenderJob.updated_at.desc()).limit(200))]


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
