from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from django.test import override_settings

from events.broker import NatsEventBridge


class FakeSubscription:
    def __init__(self, subject):
        self.subject = subject
        self.unsubscribe = AsyncMock()


class FakeConnection:
    def __init__(self, fail_on_subject=None):
        self.fail_on_subject = fail_on_subject
        self.subscriptions = []
        self.flush = AsyncMock()
        self.close = AsyncMock()

    async def subscribe(self, subject, cb):
        if subject == self.fail_on_subject:
            raise RuntimeError("subscription failed")
        subscription = FakeSubscription(subject)
        self.subscriptions.append(subscription)
        return subscription


class NatsEventBridgeTests(IsolatedAsyncioTestCase):
    def setUp(self):
        override = override_settings(
            NATS_URL="nats://nats:4222",
            NATS_BACKEND_USER="backend",
            NATS_BACKEND_PASSWORD="test-password",
        )
        override.enable()
        self.addCleanup(override.disable)

    async def test_subscribes_to_all_subjects_and_closes_resources(self):
        connection = FakeConnection()
        with patch(
            "events.broker.nats.connect", new=AsyncMock(return_value=connection)
        ) as connect:
            bridge = NatsEventBridge()
            await bridge.start(("app.one", "app.two"), AsyncMock(), AsyncMock())
            connect.assert_awaited_once()
            self.assertEqual(
                connect.await_args.kwargs["servers"], "nats://nats:4222"
            )
            self.assertEqual(connect.await_args.kwargs["user"], "backend")
            self.assertEqual(
                connect.await_args.kwargs["password"], "test-password"
            )
            self.assertEqual(
                [item.subject for item in connection.subscriptions],
                ["app.one", "app.two"],
            )
            connection.flush.assert_awaited_once()
            await bridge.close()
            await bridge.close()
        for subscription in connection.subscriptions:
            subscription.unsubscribe.assert_awaited_once()
        connection.close.assert_awaited_once()

    async def test_partial_subscription_failure_cleans_up(self):
        connection = FakeConnection(fail_on_subject="app.two")
        with patch("events.broker.nats.connect", new=AsyncMock(return_value=connection)):
            bridge = NatsEventBridge()
            with self.assertRaises(RuntimeError):
                await bridge.start(("app.one", "app.two"), AsyncMock(), AsyncMock())
        connection.subscriptions[0].unsubscribe.assert_awaited_once()
        connection.close.assert_awaited_once()
