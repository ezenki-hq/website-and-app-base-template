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
