"""Integrasi: jalankan server SUNGGUHAN (proses uvicorn terpisah, storage sementara) lalu uji alur lewat HTTP.
Alur: health -> proyek -> unggah -> klip -> render -> unduh -> verifikasi FFprobe. Juga memeriksa bind hanya ke 127.0.0.1."""
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

BACKEND = Path(__file__).resolve().parents[2] / "backend"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("live")
    port = free_port()
    env = {**os.environ, "ASF_STORAGE_DIR": str(tmp / "storage"), "ASF_MODELS_DIR": str(tmp / "models"), "ASF_PORT": str(port),
           "ASF_FRONTEND_DIST": str(tmp / "nodist"), "ASF_OLLAMA_URL": "http://127.0.0.1:9"}
    proc = subprocess.Popen([sys.executable, "-m", "app.main"], cwd=BACKEND, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                if httpx.get(f"{base}/api/system/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.2)
        else:
            proc.kill()
            raise RuntimeError("server tidak naik: " + (proc.stdout.read() or b"").decode(errors="ignore")[-800:])
        yield base, port, tmp
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_server_binds_loopback_only(server):
    base, port, _ = server
    # alamat non-loopback milik mesin ini tidak boleh menerima koneksi
    others = {a[4][0] for a in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)} - {"127.0.0.1", "127.0.1.1"}
    if not others:
        pytest.skip("mesin ini tidak punya alamat non-loopback untuk diuji")
    for ip in others:
        with pytest.raises(OSError):
            socket.create_connection((ip, port), timeout=1).close()


def test_full_flow_over_http(server):
    base, _, tmp = server
    vid = tmp / "src.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=25:duration=5", "-f", "lavfi", "-i", "sine=frequency=330:duration=5",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(vid)], check=True)
    with httpx.Client(base_url=base, timeout=60) as c:
        pid = c.post("/api/projects", json={"name": "Integrasi"}).json()["id"]
        up = c.post("/api/videos/upload", data={"project_id": pid}, files=[("files", ("src.mp4", vid.read_bytes(), "video/mp4"))])
        assert up.status_code == 201
        v = up.json()["items"][0]["video"]
        assert (v["width"], v["height"]) == (1280, 720) and v["audio_tracks"] == 1
        # tipe file berbahaya ditolak
        bad = c.post("/api/videos/upload", data={"project_id": pid}, files=[("files", ("evil.exe", b"MZ" + b"0" * 100, "application/octet-stream"))]).json()
        assert bad["failed"] == 1
        clip = c.post(f"/api/videos/{v['id']}/clips", json={"start_time": 0.5, "end_time": 4.0, "title": "Integrasi"}).json()
        c.put(f"/api/clips/{clip['id']}/edit", json={"crop_mode": "center", "captions": {"enabled": False}})
        job = c.post(f"/api/clips/{clip['id']}/render").json()
        for _ in range(300):
            j = c.get(f"/api/jobs/{job['id']}").json()
            if j["status"] in ("done", "failed"):
                break
            time.sleep(0.2)
        assert j["status"] == "done", j
        out = tmp / "out.mp4"
        out.write_bytes(c.get(j["download_url"]).content)
        probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(out)], capture_output=True, text=True, check=True).stdout)
        kinds = {s["codec_type"] for s in probe["streams"]}
        v0 = next(s for s in probe["streams"] if s["codec_type"] == "video")
        assert kinds == {"video", "audio"} and (v0["width"], v0["height"]) == (1080, 1920) and abs(float(probe["format"]["duration"]) - 3.5) < 0.4
        assert c.delete(f"/api/projects/{pid}").status_code == 204
        assert c.get("/api/dashboard").json()["totals"]["projects"] == 0
