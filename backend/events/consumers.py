import asyncio
import logging
from contextlib import suppress
from datetime import datetime, timezone

from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings

from events.broker import NatsEventBridge
from events.frames import pack_event
from events.tokens import decode_event_token


logger = logging.getLogger(__name__)
EVENTS_MESSAGE_QUEUE_LIMIT = 100


class EventsConsumer(AsyncWebsocketConsumer):
    async def connect(self) -> None:
        self.bridge = None
        self.expiry_task = None
        self.message_task = None
        self.message_queue = asyncio.Queue(maxsize=EVENTS_MESSAGE_QUEUE_LIMIT)
        self.delivery_overflow = False
        self.accepted = False

        if not self._origin_is_allowed():
            await self.close()
            return

        try:
            token = self.scope["url_route"]["kwargs"]["token"]
            claims = decode_event_token(token)
            self.bridge = NatsEventBridge()
            await self.bridge.start(
                claims.events,
                self._forward_message,
                self._broker_closed,
            )
        except Exception:
            await self._cleanup()
            await self.close()
            return

        await self.accept()
        self.accepted = True
        if self.delivery_overflow:
            await self.close(code=1013)
            return
        self.message_task = asyncio.create_task(self._deliver_messages())
        delay = max(
            0.0,
            (claims.expires_at - datetime.now(timezone.utc)).total_seconds(),
        )
        self.expiry_task = asyncio.create_task(self._expire_after(delay))

    async def receive(self, text_data=None, bytes_data=None) -> None:
        await self.close(code=1008)

    async def disconnect(self, close_code: int) -> None:
        await self._cleanup()

    async def _forward_message(self, message) -> None:
        if self.message_queue.full():
            if not self.delivery_overflow:
                self.delivery_overflow = True
                if self.accepted:
                    await self.close(code=1013)
            return
        self.message_queue.put_nowait(message)

    async def _deliver_messages(self) -> None:
        try:
            while True:
                message = await self.message_queue.get()
                await self.send(
                    bytes_data=pack_event(
                        message.subject,
                        message.headers,
                        message.data,
                    )
                )
        except Exception:
            logger.exception("Event WebSocket delivery failed")
            if self.accepted:
                with suppress(Exception):
                    await self.close(code=1011)

    async def _broker_closed(self) -> None:
        if self.accepted:
            await self.close(code=1011)

    async def _expire_after(self, delay: float) -> None:
        await asyncio.sleep(delay)
        if self.accepted:
            await self.close(code=1008)

    async def _cleanup(self) -> None:
        task = getattr(self, "expiry_task", None)
        if task is not None and task is not asyncio.current_task():
            task.cancel()
        message_task = getattr(self, "message_task", None)
        if message_task is not None and message_task is not asyncio.current_task():
            message_task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await message_task
        self.message_task = None
        bridge = getattr(self, "bridge", None)
        self.bridge = None
        if bridge is not None:
            await bridge.close()

    def _origin_is_allowed(self) -> bool:
        origin = next(
            (
                value.decode("latin1")
                for name, value in self.scope.get("headers", [])
                if name.lower() == b"origin"
            ),
            None,
        )
        if origin is None:
            return True
        allowed_origins = getattr(settings, "EVENTS_ALLOWED_ORIGINS", ())
        return origin in allowed_origins
