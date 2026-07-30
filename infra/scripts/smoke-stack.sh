#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
compose=(
  docker compose
  --env-file "${repo_root}/.env"
  -f "${repo_root}/infra/compose.yaml"
)
if [[ "${SMOKE_FLUTTER_WEB:-0}" == "1" ]]; then
  compose+=(-f "${repo_root}/infra/compose.flutter-web.yaml")
fi
smoke_compose=("${compose[@]}" --profile smoke)
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

run_native_round_trip() {
  local output_file="${temporary_directory}/native-round-trip.out"

  # shellcheck disable=SC2016 # This script is expanded by the container shell.
  if ! "${smoke_compose[@]}" run --rm --no-deps \
    -e NATS_TOKEN \
    nats-smoke \
    sh -ec '
      subscriber_output="$(mktemp)"
      publisher_output="$(mktemp)"
      subscriber_pid=""
      subscriber_ready=0
      attempt=0
      cleanup_native() {
        cleanup_attempt=0
        if [ -n "${subscriber_pid}" ]; then
          kill "${subscriber_pid}" 2>/dev/null || true
          while kill -0 "${subscriber_pid}" 2>/dev/null &&
            [ "${cleanup_attempt}" -lt 20 ]; do
            cleanup_attempt=$((cleanup_attempt + 1))
            sleep 0.1
          done
          kill -KILL "${subscriber_pid}" 2>/dev/null || true
          wait "${subscriber_pid}" 2>/dev/null || true
        fi
        rm -f "${subscriber_output}" "${publisher_output}"
      }
      trap cleanup_native EXIT

      nats --server nats://nats:4222 \
        subscribe app.smoke --count 1 \
        >"${subscriber_output}" 2>&1 &
      subscriber_pid=$!

      while [ "${attempt}" -lt 50 ]; do
        if grep -q "Subscribing on app.smoke" "${subscriber_output}"; then
          subscriber_ready=1
          break
        fi
        kill -0 "${subscriber_pid}" 2>/dev/null || exit 1
        attempt=$((attempt + 1))
        sleep 0.1
      done
      [ "${subscriber_ready}" -eq 1 ]

      nats --server nats://nats:4222 \
        publish app.smoke native-smoke-message \
        >"${publisher_output}" 2>&1

      timeout 5 sh -c \
        '"'"'while kill -0 "$1" 2>/dev/null; do sleep 0.1; done'"'"' \
        _ "${subscriber_pid}"
      wait "${subscriber_pid}"
      subscriber_pid=""
      grep -Fq native-smoke-message "${subscriber_output}"
    ' >"${output_file}" 2>&1; then
    fail 'native NATS subscribe/publish round trip failed'
  fi

  printf '%s\n' 'PASS native NATS authentication and app.smoke round trip'
}

