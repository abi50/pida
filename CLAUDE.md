# CLAUDE.md — PIDA

## Project Overview
Personal Intrusion Detection Agent — a background security agent that monitors your Windows machine and detects if someone other than you is using it. Monitors folders in real-time, detects activity during "away" time windows, parses Windows session/logon events, and sends alerts via desktop toast + email.

## Architecture
- `agent/monitors/` — data collection (FolderMonitor via watchdog, InputMonitor via GetLastInputInfo, SessionMonitor via win32evtlog)
- `agent/engine/` — event bus (asyncio.Queue), timeline engine (persist + rule evaluation)
- `agent/alerts/` — alert dispatcher with pluggable notifiers (log, toast, email, WebSocket)
- `agent/models/` — Pydantic models (TimelineEvent, Alert, config models)
- `agent/db/` — SQLite via aiosqlite
- `agent/api/` — FastAPI REST + WebSocket
- `agent/tray.py` — system tray entry point (pystray)
- `frontend/` — React dashboard

## Commands
```bash
# Install
pip install -r requirements.txt

# Run agent (tray + server)
python -m agent.tray

# Run server only (dev)
uvicorn agent.main:app --port 8765

# Tests
pytest tests/ -v
```

## Constraints
- Host bound to 127.0.0.1 — personal agent, no network exposure
- All Windows APIs injectable for cross-platform testing
- Config stored in SQLite settings table (runtime CRUD via API)
- Tray owns main thread; FastAPI runs in daemon thread
