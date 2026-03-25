# taskflow/events.py

"""Task event fan-out.

A task event starts wherever the task ran and has to reach every browser
that cares, which may be connected to a different process entirely. In one
process a direct call is enough; once workers and api are separate
containers, the event has to travel between them, which is what
RedisEventBus is for - without it a task executed on worker #3 would never
reach a dashboard connected to api #1, and the UI would just sit there.

Only one channel is used, carrying every event. Per-task channels would
save an api replica from receiving events it has no subscriber for, but
every replica serving the dashboard needs all events anyway, so the
filtering is done locally against the connections this process actually
holds (see ConnectionManager) rather than by Redis routing.
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import Awaitable, Callable, Optional

from .core.task import Task

logger = logging.getLogger(__name__)

EVENT_CHANNEL = "taskflow:events"

EventHandler = Callable[[dict], Awaitable[None]]


def build_event_message(event_type: str, task: Task) -> dict:
    """The payload WebSocket clients receive.

    Built in one place so the in-process and Redis paths cannot drift into
    sending subtly different shapes for the same event.
    """
    return {
        "type": event_type,
        "task": task.to_dict(),
        "timestamp": (
            task.completed_at.isoformat()
            if task.completed_at
            else task.created_at.isoformat()
        ),
    }


class EventBus(ABC):
    @abstractmethod
    async def publish(self, event_type: str, task: Task) -> None:
        """Emit a task event."""

    @abstractmethod
    async def start(self, handler: EventHandler) -> None:
        """Begin delivering incoming events to `handler`."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop delivering and release resources."""


class LocalEventBus(EventBus):
    """Straight in-process call. Correct only while one process both runs
    the workers and holds the WebSocket connections."""

    def __init__(self) -> None:
        self._handler: Optional[EventHandler] = None

    async def start(self, handler: EventHandler) -> None:
        self._handler = handler

    async def publish(self, event_type: str, task: Task) -> None:
        if self._handler is None:
            return
        await self._handler(build_event_message(event_type, task))

    async def stop(self) -> None:
        self._handler = None


class RedisEventBus(EventBus):
    """Fan-out over Redis pub/sub, so any process can emit and every api
    process delivers to its own WebSocket clients."""

    def __init__(self, redis_url: str, channel: str = EVENT_CHANNEL):
        import redis.asyncio as aioredis

        self._redis = aioredis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=3,
        )
        self._channel = channel
        self._pubsub = None
        self._reader: Optional[asyncio.Task] = None

    async def publish(self, event_type: str, task: Task) -> None:
        message = build_event_message(event_type, task)
        try:
            await self._redis.publish(self._channel, json.dumps(message))
        except Exception as e:
            # Losing an event degrades the live UI; it must never take the
            # task down with it, so this is logged rather than raised.
            logger.error(f"Failed to publish {event_type} for {task.task_id}: {e}")

    async def start(self, handler: EventHandler) -> None:
        self._pubsub = self._redis.pubsub()
        await self._pubsub.subscribe(self._channel)
        self._reader = asyncio.create_task(self._read_loop(handler))
        logger.info(f"Subscribed to Redis events on {self._channel}")

    async def _read_loop(self, handler: EventHandler) -> None:
        try:
            async for raw in self._pubsub.listen():
                if raw.get("type") != "message":
                    continue
                try:
                    await handler(json.loads(raw["data"]))
                except Exception as e:
                    logger.error(f"Error handling event: {e}", exc_info=True)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Event subscription failed: {e}", exc_info=True)

    async def stop(self) -> None:
        if self._reader:
            self._reader.cancel()
            try:
                await self._reader
            except asyncio.CancelledError:
                pass
            self._reader = None
        if self._pubsub:
            await self._pubsub.aclose()
            self._pubsub = None
        await self._redis.aclose()
