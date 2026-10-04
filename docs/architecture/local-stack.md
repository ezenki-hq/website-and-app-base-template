# Local stack architecture

This document describes the checked-in development topology. It is not a
production deployment design. See the [event WebSocket guide](../integrations/events-websocket.md)
for the token, origin, and MessagePack contracts.

## Topology

```text
Browser or native app
        |
        | HTTP and WebSocket through port 8081
        v
      Nginx
        |---------------- Wagtail static asset volume (read-only)
        |---------------- Django ASGI :8000 -------- PostgreSQL :5432
        |                           |
        |                           `---- NATS :4222 (internal only)
        |                                      ^
        |                                      |
        |---------------- React :5173          |
        |          or Flutter Web :8080        |
                                               |
                                      NATS event publisher
                                      (internal Compose network)
```

Compose service names and internal ports are reachable only on the Compose
network. Only Nginx publishes a host port.

## Two-host routing

| Host | Request path | Internal destination |
| --- | --- | --- |
| `localhost` | `/static/*` | Nginx static asset volume |
| `localhost` | `/ws/events/*` | Django ASGI, with access logging disabled |
| `localhost` | every other path | Django ASGI HTTP |
| `app.localhost` | `/health/` and `/api/*` | Django ASGI HTTP |
| `app.localhost` | `/ws/events/*` | Django ASGI WebSocket, with access logging disabled |
| `app.localhost` | every other path | React by default; Flutter Web with its Compose override |

The host URLs use port `8081`. Nginx forwards WebSocket upgrade headers and
uses a long read timeout. Nginx access logs are disabled on the JWT-bearing
event route. Configure any other proxy, CDN, tracing, or error logging layer
to redact that path too.

## Ports and trust boundaries

| Component | Container port | Published host port | Use |
| --- | ---: | ---: | --- |
| PostgreSQL | `5432` | none | Django database |
| Django ASGI | `8000` | none | Website, health, admin, and event WebSocket |
| React | `5173` | none | Default application frontend |
| Flutter Web override | `8080` | none | Replacement application frontend |
| NATS native listener | `4222` | none | Django and other internal publishers |
| NATS monitoring | `8222` | none | Internal health check |
| Nginx | `80` | `8081` | Browser-facing development entry point |

Django uses one authenticated NATS connection per accepted WebSocket and
subscribes only to the subjects in its validated event token. Compose gives
the broker and backend the same NATS username/password. The NATS user is
limited to publish and subscribe subjects under `app.>` by default. NATS has
no WebSocket listener in this stack.

Only Django receives `EVENTS_JWT_SIGNING_SECRET`. React and Flutter receive an
event WebSocket URL but no NATS address or credential. The token issuer is a
Python helper for derived server code; this template does not add a public
issuer API or application login flow.

## Lifecycle and persistence

Django's ASGI application routes HTTP requests through the existing Django
application and WebSockets through Channels. The WebSocket consumer validates
the token before opening NATS, accepts only after all subscriptions are
established, closes at token expiry, and releases subscriptions and its NATS
connection on disconnect or failure.

PostgreSQL data lives in the named `postgres-data` volume. Django applies
migrations and collects static assets before serving. Nginx mounts static
assets read-only. The NATS service exposes internal health on port `8222` and
has no host port mapping.

## Configuration ownership

- `infra/compose.yaml` defines the default React topology and private NATS.
- `infra/compose.flutter-web.yaml` replaces the application frontend.
- `infra/nginx/conf.d/default.conf` defines the React two-host routes.
- `infra/nginx/conf.d/flutter-web.conf` keeps the same routes for Flutter Web.
- `infra/nats/nats.conf` defines internal NATS authentication and permissions.
- `.env.example` documents the local values; the generator creates a private `.env`.

Production hostnames, TLS, credential storage, network policy, observability,
and scaling belong in deployment-specific configuration. Do not expose the
local NATS listeners or use local Nginx files as production configuration.
