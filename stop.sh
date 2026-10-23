#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# 使用系统 Python，环境或模型服务损坏时仍可停止。
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
exec python3 -u "$ROOT/scripts/lifecycle.py" stop "$@"
