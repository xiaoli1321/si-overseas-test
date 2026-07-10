import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.core.logging import log_context, request_id_var

logger = logging.getLogger(__name__)


class AppBaseException(Exception):
    message = "An unexpected error occurred."
    status_code = 500
    code = 50001

    def __init__(self, message: str | None = None, data: object | None = None) -> None:
        if message is not None:
            self.message = message
        self.data = data


class InvalidParamsError(AppBaseException):
    status_code = 400
    code = 40001
    message = "Invalid parameters."


class UnauthorizedError(AppBaseException):
    status_code = 401
    code = 40101
    message = "Unauthorized."


class ForbiddenError(AppBaseException):
    status_code = 403
    code = 40301
    message = "Forbidden."


class NotFoundError(AppBaseException):
    status_code = 404
    code = 40401
    message = "Resource not found."


class BusinessValidationError(AppBaseException):
    status_code = 422
    code = 42201
    message = "Business validation failed."


class ConflictError(AppBaseException):
    status_code = 409
    code = 40901
    message = "Conflict."


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppBaseException)
    async def app_exception_handler(
        request: Request, exc: AppBaseException
    ) -> JSONResponse:
        logger.info(
            "Application error handled",
            extra=log_context(
                "http.app_error",
                method=request.method,
                path=request.url.path,
                status_code=exc.status_code,
                error_code=exc.code,
                error_type=type(exc).__name__,
            ),
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message, "data": exc.data},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        logger.info(
            "Request validation failed",
            extra=log_context(
                "http.validation_error",
                method=request.method,
                path=request.url.path,
                status_code=422,
                error_count=len(exc.errors()),
            ),
        )
        return JSONResponse(
            status_code=422,
            content={
                "code": 40001,
                "message": "Invalid parameters.",
                "data": exc.errors(),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception(
            "Unhandled request error",
            extra=log_context(
                "http.unhandled_error",
                method=request.method,
                path=request.url.path,
                status_code=500,
                error_type=type(exc).__name__,
            ),
        )
        return JSONResponse(
            status_code=500,
            headers={"X-Request-ID": request_id_var.get() or ""},
            content={
                "code": 50001,
                "message": "An unexpected error occurred.",
                "data": None,
            },
        )
