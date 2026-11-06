"""Fase 2. Catatan jujur tentang cakupan:
- Ekstraksi audio dan FFprobe: NYATA (FFmpeg sungguhan).
- Inferensi Whisper: TIDAK diuji di sini (sandbox tak bisa mengunduh model). Antarmuka `Transcriber` diganti test-double
  yang menghasilkan segmen+kata deterministik; adaptor faster-whisper diuji dengan model tiruan (tanpa inferensi).
"""
import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from app.config import get_settings
from app.services import subtitle_export as ex
from app.services import transcription as tx
from app.services import whisper_models as wm
from app.services.transcription import Seg, TranscribeResult, Word


def W(t0, t1, w):
    return Word(t0, t1, w, 0.9)


def sample_segs():
    words = [W(0.0, 0.4, "Halo"), W(0.4, 0.9, "semua."), W(1.0, 1.4, "Hari"), W(1.4, 1.7, "ini"), W(1.7, 2.2, "kita"), W(2.2, 2.8, "bahas,"),
             W(2.8, 3.4, "Python"), W(5.0, 5.5, "menarik"), W(5.5, 6.0, "sekali!")]
    return [Seg(0.0, 6.0, "Halo semua. Hari ini kita bahas, Python menarik sekali!", words)]


# ---------------- pemisahan kalimat ----------------
def test_split_sentences_on_punctuation_and_pause():
    out = list(tx.split_sentences(sample_segs()))
    assert [s.text for s in out] == ["Halo semua.", "Hari ini kita bahas, Python", "menarik sekali!"]  # jeda 1.6s memisahkan "Python | menarik"
    assert out[0].start == 0.0 and out[0].end == 0.9 and out[2].start == 5.0
    assert not tx.validate_timestamps(out, 6.0)


def test_split_sentences_long_run_splits_at_comma():
    words = [W(i * 0.5, i * 0.5 + 0.45, f"k{i}" + ("," if i == 14 else "")) for i in range(40)]  # 20 detik tanpa titik
    out = list(tx.split_sentences([Seg(0, 20, "x", words)], max_duration=12.0, max_words=28))
    assert len(out) >= 2 and all((s.end - s.start) <= 12.5 for s in out)
    assert sum(len(s.words) for s in out) == 40  # tidak ada kata hilang / ganda
    assert out[0].words[-1].word.endswith(",")


def test_segments_without_words_pass_through_and_empty_dropped():
    out = list(tx.split_sentences([Seg(0, 2, "tanpa kata", []), Seg(2, 3, "  ", [])]))
    assert len(out) == 1 and out[0].text == "tanpa kata"


def test_validate_timestamps_detects_problems():
    bad = [Seg(0, 2, "a", [W(0, 3, "a")]), Seg(1.0, 0.5, "b"), Seg(0, 99, "c")]
    issues = tx.validate_timestamps(bad, 10.0)
    assert any("di luar segmen" in i for i in issues) and any("end < start" in i for i in issues) and any("melewati durasi" in i for i in issues)


# ---------------- ekspor ----------------
class S:
    def __init__(self, a, b, t):
        self.start_time, self.end_time, self.text = a, b, t


def test_srt_vtt_txt_format():
    segs = [S(0, 1.5, "Halo dunia"), S(3661.007, 3663.5, "Baris kedua --> aman"), S(5, 6, "   ")]
    srt = ex.to_srt(segs)
    assert srt.startswith("1\n00:00:00,000 --> 00:00:01,500\nHalo dunia\n")
    assert "2\n01:01:01,007 --> 01:01:03,500\nBaris kedua → aman" in srt and "3\n" not in srt  # segmen kosong dilewati, '-->' dinetralkan
    vtt = ex.to_vtt(segs)
    assert vtt.startswith("WEBVTT\n") and "00:00:00.000 --> 00:00:01.500" in vtt
    assert ex.to_txt(segs) == "Halo dunia\nBaris kedua → aman\n"


