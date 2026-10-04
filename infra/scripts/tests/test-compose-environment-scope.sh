#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
expected_backend_keys='["DJANGO_ALLOWED_HOSTS","DJANGO_DEBUG","DJANGO_SECRET_KEY","EVENTS_ALLOWED_ORIGINS","EVENTS_JWT_SIGNING_SECRET","EVENTS_JWT_TTL_SECONDS","NATS_BACKEND_PASSWORD","NATS_BACKEND_USER","NATS_URL","POSTGRES_DB","POSTGRES_HOST","POSTGRES_PASSWORD","POSTGRES_PORT","POSTGRES_USER","WAGTAILADMIN_BASE_URL","WAGTAIL_SITE_NAME"]'
resolved_config="$(
  env -u WAGTAIL_SITE_NAME -u WAGTAILADMIN_BASE_URL \
    docker compose --env-file "${repo_root}/.env.example" \
    -f "${repo_root}/infra/compose.yaml" config --format json
)"
backend_environment="$(jq -c '.services.backend.environment' <<<"${resolved_config}")"
resolved_backend_keys="$(jq -c 'keys | sort' <<<"${backend_environment}")"

if [[ "${resolved_backend_keys}" != "${expected_backend_keys}" ]]; then
  printf '%s\n' 'backend environment keys do not match the private event stack contract' >&2
  exit 1
fi

legacy_auth_service='nats-auth''-redirect'
if jq -e --arg service "${legacy_auth_service}" '.services | has($service)' <<<"${resolved_config}" >/dev/null; then
  printf '%s\n' 'obsolete NATS auth redirect service is still configured' >&2
  exit 1
fi

if jq -e '.services.nats.ports | length > 0' <<<"${resolved_config}" >/dev/null; then
  printf '%s\n' 'NATS ports must not be published to the host' >&2
  exit 1
fi

web_environment="$(jq -c '.services.web.environment' <<<"${resolved_config}")"
if jq -e 'has("NATS_BACKEND_USER") or has("NATS_BACKEND_PASSWORD") or has("NATS_URL")' \
  <<<"${web_environment}" >/dev/null; then
  printf '%s\n' 'web must not receive NATS credentials or URL' >&2
  exit 1
fi

nats_environment="$(jq -c '.services.nats.environment' <<<"${resolved_config}")"
for key in NATS_BACKEND_USER NATS_BACKEND_PASSWORD; do
  jq -e --arg key "${key}" 'has($key)' <<<"${nats_environment}" >/dev/null || {
    printf 'NATS service is missing %s\n' "${key}" >&2
    exit 1
  }
done

printf '%s\n' 'compose backend environment scope: PASS'
