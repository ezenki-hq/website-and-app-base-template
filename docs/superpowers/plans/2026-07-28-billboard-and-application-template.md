# Billboard Website and Application Template Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable Django/Wagtail, React, Flutter, NATS auth-callout, Nginx, PostgreSQL, and Docker Compose project template that starts locally and proves its integration boundaries.

**Architecture:** A single Compose project in `infra/compose.yaml` runs PostgreSQL, Django/Wagtail, React/Vite, NATS, the unchanged auth redirector, and Nginx. Nginx serves Django at `localhost`, React at `app.localhost`, Django API routes on both application origins, and NATS WebSockets at `/nats/`; a Compose override substitutes Flutter Web for React. Django anonymously issues development JWTs whose signed `nats` claim is converted into the redirector's exact authorization response.

**Tech Stack:** Python 3.13, uv, Django 5.2 LTS, Wagtail 7.4 LTS, PostgreSQL 18, PyJWT, Gunicorn, Node 24, npm, Vite 8, React 19, TypeScript, Flutter stable, NATS Server 2.14, `ezenki/nats-auth-redirector:1.0.0`, Nginx, Docker Compose.

## Global Constraints

- Treat `docs/integrations/nats-auth-redirect.md` as the authoritative redirect contract; do not modify or reimplement the redirector.
- Use `ezenki/nats-auth-redirector:1.0.0` exactly.
- Use Django 5.2 LTS and Wagtail 7.4 LTS on Python 3.13.
- Use plain Django views; do not add Django REST Framework.
- Use Vite, React, TypeScript, and npm without a router, state library, or UI framework.
- Keep React and Flutter integration libraries typed but deliberately unimplemented and unused.
- Do not require Android, iOS, an emulator, or a host Docker socket.
- Keep JetStream disabled.
- Use fixed local hosts `localhost` and `app.localhost`; production uses separate Nginx configuration.
- Default JWT expiry is `86400` seconds; use HS256 and a dedicated signing secret.
- Default NATS account is `APP`; default publish and subscribe allowlists are `["app.>"]`.
- Accept authorization JWTs through Bearer or the `auth` cookie; reject conflicting values.
- Do not add business features, Kubernetes, CI/CD, cloud configuration, or production deployment automation.
- Never commit generated credentials or print JWTs, passwords, or signer seeds in test output.

---

## File Map

### Root

- `.gitignore`: generated secrets, dependency caches, build products, databases, editor files.
- `.env.example`: documented non-secret local configuration contract.
- `README.md`: complete operator and extension guide.

### Backend

- `backend/pyproject.toml`, `backend/uv.lock`: Python metadata and locked dependencies.
- `backend/Dockerfile`, `backend/entrypoint.sh`: local container image and migration/start command.
- `backend/manage.py`: Django command entry point.
- `backend/config/settings.py`: environment parsing and Django/Wagtail settings.
- `backend/config/urls.py`: Wagtail, admin, health, and API route composition.
- `backend/config/wsgi.py`: Gunicorn entry point.
- `backend/home/models.py`, `backend/home/templates/home/home_page.html`: minimal Wagtail page.
- `backend/home/migrations/0001_initial.py`: `HomePage` schema.
- `backend/home/migrations/0002_create_homepage.py`: idempotent initial site/page data migration.
- `backend/health/views.py`, `backend/health/urls.py`: database-aware container health contract.
- `backend/nats_auth/config.py`: typed environment permission policy.
- `backend/nats_auth/tokens.py`: JWT issue/validate functions.
- `backend/nats_auth/views.py`, `backend/nats_auth/urls.py`: token and authorize HTTP contracts.
- `backend/home/tests/`, `backend/health/tests/`, `backend/nats_auth/tests/`: focused Django tests.

### React

- `web/package.json`, `web/package-lock.json`: npm dependency contract.
- `web/vite.config.ts`, `web/tsconfig*.json`, `web/eslint.config.js`: build and validation.
- `web/Dockerfile`: Vite development service.
- `web/src/config/runtime.ts`: API and WebSocket paths.
- `web/src/lib/auth.ts`, `web/src/lib/nats.ts`: unimplemented typed boundaries.
- `web/src/App.tsx`, `web/src/main.tsx`, `web/src/index.css`: minimal proof-of-life UI.
- `web/src/App.test.tsx`: render smoke test.

### Flutter

