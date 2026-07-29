import os
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
MANAGEMENT_COMMAND = sys.argv[1] if len(sys.argv) > 1 else ""
USES_EPHEMERAL_DATABASE = MANAGEMENT_COMMAND in {"test", "makemigrations"}

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if MANAGEMENT_COMMAND in {"test", "check", "makemigrations"}:
        SECRET_KEY = "test-only-secret-key"
    else:
        raise RuntimeError("DJANGO_SECRET_KEY must be set for runtime commands")
DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() == "true"
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "wagtail.contrib.forms",
    "wagtail.contrib.redirects",
    "wagtail.embeds",
    "wagtail.sites",
    "wagtail.users",
    "wagtail.snippets",
    "wagtail.documents",
    "wagtail.images",
    "wagtail.search",
    "wagtail.admin",
    "wagtail",
    "modelcluster",
    "taggit",
    "health",
    "home",
    "nats_auth",
]

MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "wagtail.contrib.redirects.middleware.RedirectMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "app"),
        "USER": os.environ.get("POSTGRES_USER", "app"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "postgres"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

if USES_EPHEMERAL_DATABASE:
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
WAGTAIL_SITE_NAME = os.environ.get("WAGTAIL_SITE_NAME", "Billboard website")
WAGTAILADMIN_BASE_URL = os.environ.get("WAGTAILADMIN_BASE_URL", "http://localhost:8000")

NATS_JWT_SIGNING_SECRET = os.environ.get("NATS_JWT_SIGNING_SECRET")
if not NATS_JWT_SIGNING_SECRET:
    if MANAGEMENT_COMMAND in {"test", "check", "makemigrations"}:
        NATS_JWT_SIGNING_SECRET = "test-only-nats-jwt-signing-secret"
    else:
        raise RuntimeError(
            "NATS_JWT_SIGNING_SECRET must be set for runtime commands"
        )
NATS_JWT_ISSUER = os.environ.get("NATS_JWT_ISSUER", "website-app-template")
NATS_JWT_AUDIENCE = os.environ.get("NATS_JWT_AUDIENCE", "nats")
NATS_JWT_TTL_SECONDS = int(os.environ.get("NATS_JWT_TTL_SECONDS", "86400"))
NATS_JWT_SUBJECT = os.environ.get("NATS_JWT_SUBJECT", "development-user")
NATS_ACCOUNT = os.environ.get("NATS_ACCOUNT", "APP")
NATS_PUBLISH_ALLOW = os.environ.get("NATS_PUBLISH_ALLOW", '["app.>"]')
NATS_PUBLISH_DENY = os.environ.get("NATS_PUBLISH_DENY", "[]")
NATS_SUBSCRIBE_ALLOW = os.environ.get("NATS_SUBSCRIBE_ALLOW", '["app.>"]')
NATS_SUBSCRIBE_DENY = os.environ.get("NATS_SUBSCRIBE_DENY", "[]")
