"""Exception handler middleware mapping custom Forge errors to HTTP response codes."""
from __future__ import annotations

import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from forge.core.domain.exceptions import (
    CircuitBreakerOpen,
    ConfigurationError,
    ExecutorError,
    ForgeError,
    InfiniteLoopDetected,
    MCPConnectionError,
    PlannerError,
    PluginError,
    RetryBudgetExhausted,
    VerificationError,
)

logger = logging.getLogger("forge.api.error")


def setup_exception_handlers(app: FastAPI) -> None:
    """Register custom exception mapping handlers on the FastAPI app."""

    @app.exception_handler(ForgeError)
    async def forge_exception_handler(request: Request, exc: ForgeError) -> JSONResponse:
        """Handle standard domain exceptions."""
        request_id = getattr(request.state, "request_id", "unknown")
        error_type = exc.__class__.__name__

        status_code = 500
        if isinstance(exc, PlannerError):
            status_code = 422
        elif isinstance(exc, ConfigurationError):
            status_code = 503
        elif isinstance(exc, CircuitBreakerOpen):
            status_code = 503
        elif isinstance(exc, InfiniteLoopDetected):
            status_code = 409
        elif isinstance(exc, RetryBudgetExhausted):
            status_code = 400
        elif isinstance(exc, PluginError):
            status_code = 400

        logger.warning(
            "[%s] Domain exception %s caught: %s",
            request_id,
            error_type,
            exc,
        )

        return JSONResponse(
            status_code=status_code,
            content={
                "error": {
                    "type": error_type,
                    "message": str(exc),
                    "request_id": request_id,
                }
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Fallback for unhandled Python standard exceptions."""
        request_id = getattr(request.state, "request_id", "unknown")
        
        logger.exception(
            "[%s] Unhandled exception occurred: %s",
            request_id,
            exc,
        )

        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "type": "InternalServerError",
                    "message": "An unexpected error occurred. Please try again later.",
                    "request_id": request_id,
                }
            },
        )
