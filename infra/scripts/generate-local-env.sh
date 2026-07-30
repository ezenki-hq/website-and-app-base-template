#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
local_env_file="${LOCAL_ENV_FILE:-${repo_root}/.env}"

required_keys=(
  DJANGO_SECRET_KEY DJANGO_DEBUG DJANGO_ALLOWED_HOSTS
  POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD POSTGRES_HOST POSTGRES_PORT
  NATS_JWT_SIGNING_SECRET NATS_JWT_ISSUER NATS_JWT_AUDIENCE
  NATS_JWT_TTL_SECONDS NATS_JWT_SUBJECT NATS_ACCOUNT
  NATS_PUBLISH_ALLOW NATS_PUBLISH_DENY NATS_SUBSCRIBE_ALLOW NATS_SUBSCRIBE_DENY
  NATS_AUTH_USER NATS_AUTH_PASSWORD
  NATS_ACCOUNT_SIGNER_SEED NATS_ACCOUNT_SIGNER_PUBLIC_KEY
  VITE_API_BASE_URL VITE_NATS_WEBSOCKET_URL
)

fail() {
  printf '%s\n' "generate-local-env: $*" >&2
  exit 1
}

validate_existing_environment() {
  local key count signer_seed signer_public_key derived_public_key

  for key in "${required_keys[@]}"; do
    count="$(grep -c "^${key}=" "${local_env_file}" || true)"
    [[ "${count}" -eq 1 ]] || fail "${local_env_file} must define ${key} exactly once"
  done

  grep -Eq '^DJANGO_SECRET_KEY=.{32,}$' "${local_env_file}" || fail 'invalid DJANGO_SECRET_KEY'
  grep -Eq '^NATS_JWT_SIGNING_SECRET=.{32,}$' "${local_env_file}" || fail 'invalid NATS_JWT_SIGNING_SECRET'
  grep -Eq '^POSTGRES_PASSWORD=.{32,}$' "${local_env_file}" || fail 'invalid POSTGRES_PASSWORD'
  grep -Eq '^NATS_AUTH_PASSWORD=.{32,}$' "${local_env_file}" || fail 'invalid NATS_AUTH_PASSWORD'
  grep -Eq '^NATS_ACCOUNT_SIGNER_SEED=SA[A-Z0-9]+$' "${local_env_file}" || fail 'invalid NATS_ACCOUNT_SIGNER_SEED'
  grep -Eq '^NATS_ACCOUNT_SIGNER_PUBLIC_KEY=A[A-Z0-9]+$' "${local_env_file}" || fail 'invalid NATS_ACCOUNT_SIGNER_PUBLIC_KEY'

  signer_seed="$(
    sed -n 's/^NATS_ACCOUNT_SIGNER_SEED=//p' "${local_env_file}"
  )"
  signer_public_key="$(
    sed -n 's/^NATS_ACCOUNT_SIGNER_PUBLIC_KEY=//p' "${local_env_file}"
  )"
  if ! derived_public_key="$(
    printf '%s\n' "${signer_seed}" |
      docker run --rm -i natsio/nats-box:0.19.2 \
        nk -inkey /dev/stdin -pubout 2>/dev/null
  )"; then
    fail 'NATS account signer seed could not be validated'
  fi
  [[ "${derived_public_key}" == "${signer_public_key}" ]] ||
    fail 'NATS account signer public key does not match its seed'
}

if [[ -L "${local_env_file}" || -e "${local_env_file}" ]]; then
  [[ ! -L "${local_env_file}" ]] ||
    fail "${local_env_file} must not be a symbolic link"
  [[ -f "${local_env_file}" ]] || fail "${local_env_file} is not a regular file"
  file_mode="$(stat -c '%a' "${local_env_file}")" ||
    fail "could not inspect ${local_env_file} permissions"
  [[ "${file_mode}" == "600" ]] ||
    fail "${local_env_file} must have mode 0600"
  validate_existing_environment
  exit 0
fi

mkdir -p "$(dirname "${local_env_file}")"
temporary_file="$(mktemp "${local_env_file}.tmp.XXXXXX")"
trap 'rm -f "${temporary_file}"' EXIT
chmod 600 "${temporary_file}"

nkey_output="$(docker run --rm natsio/nats-box:0.19.2 nsc generate nkey --account)"
mapfile -t nkey_lines <<< "${nkey_output}"
[[ "${#nkey_lines[@]}" -eq 2 ]] || fail 'nsc did not emit exactly two lines'
[[ "${nkey_lines[0]}" =~ ^SA[A-Z0-9]+$ ]] || fail 'nsc emitted an invalid account seed'
[[ "${nkey_lines[1]}" =~ ^A[A-Z0-9]+$ ]] || fail 'nsc emitted an invalid account public key'

django_secret_key="$(openssl rand -hex 32)"
postgres_password="$(openssl rand -hex 32)"
nats_jwt_signing_secret="$(openssl rand -hex 32)"
nats_auth_password="$(openssl rand -hex 32)"

cat >"${temporary_file}" <<EOF
DJANGO_SECRET_KEY=${django_secret_key}
DJANGO_DEBUG=true
DJANGO_ALLOWED_HOSTS=localhost,app.localhost,backend
POSTGRES_DB=app
POSTGRES_USER=app
POSTGRES_PASSWORD=${postgres_password}
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
NATS_JWT_SIGNING_SECRET=${nats_jwt_signing_secret}
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
NATS_AUTH_PASSWORD=${nats_auth_password}
NATS_ACCOUNT_SIGNER_SEED=${nkey_lines[0]}
NATS_ACCOUNT_SIGNER_PUBLIC_KEY=${nkey_lines[1]}
VITE_API_BASE_URL=/api/
VITE_NATS_WEBSOCKET_URL=/nats/
EOF

mv "${temporary_file}" "${local_env_file}"
trap - EXIT
