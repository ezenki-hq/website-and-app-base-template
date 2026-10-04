from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import jwt
from django.test import SimpleTestCase, override_settings

from events.tokens import decode_event_token, issue_event_token


@override_settings(
    EVENTS_JWT_SIGNING_SECRET="test-events-secret-with-sufficient-entropy",
    EVENTS_JWT_TTL_SECONDS=3600,
)
class EventTokenTests(SimpleTestCase):
    def test_issues_and_decodes_scoped_token(self):
        token = issue_event_token("user-1", ["app.one", "app.>"])
        claims = decode_event_token(token)
        raw = jwt.decode(
            token,
            "test-events-secret-with-sufficient-entropy",
            algorithms=["HS256"],
            audience="events-websocket",
            issuer="website-app-template",
        )
        self.assertEqual(claims.identity, "user-1")
        self.assertEqual(claims.events, ("app.one", "app.>"))
        self.assertEqual(set(raw), {"iss", "aud", "sub", "iat", "exp", "jti", "events"})
        self.assertEqual(raw["exp"] - raw["iat"], 3600)
        self.assertTrue(raw["jti"])
        self.assertIsInstance(claims.expires_at, datetime)

    def test_rejects_wrong_audience_and_invalid_subjects(self):
        now = datetime.now(timezone.utc)
        base = {
            "iss": "website-app-template",
            "aud": "wrong-audience",
            "sub": "user-1",
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "jti": "token-id",
            "events": ["app.one"],
        }
        malformed = [
            base,
            {**base, "aud": "events-websocket", "events": "app.one"},
            {**base, "aud": ["events-websocket", "other"], "events": ["app.one"]},
            {**base, "aud": "events-websocket", "events": ["app.>.one"]},
            {key: value for key, value in base.items() if key != "sub"},
            {**base, "aud": "events-websocket", "sub": ""},
            {**base, "aud": "events-websocket", "sub": None},
            {key: value for key, value in base.items() if key != "jti"},
            {**base, "aud": "events-websocket", "jti": ""},
            {**base, "aud": "events-websocket", "exp": now - timedelta(seconds=1)},
        ]
        for claims in malformed:
            with self.subTest(claims=claims):
                token = jwt.encode(
                    claims,
                    "test-events-secret-with-sufficient-entropy",
                    algorithm="HS256",
                )
                with self.assertRaises(jwt.InvalidTokenError):
                    decode_event_token(token)
