"""Fase 4 (awal): face tracking, smart crop, subtitle ASS, renderer. Seluruh tes render memakai FFmpeg/FFprobe/OpenCV NYATA.
Wajah nyata berasal dari gambar 'astronaut' (scikit-image). NVENC TIDAK diuji (sandbox tanpa GPU) -- yang diuji adalah pemilihan
encoder yang jujur (jatuh ke CPU, atau gagal jelas pada mode GPU)."""
import shutil
import subprocess
import threading
import time
from pathlib import Path

import pytest

cv2 = pytest.importorskip("cv2")
skdata = pytest.importorskip("skimage.data")

FFMPEG_OK = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
needs_ffmpeg = pytest.mark.skipif(not FFMPEG_OK, reason="FFmpeg/FFprobe tidak ditemukan di PATH")

from app.schemas.render import CaptionSpec, RenderSpec  # noqa: E402
from app.services import face_detection as fd  # noqa: E402
from app.services import rendering as rd  # noqa: E402
from app.services import smart_crop as sc  # noqa: E402
from app.services import subtitle as sub  # noqa: E402


# ---------------------------------------------------------------- fixture: video dengan wajah nyata bergerak kiri -> kanan
@pytest.fixture(scope="session")
def face_video(tmp_root) -> Path:
    if not FFMPEG_OK:
        pytest.skip("FFmpeg tidak ditemukan di PATH; tes render video dilewati")
    import numpy as np

    img = cv2.cvtColor(skdata.astronaut(), cv2.COLOR_RGB2BGR)  # 512x512; wajah ±(177..272, 66..161)
    def canvas(x0: int):
        c = np.full((720, 1280, 3), 40, np.uint8)
        c[100:612, x0:x0 + 512] = img
        return c
    for name, x0 in (("l", 60), ("r", 700)):
        cv2.imwrite(str(tmp_root / f"face_{name}.png"), canvas(x0))
    out = tmp_root / "face.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-t", "3", "-r", "25", "-i", str(tmp_root / "face_l.png"), "-loop", "1", "-t", "3", "-r", "25",
                    "-i", str(tmp_root / "face_r.png"), "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
                    "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]", "-map", "[v]", "-map", "2:a", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out)], check=True)
    return out


# ---------------------------------------------------------------- unit: crop
def test_geometry_helpers():
    assert rd.fill_crop_size(1920, 1080, 9, 16) == (606, 1080)
    assert rd.fill_crop_size(1080, 1920, 9, 16) == (1080, 1920)
    assert rd.follow_x_expr([(0.0, 0.5)], 1920, 606) == f"{0.5 * 1920 - 303:.1f}"
    e = rd.follow_x_expr([(0, 0.1), (1, 0.9)], 1920, 606)
    assert "if(lt(t,1.000)" in e and e.count("(") == e.count(")")
    assert float(rd.follow_x_expr([(0, 0.0)], 1920, 606)) == 0.0  # dijepit ke tepi


def test_smooth_track_ignores_jitter_and_fills_gaps():
    raw = [(i * 0.5, 0.5 + (0.01 if i % 2 else -0.01)) for i in range(10)]
    tr = sc.smooth_track(raw)
    assert max(x for _, x in tr) - min(x for _, x in tr) < 0.005  # getaran kecil diabaikan (dead-zone)
    gap = sc.smooth_track([(0, None), (1, 0.3), (2, None), (3, 0.3)])
    assert all(abs(x - 0.3) < 1e-9 for _, x in gap)
    assert sc.smooth_track([(0, None), (1, None)]) == []


def F(cx, area=0.01):
    s = area ** 0.5
    return fd.FaceBox(cx, 0.4, s, s)


def test_speaker_continuity_with_two_faces():
    samples = [fd.FaceSample(0, [F(0.25, 0.02), F(0.75, 0.01)]), fd.FaceSample(1, [F(0.26, 0.015), F(0.74, 0.02)]), fd.FaceSample(2, [F(0.27, 0.015), F(0.74, 0.02)])]
    pos = sc.pick_speaker_positions(samples)
    assert [round(x, 2) for _, x in pos] == [0.25, 0.26, 0.27]  # tetap pada orang yang sama walau wajah lain jadi lebih besar


