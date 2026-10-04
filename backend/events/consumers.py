import asyncio
from datetime import datetime, timezone

from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings

from events.broker import NatsEventBridge
from events.frames import pack_event
from events.tokens import decode_event_token


class EventsConsumer(AsyncWebsocketConsumer):
    async def connect(self) -> None:
        self.bridge = None
        self.expiry_task = None
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
        await self.send(
            bytes_data=pack_event(
                message.subject,
                message.headers,
                message.data,
            )
        )

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
