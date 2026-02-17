from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel

from agent.db import database as db
from agent.models.config import MonitoredFolder, AwayWindow, EmailConfig, AlertConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# ── WebSocket manager ────────────────────────────────────

_ws_clients: list[WebSocket] = []


async def broadcast_event(data: dict) -> None:
    dead: list[WebSocket] = []
    payload = json.dumps(data, default=str)
    for ws in _ws_clients:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_clients.remove(ws)


# ── Timeline ─────────────────────────────────────────────

@router.get("/timeline")
async def get_timeline(
    category: str | None = None,
    action: str | None = None,
    since: str | None = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    since_dt = None
    if since:
        since_dt = datetime.fromisoformat(since)
    events = await db.get_events(category=category, action=action, since=since_dt, limit=limit, offset=offset)
    return {"events": events, "count": len(events)}


@router.get("/timeline/{event_id}")
async def get_timeline_event(event_id: str):
    event = await db.get_event_by_id(event_id)
    if not event:
        from fastapi import HTTPException
        raise HTTPException(404, "Event not found")
    return event


# ── Alerts ───────────────────────────────────────────────

@router.get("/alerts")
async def get_alerts(
    severity: str | None = None,
    acknowledged: bool | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    alerts = await db.get_alerts(severity=severity, acknowledged=acknowledged, limit=limit, offset=offset)
    return {"alerts": alerts, "count": len(alerts)}


@router.get("/alerts/{alert_id}")
async def get_alert(alert_id: str):
    alert = await db.get_alert_by_id(alert_id)
    if not alert:
        from fastapi import HTTPException
        raise HTTPException(404, "Alert not found")
    return alert


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str):
    ok = await db.acknowledge_alert(alert_id)
    if not ok:
        from fastapi import HTTPException
        raise HTTPException(404, "Alert not found")
    return {"status": "acknowledged"}


class SnoozeBody(BaseModel):
    hours: float = 1.0


@router.post("/alerts/{alert_id}/snooze")
async def snooze_alert(alert_id: str, body: SnoozeBody):
    until = datetime.now(timezone.utc) + timedelta(hours=body.hours)
    ok = await db.snooze_alert(alert_id, until)
    if not ok:
        from fastapi import HTTPException
        raise HTTPException(404, "Alert not found")
    return {"status": "snoozed", "until": until.isoformat()}


# ── Config (stored in settings table as JSON) ────────────

@router.get("/config/folders")
async def get_folders():
    raw = await db.get_setting("monitored_folders")
    if not raw:
        return {"folders": []}
    return {"folders": json.loads(raw)}


@router.post("/config/folders")
async def set_folders(folders: list[MonitoredFolder]):
    await db.set_setting("monitored_folders", json.dumps([f.model_dump() for f in folders]))
    return {"status": "saved", "count": len(folders)}


@router.get("/config/away-windows")
async def get_away_windows():
    raw = await db.get_setting("away_windows")
    if not raw:
        return {"windows": []}
    return {"windows": json.loads(raw)}


@router.post("/config/away-windows")
async def set_away_windows(windows: list[AwayWindow]):
    await db.set_setting("away_windows", json.dumps([w.model_dump() for w in windows]))
    return {"status": "saved", "count": len(windows)}


@router.get("/config/alerts")
async def get_alert_config():
    raw = await db.get_setting("alert_config")
    if not raw:
        return AlertConfig().model_dump()
    return json.loads(raw)


@router.post("/config/alerts")
async def set_alert_config(config: AlertConfig):
    await db.set_setting("alert_config", json.dumps(config.model_dump()))
    return {"status": "saved"}


# ── Status ───────────────────────────────────────────────

@router.get("/status")
async def get_status():
    return {
        "status": "running",
        "websocket_clients": len(_ws_clients),
    }


# ── WebSocket ────────────────────────────────────────────

ws_router = APIRouter()


@ws_router.websocket("/ws/events")
async def websocket_events(ws: WebSocket):
    await ws.accept()
    _ws_clients.append(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        if ws in _ws_clients:
            _ws_clients.remove(ws)
