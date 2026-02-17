from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable, Awaitable

from agent.db import database as db
from agent.engine.event_bus import EventBus
from agent.models.alert import Alert, Severity
from agent.models.config import AwayWindow
from agent.models.event import EventAction, TimelineEvent
from agent.monitors.input_monitor import _is_within_away_window

logger = logging.getLogger(__name__)

OnAlertCallback = Callable[[Alert], Awaitable[None]]


class TimelineEngine:
    """Persists events and evaluates rules to generate alerts."""

    def __init__(
        self,
        event_bus: EventBus,
        away_windows: list[AwayWindow] | None = None,
        on_alert: OnAlertCallback | None = None,
    ) -> None:
        self._bus = event_bus
        self._away_windows = away_windows or []
        self._on_alert = on_alert

    async def start(self) -> None:
        self._bus.subscribe(self._handle_event)
        logger.info("TimelineEngine started")

    async def stop(self) -> None:
        self._bus.unsubscribe(self._handle_event)
        logger.info("TimelineEngine stopped")

    def set_away_windows(self, windows: list[AwayWindow]) -> None:
        self._away_windows = windows

    async def _handle_event(self, event: TimelineEvent) -> None:
        # Persist to DB
        try:
            await db.insert_event(event)
        except Exception:
            logger.exception("Failed to persist event %s", event.id)

        # Evaluate rules
        alerts = self._evaluate(event)
        for alert in alerts:
            try:
                await db.insert_alert(alert)
            except Exception:
                logger.exception("Failed to persist alert %s", alert.id)
            if self._on_alert:
                try:
                    await self._on_alert(alert)
                except Exception:
                    logger.exception("on_alert callback failed for %s", alert.id)

    def _evaluate(self, event: TimelineEvent) -> list[Alert]:
        alerts: list[Alert] = []
        now = event.timestamp
        in_away = _is_within_away_window(now, self._away_windows) if self._away_windows else False

        # Rule 1: File change during away window → HIGH
        if event.action in (
            EventAction.FILE_CREATED,
            EventAction.FILE_MODIFIED,
            EventAction.FILE_DELETED,
            EventAction.FILE_RENAMED,
            EventAction.FILE_MOVED,
        ) and in_away:
            alerts.append(Alert(
                severity=Severity.HIGH,
                message=f"File {event.action.value} during away window: {event.target}",
                source=event.source.value,
                detail={"event_id": event.id, "target": event.target},
            ))

        # Rule 2: Active input during away window → MEDIUM
        if event.action == EventAction.ACTIVE_DURING_AWAY:
            alerts.append(Alert(
                severity=Severity.MEDIUM,
                message="Keyboard/mouse activity detected during away window",
                source=event.source.value,
                detail={"event_id": event.id, **event.detail},
            ))

        # Rule 3: Failed login (anytime) → HIGH
        if event.action == EventAction.LOGIN_FAILED:
            alerts.append(Alert(
                severity=Severity.HIGH,
                message="Failed login attempt detected",
                source=event.source.value,
                detail={"event_id": event.id, **event.detail},
            ))

        # Rule 4: RDP during away window → CRITICAL
        if event.action == EventAction.SESSION_RDP and in_away:
            alerts.append(Alert(
                severity=Severity.CRITICAL,
                message="Remote Desktop session during away window",
                source=event.source.value,
                detail={"event_id": event.id, **event.detail},
            ))

        return alerts
