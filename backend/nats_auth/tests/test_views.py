from datetime import UTC, datetime

from django.conf import settings
from django.test import TestCase
import jwt

from nats_auth.config import NatsScope, PermissionSet
from nats_auth.tokens import decode_token, issue_token


SCOPE = NatsScope(
    account="APP",
    pub=PermissionSet(allow=("app.>",), deny=()),
    sub=PermissionSet(allow=("app.>",), deny=()),
)
SCOPE_RESPONSE = {
    "account": "APP",
    "pub": {"allow": ["app.>"], "deny": []},
    "sub": {"allow": ["app.>"], "deny": []},
}


class TokenViewTests(TestCase):
    def test_returns_exact_contract_with_server_configured_permissions(self):
        response = self.client.get(
            "/api/nats/token/",
            {
                "account": "OTHER",
                "pub": "evil.>",
                "NATS_ACCOUNT": "OTHER",
                "NATS_PUBLISH_ALLOW": '["evil.>"]',
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(
            set(body),
            {"token", "token_type", "expires_at"},
        )
        self.assertIsInstance(body["token"], str)
        self.assertTrue(body["token"])
        self.assertEqual(body["token_type"], "Bearer")
        self.assertTrue(body["expires_at"].endswith("Z"))
        self.assertEqual(decode_token(body["token"]), SCOPE)


class AuthorizeViewTests(TestCase):
    def setUp(self):
        self.encoded, _ = issue_token(SCOPE)

    def assert_invalid_credentials(self, response):
        self.assertEqual(response.status_code, 401)
        self.assertJSONEqual(
            response.content,
            {"error": "invalid credentials"},
        )
        self.assertNotIn("token", response.content.decode())
        self.assertNotIn(self.encoded, response.content.decode())

    def test_accepts_valid_bearer_and_returns_exact_scope(self):
        response = self.client.get(
            "/api/nats/authorize/",
            HTTP_AUTHORIZATION=f"Bearer {self.encoded}",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), SCOPE_RESPONSE)

    def test_accepts_valid_auth_cookie(self):
        self.client.cookies["auth"] = self.encoded

        response = self.client.get("/api/nats/authorize/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), SCOPE_RESPONSE)

    def test_accepts_equal_bearer_and_cookie(self):
        self.client.cookies["auth"] = self.encoded

        response = self.client.get(
            "/api/nats/authorize/",
            HTTP_AUTHORIZATION=f"Bearer {self.encoded}",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), SCOPE_RESPONSE)

    def test_rejects_conflicting_bearer_and_cookie(self):
        self.client.cookies["auth"] = "different-token"

        response = self.client.get(
            "/api/nats/authorize/",
            HTTP_AUTHORIZATION=f"Bearer {self.encoded}",
        )

        self.assert_invalid_credentials(response)

    def test_rejects_missing_credentials(self):
        response = self.client.get("/api/nats/authorize/")

        self.assert_invalid_credentials(response)

    def test_rejects_malformed_authorization_scheme(self):
        response = self.client.get(
            "/api/nats/authorize/",
            HTTP_AUTHORIZATION=f"Basic {self.encoded}",
        )

        self.assert_invalid_credentials(response)

    def test_rejects_invalid_jwt(self):
        response = self.client.get(
            "/api/nats/authorize/",
            HTTP_AUTHORIZATION="Bearer not-a-jwt",
        )

        self.assert_invalid_credentials(response)

    def test_rejects_expired_jwt(self):
        expired = jwt.encode(
            {
                "sub": settings.NATS_JWT_SUBJECT,
                "iss": settings.NATS_JWT_ISSUER,
                "aud": settings.NATS_JWT_AUDIENCE,
                "iat": datetime(1999, 1, 1, tzinfo=UTC),
                "exp": datetime(2000, 1, 1, tzinfo=UTC),
                "jti": "1e51f358-38e9-4f45-8590-2a08a582fc73",
                "nats": SCOPE_RESPONSE,
            },
            settings.NATS_JWT_SIGNING_SECRET,
            algorithm="HS256",
        )

        response = self.client.get(
            "/api/nats/authorize/",
            HTTP_AUTHORIZATION=f"Bearer {expired}",
        )

        self.assert_invalid_credentials(response)
