"""HTTP logging middleware for FastAPI."""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("forge.api.access")


class LoggingMiddleware(BaseHTTPMiddleware):
    """Logs incoming HTTP request paths, methods, response status codes, and latencies."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start_time = time.time()
        method = request.method
        path = request.url.path
        request_id = getattr(request.state, "request_id", "unknown")

        logger.info(
            "[%s] Request: %s %s starting",
            request_id,
            method,
            path,
        )

        try:
            response = await call_next(request)
            duration = (time.time() - start_time) * 1000

            logger.info(
                "[%s] Response: %s %s completed with status %d in %.2fms",
                request_id,
                method,
                path,
                response.status_code,
                duration,
            )
            return response
        except Exception as exc:
            duration = (time.time() - start_time) * 1000
            logger.error(
                "[%s] Request %s %s failed with exception in %.2fms: %s",
                request_id,
                method,
                path,
                duration,
                exc,
                exc_info=True,
            )
            raise
