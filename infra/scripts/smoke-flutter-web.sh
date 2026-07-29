#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

cd "${repo_root}"
SMOKE_FLUTTER_WEB=1 bash "${repo_root}/infra/scripts/smoke-stack.sh"
printf '%s\n' 'smoke-flutter-web: PASS'
