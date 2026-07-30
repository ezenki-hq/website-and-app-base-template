#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
app_root="${repo_root}/app"
dockerfile="${repo_root}/infra/scripts/tests/fixtures/flutter-context.Dockerfile"
sentinel_paths=(
  .dart_tool/context-sentinel
  build/context-sentinel
  .pub-cache/context-sentinel
  .env.context-sentinel
  .idea/context-sentinel
  .vscode/context-sentinel
  android/.gradle/context-sentinel
  android/app/build/context-sentinel
  ios/Pods/context-sentinel
  ios/.symlinks/context-sentinel
  ios/Flutter/ephemeral/context-sentinel
)

cleanup() {
  local sentinel_path

  for sentinel_path in "${sentinel_paths[@]}"; do
    rm -f "${app_root}/${sentinel_path}"
    rmdir --ignore-fail-on-non-empty "$(dirname "${app_root}/${sentinel_path}")" \
      2>/dev/null || true
  done
}
trap cleanup EXIT

for sentinel_path in "${sentinel_paths[@]}"; do
  mkdir -p "$(dirname "${app_root}/${sentinel_path}")"
  touch "${app_root}/${sentinel_path}"
done

docker build \
  --quiet \
  --file "${dockerfile}" \
  --tag billboard-flutter-context-test:local \
  "${app_root}" >/dev/null

printf '%s\n' 'Flutter Docker context exclusions: PASS'
