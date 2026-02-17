from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from agent.engine.event_bus import EventBus
from agent.models.event import TimelineEvent, MonitorSource, EventCategory, EventAction
from agent.monitors.base import BaseMonitor

logger = logging.getLogger(__name__)

# Map watchdog event types to our actions
_ACTION_MAP = {
    "created": EventAction.FILE_CREATED,
    "modified": EventAction.FILE_MODIFIED,
    "deleted": EventAction.FILE_DELETED,
}


class FolderMonitor(BaseMonitor):
    """Watches folders for file changes using watchdog."""

    def __init__(
        self,
        event_bus: EventBus,
        folders: list[str] | None = None,
        recursive: bool = True,
        observer_class: Any = None,
    ) -> None:
        super().__init__(event_bus)
        self._folders = folders or []
        self._recursive = recursive
        self._observer: Any = None
        self._observer_class = observer_class
        self._bridge_queue: asyncio.Queue[TimelineEvent] = asyncio.Queue()
        self._drain_task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self) -> None:
        if self._running:
            return
        if not self._folders:
            logger.warning("FolderMonitor: no folders configured")
            return

        self._loop = asyncio.get_running_loop()
        self._running = True

        # Import watchdog lazily so tests can mock observer_class
        if self._observer_class is None:
            from watchdog.observers import Observer
            self._observer_class = Observer

        self._observer = self._observer_class()

        from watchdog.events import FileSystemEventHandler

        class _Handler(FileSystemEventHandler):
            def __init__(handler_self, monitor: FolderMonitor):
                super().__init__()
                handler_self._monitor = monitor

            def on_created(handler_self, event):
                if not event.is_directory:
                    handler_self._monitor._bridge("created", event.src_path)

            def on_modified(handler_self, event):
                if not event.is_directory:
                    handler_self._monitor._bridge("modified", event.src_path)

            def on_deleted(handler_self, event):
                if not event.is_directory:
                    handler_self._monitor._bridge("deleted", event.src_path)

            def on_moved(handler_self, event):
                if not event.is_directory:
                    src = Path(event.src_path)
                    dest = Path(event.dest_path)
                    if src.parent == dest.parent:
                        action = EventAction.FILE_RENAMED
                    else:
                        action = EventAction.FILE_MOVED
                    te = TimelineEvent(
                        source=MonitorSource.FOLDER_MONITOR,
                        category=EventCategory.FILE_SYSTEM,
                        action=action,
                        target=event.dest_path,
                        detail={"src_path": event.src_path, "dest_path": event.dest_path},
                    )
                    handler_self._monitor._enqueue(te)

        handler = _Handler(self)
        for folder in self._folders:
            self._observer.schedule(handler, folder, recursive=self._recursive)

        self._observer.start()
        self._drain_task = asyncio.create_task(self._drain_loop())
        logger.info("FolderMonitor started watching %d folders", len(self._folders))

    async def stop(self) -> None:
        self._running = False
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=2)
            self._observer = None
        if self._drain_task:
            self._drain_task.cancel()
            try:
                await self._drain_task
            except asyncio.CancelledError:
                pass
            self._drain_task = None
        logger.info("FolderMonitor stopped")

    def _bridge(self, action_key: str, path: str) -> None:
        """Called from watchdog thread — bridges to asyncio."""
        action = _ACTION_MAP.get(action_key)
        if not action:
            return
        te = TimelineEvent(
            source=MonitorSource.FOLDER_MONITOR,
            category=EventCategory.FILE_SYSTEM,
            action=action,
            target=path,
        )
        self._enqueue(te)

    def _enqueue(self, event: TimelineEvent) -> None:
        """Thread-safe enqueue into the asyncio bridge queue."""
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._bridge_queue.put_nowait, event)

    async def _drain_loop(self) -> None:
        """Drain bridge queue and publish to event bus."""
        while self._running:
            try:
                event = await asyncio.wait_for(self._bridge_queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            await self._bus.publish(event)
