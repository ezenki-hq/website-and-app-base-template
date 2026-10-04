from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

import jwt
from django.conf import settings

from events.subjects import validate_events


_ISSUER = "website-app-template"
_AUDIENCE = "events-websocket"
_ALGORITHM = "HS256"
_REQUIRED_CLAIMS = ("iss", "aud", "sub", "iat", "exp", "jti", "events")


@dataclass(frozen=True)
class EventClaims:
    identity: str
    events: tuple[str, ...]
    expires_at: datetime


def issue_event_token(identity: str, events: Sequence[str]) -> str:
    if not isinstance(identity, str) or not identity.strip():
        raise ValueError("identity must be a nonempty string")
    validated_events = validate_events(events)
    issued_at = int(datetime.now(timezone.utc).timestamp())
    ttl = settings.EVENTS_JWT_TTL_SECONDS
    if not isinstance(ttl, int) or isinstance(ttl, bool) or ttl <= 0:
        raise ValueError("EVENTS_JWT_TTL_SECONDS must be a positive integer")
    claims = {
        "iss": _ISSUER,
        "aud": _AUDIENCE,
        "sub": identity,
        "iat": issued_at,
        "exp": issued_at + ttl,
        "jti": str(uuid4()),
        "events": list(validated_events),
    }
    return jwt.encode(claims, settings.EVENTS_JWT_SIGNING_SECRET, algorithm=_ALGORITHM)


def decode_event_token(token: str) -> EventClaims:
    if not isinstance(token, str) or not token:
        raise jwt.InvalidTokenError("token must be a nonempty string")
    try:
        claims = jwt.decode(
            token,
            settings.EVENTS_JWT_SIGNING_SECRET,
            algorithms=[_ALGORITHM],
            audience=_AUDIENCE,
            issuer=_ISSUER,
            options={"require": list(_REQUIRED_CLAIMS), "strict_aud": True},
        )
        identity = claims.get("sub")
        jti = claims.get("jti")
        raw_events = claims.get("events")
        if not isinstance(identity, str) or not identity.strip():
            raise jwt.InvalidTokenError("sub must be a nonempty string")
        if not isinstance(jti, str) or not jti:
            raise jwt.InvalidTokenError("jti must be a nonempty string")
        if not isinstance(raw_events, list):
            raise jwt.InvalidTokenError("events must be a list")
        events = validate_events(raw_events)
        exp = claims.get("exp")
        if not isinstance(exp, (int, float)) or isinstance(exp, bool):
            raise jwt.InvalidTokenError("exp must be a numeric timestamp")
        return EventClaims(
            identity=identity,
            events=events,
            expires_at=datetime.fromtimestamp(exp, tz=timezone.utc),
        )
    except jwt.InvalidTokenError:
        raise
    except (TypeError, ValueError, OverflowError) as exc:
        raise jwt.InvalidTokenError("invalid event token claims") from exc
