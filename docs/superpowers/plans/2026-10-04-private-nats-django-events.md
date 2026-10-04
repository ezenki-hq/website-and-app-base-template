# Private NATS Django Events Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Execute natively with Luna after the user approves this plan.

**Goal:** Route authorized NATS events through a Django WebSocket as binary MessagePack while keeping NATS private and giving derived projects a server-side JWT issuer.

**Architecture:** Django Channels handles `/ws/events/{jwt}` under ASGI. A valid JWT supplies NATS subscription subjects; each socket owns one private NATS connection, forwards `event`/`headers`/`message` frames, and releases resources at disconnect or expiry. Compose exposes only Nginx, and frontend projects receive integration boundaries rather than active connections.

**Tech Stack:** Python 3.13, Django 5.2, Channels 4.3, PyJWT 2.10, nats-py 2.15, msgpack 1.2, Gunicorn with Uvicorn worker, NATS 2.14, Nginx, Bash, React/TypeScript, Flutter/Dart.

**Spec:** `docs/superpowers/specs/2026-10-04-private-nats-django-events-design.md`

## Global Constraints

- Preserve the current Django 5.2, Wagtail 7.4, Python 3.13, React, and Flutter template structure.
- No public JWT issuer, application login flow, publisher API, project event schema, or automatic frontend connection.
- Route is `/ws/events/{jwt}`; JWT is HS256 with `iss=website-app-template`, `aud=events-websocket`, `sub`, `iat`, `exp`, `jti`, and nonempty `events` list.
- `EVENTS_JWT_TTL_SECONDS` defaults to `3600`; at most 32 distinct valid NATS subjects per token.
- Each binary MessagePack frame has exactly `event: string`, `headers: map<string,string>`, and `message: binary`.
- `EVENTS_ALLOWED_ORIGINS` is a comma-separated list of full origins. Validate a present browser Origin; accept an absent native Origin only with a valid JWT.
- NATS native and monitoring ports remain internal; no NATS WebSocket listener, auth callout, redirector, or client NATS credential.
- Preserve existing unrelated edits in `app/analysis_options.yaml` and `app/pubspec.lock`; stage only files this plan changes.
- A question to the user stops all work until the answer arrives, per the requested root `AGENTS.md` rule.

## File Structure

- `backend/events/subjects.py`: NATS subject validation shared by issuer and decoder.
- `backend/events/tokens.py`: public `issue_event_token` helper and strict JWT decoder.
- `backend/events/frames.py`: MessagePack wire encoding.
- `backend/events/broker.py`: one socket's NATS connection and subscriptions.
- `backend/events/consumers.py`, `backend/events/routing.py`, `backend/config/asgi.py`: WebSocket authorization, lifecycle, and ASGI routing.
- `backend/events/tests/`: isolated JWT, frame, broker, and consumer tests.
- `backend/config/settings.py`, `backend/config/urls.py`, `backend/Dockerfile`, `backend/pyproject.toml`, `backend/uv.lock`: runtime setup and removal of the old HTTP auth path.
- `infra/nats/nats.conf`, `infra/compose.yaml`, both `infra/nginx/conf.d/*.conf`, `.env.example`, `infra/scripts/`: private broker, URL handling, local credentials, and smoke checks.
- `web/src/config/runtime.ts`, `web/src/vite-env.d.ts`, `web/src/lib/events.ts`; `app/lib/config/runtime_config.dart`, `app/lib/integrations/events.dart`: frontend boundaries.
- `README.md`, `docs/architecture/local-stack.md`, `docs/integrations/events-websocket.md`, `AGENTS.md`: current instructions. Delete obsolete active NATS auth docs, endpoints, tests, and client stubs; retain historical Superpowers artifacts.

## Review Focus

These inputs and failures need explicit tests in the owning task:

1. A correctly signed JWT with the wrong audience or malformed `events` must subscribe to nothing: Task 1 `test_rejects_wrong_audience_and_invalid_subjects`, Task 2 `test_invalid_token_never_connects_to_nats`.
2. An `Origin` from another site must fail while a valid native client without Origin may connect: Task 2 `test_origin_policy`.
3. Failure on the second NATS subscription must clean up the first subscription and connection: Task 2 `test_partial_subscription_failure_cleans_up`.
4. A payload containing zero and non-UTF-8 bytes, with no NATS headers, must survive as MessagePack binary with `{}` headers: Task 2 `test_binary_frame_preserves_payload`.
5. A JWT embedded in the WebSocket URL must not enter local Nginx access logs: Task 3 `test_ws_route_has_no_access_log`.

