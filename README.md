# Website and Application Base Template

This repository is a reusable starting point for a public billboard website
and a separate application backed by Django. It proves the local architecture,
routing, and NATS authentication flow without choosing project-specific data
models, UI, identity, or real-time behavior.

> **Choose the application frontend deliberately.** React is the default and
> is the right starting point for a primarily web-first application. Use
> Flutter when the application is primarily mobile-first. Either frontend, or
> both, can remain in a derived project; the Flutter Web Compose override shows
> how Flutter can replace React on the local application host.

The local token issuer is **anonymous and development-only**. Before using this
template outside local development, replace its policy-construction and token
issuance helpers with project authentication and authorization. Never accept
an account or permissions supplied by an untrusted caller. Production also
requires separate Nginx and deployment configuration; the checked-in stack is
not a production deployment.

## Components

| Path or service | Responsibility |
| --- | --- |
| `backend/` | Django, Wagtail, health checks, and development NATS JWT endpoints |
| `web/` | Default Vite, React, and TypeScript application |
| `app/` | Mobile-first Flutter application with optional Flutter Web support |
| `postgres` | Persistent local PostgreSQL database |
| `nats` | Native and WebSocket NATS listeners with auth callout |
| `nats-auth-redirect` | Published redirector that bridges NATS auth callout to Django |
| `nginx` | Browser-facing development router for the two local hosts |
| `infra/` | Compose, NATS, Nginx, environment-generation, and smoke-test files |

The frontend auth and NATS libraries are intentionally interfaces only. The
template does not install a NATS client, open a connection, or provide a
production identity system.

For topology, ports, and trust boundaries, read
[Local stack architecture](docs/architecture/local-stack.md). For the complete
local authentication flow, read
[NATS authentication](docs/integrations/nats-authentication.md).

## Prerequisites

The repository Dev Container provides the expected Python, `uv`, Node/npm,
Flutter, Docker CLI, Bash, OpenSSL, `curl`, and `jq` tooling. The Compose
commands target the Docker daemon available inside that environment. If you
work outside it, provide equivalent tools and a running Docker daemon.

Run commands from the repository root unless a command starts with `cd`.

## Start and stop the local stack

Generate an ignored, mode-`0600` `.env` containing local-only credentials and a
paired NATS account signer:

```bash
bash infra/scripts/generate-local-env.sh
```

The generator is idempotent: a valid existing `.env` is checked and left
unchanged. Existing files must be regular, not symbolic links, and have exact
mode `0600`; the generator also derives the account public key from the seed
with the pinned NATS tooling and rejects a mismatch. It does not print
generated values.

Build and start the default React stack:

```bash
docker compose --env-file .env -f infra/compose.yaml up --build
```

The command stays attached so service logs remain visible. Use another shell
for management and inspection commands. The main local endpoints are:

- billboard website and Wagtail: <http://localhost:8081/>
- React application: <http://app.localhost:8081/>
- Django readiness: <http://app.localhost:8081/health/>
- native NATS: `nats://localhost:4222`
- NATS monitoring: <http://localhost:8222/>
- browser NATS WebSocket: `ws://app.localhost:8081/nats/`

Stop the default stack:

```bash
docker compose --env-file .env -f infra/compose.yaml down
```

The named `postgres-data` and generated `static-assets` volumes remain.
Removing the database volume is a separate, destructive operation and is not
part of normal shutdown.

To inspect service state in another shell:

```bash
docker compose --env-file .env -f infra/compose.yaml ps
docker compose --env-file .env -f infra/compose.yaml logs --tail=100
```

## Django and Wagtail

The backend container waits for PostgreSQL, runs migrations, collects Django
and Wagtail static assets into the shared `static-assets` volume, then serves
Django with Gunicorn on its internal port. Nginx mounts that volume read-only
and serves `/static/`; Gunicorn does not serve static files. The migration
creates a minimal Wagtail home page and default site.

Routes behind `localhost:8081` include:

| Route | Purpose |
| --- | --- |
| `/` | Public Wagtail billboard page |
| `/admin/` | Wagtail administration |
| `/django-admin/` | Django administration |
| `/documents/` | Wagtail document handling |
| `/health/` | Database-backed readiness response |
| `/api/nats/token/` | Anonymous development token issuer |
| `/api/nats/authorize/` | Redirector authorization API |

For a directly configured backend development process, create an administrator
with:

```bash
cd backend && uv run python manage.py createsuperuser
```

That direct command requires the Django, NATS JWT, and database environment to
be available to the process. With the Compose stack running, the equivalent
container command already has that environment and network:

```bash
docker compose --env-file .env -f infra/compose.yaml exec backend python manage.py createsuperuser
```

Add project Django applications beside `backend/home/`, register their URLs in
`backend/config/urls.py`, and add Wagtail page types under the appropriate
project application. Keep the `/health/` route cheap and free of sensitive
configuration.

## React

React is the default application served at `app.localhost:8081`. The scaffold
uses Vite, TypeScript, and same-origin defaults:

- `VITE_API_BASE_URL=/api/`
- `VITE_NATS_WEBSOCKET_URL=/nats/`

