from __future__ import annotations

import asyncio

import pytest

from agent.engine.event_bus import EventBus
from agent.models.config import AwayWindow
from agent.models.event import EventAction, TimelineEvent
from agent.monitors.input_monitor import InputMonitor, _is_within_away_window
from datetime import datetime, timezone


class TestIsWithinAwayWindow:
    def test_inside_normal_range(self):
        w = AwayWindow(start_hour=9, start_minute=0, end_hour=17, end_minute=0)
        # Monday 12:00
        now = datetime(2025, 1, 6, 12, 0, tzinfo=timezone.utc)
        assert _is_within_away_window(now, [w]) is True

    def test_outside_normal_range(self):
        w = AwayWindow(start_hour=9, start_minute=0, end_hour=17, end_minute=0)
        # Monday 20:00
        now = datetime(2025, 1, 6, 20, 0, tzinfo=timezone.utc)
        assert _is_within_away_window(now, [w]) is False

    def test_overnight_range_late(self):
        w = AwayWindow(start_hour=23, start_minute=0, end_hour=6, end_minute=0)
        # Monday 23:30
        now = datetime(2025, 1, 6, 23, 30, tzinfo=timezone.utc)
        assert _is_within_away_window(now, [w]) is True

    def test_overnight_range_early(self):
        w = AwayWindow(start_hour=23, start_minute=0, end_hour=6, end_minute=0)
        # Tuesday 03:00
        now = datetime(2025, 1, 7, 3, 0, tzinfo=timezone.utc)
        assert _is_within_away_window(now, [w]) is True

    def test_wrong_day_excluded(self):
        w = AwayWindow(start_hour=9, end_hour=17, days=[0, 1, 2, 3, 4])  # weekdays
        # Saturday 12:00
        now = datetime(2025, 1, 11, 12, 0, tzinfo=timezone.utc)
        assert _is_within_away_window(now, [w]) is False

    def test_empty_windows(self):
        now = datetime(2025, 1, 6, 12, 0, tzinfo=timezone.utc)
        assert _is_within_away_window(now, []) is False


class TestInputMonitor:
    @pytest.mark.asyncio
    async def test_start_stop(self):
        bus = EventBus()
        monitor = InputMonitor(bus, poll_interval=0.1, idle_fn=lambda: 9999.0)
        await bus.start()
        await monitor.start()
        assert monitor.running is True
        await monitor.stop()
        assert monitor.running is False
        await bus.stop()

    @pytest.mark.asyncio
    async def test_detects_input(self):
        bus = EventBus()
        received: list[TimelineEvent] = []

        async def handler(e):
            received.append(e)

        bus.subscribe(handler)
        # idle_fn returns 0 → user is active
        monitor = InputMonitor(bus, poll_interval=0.05, idle_fn=lambda: 0.0)
        await bus.start()
        await monitor.start()
        await asyncio.sleep(0.15)
        await monitor.stop()
        await bus.stop()

        actions = [e.action for e in received]
        assert EventAction.INPUT_DETECTED in actions

    @pytest.mark.asyncio
    async def test_idle_started_after_activity(self):
        bus = EventBus()
        received: list[TimelineEvent] = []

        async def handler(e):
            received.append(e)

        bus.subscribe(handler)
        call_count = 0

        def alternating_idle():
            nonlocal call_count
            call_count += 1
            # First 2 calls: active, then idle
            return 0.0 if call_count <= 2 else 9999.0

        monitor = InputMonitor(bus, poll_interval=0.05, idle_fn=alternating_idle)
        await bus.start()
        await monitor.start()
        await asyncio.sleep(0.3)
        await monitor.stop()
        await bus.stop()

        actions = [e.action for e in received]
        assert EventAction.IDLE_STARTED in actions

    @pytest.mark.asyncio
    async def test_away_window_alert(self):
        bus = EventBus()
        received: list[TimelineEvent] = []

        async def handler(e):
            received.append(e)

        bus.subscribe(handler)
        # Away window covers all times, all days
        away = AwayWindow(start_hour=0, end_hour=23, end_minute=59)
        monitor = InputMonitor(
            bus,
            poll_interval=0.05,
            idle_fn=lambda: 0.0,
            away_windows=[away],
            streak_threshold=0.1,
        )
        await bus.start()
        await monitor.start()
        await asyncio.sleep(0.3)
        await monitor.stop()
        await bus.stop()

        actions = [e.action for e in received]
        assert EventAction.ACTIVE_DURING_AWAY in actions

    @pytest.mark.asyncio
    async def test_streak_threshold_prevents_early_alert(self):
        bus = EventBus()
        received: list[TimelineEvent] = []

        async def handler(e):
            received.append(e)

        bus.subscribe(handler)
        away = AwayWindow(start_hour=0, end_hour=23, end_minute=59)
        # High threshold — won't be reached in short test
        monitor = InputMonitor(
            bus,
            poll_interval=0.05,
            idle_fn=lambda: 0.0,
            away_windows=[away],
            streak_threshold=999.0,
        )
        await bus.start()
        await monitor.start()
        await asyncio.sleep(0.15)
        await monitor.stop()
        await bus.stop()

        away_alerts = [e for e in received if e.action == EventAction.ACTIVE_DURING_AWAY]
        assert len(away_alerts) == 0
