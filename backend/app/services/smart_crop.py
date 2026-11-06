"""Smart crop: pilih pembicara dari wajah terdeteksi, haluskan pergerakan kamera virtual, hindari gerak yang tidak perlu."""
from __future__ import annotations

from dataclasses import dataclass

from .face_detection import FaceSample

Track = list[tuple[float, float]]  # (waktu relatif klip, posisi x pusat crop 0..1)


def smooth_track(raw: list[tuple[float, float | None]], deadzone: float = 0.04, alpha: float = 0.35) -> Track:
    """Isi celah deteksi, median-filter, EMA, dan dead-zone supaya crop tidak bergetar."""
    if not raw:
        return []
    times = [t for t, _ in raw]
    vals: list[float | None] = [v for _, v in raw]
    first = next((v for v in vals if v is not None), None)
    if first is None:
        return []
    last = first
    for i, v in enumerate(vals):
        if v is None:
            vals[i] = last
        else:
            last = v
    filled = [float(v) for v in vals]  # type: ignore[arg-type]
    med = [sorted(filled[max(0, i - 2): i + 3])[len(filled[max(0, i - 2): i + 3]) // 2] for i in range(len(filled))]
    out: list[float] = []
    cur = med[0]
    for v in med:
        if abs(v - cur) > deadzone:
            cur = cur + alpha * (v - cur)
        out.append(cur)
    return list(zip(times, [min(1.0, max(0.0, x)) for x in out]))


def pick_speaker_positions(samples: list[FaceSample], min_rel_area: float = 0.5) -> list[tuple[float, float | None]]:
    """Untuk tiap sampel pilih satu wajah. Awal: wajah terbesar. Selanjutnya: wajah yang paling dekat dengan posisi
    sebelumnya (kontinuitas) di antara wajah yang ukurannya wajar, agar kamera tidak melompat antar-orang tanpa alasan."""
    out: list[tuple[float, float | None]] = []
    prev: float | None = None
    for s in samples:
        if not s.faces:
            out.append((s.t, None))
            continue
        biggest = max(f.area for f in s.faces)
        cands = [f for f in s.faces if f.area >= biggest * min_rel_area]
        chosen = max(cands, key=lambda f: f.area) if prev is None else min(cands, key=lambda f: abs(f.cx - prev))
        prev = chosen.cx
        out.append((s.t, chosen.cx))
    return out


@dataclass
class CropAnalysis:
    track: Track | None  # None -> pakai center crop
    samples: int
    frames_with_face: int
    max_faces: int
    travel: float  # total pergeseran x yang dihaluskan (0..1)
    static: bool  # kamera dibuat diam karena gerak kecil
    note: str


def build_crop_track(samples: list[FaceSample], min_face_ratio: float = 0.15, static_travel: float = 0.06) -> CropAnalysis:
    n = len(samples)
    with_face = sum(1 for s in samples if s.faces)
    mx = max((len(s.faces) for s in samples), default=0)
    if n == 0 or with_face == 0:
        return CropAnalysis(None, n, with_face, mx, 0.0, False, "Tidak ada wajah terdeteksi; memakai center crop")
    if with_face / n < min_face_ratio:
        return CropAnalysis(None, n, with_face, mx, 0.0, False, f"Wajah hanya terdeteksi di {with_face}/{n} sampel; memakai center crop")
    track = smooth_track(pick_speaker_positions(samples))
    xs = [x for _, x in track]
    travel = sum(abs(b - a) for a, b in zip(xs, xs[1:]))
    if travel < static_travel:  # gerak kecil: kunci kamera di posisi median agar tidak ada gerak yang tidak perlu
        med = sorted(xs)[len(xs) // 2]
        return CropAnalysis([(0.0, med)], n, with_face, mx, travel, True, "Pembicara hampir diam; kamera dikunci (tanpa gerak)")
    return CropAnalysis(track, n, with_face, mx, travel, False, "Kamera virtual mengikuti pembicara")
