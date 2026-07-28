# Billboard Website and Application Base Template Design

**Date:** 2026-07-28
**Status:** Approved design, pending written-spec review

## Purpose

This repository will be a reusable starting point for projects that need:

- a public billboard or marketing website;
- a backend that can grow into project-specific Django applications and APIs;
- a web-first React application, a mobile-first Flutter application, or both;
- real-time NATS connectivity for native and browser clients; and
- a local Docker Compose environment with Nginx as its public entry point.

The template will prove that each component runs and that authentication works,
without including business-specific models, user interfaces, state, or
real-time features.

React is the default application frontend because the default local application
host is web-facing. Derived projects should use React when the application is
primarily web-first and Flutter when it is primarily mobile-first. Both remain
in the repository so a project may use either or both. Flutter Web can replace
React on the local application host through a documented example override.

## Scope

The template includes:

- Django and Wagtail;
- PostgreSQL;
- a minimal Vite and React TypeScript application;
- a minimal Flutter application with web support;
- NATS native and WebSocket listeners;
- NATS auth callout through
  `ezenki/nats-auth-redirector:1.0.0`;
- Nginx development routing;
- Docker Compose local orchestration;
- generated local development secrets;
- health checks and smoke checks; and
- architecture, integration, and usage documentation.

The template does not include:

- business-specific data models or behavior;
- a production authentication system;
- active NATS use in React or Flutter;
- JetStream;
- Kubernetes;
- CI/CD;
- cloud-provider configuration;
- production deployment automation;
- production Nginx configuration; or
- production credentials.

## Authoritative NATS Redirect Contract

`docs/integrations/nats-auth-redirect.md` is the authoritative integration
contract for the redirect service. The template will use the published image
unchanged and will not reimplement, wrap, or modify the redirector.

The relevant constraints are:

- The redirector has no HTTP server, exposed port, or health endpoint.
- It connects to NATS using `NATS_URL`.
- It receives auth callout requests through `$SYS.REQ.USER.AUTH`.
- It makes an HTTP `GET` request to `AUTH_SERVER` for each decoded request.
- It forwards the NATS client token as an HTTP Bearer token.
- It expects a JSON response containing `account` and optional top-level `pub`
  and `sub` permission objects.
- It signs the authorization response with `ACCOUNT_SIGNER_SEED`.
- The corresponding public key must be the NATS auth-callout `issuer`.
- Its NATS user must appear in `auth_users` and be exempt from the callout.
- Its initial NATS connection failure exits the process.
- It has no explicit HTTP timeout.

The local design will start the redirector after NATS reports healthy and use
`restart: unless-stopped` to compensate for later initial-connection failures.
It will not invent a health endpoint or claim that process liveness proves the
redirector is ready.

## Repository Structure

```text
backend/                       Django and Wagtail
web/                           React and Vite application
app/                           Flutter application
infra/
  compose.yaml                 Default local stack
  compose.flutter-web.yaml     Example Flutter Web override
  nginx/                       Default and example routing configuration
  nats/                        NATS configuration
  scripts/                     Local secret setup and smoke checks
docs/
  architecture/                Topology and trust-boundary documentation
  integrations/                Integration contracts and usage
  superpowers/specs/           Approved design specifications
```

Generated environment files and signer material will be ignored by Git. A
committed example environment file will list every variable without containing
usable production secrets.

## Component Architecture

### Backend

The backend will use:

- Python 3.13 as supplied by the Dev Container;
- `uv` for dependency and lock-file management;
- Django 5.2 LTS;
- Wagtail 7.4 LTS;
- PostgreSQL; and
- Gunicorn as the WSGI server inside the local container rather than Django's
  development server as the Compose dependency target.

Django will use one explicit project settings module loaded from environment
variables and will not add a third-party settings framework.

The project will provide clear locations for future Django applications and
APIs. The initial code will contain only:

- project configuration;
- a minimal Wagtail `HomePage`;
- the health view;
- the NATS development token view;
- the NATS authorization view; and
- focused helpers for JWT issuance, validation, and permission-policy
  construction.

No Django REST Framework dependency will be added. The three JSON/health
endpoints will use plain Django views.

### Wagtail Website

The root Wagtail site will use a minimal `HomePage` model and template. An
idempotent data migration will create the initial page and default Wagtail
`Site`, allowing a fresh database to become usable through normal migrations
without manual page setup.

Wagtail admin and Django admin will be available through their conventional
backend routes. The public page will contain only enough content and styling to
prove that Wagtail serves the billboard website.

### React Application

The React application will use:

