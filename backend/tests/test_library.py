"""Proyek, unggah video, validasi, metadata, duplikat, keamanan file."""
import io
import subprocess
from pathlib import Path

import pytest

from app.utils.files import is_within, safe_join, sanitize_filename
from .conftest import make_video


def upload(client, pid, files):
    return client.post("/api/videos/upload", data={"project_id": pid}, files=[("files", f) for f in files])


def test_project_crud(client):
    r = client.post("/api/projects", json={"name": "  Podcast A  ", "description": "d"})
    assert r.status_code == 201 and r.json()["name"] == "Podcast A"
    pid = r.json()["id"]
    assert client.post("/api/projects", json={"name": "   "}).status_code == 422
    assert client.patch(f"/api/projects/{pid}", json={"name": "Podcast B", "status": "archived"}).json()["status"] == "archived"
    assert client.patch(f"/api/projects/{pid}", json={"status": "bogus"}).status_code == 422
    assert [p["id"] for p in client.get("/api/projects", params={"status": "archived", "q": "podcast b"}).json()] == [pid]
    assert client.get("/api/projects/ngawur").status_code == 404
    assert client.delete(f"/api/projects/{pid}").status_code == 204
    assert client.get(f"/api/projects/{pid}").status_code == 404


def test_structured_errors(client):
    e = client.get("/api/projects/nope").json()["error"]
    assert e["code"] == "not_found" and "tidak ditemukan" in e["message"]
    v = client.post("/api/projects", json={}).json()["error"]
    assert v["code"] == "validation_error" and v["details"][0]["field"] == "name"


def test_upload_metadata_thumbnail_stream(client, project, sample_video):
    r = upload(client, project, [("clip.mp4", sample_video.read_bytes(), "video/mp4")])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["succeeded"] == 1 and body["failed"] == 0
    v = body["items"][0]["video"]
    assert (v["width"], v["height"]) == (640, 360) and abs(v["duration"] - 6) < 0.3 and abs(v["fps"] - 25) < 0.1
    assert v["video_codec"] == "h264" and v["audio_tracks"] == 1 and v["has_thumbnail"] is True
    assert client.get(f"/api/videos/{v['id']}/thumbnail").content[:2] == b"\xff\xd8"
    s = client.get(f"/api/videos/{v['id']}/stream")
    assert s.status_code == 200 and s.headers["content-type"] == "video/mp4" and len(s.content) == v["file_size"]
    assert client.get(f"/api/projects/{project}").json()["video_count"] == 1


def test_multi_upload_with_mixed_results_and_duplicates(client, project, sample_video, tmp_root):
    silent = make_video(tmp_root / "silent.mkv", 3, audio=False)
    files = [
        ("a.mp4", sample_video.read_bytes(), "video/mp4"),
        ("b.mkv", silent.read_bytes(), "video/x-matroska"),
        ("evil.exe", b"MZ\x90\x00", "application/octet-stream"),
        ("fake.mp4", b"ini bukan video", "video/mp4"),
        ("empty.mp4", b"", "video/mp4"),
    ]
    body = upload(client, project, files).json()
    assert body["succeeded"] == 2 and body["failed"] == 3
    errs = {i["filename"]: i["error"] for i in body["items"] if not i["ok"]}
    assert "tidak didukung" in errs["evil.exe"] and "valid" in errs["fake.mp4"]
    silent_item = next(i for i in body["items"] if i["filename"] == "b.mkv")
    assert silent_item["video"]["audio_tracks"] == 0
    # unggah ulang file yang sama persis -> ditolak, tidak ada file sisa
    before = len(list(Path(client.get('/api/system/health').json()['storage_dir'], 'uploads').glob('*')))
    dup = upload(client, project, [("again.mp4", sample_video.read_bytes(), "video/mp4")]).json()
    assert dup["failed"] == 1 and dup["items"][0]["duplicate_of"]
    after = len(list(Path(client.get('/api/system/health').json()['storage_dir'], 'uploads').glob('*')))
    assert before == after
    # tidak ada sisa file dari upload yang gagal
    names = [p.suffix for p in Path(client.get('/api/system/health').json()['storage_dir'], 'uploads').glob('*')]
    assert ".exe" not in names


