"""Ekspor transkrip ke SRT / VTT / TXT (fungsi murni)."""
from __future__ import annotations

import re
from typing import Iterable, Protocol


class SegLike(Protocol):
    start_time: float
    end_time: float
    text: str


def _ts(t: float, sep: str) -> str:
    ms = int(round(max(0.0, t) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def wrap(text: str, max_chars: int = 42, max_lines: int = 2) -> str:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_chars:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:  # jangan buang teks: gabungkan sisanya ke baris terakhir
        lines = lines[: max_lines - 1] + [" ".join(lines[max_lines - 1:])]
    return "\n".join(lines)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("-->", "→")).strip()


def to_srt(segments: Iterable[SegLike], max_chars: int = 42) -> str:
    out = []
    i = 0
    for s in segments:
        text = _clean(s.text)
        if not text:
            continue
        i += 1
        out.append(f"{i}\n{_ts(s.start_time, ',')} --> {_ts(s.end_time, ',')}\n{wrap(text, max_chars)}\n")
    return "\n".join(out)


def to_vtt(segments: Iterable[SegLike], max_chars: int = 42) -> str:
    out = ["WEBVTT\n"]
    for s in segments:
        text = _clean(s.text)
        if not text:
            continue
        out.append(f"{_ts(s.start_time, '.')} --> {_ts(s.end_time, '.')}\n{wrap(text, max_chars)}\n")
    return "\n".join(out)


def to_txt(segments: Iterable[SegLike]) -> str:
    return "\n".join(t for t in (_clean(s.text) for s in segments) if t) + "\n"
