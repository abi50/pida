from __future__ import annotations

import asyncio

import pytest

from agent.engine.event_bus import EventBus
from agent.models.event import TimelineEvent, MonitorSource, EventCategory, EventAction


def _make_event(**kwargs) -> TimelineEvent:
    defaults = dict(
        source=MonitorSource.FOLDER_MONITOR,
        category=EventCategory.FILE_SYSTEM,
        action=EventAction.FILE_CREATED,
        target="/tmp/test.txt",
    )
    defaults.update(kwargs)
    return TimelineEvent(**defaults)


class TestEventBus:
    @pytest.mark.asyncio
    async def test_start_stop(self):
        bus = EventBus()
        await bus.start()
        assert bus.running is True
        await bus.stop()
        assert bus.running is False

    @pytest.mark.asyncio
    async def test_publish_dispatches_to_subscriber(self):
        bus = EventBus()
        received: list[TimelineEvent] = []

        async def handler(event: TimelineEvent):
            received.append(event)

        bus.subscribe(handler)
        await bus.start()
        event = _make_event()
        await bus.publish(event)
        await asyncio.sleep(0.1)
        await bus.stop()
        assert len(received) == 1
        assert received[0].id == event.id

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self):
        bus = EventBus()
        results_a: list[str] = []
        results_b: list[str] = []

        async def handler_a(event: TimelineEvent):
            results_a.append(event.id)

        async def handler_b(event: TimelineEvent):
            results_b.append(event.id)

        bus.subscribe(handler_a)
        bus.subscribe(handler_b)
        await bus.start()
        await bus.publish(_make_event())
        await asyncio.sleep(0.1)
        await bus.stop()
        assert len(results_a) == 1
        assert len(results_b) == 1

    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        bus = EventBus()
        received: list[TimelineEvent] = []

        async def handler(event: TimelineEvent):
            received.append(event)

        bus.subscribe(handler)
        bus.unsubscribe(handler)
        await bus.start()
        await bus.publish(_make_event())
        await asyncio.sleep(0.1)
        await bus.stop()
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_subscriber_error_does_not_crash_bus(self):
        bus = EventBus()
        good_results: list[str] = []

        async def bad_handler(event: TimelineEvent):
            raise RuntimeError("boom")

        async def good_handler(event: TimelineEvent):
            good_results.append(event.id)

        bus.subscribe(bad_handler)
        bus.subscribe(good_handler)
        await bus.start()
        await bus.publish(_make_event())
        await asyncio.sleep(0.1)
        await bus.stop()
        assert len(good_results) == 1

    @pytest.mark.asyncio
    async def test_multiple_events(self):
        bus = EventBus()
        received: list[TimelineEvent] = []

        async def handler(event: TimelineEvent):
            received.append(event)

        bus.subscribe(handler)
        await bus.start()
        for _ in range(5):
            await bus.publish(_make_event())
        await asyncio.sleep(0.2)
        await bus.stop()
        assert len(received) == 5

    @pytest.mark.asyncio
    async def test_subscriber_count(self):
        bus = EventBus()

        async def h1(e): pass
        async def h2(e): pass

        assert bus.subscriber_count == 0
        bus.subscribe(h1)
        assert bus.subscriber_count == 1
        bus.subscribe(h2)
        assert bus.subscriber_count == 2
        bus.unsubscribe(h1)
        assert bus.subscriber_count == 1

    @pytest.mark.asyncio
    async def test_pending_count(self):
        bus = EventBus()
        # Don't start — events stay in queue
        await bus.publish(_make_event())
        await bus.publish(_make_event())
        assert bus.pending == 2
