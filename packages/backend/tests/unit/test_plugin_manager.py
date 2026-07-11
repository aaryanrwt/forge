"""Unit tests for PluginManager discovery, installation, and error resilience."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from forge.application.services.plugin_manager import PluginManager
from forge.core.config import ForgeSettings
from forge.core.domain.exceptions import PluginError
from forge.core.domain.models import Task, TaskStatus, TaskType


def test_scaffold_and_load_plugin(tmp_path: object) -> None:  # type: ignore[override]
    settings = ForgeSettings(
        plugins_dir=Path(tmp_path) / "plugins"  # type: ignore[attr-defined]
    )
    pm = PluginManager(settings)

    # 1. Scaffold plugin
    scaffold_path = pm.scaffold_plugin("custom-test-plugin", Path(tmp_path))  # type: ignore[attr-defined]
    assert scaffold_path.exists()
    assert (scaffold_path / "forge_plugin.json").exists()
    assert (scaffold_path / "plugin.py").exists()

    # 2. Install plugin
    async def install_and_discover():
        manifest = await pm.install_plugin(scaffold_path)
        assert manifest.name == "custom-test-plugin"
        assert len(pm.list_plugins()) == 1

        # Retrieve plugin instance
        plugin = pm.get_plugin("custom-test-plugin")
        assert plugin is not None
        assert plugin.name == "custom-test-plugin"
        assert plugin.supports(TaskType.CLI)

        # Try execution
        task = Task(
            execution_id=uuid4(),
            name="Run plugin message",
            description="",
            task_type=TaskType.CLI,
            inputs={"message": "custom message"},
        )
        task_res = await plugin.execute(task)
        assert task_res.status == TaskStatus.COMPLETED
        assert task_res.outputs["result"] == "custom message"

    import asyncio

    asyncio.run(install_and_discover())


def test_load_malformed_plugin_manifest(tmp_path: object) -> None:  # type: ignore[override]
    settings = ForgeSettings(
        plugins_dir=Path(tmp_path) / "plugins"  # type: ignore[attr-defined]
    )
    pm = PluginManager(settings)

    plugin_dir = Path(tmp_path) / "bad-plugin"  # type: ignore[attr-defined]
    plugin_dir.mkdir()

    # Write bad JSON
    with open(plugin_dir / "forge_plugin.json", "w") as f:
        f.write("{invalid-json}")

    with pytest.raises(PluginError):
        pm._load_manifest(plugin_dir / "forge_plugin.json")


def test_load_missing_entrypoint_plugin(tmp_path: object) -> None:  # type: ignore[override]
    settings = ForgeSettings(
        plugins_dir=Path(tmp_path) / "plugins"  # type: ignore[attr-defined]
    )
    pm = PluginManager(settings)

    plugin_dir = Path(tmp_path) / "missing-entry-plugin"  # type: ignore[attr-defined]
    plugin_dir.mkdir()

    manifest_data = {
        "name": "missing-entry-plugin",
        "version": "1.0.0",
        "description": "missing files",
        "author": "Community",
        "task_type": "cli",
        "entry_point": "nonexistent.py",
    }
    with open(plugin_dir / "forge_plugin.json", "w") as f:
        json.dump(manifest_data, f)

    from forge.core.domain.models import PluginManifest

    manifest = PluginManifest(**manifest_data)

    with pytest.raises(PluginError) as exc:
        pm._load_plugin(plugin_dir, manifest)
    assert "nonexistent.py" in str(exc.value)
