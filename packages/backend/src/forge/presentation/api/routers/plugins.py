"""API router for plugins management endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from forge.core.container import Container
from forge.core.domain.models import PluginManifest

router = APIRouter(prefix="/plugins", tags=["plugins"])


class InstallPluginRequest(BaseModel):
    """Payload to install a plugin from a local source directory path."""

    source_path: str = Field(
        ...,
        description="Absolute local filesystem path to the plugin directory containing forge_plugin.json",
    )


def _get_container(request: Request) -> Container:
    container = getattr(request.app.state, "container", None)
    if not container:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Forge container not initialized",
        )
    return container


@router.get("", response_model=list[PluginManifest])
async def list_plugins(request: Request) -> list[PluginManifest]:
    """List all loaded/discovered plugins in the environment."""
    container = _get_container(request)
    return container.plugin_manager.list_plugins()


@router.post("/install", response_model=PluginManifest, status_code=status.HTTP_201_CREATED)
async def install_plugin(
    payload: InstallPluginRequest,
    request: Request,
) -> PluginManifest:
    """Copy and install a local plugin into the registry and load it immediately."""
    container = _get_container(request)
    src_path = Path(payload.source_path)

    if not src_path.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Source path '{payload.source_path}' does not exist",
        )

    try:
        manifest = await container.plugin_manager.install_plugin(src_path)
        # Register the newly installed plugin in the executor service
        plugin = container.plugin_manager.get_plugin(manifest.name)
        if plugin:
            container.executor_service.add_executor(plugin)
        return manifest
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to install plugin: {exc}",
        ) from exc
