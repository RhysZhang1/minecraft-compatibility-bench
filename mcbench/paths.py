# SPDX-License-Identifier: GPL-3.0-or-later
"""Resolve mutable workspace data separately from installed Python code."""

import os
from pathlib import Path


def workspace() -> Path:
    """Use an explicit workspace, a source checkout, or the caller's directory.

    Wheels support offline APIs from any directory. Live tools additionally need
    a source workspace containing the Java/native sources and configuration.
    """
    if configured := os.environ.get("MCBENCH_WORKSPACE"):
        return Path(configured).expanduser().resolve()
    checkout = Path(__file__).resolve().parent.parent
    if (checkout / "instance-settings.json").is_file():
        return checkout
    return Path.cwd()


ROOT = workspace()