Run the component development server directly with:

```bash
cd web && npm run dev
```

The direct Vite server proves and develops the UI. The same-origin `/api/` and
`/nats/` paths are integrated by Nginx in the Compose stack, not by a Vite
proxy. Set Vite environment overrides only when a derived project also
provides the needed cross-origin policy and reachable endpoints.

Implement token retrieval in `web/src/lib/auth.ts`, NATS connection behavior in
`web/src/lib/nats.ts`, and application UI under `web/src/`. Add a concrete NATS
dependency only when the project implements that connection.

## Flutter

Flutter is the recommended application frontend for primarily mobile-first
projects. Run it on an available device with:

```bash
cd app && flutter run
```

Compile-time runtime values use Dart defines:

```bash
cd app && flutter run \
  --dart-define=API_BASE_URL=https://example.invalid/api/ \
  --dart-define=NATS_WEBSOCKET_URL=wss://example.invalid/nats/
```

The defaults are `/api/` and `/nats/`. Platform networking rules determine how
a simulator or physical device reaches a development host, so use device-
appropriate absolute URLs when same-origin paths do not apply.

To serve Flutter Web instead of React at `app.localhost:8081`:

```bash
docker compose --env-file .env \
  -f infra/compose.yaml \
  -f infra/compose.flutter-web.yaml \
  up --build
```

The override changes only the application frontend and its Nginx upstream.
The Django health/API routes and `/nats/` WebSocket route remain unchanged.

Implement token retrieval in `app/lib/integrations/auth.dart`, NATS connection
behavior in `app/lib/integrations/nats.dart`, and compile-time configuration in
`app/lib/config/runtime_config.dart`.

## NATS authentication

The local flow has two HTTP endpoints:

```text
GET /api/nats/token/       issue a development JWT
GET /api/nats/authorize/   validate the JWT and return NATS permissions
```

The issuer accepts no account or permission input. It constructs the signed
scope from server-side environment values, with local publish and subscribe
access limited to `app.>` by default. A client supplies that JWT as its NATS
connection token. NATS sends an auth-callout request to the redirector, the
redirector forwards the token to Django as a Bearer credential, and the
redirector signs NATS's authorization response with its separate account
signer seed.

The authorization endpoint also accepts a cookie named `auth`. If a Bearer
credential and `auth` cookie are both present, they must be byte-for-byte
equal; conflicting values are rejected rather than choosing one.

Derived projects must replace `scope_from_settings()` in
`backend/nats_auth/config.py` and the development issuance path built from
`issue_token()` and `token()` in `backend/nats_auth/tokens.py` and
`backend/nats_auth/views.py`. Bind permissions to an authenticated,
server-authorized identity. Do not extend the anonymous view to accept
caller-provided subjects or accounts.

See [NATS authentication](docs/integrations/nats-authentication.md) for the
exact JWT scope, redirect response, credential rules, and redirector
limitations. The redirector's source-derived behavior is recorded in the
[authoritative redirect contract](docs/integrations/nats-auth-redirect.md).

## Nginx routing

Nginx is the only browser-facing HTTP entry point in the default stack.

| Host | Route | Destination |
| --- | --- | --- |
| `localhost` | `/static/*` | Nginx read-only static asset volume |
| `localhost` | `/nats/` | NATS WebSocket listener |
| `localhost` | every other path | Django and Wagtail |
| `app.localhost` | `/health/` | Django |
| `app.localhost` | `/api/*` | Django |
| `app.localhost` | `/nats/` | NATS WebSocket listener |
| `app.localhost` | every other path | React by default; Flutter Web with the override |

Both hosts use port `8081` from the development machine. The configuration
preserves WebSocket upgrade headers and allows long-lived connections. See
[Local stack architecture](docs/architecture/local-stack.md) for internal and
published ports.

## Environment variables

`.env.example` mirrors the keys created and validated by
`generate-local-env.sh` for the checked-in Compose stack. Blank values are
intentional placeholders, not usable credentials. It is not an inventory of
every optional setting implemented by Django.

| Group | Keys | Notes |
| --- | --- | --- |
| Django | `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS` | Generated secret; local hosts include `localhost`, `app.localhost`, and `backend` |
| PostgreSQL | `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT` | Local database credentials and Compose service address |
| Client JWT | `NATS_JWT_SIGNING_SECRET`, `NATS_JWT_ISSUER`, `NATS_JWT_AUDIENCE`, `NATS_JWT_TTL_SECONDS`, `NATS_JWT_SUBJECT` | Dedicated HS256 secret and validation claims; default lifetime is 86,400 seconds |
| NATS policy | `NATS_ACCOUNT`, `NATS_PUBLISH_ALLOW`, `NATS_PUBLISH_DENY`, `NATS_SUBSCRIBE_ALLOW`, `NATS_SUBSCRIBE_DENY` | Permission lists are JSON arrays encoded as strings |
| Redirect auth user | `NATS_AUTH_USER`, `NATS_AUTH_PASSWORD` | Used by NATS and the redirector; current Django code does not read these values |
| Account signer | `NATS_ACCOUNT_SIGNER_SEED`, `NATS_ACCOUNT_SIGNER_PUBLIC_KEY` | Private seed is used by the redirector; matching public key is used by NATS; current Django code reads neither |
| React runtime | `VITE_API_BASE_URL`, `VITE_NATS_WEBSOCKET_URL` | Default same-origin paths are `/api/` and `/nats/` |
| Optional Wagtail | `WAGTAIL_SITE_NAME`, `WAGTAILADMIN_BASE_URL` | Defaults to `Billboard website` and `http://localhost:8000`; these optional keys are implemented but are not written by the generator or listed in `.env.example` |

