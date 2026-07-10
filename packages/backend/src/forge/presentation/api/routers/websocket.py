"""WebSocket router for streaming real-time execution events."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List
from uuid import UUID
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from forge.core.container import Container
from forge.core.domain.events import (
    ExecutionStartedEvent,
    ExecutionCompletedEvent,
    ExecutionCancelledEvent,
    ExecutionResumedEvent,
    TaskStartedEvent,
    TaskCompletedEvent,
    TaskFailedEvent,
    TaskRetriedEvent,
    VerificationCompletedEvent,
    LogEntryEvent,
)

logger = logging.getLogger("forge.api.websocket")

router = APIRouter(prefix="/ws", tags=["websocket"])


@router.websocket("/executions/{execution_id}")
async def execution_events_ws(websocket: WebSocket, execution_id: UUID) -> None:
    """Stream execution lifecycle events in real time to the connected client."""
    await websocket.accept()
    logger.info("WebSocket connection accepted for execution %s", execution_id)

    container: Container = getattr(websocket.app.state, "container")
    event_queue: asyncio.Queue[Any] = asyncio.Queue()

    # Define a single handler that puts matching events in the queue
    async def make_handler(event_type: type):
        async def handler(event: Any) -> None:
            # Check if event has a matching execution_id
            event_exec_id = getattr(event, "execution_id", None)
            if event_exec_id == execution_id:
                # Place event in the queue
                await event_queue.put({
                    "event_type": event.__class__.__name__,
                    "timestamp": event.timestamp.isoformat(),
                    "data": event.model_dump(mode="json"),
                })
        return handler

    # List of event types to monitor
    monitored_events = [
        ExecutionStartedEvent,
        ExecutionCompletedEvent,
        ExecutionCancelledEvent,
        ExecutionResumedEvent,
        TaskStartedEvent,
        TaskCompletedEvent,
        TaskFailedEvent,
        TaskRetriedEvent,
        VerificationCompletedEvent,
        LogEntryEvent,
    ]

    # Create handler instances and subscribe
    handlers_map = {}
    for et in monitored_events:
        h = await make_handler(et)
        handlers_map[et] = h
        await container.event_bus.subscribe(et, h)

    # Task to read from queue and send over websocket
    async def writer():
        try:
            while True:
                event_data = await event_queue.get()
                await websocket.send_json(event_data)
                event_queue.task_done()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.debug("WS writer task exception: %s", exc)

    writer_task = asyncio.create_task(writer())

    try:
        # Keep connection open and listen for close
        while True:
            # Keep-alive ping/pong or wait for client messages (we discard incoming)
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for execution %s", execution_id)
    finally:
        # Cancel writer task
        writer_task.cancel()
        
        # Unsubscribe handlers to avoid memory leak
        for et, h in handlers_map.items():
            try:
                await container.event_bus.unsubscribe(et, h)
            except Exception:
                pass
