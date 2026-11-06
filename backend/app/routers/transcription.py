from __future__ import annotations

import re
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ActivityLog, Transcript, TranscriptionJob, TranscriptSegment, Video
from ..models.core import utcnow
from ..services import subtitle_export as ex
from ..services import transcript_ops as ops
from ..services import whisper_models as wm
from ..utils.errors import AppError, not_found
from ..utils.files import sanitize_filename
from ..utils.events import hub
from ..workers import transcription_worker as worker

router = APIRouter(tags=["transcription"])

LANG_RE = re.compile(r"^(auto|[a-z]{2,3})$")


# ---------------- model ----------------
@router.get("/transcription/models")
def list_models() -> list[dict[str, Any]]:
    return wm.list_models()


class DownloadIn(BaseModel):
    confirm: bool = False


@router.post("/transcription/models/{name}/download", status_code=202)
def download_model(name: str, body: DownloadIn) -> dict[str, Any]:
    spec = wm.CATALOG.get(name)
    if not spec:
        raise not_found("Model")
    if not body.confirm:
        raise AppError(400, "confirmation_required",
                       f"Unduhan model '{name}' memerlukan persetujuan: perkiraan ±{spec.approx_mb} MB dari huggingface.co ({spec.repo}). Kirim confirm=true.",
                       {"approx_size_mb": spec.approx_mb, "repo": spec.repo})
    try:
        return wm.downloads.start(name)
    except FileExistsError as e:
        raise AppError(409, "already_installed", str(e)) from e
    except RuntimeError as e:
        raise AppError(409, "download_in_progress", str(e)) from e
    except OSError as e:
        raise AppError(507, "insufficient_storage", str(e)) from e


# ---------------- job ----------------
class TranscribeIn(BaseModel):
    language: str = "auto"
    model: str | None = None
    audio_track: int = Field(default=0, ge=0, le=31)


def _job(j: TranscriptionJob) -> dict[str, Any]:
    return {"id": j.id, "video_id": j.video_id, "transcript_id": j.transcript_id, "status": j.status, "progress": j.progress, "language": j.language,
            "model": j.model, "device": j.device, "audio_track": j.audio_track, "error_message": j.error_message, "created_at": j.created_at, "updated_at": j.updated_at}


