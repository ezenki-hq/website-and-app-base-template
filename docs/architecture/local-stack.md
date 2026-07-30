# Local stack architecture

This document describes the checked-in development topology. It is not a
production deployment design. Start with the root [operator guide](../../README.md)
and use [NATS authentication](../integrations/nats-authentication.md) for the
credential flow.

## Topology

```text
Browser
  |
  | http://localhost:8081 or http://app.localhost:8081
  v
Nginx :80
  |---------------- Django/Gunicorn :8000 -------- PostgreSQL :5432
  |                         ^
  |                         | GET /api/nats/authorize/
  |                         |
  |---------------- React/Vite :5173
  |                 or Flutter Web :8080
  |
  `---------------- NATS WebSocket :8080

Native or diagnostic client ---------------------- NATS :4222
                                                       |
                                                       | auth callout
                                                       v
                                              Redirector (no listener)
                                                       |
                                                       `---- Django :8000
```

All service names and internal ports are addresses on the Compose network.
Only explicit `ports` mappings are reachable from the development host.

## Two-host routing

Nginx listens once and selects a fixed local server block from the HTTP `Host`
header.

| Host | Request path | Internal destination |
| --- | --- | --- |
| `localhost` | `/nats/` | `http://nats:8080` with WebSocket upgrade |
| `localhost` | every other path | `http://backend:8000` |
| `app.localhost` | exactly `/health/` | `http://backend:8000` |
| `app.localhost` | `/api/*` | `http://backend:8000` |
| `app.localhost` | `/nats/` | `http://nats:8080` with WebSocket upgrade |
| `app.localhost` | every other path, default | `http://web:5173` for React |
| `app.localhost` | every other path, Flutter override | `http://web:8080` for Flutter Web |

The public URLs include the host-mapped port:
`http://localhost:8081` and `http://app.localhost:8081`. Nginx forwards the
original host and standard client/protocol headers to HTTP upstreams. The NATS
locations use HTTP/1.1 upgrade headers, disable proxy buffering, and set
24-hour read and send timeouts for long-lived connections.

## Ports

| Component | Container port | Published host port | Purpose |
| --- | ---: | ---: | --- |
| PostgreSQL | `5432` | none | Django database |
| Django/Gunicorn | `8000` | none | Website, health, admin, and API |
| React/Vite | `5173` | none | Default application frontend |
| Flutter Web override | `8080` | none | Replacement application frontend |
| NATS native listener | `4222` | `4222` | Native/backend/diagnostic NATS clients |
| NATS WebSocket listener | `8080` | none | Browser NATS, reached through Nginx |
| NATS monitoring | `8222` | `8222` | Development monitoring and health |
| Nginx | `80` | `8081` | Public development HTTP and WebSocket entry |
| NATS auth redirector | none | none | Outbound NATS and HTTP client only |

The Compose-only frontend ports both use service name `web`; the Flutter
override replaces the React image, health check, and upstream selection.

## Native and WebSocket NATS clients

Native NATS clients connect to `nats://localhost:4222` from the development
host or `nats://nats:4222` from another Compose service. This path is suitable
for backend code, native Flutter code when the device can reach the published
host, and diagnostic clients.

Browser clients cannot use the native NATS protocol. They connect through the
Nginx route, normally `ws://app.localhost:8081/nats/`. Nginx upgrades the
connection and proxies it to `nats:8080`. Both listeners use the same NATS
auth-callout policy and require the client token.

All checked-in NATS transport is unencrypted development traffic. A production
deployment must provide TLS and separate network exposure rules.

## Service readiness and persistence

| Service | Readiness signal |
| --- | --- |
| PostgreSQL | `pg_isready` |
| Django | database-backed `GET /health/` |
| React/Vite | successful local HTTP response |
| Flutter Web | successful local HTTP response |
| NATS | monitoring `GET /healthz` |
| Nginx | both a website health route and application frontend response |
| Redirector | none; no health endpoint exists |

The backend entrypoint applies migrations before starting Gunicorn. PostgreSQL
data lives in the named `postgres-data` volume and survives normal Compose
shutdown. The redirector starts only after Django and NATS report healthy and
uses `restart: unless-stopped` because an initial NATS connection failure exits
the process.

## Trust boundaries

### Browser and native client boundary

Clients are untrusted. The local anonymous issuer returns a development token,
but it does not accept an account, publish subjects, or subscribe subjects from
the request. The signed JWT is the client's only NATS credential. A derived
project must authenticate identity before issuance and construct permissions
on the server.

### Public HTTP boundary

Only Nginx's port `8081`, NATS native port `4222`, and NATS monitoring port
`8222` are published. Django, PostgreSQL, both frontend development servers,
NATS WebSocket port `8080`, and the redirector stay on the Compose network.
Published monitoring and native NATS access are local-development choices, not
production exposure guidance.

### Django policy boundary

Django owns the HS256 client-JWT secret and is the only component that issues
or validates that JWT. The JWT contains a server-constructed NATS scope.
The Compose file explicitly supplies the backend only with its Django/Wagtail,
PostgreSQL, client-JWT, and NATS policy settings. Account signer material,
redirect auth credentials, and React runtime values are not present in the
backend process environment. Optional Wagtail values use the same defaults as
Django settings and remain overridable through Compose interpolation.

### NATS and redirector boundary

NATS trusts the account signer public key. The redirector is the component
configured to use the matching private seed and sign authorization-response
JWTs; the backend does not receive that seed. The redirector connects as an
exempt user in the `AUTH` account; application clients are authorized into the
`APP` account. NATS uses the `SYS`
system account for the auth-callout request path.

The redirector forwards the opaque client token to Django and turns Django's
response into the signed NATS authorization response. It does not make local
authorization policy decisions. Its exact observed behavior is maintained in
the [authoritative redirect contract](../integrations/nats-auth-redirect.md).

## Credential exposure and use

| Credential or value | Django | NATS | Redirector | Client |
| --- | --- | --- | --- | --- |
| `DJANGO_SECRET_KEY` | owns/uses | no access | no access | no access |
| `NATS_JWT_SIGNING_SECRET` | owns/uses | no access | no access | no access |
| Account signer seed | no access | no access | uses | no access |
| Account signer public key | no access | trusts/uses | derives from seed | no access |
| Redirect auth password | no access | validates | uses | no access |
| Issued client JWT | issues/validates | carries in auth callout | forwards | owns/uses |
| Server-built NATS permissions | constructs/signs in JWT | enforces | copies/signs response | cannot select |

Generated credentials live in ignored `.env`, which should remain local and
must not be printed, committed, or reused in production. Compose interpolates
that file and explicitly injects only the keys each service consumes. Derived
deployments should preserve that separation while replacing local environment
injection with appropriate secret storage and mounts.

## Configuration ownership

- `infra/compose.yaml` defines the default React topology.
- `infra/compose.flutter-web.yaml` narrowly replaces the application frontend.
- `infra/nginx/conf.d/default.conf` defines default two-host routing.
- `infra/nginx/conf.d/flutter-web.conf` preserves routes while changing the
  application upstream.
- `infra/nats/nats.conf` defines listeners, accounts, the exempt auth user, and
  auth callout.
- `.env.example` inventories the keys written by the local generator; the
  generator creates `.env`. Optional application settings may exist outside
  that generated-key inventory.

Production hostnames, TLS, deployment orchestration, credentials, network
policy, and observability belong in separate configuration. Do not reuse the
development Nginx files as a parameterized production configuration.
