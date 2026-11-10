"""Dashboard (statistik dari DB), WebSocket, endpoint antrean, dan migrasi Alembic."""
import sqlite3

import pytest

from .test_library import upload


def test_dashboard_stats_come_from_db(client, sample_video):
    base = client.get("/api/dashboard").json()["totals"]
    pid = client.post("/api/projects", json={"name": "Dash"}).json()["id"]
    upload(client, pid, [("a.mp4", sample_video.read_bytes(), "video/mp4")])
    d = client.get("/api/dashboard").json()
    assert d["totals"]["projects"] == base["projects"] + 1 and d["totals"]["videos"] == base["videos"] + 1
    assert d["totals"]["clips"] == 0 and d["totals"]["renders_done"] == 0 and d["totals"]["jobs_running"] == 0
    assert d["recent_projects"][0]["name"] == "Dash" and d["recent_projects"][0]["video_count"] == 1
    kinds = [a["kind"] for a in d["activity"]]
    assert "video.uploaded" in kinds and "project.created" in kinds
    assert d["queue"] == []
    client.delete(f"/api/projects/{pid}")


def test_dashboard_counts_render_jobs(client, sample_video):
    from app.database import SessionLocal
    from app.models import Clip, RenderJob

    pid = client.post("/api/projects", json={"name": "Jobs"}).json()["id"]
    vid = upload(client, pid, [("a.mp4", sample_video.read_bytes(), "video/mp4")]).json()["items"][0]["video"]["id"]
    with SessionLocal() as db:
        c = Clip(project_id=pid, video_id=vid, start_time=0, end_time=3, duration=3, title="c")
        db.add(c)
        db.flush()
        db.add_all([RenderJob(clip_id=c.id, status="done", output_path="x.mp4"), RenderJob(clip_id=c.id, status="failed", error_message="e"),
                    RenderJob(clip_id=c.id, status="running", progress=0.4), RenderJob(clip_id=c.id, status="queued")])
        db.commit()
    t = client.get("/api/dashboard").json()
    assert t["totals"]["renders_done"] >= 1 and t["totals"]["renders_failed"] >= 1 and t["totals"]["jobs_running"] >= 1
    assert {q["status"] for q in t["queue"]} >= {"running", "queued"}
    assert len(client.get("/api/jobs").json()) >= 4 and len(client.get("/api/exports").json()) >= 1
    assert client.delete(f"/api/projects/{pid}").status_code == 204  # cascade ke clips & jobs


def test_unavailable_features_say_so(client, project):
    # Batch render SUDAH tersedia: tanpa body yang valid harus mengembalikan 422, bukan 501.
    r = client.post(f"/api/projects/{project}/render")
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    # Template masih belum tersedia dan harus mengatakannya dengan jelas.
    t = client.post("/api/templates")
    assert t.status_code == 501 and t.json()["error"]["code"] == "not_available" and t.json()["error"]["details"]["phase"] == 5
    assert client.get("/api/templates").json() == []


def test_websocket_events_and_stats(client):
    with client.websocket_connect("/ws", headers={"origin": "http://127.0.0.1:5173"}) as ws:
        assert ws.receive_json()["type"] == "hello"
        client.post("/api/projects", json={"name": "WS"})
        seen = set()
        for _ in range(12):
            m = ws.receive_json()
            seen.add(m["type"])
            if {"project.created", "system.stats"} <= seen:
                break
        assert "project.created" in seen
        assert "system.stats" in seen  # statistik berkala dari psutil/nvidia-smi nyata


def test_websocket_rejects_foreign_origin(client):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws", headers={"origin": "https://evil.example"}) as ws:
            ws.receive_json()


def test_migrations_create_schema_and_are_idempotent(tmp_path):
    from app.database import run_migrations

    db = tmp_path / "m.db"
    url = f"sqlite:///{db.as_posix()}"
    run_migrations(url)
    run_migrations(url)  # dua kali tidak error
    con = sqlite3.connect(db)
    tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    expected = {"users", "projects", "videos", "transcripts", "transcript_segments", "clips", "clip_edits", "templates",
                "render_jobs", "settings", "activity_log", "alembic_version", "transcription_jobs"}
    assert expected <= tables
    cols = {r[1] for r in con.execute("pragma table_info(videos)")}
    assert {"project_id", "filename", "source_path", "duration", "width", "height", "fps", "file_size", "created_at"} <= cols
    assert con.execute("select version_num from alembic_version").fetchone()[0] == "0003"
    con.close()


def test_models_match_migration(tmp_path):
    """Skema hasil migrasi harus sama dengan model (cegah lupa membuat migrasi baru)."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from sqlalchemy import create_engine

    from app import models  # noqa: F401
    from app.database import Base, run_migrations

    url = f"sqlite:///{(tmp_path / 'd.db').as_posix()}"
    run_migrations(url)
    eng = create_engine(url)
    with eng.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": False}), Base.metadata)
    assert diff == [], diff
