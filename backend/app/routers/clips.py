from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import ActivityLog, Clip, ClipEdit, RenderJob, Transcript, TranscriptSegment, Video
from ..schemas.render import RenderSpec
from ..services import clip_detection
from ..services import face_detection as fd
from ..services import rendering as rd
from ..services import smart_crop as sc
from ..utils.errors import AppError, not_found
from ..workers import render_worker as worker

router = APIRouter(tags=["clips"])
MIN_CLIP, MAX_CLIP = 1.0, 900.0


def _clip(c: Clip) -> dict[str, Any]:
    return {"id": c.id, "project_id": c.project_id, "video_id": c.video_id, "title": c.title, "hook": c.hook, "start_time": c.start_time, "end_time": c.end_time,
            "duration": c.duration, "transcript": c.transcript, "score": c.score, "category": c.category, "approved": c.approved, "created_at": c.created_at}


def _get(db: Session, cid: str) -> Clip:
    c = db.get(Clip, cid)
    if not c:
        raise not_found("Klip")
    return c


def _validate_range(video: Video, start: float, end: float) -> None:
    if start < 0 or end <= start:
        raise AppError(422, "validation_error", "Waktu klip tidak valid: mulai ≥ 0 dan selesai > mulai")
    if end > video.duration + 0.25:
        raise AppError(422, "validation_error", f"Waktu selesai melebihi durasi video ({video.duration:.1f} dtk)")
    if not MIN_CLIP <= end - start <= MAX_CLIP:
        raise AppError(422, "validation_error", f"Durasi klip harus {MIN_CLIP:.0f}–{MAX_CLIP:.0f} detik")


def _text_in_range(db: Session, video_id: str, start: float, end: float) -> str:
    tr = db.scalar(select(Transcript).where(Transcript.video_id == video_id).order_by(Transcript.created_at.desc()))
    if not tr:
        return ""
    segs = db.scalars(select(TranscriptSegment).where(TranscriptSegment.transcript_id == tr.id, TranscriptSegment.end_time > start, TranscriptSegment.start_time < end).order_by(TranscriptSegment.start_time))
    return " ".join(s.text.strip() for s in segs)


class ClipIn(BaseModel):
    start_time: float
    end_time: float
    title: str = Field(default="", max_length=200)
    hook: str = Field(default="", max_length=1000)
    score: float = Field(default=0, ge=0, le=100)
    category: str = Field(default="manual", max_length=60)


