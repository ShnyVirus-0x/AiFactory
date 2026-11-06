"""Deteksi wajah lokal (OpenCV Haar cascade). Mendukung banyak wajah per frame.

Keterbatasan yang jujur: Haar cascade hanya andal untuk wajah frontal; wajah menyamping/tertutup bisa terlewat.
Model deteksi yang lebih kuat (mis. YuNet) dapat ditambahkan nanti tanpa mengubah antarmuka.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("asf.face")


class FaceDetectionUnavailable(Exception):
    pass


@dataclass
class FaceBox:
    cx: float  # pusat x (0..1 dari lebar frame)
    cy: float
    w: float  # lebar relatif
    h: float

    @property
    def area(self) -> float:
        return self.w * self.h


@dataclass
class FaceSample:
    t: float  # detik relatif awal klip
    faces: list[FaceBox] = field(default_factory=list)


def _cascade_path() -> Path:
    try:
        import cv2
    except ImportError as e:
        raise FaceDetectionUnavailable("OpenCV belum terpasang") from e
    candidates = []
    data = getattr(cv2, "data", None)
    if data is not None:
        candidates.append(Path(data.haarcascades) / "haarcascade_frontalface_default.xml")
    candidates.append(Path(__file__).resolve().parents[1] / "assets" / "haarcascade_frontalface_default.xml")
    for c in candidates:
        if c.is_file():
            return c
    raise FaceDetectionUnavailable("File cascade wajah tidak ditemukan. Pasang opencv-python-headless 4.x (build 5.x tidak menyertakannya).")


def detector_status() -> dict:
    try:
        return {"available": True, "reason": None, "detector": "opencv-haar", "path": str(_cascade_path())}
    except FaceDetectionUnavailable as e:
        return {"available": False, "reason": str(e), "detector": "opencv-haar", "path": None}


def detect_faces(video: Path, start: float, end: float, sample_fps: float = 2.0, max_samples: int = 600) -> list[FaceSample]:
    """Ambil sampel frame pada rentang [start, end] dan deteksi wajah. Waktu sampel relatif terhadap `start`."""
    import cv2

    cascade = cv2.CascadeClassifier(str(_cascade_path()))
    if cascade.empty():
        raise FaceDetectionUnavailable("Cascade wajah gagal dimuat")
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise FaceDetectionUnavailable("Video tidak dapat dibuka oleh OpenCV")
    out: list[FaceSample] = []
    try:
        dur = max(0.0, end - start)
        step = max(1.0 / sample_fps, dur / max_samples) if dur else 1.0
        t = 0.0
        while t <= dur + 1e-6:
            cap.set(cv2.CAP_PROP_POS_MSEC, (start + t) * 1000)
            ok, frame = cap.read()
            if not ok:
                break
            h, w = frame.shape[:2]
            scale = 640 / w if w > 640 else 1.0
            small = cv2.resize(frame, (int(w * scale), int(h * scale))) if scale != 1.0 else frame
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            sh, sw = gray.shape[:2]
            min_px = (max(24, int(sw * 0.04)),) * 2
            found = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=min_px)
            if len(found) == 0:  # pencahayaan buruk: coba sekali lagi dengan ekualisasi histogram
                found = cascade.detectMultiScale(cv2.equalizeHist(gray), scaleFactor=1.1, minNeighbors=4, minSize=min_px)
            out.append(FaceSample(t, [FaceBox((x + fw / 2) / sw, (y + fh / 2) / sh, fw / sw, fh / sh) for (x, y, fw, fh) in found]))
            t += step
    finally:
        cap.release()
    return out
