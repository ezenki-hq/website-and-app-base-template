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

  awk -v config="${config}" '
    /location \/ws\/events\/[[:space:]]*\{/ {
      locations++
      in_location = 1
      next
    }
    in_location && /}/ { in_location = 0; next }
    in_location {
      if ($0 ~ /proxy_pass http:\/\/backend:8000;/) proxy++
      if ($0 ~ /proxy_set_header Upgrade \$http_upgrade;/) upgrade++
      if ($0 ~ /proxy_set_header Connection "upgrade";/) connection++
      if ($0 ~ /proxy_read_timeout 86400s;/) timeout++
      if ($0 ~ /access_log off;/) access_log++
    }
    END {
      if (locations == 0 || proxy != locations || upgrade != locations ||
          connection != locations || timeout != locations || access_log != locations) {
        printf "incomplete /ws/events/ directives in %s (%d locations)\n", config, locations > "/dev/stderr"
        exit 1
      }
    }
  ' "${config}"
done

printf '%s\n' 'private NATS and WebSocket routing: PASS'
