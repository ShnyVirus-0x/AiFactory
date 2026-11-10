"""Proyek, unggah video, validasi, metadata, duplikat, keamanan file."""
import io
from pathlib import Path

import pytest

from app.utils.files import is_within, safe_join, sanitize_filename
from .conftest import make_video


def upload(client, pid, files):
    return client.post(
        "/api/videos/upload",
        data={"project_id": pid},
        files=[("files", file) for file in files],
    )


def test_project_crud(client):
    response = client.post(
        "/api/projects",
        json={"name": "  Podcast A  ", "description": "d"},
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Podcast A"
    project_id = response.json()["id"]

    assert client.post("/api/projects", json={"name": "   "}).status_code == 422

    updated = client.patch(
        f"/api/projects/{project_id}",
        json={"name": "Podcast B", "status": "archived"},
    )
    assert updated.json()["status"] == "archived"
    assert client.patch(
        f"/api/projects/{project_id}",
        json={"status": "bogus"},
    ).status_code == 422

    projects = client.get(
        "/api/projects",
        params={"status": "archived", "q": "podcast b"},
    ).json()
    assert [project["id"] for project in projects] == [project_id]
    assert client.get("/api/projects/ngawur").status_code == 404
    assert client.delete(f"/api/projects/{project_id}").status_code == 204
    assert client.get(f"/api/projects/{project_id}").status_code == 404


def test_structured_errors(client):
    not_found = client.get("/api/projects/nope").json()["error"]
    assert not_found["code"] == "not_found"
    assert "tidak ditemukan" in not_found["message"]

    validation_error = client.post("/api/projects", json={}).json()["error"]
    assert validation_error["code"] == "validation_error"
    assert validation_error["details"][0]["field"] == "name"


def test_upload_metadata_thumbnail_stream(client, project, sample_video):
    response = upload(
        client,
        project,
        [("clip.mp4", sample_video.read_bytes(), "video/mp4")],
    )
    assert response.status_code == 201, response.text

    body = response.json()
    assert body["succeeded"] == 1
    assert body["failed"] == 0

    video = body["items"][0]["video"]
    assert (video["width"], video["height"]) == (640, 360)
    assert abs(video["duration"] - 6) < 0.3
    assert abs(video["fps"] - 25) < 0.1
    assert video["video_codec"] == "h264"
    assert video["audio_tracks"] == 1
    assert video["has_thumbnail"] is True

    thumbnail = client.get(f"/api/videos/{video['id']}/thumbnail")
    assert thumbnail.content[:2] == b"\xff\xd8"

    stream = client.get(f"/api/videos/{video['id']}/stream")
    assert stream.status_code == 200
    assert stream.headers["content-type"] == "video/mp4"
    assert len(stream.content) == video["file_size"]
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
    assert body["succeeded"] == 2
    assert body["failed"] == 3
    errors = {
        item["filename"]: item["error"]
        for item in body["items"]
        if not item["ok"]
    }
    assert "tidak didukung" in errors["evil.exe"]
    assert "valid" in errors["fake.mp4"]

    silent_item = next(
        item for item in body["items"] if item["filename"] == "b.mkv"
    )
    assert silent_item["video"]["audio_tracks"] == 0

    storage_dir = Path(client.get("/api/system/health").json()["storage_dir"])
    uploads_dir = storage_dir / "uploads"
    before = len(list(uploads_dir.glob("*")))
    duplicate = upload(
        client,
        project,
        [("again.mp4", sample_video.read_bytes(), "video/mp4")],
    ).json()
    assert duplicate["failed"] == 1
    assert duplicate["items"][0]["duplicate_of"]
    after = len(list(uploads_dir.glob("*")))
    assert before == after
    assert ".exe" not in [path.suffix for path in uploads_dir.glob("*")]


def test_upload_requires_existing_project_and_limits(client, sample_video):
    assert upload(
        client,
        "nope",
        [("a.mp4", sample_video.read_bytes(), "video/mp4")],
    ).status_code == 404
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
    old_n = s.max_files_per_upload
    s.max_files_per_upload = 1
    try:
        two = [
            ("a.mp4", sample_video.read_bytes(), "video/mp4"),
            ("b.mp4", b"x", "video/mp4"),
        ]
        assert upload(client, pid, two).status_code == 413
    finally:
        s.max_files_per_upload = old_n
    client.delete(f"/api/projects/{pid}")


def test_search_filter_rename_delete(client, project, sample_video, tmp_root):
    short = make_video(tmp_root / "short.mp4", 2, True, "320x180", color="blue")
    upload(
        client,
        project,
        [
            ("Interview Final.mp4", sample_video.read_bytes(), "video/mp4"),
            ("kecil.mp4", short.read_bytes(), "video/mp4"),
        ],
    )

    def list_videos(**params):
        response = client.get(
            "/api/videos",
            params={"project_id": project, **params},
        )
        return response.json()

    assert len(list_videos()) == 2
    assert [video["filename"] for video in list_videos(q="interview")] == [
        "Interview Final.mp4"
    ]
    assert [video["filename"] for video in list_videos(min_duration=4)] == [
        "Interview Final.mp4"
    ]
    assert [video["filename"] for video in list_videos(min_height=300)] == [
        "Interview Final.mp4"
    ]
    assert list_videos(sort="duration")[0]["filename"] == "Interview Final.mp4"
    assert client.get("/api/videos", params={"sort": "acak"}).status_code == 422
    video = list_videos(q="kecil")[0]
    renamed = client.patch(
        f"/api/videos/{video['id']}",
        json={"filename": "../../etc/passwd.mp4"},
    ).json()
    assert renamed["filename"] == "passwd.mp4"

    from app.models import Video
    from app.database import SessionLocal

    with SessionLocal() as db:
        path = Path(db.get(Video, video["id"]).source_path)
    assert path.is_file()
    assert client.delete(f"/api/videos/{video['id']}").status_code == 204
    assert not path.exists()
    assert client.get(f"/api/videos/{video['id']}").status_code == 404


def test_deleting_project_removes_files(client, sample_video):
    pid = client.post("/api/projects", json={"name": "Hapus"}).json()["id"]
    video = upload(
        client,
        pid,
        [("x.mp4", sample_video.read_bytes(), "video/mp4")],
    ).json()["items"][0]["video"]
    from app.database import SessionLocal
    from app.models import Video

    with SessionLocal() as db:
        row = db.get(Video, video["id"])
        source_path = Path(row.source_path)
        thumbnail_path = Path(row.thumbnail_path)
    assert source_path.exists()
    assert thumbnail_path.exists()
    assert client.delete(f"/api/projects/{pid}").status_code == 204
    assert not source_path.exists()
    assert not thumbnail_path.exists()


# --------------------------- keamanan nama/path ---------------------------
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("../../Windows/System32/evil.mp4", "evil.mp4"),
        ("C:\\Users\\x\\vid.mp4", "vid.mp4"),
        ("a/b\\c.mov", "c.mov"),
        ("CON.mp4", "video.mp4"),
        ("   ...  .mkv", "video.mkv"),
        ("rekaman<>:\"|?*.mp4", "rekaman.mp4"),
        ("Wawancara Ñandú éé.mp4", "Wawancara Ñandú éé.mp4"),
    ],
)
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
