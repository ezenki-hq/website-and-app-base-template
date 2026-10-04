from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from django.test import override_settings

from events.broker import NatsEventBridge


class FakeSubscription:
    def __init__(self, subject):
        self.subject = subject
        self.unsubscribe = AsyncMock()


class FakeConnection:
    def __init__(self, fail_on_subject=None, async_error=None, async_error_on_flush=1):
        self.fail_on_subject = fail_on_subject
        self.async_error = async_error
        self.async_error_on_flush = async_error_on_flush
        self.flush_count = 0
        self.subscriptions = []
        self.flush = AsyncMock(side_effect=self._flush)
        self.close = AsyncMock()
        self.error_cb = None

    async def _flush(self):
        self.flush_count += 1
        if (
            self.async_error is not None
            and self.flush_count == self.async_error_on_flush
        ):
            await self.error_cb(self.async_error)

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
            self.assertEqual(connection.flush.await_count, 2)
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

    async def test_async_permission_error_fails_setup_and_cleans_up(self):
        connection = FakeConnection(async_error=PermissionError("permission denied"))

        async def connect(**kwargs):
            connection.error_cb = kwargs["error_cb"]
            return connection

        with patch("events.broker.nats.connect", new=AsyncMock(side_effect=connect)):
            bridge = NatsEventBridge()
            with self.assertRaisesRegex(PermissionError, "permission denied"):
                await bridge.start(("app.one",), AsyncMock(), AsyncMock())

        connection.subscriptions[0].unsubscribe.assert_awaited_once()
        connection.close.assert_awaited_once()

    async def test_permission_error_after_first_flush_still_fails_setup(self):
        connection = FakeConnection(
            async_error=PermissionError("permission denied"), async_error_on_flush=2
        )

        async def connect(**kwargs):
            connection.error_cb = kwargs["error_cb"]
            return connection

        with patch("events.broker.nats.connect", new=AsyncMock(side_effect=connect)):
            bridge = NatsEventBridge()
            with self.assertRaisesRegex(PermissionError, "permission denied"):
                await bridge.start(("app.one",), AsyncMock(), AsyncMock())

        self.assertEqual(connection.flush.await_count, 2)
        connection.subscriptions[0].unsubscribe.assert_awaited_once()
        connection.close.assert_awaited_once()

    async def test_async_error_after_setup_closes_the_websocket(self):
        connection = FakeConnection()
        on_closed = AsyncMock()

        async def connect(**kwargs):
            connection.error_cb = kwargs["error_cb"]
            return connection

        with patch("events.broker.nats.connect", new=AsyncMock(side_effect=connect)):
            bridge = NatsEventBridge()
            await bridge.start(("app.one",), AsyncMock(), on_closed)
            await connection.error_cb(PermissionError("permission denied"))

        on_closed.assert_awaited_once()
        await bridge.close()
