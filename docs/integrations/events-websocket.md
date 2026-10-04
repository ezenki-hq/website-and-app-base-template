# Django event WebSocket integration

This template keeps NATS private and gives clients a Django WebSocket at
`/ws/events/{jwt}`. Django validates the token, subscribes to its NATS
subjects, and sends each message as a binary MessagePack frame. The template
contains the transport foundation; derived projects supply identity,
authorization policy, token delivery, and client lifecycle behavior.

## Issuing tokens

Call `events.tokens.issue_event_token(identity, events)` from trusted Django
code after authenticating the recipient and authorizing each subject:

```python
from events.tokens import issue_event_token

token = issue_event_token("member-123", ["app.orders.*"])
```

The helper does not authenticate identities or choose permissions. A derived
project must make those decisions before calling it. There is no public token
issuer route and clients cannot request arbitrary NATS subjects.

Tokens use HS256 and the dedicated `EVENTS_JWT_SIGNING_SECRET`. Required
claims are `iss="website-app-template"`, `aud="events-websocket"`, `sub`,
`iat`, `exp`, `jti`, and a nonempty `events` list. The default lifetime is
3,600 seconds (`EVENTS_JWT_TTL_SECONDS`). At most 32 distinct NATS subjects
are allowed. `*` must occupy a complete subject token, and `>` must be the
final complete token. The same validation runs when tokens are decoded.

A token is a reusable bearer credential until expiration. Django closes an
established WebSocket at the token's expiry time.

## Connect and Origin rules

Connect with the JWT in the requested path:

```text
ws(s)://<host>/ws/events/<jwt>
```

Django validates the token before connecting to NATS. It opens one NATS
connection for the socket, subscribes to every listed subject, and accepts
the WebSocket only after setup succeeds. Invalid tokens create no NATS
connection. A setup failure rejects the handshake; permanent broker failure
closes an accepted socket with `1011`; expiry closes it with `1008`.

If a request includes `Origin`, its full origin must exactly match one of the
comma-separated values in `EVENTS_ALLOWED_ORIGINS`, including scheme, host,
and port. The local defaults are `http://localhost:8081` and
`http://app.localhost:8081`. A native client may omit `Origin`, but still
needs a valid JWT.

The URL path contains the bearer credential. Local Nginx disables access
logging on this route and application code does not log the token or full
path. Deployment proxies, CDNs, load balancers, tracing, and error reports
must redact it. Use TLS and `wss://` outside local development.

## MessagePack frame

Every broker message becomes one binary WebSocket frame. The unpacked map has
exactly these keys and types:

```text
event    string                 delivered NATS subject
headers  map<string, string>    NATS headers, or {} when absent
message  binary                 unchanged NATS payload bytes
```

The socket is receive-only. The template does not decode payload contents,
validate application event schemas, publish from clients, or change
subscriptions after connection.

## Private NATS boundary

NATS native and monitoring listeners are reachable only inside the Compose
network. No host ports or NATS WebSocket listener are configured. Django and
the broker share the generated local backend username/password; the broker
limits that user to the `app.>` publish and subscribe namespace. Only Django
receives the event JWT signing secret. Frontends receive only the WebSocket
URL setting.

A derived project may adjust NATS permissions and subjects for its application
namespace. It should preserve the private broker boundary and grant the
backend only the subjects the service requires.

## Frontend extension points

The React interface is `web/src/lib/events.ts`; its runtime URL is
`runtimeConfig.eventsWebsocketUrl`, sourced from `VITE_EVENTS_WEBSOCKET_URL`.
Flutter defines `EventConnector` in `app/lib/integrations/events.dart` and
reads `EVENTS_WEBSOCKET_URL` through `RuntimeConfig.eventsWebSocketUrl`.

These are interfaces only. The screens do not connect automatically, fetch a
token, decode MessagePack, reconnect, or publish. Derived projects choose
those behaviors and add a MessagePack client library only when they implement
the decoder.

## Local setup and checks

Generate a mode-`0600` environment file and start the React stack:

```bash
bash infra/scripts/generate-local-env.sh
docker compose --env-file .env -f infra/compose.yaml up --build
```

Run both end-to-end probes:

```bash
STACK_ENV_FILE="$PWD/.env" bash infra/scripts/smoke-stack.sh
STACK_ENV_FILE="$PWD/.env" bash infra/scripts/smoke-flutter-web.sh
```

The smoke probe issues its token inside the backend container, connects
through Nginx, publishes a binary payload with a NATS header, and verifies the
MessagePack frame. It also checks malformed-token rejection and that NATS has
no published host ports. It does not print or pass the token as a command-line
argument.

## Existing environment migration

The generator never overwrites an existing environment file. A legacy file
with the previous auth-callout variables will fail and name a missing new
key. Keep it at mode `0600` under a backup name such as `.env.legacy`, then run
the generator to create a fresh `.env`. Reapply only values needed by the new
stack and keep the backup private until it is safe to remove.
