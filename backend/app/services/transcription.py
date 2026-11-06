"""Mesin transkripsi: ekstraksi audio, adaptor faster-whisper, dan pemisahan kalimat berbasis timestamp kata."""
from __future__ import annotations

import logging
import re
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Protocol

from ..config import get_settings
from . import whisper_models
from .model_manager import manager, resolve_device

log = logging.getLogger("asf.transcription")

SENTENCE_END = re.compile(r"[.!?…。？！]['\"”’)]*$")
CLAUSE_END = re.compile(r"[,;:，]['\"”’)]*$")


class TranscriptionError(Exception):
    pass


class Cancelled(Exception):
    pass


@dataclass
class Word:
    start: float
    end: float
    word: str
    probability: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"start": round(self.start, 3), "end": round(self.end, 3), "word": self.word,
                "probability": None if self.probability is None else round(self.probability, 3)}


@dataclass
class Seg:
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)


@dataclass
class TranscribeResult:
    language: str
    language_probability: float | None
    duration: float
    segments: Iterator[Seg]


class Transcriber(Protocol):
    device: str
    model_name: str

    def transcribe(self, audio: Path, language: str | None) -> TranscribeResult: ...


# --------------------------------------------------------------------------
# Audio
# --------------------------------------------------------------------------
def extract_audio(video: Path, out_wav: Path, track: int = 0, cancel: threading.Event | None = None) -> None:
    """Ekstrak trek audio ke WAV mono 16 kHz (format yang dipakai Whisper). Streaming ke disk: aman untuk video panjang."""
    s = get_settings()
    cmd = [s.ffmpeg_bin, "-nostdin", "-v", "error", "-y", "-i", str(video), "-map", f"0:a:{int(track)}", "-vn",
           "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(out_wav)]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)  # noqa: S603
    except FileNotFoundError as e:
        raise TranscriptionError("FFmpeg tidak ditemukan") from e
    while True:
        try:
            _, err = proc.communicate(timeout=0.5)
            break
        except subprocess.TimeoutExpired:
            if cancel is not None and cancel.is_set():
                proc.kill()
                proc.communicate()
                out_wav.unlink(missing_ok=True)
                raise Cancelled() from None
    if proc.returncode != 0:
        out_wav.unlink(missing_ok=True)
        raise TranscriptionError(f"Gagal mengekstrak audio: {(err or '').strip()[-300:]}")


# --------------------------------------------------------------------------
# faster-whisper
# --------------------------------------------------------------------------
class FasterWhisperTranscriber:
    def __init__(self, model_name: str, device: str, vram_reserve_mb: int, model_factory: Callable[..., Any] | None = None):
        if model_name not in whisper_models.CATALOG:
            raise TranscriptionError(f"Model '{model_name}' tidak dikenal")
        if not whisper_models.is_installed(model_name):
            raise TranscriptionError(f"Model Whisper '{model_name}' belum diunduh. Unduh dari halaman Transkripsi (dengan persetujuan ukuran).")
        self.model_name, self.device, self._reserve = model_name, device, vram_reserve_mb
        self._factory = model_factory

    def _model(self):
        spec = whisper_models.CATALOG[self.model_name]
        path = str(whisper_models.model_dir(self.model_name))
        compute = "float16" if self.device == "cuda" else "int8"

        def make():
            if self._factory is not None:
                return self._factory(path, device=self.device, compute_type=compute)
            from faster_whisper import WhisperModel

            return WhisperModel(path, device=self.device, compute_type=compute)

        def unload(m: Any) -> None:
            inner = getattr(m, "model", None)
            if inner is not None and hasattr(inner, "unload_model"):
                try:
                    inner.unload_model()
                except Exception:  # noqa: BLE001
                    pass

        return manager.acquire(f"whisper:{self.model_name}", device=self.device, est_vram_mb=spec.vram_mb,
                               vram_reserve_mb=self._reserve, factory=make, unloader=unload).obj

    def transcribe(self, audio: Path, language: str | None) -> TranscribeResult:
        model = self._model()
        segs, info = model.transcribe(str(audio), language=language, word_timestamps=True, vad_filter=True,
                                      condition_on_previous_text=False, beam_size=5)

        def gen() -> Iterator[Seg]:
            for s in segs:  # generator lazy: memori konstan untuk video panjang
                words = [Word(float(w.start), float(w.end), w.word, getattr(w, "probability", None)) for w in (s.words or [])]
                yield Seg(float(s.start), float(s.end), (s.text or "").strip(), words)

        return TranscribeResult(language=info.language, language_probability=getattr(info, "language_probability", None),
                                duration=float(getattr(info, "duration", 0.0) or 0.0), segments=gen())


def make_transcriber(model_name: str, compute_mode: str, vram_reserve_mb: int) -> Transcriber:
    """Titik injeksi: tes dapat mengganti fungsi ini. Pada penggunaan nyata selalu faster-whisper."""
    device, reason = resolve_device(compute_mode)
    if device == "unavailable":
        raise TranscriptionError(f"Mode GPU dipilih tetapi tidak tersedia: {reason}")
    if device == "cpu" and reason:
        log.info("Transkripsi memakai CPU: %s", reason)
    return FasterWhisperTranscriber(model_name, device, vram_reserve_mb)


# --------------------------------------------------------------------------
# Pemisahan kalimat
# --------------------------------------------------------------------------
def _join(words: list[Word]) -> str:
    return "".join(w.word if w.word.startswith(" ") or i == 0 else " " + w.word for i, w in enumerate(words)).strip()


def split_sentences(segments: Iterable[Seg], max_duration: float = 12.0, max_words: int = 28, pause: float = 1.0) -> Iterator[Seg]:
    """Pecah segmen Whisper menjadi kalimat memakai timestamp kata.

    Aturan: potong setelah tanda akhir kalimat; potong paksa bila ada jeda >= `pause` detik, atau bila terlalu
    panjang (durasi/jumlah kata) -- pada koma terakhir bila ada, selain itu pada kata terakhir. Segmen tanpa
    timestamp kata diteruskan apa adanya.
    """
    for seg in segments:
        words = seg.words
        if not words:
            if seg.text.strip():
                yield seg
            continue
        cur: list[Word] = []
        for i, w in enumerate(words):
            cur.append(w)
            nxt = words[i + 1] if i + 1 < len(words) else None
            end_now = bool(SENTENCE_END.search(w.word.strip()))
            if nxt is not None and not end_now:
                if nxt.start - w.end >= pause:
                    end_now = True
                elif (w.end - cur[0].start) >= max_duration or len(cur) >= max_words:
                    comma = next((k for k in range(len(cur) - 1, 0, -1) if CLAUSE_END.search(cur[k].word.strip())), None)
                    if comma is not None and comma >= len(cur) // 2:
                        head, tail = cur[: comma + 1], cur[comma + 1:]
                        yield Seg(head[0].start, head[-1].end, _join(head), head)
                        cur = tail
                    end_now = bool(cur) and (len(cur) >= max_words or (cur[-1].end - cur[0].start) >= max_duration)
            if end_now and cur:
                yield Seg(cur[0].start, cur[-1].end, _join(cur), cur)
                cur = []
        if cur:
            yield Seg(cur[0].start, cur[-1].end, _join(cur), cur)


def validate_timestamps(segs: list[Seg], duration: float, tol: float = 0.5) -> list[str]:
    """Kembalikan daftar masalah timestamp (kosong = sehat). Dipakai tes dan diagnostik."""
    issues: list[str] = []
    prev_end = 0.0
    for i, s in enumerate(segs):
        if s.end < s.start:
            issues.append(f"segmen {i}: end < start")
        if s.start < prev_end - 0.25:
            issues.append(f"segmen {i}: tumpang tindih dengan segmen sebelumnya")
        if duration and s.end > duration + tol:
            issues.append(f"segmen {i}: melewati durasi video")
        for w in s.words:
            if w.end < w.start or w.start < s.start - 0.05 or w.end > s.end + 0.05:
                issues.append(f"segmen {i}: kata '{w.word}' di luar segmen")
                break
        prev_end = max(prev_end, s.end)
    return issues
