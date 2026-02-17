from __future__ import annotations

import pytest
from unittest.mock import patch

from agent.models.event import TimelineEvent, MonitorSource, EventCategory, EventAction
from agent.models.alert import Alert, Severity


@pytest.fixture()
def db_path(tmp_path):
    path = str(tmp_path / "test_pida.db")
    with patch("agent.db.database.settings") as mock_settings:
        mock_settings.db_path = path
        yield path


@pytest.fixture()
async def db(db_path):
    from agent.db.database import init_db
    await init_db()
    yield db_path


@pytest.fixture()
def make_event():
    def _factory(**kwargs):
        defaults = dict(
            source=MonitorSource.FOLDER_MONITOR,
            category=EventCategory.FILE_SYSTEM,
            action=EventAction.FILE_CREATED,
            target="/tmp/test.txt",
        )
        defaults.update(kwargs)
        return TimelineEvent(**defaults)
    return _factory


@pytest.fixture()
def make_alert():
    def _factory(**kwargs):
        defaults = dict(
            severity=Severity.HIGH,
            message="Test alert",
            source="folder_monitor",
        )
        defaults.update(kwargs)
        return Alert(**defaults)
    return _factory
