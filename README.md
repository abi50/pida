# PIDA — Personal Intrusion Detection Agent

A lightweight Windows agent that detects if someone else is using your computer while you're away. Monitors file changes, keyboard/mouse activity, login attempts, and remote desktop sessions — then alerts you via dashboard, toast notifications, and email.

## How It Works

```
System Tray (pystray)
  └── FastAPI Server (127.0.0.1:8765)
        └── Event Bus (async pub/sub)
              ├── FolderMonitor   — watchdog, real-time file changes
              ├── InputMonitor    — GetLastInputInfo polling, away-window detection
              └── SessionMonitor  — Windows Event Log (logon/lock/RDP/power)
                      │
              Timeline Engine — persists events, evaluates rules → alerts
                      │
              Alert Dispatcher
              ├── LogNotifier       (INFO+)
              ├── DashboardNotifier (LOW+, WebSocket push)
              ├── ToastNotifier     (MEDIUM+, plyer)
              └── EmailNotifier     (HIGH+, SMTP, throttled & batched)
```

## Alert Rules

| Trigger | Severity | When |
|---------|----------|------|
| File created/modified/deleted in monitored folder | **HIGH** | During away window |
| Keyboard/mouse activity (sustained >10s) | **MEDIUM** | During away window |
| Failed login attempt | **HIGH** | Anytime |
| Remote Desktop (RDP) session | **CRITICAL** | During away window |

## Quick Start

```bash
# Clone & install
git clone https://github.com/abi50/pida.git
cd pida
pip install -r requirements.txt

# Run (server only)
python -m uvicorn agent.main:app --host 127.0.0.1 --port 8765

# Run (with system tray icon)
python -m agent
```

Then open **http://127.0.0.1:8765** in your browser.

## Dashboard

Three pages:

- **Timeline** — chronological event feed (file changes, input, sessions, system)
- **Alerts** — active alerts with Acknowledge and Snooze buttons
- **Settings** — configure monitored folders and away windows (JSON editor)

## Configuration

All config is stored in SQLite and editable via the dashboard API:

**Monitored Folders** — `POST /api/config/folders`
```json
[{"path": "C:/Users/you/Desktop", "recursive": true, "enabled": true}]
```

**Away Windows** — `POST /api/config/away-windows`
```json
[{"label": "Work hours", "start_hour": 9, "end_hour": 17, "days": [0,1,2,3,4]}]
```

Overnight windows work too (e.g. `start_hour: 23, end_hour: 6`).

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/timeline` | GET | List events (filter by category, action, since) |
| `/api/timeline/{id}` | GET | Get event by ID |
| `/api/alerts` | GET | List alerts (filter by severity, acknowledged) |
| `/api/alerts/{id}/acknowledge` | POST | Mark alert as seen |
| `/api/alerts/{id}/snooze` | POST | Snooze alert (`{"hours": 1}`) |
| `/api/config/folders` | GET/POST | Monitored folders |
| `/api/config/away-windows` | GET/POST | Away time windows |
| `/api/config/alerts` | GET/POST | Alert routing config |
| `/api/status` | GET | Server status |
| `/ws/events` | WS | Real-time event/alert stream |

## Tests

```bash
pytest tests/ -v
```

102 tests covering: models, database CRUD, event bus, all 3 monitors, timeline engine, alert dispatcher, email notifier, API routes, and end-to-end integration.

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, aiosqlite, watchdog, pywin32, pydantic
- **Frontend**: React 18, TypeScript, Vite
- **Notifications**: plyer (toast), smtplib (email)
- **System tray**: pystray + Pillow

## Project Structure

```
pida/
├── agent/
│   ├── api/routes.py          # REST + WebSocket endpoints
│   ├── alerts/
│   │   ├── dispatcher.py      # Severity-based routing
│   │   ├── email_notifier.py  # SMTP with throttle/batch
│   │   ├── log_notifier.py    # Python logging
│   │   └── toast_notifier.py  # Desktop notifications
│   ├── db/
│   │   ├── database.py        # aiosqlite CRUD
│   │   └── schema.sql         # 3 tables
│   ├── engine/
│   │   ├── event_bus.py       # Async pub/sub
│   │   └── timeline.py        # Rule evaluation
│   ├── models/
│   │   ├── alert.py           # Alert + Severity
│   │   ├── config.py          # MonitoredFolder, AwayWindow, EmailConfig
│   │   └── event.py           # TimelineEvent + enums
│   ├── monitors/
│   │   ├── base.py            # BaseMonitor ABC
│   │   ├── folder_monitor.py  # watchdog → asyncio bridge
│   │   ├── input_monitor.py   # GetLastInputInfo polling
│   │   └── session_monitor.py # Windows Event Log reader
│   ├── frontend/              # React dashboard
│   ├── main.py                # FastAPI app + lifespan wiring
│   ├── config.py              # Settings (pydantic-settings)
│   └── tray.py                # System tray entry point
├── tests/                     # 102 tests
├── requirements.txt
└── pyproject.toml
```

## License

MIT
