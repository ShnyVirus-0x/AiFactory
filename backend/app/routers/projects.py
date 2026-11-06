from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import ActivityLog, Clip, Project, Video
from ..schemas import ProjectCreate, ProjectOut, ProjectUpdate
from ..utils.errors import not_found
from ..utils.events import hub

router = APIRouter(prefix="/projects", tags=["projects"])


def _out(db: Session, p: Project) -> ProjectOut:
    vc = db.scalar(select(func.count()).select_from(Video).where(Video.project_id == p.id)) or 0
    cc = db.scalar(select(func.count()).select_from(Clip).where(Clip.project_id == p.id)) or 0
    o = ProjectOut.model_validate(p)
    o.video_count, o.clip_count = vc, cc
    return o


def get_project_or_404(db: Session, project_id: str) -> Project:
    p = db.get(Project, project_id)
    if p is None:
        raise not_found("Proyek")
    return p


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)) -> ProjectOut:
    p = Project(name=body.name, description=body.description)
    db.add(p)
    db.add(ActivityLog(kind="project.created", message=f"Proyek dibuat: {p.name}", project_id=p.id))
    db.commit()
    hub.publish("project.created", {"id": p.id})
    return _out(db, p)


@router.get("", response_model=list[ProjectOut])
def list_projects(
    status: str | None = Query(default=None, pattern="^(active|archived)$"),
    q: str | None = Query(default=None, max_length=100),
    db: Session = Depends(get_db),
) -> list[ProjectOut]:
    stmt = select(Project).order_by(Project.updated_at.desc()).limit(500)
    if status:
        stmt = stmt.where(Project.status == status)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(Project.name.ilike(like) | Project.description.ilike(like))
    return [_out(db, p) for p in db.scalars(stmt)]


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, db: Session = Depends(get_db)) -> ProjectOut:
    return _out(db, get_project_or_404(db, project_id))


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(project_id: str, body: ProjectUpdate, db: Session = Depends(get_db)) -> ProjectOut:
    p = get_project_or_404(db, project_id)
    if body.name is not None:
        p.name = body.name.strip() or p.name
    if body.description is not None:
        p.description = body.description
    if body.status is not None:
        p.status = body.status
    db.commit()
    hub.publish("project.updated", {"id": p.id})
    return _out(db, p)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, db: Session = Depends(get_db)) -> Response:
    p = get_project_or_404(db, project_id)
    s = get_settings()
    files: list[Path] = []
    for v in p.videos:
        files.append(Path(v.source_path))
        if v.thumbnail_path:
            files.append(Path(v.thumbnail_path))
    name = p.name
    db.delete(p)
    db.add(ActivityLog(kind="project.deleted", message=f"Proyek dihapus: {name}"))
    db.commit()
    for f in files:  # hapus file hanya di dalam direktori yang dikelola aplikasi
        from ..utils.files import is_within

        if is_within(f, s.storage_dir):
            f.unlink(missing_ok=True)
    hub.publish("project.deleted", {"id": project_id})
    return Response(status_code=204)
