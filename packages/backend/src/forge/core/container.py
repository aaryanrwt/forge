"""Forge Dependency Injection Container.

Assembles and configures all core engine services, adapters, and repositories
at startup based on ForgeSettings.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from forge.core.config import ForgeSettings, get_settings
from forge.core.domain.interfaces import ILLMProvider, IExecutor
from forge.core.domain.exceptions import ConfigurationError

# Planners
from forge.application.services.planner import FallbackPlanner, RulePlanner, LLMPlanner

# Executors
from forge.application.services.executor import (
    ExecutorService,
    ShellExecutor,
    PythonExecutor,
    GitExecutor,
    DockerExecutor,
    MCPExecutor,
    ModelExecutor,
)

# Verifiers
from forge.application.services.verifier import (
    CompositeVerifier,
    TaskStatusVerifier,
    ExitCodeVerifier,
    FileExistsVerifier,
    OutputPatternVerifier,
)

# Retry Controller
from forge.application.services.retry_controller import CircuitBreakerRetryController

# Context Optimizer
from forge.application.services.context_optimizer import RollingContextOptimizer

# Memory
from forge.application.services.memory_service import MemoryService
from forge.infrastructure.repository.sqlite_repository import SQLiteMemoryRepository

# Event Bus
from forge.infrastructure.event_bus.local_event_bus import LocalEventBus

# LLM Providers
from forge.infrastructure.llm.factory import create_llm_provider

# Plugins
from forge.application.services.plugin_manager import PluginManager

# Orchestrator
from forge.application.orchestrator import Orchestrator

logger = logging.getLogger(__name__)


class Container:
    """Dependency Injection Container for wiring up all backend components."""

    def __init__(self, settings: Optional[ForgeSettings] = None) -> None:
        """Initialize and wire up all services and configurations.

        Args:
            settings: Optional ForgeSettings instance. If omitted, uses default settings.
        """
        self.settings = settings or get_settings()

        # ── 1. Core Infrastructure ──────────────────────────────────────────
        self.memory_repo = SQLiteMemoryRepository(db_url=self.settings.db_url)
        self.event_bus = LocalEventBus()
        self.context_optimizer = RollingContextOptimizer(
            max_window_size=self.settings.context_window_size
        )
        self.memory_service = MemoryService(self.memory_repo, self.context_optimizer)

        # ── 2. LLM Provider (with graceful offline fallback) ───────────────
        self.llm_provider: Optional[ILLMProvider] = None
        try:
            self.llm_provider = create_llm_provider(self.settings)
            logger.info(
                "Configured LLM provider: %s (%s)",
                self.llm_provider.provider_name,
                self.llm_provider.model_name,
            )
        except ConfigurationError as exc:
            logger.warning(
                "LLM provider initialization skipped/failed: %s. "
                "Defaulting to rule-based planning.",
                exc,
            )

        # ── 3. Planner ──────────────────────────────────────────────────────
        if self.settings.planner_type == "llm" and self.llm_provider:
            self.planner = LLMPlanner(self.llm_provider)
        elif self.settings.planner_type == "fallback" and self.llm_provider:
            self.planner = FallbackPlanner(self.llm_provider)
        else:
            self.planner = RulePlanner()
            logger.info("Using offline RulePlanner for goal decomposition.")

        # ── 4. Verifiers ────────────────────────────────────────────────────
        # Order matters: check task status, then exit code, then files, then patterns
        self.verifier = CompositeVerifier(
            verifiers=[
                TaskStatusVerifier(),
                ExitCodeVerifier(),
                FileExistsVerifier(),
                OutputPatternVerifier(),
            ]
        )

        # ── 5. Retry Controller ──────────────────────────────────────────────
        self.retry_controller = CircuitBreakerRetryController(
            initial_delay=self.settings.retry_initial_delay,
            max_delay=self.settings.retry_max_delay,
            backoff_factor=self.settings.retry_backoff_factor,
            circuit_threshold=self.settings.circuit_breaker_threshold,
            circuit_timeout=self.settings.circuit_breaker_timeout,
        )

        # ── 6. Executors ────────────────────────────────────────────────────
        executors: List[IExecutor] = [
            ShellExecutor(timeout=self.settings.shell_executor_timeout),
            PythonExecutor(timeout=self.settings.python_executor_timeout),
            GitExecutor(timeout=self.settings.git_executor_timeout),
            DockerExecutor(timeout=self.settings.docker_executor_timeout),
            MCPExecutor(),
        ]

        if self.llm_provider:
            executors.append(ModelExecutor(self.llm_provider))

        self.executor_service = ExecutorService(executors=executors)

        # ── 7. Plugin Manager ──────────────────────────────────────────────
        self.plugin_manager = PluginManager(settings=self.settings)

        # ── 8. Orchestrator ─────────────────────────────────────────────────
        self.orchestrator = Orchestrator(
            planner=self.planner,
            executor_service=self.executor_service,
            verifier=self.verifier,
            retry_controller=self.retry_controller,
            memory_repo=self.memory_repo,
            event_bus=self.event_bus,
            context_optimizer=self.context_optimizer,
            memory_service=self.memory_service,
        )

    async def initialize(self) -> None:
        """Run async startup sequence: migrate SQLite, discover plugins."""
        logger.info("Initializing Forge dependency container...")
        
        # Initialize DB schemas
        await self.memory_repo.init_db()
        
        # Discover and load plugins from ~/.forge/plugins/
        try:
            manifests = await self.plugin_manager.discover()
            for manifest in manifests:
                plugin = self.plugin_manager.get_plugin(manifest.name)
                if plugin:
                    # Register plugin as an additional executor in the executor service
                    self.executor_service.add_executor(plugin)
                    logger.info("Registered plugin executor: %s", manifest.name)
        except Exception as exc:
            logger.exception("Plugin discovery encountered an error")

        logger.info("Forge dependency container initialized.")

    async def close(self) -> None:
        """Run cleanup tasks (close DB connections, HTTP clients, etc.)."""
        logger.info("Closing Forge dependency container...")
        # Add cleanup hooks here if necessary (e.g., closing http clients inside LLM providers)
        if self.llm_provider and hasattr(self.llm_provider, "_client"):
            try:
                await self.llm_provider._client.aclose()  # type: ignore[attr-defined]
            except Exception:
                pass
        logger.info("Forge container closed.")
