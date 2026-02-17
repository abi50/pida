from __future__ import annotations

import asyncio
import logging
import smtplib
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from typing import Any

from agent.models.alert import Alert
from agent.models.config import EmailConfig

logger = logging.getLogger(__name__)


class EmailNotifier:
    """Sends email alerts with throttling and batching."""

    def __init__(
        self,
        config: EmailConfig,
        smtp_class: Any = None,
    ) -> None:
        self._config = config
        self._throttle = timedelta(minutes=config.throttle_minutes)
        self._smtp_class = smtp_class or smtplib.SMTP
        self._last_sent: datetime | None = None
        self._pending: list[Alert] = []

    async def notify(self, alert: Alert) -> None:
        self._pending.append(alert)
        now = datetime.now(timezone.utc)

        if self._last_sent and (now - self._last_sent) < self._throttle:
            logger.debug("Email throttled, batching alert %s", alert.id)
            return

        await self._send_batch()

    async def flush(self) -> None:
        """Force send any pending alerts."""
        if self._pending:
            await self._send_batch()

    async def _send_batch(self) -> None:
        if not self._pending:
            return

        alerts = self._pending.copy()
        self._pending.clear()

        subject = f"PIDA: {len(alerts)} alert(s) — highest: {alerts[0].severity.value}"
        body_parts = []
        for a in alerts:
            body_parts.append(
                f"[{a.severity.value}] {a.message}\n"
                f"  Source: {a.source}\n"
                f"  Time: {a.created_at.isoformat()}\n"
            )
        body = "\n".join(body_parts)

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = self._config.sender_address
        msg["To"] = self._config.recipient_address

        try:
            await asyncio.to_thread(self._send_smtp, msg)
            self._last_sent = datetime.now(timezone.utc)
            logger.info("Sent email with %d alert(s)", len(alerts))
        except Exception:
            logger.exception("Failed to send email")
            # Put alerts back for retry
            self._pending.extend(alerts)

    def _send_smtp(self, msg: MIMEText) -> None:
        with self._smtp_class(self._config.smtp_host, self._config.smtp_port) as server:
            server.starttls()
            if self._config.sender_address and self._config.sender_password:
                server.login(self._config.sender_address, self._config.sender_password)
            server.send_message(msg)
