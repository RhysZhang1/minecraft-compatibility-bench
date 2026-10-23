#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# System Python can stop the workspace even if its environment is damaged.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
exec python3 -u "$ROOT/scripts/lifecycle.py" stop "$@"
