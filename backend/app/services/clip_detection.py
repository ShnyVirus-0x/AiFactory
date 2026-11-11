"""Local Ollama analysis for transcript-based short-clip suggestions."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any

import httpx

from ..config import get_settings

WINDOW_SECONDS = 360.0
WINDOW_CHARS = 9000


class ClipDetectionError(Exception):
    pass


@dataclass(frozen=True)
class TranscriptLine:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Candidate:
    start_time: float
    end_time: float
    title: str
    hook: str
    reason: str
    score: int
    category: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "start_time": self.start_time,
            "end_time": self.end_time,
            "title": self.title,
            "hook": self.hook,
            "reason": self.reason,
            "score": self.score,
            "category": self.category,
        }


def _windows(lines: list[TranscriptLine]) -> list[list[TranscriptLine]]:
    windows: list[list[TranscriptLine]] = []
    current: list[TranscriptLine] = []
    chars = 0
    for line in lines:
        text = line.text.strip()
        if not text:
            continue
        line = TranscriptLine(line.start, line.end, text[:2000])
        next_chars = chars + len(line.text)
        if current and (line.end - current[0].start > WINDOW_SECONDS or next_chars > WINDOW_CHARS):
            windows.append(current)
            current, chars = [], 0
        current.append(line)
        chars += len(line.text)
    if current:
        windows.append(current)
    return windows


def _parse_response(content: str, window_start: float, window_end: float, video_duration: float) -> list[Candidate]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ClipDetectionError("Ollama mengembalikan format yang bukan JSON. Coba lagi atau gunakan model yang mendukung keluaran JSON.") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("candidates"), list):
        raise ClipDetectionError("Respons Ollama tidak memiliki daftar candidates yang valid.")

    result: list[Candidate] = []
    for item in payload["candidates"]:
        if not isinstance(item, dict):
            continue
        try:
            start = float(item["start_time"])
            end = float(item["end_time"])
            score = int(item["score"])
            title = str(item["title"]).strip()[:200]
            hook = str(item.get("hook", "")).strip()[:500]
            reason = str(item.get("reason", "")).strip()[:1000]
            category = str(item.get("category", "highlight")).strip()[:60] or "highlight"
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if not math.isfinite(start) or not math.isfinite(end):
            continue
        if start < window_start - 1 or end > window_end + 1:
            continue
        start = round(max(window_start, start), 2)
        end = round(min(window_end, video_duration, end), 2)
        if end - start < 5 or end - start > 120 or not title:
            continue
        result.append(Candidate(start, end, title, hook, reason, max(0, min(100, score)), category))
    return result


def _request_window(lines: list[TranscriptLine], video_duration: float, wanted: int) -> list[Candidate]:
    settings = get_settings()
    start = max(0.0, lines[0].start)
    end = min(video_duration, lines[-1].end)
    transcript = "\n".join(f"[{line.start:.2f}-{line.end:.2f}] {line.text}" for line in lines)
    prompt = (
        "Pilih momen yang paling menarik untuk dijadikan klip video pendek dari transkrip berikut. "
        "Gunakan hanya bukti yang ada di transkrip; jangan mengarang kejadian atau konteks visual. "
        "Cari cerita yang utuh, hook kuat, punchline, insight, emosi, atau momen mengejutkan. "
        "Rentang klip harus 5 sampai 120 detik, berada di dalam jendela transkrip, dan sebisa mungkin "
        "mulai/berakhir pada batas kalimat. Berikan skor 0-100 berdasarkan kekuatan hook, keutuhan konteks, "
        "dan potensi menarik perhatian. Kembalikan paling banyak "
        f"{wanted} kandidat sebagai JSON saja dengan bentuk "
        '{"candidates":[{"start_time":angka,"end_time":angka,"title":"judul singkat","hook":"hook berdasarkan ucapan","reason":"alasan","score":0,"category":"insight|story|humor|reaction|tip|highlight"}]}. '
        f"Waktu yang diberikan adalah detik absolut video. Jendela valid {start:.2f} sampai {end:.2f} detik.\n\n"
        f"TRANSKRIP:\n{transcript}"
    )
    try:
        response = httpx.post(
            f"{settings.ollama_url.rstrip('/')}/api/chat",
            json={
                "model": settings.ollama_model,
                "messages": [
                    {"role": "system", "content": "Kamu editor video pendek yang teliti. Analisis hanya teks transkrip dan kembalikan JSON valid."},
                    {"role": "user", "content": prompt},
                ],
                "format": "json",
                "stream": False,
                "options": {"temperature": 0.2},
            },
            timeout=httpx.Timeout(connect=5.0, read=240.0, write=10.0, pool=5.0),
        )
        response.raise_for_status()
        content = response.json().get("message", {}).get("content", "")
    except httpx.TimeoutException as exc:
        raise ClipDetectionError("Analisis Ollama terlalu lama. Coba lagi atau gunakan video/transkrip yang lebih pendek.") from exc
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise ClipDetectionError(f"Model Ollama '{settings.ollama_model}' belum tersedia. Unduh dengan `ollama pull {settings.ollama_model}`.") from exc
        raise ClipDetectionError(f"Ollama menolak permintaan analisis (HTTP {exc.response.status_code}).") from exc
    except httpx.RequestError as exc:
        raise ClipDetectionError("Ollama tidak dapat dihubungi. Pastikan Ollama berjalan di perangkat ini.") from exc
    except (ValueError, AttributeError) as exc:
        raise ClipDetectionError("Respons Ollama tidak valid.") from exc

    return _parse_response(content, start, end, video_duration)


def suggest_candidates(lines: list[TranscriptLine], video_duration: float, max_candidates: int = 12) -> list[Candidate]:
    """Analyze the latest transcript in bounded local Ollama requests and rank suggestions."""
    windows = _windows(lines)
    if not windows:
        raise ClipDetectionError("Transkrip belum memiliki teks yang dapat dianalisis.")
    per_window = max(1, (max_candidates + len(windows) - 1) // len(windows))
    candidates: list[Candidate] = []
    for window in windows:
        candidates.extend(_request_window(window, video_duration, per_window))
    candidates.sort(key=lambda c: (-c.score, c.start_time))

    unique: list[Candidate] = []
    for candidate in candidates:
        overlaps = any(
            min(candidate.end_time, kept.end_time) - max(candidate.start_time, kept.start_time)
            > 0.6 * min(candidate.end_time - candidate.start_time, kept.end_time - kept.start_time)
            for kept in unique
        )
        if not overlaps:
            unique.append(candidate)
        if len(unique) >= max_candidates:
            break
    return sorted(unique, key=lambda c: c.start_time)
