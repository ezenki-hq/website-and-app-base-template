from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET
import jwt

from nats_auth.config import scope_from_settings
from nats_auth.tokens import decode_token, issue_token, scope_to_claim


def _invalid_credentials() -> JsonResponse:
    return JsonResponse({"error": "invalid credentials"}, status=401)


def _credential_from_request(request: HttpRequest) -> str:
    authorization = request.headers.get("Authorization")
    cookie_token = request.COOKIES.get("auth")
    header_token = None

    if authorization is not None:
        parts = authorization.split(" ")
        if len(parts) != 2 or parts[0] != "Bearer" or not parts[1]:
            raise jwt.InvalidTokenError("malformed authorization header")
        header_token = parts[1]

    if (
        header_token is not None
        and cookie_token is not None
        and header_token != cookie_token
    ):
        raise jwt.InvalidTokenError("conflicting credentials")

    encoded = header_token if header_token is not None else cookie_token
    if not encoded:
        raise jwt.InvalidTokenError("missing credentials")
    return encoded


@require_GET
def token(_request: HttpRequest) -> JsonResponse:
    try:
        encoded, expires_at = issue_token(scope_from_settings())
    except (ImproperlyConfigured, jwt.PyJWTError):
        return _invalid_credentials()

    return JsonResponse(
        {
            "token": encoded,
            "token_type": "Bearer",
            "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
        }
    )


@require_GET
def authorize(request: HttpRequest) -> JsonResponse:
    try:
        scope = decode_token(_credential_from_request(request))
    except (ImproperlyConfigured, jwt.PyJWTError):
        return _invalid_credentials()

    return JsonResponse(scope_to_claim(scope))
