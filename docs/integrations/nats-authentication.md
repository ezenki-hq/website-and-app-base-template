# NATS authentication

This document defines how the local template issues a client JWT, validates
its NATS scope, and integrates Django with NATS auth callout. The redirect
image is used unchanged. Its source-derived behavior and limitations are
authoritative in the
[redirect integration contract](nats-auth-redirect.md); this document applies
that contract to the local stack.

For routes, ports, and network boundaries, see the
[local stack architecture](../architecture/local-stack.md).

> The token issuer is anonymous and development-only. It is proof that the
> authentication plumbing works, not a production identity system.

## Local flow

1. A client requests `GET /api/nats/token/`.
2. Django constructs the account and permissions exclusively from server
   settings, creates an HS256 JWT, and returns it as a Bearer token.
3. The client supplies that JWT as the NATS connection token to either the
   native listener or WebSocket listener.
4. NATS creates an authorization-request JWT on `$SYS.REQ.USER.AUTH`.
5. The redirector receives the request as the exempt `AUTH` user and forwards
   the client token with `GET http://backend:8000/api/nats/authorize/` and an
   `Authorization: Bearer <client-token>` header.
6. Django validates the client JWT and returns the exact account/permission
   object.
7. The redirector signs an authorization-response JWT with the NATS account
   signer seed.
8. NATS verifies that response using the configured signer public key and
   accepts or rejects the connection.

The client JWT signing secret and NATS account signer seed are different
credentials with different consumers: Django uses the former and the
redirector uses the latter. In the checked-in Compose stack, this use boundary
is not an environment-exposure boundary because the backend receives the
entire generated `.env`.

## Development token endpoint

```http
GET /api/nats/token/ HTTP/1.1
Host: app.localhost
```

The endpoint takes no account, subject, or permission input. A success has this
shape:

```json
{
  "token": "<signed-jwt>",
  "token_type": "Bearer",
  "expires_at": "<UTC ISO-8601 timestamp>"
}
```

The JWT uses `HS256`. These standard claims are required and validated:

| Claim | Local source |
| --- | --- |
| `sub` | `NATS_JWT_SUBJECT` |
| `iss` | `NATS_JWT_ISSUER` |
| `aud` | `NATS_JWT_AUDIENCE` |
| `iat` | issuance time |
| `exp` | issuance time plus `NATS_JWT_TTL_SECONDS` |
| `jti` | newly generated UUID |

The exact default namespaced scope is:

```json
{
  "nats": {
    "account": "APP",
    "pub": {
      "allow": ["app.>"],
      "deny": []
    },
    "sub": {
      "allow": ["app.>"],
      "deny": []
    }
  }
}
```

`NATS_ACCOUNT` and the four permission-list settings change this scope.
Permission values are JSON arrays encoded in environment strings. Every item
must be a non-empty string. Empty allow lists grant no subjects; empty deny
lists are valid.

The template deliberately grants no system subjects and refuses caller-
selected permissions. In a derived project, replace the policy construction in
`backend/nats_auth/config.py` and the development issuer in
`backend/nats_auth/tokens.py` and `backend/nats_auth/views.py`. Authenticate the
caller and map its server-side identity to policy. Never add request parameters
that let a caller choose `account`, `pub`, or `sub`.

## Authorization endpoint

The redirector always uses the Bearer form:

```http
GET /api/nats/authorize/ HTTP/1.1
Host: backend
Authorization: Bearer <client-jwt>
```

The endpoint also supports a direct client request with a cookie named `auth`.
Credential selection is exact:

| Bearer header | `auth` cookie | Result |
| --- | --- | --- |
| valid token | absent | validate header token |
| absent | valid token | validate cookie token |
| token A | token A | validate the shared token |
| token A | different token B | reject with HTTP `401` |
| malformed scheme, empty, or both absent | any non-resolving case | reject with HTTP `401` |

The `Bearer` scheme is case-sensitive in the current view. Django validates the
HS256 algorithm, signature, expiration, issuer, audience, all required claims,
and the complete `nats` scope structure.

Valid credentials produce this exact redirect response:

```json
{
  "account": "APP",
  "pub": {
    "allow": ["app.>"],
    "deny": []
  },
  "sub": {
    "allow": ["app.>"],
    "deny": []
  }
}
```

The values reflect the signed JWT scope, but the object always contains
`account`, `pub.allow`, `pub.deny`, `sub.allow`, and `sub.deny`. Invalid,
missing, expired, conflicting, or malformed credentials produce:

