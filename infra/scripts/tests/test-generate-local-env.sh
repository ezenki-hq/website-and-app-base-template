#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
test_dir="$(mktemp -d)"
trap 'rm -rf "${test_dir}"' EXIT

fail() {
  printf '%s\n' "test-generate-local-env: $*" >&2
  exit 1
}

assert_validation_fails_without_material() {
  local case_name="$1"
  local environment_file="$2"
  local output_file="${test_dir}/${case_name}.out"
  local signer_seed
  local signer_public_key

  signer_seed=""
  signer_public_key=""
  if [[ -f "${environment_file}" ]]; then
    signer_seed="$(
      sed -n 's/^NATS_ACCOUNT_SIGNER_SEED=//p' "${environment_file}"
    )"
    signer_public_key="$(
      sed -n 's/^NATS_ACCOUNT_SIGNER_PUBLIC_KEY=//p' "${environment_file}"
    )"
  fi

  if LOCAL_ENV_FILE="${environment_file}" \
    "${repo_root}/infra/scripts/generate-local-env.sh" \
    >"${output_file}" 2>&1; then
    fail "${case_name} was accepted"
  fi

  if [[ -n "${signer_seed}" ]] &&
    grep -Fq "${signer_seed}" "${output_file}"; then
    fail "${case_name} exposed signer material"
  fi
  if [[ -n "${signer_public_key}" ]] &&
    grep -Fq "${signer_public_key}" "${output_file}"; then
    fail "${case_name} exposed signer material"
  fi
}

LOCAL_ENV_FILE="${test_dir}/.env" \
  "${repo_root}/infra/scripts/generate-local-env.sh"

test -s "${test_dir}/.env"
test "$(stat -c '%a' "${test_dir}/.env")" = "600"
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

replacement_nkey_output="$(
  docker run --rm natsio/nats-box:0.19.2 nsc generate nkey --account
)"
replacement_public_key="$(sed -n '2p' <<<"${replacement_nkey_output}")"
unset replacement_nkey_output
grep -Eq '^A[A-Z0-9]+$' <<<"${replacement_public_key}"

cp "${test_dir}/.env" "${test_dir}/mismatched.env"
sed -i \
  "s/^NATS_ACCOUNT_SIGNER_PUBLIC_KEY=.*/NATS_ACCOUNT_SIGNER_PUBLIC_KEY=${replacement_public_key}/" \
  "${test_dir}/mismatched.env"
assert_validation_fails_without_material mismatched-signer "${test_dir}/mismatched.env"
unset replacement_public_key

cp "${test_dir}/.env" "${test_dir}/permissive.env"
chmod 0640 "${test_dir}/permissive.env"
assert_validation_fails_without_material permissive-mode "${test_dir}/permissive.env"

ln -s "${test_dir}/.env" "${test_dir}/symlink.env"
assert_validation_fails_without_material symlink "${test_dir}/symlink.env"

mkdir "${test_dir}/directory.env"
assert_validation_fails_without_material non-regular "${test_dir}/directory.env"

printf '%s\n' 'generate-local-env regression checks: PASS'
