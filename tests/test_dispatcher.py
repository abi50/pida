from __future__ import annotations

import pytest

from agent.alerts.dispatcher import AlertDispatcher
from agent.models.alert import Alert, Severity


def _make_alert(severity: Severity = Severity.HIGH) -> Alert:
    return Alert(severity=severity, message="test", source="test")


class TestAlertDispatcher:
    @pytest.mark.asyncio
    async def test_routes_to_matching_notifier(self):
        dispatcher = AlertDispatcher()
        received: list[Alert] = []

        async def notifier(a: Alert):
            received.append(a)

        dispatcher.add_route(Severity.HIGH, notifier)
        await dispatcher.dispatch(_make_alert(Severity.HIGH))
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_skips_below_threshold(self):
        dispatcher = AlertDispatcher()
        received: list[Alert] = []

        async def notifier(a: Alert):
            received.append(a)

        dispatcher.add_route(Severity.HIGH, notifier)
        await dispatcher.dispatch(_make_alert(Severity.LOW))
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_multiple_routes(self):
        dispatcher = AlertDispatcher()
        log_alerts: list[Alert] = []
        email_alerts: list[Alert] = []

        async def log_notifier(a): log_alerts.append(a)
        async def email_notifier(a): email_alerts.append(a)

        dispatcher.add_route(Severity.INFO, log_notifier)
        dispatcher.add_route(Severity.HIGH, email_notifier)

        await dispatcher.dispatch(_make_alert(Severity.MEDIUM))
        assert len(log_alerts) == 1
        assert len(email_alerts) == 0

        await dispatcher.dispatch(_make_alert(Severity.CRITICAL))
        assert len(log_alerts) == 2
        assert len(email_alerts) == 1

    @pytest.mark.asyncio
    async def test_notifier_error_does_not_crash(self):
        dispatcher = AlertDispatcher()
        good_results: list[Alert] = []

        async def bad_notifier(a): raise RuntimeError("boom")
        async def good_notifier(a): good_results.append(a)

        dispatcher.add_route(Severity.INFO, bad_notifier)
        dispatcher.add_route(Severity.INFO, good_notifier)

        await dispatcher.dispatch(_make_alert(Severity.HIGH))
        assert len(good_results) == 1

    @pytest.mark.asyncio
    async def test_info_reaches_info_route(self):
        dispatcher = AlertDispatcher()
        received: list[Alert] = []

        async def notifier(a): received.append(a)

        dispatcher.add_route(Severity.INFO, notifier)
        await dispatcher.dispatch(_make_alert(Severity.INFO))
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_critical_reaches_all_routes(self):
        dispatcher = AlertDispatcher()
        results = {"log": [], "toast": [], "email": []}

        async def log_n(a): results["log"].append(a)
        async def toast_n(a): results["toast"].append(a)
        async def email_n(a): results["email"].append(a)

        dispatcher.add_route(Severity.INFO, log_n)
        dispatcher.add_route(Severity.MEDIUM, toast_n)
        dispatcher.add_route(Severity.HIGH, email_n)

        await dispatcher.dispatch(_make_alert(Severity.CRITICAL))
        assert len(results["log"]) == 1
        assert len(results["toast"]) == 1
        assert len(results["email"]) == 1
