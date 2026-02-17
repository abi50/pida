from __future__ import annotations

import logging

from agent.models.alert import Alert

logger = logging.getLogger("pida.alerts")


async def log_notify(alert: Alert) -> None:
    """Log alerts using Python logging."""
    level = {
        "INFO": logging.INFO,
        "LOW": logging.INFO,
        "MEDIUM": logging.WARNING,
        "HIGH": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }.get(alert.severity.value, logging.INFO)
    logger.log(level, "[%s] %s (source=%s)", alert.severity.value, alert.message, alert.source)
