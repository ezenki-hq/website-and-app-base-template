from collections.abc import Mapping

import msgpack


def pack_event(
    subject: str,
    headers: Mapping[str, str] | None,
    message: bytes,
) -> bytes:
    return msgpack.packb(
        {
            "event": subject,
            "headers": dict(headers or {}),
            "message": message,
        },
        use_bin_type=True,
    )
