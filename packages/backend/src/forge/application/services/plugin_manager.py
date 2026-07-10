"""Forge Plugin Manager — manages discovery, dynamic loading, scaffolding and installation of plugins.

Scans the plugins directory, loads JSON manifests, dynamically imports the entrypoint,
and registers plugins into the execution environment.
"""
from __future__ import annotations

import importlib.util
import json
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

from forge.core.config import ForgeSettings
from forge.core.domain.exceptions import PluginError
from forge.core.domain.interfaces import IPlugin
from forge.core.domain.models import PluginManifest, TaskType

logger = logging.getLogger(__name__)


class PluginManager:
    """Manages the Forge plugin lifecycle.

    Discovers plugins in `~/.forge/plugins/`, parses manifests, dynamically
    loads Python classes implementing `IPlugin`, installs new plugins, and scaffolds templates.
    """

    def __init__(self, settings: ForgeSettings) -> None:
        """Initialize the PluginManager.

        Args:
            settings: ForgeSettings settings instance containing the plugins directory.
        """
        self.plugins_dir = Path(settings.plugins_dir)
        self._loaded_plugins: Dict[str, IPlugin] = {}
        self._manifests: Dict[str, PluginManifest] = {}

    async def discover(self) -> List[PluginManifest]:
        """Scan the plugins directory and load all valid plugins.

        Returns a list of manifests for successfully loaded plugins.
        """
        # Ensure plugins directory exists
        self.plugins_dir.mkdir(parents=True, exist_ok=True)

        loaded_manifests: List[PluginManifest] = []
        self._loaded_plugins.clear()
        self._manifests.clear()

        for plugin_subdir in self.plugins_dir.iterdir():
            if not plugin_subdir.is_dir():
                continue

            manifest_path = plugin_subdir / "forge_plugin.json"
            if not manifest_path.exists():
                logger.warning("Directory '%s' has no forge_plugin.json manifest", plugin_subdir.name)
                continue

            try:
                manifest = self._load_manifest(manifest_path)
                plugin_instance = self._load_plugin(plugin_subdir, manifest)
                
                self._loaded_plugins[manifest.name] = plugin_instance
                self._manifests[manifest.name] = manifest
                loaded_manifests.append(manifest)
                logger.info("Successfully loaded plugin: %s v%s", manifest.name, manifest.version)
            except Exception as exc:
                logger.error("Failed to load plugin from '%s': %s", plugin_subdir, exc)

        return loaded_manifests

    def _load_manifest(self, path: Path) -> PluginManifest:
        """Read and parse the JSON manifest file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return PluginManifest(**data)
        except Exception as exc:
            raise PluginError(f"Invalid plugin manifest JSON: {exc}") from exc

    def _load_plugin(self, plugin_dir: Path, manifest: PluginManifest) -> IPlugin:
        """Dynamically import the plugin module and instantiate the class.

        Expects the module file to contain a class subclassing IPlugin.
        """
        entry_point_file = plugin_dir / manifest.entry_point
        if not entry_point_file.exists():
            raise PluginError(f"Entrypoint file '{manifest.entry_point}' not found in {plugin_dir}")

        module_name = f"forge_plugin_{manifest.name.replace('-', '_')}"

        try:
            # Add plugin directory to path so it can import local helpers
            if str(plugin_dir) not in sys.path:
                sys.path.insert(0, str(plugin_dir))

            spec = importlib.util.spec_from_file_location(module_name, entry_point_file)
            if not spec or not spec.loader:
                raise PluginError(f"Failed to create spec for '{entry_point_file}'")

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # Find a class implementing IPlugin
            plugin_class = None
            for name, attr in module.__dict__.items():
                if isinstance(attr, type) and attr is not IPlugin and issubclass(attr, IPlugin):
                    plugin_class = attr
                    break

            if not plugin_class:
                raise PluginError(f"No class implementing IPlugin found in {entry_point_file}")

            instance = plugin_class()
            return instance
        except Exception as exc:
            raise PluginError(f"Error loading python entrypoint: {exc}") from exc

    def get_plugin(self, name: str) -> Optional[IPlugin]:
        """Retrieve a loaded plugin by its name."""
        return self._loaded_plugins.get(name)

    def get_plugins_for_type(self, task_type: TaskType) -> List[IPlugin]:
        """Get all loaded plugins that claim support for *task_type*."""
        return [
            p for p in self._loaded_plugins.values() if p.supports(task_type)
        ]

    def list_plugins(self) -> List[PluginManifest]:
        """Return the manifests of all loaded plugins."""
        return list(self._manifests.values())

    @staticmethod
    def scaffold_plugin(name: str, output_dir: Path) -> Path:
        """Generate template files for a new plugin.

        Creates directory structure, forge_plugin.json, plugin.py, and README.md.
        """
        plugin_dir = output_dir / name
        plugin_dir.mkdir(parents=True, exist_ok=True)

        manifest_data = {
            "name": name,
            "version": "1.0.0",
            "description": f"Scaffolded template for {name}",
            "author": "Community",
            "task_type": "cli",
            "entry_point": "plugin.py",
        }

        # Write manifest
        with open(plugin_dir / "forge_plugin.json", "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2)

        # Write plugin template
        plugin_code = f'''"""Template plugin for Forge.

Generated by Forge CLI.
"""
from datetime import datetime
from forge.core.domain.interfaces import IPlugin
from forge.core.domain.models import Task, TaskType, TaskStatus


class {name.replace("-", " ").title().replace(" ", "")}Plugin(IPlugin):
    """Template execution plugin."""

    @property
    def name(self) -> str:
        return "{name}"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "Auto-generated plugin"

    @property
    def task_type(self) -> TaskType:
        return TaskType.CLI

    def supports(self, task_type: TaskType) -> bool:
        return task_type == self.task_type

    async def execute(self, task: Task) -> Task:
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.utcnow()

        try:
            # Implement custom plugin business logic here
            input_val = task.inputs.get("message", "Hello from {name}")
            task.outputs = {{"result": input_val, "status": "success"}}
            task.status = TaskStatus.COMPLETED
        except Exception as exc:
            task.status = TaskStatus.FAILED
            task.error = str(exc)
        finally:
            task.completed_at = datetime.utcnow()

        return task
'''
        with open(plugin_dir / "plugin.py", "w", encoding="utf-8") as f:
            f.write(plugin_code)

        # Write README
        readme_content = f"# {name}\n\nThis is a scaffolded Forge plugin directory.\n"
        with open(plugin_dir / "README.md", "w", encoding="utf-8") as f:
            f.write(readme_content)

        return plugin_dir

    async def install_plugin(self, source_path: Path) -> PluginManifest:
        """Copy a plugin directory into the runtime plugin registry and discover it.

        Args:
            source_path: Path to the directory containing forge_plugin.json.
        """
        if not source_path.exists() or not source_path.is_dir():
            raise PluginError(f"Source plugin directory '{source_path}' does not exist")

        manifest_path = source_path / "forge_plugin.json"
        if not manifest_path.exists():
            raise PluginError(f"Directory '{source_path}' contains no forge_plugin.json manifest")

        manifest = self._load_manifest(manifest_path)
        dest_dir = self.plugins_dir / manifest.name

        # Overwrite/install directory
        if dest_dir.exists():
            shutil.rmtree(dest_dir)

        shutil.copytree(source_path, dest_dir)
        logger.info("Plugin files copied to %s", dest_dir)

        # Re-discover to load it immediately
        await self.discover()
        return manifest
