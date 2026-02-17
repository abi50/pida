from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class MonitoredFolder(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    path: str
    recursive: bool = True
    enabled: bool = True
    watch_creates: bool = True
    watch_modifies: bool = True
    watch_deletes: bool = True
    watch_renames: bool = True


class AwayWindow(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    label: str = ""
    start_hour: int  # 0-23
    start_minute: int = 0
    end_hour: int  # 0-23
    end_minute: int = 0
    days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6])
    enabled: bool = True


class EmailConfig(BaseModel):
    enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    sender_address: str = ""
    sender_password: str = ""
    recipient_address: str = ""
    min_severity: str = "HIGH"
    throttle_minutes: int = 5


class AlertConfig(BaseModel):
    dashboard_min_severity: str = "LOW"
    toast_min_severity: str = "MEDIUM"
    email: EmailConfig = Field(default_factory=EmailConfig)