def test_static_camera_when_little_motion_and_fallbacks():
    still = [fd.FaceSample(i * 0.5, [F(0.5 + (0.005 if i % 2 else 0))]) for i in range(8)]
    a = sc.build_crop_track(still)
    assert a.static and a.track and len(a.track) == 1
    moving = [fd.FaceSample(i * 0.5, [F(0.2 if i < 5 else 0.8)]) for i in range(10)]
    b = sc.build_crop_track(moving)
    assert b.track and not b.static and b.travel > 0.3
    assert sc.build_crop_track([fd.FaceSample(0, []), fd.FaceSample(1, [])]).track is None
    assert sc.build_crop_track([]).track is None
    rare = [fd.FaceSample(i, [F(0.5)] if i == 0 else []) for i in range(20)]
    assert sc.build_crop_track(rare).track is None  # terlalu jarang -> center crop


# ---------------------------------------------------------------- real: deteksi wajah
def test_detector_status_available():
    assert fd.detector_status()["available"] is True


def test_real_face_detection_follows_position(face_video):
    samples = fd.detect_faces(face_video, 0.0, 6.0, sample_fps=2.0)
    left = [s.faces[0].cx for s in samples if s.t < 2.5 and s.faces]
    right = [s.faces[0].cx for s in samples if s.t > 3.5 and s.faces]
    assert len(left) >= 4 and len(right) >= 4
    assert all(0.2 < x < 0.45 for x in left), left  # wajah ±(60+224)/1280 = 0.22..0.3
    assert all(0.6 < x < 0.85 for x in right), right
    a = sc.build_crop_track(samples)
    assert a.track and not a.static and a.max_faces >= 1


# ---------------------------------------------------------------- subtitle ASS
SEGS = [{"start": 0.0, "end": 3.0, "text": "Halo semua. Ini uji {\\an8}sisipan [TAWA]", "words": [
    {"start": 0.0, "end": 0.4, "word": "Halo"}, {"start": 0.4, "end": 0.9, "word": "semua."}, {"start": 1.0, "end": 1.4, "word": "Ini"},
    {"start": 1.4, "end": 1.9, "word": "uji"}, {"start": 1.9, "end": 2.4, "word": "{\\an8}sisipan"}, {"start": 2.4, "end": 3.0, "word": "[TAWA]"}]}]


def test_ass_words_timing_and_injection_safe():
    ass = sub.build_ass(SEGS, 0.0, 3.0, CaptionSpec(), None)
    assert ass and "Style: Caption,Arial,84" in ass
    assert "{\\kf40}HALO" in ass and "{\\kf50}SEMUA." in ass  # durasi karaoke per kata (cs)
    assert "\\an8" not in ass and "TAWA" not in ass  # override ASS & tag non-ucapan dibuang
    assert "SISIPAN" in ass


def test_ass_clip_offset_and_empty():
    ass = sub.build_ass(SEGS, 1.0, 3.0, CaptionSpec(preset="clean"), None)
    assert "0:00:00.00" in ass and "Ini" in ass and "Halo" not in ass  # waktu relatif klip; kata sebelum klip tak ikut
    assert sub.build_ass(SEGS, 0, 3, CaptionSpec(enabled=False), None) is None
    assert "Title" in sub.build_ass([], 0, 5, CaptionSpec(), "Judul {x}") and "{x}" not in sub.build_ass([], 0, 5, CaptionSpec(), "Judul {x}")


def test_caption_font_validation():
    with pytest.raises(ValueError):
        CaptionSpec(font="Arial,0,0\nStyle: X")


