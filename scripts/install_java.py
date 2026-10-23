# SPDX-License-Identifier: GPL-3.0-or-later
"""Backward-compatible workspace launcher; implementation lives in mcbench.tools."""

import os
import sys
from pathlib import Path

if __name__ == "__main__":
    workspace = Path(__file__).resolve().parents[1]
    os.environ["MCBENCH_WORKSPACE"] = str(workspace)
    os.chdir(workspace)
    os.execv(sys.executable, [sys.executable, "-m", "mcbench.tools.install_java", *sys.argv[1:]])
