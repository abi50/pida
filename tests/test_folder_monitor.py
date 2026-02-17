from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from agent.engine.event_bus import EventBus
from agent.models.event import EventAction, EventCategory, MonitorSource, TimelineEvent
from agent.monitors.folder_monitor import FolderMonitor


class FakeObserver:
    """Mock watchdog Observer that doesn't touch the filesystem."""

    def __init__(self):
        self.handlers: list = []
        self.started = False
        self.stopped = False

    def schedule(self, handler, path, recursive=False):
        self.handlers.append((handler, path, recursive))

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def join(self, timeout=None):
        pass


class TestFolderMonitor:
    @pytest.mark.asyncio
    async def test_start_stop(self, tmp_path):
        bus = EventBus()
        monitor = FolderMonitor(
            bus, folders=[str(tmp_path)], observer_class=FakeObserver
        )
        await bus.start()
        await monitor.start()
        assert monitor.running is True
        await monitor.stop()
        assert monitor.running is False
        await bus.stop()

    @pytest.mark.asyncio
    async def test_no_folders_warns(self):
        bus = EventBus()
        monitor = FolderMonitor(bus, folders=[], observer_class=FakeObserver)
        await monitor.start()
        assert monitor.running is False

    @pytest.mark.asyncio
    async def test_schedules_all_folders(self, tmp_path):
        bus = EventBus()
        d1 = tmp_path / "a"
        d2 = tmp_path / "b"
        d1.mkdir()
        d2.mkdir()
        obs = FakeObserver()
        monitor = FolderMonitor(
            bus, folders=[str(d1), str(d2)], observer_class=lambda: obs
        )
        await bus.start()
        await monitor.start()
        assert len(obs.handlers) == 2
        await monitor.stop()
        await bus.stop()

    @pytest.mark.asyncio
    async def test_bridge_created_event(self, tmp_path):
        bus = EventBus()
        received: list[TimelineEvent] = []

        async def collector(event: TimelineEvent):
            received.append(event)

        bus.subscribe(collector)
        monitor = FolderMonitor(
            bus, folders=[str(tmp_path)], observer_class=FakeObserver
        )
        await bus.start()
        await monitor.start()

        # Simulate watchdog calling _bridge from its thread
        monitor._bridge("created", str(tmp_path / "newfile.txt"))
        await asyncio.sleep(0.2)

        await monitor.stop()
        await bus.stop()
        assert len(received) == 1
        assert received[0].action == EventAction.FILE_CREATED
        assert "newfile.txt" in received[0].target

    @pytest.mark.asyncio
    async def test_bridge_modified_event(self, tmp_path):
        bus = EventBus()
        received: list[TimelineEvent] = []

        async def collector(event: TimelineEvent):
            received.append(event)

        bus.subscribe(collector)
        monitor = FolderMonitor(
            bus, folders=[str(tmp_path)], observer_class=FakeObserver
        )
        await bus.start()
        await monitor.start()

        monitor._bridge("modified", str(tmp_path / "file.txt"))
        await asyncio.sleep(0.2)

        await monitor.stop()
        await bus.stop()
        assert len(received) == 1
        assert received[0].action == EventAction.FILE_MODIFIED

    @pytest.mark.asyncio
    async def test_bridge_deleted_event(self, tmp_path):
        bus = EventBus()
        received: list[TimelineEvent] = []

        async def collector(event: TimelineEvent):
            received.append(event)

        bus.subscribe(collector)
        monitor = FolderMonitor(
            bus, folders=[str(tmp_path)], observer_class=FakeObserver
        )
        await bus.start()
        await monitor.start()

        monitor._bridge("deleted", str(tmp_path / "gone.txt"))
        await asyncio.sleep(0.2)

        await monitor.stop()
        await bus.stop()
        assert len(received) == 1
        assert received[0].action == EventAction.FILE_DELETED

    @pytest.mark.asyncio
    async def test_moved_same_parent_is_rename(self, tmp_path):
        bus = EventBus()
        received: list[TimelineEvent] = []

        async def collector(event: TimelineEvent):
            received.append(event)

        bus.subscribe(collector)
        monitor = FolderMonitor(
            bus, folders=[str(tmp_path)], observer_class=FakeObserver
        )
        await bus.start()
        await monitor.start()

        # Simulate rename (same parent)
        te = TimelineEvent(
            source=MonitorSource.FOLDER_MONITOR,
            category=EventCategory.FILE_SYSTEM,
            action=EventAction.FILE_RENAMED,
            target=str(tmp_path / "new_name.txt"),
            detail={
                "src_path": str(tmp_path / "old_name.txt"),
                "dest_path": str(tmp_path / "new_name.txt"),
            },
        )
        monitor._enqueue(te)
        await asyncio.sleep(0.2)

        await monitor.stop()
        await bus.stop()
        assert len(received) == 1
        assert received[0].action == EventAction.FILE_RENAMED

    @pytest.mark.asyncio
    async def test_moved_different_parent_is_move(self, tmp_path):
        bus = EventBus()
        received: list[TimelineEvent] = []

        async def collector(event: TimelineEvent):
            received.append(event)

        bus.subscribe(collector)
        monitor = FolderMonitor(
            bus, folders=[str(tmp_path)], observer_class=FakeObserver
        )
        await bus.start()
        await monitor.start()

        te = TimelineEvent(
            source=MonitorSource.FOLDER_MONITOR,
            category=EventCategory.FILE_SYSTEM,
            action=EventAction.FILE_MOVED,
            target=str(tmp_path / "sub" / "file.txt"),
            detail={
                "src_path": str(tmp_path / "file.txt"),
                "dest_path": str(tmp_path / "sub" / "file.txt"),
            },
        )
        monitor._enqueue(te)
        await asyncio.sleep(0.2)

        await monitor.stop()
        await bus.stop()
        assert len(received) == 1
        assert received[0].action == EventAction.FILE_MOVED
