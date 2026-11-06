"""Render satu klip (status persisten di tabel render_jobs). Antrean batch lengkap (jeda/lanjut/ulang) dikerjakan Fase 6."""
from __future__ import annotations

import logging
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlalchemy import select

from ..config import get_settings
from ..database import SessionLocal
from ..models import Clip, ClipEdit, RenderJob, Transcript, TranscriptSegment, Video
from ..schemas.render import RenderSpec
from ..services import face_detection as fd
from ..services import rendering as rd
from ..services import runtime_settings as rs
from ..services import smart_crop as sc
from ..services import subtitle as st
from ..utils.events import hub

log = logging.getLogger("asf.render.worker")

_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="render")
_cancel: dict[str, threading.Event] = {}
_cv = threading.Condition()
_running = 0


def _limit() -> int:
    with SessionLocal() as db:
        return rs.get_limits(db)["gpu_render_workers"]


def _publish(job: RenderJob) -> None:
    hub.publish("render.job", {"id": job.id, "clip_id": job.clip_id, "status": job.status, "progress": round(job.progress, 4), "error": job.error_message,
                               "encoder": job.encoder, "uses_gpu": job.uses_gpu})


def submit(job_id: str) -> None:
    _cancel.setdefault(job_id, threading.Event())
    _pool.submit(_guarded, job_id)


def request_cancel(job_id: str) -> bool:
    ev = _cancel.get(job_id)
    if ev:
        ev.set()
        return True
    return False


def _guarded(job_id: str) -> None:
    global _running
    with _cv:
        while _running >= _limit() and not _cancel[job_id].is_set():
            _cv.wait(timeout=1.0)
        _running += 1
    try:
        run_render(job_id)
    finally:
        with _cv:
            _running -= 1
            _cv.notify_all()
        _cancel.pop(job_id, None)


def recover_on_startup() -> None:
    with SessionLocal() as db:
        for j in db.scalars(select(RenderJob).where(RenderJob.status == "running")):
            j.status, j.error_message = "failed", "Terhenti karena aplikasi ditutup saat render berjalan. Render ulang."
        queued = [j.id for j in db.scalars(select(RenderJob).where(RenderJob.status == "queued"))]
        db.commit()
    for jid in queued:
        submit(jid)


def transcript_segments(db, video_id: str) -> list[dict]:
    tr = db.scalar(select(Transcript).where(Transcript.video_id == video_id).order_by(Transcript.created_at.desc()))
    if not tr:
        return []
    segs = db.scalars(select(TranscriptSegment).where(TranscriptSegment.transcript_id == tr.id).order_by(TranscriptSegment.start_time))
    return [{"start": s.start_time, "end": s.end_time, "text": s.text, "words": s.word_timestamps_json or []} for s in segs]


def get_spec(db, clip_id: str) -> RenderSpec:
    edit = db.scalar(select(ClipEdit).where(ClipEdit.clip_id == clip_id))
    return RenderSpec.model_validate(edit.edit_config_json or {}) if edit else RenderSpec()


def analyze_track(video_path: Path, start: float, end: float) -> sc.CropAnalysis:
    return sc.build_crop_track(fd.detect_faces(video_path, start, end))


def run_render(job_id: str) -> None:
    s = get_settings()
    cancel = _cancel.setdefault(job_id, threading.Event())
    out_path: Path | None = None
    work: Path | None = None
    with SessionLocal() as db:
        job = db.get(RenderJob, job_id)
        if job is None:
            return
        if cancel.is_set() or job.status == "cancelled":
            job.status = "cancelled"
            db.commit()
            _publish(job)
            return
        try:
            clip = db.get(Clip, job.clip_id)
            video = db.get(Video, clip.video_id) if clip else None
            if clip is None or video is None:
                raise rd.RenderError("Klip atau video sumber tidak ditemukan")
            spec = get_spec(db, clip.id)
            limits = rs.get_limits(db)
            enc, gpu, why = rd.pick_encoder(spec.codec, limits["compute_mode"])
            job.status, job.progress, job.encoder, job.uses_gpu, job.spec_json = "running", 0.0, enc, gpu, spec.model_dump()
            db.commit()
            _publish(job)
            log.info("Render %s dengan %s (%s)", job_id, enc, why)

            src = Path(video.source_path)
            track = None
            note = ""
            if spec.layout == "fill" and spec.crop_mode == "face":
                try:
                    a = analyze_track(src, clip.start_time, clip.end_time)
                    track, note = a.track, a.note
                except fd.FaceDetectionUnavailable as e:
                    note = f"Face tracking tidak tersedia ({e}); memakai center crop"
            if cancel.is_set():
                raise rd.RenderCancelled()

            work = s.cache_dir / f"render-{job_id}"
            work.mkdir(parents=True, exist_ok=True)
            ass = st.build_ass(transcript_segments(db, video.id), clip.start_time, clip.end_time, spec.captions, spec.title_overlay or None, spec.title_seconds)
            ass_name = None
            if ass:
                (work / "subs.ass").write_text(ass, encoding="utf-8")
                ass_name = "subs.ass"

            out_path = s.outputs_dir / f"{job_id}.mp4"
            cmd = rd.build_command(ffmpeg=s.ffmpeg_bin, src=src, out=out_path, start=clip.start_time, end=clip.end_time, spec=spec, src_w=video.width, src_h=video.height,
                                   encoder=enc, ass_name=ass_name, track=track, has_audio=video.audio_tracks > 0)
            last = [0.0]

            def prog(p: float) -> None:
                job.progress = p
                if p - last[0] >= 0.02:
                    last[0] = p
                    db.commit()
                    _publish(job)

            rd.run_ffmpeg(cmd, work, clip.end_time - clip.start_time, prog, cancel)

            info = rd.probe_output(out_path)
            expected = clip.end_time - clip.start_time
            problems = []
            if (info["width"], info["height"]) != (rd.OUT_W, rd.OUT_H):
                problems.append(f"resolusi {info['width']}x{info['height']}")
            if video.audio_tracks > 0 and not info["has_audio"]:
                problems.append("trek audio hilang")
            if abs(info["duration"] - expected) > 0.5:
                problems.append(f"durasi {info['duration']}s != {expected:.2f}s")
            if problems:
                raise rd.RenderError("Verifikasi FFprobe gagal: " + ", ".join(problems))
            info["crop_note"] = note
            job.output_path, job.output_info, job.status, job.progress = str(out_path), info, "done", 1.0
            db.commit()
            _publish(job)
            hub.publish("data.changed", {"kind": "render"})
        except rd.RenderCancelled:
            db.rollback()
            _fail(db, job_id, "cancelled", None, out_path)
        except Exception as e:  # noqa: BLE001
            db.rollback()
            msg = str(e) if isinstance(e, (rd.RenderError, MemoryError)) else f"{type(e).__name__}: {e}"
            log.warning("Render %s gagal: %s", job_id, type(e).__name__)
            _fail(db, job_id, "failed", msg[:600], out_path)
        finally:
            if work is not None:
                shutil.rmtree(work, ignore_errors=True)


def _fail(db, job_id: str, status: str, msg: str | None, out_path: Path | None) -> None:
    if out_path is not None:
        out_path.unlink(missing_ok=True)
    job = db.get(RenderJob, job_id)
    job.status, job.error_message, job.output_path = status, msg, None
    db.commit()
    _publish(job)