def test_upload_requires_existing_project_and_limits(client, sample_video):
    assert upload(client, "nope", [("a.mp4", sample_video.read_bytes(), "video/mp4")]).status_code == 404
    pid = client.post("/api/projects", json={"name": "Lim"}).json()["id"]
    from app.config import get_settings

    s = get_settings()
    old = s.max_upload_mb
    s.max_upload_mb = 1
    try:
        big = io.BytesIO(b"\x00" * (2 * 1024 * 1024))
        r = upload(client, pid, [("big.mp4", big.getvalue(), "video/mp4")]).json()
        assert r["failed"] == 1 and "batas" in r["items"][0]["error"]
    finally:
        s.max_upload_mb = old
    s.max_files_per_upload, old_n = 1, s.max_files_per_upload
    try:
        two = [("a.mp4", sample_video.read_bytes(), "video/mp4"), ("b.mp4", b"x", "video/mp4")]
        assert upload(client, pid, two).status_code == 413
    finally:
        s.max_files_per_upload = old_n
    client.delete(f"/api/projects/{pid}")


def test_search_filter_rename_delete(client, project, sample_video, tmp_root):
    short = make_video(tmp_root / "short.mp4", 2, True, "320x180", color="blue")
    upload(client, project, [("Interview Final.mp4", sample_video.read_bytes(), "video/mp4"), ("kecil.mp4", short.read_bytes(), "video/mp4")])
    lst = lambda **p: client.get("/api/videos", params={"project_id": project, **p}).json()  # noqa: E731
    assert len(lst()) == 2
    assert [v["filename"] for v in lst(q="interview")] == ["Interview Final.mp4"]
    assert [v["filename"] for v in lst(min_duration=4)] == ["Interview Final.mp4"]
    assert [v["filename"] for v in lst(min_height=300)] == ["Interview Final.mp4"]
    assert [v["filename"] for v in lst(sort="duration")][0] == "Interview Final.mp4"
    assert client.get("/api/videos", params={"sort": "acak"}).status_code == 422
    vid = lst(q="kecil")[0]
    renamed = client.patch(f"/api/videos/{vid['id']}", json={"filename": "../../etc/passwd.mp4"}).json()
    assert renamed["filename"] == "passwd.mp4"  # komponen path dibuang
    from app.models import Video
    from app.database import SessionLocal

    with SessionLocal() as db:
        path = Path(db.get(Video, vid["id"]).source_path)
    assert path.is_file()
    assert client.delete(f"/api/videos/{vid['id']}").status_code == 204
    assert not path.exists()
    assert client.get(f"/api/videos/{vid['id']}").status_code == 404


def test_deleting_project_removes_files(client, sample_video):
    pid = client.post("/api/projects", json={"name": "Hapus"}).json()["id"]
    v = upload(client, pid, [("x.mp4", sample_video.read_bytes(), "video/mp4")]).json()["items"][0]["video"]
    from app.database import SessionLocal
    from app.models import Video

    with SessionLocal() as db:
        row = db.get(Video, v["id"])
        src, thumb = Path(row.source_path), Path(row.thumbnail_path)
    assert src.exists() and thumb.exists()
    client.delete(f"/api/projects/{pid}")
    assert not src.exists() and not thumb.exists()


# --------------------------- keamanan nama/path ---------------------------
@pytest.mark.parametrize("raw,expected", [
    ("../../Windows/System32/evil.mp4", "evil.mp4"),
    ("C:\\Users\\x\\vid.mp4", "vid.mp4"),
    ("a/b\\c.mov", "c.mov"),
    ("CON.mp4", "video.mp4"),
    ("   ...  .mkv", "video.mkv"),
    ("rekaman<>:\"|?*.mp4", "rekaman.mp4"),
    ("Wawancara Ñandú éé.mp4", "Wawancara Ñandú éé.mp4"),
])
def test_sanitize_filename(raw, expected):
    assert sanitize_filename(raw) == expected


def test_safe_join_blocks_traversal(tmp_path):
    assert safe_join(tmp_path, "a", "b.txt").is_relative_to(tmp_path.resolve())
    with pytest.raises(ValueError):
        safe_join(tmp_path, "..", "etc")
    with pytest.raises(ValueError):
        safe_join(tmp_path, "/etc/passwd")
    assert is_within(tmp_path / "x", tmp_path) and not is_within(tmp_path.parent, tmp_path)


def test_stored_name_is_random_not_user_controlled(client, project, sample_video):
    v = upload(client, project, [("../../hack.mp4", sample_video.read_bytes(), "video/mp4")]).json()["items"][0]["video"]
    from app.database import SessionLocal
    from app.models import Video

    with SessionLocal() as db:
        p = Path(db.get(Video, v["id"]).source_path)
    assert "hack" not in p.name and p.parent.name == "uploads"
