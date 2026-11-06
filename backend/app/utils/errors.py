"""Format error terstruktur: {"error": {"code", "message", "details"}}."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

import logging

log = logging.getLogger("asf.errors")


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details


def not_found(what: str) -> AppError:
    return AppError(404, "not_found", f"{what} tidak ditemukan")


def not_available(feature: str, phase: int) -> AppError:
    return AppError(501, "not_available", f"{feature} belum tersedia (direncanakan pada Fase {phase})", {"phase": phase})


def _body(code: str, message: str, details: Any = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, e: AppError):
        return JSONResponse(_body(e.code, e.message, e.details), status_code=e.status)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, e: StarletteHTTPException):
        return JSONResponse(_body(f"http_{e.status_code}", str(e.detail)), status_code=e.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, e: RequestValidationError):
        errs = [{"field": ".".join(str(p) for p in x["loc"] if p != "body"), "message": x["msg"]} for x in e.errors()]
        return JSONResponse(_body("validation_error", "Permintaan tidak valid", errs), status_code=422)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, e: Exception):
        log.exception("Unhandled error")
        return JSONResponse(_body("internal_error", "Terjadi kesalahan internal. Periksa log server."), status_code=500)
