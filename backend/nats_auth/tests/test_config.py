import os
import subprocess
import sys

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from nats_auth.config import (
    NatsScope,
    PermissionSet,
    parse_subjects,
    scope_from_settings,
)


class ParseSubjectsTests(SimpleTestCase):
    def test_parses_valid_json_array(self):
        self.assertEqual(
            parse_subjects('["app.>", "requests"]', "NATS_PUBLISH_ALLOW"),
            ("app.>", "requests"),
        )

    def test_accepts_empty_json_array(self):
        self.assertEqual(parse_subjects("[]", "NATS_PUBLISH_DENY"), ())

    def test_rejects_malformed_json(self):
        with self.assertRaisesRegex(ImproperlyConfigured, "NATS_PUBLISH_ALLOW"):
            parse_subjects("[", "NATS_PUBLISH_ALLOW")

    def test_rejects_non_string_members(self):
        with self.assertRaisesRegex(ImproperlyConfigured, "NATS_SUBSCRIBE_ALLOW"):
            parse_subjects(
                '["app.>", 7]',
                "NATS_SUBSCRIBE_ALLOW",
            )

    def test_rejects_empty_string_members(self):
        with self.assertRaisesRegex(ImproperlyConfigured, "NATS_SUBSCRIBE_DENY"):
            parse_subjects('[""]', "NATS_SUBSCRIBE_DENY")

    def test_rejects_non_array_json(self):
        with self.assertRaisesRegex(ImproperlyConfigured, "NATS_PUBLISH_DENY"):
            parse_subjects('"app.>"', "NATS_PUBLISH_DENY")


class ScopeFromSettingsTests(SimpleTestCase):
    def test_permission_settings_have_safe_defaults(self):
        environment = os.environ.copy()
        for setting_name in (
            "NATS_JWT_TTL_SECONDS",
            "NATS_ACCOUNT",
            "NATS_PUBLISH_ALLOW",
            "NATS_PUBLISH_DENY",
            "NATS_SUBSCRIBE_ALLOW",
            "NATS_SUBSCRIBE_DENY",
        ):
            environment.pop(setting_name, None)
        environment["DJANGO_SETTINGS_MODULE"] = "config.settings"

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; sys.argv = ['manage.py', 'test']; "
                    "from django.conf import settings; "
                    "print(settings.NATS_JWT_TTL_SECONDS); "
                    "print(settings.NATS_ACCOUNT); "
                    "print(settings.NATS_PUBLISH_ALLOW); "
                    "print(settings.NATS_PUBLISH_DENY); "
                    "print(settings.NATS_SUBSCRIBE_ALLOW); "
                    "print(settings.NATS_SUBSCRIBE_DENY)"
                ),
            ],
            capture_output=True,
            env=environment,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines(),
            ["86400", "APP", '["app.>"]', "[]", '["app.>"]', "[]"],
        )

    @override_settings(
        NATS_ACCOUNT="CUSTOM",
        NATS_PUBLISH_ALLOW='["events.>"]',
        NATS_PUBLISH_DENY='["events.internal.>"]',
        NATS_SUBSCRIBE_ALLOW='["requests"]',
        NATS_SUBSCRIBE_DENY="[]",
    )
    def test_builds_immutable_scope_from_settings(self):
        self.assertEqual(
            scope_from_settings(),
            NatsScope(
                account="CUSTOM",
                pub=PermissionSet(
                    allow=("events.>",),
                    deny=("events.internal.>",),
                ),
                sub=PermissionSet(allow=("requests",), deny=()),
            ),
        )
