from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

import jwt
import msgpack
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.test import override_settings
from django.urls import path

from events.consumers import EventsConsumer
from events.tokens import EventClaims


class FakeBridge:
    instances = []

    def __init__(self):
        self.close = AsyncMock()
        self.on_closed = None
        type(self).instances.append(self)

    async def start(self, subjects, on_message, on_closed):
        self.subjects = subjects
        self.on_message = on_message
        self.on_closed = on_closed
        self.started = True


class EventsConsumerTests(IsolatedAsyncioTestCase):
    def setUp(self):
        FakeBridge.instances = []
        self.application = URLRouter(
            [path("ws/events/<str:token>", EventsConsumer.as_asgi())]
        )
        self.claims = EventClaims(
            identity="user-1",
            events=("app.one", "app.two"),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )

    async def test_valid_token_subscribes_and_disconnect_cleans_up(self):
        with (
            patch("events.consumers.decode_event_token", return_value=self.claims),
            patch("events.consumers.NatsEventBridge", FakeBridge),
        ):
            communicator = WebsocketCommunicator(self.application, "/ws/events/token")
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            self.assertEqual(FakeBridge.instances[0].subjects, self.claims.events)
            await communicator.disconnect()
            FakeBridge.instances[0].close.assert_awaited_once()

    async def test_forwards_received_nats_message_as_binary_frame(self):
        with (
            patch("events.consumers.decode_event_token", return_value=self.claims),
            patch("events.consumers.NatsEventBridge", FakeBridge),
        ):
            communicator = WebsocketCommunicator(self.application, "/ws/events/token")
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await FakeBridge.instances[0].on_message(
                SimpleNamespace(subject="app.one", headers=None, data=b"\x00\xff")
            )
            output = await communicator.receive_output(timeout=1)
            self.assertEqual(output["type"], "websocket.send")
            frame = msgpack.unpackb(output["bytes"], raw=False)
            self.assertEqual(
                frame,
                {"event": "app.one", "headers": {}, "message": b"\x00\xff"},
            )
            await communicator.disconnect()

    async def test_invalid_token_never_connects_to_nats(self):
        with patch(
            "events.consumers.decode_event_token",
            side_effect=jwt.InvalidTokenError("invalid"),
        ), patch("events.broker.nats.connect", new=AsyncMock()) as connect:
            communicator = WebsocketCommunicator(self.application, "/ws/events/bad")
            connected, _ = await communicator.connect()
            self.assertFalse(connected)
            connect.assert_not_awaited()

    async def test_origin_policy(self):
        with override_settings(EVENTS_ALLOWED_ORIGINS=("https://app.example",)), patch(
            "events.consumers.decode_event_token", return_value=self.claims
        ), patch("events.consumers.NatsEventBridge", FakeBridge):
            rejected = WebsocketCommunicator(
                self.application,
                "/ws/events/token",
                headers=[(b"origin", b"https://evil.example")],
            )
            connected, _ = await rejected.connect()
            self.assertFalse(connected)

            native = WebsocketCommunicator(self.application, "/ws/events/token")
            connected, _ = await native.connect()
            self.assertTrue(connected)
            await native.disconnect()

    async def test_expired_connection_closes_with_policy_code(self):
        claims = EventClaims(
            identity="user-1",
            events=("app.one",),
            expires_at=datetime.now(timezone.utc) + timedelta(milliseconds=5),
        )
        with patch("events.consumers.decode_event_token", return_value=claims), patch(
            "events.consumers.NatsEventBridge", FakeBridge
        ):
            communicator = WebsocketCommunicator(self.application, "/ws/events/token")
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            output = await communicator.receive_output(timeout=1)
            self.assertEqual(output["code"], 1008)

    async def test_broker_failure_closes_with_server_error_code(self):
        with (
            patch("events.consumers.decode_event_token", return_value=self.claims),
            patch("events.consumers.NatsEventBridge", FakeBridge),
        ):
            communicator = WebsocketCommunicator(self.application, "/ws/events/token")
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await FakeBridge.instances[0].on_closed()
            output = await communicator.receive_output(timeout=1)
            self.assertEqual(output["code"], 1011)
