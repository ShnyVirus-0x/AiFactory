import uuid

import pytest

from app.database import SessionLocal
from app.models import Clip, RenderJob, Video


def create_clip(project_id, start=0):
    with SessionLocal() as db:
        video = Video(project_id=project_id, filename="sample.mp4", source_path="sample.mp4", sha256=uuid.uuid4().hex, duration=10, width=640, height=360)
        db.add(video)
        db.flush()
        clip = Clip(project_id=project_id, video_id=video.id, start_time=start, end_time=start + 2, duration=2, title=f"Klip {start}")
        db.add(clip)
        db.commit()
        return clip.id


def test_batch_render_queues_selected_project_clips(client, project, monkeypatch):
    submitted = []
    monkeypatch.setattr("app.routers.jobs.render_worker.submit", submitted.append)
    first = create_clip(project, 0)
    second = create_clip(project, 2)

    response = client.post(f"/api/projects/{project}/render", json={"clip_ids": [first, second]})

    assert response.status_code == 202, response.text
    body = response.json()
    assert len(body["jobs"]) == 2
    assert body["skipped"] == []
    assert {job["clip_id"] for job in body["jobs"]} == {first, second}
    assert {job["id"] for job in body["jobs"]} == set(submitted)


def test_batch_render_skips_active_jobs_and_validates_project(client, project, monkeypatch):
    monkeypatch.setattr("app.routers.jobs.render_worker.submit", lambda _: None)
    clip_id = create_clip(project)
    active = client.post(f"/api/clips/{clip_id}/render")
    assert active.status_code == 202
    monkeypatch.setattr("app.routers.jobs.render_worker.submit", lambda _: None)

    response = client.post(f"/api/projects/{project}/render", json={"clip_ids": [clip_id]})
    assert response.status_code == 202
    assert response.json()["jobs"] == []
    assert response.json()["skipped"] == [{"clip_id": clip_id, "reason": "already_running"}]
    assert client.post(f"/api/projects/{project}/render", json={"clip_ids": ["unknown"]}).status_code == 422
    assert client.post(f"/api/projects/{project}/render", json={"clip_ids": [clip_id, clip_id]}).status_code == 422


def test_failed_render_can_be_retried(client, project, monkeypatch):
    submitted = []
    monkeypatch.setattr("app.routers.jobs.render_worker.submit", submitted.append)
    clip_id = create_clip(project)
    with SessionLocal() as db:
        failed = RenderJob(clip_id=clip_id, status="failed", error_message="uji")
        db.add(failed)
        db.commit()
        failed_id = failed.id

    response = client.post(f"/api/jobs/{failed_id}/retry")

    assert response.status_code == 202, response.text
    assert response.json()["status"] == "queued"
    assert submitted == [response.json()["id"]]
    assert client.post(f"/api/jobs/{response.json()['id']}/retry").status_code == 409