# ---------------------------------------------------------------- encoder jujur
def test_encoder_selection_is_honest(monkeypatch):
    # Unit test logika pemilihan: ketersediaan encoder CPU di build FFmpeg di-mock agar tidak bergantung pada FFmpeg terpasang.
    monkeypatch.setattr(rd, "_has_encoder", lambda ff, name: True)
    monkeypatch.setattr(rd.gpu_monitor, "nvenc_status", lambda *a, **k: {"available": False, "h264": False, "hevc": False, "reason": "tidak ada GPU"})
    assert rd.pick_encoder("h264", "auto")[:2] == ("libx264", False)
    assert rd.pick_encoder("h264", "cpu")[:2] == ("libx264", False)
    with pytest.raises(rd.RenderError, match="Mode GPU"):
        rd.pick_encoder("h264", "gpu")
    monkeypatch.setattr(rd.gpu_monitor, "nvenc_status", lambda *a, **k: {"available": True, "h264": True, "hevc": False, "reason": None})
    assert rd.pick_encoder("h264", "auto")[:2] == ("h264_nvenc", True)
    assert rd.pick_encoder("h264", "cpu")[:2] == ("libx264", False)  # mode CPU menghormati pilihan pengguna
    assert rd.pick_encoder("h265", "auto")[:2] == ("libx265", False)  # HEVC NVENC tidak ada -> CPU, tidak berpura-pura GPU


@needs_ffmpeg
def test_run_ffmpeg_cancel_is_prompt(tmp_path):
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=60:duration=600", "-c:v", "libx264", "-preset", "veryslow",
           "-progress", "pipe:1", "-nostats", "-f", "null", "-"]
    ev = threading.Event()
    threading.Timer(1.0, ev.set).start()
    t0 = time.time()
    with pytest.raises(rd.RenderCancelled):
        rd.run_ffmpeg(cmd, tmp_path, 600, None, ev)
    assert time.time() - t0 < 10


# ---------------------------------------------------------------- API + render nyata
@pytest.fixture()
def fvideo(client, project, face_video):
    r = client.post("/api/videos/upload", data={"project_id": project}, files=[("files", ("wajah.mp4", face_video.read_bytes(), "video/mp4"))])
    assert r.status_code == 201, r.text
    return r.json()["items"][0]["video"]["id"]


def wait_job(client, jid, t=90):
    end = time.time() + t
    while time.time() < end:
        j = client.get(f"/api/jobs/{jid}").json()
        if j["status"] in ("done", "failed", "cancelled"):
            return j
        time.sleep(0.2)
    raise AssertionError(j)


def frame_faces(video: Path, t: float):
    import numpy as np

    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(video), "-frames:v", "1", "-f", "image2pipe", "-c:v", "png", "-"], capture_output=True, check=True).stdout
    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    cas = cv2.CascadeClassifier(str(fd._cascade_path()))
    return img, cas.detectMultiScale(cv2.equalizeHist(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)), 1.1, 5, minSize=(40, 40))


def test_clip_crud_and_validation(client, fvideo):
    assert client.post(f"/api/videos/{fvideo}/clips", json={"start_time": 5, "end_time": 4}).status_code == 422
    assert client.post(f"/api/videos/{fvideo}/clips", json={"start_time": 0, "end_time": 99}).status_code == 422  # lewat durasi
    assert client.post(f"/api/videos/{fvideo}/clips", json={"start_time": 0, "end_time": 0.4}).status_code == 422  # terlalu pendek
    c = client.post(f"/api/videos/{fvideo}/clips", json={"start_time": 0.5, "end_time": 5.5, "title": "Uji"})
    assert c.status_code == 201
    cid = c.json()["id"]
    assert abs(c.json()["duration"] - 5) < 1e-6
    p = client.patch(f"/api/clips/{cid}", json={"approved": True, "end_time": 5.0}).json()
    assert p["approved"] and p["duration"] == 4.5
    assert client.patch(f"/api/clips/{cid}", json={"end_time": 500}).status_code == 422
    assert client.put(f"/api/clips/{cid}/edit", json={"layout": "tiga-kolom"}).status_code == 422
    assert client.put(f"/api/clips/{cid}/edit", json={"crop_mode": "manual", "manual_x": 0.3}).json()["manual_x"] == 0.3
    assert client.get(f"/api/clips/{cid}/edit").json()["crop_mode"] == "manual"
    assert client.delete(f"/api/clips/{cid}").status_code == 204 and client.get(f"/api/clips?video_id={fvideo}").json() == []


