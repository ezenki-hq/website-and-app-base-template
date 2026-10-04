#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
test_dir="$(mktemp -d)"
trap 'rm -rf "${test_dir}"' EXIT

fail() {
  printf '%s\n' "test-generate-local-env: $*" >&2
  exit 1
}

assert_rejected_without_secret_output() {
  local case_name="$1"
  local environment_file="$2"
  local output_file="${test_dir}/${case_name}.out"
  local secret

  secret="$(sed -n 's/^EVENTS_JWT_SIGNING_SECRET=//p' "${environment_file}" | head -n 1)"
  if LOCAL_ENV_FILE="${environment_file}" \
    "${repo_root}/infra/scripts/generate-local-env.sh" \
    >"${output_file}" 2>&1; then
    fail "${case_name} was accepted"
  fi
  if [[ -n "${secret}" ]] && grep -Fq "${secret}" "${output_file}"; then
    fail "${case_name} exposed a secret"
  fi
}

output_file="${test_dir}/generate.out"
LOCAL_ENV_FILE="${test_dir}/.env" \
  "${repo_root}/infra/scripts/generate-local-env.sh" >"${output_file}"
test -s "${test_dir}/.env"
test "$(stat -c '%a' "${test_dir}/.env")" = "600"
for key in DJANGO_SECRET_KEY EVENTS_JWT_SIGNING_SECRET POSTGRES_PASSWORD NATS_BACKEND_PASSWORD; do
  grep -Eq "^${key}=.{32,}$" "${test_dir}/.env" || fail "${key} is missing or weak"
  test "$(grep -c "^${key}=" "${test_dir}/.env")" -eq 1 || fail "${key} is duplicated"
done
grep -Fxq 'NATS_BACKEND_USER=backend' "${test_dir}/.env"
grep -Fxq 'EVENTS_JWT_TTL_SECONDS=3600' "${test_dir}/.env"
grep -Fxq 'EVENTS_ALLOWED_ORIGINS=http://localhost:8081,http://app.localhost:8081' "${test_dir}/.env"
grep -Fxq 'VITE_EVENTS_WEBSOCKET_URL=/ws/events/' "${test_dir}/.env"
legacy_jwt_prefix='NATS_JWT''_'
if grep -Eq "NATS_ACCOUNT_SIGNER|NATS_AUTH_|VITE_NATS|${legacy_jwt_prefix}" "${test_dir}/.env"; then
  fail 'obsolete NATS auth variables remain in generated environment'
fi

before="$(sha256sum "${test_dir}/.env")"
LOCAL_ENV_FILE="${test_dir}/.env" \
  "${repo_root}/infra/scripts/generate-local-env.sh"
after="$(sha256sum "${test_dir}/.env")"
test "${before}" = "${after}"

cp "${test_dir}/.env" "${test_dir}/weak.env"
sed -i 's/^EVENTS_JWT_SIGNING_SECRET=.*/EVENTS_JWT_SIGNING_SECRET=weak/' "${test_dir}/weak.env"
assert_rejected_without_secret_output weak "${test_dir}/weak.env"

cp "${test_dir}/.env" "${test_dir}/duplicate.env"
printf '%s\n' 'EVENTS_JWT_SIGNING_SECRET=another-weak-secret' >>"${test_dir}/duplicate.env"
assert_rejected_without_secret_output duplicate "${test_dir}/duplicate.env"

cp "${test_dir}/.env" "${test_dir}/permissive.env"
chmod 0640 "${test_dir}/permissive.env"
assert_rejected_without_secret_output permissive-mode "${test_dir}/permissive.env"

ln -s "${test_dir}/.env" "${test_dir}/symlink.env"
if LOCAL_ENV_FILE="${test_dir}/symlink.env" \
  "${repo_root}/infra/scripts/generate-local-env.sh" >"${test_dir}/symlink.out" 2>&1; then
  fail 'symlink environment file was accepted'
fi

cat >"${test_dir}/old-format.env" <<'OLD_ENV'
DJANGO_SECRET_KEY=legacy
NATS_AUTH_PASSWORD=legacy
OLD_ENV
printf '%s\n' 'NATS_JWT''_SIGNING_SECRET=legacy' >>"${test_dir}/old-format.env"
chmod 0600 "${test_dir}/old-format.env"
old_hash="$(sha256sum "${test_dir}/old-format.env")"
if LOCAL_ENV_FILE="${test_dir}/old-format.env" \
  "${repo_root}/infra/scripts/generate-local-env.sh" >"${test_dir}/old-format.out" 2>&1; then
  fail 'old environment format was accepted'
fi
grep -Fq 'EVENTS_JWT_SIGNING_SECRET' "${test_dir}/old-format.out" ||
  fail 'old format failure did not name the missing new key'
test "${old_hash}" = "$(sha256sum "${test_dir}/old-format.env")"

if grep -Eq '^[A-Z0-9_]*(SECRET|PASSWORD)=[[:alnum:]]{32,}' "${output_file}"; then
  fail 'generation output contains a secret assignment'
fi

printf '%s\n' 'generate-local-env regression checks: PASS'
