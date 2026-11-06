"""Operasi edit transkrip: ubah teks/waktu, pisah, gabung, hapus, cari-ganti. Timing kata hasil edit ditandai perkiraan."""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Transcript, TranscriptSegment
from ..utils.errors import AppError, not_found


def estimate_words(text: str, start: float, end: float) -> list[dict[str, Any]]:
    """Bagi waktu segmen ke kata secara proporsional panjang karakter. Ini PERKIRAAN, bukan hasil Whisper."""
    toks = text.split()
    if not toks:
        return []
    total = sum(len(t) for t in toks) or 1
    span = max(end - start, 0.01)
    out, t = [], start
    for tok in toks:
        d = span * len(tok) / total
        out.append({"start": round(t, 3), "end": round(t + d, 3), "word": tok, "probability": None})
        t += d
    return out


def _get_seg(db: Session, seg_id: int) -> TranscriptSegment:
    seg = db.get(TranscriptSegment, seg_id)
    if not seg:
        raise not_found("Segmen")
    return seg


def rebuild_full_text(db: Session, tr: Transcript) -> None:
    segs = db.scalars(select(TranscriptSegment).where(TranscriptSegment.transcript_id == tr.id).order_by(TranscriptSegment.start_time, TranscriptSegment.id)).all()
    tr.full_text = " ".join(s.text.strip() for s in segs if s.text.strip())


def update_segment(db: Session, seg_id: int, text: str | None, start: float | None, end: float | None, video_duration: float) -> TranscriptSegment:
    seg = _get_seg(db, seg_id)
    ns = seg.start_time if start is None else start
    ne = seg.end_time if end is None else end
    if ns < 0 or ne <= ns:
        raise AppError(422, "validation_error", "Waktu tidak valid: mulai harus ≥ 0 dan lebih kecil dari selesai")
    if video_duration and ne > video_duration + 0.5:
        raise AppError(422, "validation_error", f"Waktu selesai melebihi durasi video ({video_duration:.1f} dtk)")
    text_changed = text is not None and text.strip() != seg.text.strip()
    time_changed = (ns, ne) != (seg.start_time, seg.end_time)
    if text is not None:
        seg.text = text.strip()
    seg.start_time, seg.end_time = ns, ne
    if text_changed:
        seg.words_estimated, seg.edited = True, True
        seg.word_timestamps_json = estimate_words(seg.text, ns, ne)
    elif time_changed:
        seg.edited = True
        if seg.word_timestamps_json:  # skala ulang timing kata ke rentang baru (perkiraan)
            ws = seg.word_timestamps_json
            os_, oe = ws[0]["start"], ws[-1]["end"]
            f = (ne - ns) / max(oe - os_, 0.01)
            seg.word_timestamps_json = [{**w, "start": round(ns + (w["start"] - os_) * f, 3), "end": round(ns + (w["end"] - os_) * f, 3)} for w in ws]
            seg.words_estimated = True
    tr = db.get(Transcript, seg.transcript_id)
    rebuild_full_text(db, tr)
    db.commit()
    return seg


def split_segment(db: Session, seg_id: int, word_index: int) -> tuple[TranscriptSegment, TranscriptSegment]:
    """Pisah segmen setelah kata ke-`word_index` (0-based, kata tersebut tetap di bagian pertama)."""
    seg = _get_seg(db, seg_id)
    words = seg.word_timestamps_json or estimate_words(seg.text, seg.start_time, seg.end_time)
    if not 0 <= word_index < len(words) - 1:
        raise AppError(422, "validation_error", f"word_index harus 0–{len(words) - 2}")
    a, b = words[: word_index + 1], words[word_index + 1:]
    t_split = (a[-1]["end"] + b[0]["start"]) / 2
    new = TranscriptSegment(transcript_id=seg.transcript_id, start_time=t_split, end_time=seg.end_time,
                            text=" ".join(w["word"].strip() for w in b), word_timestamps_json=b, edited=True, words_estimated=seg.words_estimated)
    seg.end_time, seg.text, seg.word_timestamps_json, seg.edited = t_split, " ".join(w["word"].strip() for w in a), a, True
    db.add(new)
    db.commit()
    return seg, new


def merge_with_next(db: Session, seg_id: int) -> TranscriptSegment:
    seg = _get_seg(db, seg_id)
    nxt = db.scalar(select(TranscriptSegment).where(TranscriptSegment.transcript_id == seg.transcript_id, TranscriptSegment.start_time >= seg.start_time,
                                                    TranscriptSegment.id != seg.id).order_by(TranscriptSegment.start_time, TranscriptSegment.id))
    if not nxt:
        raise AppError(409, "no_next_segment", "Tidak ada segmen berikutnya untuk digabung")
    seg.text = f"{seg.text.strip()} {nxt.text.strip()}".strip()
    seg.end_time = max(seg.end_time, nxt.end_time)
    seg.word_timestamps_json = (seg.word_timestamps_json or []) + (nxt.word_timestamps_json or [])
    seg.words_estimated = seg.words_estimated or nxt.words_estimated
    seg.edited = True
    db.delete(nxt)
    db.commit()
    return seg


def delete_segment(db: Session, seg_id: int) -> None:
    seg = _get_seg(db, seg_id)
    tr = db.get(Transcript, seg.transcript_id)
    db.delete(seg)
    db.flush()
    rebuild_full_text(db, tr)
    db.commit()


def replace_all(db: Session, tr: Transcript, find: str, repl: str, case_sensitive: bool = False, whole_word: bool = False) -> int:
    if not find:
        raise AppError(422, "validation_error", "Teks yang dicari tidak boleh kosong")
    pat = re.compile((r"\b%s\b" if whole_word else "%s") % re.escape(find), 0 if case_sensitive else re.IGNORECASE)
    changed = 0
    for seg in db.scalars(select(TranscriptSegment).where(TranscriptSegment.transcript_id == tr.id)):
        new, n = pat.subn(lambda _m: repl, seg.text)
        if n:
            seg.text, seg.edited = new, True
            if seg.word_timestamps_json:
                # ganti per kata bila memungkinkan agar timing asli tetap; jika tidak, perkirakan ulang
                new_words = [pat.sub(lambda _m: repl, w["word"]) for w in seg.word_timestamps_json]
                if " ".join(x.strip() for x in new_words).split() == new.split():
                    seg.word_timestamps_json = [{**w, "word": nw} for w, nw in zip(seg.word_timestamps_json, new_words)]
                else:
                    seg.word_timestamps_json, seg.words_estimated = estimate_words(new, seg.start_time, seg.end_time), True
            changed += n
    rebuild_full_text(db, tr)
    db.commit()
    return changed
