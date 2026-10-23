#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# 从任意目录调用均可；全部路径以本脚本所在项目为准。
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
exec python3 -u "$ROOT/scripts/lifecycle.py" start "$@"