class ClipPatch(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    start_time: float | None = None
    end_time: float | None = None
    approved: bool | None = None


class SuggestClipsIn(BaseModel):
    max_candidates: int = Field(default=12, ge=1, le=30)


@router.get("/clips")
def list_clips(video_id: str | None = None, project_id: str | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    q = select(Clip).order_by(Clip.start_time)
    if video_id:
        q = q.where(Clip.video_id == video_id)
    if project_id:
        q = q.where(Clip.project_id == project_id)
    return [_clip(c) for c in db.scalars(q.limit(500))]


@router.post("/videos/{video_id}/suggest-clips")
def suggest_clips(video_id: str, body: SuggestClipsIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    video = db.get(Video, video_id)
    if not video:
        raise not_found("Video")
    transcript = db.scalar(
        select(Transcript).where(Transcript.video_id == video_id).order_by(Transcript.created_at.desc())
    )
    if not transcript:
        raise AppError(409, "transcript_required", "Buat transkrip video ini sebelum menganalisis kandidat klip.")
    segments = db.scalars(
        select(TranscriptSegment)
        .where(TranscriptSegment.transcript_id == transcript.id)
        .order_by(TranscriptSegment.start_time, TranscriptSegment.id)
    ).all()
    lines = [clip_detection.TranscriptLine(s.start_time, s.end_time, s.text) for s in segments]
    try:
        candidates = clip_detection.suggest_candidates(lines, video.duration, body.max_candidates)
    except clip_detection.ClipDetectionError as exc:
        raise AppError(503, "clip_analysis_unavailable", str(exc)) from exc
    return {
        "video_id": video.id,
        "transcript_id": transcript.id,
        "model": get_settings().ollama_model,
        "candidates": [candidate.as_dict() for candidate in candidates],
    }


@router.post("/videos/{video_id}/clips", status_code=201)
def create_clip(video_id: str, body: ClipIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    v = db.get(Video, video_id)
    if not v:
        raise not_found("Video")
    _validate_range(v, body.start_time, body.end_time)
    c = Clip(project_id=v.project_id, video_id=v.id, title=body.title or f"Klip {body.start_time:.0f}s", start_time=body.start_time, end_time=body.end_time,
             duration=body.end_time - body.start_time, transcript=_text_in_range(db, v.id, body.start_time, body.end_time),
             hook=body.hook, score=body.score, category=body.category)
    db.add(c)
    db.add(ActivityLog(kind="clip", message=f"Klip dibuat: {c.title}", project_id=v.project_id))
    db.commit()
    return _clip(c)


@router.patch("/clips/{cid}")
def patch_clip(cid: str, body: ClipPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    c = _get(db, cid)
    ns = c.start_time if body.start_time is None else body.start_time
    ne = c.end_time if body.end_time is None else body.end_time
    if (ns, ne) != (c.start_time, c.end_time):
        _validate_range(db.get(Video, c.video_id), ns, ne)
        c.start_time, c.end_time, c.duration = ns, ne, ne - ns
        c.transcript = _text_in_range(db, c.video_id, ns, ne)
    if body.title is not None:
        c.title = body.title
    if body.approved is not None:
        c.approved = body.approved
    db.commit()
    return _clip(c)


@router.delete("/clips/{cid}", status_code=204)
def delete_clip(cid: str, db: Session = Depends(get_db)) -> Response:
    db.delete(_get(db, cid))
    db.commit()
    return Response(status_code=204)


@router.get("/clips/{cid}/edit")
def get_edit(cid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    _get(db, cid)
    return worker.get_spec(db, cid).model_dump()


@router.put("/clips/{cid}/edit")
def put_edit(cid: str, spec: RenderSpec, db: Session = Depends(get_db)) -> dict[str, Any]:
    _get(db, cid)
    row = db.scalar(select(ClipEdit).where(ClipEdit.clip_id == cid))
    if row:
        row.edit_config_json = spec.model_dump()
    else:
        db.add(ClipEdit(clip_id=cid, edit_config_json=spec.model_dump()))
    db.commit()
    return spec.model_dump()


@router.post("/clips/{cid}/analyze-crop")
def analyze_crop(cid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Jalankan deteksi wajah pada klip dan kembalikan jalur kamera virtual (untuk pratinjau sebelum render)."""
    from pathlib import Path

    c = _get(db, cid)
    v = db.get(Video, c.video_id)
    st = fd.detector_status()
    if not st["available"]:
        return {"available": False, "reason": st["reason"], "track": [], "note": "Face tracking tidak tersedia; center crop dipakai"}
    a = worker.analyze_track(Path(v.source_path), c.start_time, c.end_time)
    return {"available": True, "reason": None, "samples": a.samples, "frames_with_face": a.frames_with_face, "max_faces": a.max_faces, "travel": round(a.travel, 3),
            "static": a.static, "note": a.note, "track": [{"t": round(t, 2), "x": round(x, 4)} for t, x in (a.track or [])]}


@router.get("/clips/{cid}/preview")
def preview(cid: str, t: float = Query(0.0, ge=0), width: int = Query(540, ge=120, le=1080), db: Session = Depends(get_db)) -> Response:
    """Frame pratinjau memakai crop/layout yang sama dengan render. Posisi crop wajah dihitung dari wajah pada frame tsb."""
    from pathlib import Path

    c = _get(db, cid)
    v = db.get(Video, c.video_id)
    spec = worker.get_spec(db, cid)
    t = min(t, max(0.0, c.duration - 0.05))
    track = None
    if spec.layout == "fill" and spec.crop_mode == "face" and fd.detector_status()["available"]:
        samples = fd.detect_faces(Path(v.source_path), c.start_time + t, c.start_time + t, sample_fps=1.0)
        a = sc.build_crop_track(samples, min_face_ratio=0.5)
        track = a.track
    try:
        jpg = rd.preview_frame(Path(v.source_path), c.start_time, t, spec, v.width, v.height, track, width)
    except rd.RenderError as e:
        raise AppError(500, "preview_failed", str(e)) from e
    return Response(content=jpg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.post("/clips/{cid}/render", status_code=202)
def render_clip(cid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    c = _get(db, cid)
    v = db.get(Video, c.video_id)
    if not v:
        raise not_found("Video")
    active = db.scalar(select(RenderJob).where(RenderJob.clip_id == cid, RenderJob.status.in_(["queued", "running"])))
    if active:
        raise AppError(409, "already_running", "Klip ini sedang/akan dirender", {"job_id": active.id})
    job = RenderJob(clip_id=cid, status="queued")
    db.add(job)
    db.add(ActivityLog(kind="render", message=f"Render dimulai: {c.title}", project_id=c.project_id))
    db.commit()
    worker.submit(job.id)
    return {"id": job.id, "status": job.status}
