from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock

import pytest

from agent.engine.event_bus import EventBus
from agent.engine.timeline import TimelineEngine
from agent.models.alert import Alert, Severity
from agent.models.config import AwayWindow
from agent.models.event import (
    EventAction,
    EventCategory,
    MonitorSource,
    TimelineEvent,
)


def _make_event(**kwargs) -> TimelineEvent:
    defaults = dict(
        source=MonitorSource.FOLDER_MONITOR,
        category=EventCategory.FILE_SYSTEM,
        action=EventAction.FILE_CREATED,
        target="/tmp/test.txt",
    )
    defaults.update(kwargs)
    return TimelineEvent(**defaults)


# Away window covering all times, all days (for testing)
_ALWAYS_AWAY = AwayWindow(start_hour=0, end_hour=23, end_minute=59)


class TestTimelineEngine:
    @pytest.mark.asyncio
    async def test_persists_event(self):
        bus = EventBus()
        mock_insert = AsyncMock()
        engine = TimelineEngine(bus)
        await bus.start()
        await engine.start()

        with patch("agent.engine.timeline.db.insert_event", mock_insert), \
             patch("agent.engine.timeline.db.insert_alert", AsyncMock()):
            await bus.publish(_make_event())
            await asyncio.sleep(0.15)

        await engine.stop()
        await bus.stop()
        mock_insert.assert_called_once()

    @pytest.mark.asyncio
    async def test_file_change_during_away_creates_alert(self):
        bus = EventBus()
        alerts: list[Alert] = []

        async def collect_alert(a: Alert):
            alerts.append(a)

        engine = TimelineEngine(bus, away_windows=[_ALWAYS_AWAY], on_alert=collect_alert)
        await bus.start()
        await engine.start()

        with patch("agent.engine.timeline.db.insert_event", AsyncMock()), \
             patch("agent.engine.timeline.db.insert_alert", AsyncMock()):
            await bus.publish(_make_event(action=EventAction.FILE_CREATED))
            await asyncio.sleep(0.15)

        await engine.stop()
        await bus.stop()
        assert len(alerts) == 1
        assert alerts[0].severity == Severity.HIGH

    @pytest.mark.asyncio
    async def test_file_change_outside_away_no_alert(self):
        bus = EventBus()
        alerts: list[Alert] = []

        async def collect_alert(a: Alert):
            alerts.append(a)

        # No away windows configured
        engine = TimelineEngine(bus, away_windows=[], on_alert=collect_alert)
        await bus.start()
        await engine.start()

        with patch("agent.engine.timeline.db.insert_event", AsyncMock()), \
             patch("agent.engine.timeline.db.insert_alert", AsyncMock()):
            await bus.publish(_make_event(action=EventAction.FILE_CREATED))
            await asyncio.sleep(0.15)

        await engine.stop()
        await bus.stop()
        assert len(alerts) == 0

    @pytest.mark.asyncio
    async def test_active_during_away_creates_medium_alert(self):
        bus = EventBus()
        alerts: list[Alert] = []

        async def collect_alert(a: Alert):
            alerts.append(a)

        engine = TimelineEngine(bus, away_windows=[_ALWAYS_AWAY], on_alert=collect_alert)
        await bus.start()
        await engine.start()

        with patch("agent.engine.timeline.db.insert_event", AsyncMock()), \
             patch("agent.engine.timeline.db.insert_alert", AsyncMock()):
            await bus.publish(_make_event(
                source=MonitorSource.INPUT_MONITOR,
                category=EventCategory.USER_INPUT,
                action=EventAction.ACTIVE_DURING_AWAY,
            ))
            await asyncio.sleep(0.15)

        await engine.stop()
        await bus.stop()
        assert len(alerts) == 1
        assert alerts[0].severity == Severity.MEDIUM

    @pytest.mark.asyncio
    async def test_failed_login_always_alerts(self):
        bus = EventBus()
        alerts: list[Alert] = []

        async def collect_alert(a: Alert):
            alerts.append(a)

        # No away windows — failed login should still alert
        engine = TimelineEngine(bus, away_windows=[], on_alert=collect_alert)
        await bus.start()
        await engine.start()

        with patch("agent.engine.timeline.db.insert_event", AsyncMock()), \
             patch("agent.engine.timeline.db.insert_alert", AsyncMock()):
            await bus.publish(_make_event(
                source=MonitorSource.SESSION_MONITOR,
                category=EventCategory.SESSION,
                action=EventAction.LOGIN_FAILED,
            ))
            await asyncio.sleep(0.15)

        await engine.stop()
        await bus.stop()
        assert len(alerts) == 1
        assert alerts[0].severity == Severity.HIGH

    @pytest.mark.asyncio
    async def test_rdp_during_away_creates_critical_alert(self):
        bus = EventBus()
        alerts: list[Alert] = []

        async def collect_alert(a: Alert):
            alerts.append(a)

        engine = TimelineEngine(bus, away_windows=[_ALWAYS_AWAY], on_alert=collect_alert)
        await bus.start()
        await engine.start()

        with patch("agent.engine.timeline.db.insert_event", AsyncMock()), \
             patch("agent.engine.timeline.db.insert_alert", AsyncMock()):
            await bus.publish(_make_event(
                source=MonitorSource.SESSION_MONITOR,
                category=EventCategory.SESSION,
                action=EventAction.SESSION_RDP,
            ))
            await asyncio.sleep(0.15)

        await engine.stop()
        await bus.stop()
        assert len(alerts) == 1
        assert alerts[0].severity == Severity.CRITICAL

    @pytest.mark.asyncio
    async def test_on_alert_callback_called(self):
        bus = EventBus()
        callback = AsyncMock()
        engine = TimelineEngine(bus, away_windows=[_ALWAYS_AWAY], on_alert=callback)
        await bus.start()
        await engine.start()

        with patch("agent.engine.timeline.db.insert_event", AsyncMock()), \
             patch("agent.engine.timeline.db.insert_alert", AsyncMock()):
            await bus.publish(_make_event(action=EventAction.FILE_DELETED))
            await asyncio.sleep(0.15)

        await engine.stop()
        await bus.stop()
        callback.assert_called_once()
        alert_arg = callback.call_args[0][0]
        assert isinstance(alert_arg, Alert)