```json
{
  "error": "invalid credentials"
}
```

with HTTP `401`. The response does not echo the token or validation detail.
Because `401` is greater than `300`, the redirector converts it to a signed
NATS denial.

## NATS and redirector configuration

The local NATS configuration provides:

- native clients on `nats:4222`;
- WebSocket clients on `nats:8080`, routed publicly through `/nats/`;
- monitoring on `nats:8222`;
- `AUTH`, `APP`, and `SYS` accounts;
- `system_account: SYS`;
- the auth callout in `AUTH`;
- the generated account signer public key as `issuer`; and
- the redirector user in `auth_users`, exempting it from recursive callout.

The redirector service is configured with exactly:

| Environment key | Local value or ownership |
| --- | --- |
| `AUTH_SERVER` | `http://backend:8000/api/nats/authorize/` |
| `NATS_URL` | Native NATS URL containing the exempt auth-user credentials |
| `ACCOUNT_SIGNER_SEED` | Ignored local private account signer seed |

The public key in NATS must match the private seed in the redirector. The
redirect auth username/password must also match the user configured in NATS.
Changing only one side causes authorization startup or response verification
to fail.

Separately, `backend.env_file` loads the complete generated `.env` into the
backend process. The backend therefore also receives
`NATS_ACCOUNT_SIGNER_SEED`, `NATS_ACCOUNT_SIGNER_PUBLIC_KEY`,
`NATS_AUTH_USER`, and `NATS_AUTH_PASSWORD`, although current Django settings
and application code do not read or use them. The local topology documents
credential consumers; it does not provide least-privilege environment
isolation.

## Native and WebSocket use

From the development host, native clients use `nats://localhost:4222`. Other
Compose services use `nats://nats:4222`. Browser clients use the Nginx route,
normally `ws://app.localhost:8081/nats/`. All clients pass the same development
JWT as the NATS connection token and receive the same permissions.

The checked-in frontend libraries are only typed boundaries:

- `web/src/lib/auth.ts` and `web/src/lib/nats.ts`;
- `app/lib/integrations/auth.dart` and `app/lib/integrations/nats.dart`.

They do not currently request a token, connect to NATS, or include a NATS
client dependency. Derived projects choose a client and implement these
boundaries.

## Redirector limitations

The following are observed constraints of the pinned redirector, not behavior
implemented by this template:

- It has no HTTP server, exposed port, or health endpoint.
- It opens outbound connections to NATS and the configured authorization API.
- An initial NATS connection failure exits the process. Local Compose waits on
  NATS health and uses `restart: unless-stopped` to compensate.
- It uses the default HTTP client without an explicit request timeout. An
  externally detected stuck process cannot cancel an individual blocked
  request.
- It sends one HTTP `GET` with no body for each decoded auth request.
- It treats status codes greater than `300` as invalid-token denials, but
  attempts to decode status `300` as an authorization response. Do not design
  the authorization API around redirects.
- Transport, body-read, and JSON-decode failures become signed denials.
- It does not locally validate returned account names or permission subjects.
  Django must return trustworthy, validated policy.
- Behavior for an account not present in the NATS account model is not covered
  by the redirector contract tests.
- It does not explicitly validate its signer seed or NATS URL before trying to
  use them.
- It queue-subscribes as `auth-workers`; replicas connected to the same NATS
  deployment share auth requests through that queue group.

Do not invent a liveness/readiness endpoint for this service or treat process
liveness as proof that authorization requests complete.

## Security and production replacement

Local traffic is unencrypted, monitoring and native NATS ports are published,
and anyone able to reach the token endpoint can obtain the default `app.>`
scope. These choices are limited to development.

A production project must provide authenticated issuance, server-owned
authorization policy, least-privilege per-service secret injection, protected
secret storage, credential rotation, TLS for HTTP/NATS/WebSocket traffic,
deliberate port exposure, and independent deployment/readiness configuration.
It must use separate Nginx and deployment files rather than promoting the local
server blocks. Derived local configurations should also audit and narrow the
backend's broad `env_file` when credential isolation matters.

When changing the integration, keep these trust properties:

- clients never receive `NATS_JWT_SIGNING_SECRET`, the signer seed, or redirect
  auth credentials;
- Django uses only the client JWT secret in the current implementation, while
  its local Compose process environment also contains the signer and redirect
  credentials;
- NATS receives only the signer public key, not the seed;
- the redirector's exempt credentials are not application-client credentials;
- account and permissions come from validated server policy; and
- logs and smoke output do not expose JWTs or secret material.