- `app/pubspec.yaml`, `app/pubspec.lock`, `app/analysis_options.yaml`: Dart dependency and analysis contract.
- `app/android/`, `app/ios/`, `app/web/`: generated host projects for future mobile and web development.
- `app/Dockerfile.web`: Flutter Web example service.
- `app/lib/config/runtime_config.dart`: `--dart-define` runtime values.
- `app/lib/integrations/auth.dart`, `app/lib/integrations/nats.dart`: abstract unimplemented boundaries.
- `app/lib/main.dart`: minimal proof-of-life application.
- `app/test/widget_test.dart`: widget smoke test.

### Infrastructure

- `infra/compose.yaml`: default React-based stack.
- `infra/compose.flutter-web.yaml`: Flutter Web replacement override.
- `infra/nginx/nginx.conf`: process-level Nginx settings.
- `infra/nginx/conf.d/default.conf`: default host routing.
- `infra/nginx/conf.d/flutter-web.conf`: Flutter Web example routing.
- `infra/nats/nats.conf`: accounts, auth callout, native listener, WebSocket listener, monitoring.
- `infra/scripts/generate-local-env.sh`: idempotent local credential generation.
- `infra/scripts/validate-config.sh`: Compose, NATS, and Nginx configuration checks.
- `infra/scripts/smoke-stack.sh`: host routing and end-to-end NATS authentication checks.
- `infra/scripts/smoke-flutter-web.sh`: Flutter Web override check.

### Documentation

- `docs/architecture/local-stack.md`: topology, routing, ports, trust boundaries.
- `docs/integrations/nats-authentication.md`: Django JWT and redirector flow.

---

### Task 1: Repository Hygiene and Local Secret Contract

**Files:**
- Create: `.gitignore`
- Create: `.env.example`
- Create: `infra/scripts/generate-local-env.sh`
- Create: `infra/scripts/tests/test-generate-local-env.sh`

**Interfaces:**
- Consumes: Docker from the inner Dev Container daemon.
- Produces: ignored `.env` with `NATS_ACCOUNT_SIGNER_SEED`, `NATS_ACCOUNT_SIGNER_PUBLIC_KEY`, redirect credentials, Django secrets, PostgreSQL credentials, and permission settings.

- [ ] **Step 1: Write a failing black-box secret-generation test**

```bash
#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
test_dir="$(mktemp -d)"
trap 'rm -rf "${test_dir}"' EXIT

LOCAL_ENV_FILE="${test_dir}/.env" \
  "${repo_root}/infra/scripts/generate-local-env.sh"

test -s "${test_dir}/.env"
before="$(sha256sum "${test_dir}/.env")"
LOCAL_ENV_FILE="${test_dir}/.env" \
  "${repo_root}/infra/scripts/generate-local-env.sh"
after="$(sha256sum "${test_dir}/.env")"
test "${before}" = "${after}"
grep -Eq '^DJANGO_SECRET_KEY=.{32,}$' "${test_dir}/.env"
grep -Eq '^NATS_JWT_SIGNING_SECRET=.{32,}$' "${test_dir}/.env"
grep -Eq '^NATS_ACCOUNT_SIGNER_SEED=SA[A-Z0-9]+$' "${test_dir}/.env"
grep -Eq '^NATS_ACCOUNT_SIGNER_PUBLIC_KEY=A[A-Z0-9]+$' "${test_dir}/.env"
test "$(grep -c '^NATS_ACCOUNT_SIGNER_SEED=' "${test_dir}/.env")" -eq 1
```

- [ ] **Step 2: Run the test and verify the generator is missing**

Run: `bash infra/scripts/tests/test-generate-local-env.sh`

Expected: FAIL because `infra/scripts/generate-local-env.sh` does not exist.

- [ ] **Step 3: Add ignore rules and the explicit example environment**

Create `.gitignore` with `.env`, Python/Node/Flutter caches, coverage, build
directories, SQLite files, and generated NATS material. Create `.env.example`
with these exact keys:

```dotenv
DJANGO_SECRET_KEY=
DJANGO_DEBUG=true
DJANGO_ALLOWED_HOSTS=localhost,app.localhost,backend
POSTGRES_DB=app
POSTGRES_USER=app
POSTGRES_PASSWORD=
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
NATS_JWT_SIGNING_SECRET=
NATS_JWT_ISSUER=website-app-template
NATS_JWT_AUDIENCE=nats
NATS_JWT_TTL_SECONDS=86400
NATS_JWT_SUBJECT=development-user
NATS_ACCOUNT=APP
NATS_PUBLISH_ALLOW=["app.>"]
NATS_PUBLISH_DENY=[]
NATS_SUBSCRIBE_ALLOW=["app.>"]
NATS_SUBSCRIBE_DENY=[]
NATS_AUTH_USER=auth
NATS_AUTH_PASSWORD=
NATS_ACCOUNT_SIGNER_SEED=
NATS_ACCOUNT_SIGNER_PUBLIC_KEY=
VITE_API_BASE_URL=/api/
VITE_NATS_WEBSOCKET_URL=/nats/
```

