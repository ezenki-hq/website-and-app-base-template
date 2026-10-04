#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
stack_env_file="${STACK_ENV_FILE:-${repo_root}/.env}"
[[ -f "${stack_env_file}" ]] || {
  printf '%s\n' "smoke-stack: missing ${stack_env_file}; run infra/scripts/generate-local-env.sh first" >&2
  exit 1
}

compose=(
  docker compose
  --env-file "${stack_env_file}"
  -f "${repo_root}/infra/compose.yaml"
)
if [[ "${SMOKE_FLUTTER_WEB:-0}" == "1" ]]; then
  compose+=(-f "${repo_root}/infra/compose.flutter-web.yaml")
fi

declare -a initially_running_services=()
declare -a initially_existing_services=()
temporary_directory=""

cleanup() {
  local service
  local initially_running_service
  local was_initially_running
  local -a currently_running_services=()
  local -a services_started_by_script=()

  set +e
  mapfile -t currently_running_services < <(
    "${compose[@]}" ps --services --filter status=running 2>/dev/null |
      sed '/^$/d' ||
      true
  )

  for service in "${currently_running_services[@]}"; do
    was_initially_running=0
    for initially_running_service in "${initially_running_services[@]}"; do
      if [[ "${service}" == "${initially_running_service}" ]]; then
        was_initially_running=1
        break
      fi
    done
    if [[ "${was_initially_running}" == "0" ]]; then
      services_started_by_script+=("${service}")
    fi
  done

  if ((${#services_started_by_script[@]} > 0)); then
    "${compose[@]}" stop "${services_started_by_script[@]}" >/dev/null
  fi
  if ((${#initially_existing_services[@]} == 0)); then
    "${compose[@]}" down --remove-orphans >/dev/null
  fi
  if [[ -n "${temporary_directory}" ]]; then
    rm -rf "${temporary_directory}"
  fi
}
trap cleanup EXIT

fail() {
  printf '%s\n' "smoke-stack: $*" >&2
  exit 1
}

cd "${repo_root}"
mapfile -t initially_running_services < <(
  "${compose[@]}" ps --services --filter status=running |
    sed '/^$/d'
)
mapfile -t initially_existing_services < <(
  "${compose[@]}" ps --all --services |
    sed '/^$/d'
)
temporary_directory="$(mktemp -d)"

resolved_config="$("${compose[@]}" config --format json)"
jq -e '((.services.nats.ports // []) | length == 0)' \
  <<<"${resolved_config}" >/dev/null ||
  fail 'NATS native or monitoring port is published to the host'

"${compose[@]}" up --detach --build --wait
printf '%s\n' 'PASS Compose services are healthy'
"${compose[@]}" ps

website_page="$(
  curl --fail --silent --show-error \
    --header 'Host: localhost' \
    http://127.0.0.1:8081/
)"
grep -Fq '<h1>Billboard website</h1>' <<<"${website_page}" ||
  fail 'localhost did not return the Wagtail website'

application_page="$(
  curl --fail --silent --show-error \
    --header 'Host: app.localhost' \
    http://127.0.0.1:8081/
)"
health_response="$(
  curl --fail --silent --show-error \
    --header 'Host: app.localhost' \
    http://127.0.0.1:8081/health/
)"
[[ "$(jq --compact-output --sort-keys . <<<"${health_response}")" == \
  '{"status":"ok"}' ]] ||
  fail 'application health route did not return exactly {"status":"ok"}'

admin_page="$(
  curl --fail --location --silent --show-error \
    --header 'Host: localhost' \
    http://127.0.0.1:8081/admin/
)"
grep -Fqi 'Wagtail' <<<"${admin_page}" || fail 'Wagtail admin login did not render'
grep -Fqi 'sign in' <<<"${admin_page}" || fail 'Wagtail admin login did not offer sign in'

wagtail_admin_asset="${temporary_directory}/wagtail-admin-core.css"
curl --fail --silent --show-error \
  --header 'Host: localhost' \
  --output "${wagtail_admin_asset}" \
  http://127.0.0.1:8081/static/wagtailadmin/css/core.css
[[ -s "${wagtail_admin_asset}" ]] || fail 'Wagtail admin static asset was empty'
printf '%s\n' 'PASS Wagtail website, admin, static asset, and exact backend health'

if [[ "${SMOKE_FLUTTER_WEB:-0}" == "1" ]]; then
  grep -Fq '<script src="flutter_bootstrap.js" async></script>' \
    <<<"${application_page}" || fail 'Flutter Web proof-of-life marker was not found'
  printf '%s\n' 'PASS Flutter Web proof-of-life marker'
else
  grep -Fq '<script type="module" src="/src/main.tsx"></script>' \
    <<<"${application_page}" || fail 'React proof-of-life marker was not found'
  printf '%s\n' 'PASS React proof-of-life marker'
fi

smoke_output="${temporary_directory}/event-websocket-smoke.out"
if ! "${compose[@]}" exec -T backend python - >"${smoke_output}" 2>&1 <<'PYTHON_SMOKE'
import asyncio
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

import msgpack
import nats
import sys
import websockets
from django.conf import settings

from events.tokens import issue_event_token
from events.broker import NatsEventBridge

async def main():
    origin = "http://app.localhost:8081"
    token = issue_event_token("smoke", ["app.smoke"])
    uri = f"ws://nginx/ws/events/{token}"
    async with websockets.connect(uri, origin=origin) as websocket:
        connection = await nats.connect(
            servers=settings.NATS_URL,
            user=settings.NATS_BACKEND_USER,
            password=settings.NATS_BACKEND_PASSWORD,
        )
        try:
            await connection.publish(
                "app.smoke", b"\x00smoke", headers={"probe": "yes"}
            )
            await connection.flush()
            raw = await asyncio.wait_for(websocket.recv(), timeout=5)
            if not isinstance(raw, bytes):
                raise AssertionError("event frame was not binary")
            frame = msgpack.unpackb(raw, raw=False)
            if frame != {
                "event": "app.smoke",
                "headers": {"probe": "yes"},
                "message": b"\x00smoke",
            }:
                raise AssertionError("event frame did not match the MessagePack contract")
        finally:
            await connection.close()

    try:
        async with websockets.connect(
            "ws://nginx/ws/events/not-a-valid-token", origin=origin
        ):
            raise AssertionError("malformed token was accepted")
    except websockets.exceptions.InvalidStatus as error:
        if error.response.status_code != 403:
            raise AssertionError("malformed token did not receive HTTP 403") from error

    try:
        async with websockets.connect(f"{uri}/", origin=origin):
            raise AssertionError("malformed event path was accepted")
    except websockets.exceptions.InvalidStatus as error:
        if error.response.status_code != 403:
            raise AssertionError("malformed event path did not receive HTTP 403") from error

    denied_bridge = NatsEventBridge()
    try:
        await asyncio.wait_for(
            denied_bridge.start(
                ("outside.scope",),
                lambda message: asyncio.sleep(0),
                lambda: asyncio.sleep(0),
            ),
            timeout=5,
        )
    except nats.errors.Error as error:
        if "permissions violation" not in str(error).lower():
            raise AssertionError(
                "NATS setup failed for a reason other than permissions"
            ) from error
    else:
        raise AssertionError("NATS permission denial did not fail subscription setup")
    finally:
        await denied_bridge.close()

    print("event websocket smoke: PASS")


try:
    asyncio.run(main())
except Exception as error:
    response = getattr(error, "response", None)
    status = getattr(response, "status_code", None)
    print(f"event probe failed: {type(error).__name__}; status={status}", file=sys.stderr)
    raise
PYTHON_SMOKE
then
  diagnostic="$(grep -F 'event probe failed:' "${smoke_output}" | head -n 1 || true)"
  if [[ -n "${diagnostic}" ]]; then
    fail "${diagnostic}"
  fi
  fail 'Django WebSocket event round trip or malformed-token rejection failed'
fi
grep -Fq 'event websocket smoke: PASS' "${smoke_output}" ||
  fail 'event WebSocket probe did not report success'
backend_logs="$("${compose[@]}" logs --no-color backend 2>&1)"
if grep -Fq '/ws/events/' <<<"${backend_logs}"; then
  fail 'backend logs exposed a WebSocket event token path'
fi
printf '%s\n' 'PASS backend logs do not expose event WebSocket tokens'
printf '%s\n' 'PASS private NATS event through Django WebSocket and Nginx'
printf '%s\n' 'smoke-stack: PASS'