- Vite;
- React;
- TypeScript;
- npm and a committed lock file; and
- the minimal lint and build tooling supplied by the scaffold.

It will not include a router, state-management library, UI framework, or active
network behavior. The main `App` component will contain only a small
proof-of-life landing screen.

A configuration library will expose the Django API base path and NATS
WebSocket path. Typed library boundaries will describe:

- obtaining an authentication JWT; and
- opening and closing a NATS connection.

Those operations will deliberately remain unimplemented and unused by the
main component. No NATS client dependency will be installed until a derived
project implements the connection library.

Default development values will use Nginx same-origin paths:

```text
Django API: /api/
NATS WebSocket: /nats/
```

Vite environment variables will allow direct-development overrides.

### Flutter Application

The Flutter application will remain mobile-first while retaining Flutter Web
support. It will include:

- a minimal `MaterialApp`;
- one proof-of-life screen;
- centralized runtime configuration populated with `--dart-define`;
- an abstract token-library interface; and
- an abstract NATS connection-library interface.

The interfaces will remain unimplemented and unused by the main widget. No
business functionality or active network behavior will be present.

Repository verification will not require the Android SDK, an Android emulator,
Xcode, or an iOS simulator. Formatting, analysis, widget tests, and a web build
will be the initial verification boundary.

### PostgreSQL

PostgreSQL will persist local data in a named Docker volume. Django will obtain
its database name, user, password, host, and port from separate environment
variables. The Compose health check will use `pg_isready`, and Django startup
will wait for PostgreSQL readiness before migrations and serving traffic.

### NATS

NATS will use a committed configuration file and will provide:

- native client connections on port `4222`;
- WebSocket connections on a dedicated internal port;
- monitoring on port `8222`;
- an `AUTH` account for the redirector auth user;
- an `APP` account for application clients;
- a `SYS` system account;
- `system_account: SYS`;
- an auth callout whose account is `AUTH`;
- the generated account signer public key as the callout issuer; and
- the redirector user in `auth_users`.

JetStream will be disabled.

The native client port will remain available to backend, native Flutter, and
diagnostic clients. Browser clients will use Nginx WebSocket routing. Local
transport will be unencrypted and explicitly documented as development-only.
Production transport security belongs in separate deployment configuration.

### Redirector

Compose will run exactly:

```text
ezenki/nats-auth-redirector:1.0.0
```

Its environment will include:

- `AUTH_SERVER`, pointing to Django's internal authorization URL;
- `NATS_URL`, containing the exempt redirect auth-user credentials; and
- `ACCOUNT_SIGNER_SEED`, loaded from ignored local secret configuration.

The service will expose no port and receive no invented health check. Compose
will restart it after initial NATS connection races or process failures.

### Nginx

Nginx is the documented browser-facing entry point. Local development uses
fixed hostnames. Production must use a separate configuration file rather than
parameterizing the local server names.

Default routing is:

| Host | Route | Destination |
| --- | --- | --- |
| `localhost` | `/nats/` | NATS WebSocket listener |
| `localhost` | all other paths | Django and Wagtail |
| `app.localhost` | `/api/*` | Django |
| `app.localhost` | `/health/` | Django |
| `app.localhost` | `/nats/` | NATS WebSocket listener |
| `app.localhost` | all other paths | React/Vite |

The NATS locations will preserve WebSocket upgrade headers and use a
24-hour proxy read timeout for long-lived connections.

The Flutter Web example will replace only the application-frontend upstream.
It will preserve the `app.localhost` API, health, and NATS routes.

## Django HTTP Contracts

### Health

```http
GET /health/
```

The endpoint will perform a lightweight database query. It will return a JSON
success response only when Django is running and the database is reachable. It
will not expose configuration or dependency credentials.

### Development Token Issuance

```http
GET /api/nats/token/
```

This endpoint is anonymous and development-only. It will accept no permission
or account inputs. It will construct permissions entirely from server-side
environment configuration and return:

```json
{
  "token": "<signed-jwt>",
  "token_type": "Bearer",
  "expires_at": "<UTC ISO-8601 timestamp>"
}
```

The JWT will use HS256 with a dedicated environment-provided signing secret,
separate from Django's `SECRET_KEY`. Its default lifetime is 86,400 seconds and
is environment-configurable.

Standard claims are:

- `sub`;
- `iss`;
- `aud`;
- `iat`;
- `exp`; and
- `jti`.

A namespaced `nats` claim contains the authorization scope:

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

The account, allowlists, and denylists will be environment-configurable. The
safe local defaults grant publish and subscribe access only under `app.>`.