- [ ] **Step 4: Implement idempotent local generation**

Implement a strict Bash script that validates an existing environment file and
exits successfully without changing it. When the file is absent, use
`openssl rand -hex 32` for ordinary secrets and run:

```bash
docker run --rm natsio/nats-box:0.19.2 nsc generate nkey --account
```

The verified command emits exactly two non-empty lines: an account seed
beginning with `SA`, then its public key beginning with `A`. Accept only that
shape and fail closed otherwise. Write through a temporary file and atomically
rename it to `LOCAL_ENV_FILE` (default `<repo>/.env`).

- [ ] **Step 5: Run the generator test twice**

Run: `bash infra/scripts/tests/test-generate-local-env.sh`

Expected: PASS, including the single-definition/idempotency assertions.

- [ ] **Step 6: Verify secrets are ignored**

Run: `git check-ignore .env`

Expected: `.env`

- [ ] **Step 7: Commit**

```bash
git add .gitignore .env.example infra/scripts/generate-local-env.sh infra/scripts/tests/test-generate-local-env.sh
git commit -m "chore: define local development secrets"
```

---

### Task 2: Django/Wagtail Scaffold and Initial Home Page

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/uv.lock`
- Create: `backend/Dockerfile`
- Create: `backend/entrypoint.sh`
- Create: `backend/manage.py`
- Create: `backend/config/__init__.py`
- Create: `backend/config/settings.py`
- Create: `backend/config/urls.py`
- Create: `backend/config/wsgi.py`
- Create: `backend/home/__init__.py`
- Create: `backend/home/apps.py`
- Create: `backend/home/models.py`
- Create: `backend/home/templates/home/home_page.html`
- Create: `backend/home/migrations/__init__.py`
- Create: `backend/home/migrations/0001_initial.py`
- Create: `backend/home/migrations/0002_create_homepage.py`
- Create: `backend/home/tests/test_homepage.py`

**Interfaces:**
- Consumes: PostgreSQL environment keys from Task 1.
- Produces: `config.wsgi:application`, `home.HomePage`, and an idempotently created root page/default site.

- [ ] **Step 1: Create dependency metadata and lock it**

Use these bounded dependencies:

```toml
[project]
name = "website-app-template-backend"
version = "0.1.0"
requires-python = ">=3.13,<3.14"
dependencies = [
  "Django>=5.2,<5.3",
  "wagtail>=7.4,<7.5",
  "psycopg[binary]>=3.2,<4",
  "gunicorn>=23,<24",
  "PyJWT>=2.10,<3",
]
```

Run: `cd backend && uv lock && uv sync`

Expected: dependency resolution succeeds on Python 3.13.

- [ ] **Step 2: Write failing home-page and migration tests**

```python
class HomePageTests(TestCase):
    def test_default_site_uses_home_page(self):
        site = Site.objects.get(is_default_site=True)
        self.assertIsInstance(site.root_page.specific, HomePage)

    def test_home_page_renders(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Billboard website")
```

- [ ] **Step 3: Run the focused test and verify failure**

Run: `cd backend && uv run python manage.py test home.tests.test_homepage -v 2`

Expected: FAIL because the project and `HomePage` do not exist yet.

- [ ] **Step 4: Create the minimal Wagtail project**

Configure standard Django and Wagtail applications, middleware, templates,
static/media paths, PostgreSQL settings from individual environment values,
`ALLOWED_HOSTS`, and `WAGTAIL_SITE_NAME`. Define:

```python
class HomePage(Page):
    max_count = 1

    content_panels = Page.content_panels
```

Route Django admin, Wagtail admin/documents, then Wagtail pages. Use a small
semantic HTML template with no business content.

- [ ] **Step 5: Add idempotent page/site data migration**

The forward migration must:

```python
root = Page.objects.get(depth=1)
home = HomePage.objects.filter(slug="home").first()
if home is None:
    home = HomePage(title="Home", slug="home")
    root.add_child(instance=home)
Site.objects.update_or_create(
    is_default_site=True,
    defaults={"hostname": "localhost", "port": 80, "root_page": home},
)
```

Use historical models from `apps.get_model`, not runtime imports.

- [ ] **Step 6: Add container startup**

`backend/entrypoint.sh` must run migrations and then `exec` its arguments.
`backend/Dockerfile` must install from `uv.lock`, copy the project, use a
non-root runtime user, and default to:

```text
gunicorn config.wsgi:application --bind 0.0.0.0:8000
```

- [ ] **Step 7: Run tests and Django integrity checks**

Run:

```bash
cd backend
uv run python manage.py test home -v 2
uv run python manage.py check
uv run python manage.py makemigrations --check
```

Expected: all pass and no model changes are pending.

- [ ] **Step 8: Commit**

```bash
git add backend
git commit -m "feat: scaffold Django and Wagtail website"
```

---

### Task 3: Database-Aware Health Endpoint

**Files:**
- Create: `backend/health/__init__.py`
- Create: `backend/health/apps.py`
- Create: `backend/health/views.py`
- Create: `backend/health/urls.py`
- Create: `backend/health/tests/test_health.py`
- Modify: `backend/config/settings.py`
- Modify: `backend/config/urls.py`

**Interfaces:**
- Consumes: Django database connection.
- Produces: `GET /health/` returning `{"status":"ok"}` with 200 or `{"status":"unavailable"}` with 503.

- [ ] **Step 1: Write failing success and database-failure tests**

```python
def test_health_reports_ready(self):
    response = self.client.get("/health/")
    self.assertEqual(response.status_code, 200)
    self.assertJSONEqual(response.content, {"status": "ok"})

@mock.patch("health.views.connection.cursor", side_effect=DatabaseError)
def test_health_reports_database_failure(self, _cursor):
    response = self.client.get("/health/")
    self.assertEqual(response.status_code, 503)
    self.assertJSONEqual(response.content, {"status": "unavailable"})
```

- [ ] **Step 2: Verify the tests fail with a missing route**

Run: `cd backend && uv run python manage.py test health -v 2`

Expected: FAIL with 404 responses.

- [ ] **Step 3: Implement the minimal view**

```python
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})
```

Expose it at exactly `/health/`.

- [ ] **Step 4: Run the health tests**

Run: `cd backend && uv run python manage.py test health -v 2`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/health backend/config/settings.py backend/config/urls.py
git commit -m "feat: add backend readiness endpoint"
```

