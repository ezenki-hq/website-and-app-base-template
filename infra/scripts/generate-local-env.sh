#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
local_env_file="${LOCAL_ENV_FILE:-${repo_root}/.env}"
required_keys=(
  DJANGO_SECRET_KEY EVENTS_JWT_SIGNING_SECRET POSTGRES_PASSWORD
  NATS_BACKEND_PASSWORD DJANGO_DEBUG DJANGO_ALLOWED_HOSTS
  WAGTAIL_SITE_NAME WAGTAILADMIN_BASE_URL POSTGRES_DB POSTGRES_USER
  POSTGRES_HOST POSTGRES_PORT NATS_BACKEND_USER EVENTS_JWT_TTL_SECONDS
  EVENTS_ALLOWED_ORIGINS VITE_API_BASE_URL VITE_EVENTS_WEBSOCKET_URL
)

fail() {
  printf '%s\n' "generate-local-env: $*" >&2
  exit 1
}

validate_existing_environment() {
  local key count
  for key in "${required_keys[@]}"; do
    count="$(grep -c "^${key}=" "${local_env_file}" || true)"
    [[ "${count}" -eq 1 ]] ||
      fail "${local_env_file} must define ${key} exactly once"
  done

  for key in DJANGO_SECRET_KEY EVENTS_JWT_SIGNING_SECRET POSTGRES_PASSWORD NATS_BACKEND_PASSWORD; do
    grep -Eq "^${key}=.{32,}$" "${local_env_file}" || fail "invalid ${key}"
  done
}

if [[ -L "${local_env_file}" || -e "${local_env_file}" ]]; then
  [[ ! -L "${local_env_file}" ]] || fail "${local_env_file} must not be a symbolic link"
  [[ -f "${local_env_file}" ]] || fail "${local_env_file} is not a regular file"
  file_mode="$(stat -c '%a' "${local_env_file}")" ||
    fail "could not inspect ${local_env_file} permissions"
  [[ "${file_mode}" == "600" ]] || fail "${local_env_file} must have mode 0600"
  validate_existing_environment
  exit 0
fi

mkdir -p "$(dirname "${local_env_file}")"
temporary_file="$(mktemp "${local_env_file}.tmp.XXXXXX")"
trap 'rm -f "${temporary_file}"' EXIT
chmod 600 "${temporary_file}"

django_secret_key="$(openssl rand -hex 32)"
events_jwt_signing_secret="$(openssl rand -hex 32)"
postgres_password="$(openssl rand -hex 32)"
nats_backend_password="$(openssl rand -hex 32)"

cat >"${temporary_file}" <<ENV
DJANGO_SECRET_KEY=${django_secret_key}
DJANGO_DEBUG=true
DJANGO_ALLOWED_HOSTS=localhost,app.localhost,backend
WAGTAIL_SITE_NAME=Billboard website
WAGTAILADMIN_BASE_URL=http://localhost:8000
POSTGRES_DB=app
POSTGRES_USER=app
POSTGRES_PASSWORD=${postgres_password}
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
NATS_BACKEND_USER=backend
NATS_BACKEND_PASSWORD=${nats_backend_password}
EVENTS_JWT_SIGNING_SECRET=${events_jwt_signing_secret}
EVENTS_JWT_TTL_SECONDS=3600
EVENTS_ALLOWED_ORIGINS=http://localhost:8081,http://app.localhost:8081
VITE_API_BASE_URL=/api/
VITE_EVENTS_WEBSOCKET_URL=/ws/events/
ENV

mv "${temporary_file}" "${local_env_file}"
trap - EXIT
printf 'generated local environment at %s\n' "${local_env_file}"
