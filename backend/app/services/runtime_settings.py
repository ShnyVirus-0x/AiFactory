"""Batas sumber daya yang dapat diubah saat aplikasi berjalan. Disimpan di tabel `settings` (bukan hanya .env)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Setting
from ..utils.errors import AppError

COMPUTE_MODES = ("auto", "gpu", "cpu")

# key -> (min, max)
INT_LIMITS: dict[str, tuple[int, int]] = {
    "ai_workers": (1, 4),
    "gpu_render_workers": (1, 4),
    "cpu_workers": (1, 16),
    "vram_reserve_mb": (0, 24576),
}


def defaults() -> dict[str, Any]:
    s = get_settings()
    return {"ai_workers": s.ai_workers, "gpu_render_workers": s.gpu_render_workers, "cpu_workers": s.cpu_workers,
            "vram_reserve_mb": s.vram_reserve_mb, "compute_mode": "auto"}


def get_limits(db: Session) -> dict[str, Any]:
    out = defaults()
    rows = {r.setting_key: r.setting_value for r in db.scalars(select(Setting).where(Setting.setting_key.like("limits.%")))}
    for k in out:
        raw = rows.get(f"limits.{k}")
        if raw is None:
            continue
        if k == "compute_mode":
            if raw in COMPUTE_MODES:
                out[k] = raw
        else:
            try:
                lo, hi = INT_LIMITS[k]
                out[k] = min(hi, max(lo, int(raw)))
            except ValueError:
                pass
    return out


def set_limits(db: Session, patch: dict[str, Any]) -> dict[str, Any]:
    for k, v in patch.items():
        if v is None:
            continue
        if k == "compute_mode":
            if v not in COMPUTE_MODES:
                raise AppError(422, "validation_error", f"compute_mode harus salah satu dari {COMPUTE_MODES}")
        elif k in INT_LIMITS:
            lo, hi = INT_LIMITS[k]
            if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
                raise AppError(422, "validation_error", f"{k} harus bilangan bulat {lo}–{hi}")
        else:
            continue
        row = db.scalar(select(Setting).where(Setting.setting_key == f"limits.{k}"))
        if row:
            row.setting_value = str(v)
        else:
            db.add(Setting(setting_key=f"limits.{k}", setting_value=str(v)))
    db.commit()
    return get_limits(db)
