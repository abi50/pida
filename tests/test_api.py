from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock

import pytest
from httpx import AsyncClient, ASGITransport

from agent.models.alert import Alert, Severity
from agent.models.event import TimelineEvent, MonitorSource, EventCategory, EventAction


def _make_event(**kwargs) -> TimelineEvent:
    defaults = dict(
        source=MonitorSource.FOLDER_MONITOR,
        category=EventCategory.FILE_SYSTEM,
        action=EventAction.FILE_CREATED,
        target="/tmp/test.txt",
    )
    defaults.update(kwargs)
    return TimelineEvent(**defaults)


def _make_alert(**kwargs) -> Alert:
    defaults = dict(severity=Severity.HIGH, message="test", source="test")
    defaults.update(kwargs)
    return Alert(**defaults)


@pytest.fixture()
def app(db_path):
    """Create a test app with real DB but no monitors."""
    from agent.db.database import init_db
    import asyncio
    asyncio.get_event_loop().run_until_complete(init_db())

    from fastapi import FastAPI
    from agent.api.routes import router, ws_router
    test_app = FastAPI()
    test_app.include_router(router)
    test_app.include_router(ws_router)
    return test_app


@pytest.fixture()
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestTimelineAPI:
    @pytest.mark.asyncio
    async def test_get_timeline_empty(self, client):
        resp = await client.get("/api/timeline")
        assert resp.status_code == 200
        data = resp.json()
        assert data["events"] == []
        assert data["count"] == 0

    @pytest.mark.asyncio
    async def test_get_timeline_with_events(self, client):
        from agent.db import database as db_mod
        event = _make_event()
        await db_mod.insert_event(event)
        resp = await client.get("/api/timeline")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    @pytest.mark.asyncio
    async def test_get_timeline_event_by_id(self, client):
        from agent.db import database as db_mod
        event = _make_event()
        await db_mod.insert_event(event)
        resp = await client.get(f"/api/timeline/{event.id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == event.id

    @pytest.mark.asyncio
    async def test_get_timeline_event_not_found(self, client):
        resp = await client.get("/api/timeline/nonexistent")
        assert resp.status_code == 404


class TestAlertsAPI:
    @pytest.mark.asyncio
    async def test_get_alerts_empty(self, client):
        resp = await client.get("/api/alerts")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    @pytest.mark.asyncio
    async def test_insert_and_get_alert(self, client):
        from agent.db import database as db_mod
        alert = _make_alert()
        await db_mod.insert_alert(alert)
        resp = await client.get("/api/alerts")
        assert resp.json()["count"] == 1

    @pytest.mark.asyncio
    async def test_acknowledge_alert(self, client):
        from agent.db import database as db_mod
        alert = _make_alert()
        await db_mod.insert_alert(alert)
        resp = await client.post(f"/api/alerts/{alert.id}/acknowledge")
        assert resp.status_code == 200
        assert resp.json()["status"] == "acknowledged"

    @pytest.mark.asyncio
    async def test_acknowledge_nonexistent(self, client):
        resp = await client.post("/api/alerts/nope/acknowledge")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_snooze_alert(self, client):
        from agent.db import database as db_mod
        alert = _make_alert()
        await db_mod.insert_alert(alert)
        resp = await client.post(
            f"/api/alerts/{alert.id}/snooze",
            json={"hours": 2.0},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "snoozed"


class TestConfigAPI:
    @pytest.mark.asyncio
    async def test_get_folders_empty(self, client):
        resp = await client.get("/api/config/folders")
        assert resp.status_code == 200
        assert resp.json()["folders"] == []

    @pytest.mark.asyncio
    async def test_set_and_get_folders(self, client):
        folders = [{"path": "/tmp/watch", "recursive": True, "enabled": True}]
        resp = await client.post("/api/config/folders", json=folders)
        assert resp.status_code == 200
        resp = await client.get("/api/config/folders")
        assert len(resp.json()["folders"]) == 1

    @pytest.mark.asyncio
    async def test_away_windows_roundtrip(self, client):
        windows = [{"start_hour": 23, "end_hour": 6, "days": [0, 1, 2, 3, 4]}]
        resp = await client.post("/api/config/away-windows", json=windows)
        assert resp.status_code == 200
        resp = await client.get("/api/config/away-windows")
        assert len(resp.json()["windows"]) == 1

    @pytest.mark.asyncio
    async def test_status(self, client):
        resp = await client.get("/api/status")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"
