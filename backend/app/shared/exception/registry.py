"""Process-wide exception registry with stable, machine-readable error codes."""

import logging
from typing import ClassVar, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class ExceptionRegistry:
    """Map domain exceptions to HTTP status codes and stable error strings."""

    _map: ClassVar[dict[type[Exception], tuple[int, str]]] = {}

    @classmethod
    def register(cls, exc_class: type[Exception], status_code: int, error_code: str) -> None:
        """Register one exception mapping."""
        cls._map[exc_class] = (status_code, error_code)

    @classmethod
    def resolve(cls, exc: Exception) -> tuple[int, str]:
        """Resolve the closest registered class in the MRO."""
        for exc_type in type(exc).__mro__:
            if exc_type in cls._map:
                return cls._map[exc_type]
        return 500, "internal_error"

    @classmethod
    def setup_app(cls, app: FastAPI) -> None:
        """Install one JSON error envelope for every registered exception."""

        async def handle(_request: Request, exc: Exception) -> JSONResponse:
            status, error_code = cls.resolve(exc)
            if status >= 500:
                logger.exception("%s: %s", exc.__class__.__name__, exc)
            else:
                logger.info("%s: %s", exc.__class__.__name__, exc)
            detail = str(exc) if str(exc) else error_code
            return JSONResponse(
                status_code=status,
                content={"status": status, "error": error_code, "detail": detail},
            )

        async def handle_validation(
            _request: Request,
            exc: Exception,
        ) -> JSONResponse:
            validation_error = cast(RequestValidationError, exc)
            messages = []
            for error in validation_error.errors():
                location = ".".join(str(part) for part in error.get("loc", ()))
                messages.append(f"{location}: {error.get('msg', 'invalid value')}")
            detail = "; ".join(messages) or "Request validation failed."
            return JSONResponse(
                status_code=400,
                content={"status": 400, "error": "invalid_request", "detail": detail},
            )

        async def handle_http(_request: Request, exc: Exception) -> JSONResponse:
            http_error = cast(StarletteHTTPException, exc)
            code = "not_found" if http_error.status_code == 404 else "http_error"
            return JSONResponse(
                status_code=http_error.status_code,
                content={
                    "status": http_error.status_code,
                    "error": code,
                    "detail": str(http_error.detail),
                },
            )

        for exc_class in cls._map:
            app.add_exception_handler(exc_class, handle)
        app.add_exception_handler(RequestValidationError, handle_validation)
        app.add_exception_handler(StarletteHTTPException, handle_http)
        app.add_exception_handler(Exception, handle)
