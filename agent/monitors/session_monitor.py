from __future__ import annotations

import asyncio
import logging
import platform
from datetime import datetime, timezone
from typing import Any, Callable

from agent.engine.event_bus import EventBus
from agent.models.event import (
    EventAction,
    EventCategory,
    MonitorSource,
    TimelineEvent,
)
from agent.monitors.base import BaseMonitor

logger = logging.getLogger(__name__)

# Windows Event IDs we care about
_SECURITY_EVENTS = {
    4624: EventAction.SESSION_LOGON,
    4625: EventAction.LOGIN_FAILED,
    4800: EventAction.SESSION_LOCK,
    4801: EventAction.SESSION_UNLOCK,
}

_SYSTEM_EVENTS = {
    1: EventAction.SYSTEM_WAKE,      # Power-Troubleshooter resume
    42: EventAction.SYSTEM_SLEEP,    # Kernel-Power sleep
    107: EventAction.SYSTEM_WAKE,    # Kernel-Power resume from connected standby
}

_RDP_EVENTS = {
    21: EventAction.SESSION_RDP,     # Session logon succeeded
    23: EventAction.SESSION_LOGOFF,  # Session logoff succeeded
    24: EventAction.SESSION_RDP,     # Session disconnected
    25: EventAction.SESSION_RDP,     # Session reconnection succeeded
}


def _read_events_blocking(
    log_type: str,
    source: str | None,
    event_ids: set[int],
    since: datetime,
    read_log_fn: Callable | None = None,
) -> list[dict]:
    """Read Windows Event Log entries (blocking call).

    Parameters
    ----------
    read_log_fn : optional callable for testing (replaces win32evtlog calls)
    """
    if read_log_fn is not None:
        return read_log_fn(log_type, source, event_ids, since)

    if platform.system() != "Windows":
        return []

    try:
        import win32evtlog
        import win32evtlogutil
    except ImportError:
        logger.warning("pywin32 not available — SessionMonitor disabled")
        return []

    results: list[dict] = []
    try:
        hand = win32evtlog.OpenEventLog(None, log_type)
        flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
        while True:
            events = win32evtlog.ReadEventLog(hand, flags, 0)
            if not events:
                break
            for ev in events:
                ts = ev.TimeGenerated
                if isinstance(ts, datetime):
                    ev_time = ts.replace(tzinfo=timezone.utc)
                else:
                    ev_time = datetime.fromtimestamp(ts, tz=timezone.utc)
                if ev_time <= since:
                    win32evtlog.CloseEventLog(hand)
                    return results
                if ev.EventID & 0xFFFF in event_ids:
                    results.append({
                        "event_id": ev.EventID & 0xFFFF,
                        "timestamp": ev_time,
                        "source": ev.SourceName,
                        "message": win32evtlogutil.SafeFormatMessage(ev, log_type),
                    })
        win32evtlog.CloseEventLog(hand)
    except Exception:
        logger.exception("Error reading %s log", log_type)
    return results


class SessionMonitor(BaseMonitor):
    """Monitors Windows Event Logs for session and power events."""

    def __init__(
        self,
        event_bus: EventBus,
        poll_interval: float = 30.0,
        read_log_fn: Callable | None = None,
    ) -> None:
        super().__init__(event_bus)
        self._poll_interval = poll_interval
        self._read_log_fn = read_log_fn
        self._last_read_time = datetime.now(timezone.utc)
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._last_read_time = datetime.now(timezone.utc)
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("SessionMonitor started (poll=%.0fs)", self._poll_interval)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("SessionMonitor stopped")

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                since = self._last_read_time
                now = datetime.now(timezone.utc)

                events = await self._fetch_all(since)
                for raw in events:
                    eid = raw["event_id"]
                    action = (
                        _SECURITY_EVENTS.get(eid)
                        or _SYSTEM_EVENTS.get(eid)
                        or _RDP_EVENTS.get(eid)
                    )
                    if not action:
                        continue

                    severity = "INFO"
                    if action == EventAction.LOGIN_FAILED:
                        severity = "HIGH"
                    elif action == EventAction.SESSION_RDP:
                        severity = "MEDIUM"

                    te = TimelineEvent(
                        source=MonitorSource.SESSION_MONITOR,
                        category=EventCategory.SESSION if action not in (
                            EventAction.SYSTEM_WAKE, EventAction.SYSTEM_SLEEP
                        ) else EventCategory.SYSTEM,
                        action=action,
                        detail={
                            "event_id": eid,
                            "source": raw.get("source", ""),
                            "message": raw.get("message", ""),
                        },
                        severity=severity,
                        timestamp=raw.get("timestamp", now),
                    )
                    await self._bus.publish(te)

                self._last_read_time = now
            except Exception:
                logger.exception("SessionMonitor poll error")

            await asyncio.sleep(self._poll_interval)

    async def _fetch_all(self, since: datetime) -> list[dict]:
        """Fetch events from all relevant logs via thread pool."""
        security = await asyncio.to_thread(
            _read_events_blocking, "Security", None,
            set(_SECURITY_EVENTS.keys()), since, self._read_log_fn,
        )
        system = await asyncio.to_thread(
            _read_events_blocking, "System", None,
            set(_SYSTEM_EVENTS.keys()), since, self._read_log_fn,
        )
        rdp = await asyncio.to_thread(
            _read_events_blocking, "Microsoft-Windows-TerminalServices-LocalSessionManager/Operational",
            None, set(_RDP_EVENTS.keys()), since, self._read_log_fn,
        )
        return security + system + rdp
