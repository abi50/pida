from __future__ import annotations

import abc
import logging

from agent.engine.event_bus import EventBus

logger = logging.getLogger(__name__)


class BaseMonitor(abc.ABC):
    """Abstract base for all monitors."""

    def __init__(self, event_bus: EventBus) -> None:
        self._bus = event_bus
        self._running = False

    @abc.abstractmethod
    async def start(self) -> None: ...

    @abc.abstractmethod
    async def stop(self) -> None: ...

    @property
    def running(self) -> bool:
        return self._running
