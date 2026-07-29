import json
from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


@dataclass(frozen=True)
class PermissionSet:
    allow: tuple[str, ...]
    deny: tuple[str, ...]


@dataclass(frozen=True)
class NatsScope:
    account: str
    pub: PermissionSet
    sub: PermissionSet


def parse_subjects(raw: str, setting_name: str) -> tuple[str, ...]:
    try:
        subjects = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as error:
        raise ImproperlyConfigured(
            f"{setting_name} must be a JSON array of non-empty strings"
        ) from error

    if not isinstance(subjects, list) or any(
        not isinstance(subject, str) or not subject for subject in subjects
    ):
        raise ImproperlyConfigured(
            f"{setting_name} must be a JSON array of non-empty strings"
        )

    return tuple(subjects)


def scope_from_settings() -> NatsScope:
    account = settings.NATS_ACCOUNT
    if not isinstance(account, str) or not account:
        raise ImproperlyConfigured("NATS_ACCOUNT must be a non-empty string")

    return NatsScope(
        account=account,
        pub=PermissionSet(
            allow=parse_subjects(
                settings.NATS_PUBLISH_ALLOW,
                "NATS_PUBLISH_ALLOW",
            ),
            deny=parse_subjects(
                settings.NATS_PUBLISH_DENY,
                "NATS_PUBLISH_DENY",
            ),
        ),
        sub=PermissionSet(
            allow=parse_subjects(
                settings.NATS_SUBSCRIBE_ALLOW,
                "NATS_SUBSCRIBE_ALLOW",
            ),
            deny=parse_subjects(
                settings.NATS_SUBSCRIBE_DENY,
                "NATS_SUBSCRIBE_DENY",
            ),
        ),
    )
