from __future__ import annotations

import logging
from typing import Callable, Awaitable

from agent.models.alert import Alert, Severity, SEVERITY_ORDER

logger = logging.getLogger(__name__)

Notifier = Callable[[Alert], Awaitable[None]]


class AlertDispatcher:
    """Routes alerts to notifiers based on severity thresholds."""

    def __init__(self) -> None:
        self._routes: list[tuple[Severity, Notifier]] = []

    def add_route(self, min_severity: Severity, notifier: Notifier) -> None:
        self._routes.append((min_severity, notifier))

    async def dispatch(self, alert: Alert) -> None:
        alert_level = SEVERITY_ORDER.get(alert.severity, 0)
        for min_sev, notifier in self._routes:
            threshold = SEVERITY_ORDER.get(min_sev, 0)
            if alert_level >= threshold:
                try:
                    await notifier(alert)
                except Exception:
                    logger.exception("Notifier %s failed for alert %s", notifier, alert.id)