def test_analyze_preview_and_face_following_render(client, fvideo, tmp_root):
    cid = client.post(f"/api/videos/{fvideo}/clips", json={"start_time": 0, "end_time": 6, "title": "Ikuti wajah"}).json()["id"]
    an = client.post(f"/api/clips/{cid}/analyze-crop").json()
    assert an["available"] and not an["static"] and an["frames_with_face"] >= 8 and an["track"][0]["x"] < 0.45 < 0.55 < an["track"][-1]["x"]

    pv = client.get(f"/api/clips/{cid}/preview", params={"t": 4.5, "width": 270})
    assert pv.status_code == 200 and pv.content[:2] == b"\xff\xd8"
    jpg = cv2.imdecode(__import__("numpy").frombuffer(pv.content, "uint8"), cv2.IMREAD_COLOR)
    assert jpg.shape[1] == 270 and abs(jpg.shape[0] / jpg.shape[1] - 16 / 9) < 0.02  # pratinjau 9:16

    r = client.post(f"/api/clips/{cid}/render")
    assert r.status_code == 202
    assert client.post(f"/api/clips/{cid}/render").status_code == 409  # sedang berjalan
    j = wait_job(client, r.json()["id"])
    assert j["status"] == "done", j
    assert j["encoder"] == "libx264" and j["uses_gpu"] is False  # sandbox tanpa GPU: tidak berpura-pura GPU
    info = j["output_info"]
    assert (info["width"], info["height"]) == (1080, 1920) and info["has_audio"] and abs(info["duration"] - 6) < 0.4 and info["video_codec"] == "h264" and abs(info["fps"] - 30) < 0.5
    assert "output_path" not in j and "/storage/" not in str(j)  # path lokal tidak bocor

    dl = client.get(j["download_url"])
    assert dl.status_code == 200 and dl.headers["content-type"] == "video/mp4" and dl.content[4:8] == b"ftyp"
    assert "Ikuti%20wajah.mp4" in dl.headers["content-disposition"]
    out = tmp_root / "out_follow.mp4"
    out.write_bytes(dl.content)
    # BUKTI kamera mengikuti: wajah masih ada di dalam frame vertikal pada awal (kiri) DAN akhir (kanan) video sumber
    for t in (1.0, 5.0):
        img, faces = frame_faces(out, t)
        assert img.shape[:2] == (1920, 1080)
        assert len(faces) >= 1, f"wajah hilang dari hasil crop pada t={t}"


def test_center_crop_loses_the_face_proving_tracking_matters(client, fvideo, tmp_root):
    """Pembanding: center crop memotong wajah saat wajah di tepi kanan sumber; ini membuktikan tes di atas bermakna."""
    cid = client.post(f"/api/videos/{fvideo}/clips", json={"start_time": 3.2, "end_time": 5.5}).json()["id"]
    client.put(f"/api/clips/{cid}/edit", json={"crop_mode": "center"})
    j = wait_job(client, client.post(f"/api/clips/{cid}/render").json()["id"])
    assert j["status"] == "done"
    out = tmp_root / "out_center.mp4"
    out.write_bytes(client.get(j["download_url"]).content)
    _, faces = frame_faces(out, 1.0)
    assert len(faces) == 0


def test_all_layouts_and_manual_crop_render(client, fvideo):
    cid = client.post(f"/api/videos/{fvideo}/clips", json={"start_time": 0, "end_time": 2}).json()["id"]
    for spec in ({"layout": "letterbox", "background": "blur"}, {"layout": "letterbox", "background": "black"}, {"layout": "split", "split_top_ratio": 0.4, "cam_rect": {"x": 0, "y": 0, "w": 0.5, "h": 1}},
                 {"layout": "fill", "crop_mode": "manual", "manual_x": 0.9}):
        client.put(f"/api/clips/{cid}/edit", json=spec)
        j = wait_job(client, client.post(f"/api/clips/{cid}/render").json()["id"])
        assert j["status"] == "done", (spec, j["error_message"])
        assert (j["output_info"]["width"], j["output_info"]["height"]) == (1080, 1920)