---

### Task 1: Event JWT Contract

**Files:** Create `backend/events/__init__.py`, `backend/events/apps.py`, `backend/events/subjects.py`, `backend/events/tokens.py`, `backend/events/tests/__init__.py`, `backend/events/tests/test_subjects.py`, `backend/events/tests/test_tokens.py`; modify `backend/config/settings.py`.

**Interfaces:** Produce `validate_events(value: object) -> tuple[str, ...]`, `issue_event_token(identity: str, events: Sequence[str]) -> str`, and `decode_event_token(token: str) -> EventClaims`, where `EventClaims` has `identity: str`, `events: tuple[str, ...]`, and `expires_at: datetime`. `decode_event_token` raises `jwt.InvalidTokenError` for invalid claims. Other tasks import these exact names.

- [ ] **Step 1: Write failing tests.** Assert `decode_event_token(issue_event_token("user-1", ["app.one", "app.>"]))` returns identity `"user-1"` and events `("app.one", "app.>")`; `jwt.decode` shows the required claims and a 3,600-second default lifetime. Test `"app.orders.*"`; reject empty, duplicate, malformed wildcard, whitespace, non-string, and 33-item lists. `test_rejects_wrong_audience_and_invalid_subjects` forges signed claims with a wrong `aud`, a scalar `events` claim, and an invalid subject; all raise `jwt.InvalidTokenError`. Reject missing or empty `sub`, malformed `jti`, and expired tokens.
- [ ] **Step 2: Run** `cd backend && uv run python manage.py test events.tests.test_subjects events.tests.test_tokens` **and confirm the new tests fail** because the modules do not yet exist.
- [ ] **Step 3: Implement `validate_events`** in `events/subjects.py`; `*` occupies one complete token and `>` only the final complete token, with at most 32 distinct subjects.
- [ ] **Step 4: Implement `issue_event_token` and `decode_event_token`** in `events/tokens.py` using the existing PyJWT dependency. Add `EVENTS_JWT_SIGNING_SECRET` and `EVENTS_JWT_TTL_SECONDS` to settings with test/check-only secret fallback matching existing settings behavior. Validate decoded claim types after PyJWT checks signature, audience, issuer, and required claims.
- [ ] **Step 5: Run** `cd backend && uv run python manage.py test events.tests.test_subjects events.tests.test_tokens && uv run python manage.py check` **and confirm all pass.**
- [ ] **Step 6: Commit only Task 1 files** with `feat: add scoped event websocket tokens`.

### Task 2: ASGI WebSocket and NATS Bridge

**Files:** Create `backend/events/frames.py`, `backend/events/broker.py`, `backend/events/consumers.py`, `backend/events/routing.py`, `backend/config/asgi.py`, `backend/events/tests/test_frames.py`, `backend/events/tests/test_broker.py`, `backend/events/tests/test_consumers.py`; modify `backend/config/settings.py`, `backend/pyproject.toml`, `backend/uv.lock`, `backend/Dockerfile`.

**Interfaces:** `pack_event(subject: str, headers: Mapping[str, str] | None, message: bytes) -> bytes` encodes the exact map with MessagePack bin type. `async NatsEventBridge.start(subjects: tuple[str, ...], on_message: Callable[[Msg], Awaitable[None]], on_closed: Callable[[], Awaitable[None]]) -> None` connects and subscribes; `async close() -> None` unsubscribes and closes idempotently. `EventsConsumer(AsyncWebsocketConsumer)` owns one bridge, validates `scope['url_route']['kwargs']['token']`, and rejects before `accept()` on any invalid setup.

