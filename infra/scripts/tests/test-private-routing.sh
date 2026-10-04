#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
nats_config_dir="${repo_root}/infra/"nats
nats_config="${nats_config_dir}/nats.conf"

if grep -Eq '^[[:space:]]*websocket[[:space:]]*\{' "${nats_config}"; then
  printf '%s\n' 'NATS WebSocket listener must be disabled' >&2
  exit 1
fi

grep -Eq 'publish[[:space:]]*:[[:space:]]*\{[[:space:]]*allow:[[:space:]]*\["app\.>"\]' "${nats_config}" || {
  printf '%s\n' 'NATS publish permissions must allow only app.>' >&2
  exit 1
}
grep -Eq 'subscribe[[:space:]]*:[[:space:]]*\{[[:space:]]*allow:[[:space:]]*\["app\.>"\]' "${nats_config}" || {
  printf '%s\n' 'NATS subscribe permissions must allow only app.>' >&2
  exit 1
}

legacy_nats_path='/'nats'/'
for config in "${repo_root}/infra/nginx/conf.d/default.conf" \
  "${repo_root}/infra/nginx/conf.d/flutter-web.conf"; do
  if grep -Fq "${legacy_nats_path}" "${config}"; then
    printf 'obsolete NATS proxy remains in %s\n' "${config}" >&2
    exit 1
  fi

  ws_location="$(awk '
    /location \/ws\/events\// { in_location = 1 }
    in_location { print }
    in_location && /}/ { exit }
  ' "${config}")"
  [[ -n "${ws_location}" ]] || {
    printf 'missing /ws/events/ location in %s\n' "${config}" >&2
    exit 1
  }
  grep -Fq 'proxy_pass http://backend:8000;' <<<"${ws_location}" || {
    printf 'WebSocket route does not target Django in %s\n' "${config}" >&2
    exit 1
  }
  grep -Fq 'proxy_set_header Upgrade $http_upgrade;' <<<"${ws_location}" || {
    printf 'WebSocket upgrade header missing in %s\n' "${config}" >&2
    exit 1
  }
  grep -Fq 'proxy_set_header Connection "upgrade";' <<<"${ws_location}" || {
    printf 'WebSocket connection header missing in %s\n' "${config}" >&2
    exit 1
  }
  grep -Fq 'proxy_read_timeout 86400s;' <<<"${ws_location}" || {
    printf 'long WebSocket read timeout missing in %s\n' "${config}" >&2
    exit 1
  }
  grep -Fq 'access_log off;' <<<"${ws_location}" || {
    printf 'test_ws_route_has_no_access_log failed for %s\n' "${config}" >&2
    exit 1
  }
done

printf '%s\n' 'private NATS and WebSocket routing: PASS'