---

### Task 4: Development JWT Issuance and Authorization

**Files:**
- Create: `backend/nats_auth/__init__.py`
- Create: `backend/nats_auth/apps.py`
- Create: `backend/nats_auth/config.py`
- Create: `backend/nats_auth/tokens.py`
- Create: `backend/nats_auth/views.py`
- Create: `backend/nats_auth/urls.py`
- Create: `backend/nats_auth/tests/test_config.py`
- Create: `backend/nats_auth/tests/test_tokens.py`
- Create: `backend/nats_auth/tests/test_views.py`
- Modify: `backend/config/settings.py`
- Modify: `backend/config/urls.py`

**Interfaces:**
- Consumes: `NATS_JWT_*`, `NATS_ACCOUNT`, and four JSON permission-list environment values.
- Produces: `issue_token(scope: NatsScope) -> tuple[str, datetime]`, `decode_token(encoded: str) -> NatsScope`, `GET /api/nats/token/`, and `GET /api/nats/authorize/`.

- [ ] **Step 1: Write failing configuration tests**

Cover valid JSON arrays, empty arrays, malformed JSON, non-string members, and
defaults. The expected value object is:

```python
@dataclass(frozen=True)
class PermissionSet:
    allow: tuple[str, ...]
    deny: tuple[str, ...]

@dataclass(frozen=True)
class NatsScope:
    account: str
    pub: PermissionSet
    sub: PermissionSet
```

- [ ] **Step 2: Run and verify configuration tests fail**

Run: `cd backend && uv run python manage.py test nats_auth.tests.test_config -v 2`

Expected: FAIL because `nats_auth.config` does not exist.

- [ ] **Step 3: Implement strict environment parsing**

Implement `parse_subjects(raw: str, setting_name: str) -> tuple[str, ...]` with
`json.loads`, require a list of non-empty strings, and raise
`ImproperlyConfigured` for all invalid inputs. Implement
`scope_from_settings() -> NatsScope`.

- [ ] **Step 4: Write failing JWT tests**

Tests must freeze or patch time and assert HS256, `sub`, `iss`, `aud`, `iat`,
`exp`, `jti`, the namespaced `nats` claim, default 86,400-second lifetime,
configured lifetime, wrong signature, expiry, issuer, audience, missing claims,
and malformed scope.

- [ ] **Step 5: Implement JWT issue and validation**

Use one explicit algorithm constant:

