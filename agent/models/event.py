from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


class EventCategory(StrEnum):
    FILE_SYSTEM = "file_system"
    USER_INPUT = "user_input"
    SESSION = "session"
    SYSTEM = "system"


class EventAction(StrEnum):
    # File system
    FILE_CREATED = "file_created"
    FILE_MODIFIED = "file_modified"
    FILE_DELETED = "file_deleted"
    FILE_RENAMED = "file_renamed"
    FILE_MOVED = "file_moved"
    # User input / away
    INPUT_DETECTED = "input_detected"
    IDLE_STARTED = "idle_started"
    ACTIVE_DURING_AWAY = "active_during_away"
    # Session
    SESSION_LOGON = "session_logon"
    SESSION_LOGOFF = "session_logoff"
    SESSION_LOCK = "session_lock"
    SESSION_UNLOCK = "session_unlock"
    SESSION_RDP = "session_rdp"
    LOGIN_FAILED = "login_failed"
    # Power
    SYSTEM_WAKE = "system_wake"
    SYSTEM_SLEEP = "system_sleep"


class MonitorSource(StrEnum):
    FOLDER_MONITOR = "folder_monitor"
    INPUT_MONITOR = "input_monitor"
    SESSION_MONITOR = "session_monitor"


class TimelineEvent(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    source: MonitorSource
    category: EventCategory
    action: EventAction
    subject: str = ""
    target: str = ""
    detail: dict = Field(default_factory=dict)
    severity: str = "INFO"
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
