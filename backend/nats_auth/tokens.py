from datetime import UTC, datetime, timedelta
import uuid

from django.conf import settings
import jwt

from nats_auth.config import NatsScope, PermissionSet


ALGORITHM = "HS256"
REQUIRED_CLAIMS = ("sub", "iss", "aud", "iat", "exp", "jti", "nats")


def scope_to_claim(scope: NatsScope) -> dict[str, object]:
    return {
        "account": scope.account,
        "pub": {
            "allow": list(scope.pub.allow),
            "deny": list(scope.pub.deny),
        },
        "sub": {
            "allow": list(scope.sub.allow),
            "deny": list(scope.sub.deny),
        },
    }


def _permission_set_from_claim(claim: object) -> PermissionSet:
    if not isinstance(claim, dict):
        raise jwt.InvalidTokenError("malformed nats scope")

    allow = claim.get("allow")
    deny = claim.get("deny")
    if not _valid_subject_list(allow) or not _valid_subject_list(deny):
        raise jwt.InvalidTokenError("malformed nats scope")

    return PermissionSet(allow=tuple(allow), deny=tuple(deny))


def _valid_subject_list(value: object) -> bool:
    return isinstance(value, list) and all(
        isinstance(subject, str) and bool(subject) for subject in value
    )


def scope_from_claim(claim: object) -> NatsScope:
    if not isinstance(claim, dict):
        raise jwt.InvalidTokenError("malformed nats scope")

    account = claim.get("account")
    if not isinstance(account, str) or not account:
        raise jwt.InvalidTokenError("malformed nats scope")

    return NatsScope(
        account=account,
        pub=_permission_set_from_claim(claim.get("pub")),
        sub=_permission_set_from_claim(claim.get("sub")),
    )


def issue_token(scope: NatsScope) -> tuple[str, datetime]:
    now = datetime.now(tz=UTC)
    expires_at = now + timedelta(seconds=settings.NATS_JWT_TTL_SECONDS)
    payload = {
        "sub": settings.NATS_JWT_SUBJECT,
        "iss": settings.NATS_JWT_ISSUER,
        "aud": settings.NATS_JWT_AUDIENCE,
        "iat": now,
        "exp": expires_at,
        "jti": str(uuid.uuid4()),
        "nats": scope_to_claim(scope),
    }
    encoded = jwt.encode(
        payload,
        settings.NATS_JWT_SIGNING_SECRET,
        algorithm=ALGORITHM,
    )
    return encoded, expires_at


def decode_token(encoded: str) -> NatsScope:
    payload = jwt.decode(
        encoded,
        settings.NATS_JWT_SIGNING_SECRET,
        algorithms=[ALGORITHM],
        audience=settings.NATS_JWT_AUDIENCE,
        issuer=settings.NATS_JWT_ISSUER,
        options={"require": list(REQUIRED_CLAIMS)},
    )
    return scope_from_claim(payload["nats"])
