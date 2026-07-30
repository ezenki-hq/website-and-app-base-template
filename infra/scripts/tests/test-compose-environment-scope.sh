#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
expected_backend_keys='["DJANGO_ALLOWED_HOSTS","DJANGO_DEBUG","DJANGO_SECRET_KEY","NATS_ACCOUNT","NATS_JWT_AUDIENCE","NATS_JWT_ISSUER","NATS_JWT_SIGNING_SECRET","NATS_JWT_SUBJECT","NATS_JWT_TTL_SECONDS","NATS_PUBLISH_ALLOW","NATS_PUBLISH_DENY","NATS_SUBSCRIBE_ALLOW","NATS_SUBSCRIBE_DENY","POSTGRES_DB","POSTGRES_HOST","POSTGRES_PASSWORD","POSTGRES_PORT","POSTGRES_USER","WAGTAILADMIN_BASE_URL","WAGTAIL_SITE_NAME"]'

default_backend_environment="$(
  env -u WAGTAIL_SITE_NAME -u WAGTAILADMIN_BASE_URL \
    docker compose \
    --env-file "${repo_root}/.env.example" \
    -f "${repo_root}/infra/compose.yaml" \
    config --format json |
    jq -c '.services.backend.environment'
)"
resolved_backend_keys="$(
  jq -c 'keys | sort' <<<"${default_backend_environment}"
)"

if [[ "${resolved_backend_keys}" != "${expected_backend_keys}" ]]; then
  printf '%s\n' \
    'backend must receive only the Django, Wagtail, database, client-JWT, and NATS policy environment keys' \
    >&2
  exit 1
fi

if [[ "$(
  jq -r '.WAGTAIL_SITE_NAME // ""' <<<"${default_backend_environment}"
)" != "Billboard website" ]] ||
  [[ "$(
    jq -r '.WAGTAILADMIN_BASE_URL // ""' <<<"${default_backend_environment}"
  )" != "http://localhost:8000" ]]; then
  printf '%s\n' 'backend Wagtail environment defaults do not match Django' >&2
  exit 1
fi

override_backend_environment="$(
  WAGTAIL_SITE_NAME="Custom billboard" \
    WAGTAILADMIN_BASE_URL="http://admin.app.localhost" \
    docker compose \
    --env-file "${repo_root}/.env.example" \
    -f "${repo_root}/infra/compose.yaml" \
    config --format json |
    jq -c '.services.backend.environment'
)"

if [[ "$(
  jq -r '.WAGTAIL_SITE_NAME // ""' <<<"${override_backend_environment}"
)" != "Custom billboard" ]] ||
  [[ "$(
    jq -r '.WAGTAILADMIN_BASE_URL // ""' <<<"${override_backend_environment}"
  )" != "http://admin.app.localhost" ]]; then
  printf '%s\n' 'backend Wagtail environment overrides did not resolve' >&2
  exit 1
fi

printf '%s\n' 'compose backend environment scope: PASS'
