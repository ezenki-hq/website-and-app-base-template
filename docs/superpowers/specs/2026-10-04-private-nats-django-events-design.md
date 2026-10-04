# Private NATS Events Through Django WebSockets

**Date:** 2026-10-04
**Status:** Approved conversational design, pending written-spec review

## Purpose

Keep NATS as a private broker while making Django the only WebSocket endpoint
for application clients. A derived project can decide which NATS subjects a
client may receive, call a server-side JWT issuer with that decision, and give
the token to the client through its own authentication flow. This template
supplies the transport and authorization foundation without choosing an
application user model, event schema, or token-delivery API.

Success means a client with a valid token can connect to
`/ws/events/{jwt}`, receive subscribed NATS messages as MessagePack frames,
and lose access when the token expires or the socket closes. Invalid tokens
must create no NATS subscriptions. No NATS listener is published to the host
or proxied to clients.

## Scope

The change includes Django ASGI serving, an event WebSocket endpoint, JWT
issuing and validation helpers, an internal NATS connection, MessagePack
encoding, local Compose and Nginx changes, frontend integration boundaries,
tests, documentation, and a root `AGENTS.md`.

The change removes the public NATS JWT endpoints, NATS auth callout and
redirector, browser NATS proxy, and obsolete environment variables and
integration instructions. The old Superpowers design and plan remain as
historical records.

The template does not add an application login flow, a public JWT issuer
endpoint, a publisher API, project-specific event names or payload parsing,
JetStream, automatic frontend connections, reconnect behavior in the
frontends, or production deployment configuration.

## Architecture

The existing Django HTTP routes continue to run through Django's ASGI
application. A Channels WebSocket consumer handles `/ws/events/{jwt}`. The
backend container runs an ASGI-capable Gunicorn worker. Nginx forwards
WebSocket upgrades on that path to the backend for both the React and Flutter
Web layouts. React and Flutter mobile clients use the same endpoint at the
host reachable from their device.

NATS retains its internal native listener and monitoring endpoint for Compose
health checks. Compose publishes neither port, and NATS no longer starts its
WebSocket listener. A private NATS username and password shared only by the
broker and backend replace auth callout. Broker publish and subscribe
permissions default to `app.>`; a derived project can change that namespace
in the NATS configuration. NATS itself still enforces those permissions when
Django subscribes. The backend opens one NATS client connection per valid
incoming WebSocket and one subscription per subject in that socket's JWT.
This simple lifecycle avoids a separate channel layer or fan-out worker.

No NATS credential or direct NATS URL reaches React, Flutter, or the browser.
The HTTP health check stays focused on Django and its database; NATS is
contacted when an event socket connects.

## JWT Contract

`events.tokens.issue_event_token(identity, events)` is the server-side entry
point for other Django code. `identity` is a nonempty application-defined
string; it becomes the JWT `sub`. `events` is a nonempty sequence of distinct
NATS subscription subjects, including valid NATS wildcard patterns where
needed. The caller must authenticate the recipient and authorize every
requested subject before calling this function. The template never accepts
subject choices from a client request or offers a public issuance view.

The function uses a dedicated `EVENTS_JWT_SIGNING_SECRET` and fixed HS256
algorithm. Tokens contain `iss="website-app-template"`,
`aud="events-websocket"`, `sub`, `iat`, `exp`, `jti`, and `events` claims. The
default lifetime is 3,600 seconds, configurable through
`EVENTS_JWT_TTL_SECONDS`; derived projects may choose a shorter value.
Validation requires the signature, exact issuer and audience, all required
claims, a future expiry, a nonempty identity, and at most 32 valid, distinct
NATS subscription subjects. A valid subject has no whitespace or empty
tokens; `*` occupies one whole token, and `>` occupies only the final whole
token. Issuance and validation apply the same subject rules. Tokens signed
for the former direct NATS flow are invalid for this WebSocket flow.

