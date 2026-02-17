from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from agent.config import settings
from agent.models.alert import Alert
from agent.models.event import TimelineEvent

logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


async def _connect() -> aiosqlite.Connection:
    """Open a new connection with WAL mode and Row factory."""
    db = await aiosqlite.connect(settings.db_path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    return db


async def init_db() -> None:
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
    schema = _SCHEMA_PATH.read_text()
    db = await _connect()
    try:
        await db.executescript(schema)
        await db.commit()
    finally:
        await db.close()


# ── Timeline events ──────────────────────────────────────


async def insert_event(event: TimelineEvent) -> None:
    db = await _connect()
    try:
        await db.execute(
            """INSERT INTO timeline_events
               (id, source, category, action, subject, target, detail, severity, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event.id,
                event.source.value,
                event.category.value,
                event.action.value,
                event.subject,
                event.target,
                json.dumps(event.detail),
                event.severity,
                event.timestamp.isoformat(),
            ),
        )
        await db.commit()
    finally:
        await db.close()


async def get_events(
    category: str | None = None,
    action: str | None = None,
    since: datetime | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    clauses: list[str] = []
    params: list = []
    if category:
        clauses.append("category = ?")
        params.append(category)
    if action:
        clauses.append("action = ?")
        params.append(action)
    if since:
        clauses.append("timestamp >= ?")
        params.append(since.isoformat())
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    query = f"SELECT * FROM timeline_events {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    db = await _connect()
    try:
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
    finally:
        await db.close()
    return [_row_to_dict(r) for r in rows]


async def get_event_by_id(event_id: str) -> dict | None:
    db = await _connect()
    try:
        cursor = await db.execute("SELECT * FROM timeline_events WHERE id = ?", (event_id,))
        row = await cursor.fetchone()
    finally:
        await db.close()
    return _row_to_dict(row) if row else None


# ── Alerts ───────────────────────────────────────────────


async def insert_alert(alert: Alert) -> None:
    db = await _connect()
    try:
        await db.execute(
            """INSERT INTO alerts
               (id, severity, message, source, detail, acknowledged, snoozed_until, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                alert.id,
                alert.severity.value,
                alert.message,
                alert.source,
                json.dumps(alert.detail),
                int(alert.acknowledged),
                alert.snoozed_until.isoformat() if alert.snoozed_until else None,
                alert.created_at.isoformat(),
            ),
        )
        await db.commit()
    finally:
        await db.close()


async def get_alerts(
    severity: str | None = None,
    acknowledged: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    clauses: list[str] = []
    params: list = []
    if severity:
        clauses.append("severity = ?")
        params.append(severity)
    if acknowledged is not None:
        clauses.append("acknowledged = ?")
        params.append(int(acknowledged))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    query = f"SELECT * FROM alerts {where} ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    db = await _connect()
    try:
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
    finally:
        await db.close()
    return [_row_to_dict(r) for r in rows]


async def get_alert_by_id(alert_id: str) -> dict | None:
    db = await _connect()
    try:
        cursor = await db.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,))
        row = await cursor.fetchone()
    finally:
        await db.close()
    return _row_to_dict(row) if row else None


async def acknowledge_alert(alert_id: str) -> bool:
    db = await _connect()
    try:
        cursor = await db.execute(
            "UPDATE alerts SET acknowledged = 1 WHERE id = ?", (alert_id,)
        )
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()


async def snooze_alert(alert_id: str, until: datetime) -> bool:
    db = await _connect()
    try:
        cursor = await db.execute(
            "UPDATE alerts SET snoozed_until = ? WHERE id = ?",
            (until.isoformat(), alert_id),
        )
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()


# ── Settings ─────────────────────────────────────────────


async def get_setting(key: str) -> str | None:
    db = await _connect()
    try:
        cursor = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = await cursor.fetchone()
    finally:
        await db.close()
    return row["value"] if row else None


async def set_setting(key: str, value: str) -> None:
    db = await _connect()
    try:
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
        await db.commit()
    finally:
        await db.close()


# ── Helpers ──────────────────────────────────────────────


def _row_to_dict(row: aiosqlite.Row) -> dict:
    d = dict(row)
    if "detail" in d and isinstance(d["detail"], str):
        try:
            d["detail"] = json.loads(d["detail"])
        except (json.JSONDecodeError, TypeError):
            pass
    if "acknowledged" in d:
        d["acknowledged"] = bool(d["acknowledged"])
    return d
