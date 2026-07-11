"""In-process async event bus using a handler registry.

Handlers are coroutine functions keyed by the event's exact Python type.
The bus does NOT persist events; it is suitable for in-process pub/sub within
a single Forge server process.  Swap for a Redis-backed bus in distributed
deployments.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from forge.core.domain.interfaces import IEventBus

logger = logging.getLogger(__name__)


class LocalEventBus(IEventBus):
    """Simple in-process event bus.

    Handlers are registered per event type and called in registration order.
    Exceptions raised by handlers are logged but do not interrupt other handlers.
    """

    def __init__(self) -> None:
        self._subscribers: dict[type, list[Callable]] = {}

    async def publish(self, event: Any) -> None:
        """Publish *event* to all registered handlers for its type.

        Handlers that raise exceptions have their errors logged; other
        handlers continue executing.
        """
        event_type = type(event)
        handlers = list(self._subscribers.get(event_type, []))
        for handler in handlers:
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                logger.exception(
                    "Event handler %s raised an exception for event %s",
                    getattr(handler, "__name__", repr(handler)),
                    event_type.__name__,
                )

    async def subscribe(self, event_type: type, handler: Callable) -> None:
        """Register *handler* to be called when events of *event_type* arrive.

        Duplicate registrations are ignored (same object identity check).
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        if handler not in self._subscribers[event_type]:
            self._subscribers[event_type].append(handler)
            logger.debug(
                "Subscribed %s to %s",
                getattr(handler, "__name__", repr(handler)),
                event_type.__name__,
            )

    async def unsubscribe(self, event_type: type, handler: Callable) -> None:
        """Remove *handler* from the registry for *event_type*.

        No-ops if the handler was never registered.
        """
        if event_type in self._subscribers:
            try:
                self._subscribers[event_type].remove(handler)
                logger.debug(
                    "Unsubscribed %s from %s",
                    getattr(handler, "__name__", repr(handler)),
                    event_type.__name__,
                )
            except ValueError:
                pass  # handler was not registered — ignore

    def handler_count(self, event_type: type) -> int:
        """Return the number of handlers registered for *event_type*."""
        return len(self._subscribers.get(event_type, []))