```python
ALGORITHM = "HS256"

def issue_token(scope: NatsScope) -> tuple[str, datetime]:
    now = datetime.now(tz=UTC)
    expires_at = now + timedelta(seconds=settings.NATS_JWT_TTL_SECONDS)
    payload = {
        "sub": settings.NATS_JWT_SUBJECT,
        "iss": settings.NATS_JWT_ISSUER,
        "aud": settings.NATS_JWT_AUDIENCE,
        "iat": now,
        "exp": expires_at,
        "jti": str(uuid.uuid4()),
        "nats": scope_to_claim(scope),
    }
    return jwt.encode(payload, settings.NATS_JWT_SIGNING_SECRET, algorithm=ALGORITHM), expires_at
```

Decode with the same algorithm list, required claims, issuer, and audience.
Convert the claim back into `NatsScope`; never return unchecked dictionaries.

- [ ] **Step 6: Write failing HTTP contract tests**

Cover:

- `GET /api/nats/token/` exact keys and no accepted permission inputs;
- valid Bearer;
- valid `auth` cookie;
- equal Bearer and cookie;
- conflicting Bearer and cookie;
- missing credentials;
- malformed scheme;
- invalid/expired JWT;
- exact successful `account`/`pub`/`sub` response; and
- generic 401 JSON failures that never contain a token.

- [ ] **Step 7: Implement plain Django views**

Token response:

```python
return JsonResponse({
    "token": encoded,
    "token_type": "Bearer",
    "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
})
```

Credential extraction must compare header and cookie before decoding. The
authorization response must serialize tuples as lists and match the redirect
contract exactly. Catch expected JWT/configuration errors and return
`{"error":"invalid credentials"}` with 401.

- [ ] **Step 8: Run focused and full backend tests**

Run:

```bash
cd backend
uv run python manage.py test nats_auth -v 2
uv run python manage.py test -v 2
uv run python manage.py check
uv run python manage.py makemigrations --check
```

Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add backend/nats_auth backend/config/settings.py backend/config/urls.py backend/pyproject.toml backend/uv.lock
git commit -m "feat: add development NATS JWT authorization"
```

---

### Task 5: Minimal React Application and Typed Boundaries

**Files:**
- Create: `web/package.json`
- Create: `web/package-lock.json`
- Create: `web/index.html`
- Create: `web/vite.config.ts`
- Create: `web/tsconfig.json`
- Create: `web/tsconfig.app.json`
- Create: `web/tsconfig.node.json`
- Create: `web/eslint.config.js`
- Create: `web/Dockerfile`
- Create: `web/src/vite-env.d.ts`
- Create: `web/src/config/runtime.ts`
- Create: `web/src/lib/auth.ts`
- Create: `web/src/lib/nats.ts`
- Create: `web/src/App.tsx`
- Create: `web/src/App.test.tsx`
- Create: `web/src/main.tsx`
- Create: `web/src/index.css`

**Interfaces:**
- Consumes: `VITE_API_BASE_URL` and `VITE_NATS_WEBSOCKET_URL`.
- Produces: `RuntimeConfig`, `AuthTokenProvider`, and `NatsConnection` TypeScript contracts; Vite service on port 5173.

- [ ] **Step 1: Scaffold Vite React TypeScript and install test dependencies**

Use Vite 8/React 19 compatible current releases, commit the npm lock file, and
add Vitest, jsdom, and Testing Library only for the render smoke test.

- [ ] **Step 2: Write failing runtime and render tests**

```tsx
it("renders the empty application marker", () => {
  render(<App />);
  expect(screen.getByRole("heading", { name: "Application" })).toBeVisible();
});
```

Also assert runtime defaults are `/api/` and `/nats/`.

- [ ] **Step 3: Run and verify tests fail**

Run: `cd web && npm test -- --run`

Expected: FAIL until the config and minimal component exist.

- [ ] **Step 4: Add configuration and unimplemented interfaces**

```ts
export interface AuthToken {
  token: string;
  tokenType: "Bearer";
  expiresAt: string;
}

export interface AuthTokenProvider {
  getToken(): Promise<AuthToken>;
}

export interface NatsConnection {
  close(): Promise<void>;
}

