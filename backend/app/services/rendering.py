"""Pembangun command FFmpeg (murni, mudah dites), pemilihan encoder yang JUJUR, runner dengan progres + pembatalan,
dan verifikasi hasil dengan FFprobe. Dipindahkan dari ClipForge dan diadaptasi."""
from __future__ import annotations

import json
import subprocess
import tempfile
import threading
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..schemas.render import RenderSpec
from . import gpu_monitor
from .model_manager import resolve_device  # noqa: F401  (dipakai pemanggil untuk mode komputasi)
from .smart_crop import Track

OUT_W, OUT_H = 1080, 1920


class RenderError(Exception):
    pass


class RenderCancelled(Exception):
    pass


def even(n: float) -> int:
    return max(2, int(n) // 2 * 2)


# ---------------------------------------------------------------- encoder
@lru_cache(maxsize=4)
def _hevc_nvenc_ok(ffmpeg: str) -> bool:
    try:
        r = subprocess.run([ffmpeg, "-hide_banner", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.2", "-c:v", "hevc_nvenc", "-f", "null", "-"],
                           capture_output=True, text=True, timeout=30)
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


@lru_cache(maxsize=4)
def _has_encoder(ffmpeg: str, name: str) -> bool:
    try:
        return name in subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.TimeoutExpired):
        return False


def pick_encoder(codec: str, compute_mode: str) -> tuple[str, bool, str]:
    """Kembalikan (nama_encoder, memakai_gpu, alasan). TIDAK pernah mengklaim GPU bila encoder yang dipakai CPU."""
    ff = get_settings().ffmpeg_bin
    cpu = {"h264": "libx264", "h265": "libx265"}[codec]
    if compute_mode == "cpu":
        return cpu, False, "Mode CPU dipilih pengguna"
    nv = gpu_monitor.nvenc_status()
    gpu_name = {"h264": "h264_nvenc", "h265": "hevc_nvenc"}[codec]
    ok = nv["available"] if codec == "h264" else (nv["available"] and nv["hevc"] and _hevc_nvenc_ok(ff))
    if ok:
        return gpu_name, True, "NVENC lolos uji encode"
    if compute_mode == "gpu":
        raise RenderError(f"Mode GPU dipilih tetapi {gpu_name} tidak tersedia: {nv['reason'] or 'uji encode gagal'}")
    if not _has_encoder(ff, cpu):
        raise RenderError(f"Encoder {cpu} tidak tersedia di build FFmpeg ini")
    return cpu, False, nv["reason"] or "NVENC tidak tersedia"


def encoder_args(encoder: str, crf: int) -> list[str]:
    if encoder == "h264_nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", str(crf + 1), "-b:v", "0", "-profile:v", "high"]
    if encoder == "hevc_nvenc":
        return ["-c:v", "hevc_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", str(crf + 1), "-b:v", "0", "-tag:v", "hvc1"]
    if encoder == "libx265":
        return ["-c:v", "libx265", "-preset", "veryfast", "-crf", str(crf + 2), "-tag:v", "hvc1"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-profile:v", "high"]


# ---------------------------------------------------------------- geometri
def fill_crop_size(src_w: int, src_h: int, aw: float, ah: float) -> tuple[int, int]:
    target = aw / ah
    if src_w / src_h >= target:
        return even(src_h * target), even(src_h)
    return even(src_w), even(src_w / target)


def follow_x_expr(track: Track, src_w: int, crop_w: int, max_points: int = 24) -> str:
    """Ekspresi FFmpeg posisi x crop yang mengikuti wajah (interpolasi linier)."""
    max_x = max(0, src_w - crop_w)
    pts = [(t, min(max_x, max(0.0, cx * src_w - crop_w / 2))) for t, cx in track]
    if len(pts) > max_points:
        idx = sorted({round(i * (len(pts) - 1) / (max_points - 1)) for i in range(max_points)})
        pts = [pts[i] for i in idx]
    if pts[0][0] > 0:
        pts.insert(0, (0.0, pts[0][1]))
    if len(pts) == 1:
        return f"{pts[0][1]:.1f}"
    expr = f"{pts[-1][1]:.1f}"
    for (t0, x0), (t1, x1) in reversed(list(zip(pts, pts[1:]))):
        span = max(t1 - t0, 1e-3)
        expr = f"if(lt(t,{t1:.3f}),{x0:.1f}+({x1 - x0:.1f})*(t-{t0:.3f})/{span:.3f},{expr})"
    return expr


def _x_for(spec: RenderSpec, track: Track | None, src_w: int, cw: int) -> str:
    if src_w <= cw:
        return "0"
    if spec.crop_mode == "manual":
        return f"{min(max(0.0, spec.manual_x * src_w - cw / 2), src_w - cw):.1f}"
    if spec.crop_mode == "face" and track:
        return follow_x_expr(track, src_w, cw)
    return f"{max(0, (src_w - cw) // 2)}"


def _cam_px(spec: RenderSpec, W: int, H: int) -> tuple[int, int, int, int]:
    r = spec.cam_rect
    cw, ch = min(even(W * r.w), even(W)), min(even(H * r.h), even(H))
    return cw, ch, min(max(0, even(W * r.x)), W - cw), min(max(0, even(H * r.y)), H - ch)


def escape_filter_path(p: str) -> str:
    return p.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def build_filter_graph(spec: RenderSpec, src_w: int, src_h: int, track: Track | None, ass_name: str | None) -> str:
    W, H = src_w, src_h
    parts: list[str] = []
    if spec.layout == "fill":
        cw, ch = fill_crop_size(W, H, 9, 16)
        parts.append(f"[0:v]crop=w={cw}:h={ch}:x='{_x_for(spec, track, W, cw)}':y={max(0, (H - ch) // 2)},scale={OUT_W}:{OUT_H}:flags=lanczos,setsar=1[base]")
    elif spec.layout == "letterbox":
        scale = min(OUT_W / W, OUT_H / H)
        fw, fh = even(W * scale), even(H * scale)
        if spec.background == "blur":
            parts += ["[0:v]split=2[bg][fg]",
                      f"[bg]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,crop={OUT_W}:{OUT_H},boxblur=24:6,eq=brightness=-0.08[bgb]",
                      f"[fg]scale={fw}:{fh}:flags=lanczos[fgs]", "[bgb][fgs]overlay=(W-w)/2:(H-h)/2,setsar=1[base]"]
        else:
            parts.append(f"[0:v]scale={fw}:{fh}:flags=lanczos,pad={OUT_W}:{OUT_H}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1[base]")
    else:  # split: kamera di atas, seluruh frame (mis. gameplay/layar) di bawah
        top_h = even(OUT_H * spec.split_top_ratio)
        bot_h = OUT_H - top_h
        ccw, cch, ccx, ccy = _cam_px(spec, W, H)
        gw, gh = fill_crop_size(W, H, OUT_W, bot_h)
        parts += ["[0:v]split=2[a][b]",
                  f"[a]crop={ccw}:{cch}:{ccx}:{ccy},scale={OUT_W}:{top_h}:force_original_aspect_ratio=increase,crop={OUT_W}:{top_h},setsar=1[top]",
                  f"[b]crop={gw}:{gh}:{max(0, (W - gw) // 2)}:{max(0, (H - gh) // 2)},scale={OUT_W}:{bot_h}:flags=lanczos,setsar=1[bot]",
                  "[top][bot]vstack=inputs=2[base]"]
    tail = "[base]fps=30"
    if ass_name:
        tail += f",ass={ass_name}"
    parts.append(tail + "[v]")
    return ";".join(parts)


def build_command(*, ffmpeg: str, src: Path, out: Path, start: float, end: float, spec: RenderSpec, src_w: int, src_h: int,
                  encoder: str, ass_name: str | None, track: Track | None, has_audio: bool) -> list[str]:
    graph = build_filter_graph(spec, src_w, src_h, track, ass_name)
    cmd = [ffmpeg, "-hide_banner", "-y", "-nostdin", "-ss", f"{start:.3f}", "-i", str(src), "-t", f"{end - start:.3f}",
           "-filter_complex", graph, "-map", "[v]"]
    if has_audio:
        cmd += ["-map", "0:a:0?"]
        if spec.loudnorm:
            cmd += ["-af", "loudnorm=I=-16:TP=-1.5:LRA=11"]
        cmd += ["-c:a", "aac", "-b:a", "160k", "-ar", "48000"]
    cmd += [*encoder_args(encoder, spec.crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(out)]
    return cmd


# ---------------------------------------------------------------- runner
def run_ffmpeg(cmd: list[str], cwd: Path, duration: float, on_progress: Callable[[float], None] | None = None, cancel: threading.Event | None = None) -> None:
    with tempfile.TemporaryFile("w+") as err:
        try:
            proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=err, text=True)  # noqa: S603
        except FileNotFoundError as e:
            raise RenderError("FFmpeg tidak ditemukan") from e
        assert proc.stdout is not None
        for line in proc.stdout:
            if cancel is not None and cancel.is_set():
                proc.kill()
                proc.wait()
                raise RenderCancelled()
            key, _, val = line.strip().partition("=")
            if key in ("out_time_us", "out_time_ms") and on_progress and duration > 0:
                try:
                    on_progress(max(0.0, min(1.0, int(val) / 1_000_000 / duration)))
                except ValueError:
                    pass
        rc = proc.wait()
        if cancel is not None and cancel.is_set():
            raise RenderCancelled()
        if rc != 0:
            err.seek(0)
            raise RenderError(err.read()[-600:].strip() or f"FFmpeg keluar dengan kode {rc}")


def preview_frame(src: Path, start: float, t_rel: float, spec: RenderSpec, src_w: int, src_h: int, track: Track | None, width: int = 540) -> bytes:
    """Satu frame hasil crop/layout (tanpa subtitle) sebagai JPEG. Memakai graf filter yang SAMA dengan render."""
    s = get_settings()
    graph = build_filter_graph(spec, src_w, src_h, track, None).replace("[v]", "[vv]")
    graph += f";[vv]scale={int(width)}:-2[v]"
    cmd = [s.ffmpeg_bin, "-nostdin", "-v", "error", "-ss", f"{start:.3f}", "-i", str(src), "-ss", f"{max(0.0, t_rel):.3f}",
           "-filter_complex", graph, "-map", "[v]", "-frames:v", "1", "-f", "image2pipe", "-c:v", "mjpeg", "-q:v", "4", "-"]
    r = subprocess.run(cmd, capture_output=True, timeout=60)  # noqa: S603
    if r.returncode != 0 or not r.stdout:
        raise RenderError("Gagal membuat pratinjau frame: " + r.stderr.decode(errors="ignore")[-300:])
    return r.stdout


def probe_output(path: Path) -> dict[str, Any]:
    """Verifikasi hasil render dengan FFprobe: trek video/audio, resolusi, fps, durasi, codec."""
    s = get_settings()
    r = subprocess.run([s.ffprobe_bin, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)], capture_output=True, text=True, timeout=60)  # noqa: S603
    if r.returncode != 0:
        raise RenderError("FFprobe gagal membaca hasil render")
    j = json.loads(r.stdout)
    v = next((x for x in j["streams"] if x["codec_type"] == "video"), None)
    a = next((x for x in j["streams"] if x["codec_type"] == "audio"), None)
    if v is None:
        raise RenderError("Hasil render tidak memiliki trek video")
    num, _, den = v.get("avg_frame_rate", "0/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 0.0
    return {"width": v["width"], "height": v["height"], "fps": round(fps, 2), "video_codec": v["codec_name"], "has_audio": a is not None,
            "audio_codec": a["codec_name"] if a else None, "duration": round(float(j["format"].get("duration", 0)), 3), "size": int(j["format"].get("size", 0))}
