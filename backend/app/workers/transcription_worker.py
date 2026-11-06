"""Antrean transkripsi persisten (status di tabel transcription_jobs) dengan batas worker dinamis.

Saat start: job `running` yang tertinggal ditandai gagal (proses sebelumnya berhenti), job `queued` dijadwalkan ulang.
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlalchemy import select

from ..config import get_settings
from ..database import SessionLocal
from ..models import Transcript, TranscriptionJob, TranscriptSegment, Video
from ..models.core import utcnow
from ..services import runtime_settings as rs
from ..services import transcription as tx
from ..utils.events import hub

log = logging.getLogger("asf.transcription.worker")

_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="asr")
_cancel: dict[str, threading.Event] = {}
_cv = threading.Condition()
_running = 0


def _limit() -> int:
    with SessionLocal() as db:
        return rs.get_limits(db)["ai_workers"]


def _publish(job: TranscriptionJob) -> None:
    hub.publish("transcription.job", {"id": job.id, "video_id": job.video_id, "status": job.status, "progress": round(job.progress, 4),
                                       "error": job.error_message, "transcript_id": job.transcript_id})


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
    """Batas jumlah job AI yang berjalan bersamaan (dapat diubah dari Pengaturan tanpa restart)."""
    global _running
    with _cv:
        while _running >= _limit() and not _cancel[job_id].is_set():
            _cv.wait(timeout=1.0)
        _running += 1
    try:
        run_job(job_id)
    finally:
        with _cv:
            _running -= 1
            _cv.notify_all()
        _cancel.pop(job_id, None)


def recover_on_startup() -> None:
    with SessionLocal() as db:
        for j in db.scalars(select(TranscriptionJob).where(TranscriptionJob.status == "running")):
            j.status, j.error_message = "failed", "Terhenti karena aplikasi ditutup saat transkripsi berjalan. Jalankan ulang."
        queued = [j.id for j in db.scalars(select(TranscriptionJob).where(TranscriptionJob.status == "queued"))]
        db.commit()
    for jid in queued:
        submit(jid)


def run_job(job_id: str) -> None:
    s = get_settings()
    cancel = _cancel.setdefault(job_id, threading.Event())
    wav: Path | None = None
    transcript_id: str | None = None
    with SessionLocal() as db:
        job = db.get(TranscriptionJob, job_id)
        if job is None:
            return
        if cancel.is_set() or job.status == "cancelled":
            job.status = "cancelled"
            db.commit()
            _publish(job)
            return
        video = db.get(Video, job.video_id)
        try:
            if video is None:
                raise tx.TranscriptionError("Video tidak ditemukan")
            limits = rs.get_limits(db)
            job.status, job.progress = "running", 0.0
            db.commit()
            _publish(job)

            transcriber = tx.make_transcriber(job.model, limits["compute_mode"], limits["vram_reserve_mb"])
            job.device = transcriber.device
            db.commit()

            wav = s.cache_dir / f"asr-{job.id}.wav"
            tx.extract_audio(Path(video.source_path), wav, job.audio_track, cancel)
            if cancel.is_set():
                raise tx.Cancelled()

            res = transcriber.transcribe(wav, None if job.language == "auto" else job.language)
            duration = res.duration or video.duration
            tr = Transcript(video_id=video.id, language=res.language, model=job.model, duration=duration,
                            language_probability=res.language_probability, source="whisper", full_text="")
            db.add(tr)
            db.flush()
            transcript_id = tr.id
            texts: list[str] = []
            batch = 0
            last_pub = 0.0
            for seg in tx.split_sentences(res.segments):
                if cancel.is_set():
                    raise tx.Cancelled()
                if not seg.text.strip():
                    continue
                db.add(TranscriptSegment(transcript_id=tr.id, start_time=seg.start, end_time=seg.end, text=seg.text,
                                         word_timestamps_json=[w.as_dict() for w in seg.words] or None))
                texts.append(seg.text)
                batch += 1
                job.progress = min(0.99, seg.end / duration) if duration else 0.0
                if batch >= 50:
                    db.commit()
                    batch = 0
                if job.progress - last_pub >= 0.01:
                    last_pub = job.progress
                    _publish(job)
            tr.full_text = " ".join(texts)
            job.status, job.progress, job.transcript_id = "done", 1.0, tr.id
            db.commit()
            _publish(job)
            hub.publish("data.changed", {"kind": "transcript", "video_id": video.id})
        except tx.Cancelled:
            db.rollback()
            _drop_partial(db, transcript_id)
            job = db.get(TranscriptionJob, job_id)
            job.status = "cancelled"
            db.commit()
            _publish(job)
        except Exception as e:  # noqa: BLE001
            db.rollback()
            _drop_partial(db, transcript_id)
            job = db.get(TranscriptionJob, job_id)
            job.status = "failed"
            job.error_message = (str(e) if isinstance(e, (tx.TranscriptionError, MemoryError)) else f"{type(e).__name__}: {e}")[:500]
            log.warning("Transkripsi %s gagal: %s", job_id, type(e).__name__)
            db.commit()
            _publish(job)
        finally:
            if wav is not None:
                wav.unlink(missing_ok=True)


def _drop_partial(db, transcript_id: str | None) -> None:
    """Transkrip yang tidak selesai dibuang agar tidak ada data setengah jadi."""
    if transcript_id:
        tr = db.get(Transcript, transcript_id)
        if tr is not None:
            db.delete(tr)
            db.commit()
