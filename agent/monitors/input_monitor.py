from __future__ import annotations

import asyncio
import ctypes
import ctypes.wintypes
import logging
import platform
from datetime import datetime, timezone
from typing import Callable

from agent.engine.event_bus import EventBus
from agent.models.config import AwayWindow
from agent.models.event import (
    EventAction,
    EventCategory,
    MonitorSource,
    TimelineEvent,
)
from agent.monitors.base import BaseMonitor

logger = logging.getLogger(__name__)


def _win32_idle_seconds() -> float:
    """Return seconds since last keyboard/mouse input (Windows only)."""

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.wintypes.UINT),
            ("dwTime", ctypes.wintypes.DWORD),
        ]

    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
    millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
    return millis / 1000.0


def _is_within_away_window(now: datetime, windows: list[AwayWindow]) -> bool:
    """Check if the current time falls within any configured away window."""
    weekday = now.weekday()
    t = now.hour * 60 + now.minute

    for w in windows:
        if weekday not in w.days:
            continue
        start = w.start_hour * 60 + w.start_minute
        end = w.end_hour * 60 + w.end_minute

        if start <= end:
            # Normal range, e.g. 09:00 - 17:00
            if start <= t < end:
                return True
        else:
            # Overnight range, e.g. 23:00 - 06:00
            if t >= start or t < end:
                return True
    return False


class InputMonitor(BaseMonitor):
    """Polls for keyboard/mouse activity; alerts if active during away windows."""

    def __init__(
        self,
        event_bus: EventBus,
        poll_interval: float = 5.0,
        away_windows: list[AwayWindow] | None = None,
        idle_fn: Callable[[], float] | None = None,
        streak_threshold: float = 10.0,
    ) -> None:
        super().__init__(event_bus)
        self._poll_interval = poll_interval
        self._away_windows = away_windows or []
        self._streak_threshold = streak_threshold
        self._active_streak: float = 0.0
        self._task: asyncio.Task | None = None

        # Injectable idle function for testing
        if idle_fn is not None:
            self._get_idle = idle_fn
        elif platform.system() == "Windows":
            self._get_idle = _win32_idle_seconds
        else:
            self._get_idle = lambda: 9999.0  # non-Windows: always idle

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._active_streak = 0.0
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("InputMonitor started (poll=%.1fs)", self._poll_interval)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("InputMonitor stopped")

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                idle = self._get_idle()
                now = datetime.now(timezone.utc)

                if idle < self._poll_interval:
                    # User is active
                    self._active_streak += self._poll_interval

                    if (
                        self._active_streak >= self._streak_threshold
                        and self._away_windows
                        and _is_within_away_window(now, self._away_windows)
                    ):
                        event = TimelineEvent(
                            source=MonitorSource.INPUT_MONITOR,
                            category=EventCategory.USER_INPUT,
                            action=EventAction.ACTIVE_DURING_AWAY,
                            detail={
                                "idle_seconds": idle,
                                "streak_seconds": self._active_streak,
                            },
                            severity="MEDIUM",
                        )
                        await self._bus.publish(event)
                        # Reset streak after alerting to avoid spam
                        self._active_streak = 0.0
                    elif self._active_streak == self._poll_interval:
                        # First detection — emit input_detected
                        event = TimelineEvent(
                            source=MonitorSource.INPUT_MONITOR,
                            category=EventCategory.USER_INPUT,
                            action=EventAction.INPUT_DETECTED,
                            detail={"idle_seconds": idle},
                        )
                        await self._bus.publish(event)
                else:
                    # User is idle
                    if self._active_streak > 0:
                        event = TimelineEvent(
                            source=MonitorSource.INPUT_MONITOR,
                            category=EventCategory.USER_INPUT,
                            action=EventAction.IDLE_STARTED,
                            detail={"last_active_streak": self._active_streak},
                        )
                        await self._bus.publish(event)
                    self._active_streak = 0.0

            except Exception:
                logger.exception("InputMonitor poll error")

            await asyncio.sleep(self._poll_interval)