Compose interpolates the generated `.env` on the host and explicitly injects
only each service's required keys. The backend receives its Django/Wagtail,
PostgreSQL, client-JWT, and NATS policy settings; it does not receive the
redirect auth credentials, account signer material, or React runtime values.

Malformed permission JSON fails Django configuration. An empty allow list
allows no subjects; it does not mean unrestricted access. Keep `.env` ignored,
do not print or commit it, and never reuse generated local values in
production.

## Extension locations

| Concern | Extend or replace |
| --- | --- |
| Project data and APIs | New Django applications under `backend/`; URL composition in `backend/config/urls.py` |
| Billboard content types | Wagtail models/templates under `backend/home/` or a new project application |
| Authenticated token issuance | Replace the development path in `backend/nats_auth/views.py` and `backend/nats_auth/tokens.py` |
| NATS permission policy | Replace `scope_from_settings()` in `backend/nats_auth/config.py` |
| React UI and integration | `web/src/`, especially `web/src/lib/auth.ts` and `web/src/lib/nats.ts` |
| Flutter UI and integration | `app/lib/`, especially `app/lib/integrations/` |
| Local routes | `infra/nginx/conf.d/default.conf` and the Flutter example |
| Local orchestration | `infra/compose.yaml` and narrowly scoped Compose overrides |
| Credential injection | Preserve explicit per-service environment/secret injection when adapting the local Compose topology |

Keep the redirector image unchanged unless the project deliberately adopts and
documents a different redirect service contract.

## Verification

Validate both Compose resolutions, NATS configuration, and both Nginx
configurations:

```bash
bash infra/scripts/validate-config.sh
```

Run the default full-stack routing and authentication smoke test:

```bash
bash infra/scripts/smoke-stack.sh
```

Run the same checks with Flutter Web replacing React:

```bash
bash infra/scripts/smoke-flutter-web.sh
```

The smoke scripts do not print JWTs or signer/password values. On a cold
project they remove the containers and network they created. On a warm or
partially running Compose project, preservation is tracked by Compose service
name rather than exact pre-run container identity; avoid changing or replacing
the same project’s containers concurrently with a smoke run.

Component checks are:

```bash
cd backend
uv sync --locked
uv run python manage.py test
uv run python manage.py check
uv run python manage.py makemigrations --check
```

```bash
cd web
npm ci
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

## Troubleshooting

- **`.env` is missing or invalid:** run the generator. If it reports an
  existing invalid file, inspect key names without printing values. To rotate
  local credentials intentionally, stop the stack and preserve the old file
  before generating a replacement so the signer seed and public key remain a
  matched pair.
- **`app.localhost` does not resolve:** most modern resolvers map `*.localhost`
  to loopback. If yours does not, add a local hosts-file mapping or send
  `Host: app.localhost` to `127.0.0.1:8081`.
- **A container is unhealthy:** inspect `docker compose ... ps` and
  `docker compose ... logs --tail=100`. PostgreSQL, Django, NATS, the frontend,
  and Nginx have health checks; the redirector intentionally does not.
- **The redirector restarts:** it exits when its initial NATS connection fails.
  Compose waits for NATS health and uses `restart: unless-stopped`, but logs
  should still be checked for bad auth-user credentials or mismatched signer
  material.
- **A browser WebSocket cannot connect:** use `/nats/` through Nginx, including
  the trailing slash, and supply the development JWT as the NATS connection
  token. Do not use NATS's internal WebSocket port directly from a browser.
- **Direct React or Flutter development cannot reach `/api/`:** same-origin
  defaults assume the Nginx-served stack. Use device-appropriate overrides and
  add a deliberate cross-origin policy only when the project needs one.
- **Port conflict:** the local stack publishes `8081`, `4222`, and `8222`.
  Stop the conflicting process or change the development Compose mapping and
  update all local documentation and tests together.

## Production separation

Do not promote `infra/compose.yaml`, either local Nginx file, `.env`, the
anonymous issuer, or unencrypted local NATS transport as production
configuration. A production deployment must separately define:

- real hostnames, TLS, proxy policy, and Nginx/deployment configuration;
- authenticated identity and server-owned authorization policy;
- least-privilege secret injection, secret storage, and credential rotation;
- encrypted NATS and HTTP transport;
- observability, readiness, scaling, and recovery behavior; and
- production database, static/media storage, and frontend delivery.

The local files are intentionally fixed and understandable. Keep production
concerns in separate deployment configuration rather than parameterizing the
development Nginx server blocks into a production template.
