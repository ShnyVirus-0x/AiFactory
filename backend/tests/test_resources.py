"""Batas runtime, model manager (aturan VRAM, unload), kompatibilitas CUDA, logging terstruktur."""
import json
import logging

import pytest

from app.services import gpu_monitor as gm
from app.services import model_manager as mm
from app.utils.logging import JsonFormatter


def test_limits_roundtrip_and_validation(client):
    r = client.get("/api/system/limits").json()
    assert r["compute_mode"] == "auto" and r["ai_workers"] >= 1
    r = client.put("/api/system/limits", json={"cpu_workers": 4, "compute_mode": "cpu", "vram_reserve_mb": 2048})
    assert r.status_code == 200 and r.json()["cpu_workers"] == 4 and r.json()["effective_device"] == "cpu"
    assert client.get("/api/system/limits").json()["vram_reserve_mb"] == 2048  # tersimpan di DB
    bad = client.put("/api/system/limits", json={"ai_workers": 99})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "validation_error"
    assert client.put("/api/system/limits", json={"compute_mode": "tpu"}).status_code == 422
    client.put("/api/system/limits", json={"compute_mode": "auto", "cpu_workers": 2, "vram_reserve_mb": 1024})


def test_resolve_device(monkeypatch):
    monkeypatch.setattr(mm, "cuda_available", lambda: False)
    assert mm.resolve_device("auto")[0] == "cpu"
    assert mm.resolve_device("gpu")[0] == "unavailable"
    assert mm.resolve_device("cpu")[0] == "cpu"
    monkeypatch.setattr(mm, "cuda_available", lambda: True)
    assert mm.resolve_device("auto")[0] == "cuda"


def test_model_manager_unload_and_reuse():
    m = mm.ModelManager()
    freed = []
    a = m.acquire("a", device="cpu", est_vram_mb=0, vram_reserve_mb=0, factory=lambda: object(), unloader=lambda o: freed.append(1))
    assert m.acquire("a", device="cpu", est_vram_mb=0, vram_reserve_mb=0, factory=lambda: 1 / 0) is a  # reuse, factory tidak dipanggil
    assert m.status()[0]["est_vram_mb"] == 0
    assert m.unload("a") and freed == [1] and not m.is_loaded("a") and not m.unload("a")


def test_model_manager_vram_rules(monkeypatch):
    m = mm.ModelManager()
    free = {"v": 12000}
    monkeypatch.setattr(mm.ModelManager, "_free_vram_mb", staticmethod(lambda: free["v"]))
    freed = []
    m.acquire("big1", device="cuda", est_vram_mb=6000, vram_reserve_mb=1000, factory=lambda: "x", unloader=lambda o: freed.append("big1"))
    free["v"] = 4000  # model pertama memakan VRAM
    # model kedua tidak muat -> model pertama dilepas lebih dulu
    def release(_):
        free["v"] = 12000
    m._models["big1"].unloader = lambda o: (freed.append("big1"), release(o))
    m.acquire("big2", device="cuda", est_vram_mb=7000, vram_reserve_mb=1000, factory=lambda: "y")
    assert freed == ["big1"] and m.is_loaded("big2") and not m.is_loaded("big1")
    free["v"] = 2000  # benar-benar tidak cukup
    with pytest.raises(MemoryError):
        m.acquire("huge", device="cuda", est_vram_mb=9000, vram_reserve_mb=1000, factory=lambda: "z")


def test_unload_endpoints(client):
    assert client.post("/api/system/models/nonexistent/unload").status_code == 404
    assert client.post("/api/system/models/unload-all").json() == {"unloaded": 0}


def test_cuda_compat_no_gpu(monkeypatch):
    monkeypatch.setattr(gm, "find_nvidia_smi", lambda: None)
    r = gm.cuda_compatibility()
    assert r["ok"] is False and r["gpu_present"] is False and r["reason"]


def test_cuda_compat_old_driver(monkeypatch):
    monkeypatch.setattr(gm, "query_gpus", lambda: {"available": True, "reason": None, "gpus": [{}], "cuda_version": "11.8", "driver_version": "520"})
    r = gm.cuda_compatibility()
    assert r["ok"] is False and "12" in r["reason"]


def test_health_includes_cuda_and_limits(client):
    h = client.get("/api/system/health").json()
    assert "cuda" in h and "models_loaded" in h and "compute_mode" in h["limits"]


def test_json_log_redacts_secrets():
    rec = logging.LogRecord("t", logging.INFO, "f", 1, "login api_key=ABC123 token: XYZ ok", None, None)
    out = json.loads(JsonFormatter().format(rec))
    assert "ABC123" not in out["msg"] and "XYZ" not in out["msg"] and out["level"] == "INFO"