- [ ] **Step 1: Write failing tests.** `test_binary_frame_preserves_payload` unpacks a frame and asserts exact keys, `event="app.one"`, `headers={}`, and `message=b"\x00\xff"`; another checks present headers. Fake NATS tests assert two subjects create two subscriptions and `close()` releases both. `test_partial_subscription_failure_cleans_up` injects a failure on subscription two. Channels `WebsocketCommunicator` tests cover valid token and two subjects, invalid token without `nats.connect`, `test_origin_policy`, expiry close code `1008`, disconnect cleanup, and permanent broker failure close code `1011`.
- [ ] **Step 2: Add compatible dependencies** `channels>=4.3,<5`, `nats-py>=2.15,<3`, `msgpack>=1.2,<2`, `uvicorn[standard]>=0.35,<1`, `uvicorn-worker>=0.4,<1` to `backend/pyproject.toml`, plus `daphne>=4.2,<5` in a dev dependency group because `channels.testing` imports Daphne. Run `cd backend && uv lock`; then run `uv run python manage.py test events.tests.test_frames events.tests.test_broker events.tests.test_consumers` and confirm the tests fail against missing behavior.
- [ ] **Step 3: Implement `pack_event`** in `events/frames.py` with `msgpack.packb(..., use_bin_type=True)`; run `cd backend && uv run python manage.py test events.tests.test_frames` and confirm it passes.
- [ ] **Step 4: Implement `NatsEventBridge`** in `events/broker.py`; connect with `NATS_URL`, `NATS_BACKEND_USER`, and `NATS_BACKEND_PASSWORD`, subscribe and flush before returning, and clean partial state. Run `cd backend && uv run python manage.py test events.tests.test_broker` and confirm it passes.
- [ ] **Step 5: Implement ASGI routing and `EventsConsumer`.** Add `channels` and `events` to `INSTALLED_APPS`, set `ASGI_APPLICATION="config.asgi.application"`, and parse `EVENTS_ALLOWED_ORIGINS`. Use `ProtocolTypeRouter` for existing Django HTTP and `URLRouter` for `path("ws/events/<str:token>", ...)`. In `connect`, check Origin when present, decode token, start the bridge, then accept. On broker close, close with `1011`; on token expiry, close with `1008`. Cancel timer and close bridge on all exits. Never log the token or full path. Run `cd backend && uv run python manage.py test events.tests.test_consumers` and confirm it passes.
- [ ] **Step 6: Switch the container** to `gunicorn config.asgi:application --bind 0.0.0.0:8000 -k uvicorn_worker.UvicornWorker`. Keep the existing WSGI module available for tooling.
- [ ] **Step 7: Run** `cd backend && uv run python manage.py test events && uv run python manage.py check && uv run python manage.py makemigrations --check` **and confirm all pass.**
- [ ] **Step 8: Commit only Task 2 files** with `feat: relay private NATS events through ASGI`.

### Task 3: Private Broker and Local Routing

**Files:** Modify `backend/config/settings.py`, `backend/config/urls.py`, `.env.example`, `infra/nats/nats.conf`, `infra/compose.yaml`, `infra/nginx/conf.d/default.conf`, `infra/nginx/conf.d/flutter-web.conf`, `infra/scripts/generate-local-env.sh`, `infra/scripts/tests/test-generate-local-env.sh`, `infra/scripts/tests/test-compose-environment-scope.sh`, `infra/scripts/validate-config.sh`; create `backend/events/tests/test_removed_routes.py`, `infra/scripts/tests/test-private-routing.sh`; delete `backend/nats_auth/`.

**Interfaces:** The broker and backend alone receive `NATS_BACKEND_USER` and `NATS_BACKEND_PASSWORD`; only the backend receives `EVENTS_JWT_SIGNING_SECRET`. Backend environment keys are `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `WAGTAIL_SITE_NAME`, `WAGTAILADMIN_BASE_URL`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`, `NATS_URL`, `NATS_BACKEND_USER`, `NATS_BACKEND_PASSWORD`, `EVENTS_JWT_SIGNING_SECRET`, `EVENTS_JWT_TTL_SECONDS`, and `EVENTS_ALLOWED_ORIGINS`. Backend `NATS_URL` is `nats://nats:4222`. The example environment includes `EVENTS_JWT_TTL_SECONDS=3600`, `EVENTS_ALLOWED_ORIGINS=http://localhost:8081,http://app.localhost:8081`, and `VITE_EVENTS_WEBSOCKET_URL=/ws/events/`. NATS user permissions allow publish and subscribe only to `app.>`.

