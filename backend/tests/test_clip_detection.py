from __future__ import annotations

from app.config import get_settings
from app.database import SessionLocal
from app.models import Project, Transcript, TranscriptSegment, Video
from app.services import clip_detection as detector


def test_transcript_windows_respect_time_and_text_limits():
    lines = [detector.TranscriptLine(i, i + 1, str(i) * 5000) for i in range(5)]
    lines.append(detector.TranscriptLine(500, 550, "later"))
    windows = detector._windows(lines)
    assert [len(window) for window in windows] == [4, 1, 1]
    assert all(sum(len(line.text) for line in window) <= detector.WINDOW_CHARS for window in windows)


def test_parse_response_keeps_only_valid_in_window_candidates():
    raw = """{"candidates":[
      {"start_time":10,"end_time":35,"title":" Insight ","hook":"Hook","reason":"Konteks utuh","score":93,"category":"insight"},
      {"start_time":90,"end_time":110,"title":"Di luar jendela","score":100},
      {"start_time":20,"end_time":200,"title":"Terlalu panjang","score":20},
      {"start_time":50,"end_time":54,"title":"Terlalu pendek","score":20}
    ]}"""
    items = detector._parse_response(raw, 0, 100, 200)
    assert len(items) == 1
    assert items[0].start_time == 10
    assert items[0].title == "Insight"
    assert items[0].score == 93


def test_suggest_candidates_uses_local_ollama_and_deduplicates(monkeypatch):
    settings = get_settings()
    seen = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"content": '{"candidates":[{"start_time":10,"end_time":35,"title":"Insight","hook":"Hook","reason":"Utuh","score":91,"category":"insight"}]}'}}

    def fake_post(url, **kwargs):
        seen.append((url, kwargs))
        return Response()

    monkeypatch.setattr(detector.httpx, "post", fake_post)
    lines = [
        detector.TranscriptLine(0, 20, "Pembukaan ide."),
        detector.TranscriptLine(20, 40, "Penjelasan dan kesimpulan."),
    ]
    result = detector.suggest_candidates(lines, 60, 5)
    assert len(result) == 1
    assert result[0].title == "Insight"
    assert seen[0][0] == f"{settings.ollama_url.rstrip('/')}/api/chat"
    assert seen[0][1]["json"]["model"] == settings.ollama_model
    assert seen[0][1]["json"]["stream"] is False
    assert "temperature" in seen[0][1]["json"]["options"]


def test_suggest_clips_requires_transcript(client):
    with SessionLocal() as db:
        project = Project(name="Analisis")
        db.add(project)
        db.flush()
        video = Video(project_id=project.id, filename="video.mp4", source_path="missing.mp4", duration=90, sha256="test")
        db.add(video)
        db.commit()
        video_id = video.id
    response = client.post(f"/api/videos/{video_id}/suggest-clips", json={"max_candidates": 5})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "transcript_required"


def test_suggest_clips_returns_ranked_candidates(client, monkeypatch):
    with SessionLocal() as db:
        project = Project(name="Analisis")
        db.add(project)
        db.flush()
        video = Video(project_id=project.id, filename="video.mp4", source_path="missing.mp4", duration=90, sha256="test")
        db.add(video)
        db.flush()
        transcript = Transcript(video_id=video.id, language="id", full_text="Contoh transkrip")
        db.add(transcript)
        db.flush()
        db.add(TranscriptSegment(transcript_id=transcript.id, start_time=0, end_time=20, text="Contoh transkrip"))
        db.commit()
        video_id, transcript_id = video.id, transcript.id

    monkeypatch.setattr(
        "app.routers.clips.clip_detection.suggest_candidates",
        lambda lines, duration, maximum: [detector.Candidate(1, 20, "Hook", "Kalimat", "Alasan", 88, "insight")],
    )
    response = client.post(f"/api/videos/{video_id}/suggest-clips", json={"max_candidates": 5})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["video_id"] == video_id
    assert body["transcript_id"] == transcript_id
    assert body["model"] == get_settings().ollama_model
    assert body["candidates"][0]["score"] == 88
    candidate = body["candidates"][0]
    saved = client.post(
        f"/api/videos/{video_id}/clips",
        json={
            "start_time": candidate["start_time"],
            "end_time": candidate["end_time"],
            "title": candidate["title"],
            "hook": candidate["hook"],
            "score": candidate["score"],
            "category": candidate["category"],
        },
    )
    assert saved.status_code == 201, saved.text
    assert saved.json()["hook"] == "Kalimat"
    assert saved.json()["score"] == 88
    assert saved.json()["category"] == "insight"