run_websocket_exchange() {
  local mode="$1"
  local output_file="$2"
  local command_status

  export WS_SMOKE_MODE="${mode}"
  set +e
  "${smoke_compose[@]}" run --rm --no-deps \
    -e NATS_TOKEN \
    -e WS_SMOKE_MODE \
    nats-smoke \
    sh -s >"${output_file}" 2>&1 <<'WS_CLIENT'
set -eu

temporary_directory="$(mktemp -d)"
client_input="${temporary_directory}/client-input"
server_output="${temporary_directory}/server-output"
network_pid=""
client_fd_open=0

stop_network_process() {
  cleanup_attempt=0
  if [ -n "${network_pid}" ]; then
    kill "${network_pid}" 2>/dev/null || true
    while kill -0 "${network_pid}" 2>/dev/null &&
      [ "${cleanup_attempt}" -lt 20 ]; do
      cleanup_attempt=$((cleanup_attempt + 1))
      sleep 0.1
    done
    kill -KILL "${network_pid}" 2>/dev/null || true
    wait "${network_pid}" 2>/dev/null || true
    network_pid=""
  fi
}

cleanup_websocket() {
  if [ "${client_fd_open}" -eq 1 ]; then
    exec 3>&-
  fi
  stop_network_process
  rm -rf "${temporary_directory}"
}
trap cleanup_websocket EXIT

write_byte() {
  byte_value="$1"
  printf "\\$(printf '%03o' "${byte_value}")"
}

wait_for_output() {
  output_pattern="$1"
  attempt=0

  while [ "${attempt}" -lt 60 ]; do
    if grep -aFq "${output_pattern}" "${server_output}"; then
      return 0
    fi
    kill -0 "${network_pid}" 2>/dev/null || break
    attempt=$((attempt + 1))
    sleep 0.1
  done

  grep -aFq "${output_pattern}" "${server_output}"
}

wait_for_http_headers() {
  attempt=0

  while [ "${attempt}" -lt 60 ]; do
    if od -An -v -tx1 "${server_output}" |
      tr -d ' \n' |
      grep -q '0d0a0d0a'; then
      return 0
    fi
    kill -0 "${network_pid}" 2>/dev/null || break
    attempt=$((attempt + 1))
    sleep 0.1
  done

  return 1
}

write_masked_websocket_frame() {
  frame_payload="$1"
  frame_length="${#frame_payload}"
  set -- $(od -An -N4 -tu1 /dev/urandom)
  mask_1="$1"
  mask_2="$2"
  mask_3="$3"
  mask_4="$4"

  write_byte 130
  if [ "${frame_length}" -le 125 ]; then
    write_byte "$((128 + frame_length))"
  elif [ "${frame_length}" -le 65535 ]; then
    write_byte 254
    write_byte "$((frame_length / 256))"
    write_byte "$((frame_length % 256))"
  else
    printf '%s\n' 'websocket payload is unexpectedly large' >&2
    exit 1
  fi

  write_byte "${mask_1}"
  write_byte "${mask_2}"
  write_byte "${mask_3}"
  write_byte "${mask_4}"
  printf '%s' "${frame_payload}" |
    od -An -v -tu1 |
    awk \
      -v mask_1="${mask_1}" \
      -v mask_2="${mask_2}" \
      -v mask_3="${mask_3}" \
      -v mask_4="${mask_4}" \
      '
      BEGIN {
        mask[1] = mask_1
        mask[2] = mask_2
        mask[3] = mask_3
        mask[4] = mask_4
        offset = 0
      }
      {
        for (field = 1; field <= NF; field++) {
          printf "%c", xor($field, mask[(offset % 4) + 1])
          offset++
        }
      }
    '
}

connect_line="$(printf \
  'CONNECT {"verbose":false,"pedantic":false,"auth_token":"%s","lang":"smoke-shell","version":"1.0","protocol":1,"echo":true}\r\n_' \
  "${NATS_TOKEN}")"
connect_line="${connect_line%_}"
if [ "${WS_SMOKE_MODE}" = "round-trip" ]; then
  protocol_payload="$(
    printf '%sSUB app.smoke 1\r\nPUB app.smoke 16\r\nws-smoke-message\r\nPING\r\n_' \
      "${connect_line}"
  )"
else
  protocol_payload="$(printf '%sPING\r\n_' "${connect_line}")"
fi
protocol_payload="${protocol_payload%_}"
websocket_key="$(head -c 16 /dev/urandom | base64)"
expected_websocket_accept="$(
  printf '%s' \
    "${websocket_key}258EAFA5-E914-47DA-95CA-C5AB0DC85B11" |
    sha1sum |
    awk '{print $1}' |
    xxd -r -p |
    base64
)"

mkfifo "${client_input}"
nc -w 4 nginx 80 <"${client_input}" >"${server_output}" &
network_pid=$!
exec 3>"${client_input}"
client_fd_open=1

printf '%s\r\n' \
  'GET /nats/ HTTP/1.1' \
  'Host: nginx' \
  'Upgrade: websocket' \
  'Connection: Upgrade' \
  "Sec-WebSocket-Key: ${websocket_key}" \
  'Sec-WebSocket-Version: 13' \
  'Sec-WebSocket-Protocol: nats' \
  '' >&3

wait_for_http_headers
http_status="$(sed -n '1{s/\r$//;p;}' "${server_output}")"
actual_websocket_accept="$(
  sed -n 's/^Sec-WebSocket-Accept: //p' "${server_output}" |
    tr -d '\r' |
    head -n 1
)"
[ "${http_status}" = 'HTTP/1.1 101 Switching Protocols' ]
[ "${actual_websocket_accept}" = "${expected_websocket_accept}" ]

write_masked_websocket_frame "${protocol_payload}" >&3
if [ "${WS_SMOKE_MODE}" = "round-trip" ]; then
  wait_for_output 'ws-smoke-message'
else
  wait_for_output 'Authorization Violation'
fi

exec 3>&-
client_fd_open=0
stop_network_process
cat "${server_output}"
WS_CLIENT
  command_status=$?
  set -e
  unset WS_SMOKE_MODE
  return "${command_status}"
}

run_websocket_round_trip() {
  local output_file="${temporary_directory}/websocket-round-trip.out"

  if ! run_websocket_exchange round-trip "${output_file}"; then
    fail 'WebSocket NATS client failed'
  fi
  grep -aFq '101 Switching Protocols' "${output_file}" ||
    fail 'WebSocket upgrade through /nats/ was not accepted'
  grep -aFq 'MSG app.smoke 1 16' "${output_file}" ||
    fail 'WebSocket NATS subscription did not receive app.smoke'
  grep -aFq 'ws-smoke-message' "${output_file}" ||
    fail 'WebSocket NATS message payload did not round trip'
  if grep -aiq 'Authorization Violation' "${output_file}"; then
    fail 'valid token was rejected over WebSocket'
  fi

  printf '%s\n' 'PASS WebSocket NATS authentication and /nats/ round trip'
}

