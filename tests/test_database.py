from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from agent.db import database as db
from agent.models.alert import Severity


class TestInitDb:
    @pytest.mark.asyncio
    async def test_creates_tables(self, db_path):
        await db.init_db()
        # Should not raise on second call (idempotent)
        await db.init_db()

    @pytest.mark.asyncio
    async def test_tables_exist(self, db_path):
        await db.init_db()
        import aiosqlite
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = [r[0] for r in await cursor.fetchall()]
        assert "timeline_events" in tables
        assert "alerts" in tables
        assert "settings" in tables


class TestTimelineEvents:
    @pytest.mark.asyncio
    async def test_insert_and_get_by_id(self, db, make_event):
        event = make_event(subject="test_user", target="/etc/passwd")
        await db_mod.insert_event(event)
        result = await db_mod.get_event_by_id(event.id)
        assert result is not None
        assert result["id"] == event.id
        assert result["target"] == "/etc/passwd"
        assert result["subject"] == "test_user"
        assert isinstance(result["detail"], dict)

    @pytest.mark.asyncio
    async def test_get_nonexistent_event(self, db):
        result = await db_mod.get_event_by_id("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_filter_by_category(self, db, make_event):
        from agent.models.event import EventCategory, EventAction, MonitorSource
        e1 = make_event(category=EventCategory.FILE_SYSTEM)
        e2 = make_event(
            source=MonitorSource.INPUT_MONITOR,
            category=EventCategory.USER_INPUT,
            action=EventAction.INPUT_DETECTED,
        )
        await db_mod.insert_event(e1)
        await db_mod.insert_event(e2)
        results = await db_mod.get_events(category="file_system")
        assert len(results) == 1
        assert results[0]["category"] == "file_system"

    @pytest.mark.asyncio
    async def test_filter_by_since(self, db, make_event):
        old = make_event(
            timestamp=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )
        new = make_event()
        await db_mod.insert_event(old)
        await db_mod.insert_event(new)
        results = await db_mod.get_events(since=datetime(2024, 1, 1, tzinfo=timezone.utc))
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_pagination(self, db, make_event):
        for _ in range(5):
            await db_mod.insert_event(make_event())
        page1 = await db_mod.get_events(limit=2, offset=0)
        page2 = await db_mod.get_events(limit=2, offset=2)
        assert len(page1) == 2
        assert len(page2) == 2
        assert page1[0]["id"] != page2[0]["id"]


class TestAlerts:
    @pytest.mark.asyncio
    async def test_insert_and_get(self, db, make_alert):
        alert = make_alert()
        await db_mod.insert_alert(alert)
        results = await db_mod.get_alerts()
        assert len(results) == 1
        assert results[0]["id"] == alert.id
        assert results[0]["severity"] == "HIGH"
        assert results[0]["acknowledged"] is False

    @pytest.mark.asyncio
    async def test_acknowledge(self, db, make_alert):
        alert = make_alert()
        await db_mod.insert_alert(alert)
        ok = await db_mod.acknowledge_alert(alert.id)
        assert ok is True
        result = await db_mod.get_alert_by_id(alert.id)
        assert result["acknowledged"] is True

    @pytest.mark.asyncio
    async def test_acknowledge_nonexistent(self, db):
        ok = await db_mod.acknowledge_alert("nope")
        assert ok is False

    @pytest.mark.asyncio
    async def test_snooze(self, db, make_alert):
        alert = make_alert()
        await db_mod.insert_alert(alert)
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        ok = await db_mod.snooze_alert(alert.id, future)
        assert ok is True
        result = await db_mod.get_alert_by_id(alert.id)
        assert result["snoozed_until"] is not None

    @pytest.mark.asyncio
    async def test_filter_by_severity(self, db, make_alert):
        await db_mod.insert_alert(make_alert(severity=Severity.HIGH))
        await db_mod.insert_alert(make_alert(severity=Severity.LOW))
        results = await db_mod.get_alerts(severity="HIGH")
        assert len(results) == 1
        assert results[0]["severity"] == "HIGH"


class TestSettings:
    @pytest.mark.asyncio
    async def test_get_nonexistent(self, db):
        result = await db_mod.get_setting("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_and_get(self, db):
        await db_mod.set_setting("key1", '{"data": true}')
        result = await db_mod.get_setting("key1")
        assert result == '{"data": true}'

    @pytest.mark.asyncio
    async def test_upsert(self, db):
        await db_mod.set_setting("key1", "old")
        await db_mod.set_setting("key1", "new")
        result = await db_mod.get_setting("key1")
        assert result == "new"


# Module-level reference so the `db` fixture's patch is active
import agent.db.database as db_mod