export interface NatsConnector {
  connect(token: string): Promise<NatsConnection>;
}
```

Do not add concrete classes, fetch calls, NATS packages, or imports from the
main component.

- [ ] **Step 5: Implement the proof-of-life component**

Render one `<main>` with an `Application` heading and short template message.
Keep CSS small, accessible, and business-neutral.

- [ ] **Step 6: Add the development container**

Use Node 24, `npm ci`, a non-root user, and:

```text
npm run dev -- --host 0.0.0.0
```

- [ ] **Step 7: Run all React checks**

Run:

```bash
cd web
npm test -- --run
npm run lint
npm run build
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add web
git commit -m "feat: scaffold empty React application"
```

---

### Task 6: Minimal Flutter Application and Typed Boundaries

**Files:**
- Create: `app/pubspec.yaml`
- Create: `app/pubspec.lock`
- Create: `app/analysis_options.yaml`
- Create: `app/android/**`
- Create: `app/ios/**`
- Create: `app/web/index.html`
- Create: `app/web/manifest.json`
- Create: `app/Dockerfile.web`
- Create: `app/lib/config/runtime_config.dart`
- Create: `app/lib/integrations/auth.dart`
- Create: `app/lib/integrations/nats.dart`
- Create: `app/lib/main.dart`
- Create: `app/test/widget_test.dart`

**Interfaces:**
- Consumes: `API_BASE_URL` and `NATS_WEBSOCKET_URL` through `--dart-define`.
- Produces: `RuntimeConfig`, `AuthTokenProvider`, `NatsConnector`, and `NatsConnection` abstract Dart contracts; optional Flutter Web service on port 8080.

- [ ] **Step 1: Scaffold Flutter without platform SDK assumptions**

Run: `flutter create --platforms=android,ios,web --project-name app app`

Then remove generated counter behavior. Keep the generated Android, iOS, and
web host projects so the template is ready for future mobile development, but
do not build or run Android/iOS in this environment.

- [ ] **Step 2: Write the failing widget/config test**

```dart
testWidgets('renders the empty application marker', (tester) async {
  await tester.pumpWidget(const TemplateApp());
  expect(find.text('Application'), findsOneWidget);
});

test('uses same-origin defaults', () {
  expect(RuntimeConfig.apiBaseUrl, '/api/');
  expect(RuntimeConfig.natsWebSocketUrl, '/nats/');
});
```

- [ ] **Step 3: Run and verify failure**

Run: `cd app && flutter test`

Expected: FAIL until `TemplateApp` and `RuntimeConfig` exist.

- [ ] **Step 4: Add runtime configuration and abstract boundaries**

```dart
abstract interface class AuthTokenProvider {
  Future<AuthToken> getToken();
}

abstract interface class NatsConnection {
  Future<void> close();
}

abstract interface class NatsConnector {
  Future<NatsConnection> connect(String token);
}
```

Use `String.fromEnvironment` defaults in `RuntimeConfig`. Do not add concrete
implementations or a NATS package.

- [ ] **Step 5: Add the minimal app and Flutter Web container**

Create one `MaterialApp`/`Scaffold` with an `Application` title and neutral
message. `Dockerfile.web` runs:

```text
flutter run -d web-server --web-hostname 0.0.0.0 --web-port 8080
```

- [ ] **Step 6: Run Flutter verification**

Run:

```bash
cd app
dart format --output=none --set-exit-if-changed .
flutter analyze
flutter test
flutter build web
```

Expected: all pass without Android/iOS tooling.

- [ ] **Step 7: Commit**

```bash
git add app
git commit -m "feat: scaffold empty Flutter application"
```

---

### Task 7: NATS, Nginx, and Default Compose Stack

**Files:**
- Create: `infra/nats/nats.conf`
- Create: `infra/nginx/nginx.conf`
- Create: `infra/nginx/conf.d/default.conf`
- Create: `infra/nginx/conf.d/flutter-web.conf`
- Create: `infra/compose.yaml`
- Create: `infra/compose.flutter-web.yaml`
- Create: `infra/scripts/validate-config.sh`

**Interfaces:**
- Consumes: `.env`, backend port 8000, React port 5173, Flutter Web port 8080.
- Produces: native NATS `4222`, monitoring `8222`, Nginx `8081`, both local virtual hosts, and `/nats/` WebSockets.

- [ ] **Step 1: Write the failing configuration validator**

The script must run:

```bash
docker compose --env-file "${repo_root}/.env" -f infra/compose.yaml config --quiet
docker compose --env-file "${repo_root}/.env" -f infra/compose.yaml \
  run --rm nats -t -c /etc/nats/nats.conf
docker compose --env-file "${repo_root}/.env" -f infra/compose.yaml run --rm nginx nginx -t
docker compose --env-file "${repo_root}/.env" -f infra/compose.yaml \
  -f infra/compose.flutter-web.yaml config --quiet
```

The NATS Server 2.14 `-t` flag validates configuration and exits. The validator
must return nonzero on malformed configuration.

- [ ] **Step 2: Run and verify the validator fails**

Run: `bash infra/scripts/validate-config.sh`

Expected: FAIL because Compose and server configuration do not exist.

- [ ] **Step 3: Add explicit NATS configuration**

Define native `4222`, monitoring `8222`, WebSockets `8080` with local
development `no_tls: true`, `AUTH`/`APP`/`SYS` accounts, `system_account: SYS`,
and:

```hcl
authorization {
  auth_callout {
    issuer: $NATS_ACCOUNT_SIGNER_PUBLIC_KEY
    account: AUTH
    auth_users: [ $NATS_AUTH_USER ]
  }
}
```

The `AUTH` account contains only the environment-configured redirect user.
Do not enable JetStream.

- [ ] **Step 4: Add exact Nginx route precedence**

For `localhost`, put `location /nats/` before `location /`. For
`app.localhost`, put exact/prefix health and API routes plus `/nats/` before
the frontend catch-all. NATS proxy settings include:

```nginx
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
proxy_read_timeout 86400s;
proxy_send_timeout 86400s;
proxy_buffering off;
```

Use a URI-preserving `proxy_pass` form verified by the WebSocket smoke test.

- [ ] **Step 5: Add Compose services and health checks**

Use pinned major/minor image lines:

```yaml
postgres: postgres:18-alpine
nats: nats:2.14-alpine
nats-auth-redirect: ezenki/nats-auth-redirector:1.0.0
nginx: nginx:1.30-alpine
nats-smoke: natsio/nats-box:0.19.2
```

Add PostgreSQL `pg_isready`, Django `/health/`, NATS monitoring, React HTTP,
and Nginx virtual-host HTTP health checks. Bind public development ports to
the Dev Container, never `/var/run/docker.sock`. Configure redirector
`AUTH_SERVER=http://backend:8000/api/nats/authorize/`,
`NATS_URL=nats://<auth-user>:<password>@nats:4222`, signer seed, NATS health
dependency, and `restart: unless-stopped`.

- [ ] **Step 6: Add Flutter Web override**

Disable/replace the React dependency, start `app/Dockerfile.web`, and mount or
select `flutter-web.conf`. Preserve `/api/`, `/health/`, and `/nats/`.

- [ ] **Step 7: Validate both configurations**

Run: `bash infra/scripts/validate-config.sh`

Expected: default and override Compose resolution, NATS startup validation,
and both Nginx syntax checks pass.

- [ ] **Step 8: Commit**

```bash
git add infra/nats infra/nginx infra/compose.yaml infra/compose.flutter-web.yaml infra/scripts/validate-config.sh
git commit -m "feat: add local NATS and Nginx stack"
```

---

### Task 8: Full-Stack Authentication and Routing Smoke Checks

**Files:**
- Create: `infra/scripts/smoke-stack.sh`
- Create: `infra/scripts/smoke-flutter-web.sh`

**Interfaces:**
- Consumes: Task 7 Compose services and Task 4 token contract.
- Produces: one-command evidence for host routing, native NATS auth, WebSocket NATS auth, allowed subjects, denied subjects, invalid tokens, and Flutter Web substitution.

- [ ] **Step 1: Write smoke assertions before starting the stack**

The script must use strict mode, trap cleanup only for services it started,
keep JWTs in shell variables without echoing them, and assert:

```bash
curl --fail --header 'Host: localhost' http://127.0.0.1:8081/
curl --fail --header 'Host: app.localhost' http://127.0.0.1:8081/
curl --fail --header 'Host: app.localhost' http://127.0.0.1:8081/health/
```

Extract `.token` and validate `.token_type == "Bearer"` with `jq`.

- [ ] **Step 2: Run and verify the smoke test fails before startup**

Run: `bash infra/scripts/smoke-stack.sh`

Expected: FAIL because the stack is not running or the remaining NATS checks
are not implemented.

- [ ] **Step 3: Implement native and WebSocket NATS checks**

Use the profile-gated `nats-smoke` service. Pass the token only through the
service process environment, never through a command argument. Check:

1. native subscribe/publish round trip on `app.smoke`;
2. WebSocket subscribe/publish through `ws://nginx/nats/`;
3. publish to `forbidden.smoke` returns a permissions error; and
4. a fixed invalid token cannot connect.

Capture command output into temporary files, assert expected exit codes/text,
then delete them. Never enable shell tracing.

- [ ] **Step 4: Run the default smoke workflow**

Run:

```bash
bash infra/scripts/generate-local-env.sh
bash infra/scripts/validate-config.sh
bash infra/scripts/smoke-stack.sh
```

Expected: all checks pass; `docker compose ps` shows healthy infrastructure.

- [ ] **Step 5: Implement and run the Flutter Web smoke workflow**

Start with both Compose files, assert `app.localhost` contains the Flutter
proof-of-life marker, and re-run the application-host `/health/` route plus
the WebSocket NATS authentication check.

Run: `bash infra/scripts/smoke-flutter-web.sh`

Expected: PASS without Android/iOS tooling.

- [ ] **Step 6: Commit**

```bash
git add infra/scripts/smoke-stack.sh infra/scripts/smoke-flutter-web.sh
git commit -m "test: add full-stack authentication smoke checks"
```

---

### Task 9: Architecture, Integration, and Operator Documentation

**Files:**
- Create: `README.md`
- Create: `docs/architecture/local-stack.md`
- Create: `docs/integrations/nats-authentication.md`

**Interfaces:**
- Consumes: all implemented commands, paths, environment keys, routes, and extension points.
- Produces: complete template onboarding, operations, architecture, and customization guidance.

- [ ] **Step 1: Write a documentation acceptance checklist**

Create a temporary reviewer checklist from the specification and verify the
README has sections for purpose, components, startup, Django/Wagtail, React,
Flutter, NATS authentication, Nginx routing, environment variables, extension
locations, verification, troubleshooting, and production separation.

- [ ] **Step 2: Write the root README**

Include exact copy/paste commands for:

```bash
bash infra/scripts/generate-local-env.sh
docker compose --env-file .env -f infra/compose.yaml up --build
docker compose --env-file .env -f infra/compose.yaml down
cd backend && uv run python manage.py createsuperuser
cd web && npm run dev
cd app && flutter run
bash infra/scripts/validate-config.sh
bash infra/scripts/smoke-stack.sh
bash infra/scripts/smoke-flutter-web.sh
```

State prominently:

- use Flutter when the application is primarily mobile-first;
- use React when it is primarily web-first;
- either or both can remain;
- the token issuer is anonymous and development-only;
- custom projects replace the policy/issuer helpers rather than accepting
  caller-provided permissions; and
- production uses separate Nginx/deployment configuration.

- [ ] **Step 3: Write architecture and NATS integration documents**

Document the two-host routing table, native versus WebSocket clients, all
internal/public ports, trust boundaries, credential ownership, the `auth`
cookie/Bearer conflict rule, exact JWT scope, exact redirect response, known
redirector limitations, and links back to the authoritative local contract.

- [ ] **Step 4: Validate every documented command and link**

Run documented validation and component commands. Use:

```bash
rg -n '\]\([^)]*\.md(#[^)]*)?\)' README.md docs
```

Open every relative link target and correct broken commands or paths.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/architecture/local-stack.md docs/integrations/nats-authentication.md
git commit -m "docs: explain template operation and extension"
```

---

### Task 10: Final Verification and Template Audit

**Files:**
- Modify only files whose verification exposes a defect.

**Interfaces:**
- Consumes: the complete repository.
- Produces: evidence that all acceptance criteria pass and the repository remains a reusable base template.

- [ ] **Step 1: Run backend verification**

```bash
cd backend
uv sync --locked
uv run python manage.py test -v 2
uv run python manage.py check
uv run python manage.py makemigrations --check
```

Expected: all pass.

- [ ] **Step 2: Run React verification**

```bash
cd web
npm ci
npm test -- --run
npm run lint
npm run build
```

Expected: all pass.

- [ ] **Step 3: Run Flutter verification**

```bash
cd app
flutter pub get
dart format --output=none --set-exit-if-changed .
flutter analyze
flutter test
flutter build web
```

Expected: all pass without Android/iOS tooling.

- [ ] **Step 4: Run configuration and end-to-end verification**

```bash
bash infra/scripts/validate-config.sh
bash infra/scripts/smoke-stack.sh
bash infra/scripts/smoke-flutter-web.sh
```

Expected: all pass.

- [ ] **Step 5: Audit scope and secrets**

Run:

```bash
git status --short
git diff --check
rg -n 'docker\.sock|JetStream' . \
  --glob '!docs/superpowers/**' --glob '!docs/integrations/nats-auth-redirect.md'
git ls-files '.env' '*.seed' '*.creds'
```

Expected: no host socket, enabled JetStream, placeholders, or tracked generated
secrets. Review any documentation-only mentions rather than blindly removing
valid warnings.

- [ ] **Step 6: Confirm image and dependency versions**

Record `uv lock --check`, `npm outdated` review, `flutter pub outdated` review,
and resolved Compose image tags. Upgrade only within the approved major/minor
boundaries, then rerun the affected checks.

- [ ] **Step 7: Request code review**

Invoke `superpowers:requesting-code-review` against the approved specification
and this plan. Resolve each finding by returning to the test-first steps in the
task that owns the affected file.

- [ ] **Step 8: Commit corrections found by final verification**

```bash
git add <only-the-files-corrected-after-verification>
git commit -m "fix: address final template verification"
```

If verification produced no corrections, record that result in the execution
report and do not create an empty commit.
