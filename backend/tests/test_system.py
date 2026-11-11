"""Diagnostik GPU / sumber daya / kesehatan: parser dan perilaku saat GPU tidak ada."""
from app.services import gpu_monitor as gm

SMI_CSV = (
    "0, NVIDIA GeForce RTX 4070 Ti, 552.22, 12282, 1520, 10554, 37, 46, 38.12\n"
    "1, NVIDIA Test GPU, 552.22, 8192, 100, 8092, [N/A], [Not Supported], [N/A]\n"
)
SMI_PLAIN = "| NVIDIA-SMI 552.22   Driver Version: 552.22   CUDA Version: 12.4 |"


def test_parse_gpu_csv_real_format():
    g = gm.parse_gpu_csv(SMI_CSV)
    assert len(g) == 2
    assert g[0].name == "NVIDIA GeForce RTX 4070 Ti" and g[0].vram_total_mb == 12282 and g[0].vram_free_mb == 10554
    assert g[0].utilization_percent == 37 and g[0].temperature_c == 46 and g[0].power_w == 38.12
    assert g[1].utilization_percent is None and g[1].temperature_c is None  # [N/A] -> None, bukan 0 palsu


def test_parse_gpu_csv_ignores_garbage():
    assert gm.parse_gpu_csv("") == []
    assert gm.parse_gpu_csv("bukan, csv") == []
    assert gm.parse_gpu_csv("x, name, drv, a, b, c, d, e") == []


def test_parse_cuda_version():
    assert gm.parse_cuda_version(SMI_PLAIN) == "12.4"
    assert gm.parse_cuda_version("tidak ada") is None


def test_no_gpu_is_reported_honestly(monkeypatch):
    monkeypatch.setattr(gm, "find_nvidia_smi", lambda: None)
    r = gm.query_gpus()
    assert r["available"] is False and r["gpus"] == [] and "nvidia-smi" in r["reason"]


def test_gpu_with_fake_smi(monkeypatch):
    import subprocess

    monkeypatch.setattr(gm, "find_nvidia_smi", lambda: "nvidia-smi")
    gm._cuda_cache.clear()

    def fake_run(cmd, timeout=8.0):
        out = SMI_CSV if any(a.startswith("--query-gpu") for a in cmd) else SMI_PLAIN
        return subprocess.CompletedProcess(cmd, 0, out, "")

    monkeypatch.setattr(gm, "_run", fake_run)
    r = gm.query_gpus()
    assert r["available"] and r["cuda_version"] == "12.4" and r["driver_version"] == "552.22" and len(r["gpus"]) == 2


def test_smi_failure_is_reported(monkeypatch):
    import subprocess

    monkeypatch.setattr(gm, "find_nvidia_smi", lambda: "nvidia-smi")
    monkeypatch.setattr(gm, "_run", lambda cmd, timeout=8.0: subprocess.CompletedProcess(cmd, 9, "", "NVIDIA-SMI has failed"))
    r = gm.query_gpus()
    assert r["available"] is False and "failed" in r["reason"]


def test_nvenc_requires_real_encode_test(monkeypatch):
    import subprocess

    gm._nvenc_cache.clear()
    calls = []

    def fake_run(cmd, timeout=8.0):
        calls.append(cmd)
        if "-encoders" in cmd:
            return subprocess.CompletedProcess(cmd, 0, " V....D h264_nvenc  NVIDIA NVENC\n V....D hevc_nvenc", "")
        return subprocess.CompletedProcess(cmd, 1, "", "Cannot load nvcuda.dll\n")  # uji encode gagal: tidak ada GPU

    monkeypatch.setattr(gm, "_run", fake_run)
    monkeypatch.setattr(gm.shutil, "which", lambda b: "/usr/bin/ffmpeg")
    r = gm.nvenc_status(force=True)
    assert r["available"] is False and "nvcuda" in r["reason"]  # terdaftar di FFmpeg BUKAN berarti bisa dipakai
    assert len(calls) == 2


def test_resources_are_real(client):
    r = client.get("/api/system/resources").json()
    assert r["ram"]["total"] > 0 and 0 <= r["cpu"]["percent"] <= 100 and r["disk"]["free"] > 0
    assert r["cpu"]["cores_logical"] >= 1 and "gpu" in r


def test_health_and_capabilities(client):
    import shutil

    h = client.get("/api/system/health").json()
    checks = {c["key"]: c for c in h["checks"]}
    # Laporan kesehatan harus JUJUR sesuai lingkungan: ok bila FFmpeg/FFprobe ada, degraded bila tidak.
    ff_ok = shutil.which("ffmpeg") is not None
    fp_ok = shutil.which("ffprobe") is not None
    assert checks["ffmpeg"]["ok"] is ff_ok and checks["ffprobe"]["ok"] is fp_ok
    assert h["status"] == ("ok" if ff_ok and fp_ok else "degraded")
    assert checks["ollama"]["ok"] is False  # tidak ada Ollama di lingkungan uji -> dilaporkan apa adanya
    assert h["bind"].startswith("127.0.0.1")
    caps = {c["key"]: c for c in h["capabilities"]}
    assert caps["library"]["available"] is True
    assert caps["transcription"]["available"] is True and caps["transcription"]["phase"] == 2
    assert caps["clip_detection"]["available"] is True and caps["clip_detection"]["phase"] == 3
    assert caps["batch_renderer"]["available"] is True  # batch render dasar sudah tersedia
    assert caps["export_center"]["available"] is True
    assert caps["templates"]["available"] is False  # tidak berpura-pura sudah ada


def test_gpu_endpoint_shape(client):
    g = client.get("/api/system/gpu").json()
    assert set(["available", "gpus", "cuda_version", "nvenc"]) <= set(g)