- [ ] **Step 1: Update configuration regression checks first.** In `test-compose-environment-scope.sh`, assert the exact backend keys, no `nats-auth-redirect` service, no NATS `ports`, and no NATS credential in `web`. Add `test-private-routing.sh` to assert the NATS WebSocket stanza is absent, broker publish/subscribe allow lists are `app.>`, and, for both Nginx files, `/ws/events/` routes to `backend:8000`, includes WebSocket upgrade headers, and sets `access_log off` (`test_ws_route_has_no_access_log`). In `test-generate-local-env.sh`, assert new secret keys and idempotence, rejection of weak/duplicate values, mode `0600`, symlink refusal, and no secret output. Add `test_removed_routes.py` asserting `/api/nats/token/` and `/api/nats/authorize/` return 404.
- [ ] **Step 2: Run** `bash infra/scripts/tests/test-compose-environment-scope.sh`, `bash infra/scripts/tests/test-private-routing.sh`, and `bash infra/scripts/tests/test-generate-local-env.sh` **and confirm failure against the old configuration.**
- [ ] **Step 3: Configure the private broker and Compose graph.** Use one password-authenticated NATS user with `app.>` publish/subscribe permissions, retain internal native/monitoring listeners, remove the NATS WebSocket stanza and published ports, remove redirector, and inject only the new backend settings.
- [ ] **Step 4: Change Nginx routing.** Add `/ws/events/` locations for both hosts and Flutter Web with proxy upgrade, long read timeout, and `access_log off`; remove `/nats/` locations. Preserve `/api/`, `/health/`, Wagtail, static, and frontend routes.
- [ ] **Step 5: Remove the old HTTP auth flow.** Delete `backend/nats_auth/` and its URL inclusion and settings; run `cd backend && uv run python manage.py test events.tests.test_removed_routes` and confirm both routes return 404.
- [ ] **Step 6: Replace local secret generation.** Generate separate 32-byte-or-longer Django, events JWT, PostgreSQL, and NATS password secrets; do not generate NKeys. An existing old-format `.env` fails with a clear missing-key message and stays untouched; docs will explain regeneration. Update `.env.example` and the NATS/Nginx config validator. Make `STACK_ENV_FILE` override the default root `.env` in `validate-config.sh`, so validation can use a temporary generated env without modifying a user's file.
- [ ] **Step 7: Run** `bash infra/scripts/tests/test-compose-environment-scope.sh && bash infra/scripts/tests/test-private-routing.sh && bash infra/scripts/tests/test-generate-local-env.sh && bash infra/scripts/validate-config.sh && cd backend && uv run python manage.py test && uv run python manage.py check` **and confirm all pass.** Set `STACK_ENV_FILE` to a temporary generated env if the local `.env` is still in the old format; do not overwrite it.
- [ ] **Step 8: Commit only Task 3 files** with `refactor: keep NATS private behind Django`.

### Task 4: Full-Stack Event Smoke Test

**Files:** Modify `infra/scripts/smoke-stack.sh`, `infra/compose.yaml`; remove the now-unused `nats-smoke` Compose profile. The existing Flutter Web wrapper continues to call `smoke-stack.sh`.

**Interfaces:** Smoke code obtains a token by calling `events.tokens.issue_event_token("smoke", ["app.smoke"])` inside the backend container. It never prints or passes the JWT as a command argument. The probe uses a WebSocket client inside the backend container to reach Nginx, publishes through internal NATS, and decodes the binary frame with `msgpack.unpackb(raw=False)`.

- [ ] **Step 1: Replace the old direct-NATS smoke assertions.** Retain the website, admin, static, health, React, and Flutter Web checks. Add assertions that `/ws/events/<valid-token>` upgrades through Nginx, receives `{"event":"app.smoke","headers":{"probe":"yes"},"message":b"\x00smoke"}`, and a malformed token is rejected. Check that `nats` has no host port binding in resolved Compose config.
- [ ] **Step 2: Run** `bash infra/scripts/smoke-stack.sh` with a generated temporary env **and confirm the new probe fails** before its implementation is complete.
- [ ] **Step 3: Implement the probe** using a Python heredoc executed inside `backend`; its installed `websockets`, `nats-py`, and `msgpack` packages avoid a new smoke image. Establish the socket before publishing and use bounded timeouts. Remove the obsolete `nats-smoke` service. Make `STACK_ENV_FILE` override the default root `.env` in `smoke-stack.sh`; the Flutter Web wrapper inherits it. Keep the existing cleanup behavior for cold and warm Compose runs, and never print token-bearing URLs.
- [ ] **Step 4: Run** `bash infra/scripts/smoke-stack.sh` and `bash infra/scripts/smoke-flutter-web.sh` **and confirm both pass.** If Docker is unavailable, report that exact limitation and run the configuration and component checks that do not require it.
- [ ] **Step 5: Commit only Task 4 files** with `test: smoke private event websocket`.

