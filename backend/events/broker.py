from collections.abc import Awaitable, Callable

import nats
from django.conf import settings
from nats.aio.msg import Msg
from nats.aio.subscription import Subscription


class NatsEventBridge:
    def __init__(self) -> None:
        self._connection = None
        self._subscriptions: list[Subscription] = []
        self._on_closed: Callable[[], Awaitable[None]] | None = None
        self._closing = False

    async def start(
        self,
        subjects: tuple[str, ...],
        on_message: Callable[[Msg], Awaitable[None]],
        on_closed: Callable[[], Awaitable[None]],
    ) -> None:
        self._on_closed = on_closed
        setup_errors: list[Exception] = []
        setup_complete = False

        async def handle_closed() -> None:
            if not self._closing and self._on_closed is not None:
                await self._on_closed()

        async def handle_error(error: Exception) -> None:
            if not setup_complete:
                setup_errors.append(error)
            elif not self._closing and self._on_closed is not None:
                await self._on_closed()

        try:
            self._connection = await nats.connect(
                servers=settings.NATS_URL,
                user=settings.NATS_BACKEND_USER,
                password=settings.NATS_BACKEND_PASSWORD,
                closed_cb=handle_closed,
                error_cb=handle_error,
            )
            for subject in subjects:
                async def handle_message(message: Msg) -> None:
                    await on_message(message)

                subscription = await self._connection.subscribe(
                    subject, cb=handle_message
                )
                self._subscriptions.append(subscription)
            await self._connection.flush()
            # The server can report subscription permissions just after the first PONG.
            await self._connection.flush()
            if setup_errors:
                raise setup_errors[0]
            setup_complete = True
        except BaseException:
            await self.close()
            raise

    async def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        subscriptions, self._subscriptions = self._subscriptions, []
        connection, self._connection = self._connection, None
        for subscription in subscriptions:
            try:
                await subscription.unsubscribe()
            except Exception:
                pass
        if connection is not None:
            try:
                await connection.close()
            except Exception:
                pass
