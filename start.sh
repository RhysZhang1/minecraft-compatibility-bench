#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# May be invoked from any directory; paths belong to this workspace.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
exec python3 -u "$ROOT/scripts/lifecycle.py" start "$@"
