from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import ActivityLog, Video
from ..schemas import UploadItem, UploadResult, VideoOut, VideoUpdate
from ..services import video_import
from ..utils.errors import AppError, not_found
from ..utils.events import hub
from ..utils.files import is_within, sanitize_filename
from .projects import get_project_or_404

router = APIRouter(prefix="/videos", tags=["videos"])

MIME = {".mp4": "video/mp4", ".mov": "video/quicktime", ".mkv": "video/x-matroska", ".webm": "video/webm", ".avi": "video/x-msvideo"}


def video_out(v: Video) -> VideoOut:
    o = VideoOut.model_validate(v)
    o.has_thumbnail = bool(v.thumbnail_path and Path(v.thumbnail_path).is_file())
    return o


def get_video_or_404(db: Session, video_id: str) -> Video:
    v = db.get(Video, video_id)
    if v is None:
        raise not_found("Video")
    return v


@router.post("/upload", response_model=UploadResult, status_code=201)
def upload_videos(
    project_id: str = Form(...),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
) -> UploadResult:
    s = get_settings()
    project = get_project_or_404(db, project_id)
    if len(files) > s.max_files_per_upload:
        raise AppError(413, "too_many_files", f"Maksimal {s.max_files_per_upload} file per unggahan")
    items: list[UploadItem] = []
    for f in files:
        name = f.filename or "video"
        try:
            imp = video_import.import_stream(f.file, name)
        except video_import.ImportError_ as e:
            items.append(UploadItem(filename=name, ok=False, error=str(e)))
            continue
        dup = db.scalar(select(Video).where(Video.project_id == project.id, Video.sha256 == imp.sha256))
        if dup is not None:  # file yang sama persis sudah ada: jangan proses/simpan ulang
            imp.path.unlink(missing_ok=True)
            if imp.thumbnail:
                imp.thumbnail.unlink(missing_ok=True)
            items.append(UploadItem(filename=name, ok=False, error="File yang sama sudah ada di proyek ini", duplicate_of=dup.id))
            continue
        v = Video(
            project_id=project.id, filename=imp.display_name, source_path=str(imp.path), duration=imp.info.duration,
            width=imp.info.width, height=imp.info.height, fps=imp.info.fps, file_size=imp.size, sha256=imp.sha256,
            video_codec=imp.info.video_codec, audio_tracks=imp.info.audio_tracks,
            thumbnail_path=str(imp.thumbnail) if imp.thumbnail else None,
        )
        db.add(v)
        db.add(ActivityLog(kind="video.uploaded", message=f"Video diunggah: {v.filename}", project_id=project.id))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            imp.path.unlink(missing_ok=True)
            items.append(UploadItem(filename=name, ok=False, error="File yang sama sudah ada di proyek ini"))
            continue
        hub.publish("video.created", {"id": v.id, "project_id": project.id})
        items.append(UploadItem(filename=name, ok=True, video=video_out(v)))
    ok = sum(1 for i in items if i.ok)
    return UploadResult(items=items, succeeded=ok, failed=len(items) - ok)


@router.get("", response_model=list[VideoOut])
def list_videos(
    project_id: str | None = None,
    q: str | None = Query(default=None, max_length=100),
    min_duration: float | None = Query(default=None, ge=0),
    max_duration: float | None = Query(default=None, ge=0),
    min_height: int | None = Query(default=None, ge=0),
    has_audio: bool | None = None,
    sort: str = Query(default="newest", pattern="^(newest|oldest|name|duration|size)$"),
    db: Session = Depends(get_db),
) -> list[VideoOut]:
    stmt = select(Video)
    if project_id:
        stmt = stmt.where(Video.project_id == project_id)
    if q:
        stmt = stmt.where(Video.filename.ilike(f"%{q.strip()}%"))
    if min_duration is not None:
        stmt = stmt.where(Video.duration >= min_duration)
    if max_duration is not None:
        stmt = stmt.where(Video.duration <= max_duration)
    if min_height is not None:
        stmt = stmt.where(Video.height >= min_height)
    if has_audio is not None:
        stmt = stmt.where(Video.audio_tracks > 0 if has_audio else Video.audio_tracks == 0)
    order = {"newest": Video.created_at.desc(), "oldest": Video.created_at.asc(), "name": Video.filename.asc(),
             "duration": Video.duration.desc(), "size": Video.file_size.desc()}[sort]
    return [video_out(v) for v in db.scalars(stmt.order_by(order).limit(1000))]


@router.get("/{video_id}", response_model=VideoOut)
def get_video(video_id: str, db: Session = Depends(get_db)) -> VideoOut:
    return video_out(get_video_or_404(db, video_id))


@router.patch("/{video_id}", response_model=VideoOut)
def rename_video(video_id: str, body: VideoUpdate, db: Session = Depends(get_db)) -> VideoOut:
    v = get_video_or_404(db, video_id)
    v.filename = sanitize_filename(body.filename, default=v.filename)  # hanya nama tampilan; file di disk tidak berubah
    db.commit()
    hub.publish("video.updated", {"id": v.id})
    return video_out(v)


@router.delete("/{video_id}", status_code=204)
def delete_video(video_id: str, db: Session = Depends(get_db)) -> Response:
    v = get_video_or_404(db, video_id)
    s = get_settings()
    files = [Path(v.source_path)] + ([Path(v.thumbnail_path)] if v.thumbnail_path else [])
    pid, name = v.project_id, v.filename
    db.delete(v)
    db.add(ActivityLog(kind="video.deleted", message=f"Video dihapus: {name}", project_id=pid))
    db.commit()
    for f in files:
        if is_within(f, s.storage_dir):
            f.unlink(missing_ok=True)
    hub.publish("video.deleted", {"id": video_id, "project_id": pid})
    return Response(status_code=204)


@router.get("/{video_id}/thumbnail")
def video_thumbnail(video_id: str, db: Session = Depends(get_db)) -> FileResponse:
    v = get_video_or_404(db, video_id)
    p = Path(v.thumbnail_path) if v.thumbnail_path else None
    if not p or not p.is_file() or not is_within(p, get_settings().thumbnails_dir):
        raise not_found("Thumbnail")
    return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@router.get("/{video_id}/stream")
def video_stream(video_id: str, db: Session = Depends(get_db)) -> FileResponse:
    v = get_video_or_404(db, video_id)
    p = Path(v.source_path)
    if not p.is_file() or not is_within(p, get_settings().uploads_dir):
        raise not_found("File video")
    return FileResponse(p, media_type=MIME.get(p.suffix.lower(), "application/octet-stream"))
