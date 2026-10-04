# Website and Application Base Template

A reusable Django and Wagtail website with React and Flutter application
frontends. Django serves authenticated event WebSockets and subscribes to a
private NATS broker. The template supplies transport and authorization
boundaries without choosing an application identity system, event schema, or
client connection lifecycle.

## Project map

| Location | Purpose |
| --- | --- |
| `backend/` | Django/Wagtail HTTP and ASGI WebSocket application |
| `backend/events/` | Event JWT helpers, NATS bridge, MessagePack frames, and tests |
| `web/` | React/TypeScript application and integration interfaces |
| `app/` | Flutter application and integration interfaces |
| `infra/` | Private NATS, Compose, Nginx, local secret generator, and smoke tests |
| `docs/` | Architecture and event WebSocket integration guide |

## Start the local stack

Generate a local `.env` with separate Django, event-token, database, and NATS
secrets. The file is created with mode `0600` and is ignored by Git.

```bash
bash infra/scripts/generate-local-env.sh
docker compose --env-file .env -f infra/compose.yaml up --build
```

The browser-facing endpoints use port `8081`:

- Wagtail site: <http://localhost:8081/>
- React app: <http://app.localhost:8081/>
- Django health: <http://app.localhost:8081/health/>
- Event WebSocket path: `/ws/events/{jwt}`

Neither NATS listener is published to the host. Compose gives the broker an
internal native listener and monitoring endpoint. Only Django receives the
NATS credentials and the event JWT signing secret; the browser receives none
of them.

To use Flutter Web in place of React:

```bash
docker compose --env-file .env \
  -f infra/compose.yaml \
  -f infra/compose.flutter-web.yaml \
  up --build
```

Validate Compose, NATS, and both Nginx configurations without relying on the
root `.env` path:

```bash
STACK_ENV_FILE="$PWD/.env" bash infra/scripts/validate-config.sh
```

Run the full stack smoke checks with the same optional environment override:

```bash
STACK_ENV_FILE="$PWD/.env" bash infra/scripts/smoke-stack.sh
STACK_ENV_FILE="$PWD/.env" bash infra/scripts/smoke-flutter-web.sh
```

The smoke probes issue their JWT inside the backend container. They do not
print it or pass it as a shell argument.

## Event authorization and transport

Derived Django code calls `events.tokens.issue_event_token(identity, events)`
after authenticating the recipient and authorizing every requested subject.
For example:

```python
from events.tokens import issue_event_token

token = issue_event_token("member-123", ["app.orders.*"])
```

There is no public token issuer route. Never take event subjects from an
untrusted request and pass them to the helper without server-side policy. The
token is HS256 signed with `EVENTS_JWT_SIGNING_SECRET`, has issuer
`website-app-template`, audience `events-websocket`, a token ID, issue/expiry
times, a subject identity, and a nonempty list of up to 32 distinct NATS
subjects. The default lifetime is 3,600 seconds. Valid NATS wildcards must
occupy whole subject tokens; `>` is final.

A client connects to `/ws/events/{jwt}`. Django validates the token before
connecting to NATS, checks a present browser `Origin` against the exact full
origins in `EVENTS_ALLOWED_ORIGINS`, then subscribes to the token's subjects.
Native clients may omit `Origin`, but still need a valid token. Django closes
the socket at expiry and releases each subscription and the NATS connection
on disconnect or failure.

Each NATS message is one binary WebSocket frame containing this exact
MessagePack map:

| Key | Type | Value |
| --- | --- | --- |
| `event` | string | Delivered NATS subject |
| `headers` | string-to-string map | NATS headers, or `{}` when absent |
| `message` | binary | Unchanged payload bytes |

The socket is receive-only. The frontend interfaces in
`web/src/lib/events.ts` and `app/lib/integrations/events.dart` describe a
future connection boundary; they do not connect or decode MessagePack. A
derived project can add the required client library and lifecycle after it
chooses those behaviors.

The JWT is a bearer credential in the URL path. Nginx disables access logging
for the event path, and Django does not log the token or full path. Deployment
proxies, CDNs, tracing, and error reports must also redact it. Use `wss://`
with TLS outside local development.

## Existing `.env` files

The generator validates an existing file and never overwrites it. An
old-format file containing direct NATS auth-callout settings will fail with a
message naming the first missing event-stack key. Preserve it with mode `0600`
under a backup name such as `.env.legacy`, then run the generator to create a
new `.env`. Reapply only still-needed local values to the new file, and keep
the backup private until it can be safely removed.

## Checks

```bash
cd backend
uv sync --locked
uv run python manage.py test
uv run python manage.py check
uv run python manage.py makemigrations --check
```

```bash
cd web
npm test -- --run
npm run lint
npm run build
```

```bash
cd app
dart format --output=none --set-exit-if-changed .
flutter analyze
flutter test
flutter build web
```

The local Docker stack and environment are development examples. Derived
projects must provide their own identity and authorization policy, production
secrets, TLS, logging redaction, deployment topology, and operational
behavior.
