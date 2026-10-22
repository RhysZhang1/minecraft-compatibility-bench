#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
exec "$ROOT/.venv/bin/python" "$ROOT/scripts/serve_model.py" "${1:-balanced}"