### Task 5: Client Boundaries and Current Documentation

**Files:** Modify `web/src/config/runtime.ts`, `web/src/vite-env.d.ts`, `web/src/App.test.tsx`, `app/lib/config/runtime_config.dart`, `README.md`, `docs/architecture/local-stack.md`; create `web/src/lib/events.ts`, `app/lib/integrations/events.dart`, `docs/integrations/events-websocket.md`, `AGENTS.md`; delete `web/src/lib/nats.ts`, `web/src/lib/auth.ts`, `app/lib/integrations/nats.dart`, `app/lib/integrations/auth.dart`, `docs/integrations/nats-authentication.md`, `docs/integrations/nats-auth-redirect.md`.

**Interfaces:** React `runtimeConfig.eventsWebsocketUrl` reads `VITE_EVENTS_WEBSOCKET_URL` with default `/ws/events/`; Flutter `RuntimeConfig.eventsWebSocketUrl` reads `EVENTS_WEBSOCKET_URL` with the same default. TypeScript `EventConnector.connect(token: string): Promise<EventConnection>` and `EventConnection.close(): Promise<void>` mirror Dart `Future<EventConnection> connect(String token)` and `Future<void> close()`. No implementation or UI connection is added.

- [ ] **Step 1: Update the existing React runtime test** to require `eventsWebsocketUrl="/ws/events/"` and no `natsWebsocketUrl`; run `cd web && npm test -- --run` and confirm it fails before the config change.
- [ ] **Step 2: Replace client stubs and settings.** Keep the current proof-of-life screens. Do not add MessagePack libraries to frontends until a derived project implements decoding. Preserve unrelated user edits in Flutter files.
- [ ] **Step 3: Rewrite current documentation.** Describe the private broker, `issue_event_token(identity, events)`, token path, expiry and origin rules, exact MessagePack map, local setup, smoke commands, and extension points. Explain that URL-bearing tokens need redacted upstream logs and `wss://` in deployment. Document how to regenerate an old-format local `.env` without overwriting it. Add root `AGENTS.md` with the repository map, validation commands, private-NATS/ASGI boundaries, protection of user changes, and the blocking-question rule. Remove obsolete active NATS auth docs; leave `docs/superpowers/` history intact.
- [ ] **Step 4: Run** `cd web && npm test -- --run && npm run lint && npm run build`; then `cd app && dart format --output=none --set-exit-if-changed . && flutter analyze && flutter test && flutter build web`. Check old direct-client terms only in historical artifacts with `rg -n 'nats-auth-redirect|/nats/|NATS_JWT_' README.md backend web/src app/lib infra docs/architecture docs/integrations AGENTS.md` and expect no matches. Run `git diff --check`.
- [ ] **Step 5: Commit only Task 5 files** with `docs: explain private event websocket template`.

## Final Verification

- [ ] Run `cd backend && uv sync --locked && uv run python manage.py test && uv run python manage.py check && uv run python manage.py makemigrations --check`.
- [ ] Run `bash infra/scripts/tests/test-compose-environment-scope.sh`, `bash infra/scripts/tests/test-private-routing.sh`, `bash infra/scripts/tests/test-generate-local-env.sh`, and `bash infra/scripts/validate-config.sh`.
- [ ] Run both smoke scripts if Docker is available; record exactly which pass or why they could not run.
- [ ] Run React and Flutter checks from Task 5; inspect `git diff --check`, `git status --short`, and confirm the two pre-existing Flutter edits were neither overwritten nor staged.
- [ ] Re-read the spec against the final diff, including token secrecy, no public NATS transport, expiry cleanup, AGENTS.md, and the MessagePack wire shape. Use superpowers:verification-before-completion and superpowers:requesting-code-review before claiming completion.