def test_captions_are_actually_burned_in(client, project, fvideo, tmp_root):
    import numpy as np

    from app.database import SessionLocal
    from app.models import Transcript, TranscriptSegment

    with SessionLocal() as db:
        tr = Transcript(video_id=fvideo, language="id", model="tiny", full_text="x")
        db.add(tr)
        db.flush()
        words = [{"start": 0.1 + i * 0.4, "end": 0.45 + i * 0.4, "word": w} for i, w in enumerate(["HALO", "SEMUA", "APA", "KABAR"])]
        db.add(TranscriptSegment(transcript_id=tr.id, start_time=0.1, end_time=1.9, text="HALO SEMUA APA KABAR", word_timestamps_json=words))
        db.commit()
    cid = client.post(f"/api/videos/{fvideo}/clips", json={"start_time": 0, "end_time": 2.5}).json()["id"]
    outs = {}
    for name, enabled in (("on", True), ("off", False)):
        client.put(f"/api/clips/{cid}/edit", json={"crop_mode": "center", "captions": {"enabled": enabled, "preset": "pop_yellow", "y": 0.7}})
        j = wait_job(client, client.post(f"/api/clips/{cid}/render").json()["id"])
        assert j["status"] == "done", j["error_message"]
        p = tmp_root / f"cap_{name}.mp4"
        p.write_bytes(client.get(j["download_url"]).content)
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", "0.9", "-i", str(p), "-frames:v", "1", "-f", "image2pipe", "-c:v", "png", "-"], capture_output=True, check=True).stdout
        outs[name] = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    band = slice(int(1920 * 0.62), int(1920 * 0.80))
    diff = np.abs(outs["on"][band].astype(int) - outs["off"][band].astype(int)).mean()
    outside = np.abs(outs["on"][: int(1920 * 0.3)].astype(int) - outs["off"][: int(1920 * 0.3)].astype(int)).mean()
    assert diff > 5 * max(outside, 0.5), (diff, outside)  # perubahan terkonsentrasi di area caption
    yellow = ((outs["on"][..., 2] > 200) & (outs["on"][..., 1] > 180) & (outs["on"][..., 0] < 80)).sum()  # warna highlight kuning (BGR)
    assert yellow > 200


def test_gpu_mode_fails_clearly_without_nvenc(client, fvideo):
    client.put("/api/system/limits", json={"compute_mode": "gpu"})
    try:
        cid = client.post(f"/api/videos/{fvideo}/clips", json={"start_time": 0, "end_time": 2}).json()["id"]
        j = wait_job(client, client.post(f"/api/clips/{cid}/render").json()["id"])
        assert j["status"] == "failed" and "Mode GPU" in j["error_message"]
        assert j["download_url"] is None
    finally:
        client.put("/api/system/limits", json={"compute_mode": "auto"})


def test_download_is_restricted_to_outputs_dir(client, fvideo):
    from app.database import SessionLocal
    from app.models import RenderJob

    cid = client.post(f"/api/videos/{fvideo}/clips", json={"start_time": 0, "end_time": 2}).json()["id"]
    with SessionLocal() as db:
        j = RenderJob(clip_id=cid, status="done", output_path="/etc/passwd")
        db.add(j)
        db.commit()
        jid = j.id
    assert client.get(f"/api/exports/{jid}/file").status_code == 404


def test_cancel_queued_render_and_unknown_ids(client, fvideo):
    assert client.post("/api/jobs/nope/cancel").status_code == 404
    assert client.get("/api/exports/nope/file").status_code == 404
    assert client.post("/api/clips/nope/render").status_code == 404
