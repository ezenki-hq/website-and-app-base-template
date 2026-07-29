#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

cd "${repo_root}"

docker compose --env-file "${repo_root}/.env" -f infra/compose.yaml config --quiet
docker compose --env-file "${repo_root}/.env" -f infra/compose.yaml \
  run --rm nats -t -c /etc/nats/nats.conf
docker compose --env-file "${repo_root}/.env" -f infra/compose.yaml \
  run --rm nginx nginx -t
docker compose --env-file "${repo_root}/.env" -f infra/compose.yaml \
  -f infra/compose.flutter-web.yaml config --quiet
docker compose --env-file "${repo_root}/.env" -f infra/compose.yaml \
  -f infra/compose.flutter-web.yaml run --rm nginx nginx -t
