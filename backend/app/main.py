from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from . import __version__
from .config import get_settings
from .database import run_migrations
from .routers import clips, jobs, projects, system, transcription, videos
from .services import gpu_monitor
from .utils.errors import install_error_handlers
from .utils.events import hub
from .workers import render_worker, transcription_worker
from .utils.logging import setup_logging

setup_logging(get_settings().logs_dir)
log = logging.getLogger("asf")


async def _stats_pusher() -> None:
    """Dorong statistik sumber daya NYATA ke klien WebSocket selama ada klien yang terhubung."""
    s = get_settings()
    while True:
        await asyncio.sleep(s.stats_push_seconds)
        if hub.client_count:
            try:
                snap = await asyncio.to_thread(gpu_monitor.resource_snapshot)
                await hub.broadcast({"type": "system.stats", "data": snap})
            except Exception:  # noqa: BLE001
                log.exception("Gagal mengumpulkan statistik sistem")


@asynccontextmanager
async def lifespan(_: FastAPI):
    s = get_settings()
    s.ensure_dirs()
    await asyncio.to_thread(run_migrations)
    hub.bind_loop(asyncio.get_running_loop())
    gpu_monitor.psutil.cpu_percent(interval=None)  # inisialisasi pembacaan CPU
    await asyncio.to_thread(transcription_worker.recover_on_startup)
    await asyncio.to_thread(render_worker.recover_on_startup)
    task = asyncio.create_task(_stats_pusher())
    log.info("AI Shorts Factory %s siap di http://%s:%s", __version__, s.host, s.port)
    try:
        yield
    finally:
        task.cancel()


def _origin_allowed(origin: str | None, allowed: list[str]) -> bool:
    if not origin:  # klien non-browser (mis. uji) tidak mengirim Origin
        return True
    return origin.rstrip("/") in allowed


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="AI Shorts Factory API", version=__version__, lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=s.origins, allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"], allow_headers=["*"])
    install_error_handlers(app)

    @app.middleware("http")
    async def security_headers(request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        return resp

    for r in (system.router, projects.router, videos.router, jobs.router, transcription.router, clips.router):
        app.include_router(r, prefix="/api")

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        # cegah cross-site WebSocket hijacking: hanya Origin yang diizinkan
        if not _origin_allowed(ws.headers.get("origin"), s.origins):
            await ws.close(code=4403)
            return
        await ws.accept()
        await hub.connect(ws)
        await ws.send_json({"type": "hello", "data": {"version": __version__}})
        try:
            while True:
                await ws.receive_text()  # abaikan pesan klien; menjaga koneksi tetap terbuka
        except WebSocketDisconnect:
            pass
        finally:
            hub.disconnect(ws)

    dist = Path(s.frontend_dist)
    if (dist / "index.html").is_file():
        dist_r = dist.resolve()

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str):
            if full_path.startswith(("api/", "ws")):
                from fastapi import HTTPException

                raise HTTPException(404, "Not found")
            cand = (dist_r / full_path).resolve()
            if full_path and cand.is_file() and (dist_r in cand.parents):
                return FileResponse(cand)
            return FileResponse(dist_r / "index.html")

    return app


app = create_app()


def run() -> None:  # pragma: no cover
    import uvicorn

    s = get_settings()
    uvicorn.run("app.main:app", host=s.host, port=s.port, log_level="info")


if __name__ == "__main__":  # pragma: no cover
    run()
