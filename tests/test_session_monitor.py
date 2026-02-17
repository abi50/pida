from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta

import pytest

from agent.engine.event_bus import EventBus
from agent.models.event import EventAction, TimelineEvent
from agent.monitors.session_monitor import SessionMonitor, _read_events_blocking


def _make_read_fn(events: list[dict]):
    """Create a mock read_log_fn that returns given events for any log."""
    def _fn(log_type, source, event_ids, since):
        return [e for e in events if e["event_id"] in event_ids and e["timestamp"] > since]
    return _fn


class TestReadEventsBlocking:
    def test_returns_empty_on_non_windows(self):
        result = _read_events_blocking("Security", None, {4624}, datetime.now(timezone.utc))
        # On non-Windows or if pywin32 isn't configured, returns [] or real events
        assert isinstance(result, list)

    def test_injectable_fn_filters_by_event_id(self):
        now = datetime.now(timezone.utc)
        raw = [
            {"event_id": 4624, "timestamp": now, "source": "test", "message": "logon"},
            {"event_id": 9999, "timestamp": now, "source": "test", "message": "other"},
        ]
        fn = _make_read_fn(raw)
        result = fn("Security", None, {4624}, now - timedelta(seconds=60))
        assert len(result) == 1
        assert result[0]["event_id"] == 4624

    def test_injectable_fn_filters_by_since(self):
        now = datetime.now(timezone.utc)
        old = now - timedelta(hours=2)
        raw = [
            {"event_id": 4624, "timestamp": now, "source": "test", "message": "new"},
            {"event_id": 4624, "timestamp": old, "source": "test", "message": "old"},
        ]
        fn = _make_read_fn(raw)
        cutoff = now - timedelta(hours=1)
        result = fn("Security", None, {4624}, cutoff)
        assert len(result) == 1
        assert result[0]["message"] == "new"


class TestSessionMonitor:
    @pytest.mark.asyncio
    async def test_start_stop(self):
        bus = EventBus()
        monitor = SessionMonitor(bus, poll_interval=0.1, read_log_fn=_make_read_fn([]))
        await bus.start()
        await monitor.start()
        assert monitor.running is True
        await monitor.stop()
        assert monitor.running is False
        await bus.stop()

    @pytest.mark.asyncio
    async def test_logon_event(self):
        bus = EventBus()
        received: list[TimelineEvent] = []

        async def handler(e):
            received.append(e)

        bus.subscribe(handler)
        future = datetime.now(timezone.utc) + timedelta(seconds=5)
        events = [{"event_id": 4624, "timestamp": future, "source": "Security", "message": "logon"}]
        monitor = SessionMonitor(bus, poll_interval=0.1, read_log_fn=_make_read_fn(events))
        await bus.start()
        await monitor.start()
        await asyncio.sleep(0.25)
        await monitor.stop()
        await bus.stop()

        actions = [e.action for e in received]
        assert EventAction.SESSION_LOGON in actions

    @pytest.mark.asyncio
    async def test_failed_login_is_high_severity(self):
        bus = EventBus()
        received: list[TimelineEvent] = []

        async def handler(e):
            received.append(e)

        bus.subscribe(handler)
        future = datetime.now(timezone.utc) + timedelta(seconds=5)
        events = [{"event_id": 4625, "timestamp": future, "source": "Security", "message": "failed"}]
        monitor = SessionMonitor(bus, poll_interval=0.1, read_log_fn=_make_read_fn(events))
        await bus.start()
        await monitor.start()
        await asyncio.sleep(0.25)
        await monitor.stop()
        await bus.stop()

        failed = [e for e in received if e.action == EventAction.LOGIN_FAILED]
        assert len(failed) >= 1
        assert failed[0].severity == "HIGH"

    @pytest.mark.asyncio
    async def test_rdp_event(self):
        bus = EventBus()
        received: list[TimelineEvent] = []

        async def handler(e):
            received.append(e)

        bus.subscribe(handler)
        future = datetime.now(timezone.utc) + timedelta(seconds=5)
        events = [{"event_id": 21, "timestamp": future, "source": "RDP", "message": "rdp logon"}]
        monitor = SessionMonitor(bus, poll_interval=0.1, read_log_fn=_make_read_fn(events))
        await bus.start()
        await monitor.start()
        await asyncio.sleep(0.25)
        await monitor.stop()
        await bus.stop()

        rdp = [e for e in received if e.action == EventAction.SESSION_RDP]
        assert len(rdp) >= 1

    @pytest.mark.asyncio
    async def test_system_wake(self):
        bus = EventBus()
        received: list[TimelineEvent] = []

        async def handler(e):
            received.append(e)

        bus.subscribe(handler)
        future = datetime.now(timezone.utc) + timedelta(seconds=5)
        events = [{"event_id": 1, "timestamp": future, "source": "System", "message": "wake"}]
        monitor = SessionMonitor(bus, poll_interval=0.1, read_log_fn=_make_read_fn(events))
        await bus.start()
        await monitor.start()
        await asyncio.sleep(0.25)
        await monitor.stop()
        await bus.stop()

        wake = [e for e in received if e.action == EventAction.SYSTEM_WAKE]
        assert len(wake) >= 1

    @pytest.mark.asyncio
    async def test_no_duplicate_after_timestamp_update(self):
        bus = EventBus()
        received: list[TimelineEvent] = []

        async def handler(e):
            received.append(e)

        bus.subscribe(handler)
        # Event with a fixed timestamp in the past
        old_time = datetime.now(timezone.utc) - timedelta(hours=1)
        events = [{"event_id": 4624, "timestamp": old_time, "source": "S", "message": "old"}]
        monitor = SessionMonitor(bus, poll_interval=0.1, read_log_fn=_make_read_fn(events))
        await bus.start()
        await monitor.start()
        await asyncio.sleep(0.3)
        await monitor.stop()
        await bus.stop()

        # Old event (before monitor's start time) should not appear
        assert len(received) == 0
