from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from agent.api.routes import router, ws_router, broadcast_event
from agent.config import settings
from agent.db import database as db
from agent.engine.event_bus import EventBus
from agent.engine.timeline import TimelineEngine
from agent.alerts.dispatcher import AlertDispatcher
from agent.alerts.log_notifier import log_notify
from agent.models.alert import Alert, Severity
from agent.models.config import MonitoredFolder, AwayWindow, AlertConfig
from agent.monitors.folder_monitor import FolderMonitor
from agent.monitors.input_monitor import InputMonitor
from agent.monitors.session_monitor import SessionMonitor

logger = logging.getLogger(__name__)

_FRONTEND_DIST = Path(__file__).resolve().parent / "frontend" / "dist"

# Global references for lifecycle
_bus: EventBus | None = None
_timeline: TimelineEngine | None = None
_dispatcher: AlertDispatcher | None = None
_folder_monitor: FolderMonitor | None = None
_input_monitor: InputMonitor | None = None
_session_monitor: SessionMonitor | None = None


async def _load_config_from_db() -> tuple[list[MonitoredFolder], list[AwayWindow], AlertConfig]:
    folders_raw = await db.get_setting("monitored_folders")
    folders = []
    if folders_raw:
        folders = [MonitoredFolder(**f) for f in json.loads(folders_raw)]

    windows_raw = await db.get_setting("away_windows")
    windows = []
    if windows_raw:
        windows = [AwayWindow(**w) for w in json.loads(windows_raw)]

    alert_raw = await db.get_setting("alert_config")
    alert_config = AlertConfig()
    if alert_raw:
        alert_config = AlertConfig(**json.loads(alert_raw))

    return folders, windows, alert_config


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _bus, _timeline, _dispatcher, _folder_monitor, _input_monitor, _session_monitor

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    await db.init_db()

    folders, windows, alert_config = await _load_config_from_db()

    # Event bus
    _bus = EventBus()
    await _bus.start()

    # Dispatcher
    _dispatcher = AlertDispatcher()
    _dispatcher.add_route(Severity.INFO, log_notify)

    async def on_alert(alert: Alert):
        await _dispatcher.dispatch(alert)
        await broadcast_event({"type": "alert", "data": alert.model_dump(mode="json")})

    # Timeline engine
    _timeline = TimelineEngine(_bus, away_windows=windows, on_alert=on_alert)
    await _timeline.start()

    # Subscribe bus to broadcast events to WebSocket
    async def ws_forward(event):
        await broadcast_event({"type": "event", "data": event.model_dump(mode="json")})
    _bus.subscribe(ws_forward)

    # Monitors
    folder_paths = [f.path for f in folders if f.enabled]
    if folder_paths:
        _folder_monitor = FolderMonitor(_bus, folders=folder_paths)
        await _folder_monitor.start()

    _input_monitor = InputMonitor(
        _bus,
        poll_interval=settings.input_poll_interval,
        away_windows=windows,
    )
    await _input_monitor.start()

    _session_monitor = SessionMonitor(_bus, poll_interval=settings.session_poll_interval)
    await _session_monitor.start()

    logger.info("PIDA started — monitoring %d folders, %d away windows", len(folder_paths), len(windows))
    yield

    # Shutdown
    if _session_monitor:
        await _session_monitor.stop()
    if _input_monitor:
        await _input_monitor.stop()
    if _folder_monitor:
        await _folder_monitor.stop()
    if _timeline:
        await _timeline.stop()
    if _bus:
        await _bus.stop()
    logger.info("PIDA stopped")


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)
    app.include_router(ws_router)

    # Serve frontend if built
    if _FRONTEND_DIST.exists():
        app.mount("/assets", StaticFiles(directory=str(_FRONTEND_DIST / "assets")), name="static")

        from fastapi.responses import FileResponse

        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str):
            return FileResponse(str(_FRONTEND_DIST / "index.html"))

    return app


app = create_app()
