from datetime import UTC, datetime, timedelta
import uuid
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase, override_settings
import jwt

from nats_auth.config import NatsScope, PermissionSet
from nats_auth.tokens import decode_token, issue_token


FROZEN_NOW = datetime(2020, 1, 2, 3, 4, 5, tzinfo=UTC)
VALID_EXPIRY = datetime(2099, 1, 2, 3, 4, 5, tzinfo=UTC)
SCOPE = NatsScope(
    account="APP",
    pub=PermissionSet(allow=("app.>",), deny=()),
    sub=PermissionSet(allow=("app.>",), deny=()),
)
SCOPE_CLAIM = {
    "account": "APP",
    "pub": {"allow": ["app.>"], "deny": []},
    "sub": {"allow": ["app.>"], "deny": []},
}


def encoded_payload(**updates):
    payload = {
        "sub": settings.NATS_JWT_SUBJECT,
        "iss": settings.NATS_JWT_ISSUER,
        "aud": settings.NATS_JWT_AUDIENCE,
        "iat": FROZEN_NOW,
        "exp": VALID_EXPIRY,
        "jti": "1e51f358-38e9-4f45-8590-2a08a582fc73",
        "nats": SCOPE_CLAIM,
    }
    payload.update(updates)
    return jwt.encode(
        payload,
        settings.NATS_JWT_SIGNING_SECRET,
        algorithm="HS256",
    )


class IssueTokenTests(SimpleTestCase):
    @override_settings(
        NATS_JWT_TTL_SECONDS=86_400,
        NATS_JWT_SUBJECT="development-user",
        NATS_JWT_ISSUER="website-app-template",
        NATS_JWT_AUDIENCE="nats",
    )
    @mock.patch("nats_auth.tokens.datetime", wraps=datetime)
    def test_issues_hs256_token_with_required_claims_and_default_lifetime(
        self,
        mocked_datetime,
    ):
        mocked_datetime.now.return_value = FROZEN_NOW

        encoded, expires_at = issue_token(SCOPE)

        header = jwt.get_unverified_header(encoded)
        payload = jwt.decode(
            encoded,
            settings.NATS_JWT_SIGNING_SECRET,
            algorithms=["HS256"],
            audience=settings.NATS_JWT_AUDIENCE,
            issuer=settings.NATS_JWT_ISSUER,
            options={"verify_exp": False},
        )
        self.assertEqual(header["alg"], "HS256")
        self.assertEqual(payload["sub"], "development-user")
        self.assertEqual(payload["iss"], "website-app-template")
        self.assertEqual(payload["aud"], "nats")
        self.assertEqual(payload["iat"], int(FROZEN_NOW.timestamp()))
        self.assertEqual(
            payload["exp"],
            int((FROZEN_NOW + timedelta(seconds=86_400)).timestamp()),
        )
        uuid.UUID(payload["jti"])
        self.assertEqual(payload["nats"], SCOPE_CLAIM)
        self.assertEqual(
            expires_at,
            FROZEN_NOW + timedelta(seconds=86_400),
        )

    @override_settings(NATS_JWT_TTL_SECONDS=45)
    @mock.patch("nats_auth.tokens.datetime", wraps=datetime)
    def test_uses_configured_lifetime(self, mocked_datetime):
        mocked_datetime.now.return_value = FROZEN_NOW

        _, expires_at = issue_token(SCOPE)

        self.assertEqual(expires_at, FROZEN_NOW + timedelta(seconds=45))


class DecodeTokenTests(SimpleTestCase):
    def test_returns_typed_scope_for_valid_token(self):
        self.assertEqual(decode_token(encoded_payload()), SCOPE)

    @override_settings(
        NATS_JWT_SIGNING_SECRET="different-signing-secret-at-least-32-bytes"
    )
    def test_rejects_wrong_signature(self):
        encoded = jwt.encode(
            {
                "sub": "development-user",
                "iss": "website-app-template",
                "aud": "nats",
                "iat": FROZEN_NOW,
                "exp": VALID_EXPIRY,
                "jti": "1e51f358-38e9-4f45-8590-2a08a582fc73",
                "nats": SCOPE_CLAIM,
            },
            "original-signing-secret-at-least-32-bytes",
            algorithm="HS256",
        )

        with self.assertRaises(jwt.InvalidSignatureError):
            decode_token(encoded)

    def test_rejects_expired_token(self):
        encoded = encoded_payload(
            iat=datetime(1999, 1, 1, tzinfo=UTC),
            exp=datetime(2000, 1, 1, tzinfo=UTC),
        )

        with self.assertRaises(jwt.ExpiredSignatureError):
            decode_token(encoded)

    def test_rejects_wrong_issuer(self):
        with self.assertRaises(jwt.InvalidIssuerError):
            decode_token(encoded_payload(iss="another-issuer"))

    def test_rejects_wrong_audience(self):
        with self.assertRaises(jwt.InvalidAudienceError):
            decode_token(encoded_payload(aud="another-audience"))

    def test_rejects_each_missing_required_claim(self):
        required_claims = ("sub", "iss", "aud", "iat", "exp", "jti", "nats")

        for claim in required_claims:
            with self.subTest(claim=claim):
                payload = {
                    "sub": settings.NATS_JWT_SUBJECT,
                    "iss": settings.NATS_JWT_ISSUER,
                    "aud": settings.NATS_JWT_AUDIENCE,
                    "iat": FROZEN_NOW,
                    "exp": VALID_EXPIRY,
                    "jti": "1e51f358-38e9-4f45-8590-2a08a582fc73",
                    "nats": SCOPE_CLAIM,
                }
                del payload[claim]
                encoded = jwt.encode(
                    payload,
                    settings.NATS_JWT_SIGNING_SECRET,
                    algorithm="HS256",
                )

                with self.assertRaises(jwt.MissingRequiredClaimError):
                    decode_token(encoded)

    def test_rejects_malformed_scope(self):
        malformed_scope = {
            "account": "APP",
            "pub": {"allow": ["app.>", 7], "deny": []},
            "sub": {"allow": ["app.>"], "deny": []},
        }

        with self.assertRaises(jwt.InvalidTokenError):
            decode_token(encoded_payload(nats=malformed_scope))
