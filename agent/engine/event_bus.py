from __future__ import annotations

import asyncio
import logging
from typing import Callable, Awaitable

from agent.models.event import TimelineEvent

logger = logging.getLogger(__name__)

Subscriber = Callable[[TimelineEvent], Awaitable[None]]


class EventBus:
    """Async pub/sub bus for TimelineEvent objects."""

    def __init__(self, maxsize: int = 0) -> None:
        self._queue: asyncio.Queue[TimelineEvent] = asyncio.Queue(maxsize=maxsize)
        self._subscribers: list[Subscriber] = []
        self._running = False
        self._task: asyncio.Task | None = None

    # ── pub/sub ──────────────────────────────────────────

    def subscribe(self, callback: Subscriber) -> None:
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Subscriber) -> None:
        self._subscribers.remove(callback)

    async def publish(self, event: TimelineEvent) -> None:
        await self._queue.put(event)

    # ── lifecycle ────────────────────────────────────────

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._dispatch_loop())
        logger.info("EventBus started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("EventBus stopped")

    # ── internal ─────────────────────────────────────────

    async def _dispatch_loop(self) -> None:
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            for sub in self._subscribers:
                try:
                    await sub(event)
                except Exception:
                    logger.exception("Subscriber %s failed for event %s", sub, event.id)

    @property
    def running(self) -> bool:
        return self._running

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    @property
    def pending(self) -> int:
        return self._queue.qsize()
