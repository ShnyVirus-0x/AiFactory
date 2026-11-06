"""Utilitas file yang aman: sanitasi nama, anti path traversal, hash streaming."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path

_BAD = re.compile(r"[^\w\s.\-()\[\]]", re.UNICODE)
_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def sanitize_filename(name: str, default: str = "video", max_len: int = 150) -> str:
    """Bersihkan nama file dari path, karakter kontrol, dan nama yang dicadangkan Windows."""
    name = unicodedata.normalize("NFKC", name or "")
    name = name.replace("\\", "/").split("/")[-1]  # buang komponen direktori
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    stem = _BAD.sub("", stem).strip(" .")
    stem = re.sub(r"\s+", " ", stem)
    if not stem or stem.upper() in _WINDOWS_RESERVED:
        stem = default
    ext = re.sub(r"[^A-Za-z0-9]", "", ext).lower()[:8]
    out = stem[: max_len - (len(ext) + 1 if ext else 0)]
    return f"{out}.{ext}" if ext else out


def safe_join(base: Path, *parts: str) -> Path:
    """Gabungkan path dan pastikan hasilnya tetap berada di dalam ``base`` (cegah path traversal)."""
    base_r = base.resolve()
    target = base_r.joinpath(*parts).resolve()
    if target != base_r and base_r not in target.parents:
        raise ValueError("Path di luar direktori yang diizinkan")
    return target


def is_within(path: Path, base: Path) -> bool:
    try:
        p, b = path.resolve(), base.resolve()
    except OSError:
        return False
    return p == b or b in p.parents


def sha256_stream_copy(src, dest: Path, max_bytes: int, chunk: int = 1024 * 1024) -> tuple[int, str]:
    """Salin stream ke ``dest`` per chunk sambil menghitung SHA-256. Batalkan bila melebihi ``max_bytes``."""
    h = hashlib.sha256()
    total = 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(dest, "wb") as out:
            while True:
                buf = src.read(chunk)
                if not buf:
                    break
                total += len(buf)
                if total > max_bytes:
                    raise ValueError(f"File melebihi batas {max_bytes // (1024 * 1024)} MB")
                h.update(buf)
                out.write(buf)
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    if total == 0:
        dest.unlink(missing_ok=True)
        raise ValueError("File kosong")
    return total, h.hexdigest()
