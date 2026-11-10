import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Environment harus diset SEBELUM app diimpor.
_TMP = tempfile.mkdtemp(prefix="asf-test-")
os.environ.update(ASF_STORAGE_DIR=f"{_TMP}/storage", ASF_MODELS_DIR=f"{_TMP}/models", ASF_FRONTEND_DIST=f"{_TMP}/nodist",
                  ASF_OLLAMA_URL="http://127.0.0.1:9", ASF_STATS_PUSH_SECONDS="0.5")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.fixture(scope="session")
def tmp_root() -> Path:
    return Path(_TMP)


def make_video(path: Path, seconds=6, audio=True, size="640x360", color=None) -> Path:
    if shutil.which("ffmpeg") is None:
        pytest.skip("FFmpeg tidak ditemukan di PATH; tes yang membutuhkan video sampel dilewati")
    src = f"testsrc2=size={size}:rate=25:duration={seconds}" if color is None else f"color=c={color}:size={size}:rate=25:duration={seconds}"
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", src]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
    if audio:
        cmd += ["-c:a", "aac", "-shortest"]
    subprocess.run(cmd + [str(path)], check=True)
    return path


@pytest.fixture(scope="session")
def sample_video(tmp_root) -> Path:
    return make_video(tmp_root / "sample.mp4", 6, True)


@pytest.fixture(scope="session")
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def project(client):
    r = client.post("/api/projects", json={"name": "Proyek Uji"})
    assert r.status_code == 201
    pid = r.json()["id"]
    yield pid
    client.delete(f"/api/projects/{pid}")