run_forbidden_publish_check() {
  local output_file="${temporary_directory}/forbidden-publish.out"
  local command_status

  set +e
  "${smoke_compose[@]}" run --rm --no-deps \
    -e NATS_TOKEN \
    nats-smoke \
    nats --server nats://nats:4222 \
    publish forbidden.smoke forbidden-smoke-message \
    >"${output_file}" 2>&1
  command_status=$?
  set -e

  [[ "${command_status}" -ne 0 ]] ||
    fail 'forbidden NATS publish unexpectedly exited successfully'
  grep -Eiq 'permissions violation|permission denied' "${output_file}" ||
    fail 'forbidden NATS publish did not return a permissions error'

  printf '%s\n' 'PASS forbidden.smoke publish denied'
}

run_invalid_token_check() {
  local output_file="${temporary_directory}/invalid-token.out"
  local valid_token="${NATS_TOKEN}"

  NATS_TOKEN='fixed-invalid-smoke-token'
  export NATS_TOKEN
  if ! run_websocket_exchange invalid-token "${output_file}"; then
    NATS_TOKEN="${valid_token}"
    export NATS_TOKEN
    fail 'invalid-token WebSocket probe did not complete'
  fi
  NATS_TOKEN="${valid_token}"
  export NATS_TOKEN

  grep -aFq '101 Switching Protocols' "${output_file}" ||
    fail 'invalid-token probe did not reach the /nats/ WebSocket route'
  grep -aiq 'Authorization Violation' "${output_file}" ||
    fail 'fixed invalid token was not rejected'
  if grep -aFq 'MSG app.smoke' "${output_file}"; then
    fail 'fixed invalid token received an application message'
  fi

  printf '%s\n' 'PASS fixed invalid token rejected'
}

cd "${repo_root}"
[[ -f "${repo_root}/.env" ]] ||
  fail 'missing .env; run infra/scripts/generate-local-env.sh first'
mapfile -t initially_running_services < <(
  "${compose[@]}" ps --services --filter status=running |
    sed '/^$/d'
)
mapfile -t initially_existing_services < <(
  "${compose[@]}" ps --all --services |
    sed '/^$/d'
)
temporary_directory="$(mktemp -d)"

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
grep -Fqi 'Wagtail' <<<"${admin_page}" ||
  fail 'Wagtail admin login did not render'
grep -Fqi 'sign in' <<<"${admin_page}" ||
  fail 'Wagtail admin login did not offer sign in'

wagtail_admin_asset="${temporary_directory}/wagtail-admin-core.css"
curl --fail --silent --show-error \
  --header 'Host: localhost' \
  --output "${wagtail_admin_asset}" \
  http://127.0.0.1:8081/static/wagtailadmin/css/core.css
[[ -s "${wagtail_admin_asset}" ]] ||
  fail 'Wagtail admin static asset was empty'

printf '%s\n' \
  'PASS Wagtail website, admin, static asset, and exact backend health'

if [[ "${SMOKE_FLUTTER_WEB:-0}" == "1" ]]; then
  grep -Fq '<script src="flutter_bootstrap.js" async></script>' \
    <<<"${application_page}" ||
    fail 'Flutter Web proof-of-life marker was not found'
  printf '%s\n' 'PASS Flutter Web proof-of-life marker'
else
  grep -Fq '<script type="module" src="/src/main.tsx"></script>' \
    <<<"${application_page}" ||
    fail 'React proof-of-life marker was not found'
  printf '%s\n' 'PASS React proof-of-life marker'
fi

token_response="$(
  curl --fail --silent --show-error \
    --header 'Host: app.localhost' \
    http://127.0.0.1:8081/api/nats/token/
)"
token_type="$(
  jq --exit-status --raw-output '.token_type | select(. == "Bearer")' \
    <<<"${token_response}"
)"
[[ "${token_type}" == "Bearer" ]] || fail 'token_type was not Bearer'
NATS_TOKEN="$(
  jq --exit-status --raw-output \
    '.token | select(type == "string" and length > 0)' \
    <<<"${token_response}"
)"
[[ -n "${NATS_TOKEN}" ]] || fail 'token endpoint returned an empty token'
export NATS_TOKEN
unset token_response
printf '%s\n' 'PASS bearer token contract'

run_native_round_trip
run_websocket_round_trip
run_forbidden_publish_check
run_invalid_token_check

unset NATS_TOKEN
printf '%s\n' 'smoke-stack: PASS'