@router.post("/videos/{video_id}/transcribe", status_code=202)
def transcribe(video_id: str, body: TranscribeIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    from ..config import get_settings

    video = db.get(Video, video_id)
    if not video:
        raise not_found("Video")
    if not LANG_RE.match(body.language):
        raise AppError(422, "validation_error", "language harus 'auto' atau kode ISO seperti 'id', 'en'")
    model = body.model or get_settings().whisper_model
    if model not in wm.CATALOG:
        raise AppError(422, "validation_error", f"Model tidak dikenal: {model}")
    if not wm.is_installed(model):
        raise AppError(409, "model_not_installed", f"Model Whisper '{model}' belum diunduh. Unduh dahulu (±{wm.CATALOG[model].approx_mb} MB).", {"model": model})
    if video.audio_tracks < 1:
        raise AppError(422, "no_audio", "Video ini tidak memiliki trek audio")
    if body.audio_track >= video.audio_tracks:
        raise AppError(422, "validation_error", f"Trek audio {body.audio_track} tidak ada (video punya {video.audio_tracks} trek)")
    active = db.scalar(select(TranscriptionJob).where(TranscriptionJob.video_id == video_id, TranscriptionJob.status.in_(["queued", "running"])))
    if active:
        raise AppError(409, "already_running", "Video ini sedang/akan ditranskripsi", {"job_id": active.id})
    job = TranscriptionJob(video_id=video_id, language=body.language, model=model, audio_track=body.audio_track)
    db.add(job)
    db.add(ActivityLog(kind="transcribe", message=f"Transkripsi dimulai: {video.filename}", project_id=video.project_id))
    db.commit()
    worker.submit(job.id)
    return _job(job)


@router.get("/transcription/jobs")
def list_jobs(video_id: str | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    q = select(TranscriptionJob).order_by(TranscriptionJob.created_at.desc()).limit(100)
    if video_id:
        q = q.where(TranscriptionJob.video_id == video_id)
    return [_job(j) for j in db.scalars(q)]


@router.get("/transcription/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    j = db.get(TranscriptionJob, job_id)
    if not j:
        raise not_found("Job")
    return _job(j)


@router.post("/transcription/jobs/{job_id}/cancel")
def cancel_job(job_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    j = db.get(TranscriptionJob, job_id)
    if not j:
        raise not_found("Job")
    if j.status not in ("queued", "running"):
        raise AppError(409, "not_cancellable", f"Job berstatus '{j.status}'")
    worker.request_cancel(job_id)
    if j.status == "queued":
        j.status = "cancelled"
        db.commit()
        hub.publish("transcription.job", {"id": j.id, "video_id": j.video_id, "status": "cancelled", "progress": 0})
    return _job(j)


# ---------------- transkrip ----------------
def _tr(t: Transcript, db: Session) -> dict[str, Any]:
    n = db.scalar(select(func.count()).select_from(TranscriptSegment).where(TranscriptSegment.transcript_id == t.id)) or 0
    return {"id": t.id, "video_id": t.video_id, "language": t.language, "model": t.model, "duration": t.duration,
            "language_probability": t.language_probability, "source": t.source, "segment_count": n, "created_at": t.created_at}


def _seg(s: TranscriptSegment) -> dict[str, Any]:
    return {"id": s.id, "start_time": s.start_time, "end_time": s.end_time, "text": s.text, "edited": s.edited,
            "words_estimated": s.words_estimated, "word_count": len(s.word_timestamps_json or []) or len(s.text.split()),
            "words": [w["word"].strip() for w in (s.word_timestamps_json or [])] or s.text.split()}


@router.get("/videos/{video_id}/transcripts")
def video_transcripts(video_id: str, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    if not db.get(Video, video_id):
        raise not_found("Video")
    return [_tr(t, db) for t in db.scalars(select(Transcript).where(Transcript.video_id == video_id).order_by(Transcript.created_at.desc()))]


def _get_tr(db: Session, tid: str) -> Transcript:
    t = db.get(Transcript, tid)
    if not t:
        raise not_found("Transkrip")
    return t


def _like_escape(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/transcripts/{tid}")
def get_transcript(tid: str, q: str = "", offset: int = Query(0, ge=0), limit: int = Query(2000, ge=1, le=5000), db: Session = Depends(get_db)) -> dict[str, Any]:
    t = _get_tr(db, tid)
    base = select(TranscriptSegment).where(TranscriptSegment.transcript_id == tid)
    if q.strip():
        base = base.where(TranscriptSegment.text.ilike(f"%{_like_escape(q.strip())}%", escape="\\"))
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    segs = db.scalars(base.order_by(TranscriptSegment.start_time, TranscriptSegment.id).offset(offset).limit(limit)).all()
    return {**_tr(t, db), "total_matches": total, "segments": [_seg(s) for s in segs]}


@router.delete("/transcripts/{tid}", status_code=204)
def delete_transcript(tid: str, db: Session = Depends(get_db)) -> Response:
    db.delete(_get_tr(db, tid))
    db.commit()
    return Response(status_code=204)


class SegmentPatch(BaseModel):
    text: str | None = Field(default=None, max_length=5000)
    start_time: float | None = None
    end_time: float | None = None


def _video_of(db: Session, seg: TranscriptSegment) -> Video | None:
    t = db.get(Transcript, seg.transcript_id)
    return db.get(Video, t.video_id) if t else None


@router.patch("/transcripts/segments/{seg_id}")
def patch_segment(seg_id: int, body: SegmentPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    seg = db.get(TranscriptSegment, seg_id)
    if not seg:
        raise not_found("Segmen")
    v = _video_of(db, seg)
    return _seg(ops.update_segment(db, seg_id, body.text, body.start_time, body.end_time, v.duration if v else 0.0))


class SplitIn(BaseModel):
    word_index: int = Field(ge=0)


@router.post("/transcripts/segments/{seg_id}/split")
def split(seg_id: int, body: SplitIn, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    a, b = ops.split_segment(db, seg_id, body.word_index)
    return [_seg(a), _seg(b)]


@router.post("/transcripts/segments/{seg_id}/merge-next")
def merge_next(seg_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    seg = ops.merge_with_next(db, seg_id)
    ops.rebuild_full_text(db, db.get(Transcript, seg.transcript_id))
    db.commit()
    return _seg(seg)


@router.delete("/transcripts/segments/{seg_id}", status_code=204)
def delete_seg(seg_id: int, db: Session = Depends(get_db)) -> Response:
    ops.delete_segment(db, seg_id)
    return Response(status_code=204)


class ReplaceIn(BaseModel):
    find: str = Field(min_length=1, max_length=200)
    replace: str = Field(max_length=200)
    case_sensitive: bool = False
    whole_word: bool = False


@router.post("/transcripts/{tid}/replace")
def replace(tid: str, body: ReplaceIn, db: Session = Depends(get_db)) -> dict[str, int]:
    return {"replaced": ops.replace_all(db, _get_tr(db, tid), body.find, body.replace, body.case_sensitive, body.whole_word)}


@router.get("/transcripts/{tid}/export")
def export(tid: str, format: Literal["srt", "vtt", "txt"] = "srt", db: Session = Depends(get_db)) -> Response:
    t = _get_tr(db, tid)
    segs = db.scalars(select(TranscriptSegment).where(TranscriptSegment.transcript_id == tid).order_by(TranscriptSegment.start_time, TranscriptSegment.id)).all()
    body = {"srt": ex.to_srt, "vtt": ex.to_vtt, "txt": ex.to_txt}[format](segs)
    v = db.get(Video, t.video_id)
    stem = sanitize_filename(v.filename if v else "transkrip").rsplit(".", 1)[0] or "transkrip"
    media = {"srt": "application/x-subrip", "vtt": "text/vtt", "txt": "text/plain"}[format]
    return Response(content=body, media_type=f"{media}; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{stem}.{t.language or "xx"}.{format}"'})
