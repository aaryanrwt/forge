"""Main entrypoint for the Forge FastAPI application."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from forge.core.config import get_settings
from forge.core.container import Container
from forge.presentation.api.middleware.error_handler import setup_exception_handlers
from forge.presentation.api.middleware.logging_middleware import LoggingMiddleware
from forge.presentation.api.middleware.request_id import RequestIDMiddleware

# Import routers
from forge.presentation.api.routers import (
    config,
    executions,
    health,
    logs,
    plugins,
    tasks,
    websocket,
)

logger = logging.getLogger("forge.api.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manages application startup and shutdown lifecycle hooks."""
    settings = get_settings()
    
    # Configure logging level
    logging.basicConfig(level=settings.log_level)
    logging.getLogger("uvicorn.access").disabled = True  # We use our own access logging

    logger.info("Initializing dependency injection container...")
    container = Container(settings=settings)
    await container.initialize()
    
    # Attach container to app state
    app.state.container = container
    
    yield
    
    logger.info("Closing dependency injection container...")
    await container.close()


def create_app() -> FastAPI:
    """FastAPI application factory."""
    settings = get_settings()

    app = FastAPI(
        title="Forge API",
        version="1.0.0",
        description="The AI Execution Layer — API Server",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # ── Middleware ──────────────────────────────────────────────────────────
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(LoggingMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Exception Handlers ──────────────────────────────────────────────────
    setup_exception_handlers(app)

    # ── Routers ─────────────────────────────────────────────────────────────
    # Standard health check
    app.include_router(health.router)

    # REST endpoints prefixed with /api/v1
    api_prefix = "/api/v1"
    app.include_router(executions.router, prefix=api_prefix)
    app.include_router(tasks.router, prefix=api_prefix)
    app.include_router(logs.router, prefix=api_prefix)
    app.include_router(config.router, prefix=api_prefix)
    app.include_router(plugins.router, prefix=api_prefix)

    # WebSocket router (no /api/v1 prefix as standard for ws)
    app.include_router(websocket.router)

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
