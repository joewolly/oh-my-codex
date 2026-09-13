#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BOOTSTRAP="$ROOT_DIR/scripts/bootstrap.py"

if [[ ! -f "$BOOTSTRAP" ]]; then
  echo "Oh-My-Codex bootstrap is missing: $BOOTSTRAP" >&2
  exit 2
fi

candidates=()
if [[ -n "${PYTHON:-}" ]]; then
  candidates+=("$PYTHON")
fi
candidates+=(python3.13 python3.12 python3.11 python3)

for candidate in "${candidates[@]}"; do
  if ! command -v "$candidate" >/dev/null 2>&1; then
    continue
  fi
  if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
    exec "$candidate" "$BOOTSTRAP" "$@"
  fi
done

echo "Oh-My-Codex requires Python 3.11 or newer." >&2
echo "Install Python 3.11+ and rerun: bash install.sh" >&2
exit 2
