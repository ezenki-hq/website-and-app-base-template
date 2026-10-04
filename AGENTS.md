# Project instructions

## Repository map

- `backend/`: Django 5.2, Wagtail, ASGI, Channels, event JWTs, and NATS bridge.
- `backend/events/`: subject validation, internal token issuer/decoder,
  MessagePack frames, WebSocket consumer, and tests.
- `web/`: React and TypeScript application; `web/src/lib/events.ts` is an
  interface boundary only.
- `app/`: Flutter application; `app/lib/integrations/events.dart` is an
  interface boundary only.
- `infra/`: private NATS, Compose, Nginx routes, local environment generation,
  config checks, and full-stack smoke scripts.
- `docs/`: current architecture and event WebSocket integration contracts.
- `docs/superpowers/`: historical design and implementation planning records.

## Validation commands

Backend:

```bash
cd backend
uv sync --locked
uv run python manage.py test
uv run python manage.py check
uv run python manage.py makemigrations --check
```

React:

```bash
cd web
npm test -- --run
npm run lint
npm run build
```

Flutter:

```bash
cd app
dart format --output=none --set-exit-if-changed .
flutter analyze
flutter test
flutter build web
```

Local infrastructure:

```bash
bash infra/scripts/tests/test-compose-environment-scope.sh
bash infra/scripts/tests/test-private-routing.sh
bash infra/scripts/tests/test-generate-local-env.sh
STACK_ENV_FILE="$PWD/.env" bash infra/scripts/validate-config.sh
STACK_ENV_FILE="$PWD/.env" bash infra/scripts/smoke-stack.sh
STACK_ENV_FILE="$PWD/.env" bash infra/scripts/smoke-flutter-web.sh
```

## Architecture boundaries

- Django ASGI serves `/ws/events/{jwt}`. Validate the JWT before connecting to
  NATS. Only server-side code should call `events.tokens.issue_event_token`
  after authorizing every requested subject.
- NATS is private to the Compose network. Do not publish its ports, add a NATS
  WebSocket listener, or send NATS credentials to React, Flutter, or browsers.
- The WebSocket sends binary MessagePack maps with exactly `event`, `headers`,
  and `message`. Keep application event schemas and frontend connection
  behavior in derived projects.
- The JWT is in the URL path. Keep it out of application logs and configure
  deployment proxy, CDN, and tracing logs to redact the path. Use `wss://`
  with TLS outside local development.
- `EVENTS_ALLOWED_ORIGINS` contains exact full browser origins. Missing Origin
  is permitted for native clients only when the JWT is valid.

## Working tree care

- Inspect `git status --short` before editing and before committing.
- Preserve pre-existing user changes, including Flutter analysis or lockfile
  edits. Stage only files belonging to the requested change.
- Do not replace a user's `.env`; the generator refuses existing invalid files.
  Preserve old local credentials before creating a new-format environment.
- Keep generated secrets, tokens, and token-bearing URLs out of command output,
  logs, commits, and documentation examples.

## User questions

Whenever you ask the user a question, stop work immediately. Do not continue
investigating, run commands, edit files, make assumptions, or work on unrelated
parts of the task. Wait for the user's response before continuing.