The JWT is a bearer credential. It can be reused until expiration; one-time
use and revocation require project-specific state and are outside this
foundation. A connected socket closes when its JWT expires, even if NATS is
still connected.

## WebSocket and MessagePack Contract

For an incoming connection, Django checks the browser `Origin` when present,
validates the JWT, opens NATS with the backend credential, and subscribes to
each token subject. It accepts the WebSocket only when setup succeeds. A
missing, malformed, incorrectly signed, expired, or otherwise invalid JWT
rejects the handshake without connecting to NATS. If NATS setup fails, the
handshake is rejected without leaving a partial subscription. After
acceptance, permanent broker failure closes the socket. Disconnect, expiry,
and errors release every subscription and the NATS connection, including
partially established resources.

Each received NATS message becomes one **binary** WebSocket frame containing
a MessagePack map with exactly these keys:

```text
event    string                  delivered NATS subject, not the subscription pattern
headers  map<string, string>     NATS headers; empty map when absent
message  binary                  unchanged NATS message payload bytes
```

The selected Python NATS client's header representation is a string map, so
the template preserves the values exposed by that client. The payload is not
decoded or validated as application data. The socket is receive-only:
client-to-server event publishing or subscription changes are not provided.

Browser requests with an `Origin` header must match one of the full origins
in `EVENTS_ALLOWED_ORIGINS`, a comma-separated setting without wildcards.
The generated local `.env` lists `http://localhost:8081` and
`http://app.localhost:8081`; other development origins are explicit
overrides. Native clients without an `Origin` header may connect with a valid
JWT. The token remains mandatory for both. No application session or user
database is implied by the `sub` string.

## URL Credential Handling

The requested path form places a bearer token in the URL. Nginx disables
access logging for the `/ws/events/` location, and application code does not
log the token or full path. Documentation identifies upstream proxy, CDN,
and tracing logs as deployment concerns that must redact the path. Local
development uses `ws://`; a production deployment must use TLS and `wss://`.
Token expiry limits the lifetime of a leaked URL.

## Frontend Boundaries

React and Flutter replace their NATS WebSocket URL setting and direct NATS
connector interface with a Django events WebSocket URL and a small
token-taking connection interface. The interface describes connection and
closure; the documented binary MessagePack frame is the wire contract.
Neither placeholder screen opens a connection. Each derived project decides
how to obtain a token and when to connect. A separate application API base
setting may remain for future Django APIs.

## Verification

Focused backend tests prove JWT issuance and rejection, subject validation,
multiple subscriptions, MessagePack field types and bytes, missing headers,
invalid-token rejection before NATS access, expiry closure, and cleanup on
disconnect or partial failure. Consumer tests use a fake NATS client rather
than requiring a broker.

Configuration tests check that neither NATS port nor a NATS WebSocket proxy is
published, that only the broker and backend receive their shared NATS
credential, that only the backend receives the JWT secret,
and that Nginx proxies `/ws/events/` to Django without access logging. The
existing environment generation and Compose checks are updated to the new
secrets and service graph. A full-stack smoke test issues a token inside the
backend, publishes a message through internal NATS, and verifies the
MessagePack frame through Nginx; it also checks rejection of an invalid
token. Existing Django, React, Flutter, and configuration checks continue to
pass. Unrelated existing Flutter working-tree changes are preserved.

## Documentation and Agent Instructions

The README and local architecture documentation describe the new private
broker path, the issuer function, the WebSocket and MessagePack contract,
setup, smoke checks, and extension points. Obsolete direct-client NATS auth
documents are removed or replaced so they cannot be mistaken for current
instructions. Historical Superpowers artifacts remain intact.

Root `AGENTS.md` describes the repository layout, how to validate changes,
the ASGI and private-NATS boundaries, the rule to protect existing user
changes, and the user's instruction: whenever an agent asks a question, it
must stop all work until the user responds. Session-specific model choices
are not encoded as project policy.
