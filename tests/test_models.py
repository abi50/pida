from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest
from pydantic import ValidationError

from agent.models.event import TimelineEvent, EventCategory, EventAction, MonitorSource
from agent.models.alert import Alert, Severity, SEVERITY_ORDER
from agent.models.config import MonitoredFolder, AwayWindow, EmailConfig, AlertConfig


class TestTimelineEvent:
    def test_auto_id_is_12_hex_chars(self):
        e = TimelineEvent(
            source=MonitorSource.FOLDER_MONITOR,
            category=EventCategory.FILE_SYSTEM,
            action=EventAction.FILE_CREATED,
        )
        assert len(e.id) == 12
        int(e.id, 16)  # must be valid hex

    def test_unique_ids(self):
        e1 = TimelineEvent(
            source=MonitorSource.FOLDER_MONITOR,
            category=EventCategory.FILE_SYSTEM,
            action=EventAction.FILE_CREATED,
        )
        e2 = TimelineEvent(
            source=MonitorSource.FOLDER_MONITOR,
            category=EventCategory.FILE_SYSTEM,
            action=EventAction.FILE_CREATED,
        )
        assert e1.id != e2.id

    def test_timestamp_defaults_to_utc(self):
        e = TimelineEvent(
            source=MonitorSource.FOLDER_MONITOR,
            category=EventCategory.FILE_SYSTEM,
            action=EventAction.FILE_CREATED,
        )
        assert e.timestamp.tzinfo is not None
        assert (datetime.now(timezone.utc) - e.timestamp).total_seconds() < 2

    def test_default_fields(self):
        e = TimelineEvent(
            source=MonitorSource.INPUT_MONITOR,
            category=EventCategory.USER_INPUT,
            action=EventAction.INPUT_DETECTED,
        )
        assert e.subject == ""
        assert e.target == ""
        assert e.detail == {}
        assert e.severity == "INFO"

    def test_json_serialization(self):
        e = TimelineEvent(
            source=MonitorSource.SESSION_MONITOR,
            category=EventCategory.SESSION,
            action=EventAction.SESSION_LOGON,
            subject="admin",
            target="RDP",
            detail={"ip": "1.2.3.4"},
            severity="HIGH",
        )
        data = e.model_dump(mode="json")
        assert isinstance(data["timestamp"], str)
        assert data["source"] == "session_monitor"
        assert data["detail"] == {"ip": "1.2.3.4"}


class TestAlert:
    def test_severity_serializes_to_string(self):
        a = Alert(severity=Severity.CRITICAL, message="test")
        assert a.severity == "CRITICAL"
        data = a.model_dump(mode="json")
        assert data["severity"] == "CRITICAL"

    def test_snoozed_until_accepts_none(self):
        a = Alert(severity=Severity.LOW, message="test")
        assert a.snoozed_until is None

    def test_snoozed_until_accepts_datetime(self):
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        a = Alert(severity=Severity.LOW, message="test", snoozed_until=future)
        assert a.snoozed_until == future

    def test_severity_order(self):
        assert SEVERITY_ORDER[Severity.INFO] < SEVERITY_ORDER[Severity.LOW]
        assert SEVERITY_ORDER[Severity.LOW] < SEVERITY_ORDER[Severity.MEDIUM]
        assert SEVERITY_ORDER[Severity.MEDIUM] < SEVERITY_ORDER[Severity.HIGH]
        assert SEVERITY_ORDER[Severity.HIGH] < SEVERITY_ORDER[Severity.CRITICAL]

    def test_invalid_severity_raises(self):
        with pytest.raises(ValidationError):
            Alert(severity="INVALID", message="test")


class TestMonitoredFolder:
    def test_defaults(self):
        f = MonitoredFolder(path="/tmp/test")
        assert f.recursive is True
        assert f.enabled is True
        assert f.watch_creates is True
        assert f.watch_modifies is True
        assert f.watch_deletes is True
        assert f.watch_renames is True
        assert len(f.id) == 8


class TestAwayWindow:
    def test_default_days_all_seven(self):
        w = AwayWindow(start_hour=1, end_hour=7)
        assert w.days == [0, 1, 2, 3, 4, 5, 6]
        assert w.enabled is True
        assert w.start_minute == 0
        assert w.end_minute == 0

    def test_custom_days(self):
        w = AwayWindow(start_hour=9, end_hour=17, days=[0, 1, 2, 3, 4])
        assert len(w.days) == 5


class TestEmailConfig:
    def test_defaults(self):
        c = EmailConfig()
        assert c.enabled is False
        assert c.smtp_host == "smtp.gmail.com"
        assert c.smtp_port == 587
        assert c.throttle_minutes == 5
        assert c.min_severity == "HIGH"


class TestAlertConfig:
    def test_defaults(self):
        c = AlertConfig()
        assert c.dashboard_min_severity == "LOW"
        assert c.toast_min_severity == "MEDIUM"
        assert c.email.enabled is False
