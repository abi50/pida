"""End-to-end test: inject file event during away window → verify DB event + alert + dispatcher callback."""
from __future__ import annotations

import asyncio
from unittest.mock import patch, AsyncMock

import pytest

from agent.alerts.dispatcher import AlertDispatcher
from agent.db import database as db
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


# Away window covering all times
_ALWAYS_AWAY = AwayWindow(start_hour=0, end_hour=23, end_minute=59)


class TestEndToEnd:
    @pytest.mark.asyncio
    async def test_file_event_during_away_full_pipeline(self, db_path):
        """Full pipeline: event → bus → timeline → DB + alert → dispatcher."""
        await db.init_db()

        bus = EventBus()
        dispatcher = AlertDispatcher()
        dispatched: list[Alert] = []

        async def mock_notifier(alert: Alert):
            dispatched.append(alert)

        dispatcher.add_route(Severity.INFO, mock_notifier)

        async def on_alert(alert: Alert):
            await dispatcher.dispatch(alert)

        timeline = TimelineEngine(bus, away_windows=[_ALWAYS_AWAY], on_alert=on_alert)

        await bus.start()
        await timeline.start()

        # Inject a file-created event
        event = TimelineEvent(
            source=MonitorSource.FOLDER_MONITOR,
            category=EventCategory.FILE_SYSTEM,
            action=EventAction.FILE_CREATED,
            target="/sensitive/docs/secret.txt",
            severity="INFO",
        )
        await bus.publish(event)
        await asyncio.sleep(0.2)

        await timeline.stop()
        await bus.stop()

        # Verify event persisted in DB
        db_event = await db.get_event_by_id(event.id)
        assert db_event is not None
        assert db_event["target"] == "/sensitive/docs/secret.txt"
        assert db_event["action"] == "file_created"

        # Verify alert was created in DB
        alerts = await db.get_alerts()
        assert len(alerts) >= 1
        assert alerts[0]["severity"] == "HIGH"
        assert "file_created" in alerts[0]["message"]

        # Verify dispatcher received the alert
        assert len(dispatched) >= 1
        assert dispatched[0].severity == Severity.HIGH

    @pytest.mark.asyncio
    async def test_failed_login_no_away_window_still_alerts(self, db_path):
        """Failed login should alert even without away windows configured."""
        await db.init_db()

        bus = EventBus()
        dispatched: list[Alert] = []

        async def mock_notifier(alert: Alert):
            dispatched.append(alert)

        dispatcher = AlertDispatcher()
        dispatcher.add_route(Severity.INFO, mock_notifier)

        async def on_alert(alert: Alert):
            await dispatcher.dispatch(alert)

        timeline = TimelineEngine(bus, away_windows=[], on_alert=on_alert)

        await bus.start()
        await timeline.start()

        event = TimelineEvent(
            source=MonitorSource.SESSION_MONITOR,
            category=EventCategory.SESSION,
            action=EventAction.LOGIN_FAILED,
            detail={"event_id": 4625, "message": "bad password"},
        )
        await bus.publish(event)
        await asyncio.sleep(0.2)

        await timeline.stop()
        await bus.stop()

        # Verify alert
        alerts = await db.get_alerts()
        assert len(alerts) >= 1
        assert alerts[0]["severity"] == "HIGH"
        assert len(dispatched) >= 1

    @pytest.mark.asyncio
    async def test_rdp_during_away_is_critical(self, db_path):
        """RDP session during away window should generate CRITICAL alert."""
        await db.init_db()

        bus = EventBus()
        dispatched: list[Alert] = []

        async def mock_notifier(alert: Alert):
            dispatched.append(alert)

        dispatcher = AlertDispatcher()
        dispatcher.add_route(Severity.INFO, mock_notifier)

        async def on_alert(alert: Alert):
            await dispatcher.dispatch(alert)

        timeline = TimelineEngine(bus, away_windows=[_ALWAYS_AWAY], on_alert=on_alert)

        await bus.start()
        await timeline.start()

        event = TimelineEvent(
            source=MonitorSource.SESSION_MONITOR,
            category=EventCategory.SESSION,
            action=EventAction.SESSION_RDP,
            detail={"event_id": 21},
        )
        await bus.publish(event)
        await asyncio.sleep(0.2)

        await timeline.stop()
        await bus.stop()

        assert len(dispatched) >= 1
        assert dispatched[0].severity == Severity.CRITICAL

    @pytest.mark.asyncio
    async def test_normal_event_outside_away_no_alert(self, db_path):
        """File event with no away windows configured → no alert, but event is persisted."""
        await db.init_db()

        bus = EventBus()
        dispatched: list[Alert] = []

        async def mock_notifier(alert: Alert):
            dispatched.append(alert)

        dispatcher = AlertDispatcher()
        dispatcher.add_route(Severity.INFO, mock_notifier)

        async def on_alert(alert: Alert):
            await dispatcher.dispatch(alert)

        timeline = TimelineEngine(bus, away_windows=[], on_alert=on_alert)

        await bus.start()
        await timeline.start()

        event = TimelineEvent(
            source=MonitorSource.FOLDER_MONITOR,
            category=EventCategory.FILE_SYSTEM,
            action=EventAction.FILE_CREATED,
            target="/tmp/normal.txt",
        )
        await bus.publish(event)
        await asyncio.sleep(0.2)

        await timeline.stop()
        await bus.stop()

        # Event persisted, no alert
        db_event = await db.get_event_by_id(event.id)
        assert db_event is not None
        assert len(dispatched) == 0
        alerts = await db.get_alerts()
        assert len(alerts) == 0
