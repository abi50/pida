from __future__ import annotations

import pytest

from agent.alerts.email_notifier import EmailNotifier
from agent.models.alert import Alert, Severity
from agent.models.config import EmailConfig


def _make_config(**kwargs) -> EmailConfig:
    defaults = dict(
        enabled=True,
        smtp_host="localhost",
        smtp_port=587,
        sender_address="pida@test.com",
        sender_password="pass",
        recipient_address="user@test.com",
        throttle_minutes=5,
    )
    defaults.update(kwargs)
    return EmailConfig(**defaults)


def _make_alert(severity: Severity = Severity.HIGH) -> Alert:
    return Alert(severity=severity, message="test alert", source="test")


class FakeSMTP:
    """Mock SMTP that records calls."""
    instances: list[FakeSMTP] = []

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.messages: list = []
        self.started_tls = False
        self.logged_in = False
        FakeSMTP.instances.append(self)

    def starttls(self):
        self.started_tls = True

    def login(self, user, password):
        self.logged_in = True

    def send_message(self, msg):
        self.messages.append(msg)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class TestEmailNotifier:
    def setup_method(self):
        FakeSMTP.instances.clear()

    @pytest.mark.asyncio
    async def test_sends_email(self):
        notifier = EmailNotifier(_make_config(), smtp_class=FakeSMTP)
        await notifier.notify(_make_alert())
        assert len(FakeSMTP.instances) == 1
        assert len(FakeSMTP.instances[0].messages) == 1

    @pytest.mark.asyncio
    async def test_throttle_batches(self):
        notifier = EmailNotifier(_make_config(throttle_minutes=5), smtp_class=FakeSMTP)
        await notifier.notify(_make_alert())  # sends immediately
        await notifier.notify(_make_alert())  # throttled
        await notifier.notify(_make_alert())  # throttled

        assert len(FakeSMTP.instances) == 1

        await notifier.flush()
        assert len(FakeSMTP.instances) == 2

    @pytest.mark.asyncio
    async def test_subject_includes_count(self):
        notifier = EmailNotifier(_make_config(throttle_minutes=0), smtp_class=FakeSMTP)
        await notifier.notify(_make_alert())
        msg = FakeSMTP.instances[0].messages[0]
        assert "1 alert(s)" in msg["Subject"]

    @pytest.mark.asyncio
    async def test_batch_subject_includes_count(self):
        notifier = EmailNotifier(_make_config(throttle_minutes=5), smtp_class=FakeSMTP)
        await notifier.notify(_make_alert())
        await notifier.notify(_make_alert())
        await notifier.notify(_make_alert())
        await notifier.flush()

        msg = FakeSMTP.instances[1].messages[0]
        assert "2 alert(s)" in msg["Subject"]

    @pytest.mark.asyncio
    async def test_starttls_and_login(self):
        notifier = EmailNotifier(_make_config(), smtp_class=FakeSMTP)
        await notifier.notify(_make_alert())
        smtp = FakeSMTP.instances[0]
        assert smtp.started_tls is True
        assert smtp.logged_in is True

    @pytest.mark.asyncio
    async def test_failed_send_keeps_pending(self):
        class FailSMTP(FakeSMTP):
            def send_message(self, msg):
                raise ConnectionError("fail")

        notifier = EmailNotifier(_make_config(), smtp_class=FailSMTP)
        await notifier.notify(_make_alert())
        assert len(notifier._pending) == 1
