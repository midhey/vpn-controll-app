"""Единый формат ошибок API.

Фронт всегда получает {"error": {"code", "message", "details"}} с человеческим
сообщением на русском. Коды — фиксированный словарь из плана.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ErrorCode(str, Enum):
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    CSRF_FAILED = "csrf_failed"
    NOT_FOUND = "not_found"
    VALIDATION_ERROR = "validation_error"
    RATE_LIMITED = "rate_limited"
    DEVICE_LIMIT_REACHED = "device_limit_reached"
    ISSUE_RESULT_EXPIRED = "issue_result_expired"
    SERVER_UNAVAILABLE = "server_unavailable"
    AGENT_UNAVAILABLE = "agent_unavailable"
    AGENT_REJECTED = "agent_rejected"
    SETUP_JOB_FAILED = "setup_job_failed"
    SECRET_REQUIRED = "secret_required"
    INTERNAL_ERROR = "internal_error"


class AppError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        status: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details or {}


def unauthorized(message: str = "Нужно войти") -> AppError:
    return AppError(ErrorCode.UNAUTHORIZED, message, status=401)


def forbidden(message: str = "Недостаточно прав") -> AppError:
    return AppError(ErrorCode.FORBIDDEN, message, status=403)


def not_found(message: str = "Не найдено") -> AppError:
    return AppError(ErrorCode.NOT_FOUND, message, status=404)


def error_body(code: ErrorCode, message: str, details: dict[str, Any] | None = None) -> dict:
    return {"error": {"code": code.value, "message": message, "details": details or {}}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status,
            content=error_body(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = [
            {"loc": list(item.get("loc", ())), "msg": item.get("msg"), "type": item.get("type")}
            for item in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=error_body(
                ErrorCode.VALIDATION_ERROR, "Неверные данные запроса", {"errors": errors}
            ),
        )
