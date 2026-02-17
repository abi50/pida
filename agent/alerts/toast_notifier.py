from __future__ import annotations

import asyncio
import logging
from typing import Callable

from agent.models.alert import Alert

logger = logging.getLogger(__name__)


async def toast_notify(
    alert: Alert,
    notify_fn: Callable | None = None,
) -> None:
    """Show a desktop toast notification via plyer (or injectable fn for tests)."""
    if notify_fn is not None:
        await asyncio.to_thread(notify_fn, alert)
        return

    try:
        from plyer import notification
        await asyncio.to_thread(
            notification.notify,
            title=f"PIDA Alert [{alert.severity.value}]",
            message=alert.message,
            app_name="PIDA",
            timeout=10,
        )
    except Exception:
        logger.exception("Toast notification failed")