Documentation will identify the policy-construction and issuance helpers as
the place where derived projects must add authenticated identity and custom
permission logic. Anonymous callers must never be allowed to submit arbitrary
permissions.

### Authorization

```http
GET /api/nats/authorize/
Authorization: Bearer <jwt>
```

The endpoint accepts the same JWT from either:

- the `Authorization: Bearer <jwt>` header; or
- a cookie named `auth`.

The general name `auth` allows a derived application to reuse the cookie for
other authentication decisions. This endpoint reads and enforces its signed
`nats` claim. The redirector always uses the Bearer form because that behavior
is fixed by its authoritative contract.

If both credential sources are present and differ, the endpoint rejects the
request. It will not silently choose one.

Validation includes:

- signing algorithm;
- signature;
- expiration;
- issuer;
- audience;
- required standard claims;
- the `nats` object;
- account name; and
- publish and subscribe permission-list structure.

A valid token produces the exact redirect response shape:

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

Missing, conflicting, expired, malformed, or invalid credentials return an
HTTP failure status greater than 300. This ensures the redirector converts the
failure into a signed denial. Error responses will not include the token or
verification details useful to an attacker.

## Authentication and Trust Flow

```text
Client
  |
  | GET /api/nats/token/ (development issuer)
  v
Django signs JWT containing the NATS scope
  |
  | token authentication
  v
NATS creates authorization-request JWT
  |
  | $SYS.REQ.USER.AUTH
  v
Redirector, connected as exempt AUTH user
  |
  | GET /api/nats/authorize/
  | Authorization: Bearer <client JWT>
  v
Django validates JWT and returns account/pub/sub
  |
  v
Redirector signs authorization-response JWT
  |
  v
NATS accepts or rejects the client
```

Credential ownership is explicit:

| Value | Django | NATS | Redirector | Client |
| --- | --- | --- | --- | --- |
| Django application secret | uses | no access | no access | no access |
| NATS client JWT signing secret | uses | no access | no access | no access |
| Account signer seed | no access | no access | uses | no access |
| Account signer public key | no access | trusts | derives | no access |
| Redirect auth password | no access | validates | uses | no access |
| Issued client JWT | issues/validates | forwards in callout | forwards to API | uses |

## Environment Configuration

The committed example environment file will document at least:

- Django secret key;
- Django debug mode;
- Django allowed hosts needed for the two local domains;
- PostgreSQL database, user, password, host, and port;
- NATS JWT signing secret;
- JWT issuer;
- JWT audience;
- JWT lifetime in seconds, defaulting to `86400`;
- development subject;
- NATS account, defaulting to `APP`;
- publish allow and deny lists;
- subscribe allow and deny lists;
- redirect auth username and password;
- account signer seed;
- account signer public key; and
- Vite API and NATS WebSocket overrides.

Permission lists will be JSON arrays encoded in environment-variable strings
and will reject malformed values during settings initialization. Empty deny
lists are valid. Empty allow lists mean no allowed subjects rather than
unrestricted access.

A repository script will generate development-only secrets and the NATS
account signing key pair. Generated files will be ignored. The README will
warn users not to reuse local values in production.

## Compose Behavior

`infra/compose.yaml` will be the single default local stack. It will build or
run:

- `postgres`;
- `backend`;
- `web`;
- `nats`;
- `nats-auth-redirect`;
- `nginx`; and
- a profile-gated `nats-smoke` service based on a pinned `nats-box` image for
  native and WebSocket authentication checks.

The default documented startup command will initialize local secrets, build
the services, run database migrations, and start the stack. It will not mount
the host Docker socket. All Docker commands run against the Dev Container's
inner daemon.

Health checks:

| Service | Check |
| --- | --- |
| PostgreSQL | `pg_isready` |
| Django | `/health/` |
| NATS | monitoring readiness |
| React/Vite | HTTP response |
| Nginx | HTTP response through a local server block |
| Redirector | no invented health check |

Compose dependency conditions will be used only when the dependency has a
meaningful readiness contract. The redirector restart policy compensates for
its documented initial-connection exit behavior.

The Flutter Web example Compose override will start the Flutter web server and
select the corresponding Nginx frontend configuration. It is an example, not
the default stack.

## Verification Strategy

### Django Tests

Tests will cover:

- the initial `HomePage` and Wagtail `Site` migration behavior;
- public home-page routing;
- successful and failed database health checks;
- token response shape;
- default and configured JWT lifetime;
- required standard claims;
- environment-derived account and permissions;
- refusal to accept caller-selected permissions;
- Bearer authorization;
- `auth` cookie authorization;
- matching header and cookie credentials;
- conflicting header and cookie credentials;
- missing, expired, malformed, wrongly signed, wrong-issuer, and
  wrong-audience tokens;