def test_wrap_never_drops_text():
    t = "satu dua tiga empat lima enam tujuh delapan sembilan sepuluh sebelas dua belas tiga belas"
    w = ex.wrap(t, 20, 2)
    assert w.count("\n") == 1 and w.replace("\n", " ").split() == t.split()


# ---------------- audio (FFmpeg nyata) ----------------
def _probe(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,channels,sample_rate:format=duration", "-of", "json", str(p)],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def test_extract_audio_16k_mono_and_duration(sample_video, tmp_path):
    out = tmp_path / "a.wav"
    tx.extract_audio(sample_video, out)
    j = _probe(out)
    st = j["streams"][0]
    assert st["codec_name"] == "pcm_s16le" and st["channels"] == 1 and st["sample_rate"] == "16000"
    assert abs(float(j["format"]["duration"]) - 6.0) < 0.15  # akurasi durasi/timestamp audio


def test_extract_audio_no_audio_track(tmp_path):
    from tests.conftest import make_video

    v = make_video(tmp_path / "mute.mp4", 2, audio=False)
    with pytest.raises(tx.TranscriptionError):
        tx.extract_audio(v, tmp_path / "x.wav")
    assert not (tmp_path / "x.wav").exists()


# ---------------- model & unduhan ----------------
@pytest.fixture()
def clean_models():
    d = get_settings().whisper_dir
    yield d
    for p in d.glob("*"):
        shutil.rmtree(p, ignore_errors=True)
    wm.downloads._state.clear()


def _fake_install(name="tiny"):
    d = wm.model_dir(name)
    d.mkdir(parents=True, exist_ok=True)
    (d / "config.json").write_text("{}")
    (d / "model.bin").write_bytes(b"0" * 1024)


def _wait(client, url, done=("done", "failed", "cancelled"), t=10):
    end = time.time() + t
    while time.time() < end:
        j = client.get(url).json()
        if j["status"] in done:
            return j
        time.sleep(0.05)
    raise AssertionError(f"timeout: {j}")


def test_model_listing_and_confirmation_required(client, clean_models):
    ms = {m["name"]: m for m in client.get("/api/transcription/models").json()}
    assert ms["large-v3-turbo"]["default"] and not ms["large-v3-turbo"]["installed"] and ms["large-v3-turbo"]["size_is_estimate"]
    r = client.post("/api/transcription/models/large-v3-turbo/download", json={})
    assert r.status_code == 400 and r.json()["error"]["code"] == "confirmation_required"
    assert "MB" in r.json()["error"]["message"]
    assert client.post("/api/transcription/models/nope/download", json={"confirm": True}).status_code == 404


def test_download_success_is_atomic_and_never_overwrites(client, clean_models, monkeypatch):
    def fake_dl(repo, dest: Path):
        assert repo == wm.CATALOG["tiny"].repo and dest.name.endswith(".partial")
        (dest / "config.json").write_text("{}")
        (dest / "model.bin").write_bytes(b"1" * 2048)

    real_start = wm.DownloadManager.start
    monkeypatch.setattr(wm.DownloadManager, "start", lambda self, name, downloader=None: real_start(self, name, fake_dl))
    assert client.post("/api/transcription/models/tiny/download", json={"confirm": True}).status_code == 202
    end = time.time() + 5
    while time.time() < end and wm.downloads.state("tiny")["status"] == "downloading":
        time.sleep(0.05)
    assert wm.downloads.state("tiny")["status"] == "done" and wm.is_installed("tiny")
    assert not wm.model_dir("tiny").with_name("tiny.partial").exists()
    r = client.post("/api/transcription/models/tiny/download", json={"confirm": True})
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_installed"


def test_download_failure_leaves_no_partial_model(client, clean_models, monkeypatch):
    def bad(repo, dest):
        (dest / "model.bin").write_bytes(b"partial")
        raise ConnectionError("putus")

    real_start = wm.DownloadManager.start
    monkeypatch.setattr(wm.DownloadManager, "start", lambda self, name, downloader=None: real_start(self, name, bad))
    client.post("/api/transcription/models/base/download", json={"confirm": True})
    end = time.time() + 5
    while time.time() < end and wm.downloads.state("base")["status"] == "downloading":
        time.sleep(0.05)
    st = wm.downloads.state("base")
    assert st["status"] == "failed" and "ConnectionError" in st["error"]
    assert not wm.is_installed("base") and not wm.model_dir("base").with_name("base.partial").exists()


def test_download_refused_when_disk_too_small(client, clean_models, monkeypatch):
    class U:
        free = 10 * 1024 * 1024

    monkeypatch.setattr(wm.shutil, "disk_usage", lambda p: U)
    r = client.post("/api/transcription/models/large-v3-turbo/download", json={"confirm": True})
    assert r.status_code == 507 and r.json()["error"]["code"] == "insufficient_storage"


# ---------------- adaptor faster-whisper (model tiruan, TANPA inferensi) ----------------
def test_fasterwhisper_adapter_with_stub_model(clean_models, tmp_path):
    from app.services.model_manager import manager

    _fake_install("tiny")
    calls = {}

    class StubWord:
        def __init__(self, s, e, w):
            self.start, self.end, self.word, self.probability = s, e, w, 0.8

    class StubSeg:
        start, end, text = 0.0, 1.0, " Halo dunia "
        words = [StubWord(0.0, 0.5, " Halo"), StubWord(0.5, 1.0, " dunia")]

    class StubInfo:
        language, language_probability, duration = "id", 0.97, 1.0

    class StubModel:
        def transcribe(self, audio, **kw):
            calls.update(kw)
            return iter([StubSeg()]), StubInfo()

    t = tx.FasterWhisperTranscriber("tiny", "cpu", 0, model_factory=lambda path, device, compute_type: (calls.update(path=path, device=device, compute=compute_type), StubModel())[1])
    res = t.transcribe(tmp_path / "a.wav", None)
    segs = list(res.segments)
    assert res.language == "id" and segs[0].text == "Halo dunia" and segs[0].words[1].word == " dunia"
    assert calls["word_timestamps"] is True and calls["vad_filter"] is True and calls["compute"] == "int8" and calls["language"] is None
    assert manager.is_loaded("whisper:tiny")
    assert manager.unload("whisper:tiny")


def test_adapter_requires_installed_model(clean_models):
    with pytest.raises(tx.TranscriptionError, match="belum diunduh"):
        tx.FasterWhisperTranscriber("small", "cpu", 0)


def test_make_transcriber_gpu_mode_unavailable(monkeypatch):
    from app.services import model_manager as mm

    monkeypatch.setattr(mm, "cuda_available", lambda: False)
    with pytest.raises(tx.TranscriptionError, match="Mode GPU"):
        tx.make_transcriber("tiny", "gpu", 0)


# ---------------- alur end-to-end dengan test-double Transcriber ----------------
class FakeTx:
    device, model_name = "cpu", "tiny"

    def __init__(self, segs=None, fail=None, delay=0.0):
        self.segs, self.fail, self.delay = segs if segs is not None else sample_segs(), fail, delay

    def transcribe(self, audio, language):
        assert Path(audio).exists() and Path(audio).suffix == ".wav"
        self.language = language
        if self.fail:
            raise self.fail

        def gen():
            for s in self.segs:
                time.sleep(self.delay)
                yield s

        return TranscribeResult("id", 0.98, 6.0, gen())


@pytest.fixture()
def video(client, project, sample_video):
    r = client.post("/api/videos/upload", data={"project_id": project}, files=[("files", ("kuliah.mp4", sample_video.read_bytes(), "video/mp4"))])
    assert r.status_code == 201, r.text
    return r.json()["items"][0]["video"]["id"]


def _patch(monkeypatch, fake):
    monkeypatch.setattr(tx, "make_transcriber", lambda *a, **k: fake)


def test_transcribe_validations(client, video, clean_models):
    r = client.post(f"/api/videos/{video}/transcribe", json={"model": "tiny"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "model_not_installed"
    _fake_install("tiny")
    assert client.post(f"/api/videos/{video}/transcribe", json={"model": "tiny", "language": "Indonesia!"}).status_code == 422
    assert client.post(f"/api/videos/{video}/transcribe", json={"model": "tiny", "audio_track": 3}).status_code == 422
    assert client.post("/api/videos/xxxx/transcribe", json={"model": "tiny"}).status_code == 404


def test_full_flow_edit_search_export(client, video, clean_models, monkeypatch):
    _install = _fake_install("tiny")
    fake = FakeTx()
    _patch(monkeypatch, fake)
    r = client.post(f"/api/videos/{video}/transcribe", json={"model": "tiny", "language": "id"})
    assert r.status_code == 202
    job = _wait(client, f"/api/transcription/jobs/{r.json()['id']}")
    assert job["status"] == "done" and job["progress"] == 1.0 and job["device"] == "cpu" and fake.language == "id"
    assert not list(get_settings().cache_dir.glob("asr-*.wav"))  # WAV sementara dibersihkan

    trs = client.get(f"/api/videos/{video}/transcripts").json()
    assert len(trs) == 1 and trs[0]["segment_count"] == 3 and trs[0]["language"] == "id"
    tid = trs[0]["id"]
    full = client.get(f"/api/transcripts/{tid}").json()
    assert [s["text"] for s in full["segments"]] == ["Halo semua.", "Hari ini kita bahas, Python", "menarik sekali!"]

    # cari (termasuk karakter khusus LIKE)
    assert client.get(f"/api/transcripts/{tid}", params={"q": "PYTHON"}).json()["total_matches"] == 1
    assert client.get(f"/api/transcripts/{tid}", params={"q": "%"}).json()["total_matches"] == 0

    # edit teks: timing kata menjadi perkiraan dan ditandai
    sid = full["segments"][1]["id"]
    p = client.patch(f"/api/transcripts/segments/{sid}", json={"text": "Hari ini kita bahas Django"})
    assert p.status_code == 200 and p.json()["edited"] and p.json()["words_estimated"]
    # waktu tidak valid
    assert client.patch(f"/api/transcripts/segments/{sid}", json={"start_time": 5, "end_time": 4}).status_code == 422
    assert client.patch(f"/api/transcripts/segments/{sid}", json={"end_time": 999}).status_code == 422

    # cari-ganti
    assert client.post(f"/api/transcripts/{tid}/replace", json={"find": "django", "replace": "FastAPI"}).json() == {"replaced": 1}
    assert client.post(f"/api/transcripts/{tid}/replace", json={"find": "", "replace": "x"}).status_code == 422

    # pisah & gabung
    parts = client.post(f"/api/transcripts/segments/{sid}/split", json={"word_index": 1}).json()
    assert [x["text"] for x in parts] == ["Hari ini", "kita bahas FastAPI"] and parts[0]["end_time"] <= parts[1]["start_time"] + 1e-6
    assert client.post(f"/api/transcripts/segments/{sid}/split", json={"word_index": 50}).status_code == 422
    m = client.post(f"/api/transcripts/segments/{sid}/merge-next").json()
    assert m["text"] == "Hari ini kita bahas FastAPI"

    # hapus segmen terakhir lalu ekspor
    last = client.get(f"/api/transcripts/{tid}").json()["segments"][-1]["id"]
    assert client.delete(f"/api/transcripts/segments/{last}").status_code == 204
    srt = client.get(f"/api/transcripts/{tid}/export", params={"format": "srt"})
    assert srt.status_code == 200 and "00:00:00,000 --> 00:00:00,900\nHalo semua." in srt.text and "menarik" not in srt.text
    assert 'filename="kuliah.id.srt"' in srt.headers["content-disposition"]
    assert client.get(f"/api/transcripts/{tid}/export", params={"format": "vtt"}).text.startswith("WEBVTT")
    assert "FastAPI" in client.get(f"/api/transcripts/{tid}/export", params={"format": "txt"}).text
    assert client.get(f"/api/transcripts/{tid}/export", params={"format": "exe"}).status_code == 422

    # transkrip baru tidak menimpa yang lama
    j2 = _wait(client, f"/api/transcription/jobs/{client.post(f'/api/videos/{video}/transcribe', json={'model': 'tiny'}).json()['id']}")
    assert j2["status"] == "done" and len(client.get(f"/api/videos/{video}/transcripts").json()) == 2
    assert client.delete(f"/api/transcripts/{tid}").status_code == 204


def test_failed_job_leaves_no_partial_transcript(client, video, clean_models, monkeypatch):
    _fake_install("tiny")
    _patch(monkeypatch, FakeTx(fail=RuntimeError("CUDA out of memory")))
    jid = client.post(f"/api/videos/{video}/transcribe", json={"model": "tiny"}).json()["id"]
    job = _wait(client, f"/api/transcription/jobs/{jid}")
    assert job["status"] == "failed" and "CUDA out of memory" in job["error_message"]
    assert client.get(f"/api/videos/{video}/transcripts").json() == []
    assert client.post(f"/api/transcription/jobs/{jid}/cancel").status_code == 409  # sudah selesai


def test_failure_midway_drops_partial_segments(client, video, clean_models, monkeypatch):
    _fake_install("tiny")

    def broken():
        yield Seg(0, 1, "satu.", [W(0, 1, "satu.")])
        raise RuntimeError("putus di tengah")

    class Mid(FakeTx):
        def transcribe(self, audio, language):
            return TranscribeResult("id", 0.9, 6.0, broken())

    _patch(monkeypatch, Mid())
    jid = client.post(f"/api/videos/{video}/transcribe", json={"model": "tiny"}).json()["id"]
    assert _wait(client, f"/api/transcription/jobs/{jid}")["status"] == "failed"
    assert client.get(f"/api/videos/{video}/transcripts").json() == []


def test_cancel_running_job(client, video, clean_models, monkeypatch):
    _fake_install("tiny")
    many = [Seg(i, i + 0.9, f"kalimat {i}.", [W(i, i + 0.9, f"kalimat{i}.")]) for i in range(5)]
    _patch(monkeypatch, FakeTx(segs=many, delay=0.4))
    jid = client.post(f"/api/videos/{video}/transcribe", json={"model": "tiny"}).json()["id"]
    assert client.post(f"/api/videos/{video}/transcribe", json={"model": "tiny"}).status_code == 409  # sudah ada job aktif
    _wait(client, f"/api/transcription/jobs/{jid}", done=("running",))
    time.sleep(0.5)
    assert client.post(f"/api/transcription/jobs/{jid}/cancel").status_code == 200
    assert _wait(client, f"/api/transcription/jobs/{jid}")["status"] == "cancelled"
    assert client.get(f"/api/videos/{video}/transcripts").json() == []


def test_recover_on_startup_marks_orphans_failed(client, video, clean_models):
    from app.database import SessionLocal
    from app.models import TranscriptionJob
    from app.workers import transcription_worker as w

    with SessionLocal() as db:
        j = TranscriptionJob(video_id=video, status="running", model="tiny")
        db.add(j)
        db.commit()
        jid = j.id
    w.recover_on_startup()
    j = client.get(f"/api/transcription/jobs/{jid}").json()
    assert j["status"] == "failed" and "ditutup" in j["error_message"]