- malformed NATS scope claims;
- exact successful redirect response shape; and
- non-sensitive failure responses with status codes greater than 300.

### React Checks

Checks will include:

- linting;
- TypeScript compilation;
- production build; and
- a minimal render smoke test for the proof-of-life component.

The typed integration boundaries will be checked without implementing or
calling them.

### Flutter Checks

Checks will include:

- Dart formatting;
- `flutter analyze`;
- a widget test for the proof-of-life screen; and
- `flutter build web`.

No Android or iOS toolchain will be required.

### Configuration Checks

Checks will include:

- resolved `docker compose config`;
- NATS configuration validation with generated local values;
- `nginx -t` for default React routing; and
- `nginx -t` for the Flutter Web example.

### Full-Stack Smoke Check

The smoke workflow will:

1. generate disposable local secrets;
2. start the Compose stack;
3. wait for meaningful health checks;
4. verify the Wagtail site through `localhost`;
5. verify React through `app.localhost`;
6. verify Django API routing through `app.localhost`;
7. obtain a development JWT;
8. connect through the native NATS listener;
9. connect through the Nginx NATS WebSocket route;
10. publish and subscribe under `app.>`;
11. confirm an unauthorized subject is rejected;
12. confirm an invalid token is rejected; and
13. avoid printing JWTs, signer seeds, or passwords.

The Flutter Web example will have a separate smoke check proving that the
frontend replacement preserves the API and NATS route configuration.

## Documentation

The root README will explain:

- the template's purpose;
- its major components;
- React for web-first and Flutter for mobile-first projects;
- why both applications remain available;
- prerequisites provided by the Dev Container;
- local secret initialization;
- starting, stopping, rebuilding, and inspecting the stack;
- Django and Wagtail commands and administration;
- React commands and environment variables;
- Flutter commands, `--dart-define`, and web example;
- fixed local hostnames;
- Nginx route boundaries;
- Django token and authorization contracts;
- Bearer and `auth` cookie behavior;
- the NATS auth callout flow;
- redirector constraints;
- expected environment variables;
- verification and smoke-test commands;
- troubleshooting;
- where project-specific backend, website, frontend, and permission logic
  belongs; and
- the need for separate production Nginx and deployment configuration.

Architecture documentation will explain the container topology, internal and
public ports, trust boundaries, credential ownership, and native versus
WebSocket NATS access.

## Error Handling and Security

- Environment secrets will not have production defaults in committed files.
- Generated development secrets will be ignored by Git.
- JWT validation will use an explicit algorithm rather than trusting the token
  header to select one.
- JWT tokens and signer material will not be logged.
- The authorization endpoint will provide generic denial responses.
- Conflicting Bearer and cookie tokens will be rejected.
- Anonymous token issuance will be labeled development-only in code and docs.
- The anonymous issuer will not accept account or permission input.
- Default permissions will be limited to `app.>`.
- NATS system subjects will not be granted to application clients.
- Nginx will set only the forwarding and upgrade headers required by each
  route.
- Local unencrypted NATS transport will be documented as unsuitable for
  production.
- The redirector's absent timeout and health endpoint will be documented
  rather than hidden behind misleading checks.

## Acceptance Criteria

The design is successfully implemented when:

1. A new Dev Container checkout can initialize local secrets and start the
   default Compose stack using the inner Docker daemon.
2. `http://localhost` serves the initial Wagtail home page.
3. Wagtail administration is reachable through `localhost`.
4. `http://app.localhost` serves the React proof-of-life application.
5. Django API and health routes work through `app.localhost`.
6. Both hosts expose NATS WebSockets at `/nats/`.
7. Native NATS clients can connect on the documented native endpoint.
8. The development token endpoint issues a one-day JWT by default with
   environment-configured NATS permissions.
9. Authorization accepts that JWT through Bearer or the `auth` cookie and
   emits the redirector's exact response shape.
10. End-to-end NATS callout authentication succeeds for valid permissions and
    rejects invalid tokens and denied subjects.
11. React and Flutter contain only empty main UI components, configuration,
    and unimplemented typed integration libraries.
12. Flutter verification succeeds without Android or iOS tooling.
13. The Flutter Web example can replace React without breaking API or NATS
    routes.
14. Component tests, configuration validation, builds, and smoke checks pass.
15. The README covers every required operational and extension topic.
16. No host Docker socket, production credential, business feature, JetStream,
    Kubernetes, CI/CD, or production deployment automation is added.
